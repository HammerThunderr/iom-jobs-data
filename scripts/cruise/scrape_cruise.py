"""
scripts/cruise/scrape_cruise.py

Scrapes the Visit Isle of Man cruise schedule.

TWO THINGS THAT SHAPED THIS:

1. The PDF filename is VERSIONED — "Cruise Schedule 2026 V16.pdf" — and the
   version bumps whenever the schedule changes (V16 was 20 July 2026). So the
   scraper reads the schedule page first and follows whatever PDF link it
   finds, rather than hardcoding a URL that will 404 within weeks.

2. Only FACTS are stored: ship, line, port, date, times, passenger and crew
   numbers. The Visit Isle of Man site is marked "All Rights Reserved" rather
   than Open Government Licence, so the app indexes the facts, credits the
   source and links back — it does not reproduce their page.

Usage:
    pip install requests beautifulsoup4 pdfplumber
    python scripts/cruise/scrape_cruise.py
    OUTPUT_PATH=docs/cruise.json python scripts/cruise/scrape_cruise.py
"""

import json
import os
import re
import sys
from datetime import date, datetime
from urllib.parse import urljoin, quote

import pdfplumber
import requests
from bs4 import BeautifulSoup

SCHEDULE_PAGE = (
    "https://www.visitisleofman.com/traveltrade/cruise/cruise-schedule"
)

OUTPUT = os.environ.get("OUTPUT_PATH", "cruise.json")

USER_AGENT = "ManxOneBot/1.0 (+mailto:hammerpunch786@gmail.com)"
TIMEOUT = 45

SEASON = str(date.today().year)

DISCLAIMER = (
    "Cruise arrivals as published by Visit Isle of Man. The schedule is "
    "subject to change at short notice, and calls can be cancelled at sea due "
    "to weather. Manx One is not affiliated with Visit Isle of Man or any "
    "cruise line."
)

LOCAL_NOTE = (
    "Cruise days mean a busier Douglas — more people on the promenade, at the "
    "horse trams and in the cafes. The passenger figures give a rough idea of "
    "how busy."
)

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}


def find_pdf_url():
    """Follow whatever cruise-schedule PDF the page currently links to."""
    res = requests.get(
        SCHEDULE_PAGE, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
    )
    if res.status_code != 200:
        sys.exit(f"ABORT: schedule page returned HTTP {res.status_code}")

    soup = BeautifulSoup(res.text, "html.parser")
    candidates = []
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if ".pdf" not in href.lower():
            continue
        if "cruise" in href.lower() and "schedule" in href.lower():
            candidates.append(href)

    if not candidates:
        sys.exit("ABORT: no cruise schedule PDF link found on the page.")

    # Prefer the highest version number if several are listed.
    def version_of(href):
        match = re.search(r"[Vv](\d+)", href)
        return int(match.group(1)) if match else 0

    best = sorted(candidates, key=version_of)[-1]
    # Spaces in the filename need encoding, but an already-encoded URL must
    # not be double-encoded.
    if " " in best:
        best = quote(best, safe=":/?&=%")
    return urljoin(SCHEDULE_PAGE, best)


def parse_date(day_text, season):
    """'Thursday, 23 April' or '23 April' -> a date in the season."""
    cleaned = day_text.replace(",", " ")
    match = re.search(r"(\d{1,2})\s+([A-Za-z]+)", cleaned)
    if not match:
        return None
    day = int(match.group(1))
    month = MONTHS.get(match.group(2).lower())
    if month is None:
        return None
    try:
        return date(int(season), month, day)
    except ValueError:
        return None


def clean_time(raw):
    match = re.search(r"(\d{1,2}):(\d{2})", raw or "")
    if not match:
        return ""
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def to_int(raw):
    digits = re.sub(r"[^\d]", "", raw or "")
    return int(digits) if digits else None


