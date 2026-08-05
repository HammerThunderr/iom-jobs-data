"""
scripts/driving/scrape_instructors.py

Scrapes the Isle of Man Government's Approved Driving Instructors register.

The register changes as instructors qualify or leave, so this runs monthly and
the app always shows the current list.

LICENCE: gov.im content is published under the Isle of Man Open Government
Licence, which permits copying, publishing, distributing and transmitting the
information provided the source is acknowledged. The attribution line is
written into the JSON and displayed in the app.

BE GENTLE: gov.im rate-limits. This fetches exactly ONE page per run. Do not
add retries in a tight loop or increase the schedule frequency.

Usage:
    pip install requests beautifulsoup4
    python scripts/driving/scrape_instructors.py
    OUTPUT_PATH=docs/driving.json python scripts/driving/scrape_instructors.py
"""

import json
import os
import re
import sys
from datetime import date

import requests
from bs4 import BeautifulSoup

URL = (
    "https://www.gov.im/categories/travel-traffic-and-motoring/"
    "drivers-and-vehicles/learning-to-drive/approved-driving-instructors/"
)

OUTPUT = os.environ.get("OUTPUT_PATH", "driving.json")

USER_AGENT = "ManxOneBot/1.0 (+mailto:hammerpunch786@gmail.com)"
TIMEOUT = 30

LICENCE = (
    "Contains public sector information licensed under the "
    "Isle of Man Open Government Licence."
)

DISCLAIMER = (
    "Instructor details are taken from the Isle of Man Government's approved "
    "register. The Department of Infrastructure does not recommend individual "
    "instructors. Always confirm availability and prices directly with the "
    "instructor."
)

REGISTRAR_NOTE = (
    "It is an offence for a car driving instructor who is not on the "
    "Government approved register to charge a fee. Problems with an instructor "
    "can be reported to the Registrar for Driving Instructors."
)

# Static reference information that does not live in the table.
CONTACTS = [
    {
        "name": "Vehicle Test Centre",
        "detail": "Driving tests and CBT enquiries",
        "phone": "+441624627431",
    },
    {
        "name": "Registrar for Driving Instructors",
        "detail": "Report a problem with an instructor",
        "phone": "+441624686753",
    },
]

NOTES = [
    "A theory test pass certificate is valid for 2 years from the date the "
    "test was taken.",
    "Driving tests must be booked directly with the Driving Test Centre.",
    "A list of approved CBT instructors is available from test centres and "
    "motorcycle shops around the Island.",
    "If you hold a current UK CBT certificate you may be able to exchange it "
    "for an Isle of Man certificate — contact the Vehicle Test Centre.",
    "Tests cancelled with less than 7 days' notice will lose the fee.",
]


def normalise_phone(raw):
    """'+44 1624 661783' -> '+441624661783'. Returns '' for N/A or blanks."""
    if not raw:
        return ""
    cleaned = re.sub(r"[^\d+]", "", raw)
    return cleaned if len(cleaned) >= 10 else ""


def split_phones(cell_text):
    """The phone cell holds 'Home: ... Mobile: ...' in either order."""
    home = mobile = ""
    # Split on the labels, keeping what follows each.
    for label, pattern in (
        ("home", r"home\s*:?\s*([+\d\s]+)"),
        ("mobile", r"mobile\s*:?\s*([+\d\s]+)"),
    ):
        match = re.search(pattern, cell_text, flags=re.I)
        if match:
            number = normalise_phone(match.group(1))
            if label == "home":
                home = number
            else:
                mobile = number

    # Some rows give a bare number with no label — treat it as mobile.
    if not home and not mobile:
        bare = normalise_phone(cell_text)
        if bare:
            mobile = bare
    return home, mobile


def parse_contact_cell(cell):
    """Pull an email and a website out of the 'Website / email' column."""
    email = website = ""
    for link in cell.find_all("a", href=True):
        href = link["href"].strip()
        if href.lower().startswith("mailto:"):
            candidate = href[7:].split("?")[0].strip()
            if candidate and not email:
                email = candidate
        elif href.lower().startswith("http"):
            # Skip mailto links that were written as http by mistake.
            if "mailto" not in href.lower() and not website:
                website = href

    # Fall back to a plain-text email if there was no mailto link.
    if not email:
        match = re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", cell.get_text(" "))
        if match:
            email = match.group(0)
    return email, website


