import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.ugc.gov.in"


UGC_UNIVERSITY_URLS = {
    "central": "https://www.ugc.gov.in/universitydetails/university?type=ddmCMsxJZgXH2S%2Fm0uMOKQ%3D%3D",
    "state": "https://www.ugc.gov.in/universitydetails/university?type=LZ1FUMk6U2JWGNLvhWfVSA%3D%3D",
    "deemed": "https://www.ugc.gov.in/universitydetails/university?type=UCL6fMspL2LJS89kv++N3A%3D%3D",
    "private": "https://www.ugc.gov.in/universitydetails/university?type=0wBmFB1Rb4JGVzq9UP%2FiOg%3D%3D",
}


def clean_text(value: str) -> str:
    if not value:
        return ""

    value = re.sub(r"\s+", " ", value)
    return value.strip()


def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    print("STATUS:", response.status_code)
    print("FINAL URL:", response.url)
    print("HTML LENGTH:", len(response.text))
    print("HAS ALIGARH:", "Aligarh Muslim University" in response.text)

    with open("ugc_debug.html", "w", encoding="utf-8") as f:
        f.write(response.text)

    return response.text


def parse_university_rows(html: str, source_url: str, fallback_type: str):
    soup = BeautifulSoup(html, "lxml")

    table = soup.find("table")

    if not table:
        return []

    universities = []

    rows = table.find_all("tr")

    for row in rows:
        cells = row.find_all(["td", "th"])

        cell_values = [clean_text(cell.get_text(" ", strip=True)) for cell in cells]

        # Skip header rows
        if not cell_values:
            continue

        if "Sr.No" in cell_values[0] or "Name of the University" in " ".join(cell_values):
            continue

        # Expected:
        # Sr.No, Type, Name, Address, Zip, State, Status, URL
        if len(cell_values) < 7:
            continue

        try:
            sr_no = int(cell_values[0])
        except ValueError:
            sr_no = None

        ugc_type_raw = cell_values[1]
        name = cell_values[2]
        address = cell_values[3]
        zip_code = cell_values[4]
        state = cell_values[5]
        status = cell_values[6]

        website_url = ""

        for link in row.find_all("a", href=True):
            link_text = clean_text(link.get_text(" ", strip=True)).lower()

            if "website" in link_text or "view website" in link_text:
                website_url = urljoin(BASE_URL, link["href"])
                break

        universities.append(
            {
                "source_sr_no": sr_no,
                "university_type": fallback_type,
                "ugc_type_raw": ugc_type_raw,
                "name": name,
                "address": address,
                "zip_code": zip_code,
                "state": state,
                "ugc_status": status,
                "website_url": website_url,
                "source_url": source_url,
                "raw_data": {
                    "source_sr_no": sr_no,
                    "ugc_type_raw": ugc_type_raw,
                    "row_values": cell_values,
                },
            }
        )

    return universities


def scrape_ugc_universities(university_type: str):
    if university_type not in UGC_UNIVERSITY_URLS:
        raise ValueError(f"Invalid university_type: {university_type}")

    source_url = UGC_UNIVERSITY_URLS[university_type]
    html = fetch_html(source_url)

    return parse_university_rows(
        html=html,
        source_url=source_url,
        fallback_type=university_type,
    )