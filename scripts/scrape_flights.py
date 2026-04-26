"""
Isle of Man Airport Flight Scraper
-----------------------------------
Scrapes departures + arrivals from airport.im every 5 minutes.
Saves to docs/flights.json on GitHub Pages.

Place at: scripts/scrape_flights.py in your iom-jobs-data repo.
"""

import requests
import urllib3
import json
import os
import re
import ssl
from datetime import datetime, timezone
from bs4 import BeautifulSoup

# Disable SSL warnings — airport.im has cert issues on some runners
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Try multiple URLs in order of preference
URLS = [
    "https://www.airport.im/",
    "https://airport.im/",
    "http://www.airport.im/",   # fallback to HTTP if HTTPS fails
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


def fetch_html():
    """Try multiple URL variants until one succeeds."""
    last_error = None
    for url in URLS:
        for verify in [True, False]:  # try with SSL verification, then without
            try:
                print(f"Trying {url} (SSL verify={verify})...")
                resp = requests.get(
                    url,
                    headers=HEADERS,
                    timeout=20,
                    verify=verify,
                    allow_redirects=True,
                )
                resp.raise_for_status()
                print(f"  ✓ Got {len(resp.text)} bytes from {url}")
                return resp.text
            except Exception as e:
                last_error = e
                print(f"  ✗ {type(e).__name__}: {str(e)[:80]}")
                continue
    raise Exception(f"All URLs failed. Last error: {last_error}")


def parse_flights(html):
    """Scrape arrivals & departures from airport.im homepage."""
    soup = BeautifulSoup(html, "html.parser")

    departures = []
    arrivals = []

    tables = soup.find_all("table")
    print(f"Found {len(tables)} tables")

    for table in tables:
        # Determine if departure or arrival table
        is_departure = False
        is_arrival = False

        # Check thead first
        thead = table.find("thead")
        if thead:
            header_text = thead.get_text().lower()
            if any(k in header_text for k in ["departing to", "destination", "departures"]):
                is_departure = True
            elif any(k in header_text for k in ["arriving from", "origin", "arrivals"]):
                is_arrival = True

        # Check ALL surrounding text — sections often have h1/h2 above the table
        if not is_departure and not is_arrival:
            # Look at previous siblings for headings
            for prev in table.find_all_previous(['h1', 'h2', 'h3', 'h4'], limit=3):
                t = prev.get_text().lower()
                if 'depart' in t:
                    is_departure = True
                    break
                elif 'arriv' in t:
                    is_arrival = True
                    break

        # Last resort — check first data row
        if not is_departure and not is_arrival:
            first_row = table.find("tr")
            if first_row:
                row_text = first_row.get_text().lower()
                if any(k in row_text for k in ["departing", "destination"]):
                    is_departure = True
                elif any(k in row_text for k in ["arriving", "origin"]):
                    is_arrival = True

        if not is_departure and not is_arrival:
            continue

        tbody = table.find("tbody")
        rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]

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
                print(f"  Row parse error: {e}")

    # Find "last updated" timestamp
    last_updated = ""
    text = soup.get_text()
    m = re.search(r'last updated[:\s]+(.+?)(?:\n|$)', text, re.IGNORECASE)
    if m:
        last_updated = m.group(1).strip()[:50]

    return departures, arrivals, last_updated


def categorize_status(status):
    s = status.lower()
    if "cancel"   in s: return "cancelled"
    if "delay"    in s: return "delayed"
    if "boarding" in s: return "boarding"
    if "departed" in s: return "departed"
    if "arrived"  in s: return "arrived"
    if "expected" in s: return "expected"
    if "on-time"  in s or "on time" in s: return "ontime"
    if "scheduled" in s: return "scheduled"
    return "scheduled"


def main():
    os.makedirs("docs", exist_ok=True)

    try:
        html = fetch_html()
        deps, arrs, page_updated = parse_flights(html)

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
        print(f"\n✓ Departures: {len(deps)}, Arrivals: {len(arrs)}")

    except Exception as e:
        print(f"\n✗ Final error: {e}")
        data = {
            "success":     False,
            "error":       str(e)[:200],
            "fetchedAt":   datetime.now(timezone.utc).isoformat(),
            "departures":  [],
            "arrivals":    [],
        }

    with open("docs/flights.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("✓ Saved docs/flights.json")


if __name__ == "__main__":
    main()
