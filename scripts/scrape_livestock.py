#!/usr/bin/env python3
"""
scrape_livestock.py — Isle of Man live-export figures -> docs/livestock_exports.json

Reads the DEFA cattle and sheep export-statistics tables from gov.im and keeps
docs/livestock_exports.json current, so the Farming section's chart and trend
never need hand-updating.

WHY THIS MIGHT NOT WORK, AND WHAT HAPPENS THEN
----------------------------------------------
gov.im sits behind a firewall that has rejected automated requests before
(the school-holiday pages did). A GitHub runner may or may not get through. So
this script degrades safely:

  - if it fetches and parses both tables cleanly -> it writes the file
  - if a page is blocked, missing, or parses to nonsense -> it writes NOTHING
    and exits non-zero, leaving the last good file untouched. The workflow then
    shows a red X and (optionally) opens an issue, so a human knows to check.

A stale-but-correct file always beats a fresh broken one for published data.

SAFETY GATES
  - both species must parse
  - at least 3 months of data per species (a near-empty parse is a failure)
  - monthly totals must be plausible (0..20000)

SETUP
  pip install requests beautifulsoup4
  python scrape_livestock.py            # writes docs/livestock_exports.json
  python scrape_livestock.py --debug    # prints what it found, writes nothing
"""

import argparse
import datetime
import json
import os
import re
import sys

import requests
from bs4 import BeautifulSoup

CATTLE_URL = ("https://www.gov.im/categories/business-and-industries/"
              "agriculture/cattle/cattle-export-statistics/")
SHEEP_URL = ("https://www.gov.im/categories/business-and-industries/"
             "agriculture/sheep-goats/sheep-export-statistics/")
OUT_PATH = os.environ.get("LIVESTOCK_OUT", "docs/livestock_exports.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_ALIASES = {
    "jan": "Jan", "january": "Jan", "feb": "Feb", "february": "Feb",
    "mar": "Mar", "march": "Mar", "apr": "Apr", "april": "Apr",
    "may": "May", "jun": "Jun", "june": "Jun", "jul": "Jul", "july": "Jul",
    "aug": "Aug", "august": "Aug", "sep": "Sep", "sept": "Sep",
    "september": "Sep", "oct": "Oct", "october": "Oct", "nov": "Nov",
    "november": "Nov", "dec": "Dec", "december": "Dec",
}

MIN_MONTHS = 3
MAX_PLAUSIBLE = 20000

# Archive years available on gov.im. The current-year pages live at the base
# URL; each past year is at <base>/<year>-archive/. Fetched once to build the
# history behind the trend read-out; on later runs the years already in the
# file are kept, so old archives are only fetched when missing.
ARCHIVE_YEARS = [2019, 2020, 2021, 2022, 2023, 2024, 2025]

def archive_url(base, year):
    return base.rstrip("/") + f"/{year}-archive/"


def fetch(url):
    r = requests.get(url, headers={"User-Agent": UA, "Accept": "text/html"},
                     timeout=40)
    if r.status_code != 200:
        raise RuntimeError(f"{url} returned HTTP {r.status_code}")
    if re.search(r"request rejected|access denied", r.text, re.I):
        raise RuntimeError(f"{url} was blocked by the gov.im firewall")
    return r.text


def cell_int(text):
    t = (text or "").strip().replace(",", "")
    if t.upper() in ("", "N/A", "NA", "-", "–"):
        return None
    m = re.search(r"-?\d+", t)
    return int(m.group(0)) if m else None


def find_month(row_label):
    key = re.sub(r"[^a-z]", "", (row_label or "").lower())
    return MONTH_ALIASES.get(key)


def parse_month_total_table(html, want_year, total_col_hint="monthly"):
    """
    Find the table whose rows are months and whose last (or 'monthly totals')
    column is the monthly figure. Returns {month: total or None}.
    """
    soup = BeautifulSoup(html, "html.parser")
    best = None

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        month_rows = {}
        for tr in rows:
            cells = tr.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            month = find_month(cells[0].get_text())
            if not month:
                continue
            # The monthly total is the LAST numeric cell on the row.
            nums = [cell_int(c.get_text()) for c in cells[1:]]
            nums = [n for n in nums if n is not None]
            month_rows[month] = nums[-1] if nums else None
        if len([m for m in month_rows if month_rows.get(m) is not None]) >= MIN_MONTHS:
            best = month_rows
            break

    if best is None:
        raise RuntimeError("no month-by-month table found")

    result = {m: best.get(m) for m in MONTHS}
    # plausibility
    for m, v in result.items():
        if v is not None and (v < 0 or v > MAX_PLAUSIBLE):
            raise RuntimeError(f"implausible value {v} for {m}")
    return result


def parse_cattle_split(html):
    """
    The cattle page has a second 'Further rearing / Direct to slaughter' table.
    Returns {month: (rearing, slaughter)} where found.
    """
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        header = table.get_text(" ", strip=True).lower()
        if "rearing" not in header or "slaughter" not in header:
            continue
        out = {}
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            month = find_month(cells[0].get_text())
            if not month:
                continue
            rearing = cell_int(cells[1].get_text())
            slaughter = cell_int(cells[2].get_text())
            out[month] = (rearing, slaughter)
        if out:
            return out
    return {}


def current_year():
    return datetime.date.today().year


