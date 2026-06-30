import re
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.db import transaction

from institutions.models import NIRFRanking, University


BASE_URL = "https://www.nirfindia.org/Rankings/2025/"

NIRF_URLS = {
    "overall": "https://www.nirfindia.org/Rankings/2025/OverallRanking.html",
    "university": "https://www.nirfindia.org/Rankings/2025/UniversityRanking.html",
    "college": "https://www.nirfindia.org/Rankings/2025/CollegeRanking.html",
    "engineering": "https://www.nirfindia.org/Rankings/2025/EngineeringRanking.html",
    "management": "https://www.nirfindia.org/Rankings/2025/ManagementRanking.html",
    "medical": "https://www.nirfindia.org/Rankings/2025/MedicalRanking.html",
    "law": "https://www.nirfindia.org/Rankings/2025/LawRanking.html",
    "pharmacy": "https://www.nirfindia.org/Rankings/2025/PharmacyRanking.html",
}


def clean_text(value):
    if value is None:
        return ""

    value = str(value)
    value = value.replace("\ufeff", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_state(value):
    value = clean_text(value).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_name(value):
    value = clean_text(value).lower()
    value = value.replace("&", " and ")
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)

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

    words = [word for word in value.split() if word not in noise_words]
    value = " ".join(words)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def parse_decimal(value):
    value = clean_text(value)

    if not value:
        return None

    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def fetch_html(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }

    response = requests.get(url, headers=headers, timeout=60)
    response.raise_for_status()
    return response.text


def extract_name(name_cell):
    """
    NIRF name cell has institution name plus extra divs/tables.
    We only want the direct text before More Details.
    """

    direct_text_parts = []

    for child in name_cell.children:
        if getattr(child, "name", None) == "div":
            break

        text = clean_text(child)

        if text:
            direct_text_parts.append(text)

    name = clean_text(" ".join(direct_text_parts))

    if name:
        return name

    # fallback: remove nested div/table, then read text
    clone = BeautifulSoup(str(name_cell), "lxml")
    td = clone.find("td")

    if td:
        for tag in td.find_all(["div", "table", "a", "img"]):
            tag.decompose()

        return clean_text(td.get_text(" ", strip=True))

    return ""


def extract_links(name_cell):
    pdf_url = ""
    graph_url = ""

    for link in name_cell.find_all("a", href=True):
        href = link["href"]

        if "/pdf/" in href.lower() and href.lower().endswith(".pdf"):
            pdf_url = urljoin(BASE_URL, href)

        if "/graph/" in href.lower() and href.lower().endswith((".jpg", ".jpeg", ".png")):
            graph_url = urljoin(BASE_URL, href)

    return pdf_url, graph_url


def extract_parameter_scores(name_cell):
    """
    Extract hidden score table:
    TLR, RPC, GO, OI, PERCEPTION
    """

    scores = {
        "tlr_score": None,
        "rpc_score": None,
        "go_score": None,
        "oi_score": None,
        "perception_score": None,
    }

    hidden_table = name_cell.find("div", class_="tbl_hidden")

    if not hidden_table:
        return scores

    score_cells = hidden_table.find_all("td")

    if len(score_cells) < 5:
        return scores

    scores["tlr_score"] = parse_decimal(score_cells[0].get_text(" ", strip=True))
    scores["rpc_score"] = parse_decimal(score_cells[1].get_text(" ", strip=True))
    scores["go_score"] = parse_decimal(score_cells[2].get_text(" ", strip=True))
    scores["oi_score"] = parse_decimal(score_cells[3].get_text(" ", strip=True))
    scores["perception_score"] = parse_decimal(score_cells[4].get_text(" ", strip=True))

    return scores


def parse_nirf_html(html, category, source_url, year):
    soup = BeautifulSoup(html, "lxml")

    table = soup.find("table")

    if not table:
        return []

    tbody = table.find("tbody")

    if not tbody:
        return []

    rows = []

    for tr in tbody.find_all("tr", recursive=False):
        cells = tr.find_all("td", recursive=False)

        if len(cells) < 6:
            continue

        institute_id = clean_text(cells[0].get_text(" ", strip=True))
        name_cell = cells[1]

        name = extract_name(name_cell)
        city = clean_text(cells[2].get_text(" ", strip=True))
        state = clean_text(cells[3].get_text(" ", strip=True))
        score = parse_decimal(cells[4].get_text(" ", strip=True))
        rank = clean_text(cells[5].get_text(" ", strip=True))

        if not institute_id or not name:
            continue

        pdf_url, graph_url = extract_links(name_cell)
        parameter_scores = extract_parameter_scores(name_cell)

        rows.append(
            {
                "year": year,
                "category": category,
                "institute_id": institute_id,
                "name": name,
                "city": city,
                "state": state,
                "score": score,
                "rank": rank,
                "pdf_url": pdf_url,
                "graph_url": graph_url,
                "source_url": source_url,
                **parameter_scores,
                "raw_data": {
                    "category": category,
                    "source_url": source_url,
                    "html_cells": [
                        clean_text(cell.get_text(" ", strip=True)) for cell in cells
                    ],
                },
            }
        )

    return rows


