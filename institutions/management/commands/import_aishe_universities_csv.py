import csv
import re
from difflib import SequenceMatcher
from pathlib import Path

import openpyxl
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from institutions.models import University, DataSource, UniversityType


AISHE_HEADERS = [
    "Aishe Code",
    "Name",
    "State",
    "District",
    "Website",
    "Year Of Establishment",
    "Location",
]


def clean_text(value):
    if value is None:
        return ""

    value = str(value)
    value = value.replace("\ufeff", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def limit_text(value, max_length):
    value = clean_text(value)

    if len(value) <= max_length:
        return value

    return value[:max_length]


def normalize_key(value):
    value = clean_text(value).lower()
    value = value.replace(".", "")
    value = value.replace("_", "")
    value = value.replace("-", "")
    value = value.replace("/", "")
    value = value.replace(" ", "")
    return value


def normalize_state(value):
    value = clean_text(value).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_university_name(value):
    """
    Used only for matching names safely.

    Handles:
    - H/h case difference
    - punctuation difference
    - extra spaces
    - '&' vs 'and'
    - common university suffix differences

    It does NOT do unsafe random partial matching.
    """

    value = clean_text(value).lower()

    value = value.replace("&", " and ")

    # remove bracket text
    value = re.sub(r"\([^)]*\)", " ", value)

    # normalize punctuation
    value = re.sub(r"[^a-z0-9]+", " ", value)

    # remove common noise words
    noise_words = {
        "the",
        "university",
        "universities",
        "deemed",
        "to",
        "be",
        "deemedtobe",
        "deemed-to-be",
        "private",
        "state",
        "central",
        "institute",
        "institution",
    }

    words = []
    for word in value.split():
        if word not in noise_words:
            words.append(word)

    value = " ".join(words)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_row(row):
    normalized = {}

    for key, value in row.items():
        normalized[normalize_key(key)] = clean_text(value)

    return normalized


def get_value(row, possible_keys):
    for key in possible_keys:
        value = row.get(normalize_key(key))

        if value:
            return value

    return ""


def clean_url(value):
    value = clean_text(value)

    if not value:
        return ""

    if value.lower() in ["na", "n/a", "-", "nil", "null"]:
        return ""

    if value.startswith("http://") or value.startswith("https://"):
        return value

    if value.startswith("www."):
        return f"https://{value}"

    return ""


def read_csv_rows(file_path):
    """
    Reads CSV with multiple encoding fallbacks.

    Some government exports are not UTF-8, so utf-8-sig can fail.
    """

    encodings = ["utf-8-sig", "utf-8", "cp1252", "latin1"]

    last_error = None

    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding, newline="") as csv_file:
                reader = csv.DictReader(csv_file)

                if not reader.fieldnames:
                    return []

                return list(reader)

        except UnicodeDecodeError as error:
            last_error = error

    raise CommandError(
        f"Could not read CSV file because of encoding issue: {file_path}. "
        f"Last error: {last_error}"
    )


def read_xlsx_rows(file_path):
    """
    Reads AISHE Excel file.

    AISHE file has first two title rows:
    Row 1: ALL UNIVERSITIES
    Row 2: As on Date...
    Row 3: Actual headers
    """

    workbook = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    sheet = workbook.active

    rows = list(sheet.iter_rows(values_only=True))

    header_index = None
    headers = None

    for index, row in enumerate(rows):
        row_values = [clean_text(cell) for cell in row]

        normalized_values = [normalize_key(cell) for cell in row_values]

        if "aishecode" in normalized_values and "name" in normalized_values:
            header_index = index
            headers = row_values
            break

    if header_index is None or not headers:
        raise CommandError(
            "Could not find AISHE header row in Excel file. "
            "Expected columns like: Aishe Code, Name, State, District, Website."
        )

    data_rows = []

    for row in rows[header_index + 1:]:
        values = [clean_text(cell) for cell in row]

        if not any(values):
            continue

        raw_row = {}

        for key, value in zip(headers, values):
            if key:
                raw_row[key] = value

        data_rows.append(raw_row)

    return data_rows


