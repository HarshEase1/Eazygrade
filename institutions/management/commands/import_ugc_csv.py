import csv
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from institutions.models import University, UniversityType, DataSource


FILE_TYPE_MAP = {
    "central.csv": UniversityType.CENTRAL,
    "state.csv": UniversityType.STATE,
    "deemed.csv": UniversityType.DEEMED,
    "stateprivate.csv": UniversityType.PRIVATE,
    "fake.csv": UniversityType.FAKE,
}


def limit_text(value, max_length):
    value = clean_text(value)

    if len(value) <= max_length:
        return value

    return value[:max_length]

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
    value = value.replace(" ", "")
    return value


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


def get_int_value(value):
    value = clean_text(value)

    if not value:
        return None

    value = re.sub(r"[^\d]", "", value)

    if not value:
        return None

    try:
        return int(value)
    except ValueError:
        return None


def clean_url(value):
    value = clean_text(value)

    if not value:
        return ""

    lower_value = value.lower()

    if lower_value in ["view", "view website", "website", "url", "-"]:
        return ""

    if value.startswith("http://") or value.startswith("https://"):
        return value

    if value.startswith("www."):
        return f"https://{value}"

    return ""


def detect_university_type(file_path, explicit_type):
    if explicit_type:
        return explicit_type

    filename = file_path.name.lower().replace(" ", "")

    if filename in FILE_TYPE_MAP:
        return FILE_TYPE_MAP[filename]

    raise CommandError(
        f"Cannot detect university type from file name: {file_path.name}. "
        f"Use --type central/state/deemed/private/fake"
    )


def parse_ugc_csv(file_path, university_type):
    rows = []

    with open(file_path, "r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)

        if not reader.fieldnames:
            return rows

        for index, raw_row in enumerate(reader, start=1):
            row = normalize_row(raw_row)

            sr_no = get_value(row, ["Sr.No", "Sr No", "S.No", "S No", "SNo", "Serial No"])
            ugc_type_raw = get_value(row, ["Type", "University Type"])
            name = get_value(
                row,
                [
                    "Name of the University",
                    "Name Of University",
                    "University Name",
                    "Name",
                ],
            )
            address = get_value(row, ["Address"])
            zip_code = get_value(row, ["Zip", "Zip Code", "Pincode", "Pin Code", "PIN"])
            state = get_value(row, ["State", "state"])
            status = get_value(row, ["Status", "UGC Status"])
            website_url = get_value(row, ["URL", "Website", "Website URL", "University URL"])

            name = clean_text(name)

            if not name:
                continue

            rows.append(
                {
                    "source_sr_no": get_int_value(sr_no),
                    "university_type": university_type,
                    "ugc_type_raw": ugc_type_raw,
                    "name": name,
                    "address": address,
                    "zip_code": limit_text(zip_code, 100),
                    "state": limit_text(state, 150),
                    "ugc_status": limit_text(status, 255),
                    "website_url": clean_url(website_url),
                    "source_url": "",
                    "raw_data": {
                        "file_name": file_path.name,
                        "row_number": index,
                        "ugc_type_raw": ugc_type_raw,
                        "original_row": raw_row,
                    },
                }
            )

    return rows


class Command(BaseCommand):
    help = "Import UGC university CSV files downloaded manually."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            help="Single CSV file path. Example: ../../data/ugc/Central.csv",
        )

        parser.add_argument(
            "--folder",
            type=str,
            default="../../data/ugc",
            help="Folder containing UGC CSV files.",
        )

        parser.add_argument(
            "--type",
            choices=["central", "state", "deemed", "private", "fake"],
            help="Required only when importing a single file with unknown name.",
        )

    def handle(self, *args, **options):
        explicit_file = options.get("file")
        folder = options.get("folder")
        explicit_type = options.get("type")

        if explicit_file:
            files = [Path(explicit_file)]
        else:
            folder_path = Path(folder)

            if not folder_path.exists():
                raise CommandError(f"Folder does not exist: {folder_path}")

            files = [
                folder_path / "Central.csv",
                folder_path / "state.csv",
                folder_path / "deemed.csv",
                folder_path / "StatePrivate.csv",
                folder_path / "Fake.csv",
            ]

        total_created = 0
        total_updated = 0
        total_skipped_files = 0

        for file_path in files:
            if not file_path.exists():
                self.stdout.write(
                    self.style.WARNING(f"Skipping missing file: {file_path}")
                )
                total_skipped_files += 1
                continue

            university_type = detect_university_type(file_path, explicit_type)

            self.stdout.write(
                self.style.WARNING(
                    f"Importing {file_path} as university_type={university_type}"
                )
            )

            rows = parse_ugc_csv(file_path, university_type)

            self.stdout.write(f"Found {len(rows)} rows in {file_path.name}")

            created_count = 0
            updated_count = 0

            with transaction.atomic():
                for item in rows:
                    university, created = University.objects.update_or_create(
                        name=item["name"],
                        state=item["state"],
                        university_type=item["university_type"],
                        defaults={
                            "address": item["address"],
                            "zip_code": item["zip_code"],
                            "ugc_status": item["ugc_status"],
                            "website_url": item["website_url"],
                            "source": DataSource.UGC,
                            "source_url": item["source_url"],
                            "source_sr_no": item["source_sr_no"],
                            "raw_data": item["raw_data"],
                            "is_active": item["university_type"] != UniversityType.FAKE,
                            "is_fake": item["university_type"] == UniversityType.FAKE,
                        },
                    )

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

            total_created += created_count
            total_updated += updated_count

            self.stdout.write(
                self.style.SUCCESS(
                    f"{file_path.name}: Created={created_count}, Updated={updated_count}"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"UGC CSV import completed. "
                f"Created={total_created}, Updated={total_updated}, "
                f"Skipped files={total_skipped_files}"
            )
        )