def build_university_index():
    index = []

    for university in University.objects.all().only("id", "name", "state"):
        index.append(
            {
                "university": university,
                "name": normalize_name(university.name),
                "state": normalize_state(university.state),
            }
        )

    return index


def find_matching_university(name, state, university_index):
    """
    Conservative match.

    NIRF includes IITs, AIIMS, colleges and institutes also, not only universities.
    So we should match only when confidence is high.
    """

    normalized_name = normalize_name(name)
    normalized_state = normalize_state(state)

    if not normalized_name:
        return None, 0

    best_match = None
    best_score = 0

    for item in university_index:
        if normalized_state and item["state"] and item["state"] != normalized_state:
            continue

        db_name = item["name"]

        if not db_name:
            continue

        if db_name == normalized_name:
            return item["university"], 100

        score = SequenceMatcher(None, normalized_name, db_name).ratio() * 100

        if score > best_score:
            best_score = score
            best_match = item["university"]

    if best_match and best_score >= 94:
        return best_match, round(best_score, 2)

    return None, round(best_score, 2)


class Command(BaseCommand):
    help = "Scrape NIRF ranking pages and save rankings."

    def add_arguments(self, parser):
        parser.add_argument(
            "--category",
            choices=list(NIRF_URLS.keys()) + ["all"],
            default="all",
            help="NIRF category to scrape.",
        )

        parser.add_argument(
            "--year",
            type=int,
            default=2025,
            help="NIRF ranking year.",
        )

    def handle(self, *args, **options):
        selected_category = options["category"]
        year = options["year"]

        if selected_category == "all":
            categories = list(NIRF_URLS.keys())
        else:
            categories = [selected_category]

        university_index = build_university_index()

        total_created = 0
        total_updated = 0
        total_matched = 0

        for category in categories:
            source_url = NIRF_URLS[category]

            self.stdout.write(
                self.style.WARNING(f"Scraping NIRF {year}: {category}")
            )

            html = fetch_html(source_url)
            rows = parse_nirf_html(
                html=html,
                category=category,
                source_url=source_url,
                year=year,
            )

            self.stdout.write(f"Found {len(rows)} NIRF rows for {category}")

            created_count = 0
            updated_count = 0
            matched_count = 0

            with transaction.atomic():
                for item in rows:
                    university, match_score = find_matching_university(
                        name=item["name"],
                        state=item["state"],
                        university_index=university_index,
                    )

                    if university:
                        matched_count += 1

                    ranking, created = NIRFRanking.objects.update_or_create(
                        year=item["year"],
                        category=item["category"],
                        institute_id=item["institute_id"],
                        defaults={
                            "name": item["name"],
                            "city": item["city"],
                            "state": item["state"],
                            "score": item["score"],
                            "rank": item["rank"],
                            "tlr_score": item["tlr_score"],
                            "rpc_score": item["rpc_score"],
                            "go_score": item["go_score"],
                            "oi_score": item["oi_score"],
                            "perception_score": item["perception_score"],
                            "pdf_url": item["pdf_url"],
                            "graph_url": item["graph_url"],
                            "source_url": item["source_url"],
                            "university": university,
                            "raw_data": {
                                **item["raw_data"],
                                "university_match_score": match_score,
                                "matched_university_id": university.id if university else None,
                                "matched_university_name": university.name if university else "",
                            },
                        },
                    )

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

            total_created += created_count
            total_updated += updated_count
            total_matched += matched_count

            self.stdout.write(
                self.style.SUCCESS(
                    f"{category}: Created={created_count}, "
                    f"Updated={updated_count}, Matched universities={matched_count}"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"NIRF sync completed. Created={total_created}, "
                f"Updated={total_updated}, Matched universities={total_matched}"
            )
        )