def read_input_rows(file_path):
    suffix = file_path.suffix.lower()

    if suffix == ".xlsx":
        return read_xlsx_rows(file_path)

    if suffix == ".csv":
        return read_csv_rows(file_path)

    raise CommandError(
        f"Unsupported file type: {suffix}. Use .xlsx or .csv"
    )


def build_university_index():
    """
    Build safe lookup maps once.

    This avoids querying DB repeatedly and also avoids unsafe fuzzy matching.
    """

    index = {
        "exact_name_state": {},
        "normalized_name_state": {},
        "normalized_name": {},
        "all": [],
    }

    universities = University.objects.all().only(
        "id",
        "name",
        "state",
        "university_type",
    )

    for university in universities:
        name_clean = clean_text(university.name).lower()
        state_clean = normalize_state(university.state)
        normalized_name = normalize_university_name(university.name)

        if name_clean and state_clean:
            index["exact_name_state"][(name_clean, state_clean)] = university

        if normalized_name and state_clean:
            index["normalized_name_state"][(normalized_name, state_clean)] = university

        if normalized_name:
            index["normalized_name"].setdefault(normalized_name, []).append(university)

        index["all"].append(
            {
                "university": university,
                "normalized_name": normalized_name,
                "state": state_clean,
            }
        )

    return index


def find_matching_university(name, state, university_index):
    """
    Safe matching priority:

    1. Exact name + exact state
    2. Normalized name + exact state
    3. Normalized name only, only if one result
    4. High-confidence fuzzy match inside same state only

    We avoid loose contains matching because it can map wrong universities.
    """

    name = clean_text(name)
    state = clean_text(state)

    if not name:
        return None, "empty_name", 0

    name_lower = name.lower()
    normalized_state = normalize_state(state)
    normalized_name = normalize_university_name(name)

    # 1. Exact name + state
    match = university_index["exact_name_state"].get((name_lower, normalized_state))
    if match:
        return match, "exact_name_state", 100

    # 2. Normalized name + state
    match = university_index["normalized_name_state"].get(
        (normalized_name, normalized_state)
    )
    if match:
        return match, "normalized_name_state", 98

    # 3. Normalized name only, but only if unique
    same_name_matches = university_index["normalized_name"].get(normalized_name, [])

    if len(same_name_matches) == 1:
        return same_name_matches[0], "unique_normalized_name", 95

    # 4. High-confidence fuzzy match only within same state
    best_match = None
    best_score = 0

    for item in university_index["all"]:
        if normalized_state and item["state"] != normalized_state:
            continue

        db_normalized_name = item["normalized_name"]

        if not db_normalized_name:
            continue

        score = SequenceMatcher(
            None,
            normalized_name,
            db_normalized_name,
        ).ratio()

        if score > best_score:
            best_score = score
            best_match = item["university"]

    # Keep threshold strict to prevent wrong update.
    if best_match and best_score >= 0.94:
        return best_match, "fuzzy_same_state", round(best_score * 100, 2)

    return None, "unmatched", round(best_score * 100, 2)


def parse_aishe_rows(raw_rows, file_path):
    parsed_rows = []

    for index, raw_row in enumerate(raw_rows, start=1):
        row = normalize_row(raw_row)

        aishe_code = get_value(row, ["Aishe Code", "AISHE Code", "Code"])
        name = get_value(row, ["Name", "University Name", "Institution Name"])
        state = get_value(row, ["State"])
        district = get_value(row, ["District"])
        website = get_value(row, ["Website", "URL"])
        year = get_value(row, ["Year Of Establishment", "Year of Establishment"])
        location = get_value(row, ["Location"])

        name = clean_text(name)

        if not name:
            continue

        parsed_rows.append(
            {
                "aishe_code": limit_text(aishe_code, 50),
                "name": limit_text(name, 500),
                "state": limit_text(state, 150),
                "district": limit_text(district, 150),
                "aishe_website": clean_url(website),
                "year_of_establishment": limit_text(year, 20),
                "location": limit_text(location, 50),
                "raw_data": {
                    "file_name": file_path.name,
                    "row_number": index,
                    "original_row": raw_row,
                },
            }
        )

    return parsed_rows


