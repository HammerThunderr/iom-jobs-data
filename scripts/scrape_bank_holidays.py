#!/usr/bin/env python3
"""
scrape_bank_holidays.py  —  Isle of Man bank holidays -> docs/bank_holidays.json

Source : https://www.gov.im/categories/home-and-neighbourhood/bank-holidays/
Licence: Open Government Licence (Crown Copyright).

This page is refreshingly simple, unlike the pharmacies one:

    <h2>2026</h2>
    <ul>
      <li>Thursday, 1 January (New Year's Day)</li>
      <li>Friday, 3 April (Good Friday)</li>
      ...
    </ul>

So the parser looks for year headings (a bare 4-digit number) and reads the
list that follows. It copes with the page listing one year or several -- gov.im
usually adds next year's dates partway through the current year.

SAFETY: refuses to write if it finds no years, or if a year has an implausible
number of holidays. A stale-but-correct file beats a fresh empty one.

Run with --debug to print what it found without writing anything.
"""

import argparse
import datetime
import json
import os
import re
import sys

import requests
from bs4 import BeautifulSoup, Tag

SOURCE_URL = ("https://www.gov.im/categories/home-and-neighbourhood/"
              "bank-holidays/")
OUT_PATH = os.environ.get("BANK_HOLIDAYS_OUT", "docs/bank_holidays.json")
USER_AGENT = "ManxOneBot/1.0 (+https://manxone.hammerlabs.app)"

MIN_PER_YEAR = 6      # IoM normally has 10; fewer than 6 means a bad parse
MAX_PER_YEAR = 20

MONTHS = {m.lower(): i for i, m in enumerate(
    ["", "January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"]) if i}

YEAR_RE = re.compile(r"^\s*(20\d{2})\s*$")

# "Thursday, 1 January (New Year's Day)"  ->  day, month, name
ENTRY_RE = re.compile(
    r"^(?:mon|tues|wednes|thurs|fri|satur|sun)day\s*,?\s*"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"([a-z]+)"
    r"(?:\s*[\(\-\u2013]\s*(.+?)\s*\)?)?$",
    re.IGNORECASE,
)


def clean(s):
    return re.sub(r"\s+", " ", (s or "")).replace("\xa0", " ").strip()


def parse_entry(text, year):
    """'Thursday, 1 January (New Year's Day)' -> ('2026-01-01', "New Year's Day")"""
    t = clean(text)
    m = ENTRY_RE.match(t)
    if not m:
        return None
    day = int(m.group(1))
    month = MONTHS.get(m.group(2).lower())
    if not month:
        return None
    name = clean(m.group(3) or "")
    if not name:
        # Fall back to whatever sits in brackets anywhere in the line.
        b = re.search(r"\(([^)]+)\)", t)
        name = clean(b.group(1)) if b else "Bank Holiday"
    try:
        date = datetime.date(year, month, day)
    except ValueError:
        return None
    return date.isoformat(), name


def scrape(debug=False):
    resp = requests.get(SOURCE_URL, headers={"User-Agent": USER_AGENT},
                        timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    root = (soup.find("div", id="content") or soup.find("main")
            or soup.find("article") or soup.body)

    years = []
    for heading in root.find_all(["h2", "h3", "h4"]):
        m = YEAR_RE.match(clean(heading.get_text()))
        if not m:
            continue
        year = int(m.group(1))

        holidays = []
        for sib in heading.next_siblings:
            if not isinstance(sib, Tag):
                continue
            if sib.name in ("h2", "h3", "h4"):
                break
            if sib.name in ("ul", "ol"):
                for li in sib.find_all("li"):
                    parsed = parse_entry(li.get_text(), year)
                    if parsed:
                        holidays.append({"date": parsed[0], "name": parsed[1]})
                    elif debug:
                        print(f"    ? unparsed: {clean(li.get_text())}")

        if debug:
            print(f"[{year}] {len(holidays)} holidays")

        if not holidays:
            continue
        if not (MIN_PER_YEAR <= len(holidays) <= MAX_PER_YEAR):
            raise RuntimeError(
                f"Year {year} parsed {len(holidays)} holidays, expected "
                f"{MIN_PER_YEAR}-{MAX_PER_YEAR}. Refusing to overwrite.")

        holidays.sort(key=lambda h: h["date"])
        years.append({"year": year, "holidays": holidays})

    if not years:
        raise RuntimeError(
            "No bank holiday years parsed - the gov.im page layout may have "
            "changed. Refusing to overwrite. Run with --debug to inspect.")

    years.sort(key=lambda y: y["year"])
    total = sum(len(y["holidays"]) for y in years)
    print(f"Parsed {len(years)} year(s), {total} holidays: "
          + ", ".join(str(y["year"]) for y in years))

    return {
        "meta": {
            "schemaVersion": 1,
            "generated": datetime.date.today().isoformat(),
            "source": "Isle of Man Government - Bank holidays",
            "sourceUrl": SOURCE_URL,
            "licence": "Open Government Licence",
            "attribution": ("Contains public sector information licensed under "
                            "the Open Government Licence. © Crown Copyright."),
            "note": ("Isle of Man bank holidays differ from those in the UK - "
                     "the Island has TT and Tynwald Day, and some shared dates "
                     "fall differently."),
            "yearsIncluded": [str(y["year"]) for y in years],
        },
        "years": years,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true",
                    help="print what was found and write nothing")
    args = ap.parse_args()

    data = scrape(debug=args.debug)
    if args.debug:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print("\n--debug: nothing written.")
        return

    os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