def transmissions_from(category):
    low = category.lower()
    found = []
    if "manual" in low:
        found.append("manual")
    if "automatic" in low:
        found.append("automatic")
    return found or ["manual"]


def split_category_and_area(cell_text):
    """The last column mixes vehicle type and area, separated by whitespace.

    e.g. 'Manual Car     Douglas and Onchan'. The vehicle type always comes
    first and uses a known vocabulary, so match that and treat the rest as
    the area.
    """
    text = re.sub(r"\s+", " ", cell_text).strip()
    match = re.match(
        r"^((?:manual|automatic|and|/|car|motorcycle|motocycle|\s)+)",
        text,
        flags=re.I,
    )
    if not match:
        return text, ""
    category = match.group(1).strip(" /")
    area = text[match.end():].strip(" ,/")
    return category, area


def parse_areas(area_label):
    if not area_label:
        return []
    parts = re.split(r",| and |/", area_label)
    return [p.strip() for p in parts if p.strip()]


def find_register_table(soup):
    """The instructor table is the one whose header mentions 'Telephone'."""
    for table in soup.find_all("table"):
        header = table.get_text(" ")[:400].lower()
        if "telephone" in header and (
            "name" in header or "instructor" in header
        ):
            return table
    return None


def register_date(soup):
    """The table caption says 'as of September 2025'."""
    match = re.search(
        r"as of\s+([A-Z][a-z]+\s+\d{4})", soup.get_text(" "), flags=re.I
    )
    return match.group(1) if match else ""


def scrape():
    print(f"Fetching {URL}")
    res = requests.get(URL, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    if res.status_code != 200:
        # gov.im rate-limits; a non-200 is usually that, not a dead page.
        sys.exit(f"ABORT: HTTP {res.status_code} from gov.im")

    soup = BeautifulSoup(res.text, "html.parser")
    table = find_register_table(soup)
    if table is None:
        sys.exit("ABORT: instructor table not found — page layout may have changed.")

    instructors = []
    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 5:
            continue

        name = re.sub(r"\s+", " ", cells[0].get_text(" ")).strip()
        # Skip header and caption rows.
        if not name or name.lower() in ("name", "") or "list of approved" in name.lower():
            continue

        home, mobile = split_phones(cells[1].get_text(" "))
        email, website = parse_contact_cell(cells[2])
        category, area_label = split_category_and_area(cells[3].get_text(" "))

        year_text = re.sub(r"\D", "", cells[4].get_text())
        qualified = int(year_text) if len(year_text) == 4 else None

        instructors.append({
            "name": name,
            "mobile": mobile,
            "landline": home,
            "email": email,
            "website": website,
            "category": category,
            "transmissions": transmissions_from(category),
            "motorcycle": bool(
                re.search(r"moto?rcycle", category, flags=re.I)
            ),
            "areas": parse_areas(area_label),
            "areaLabel": area_label,
            "qualifiedSince": qualified,
        })

    if not instructors:
        sys.exit("ABORT: table found but no instructors parsed.")

    payload = {
        "meta": {
            "schemaVersion": 1,
            "generated": date.today().isoformat(),
            "registerDate": register_date(soup),
            "source": "Isle of Man Government — Approved driving instructors register",
            "sourceUrl": URL,
            "licence": LICENCE,
            "disclaimer": DISCLAIMER,
            "registrarNote": REGISTRAR_NOTE,
            "registrarPhone": "+441624686753",
        },
        "instructors": instructors,
        "contacts": CONTACTS,
        "notes": NOTES,
    }

    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, ensure_ascii=False)

    with_mobile = sum(1 for i in instructors if i["mobile"])
    with_email = sum(1 for i in instructors if i["email"])
    print(f"\nWrote {len(instructors)} instructors to {OUTPUT}")
    print(f"  register date : {payload['meta']['registerDate'] or 'not stated'}")
    print(f"  with phone    : {with_mobile}")
    print(f"  with email    : {with_email}")

    # A collapse in contact details means the columns moved.
    if with_mobile < len(instructors) * 0.5:
        print("  WARNING: over half have no phone — check the column order.")


if __name__ == "__main__":
    scrape()