def write_unmatched_report(unmatched_rows, output_path):
    if not unmatched_rows:
        return

    with open(output_path, "w", encoding="utf-8", newline="") as csv_file:
        fieldnames = [
            "aishe_code",
            "name",
            "state",
            "district",
            "best_score",
            "reason",
        ]

        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        for row in unmatched_rows:
            writer.writerow(
                {
                    "aishe_code": row["item"]["aishe_code"],
                    "name": row["item"]["name"],
                    "state": row["item"]["state"],
                    "district": row["item"]["district"],
                    "best_score": row["score"],
                    "reason": row["reason"],
                }
            )


class Command(BaseCommand):
    help = "Import AISHE university file and enrich existing University records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            required=True,
            help="AISHE file path. Supports .xlsx and .csv",
        )

        parser.add_argument(
            "--create-missing",
            action="store_true",
            help="Create University records if AISHE row does not match existing UGC data.",
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Check matching without saving changes.",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        create_missing = options["create_missing"]
        dry_run = options["dry_run"]

        if not file_path.exists():
            raise CommandError(f"File does not exist: {file_path}")

        raw_rows = read_input_rows(file_path)
        rows = parse_aishe_rows(raw_rows, file_path)

        self.stdout.write(
            self.style.WARNING(f"Found {len(rows)} AISHE university rows")
        )

        university_index = build_university_index()

        updated_count = 0
        created_count = 0
        unmatched_count = 0

        match_stats = {}
        unmatched_rows = []

        with transaction.atomic():
            for item in rows:
                university, reason, score = find_matching_university(
                    name=item["name"],
                    state=item["state"],
                    university_index=university_index,
                )

                match_stats[reason] = match_stats.get(reason, 0) + 1

                if university:
                    if not dry_run:
                        university.aishe_code = item["aishe_code"]
                        university.district = item["district"]
                        university.aishe_website = item["aishe_website"]
                        university.year_of_establishment = item["year_of_establishment"]
                        university.location = item["location"]

                        existing_raw_data = university.raw_data or {}
                        existing_raw_data["aishe"] = {
                            **item["raw_data"],
                            "match_reason": reason,
                            "match_score": score,
                            "matched_university_id": university.id,
                            "matched_university_name": university.name,
                        }
                        university.raw_data = existing_raw_data

                        if not university.website_url and item["aishe_website"]:
                            university.website_url = item["aishe_website"]

                        university.save()

                    updated_count += 1
                    continue

                if create_missing:
                    if not dry_run:
                        University.objects.create(
                            name=item["name"],
                            university_type=UniversityType.UNKNOWN,
                            state=item["state"],
                            district=item["district"],
                            aishe_code=item["aishe_code"],
                            aishe_website=item["aishe_website"],
                            website_url=item["aishe_website"],
                            year_of_establishment=item["year_of_establishment"],
                            location=item["location"],
                            source=DataSource.UGC,
                            raw_data={
                                "aishe": {
                                    **item["raw_data"],
                                    "match_reason": "created_missing",
                                }
                            },
                            is_active=True,
                        )

                    created_count += 1
                else:
                    unmatched_count += 1
                    unmatched_rows.append(
                        {
                            "item": item,
                            "reason": reason,
                            "score": score,
                        }
                    )

            if dry_run:
                transaction.set_rollback(True)

        output_path = file_path.parent / "aishe_unmatched_universities.csv"
        write_unmatched_report(unmatched_rows, output_path)

        self.stdout.write(self.style.WARNING(f"Match stats: {match_stats}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"AISHE import completed. "
                f"Updated={updated_count}, Created={created_count}, "
                f"Unmatched={unmatched_count}, Dry run={dry_run}"
            )
        )

        if unmatched_rows:
            self.stdout.write(
                self.style.WARNING(
                    f"Unmatched report saved at: {output_path}"
                )
            )