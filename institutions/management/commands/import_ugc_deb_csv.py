import csv
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from institutions.models import University, UGCDEBProgramme


def clean_text(value):
    if value is None:
        return ""

    value = str(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_key(value):
    value = clean_text(value).lower()
    value = value.replace(".", "")
    value = value.replace("_", "")
    value = value.replace("-", "")
    value = value.replace("/", "")
    value = value.replace(" ", "")
    return value


def normalize_name(value):
    value = clean_text(value).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_row(row):
    normalized = {}

    for key, value in row.items():
        normalized[normalize_key(key)] = clean_text(value)

    return normalized


def get_value(row, possible_keys):
    for key in possible_keys:
        normalized_key = normalize_key(key)
        value = row.get(normalized_key)

        if value:
            return value

    return ""


def find_matching_university(hei_name, state):
    """
    Best-effort matching with UGC University table.

    First exact name + state.
    Then exact name only.
    Then icontains fallback.
    """

    hei_name = clean_text(hei_name)
    state = clean_text(state)

    if not hei_name:
        return None

    qs = University.objects.all()

    exact_qs = qs.filter(name__iexact=hei_name)

    if state:
        state_match = exact_qs.filter(state__iexact=state).first()
        if state_match:
            return state_match

    exact_match = exact_qs.first()

    if exact_match:
        return exact_match

    # fallback: useful when CSV has slightly different spelling/casing
    contains_match = qs.filter(name__icontains=hei_name[:80]).first()

    if contains_match:
        return contains_match

    return None


def parse_ugc_deb_csv(file_path):
    rows = []

    with open(file_path, "r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)

        if not reader.fieldnames:
            return rows

        for index, raw_row in enumerate(reader, start=1):
            row = normalize_row(raw_row)

            year = get_value(row, ["Year"])
            session = get_value(row, ["Session"])
            mode = get_value(row, ["Mode"])
            hei_name = get_value(row, ["Name", "HEI Name", "Institution Name", "University Name"])
            hei_type = get_value(row, ["Type", "HEI Type"])
            state = get_value(row, ["State"])
            program_name = get_value(row, ["Program name", "Programme name", "Program", "Programme"])
            level = get_value(row, ["UG/PG", "UG PG", "Level"])

            year = clean_text(year)
            mode = clean_text(mode)
            hei_name = clean_text(hei_name)
            state = clean_text(state)
            program_name = clean_text(program_name)
            level = clean_text(level).upper()

            # Skip junk/test rows
            if not hei_name or not program_name:
                continue

            if hei_name.lower() == "test" or program_name.lower() == "test":
                continue

            rows.append(
                {
                    "year": year,
                    "session": session,
                    "mode": mode,
                    "hei_name": hei_name,
                    "hei_type": hei_type,
                    "state": state,
                    "program_name": program_name,
                    "level": level,
                    "source_file": file_path.name,
                    "raw_data": {
                        "file_name": file_path.name,
                        "row_number": index,
                        "original_row": raw_row,
                    },
                }
            )

    return rows


class Command(BaseCommand):
    help = "Import UGC-DEB online/distance programme CSV."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            required=True,
            help="CSV file path. Example: ../../data/ugc_deb/Distance Education Bureau.csv",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"])

        if not file_path.exists():
            raise CommandError(f"File does not exist: {file_path}")

        rows = parse_ugc_deb_csv(file_path)

        self.stdout.write(
            self.style.WARNING(f"Found {len(rows)} valid UGC-DEB rows in {file_path.name}")
        )

        created_count = 0
        updated_count = 0
        matched_university_count = 0

        with transaction.atomic():
            for item in rows:
                university = find_matching_university(
                    hei_name=item["hei_name"],
                    state=item["state"],
                )

                if university:
                    matched_university_count += 1

                programme, created = UGCDEBProgramme.objects.update_or_create(
                    year=item["year"],
                    mode=item["mode"],
                    hei_name=item["hei_name"],
                    state=item["state"],
                    program_name=item["program_name"],
                    level=item["level"],
                    defaults={
                        "session": item["session"],
                        "hei_type": item["hei_type"],
                        "university": university,
                        "source_file": item["source_file"],
                        "raw_data": item["raw_data"],
                        "is_active": True,
                    },
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"UGC-DEB import completed. "
                f"Created={created_count}, Updated={updated_count}, "
                f"Matched universities={matched_university_count}"
            )
        )