def scrape():
    pdf_url = find_pdf_url()
    print(f"Schedule PDF: {pdf_url}")

    res = requests.get(
        pdf_url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
    )
    if res.status_code != 200:
        sys.exit(f"ABORT: PDF returned HTTP {res.status_code}")

    path = "_cruise_tmp.pdf"
    with open(path, "wb") as fh:
        fh.write(res.content)

    calls = []
    version_note = ""
    season = SEASON

    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""

                if not version_note:
                    match = re.search(r"Version\s+\d+[^\n]*", text)
                    if match:
                        version_note = match.group(0).strip()

                match = re.search(r"CRUISE SCHEDULE\s+(\d{4})", text)
                if match:
                    season = match.group(1)

                for table in page.extract_tables() or []:
                    for row in table:
                        parsed = parse_row(row, season)
                        if parsed:
                            calls.append(parsed)

                # Some pages render as text rather than a detected table.
                if not calls:
                    for line in text.split("\n"):
                        parsed = parse_text_line(line, season)
                        if parsed:
                            calls.append(parsed)
    finally:
        if os.path.exists(path):
            os.remove(path)

    if not calls:
        sys.exit("ABORT: no cruise calls parsed — PDF layout may have changed.")

    calls.sort(key=lambda c: (c["date"], c["eta"]))

    payload = {
        "meta": {
            "schemaVersion": 1,
            "season": season,
            "generated": date.today().isoformat(),
            "scheduleVersion": version_note,
            "source": f"Visit Isle of Man {season} Cruise Schedule",
            "sourceUrl": SCHEDULE_PAGE,
            "disclaimer": DISCLAIMER,
            "attribution": "Schedule information courtesy of Visit Isle of Man.",
            "localNote": LOCAL_NOTE,
        },
        "calls": calls,
    }

    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, ensure_ascii=False)

    print(f"\nWrote {len(calls)} calls to {OUTPUT}")
    print(f"  season  : {season}")
    print(f"  version : {version_note or 'not stated'}")
    upcoming = [c for c in calls if c["date"] >= date.today().isoformat()]
    print(f"  upcoming: {len(upcoming)}")


def parse_row(row, season):
    """A table row from the schedule PDF."""
    if not row or len(row) < 6:
        return None
    cells = [(c or "").strip() for c in row]
    joined = " ".join(cells)
    if "Ship Name" in joined or "Call Number" in joined:
        return None
    return build_call(cells, season)


def parse_text_line(line, season):
    """Fallback for pages where the table is not detected as a table."""
    if not line or "Ship Name" in line or "PLEASE NOTE" in line:
        return None
    # Lines start with a call number and contain a time like 08:00.
    if not re.match(r"^\s*\d{1,3}\s", line) or ":" not in line:
        return None
    return None  # table extraction is the reliable path; do not guess here


def build_call(cells, season):
    joined = " ".join(cells)

    when = parse_date(joined, season)
    if when is None:
        return None

    times = re.findall(r"\d{1,2}:\d{2}", joined)
    if not times:
        return None

    call_number = to_int(cells[0]) if cells and cells[0] else None

    # Ports are a known short list, which makes them a reliable anchor for
    # splitting the ship/line text from everything after it.
    port = ""
    for candidate in ("Douglas Bay", "Calf of Man", "Douglas", "Peel", "Ramsey"):
        if candidate in joined:
            port = candidate
            break

    before_port = joined.split(port)[0] if port else joined
    before_port = re.sub(r"^\s*\d{1,3}\s+", "", before_port).strip()

    numbers = [to_int(n) for n in re.findall(r"\b\d{2,5}\b", joined.split(times[-1])[-1])]
    passengers = numbers[0] if len(numbers) > 0 else None
    crew = numbers[1] if len(numbers) > 1 else None

    return {
        "callNumber": call_number,
        "ship": before_port,
        "line": "",
        "port": port,
        "date": when.isoformat(),
        "eta": clean_time(times[0]),
        "etd": clean_time(times[-1]) if len(times) > 1 else "",
        "passengers": passengers,
        "crew": crew,
    }


if __name__ == "__main__":
    scrape()