def year_from_page(html, fallback):
    """The stats tables head their first column with the year, e.g. '2026'.
    Read it so a page is filed under the year it actually reports, not the
    calendar year the scraper happened to run in."""
    m = re.search(r"\b(20[12]\d)\b", html[:4000])
    return int(m.group(1)) if m else fallback


def build_cattle_year(year, totals, split):
    months = []
    for m in MONTHS:
        tot = totals.get(m)
        rear, slau = split.get(m, (None, None))
        months.append({"month": m, "total": tot,
                       "rearing": rear, "slaughter": slau})
    known = [x for x in months if x["total"] is not None]
    return {
        "year": year,
        "months": months,
        "totalToDate": sum(x["total"] for x in known),
        "rearingToDate": sum(x["rearing"] for x in months if x["rearing"]),
        "slaughterToDate": sum(x["slaughter"] for x in months if x["slaughter"]),
        "monthsReported": len(known),
    }


def build_sheep_year(year, totals):
    months = [{"month": m, "total": totals.get(m)} for m in MONTHS]
    known = [x["total"] for x in months if x["total"] is not None]
    return {"year": year, "months": months,
            "totalToDate": sum(known), "monthsReported": len(known)}


def load_existing():
    try:
        with open(OUT_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def merge_year(years, new_year):
    """Replace the entry for new_year['year'], keep older years untouched."""
    out = [y for y in years if y.get("year") != new_year["year"]]
    out.append(new_year)
    out.sort(key=lambda y: y["year"], reverse=True)
    return out


def scrape_cattle_page(html, fallback_year):
    yr = year_from_page(html, fallback_year)
    totals = parse_month_total_table(html, yr)
    split = parse_cattle_split(html)
    year = build_cattle_year(yr, totals, split)
    if year["monthsReported"] < MIN_MONTHS:
        raise RuntimeError(f"cattle {yr}: only {year['monthsReported']} months")
    return year


def scrape_sheep_page(html, fallback_year):
    yr = year_from_page(html, fallback_year)
    totals = parse_month_total_table(html, yr)
    year = build_sheep_year(yr, totals)
    if year["monthsReported"] < MIN_MONTHS:
        raise RuntimeError(f"sheep {yr}: only {year['monthsReported']} months")
    return year


def main(debug=False):
    yr = current_year()

    # Current year (required — failure here fails the whole run).
    cattle_year = scrape_cattle_page(fetch(CATTLE_URL), yr)
    sheep_year = scrape_sheep_page(fetch(SHEEP_URL), yr)
    print(f"cattle {cattle_year['year']}: {cattle_year['totalToDate']} head "
          f"({cattle_year['monthsReported']} months, "
          f"{cattle_year['rearingToDate']} rearing / "
          f"{cattle_year['slaughterToDate']} slaughter)")
    print(f"sheep  {sheep_year['year']}: {sheep_year['totalToDate']} head "
          f"({sheep_year['monthsReported']} months)")

    existing = load_existing() or {}
    cattle_years = merge_year(
        (existing.get("cattle") or {}).get("years", []), cattle_year)
    sheep_years = merge_year(
        (existing.get("sheep") or {}).get("years", []), sheep_year)

    # Archive years: only fetch ones we do not already hold, so this cost is
    # paid once. A single archive failing must NOT sink the whole run — the
    # current year is what matters — so these are best-effort.
    have_cattle = {y["year"] for y in cattle_years}
    have_sheep = {y["year"] for y in sheep_years}

    for ay in ARCHIVE_YEARS:
        if ay >= cattle_year["year"]:
            continue
        if ay not in have_cattle:
            try:
                cy = scrape_cattle_page(fetch(archive_url(CATTLE_URL, ay)), ay)
                cattle_years = merge_year(cattle_years, cy)
                print(f"  + cattle archive {cy['year']}: {cy['totalToDate']}")
            except Exception as e:  # noqa: BLE001
                print(f"  ! cattle archive {ay} skipped: {e}", file=sys.stderr)
        if ay not in have_sheep:
            try:
                sy = scrape_sheep_page(fetch(archive_url(SHEEP_URL, ay)), ay)
                sheep_years = merge_year(sheep_years, sy)
                print(f"  + sheep archive {sy['year']}: {sy['totalToDate']}")
            except Exception as e:  # noqa: BLE001
                print(f"  ! sheep archive {ay} skipped: {e}", file=sys.stderr)

    data = {
        "meta": {
            "schemaVersion": 1,
            "generated": datetime.date.today().isoformat(),
            "source": "Isle of Man Government (DEFA) - Cattle & Sheep Export Statistics",
            "sourceUrls": {"cattle": CATTLE_URL, "sheep": SHEEP_URL},
            "licence": "Open Government Licence",
            "attribution": ("Contains public sector information licensed under "
                            "the Open Government Licence. © Crown Copyright."),
            "note": ("Live export figures from DEFA. Data runs about 8 weeks "
                     "behind, as it awaits export health certificates, so the "
                     "most recent month or two may be incomplete or missing."),
            "unit": "head of livestock",
        },
        "cattle": {
            "note": ("Cattle exported live, split by destination: 'Further "
                     "rearing' (marts and farms) vs 'Direct to slaughter'."),
            "years": cattle_years,
        },
        "sheep": {
            "note": "Sheep exported live from the Island.",
            "years": sheep_years,
        },
    }

    if debug:
        print(json.dumps(data["cattle"]["years"][0], indent=1))
        print("\n--debug: nothing written.")
        return

    os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()
    try:
        main(debug=args.debug)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
