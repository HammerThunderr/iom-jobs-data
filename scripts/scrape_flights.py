"""
Isle of Man Airport Flight Scraper
-----------------------------------
Run by GitHub Actions every 5 minutes.
Scrapes departures + arrivals from airport.im and saves to docs/flights.json.

Place at: scripts/scrape_flights.py in your iom-jobs-data repo.
"""

import requests
import json
import os
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup

URL = "https://www.airport.im/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-GB,en;q=0.9",
}


def parse_flights():
    """Scrape arrivals & departures from airport.im homepage."""
    resp = requests.get(URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    departures = []
    arrivals = []

    # Find all tables — airport.im uses two tables: departures + arrivals
    tables = soup.find_all("table")

    for table in tables:
        # Try to determine if this is departures or arrivals
        headers_row = table.find("thead")
        is_departure = False
        is_arrival = False

        if headers_row:
            header_text = headers_row.get_text().lower()
            if "departing to" in header_text or "destination" in header_text:
                is_departure = True
            elif "arriving from" in header_text or "origin" in header_text:
                is_arrival = True

        # Fallback — check first row
        if not is_departure and not is_arrival:
            first_row = table.find("tr")
            if first_row:
                row_text = first_row.get_text().lower()
                if "departing" in row_text or "to" in row_text and "from" not in row_text:
                    is_departure = True
                elif "arriving" in row_text or "from" in row_text:
                    is_arrival = True

        if not is_departure and not is_arrival:
            continue

        rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")[1:]

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 5:
                continue

            try:
                if is_departure:
                    flight = {
                        "destination": cols[0].get_text(strip=True),
                        "flightNo":    cols[1].get_text(strip=True),
                        "airline":     cols[2].get_text(strip=True),
                        "scheduled":   cols[3].get_text(strip=True),
                        "status":      cols[4].get_text(strip=True),
                    }
                    if flight["flightNo"]:
                        departures.append(flight)
                elif is_arrival:
                    flight = {
                        "origin":      cols[0].get_text(strip=True),
                        "flightNo":    cols[1].get_text(strip=True),
                        "airline":     cols[2].get_text(strip=True),
                        "scheduled":   cols[3].get_text(strip=True),
                        "status":      cols[4].get_text(strip=True),
                    }
                    if flight["flightNo"]:
                        arrivals.append(flight)
            except Exception as e:
                print(f"Row parse error: {e}")

    # Try to find "last updated" timestamp on page
    last_updated = ""
    text = soup.get_text()
    m = re.search(r'last updated[:\s]+(.+?)(?:\n|$)', text, re.IGNORECASE)
    if m:
        last_updated = m.group(1).strip()[:50]

    return departures, arrivals, last_updated


def categorize_status(status):
    """Group statuses for UI coloring."""
    s = status.lower()
    if "cancel" in s:           return "cancelled"
    if "delay" in s:            return "delayed"
    if "boarding" in s:         return "boarding"
    if "departed" in s:         return "departed"
    if "arrived" in s:          return "arrived"
    if "expected" in s:         return "expected"
    if "on-time" in s or "on time" in s: return "ontime"
    if "scheduled" in s:        return "scheduled"
    return "scheduled"


def main():
    os.makedirs("docs", exist_ok=True)

    try:
        deps, arrs, page_updated = parse_flights()

        # Add status category to each flight
        for f in deps + arrs:
            f["statusType"] = categorize_status(f.get("status", ""))

        data = {
            "success":      True,
            "fetchedAt":    datetime.now(timezone.utc).isoformat(),
            "lastUpdated":  page_updated,
            "departures":   deps,
            "arrivals":     arrs,
            "totalCount":   len(deps) + len(arrs),
        }
        print(f"✓ Departures: {len(deps)}, Arrivals: {len(arrs)}")

    except Exception as e:
        print(f"✗ Error: {e}")
        data = {
            "success":     False,
            "error":       str(e),
            "fetchedAt":   datetime.now(timezone.utc).isoformat(),
            "departures":  [],
            "arrivals":    [],
        }

    with open("docs/flights.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("✓ Saved docs/flights.json")


if __name__ == "__main__":
    main()
