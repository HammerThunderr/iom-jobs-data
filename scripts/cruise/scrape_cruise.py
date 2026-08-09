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
    last_call = None  # carried across continuation rows

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

                # Text, not extract_tables(): this PDF's rows are not drawn
                # as a table, and table extraction found 2 rows out of 40.
                for line in text.split("\n"):
                    parsed = parse_line(line, season, last_call)
                    if parsed:
                        last_call = parsed["callNumber"]
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


PORTS = ("Douglas Bay", "Calf of Man", "Douglas", "Peel", "Ramsey")

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday")

# Some cruise lines are two or three words, so the ship name cannot simply be
# "the first word". These are matched against the end of the ship+line text
# and stripped off, longest first so "Seabourn Cruises" wins over "Seabourn".
KNOWN_LINES = sorted([
    "Compagnie du Ponant", "Seabourn Cruises", "Noble Caledonia",
    "Hebridean Island Cruises", "Aurora Expeditions", "Windstar Cruises",
    "Grand Circle Travel", "Phoenix Reisen", "Hapag-Lloyd Cruises",
    "Saga Cruises", "Azamara", "Regent Seven Seas Cruises",
    "Crystal Cruises", "Holland America Line", "Oceania Cruises",
    "Swan Hellenic", "Carnival Cruise Line", "Seadream Yachts",
    "Ponant", "Silversea", "Viking Ocean Cruises", "Fred Olsen Cruise Lines",
    "Cunard", "P&O Cruises", "Princess Cruises", "Celebrity Cruises",
], key=len, reverse=True)


def split_ship_and_line(text):
    """'Zuiderdam Holland America Line' -> ('Zuiderdam', 'Holland America Line')

    Falls back to putting everything in the ship name rather than guessing —
    a wrong split is worse than an unsplit label.
    """
    cleaned = " ".join(text.split())
    for line in KNOWN_LINES:
        if cleaned.endswith(line):
            ship = cleaned[: -len(line)].strip()
            if ship:
                return ship, line
    return cleaned, ""


def parse_line(text, season, last_call=None):
    """Parse one row of the schedule as plain text.

    pdfplumber does not detect this PDF's rows as a table, so the text path is
    the primary one — an earlier version relied on extract_tables() and found
    only 2 rows out of 40.

    Handles two awkward cases seen in the real file:
      * continuation rows for a second port call, which omit the call number
      * "-" in the Pax and Crew columns, meaning no figure given
    """
    line = " ".join((text or "").split())
    if not line:
        return None
    if "Ship Name" in line or "PLEASE NOTE" in line or "CRUISE SCHEDULE" in line:
        return None

    # Find the port, but NOT inside a ship's name — the vessel "Douglas
    # Mawson" would otherwise be split at "Douglas" and lose its name.
    # The real port always sits immediately before the weekday, so search
    # from the weekday backwards.
    weekday_match = re.search(r"\b(?:%s)\b" % "|".join(WEEKDAYS), line)
    if weekday_match is None:
        return None
    head = line[: weekday_match.start()]

    port = None
    port_at = -1
    for candidate in PORTS:
        found = head.rfind(candidate)
        if found > port_at:
            port, port_at = candidate, found
    if port is None or port_at < 0:
        return None

    times = re.findall(r"\b(\d{1,2}:\d{2})\b", line)
    if not times:
        return None

    call_number = last_call
    match = re.match(r"^(\d{1,3})\s+", line)
    if match:
        call_number = int(match.group(1))
        rest = line[match.end():]
    else:
        rest = line

    # Split at the located occurrence, not the first match in the string.
    offset = port_at - (len(line) - len(rest))
    if offset < 0:
        offset = rest.rfind(port)
    before_port = rest[:offset].strip()
    after_port = rest[offset + len(port):].strip()

    date_match = re.search(
        r"(?:%s),?\s+(\d{1,2})\s+([A-Za-z]+)" % "|".join(WEEKDAYS),
        after_port,
    )
    if not date_match:
        return None
    day = int(date_match.group(1))
    month = MONTHS.get(date_match.group(2).lower())
    if month is None:
        return None
    try:
        when = date(int(season), month, day)
    except ValueError:
        return None

    # Pax and crew are the trailing integers after the final time.
    tail = after_port.rsplit(times[-1], 1)[-1]
    numbers = [int(n) for n in re.findall(r"\b(\d{2,5})\b", tail)]

    ship, cruise_line = split_ship_and_line(before_port)

    return {
        "callNumber": call_number,
        "ship": ship,
        "line": cruise_line,
        "port": port,
        "date": when.isoformat(),
        "eta": clean_time(times[0]),
        "etd": clean_time(times[-1]) if len(times) > 1 else "",
        "passengers": numbers[0] if len(numbers) > 0 else None,
        "crew": numbers[1] if len(numbers) > 1 else None,
    }


if __name__ == "__main__":
    scrape()
