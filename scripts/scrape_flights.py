"""
Isle of Man Airport Flight Scraper (FlightAware)
-------------------------------------------------
Scrapes departures + arrivals from FlightAware's public airport page.
Saves to docs/flights.json on GitHub Pages.

FlightAware embeds the flight data as JSON inside a <script> tag,
which is reliable to parse and doesn't change often.

Place at: scripts/scrape_flights.py in your iom-jobs-data repo.
"""

import requests
import urllib3
import json
import os
import re
from datetime import datetime, timezone

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# FlightAware airport pages — publicly accessible
ARRIVALS_URL    = "https://www.flightaware.com/live/airport/EGNS/arrivals"
DEPARTURES_URL  = "https://www.flightaware.com/live/airport/EGNS/departures"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def fetch(url):
    """Fetch URL with SSL fallback."""
    for verify in [True, False]:
        try:
            print(f"  Fetching {url} (verify={verify})")
            resp = requests.get(url, headers=HEADERS, timeout=25, verify=verify)
            resp.raise_for_status()
            print(f"  ✓ {len(resp.text)} bytes")
            return resp.text
        except Exception as e:
            print(f"  ✗ {type(e).__name__}: {str(e)[:80]}")
    return None


def extract_flightaware_data(html, is_departure):
    """
    FlightAware embeds flight data as JSON in window variables.
    Look for `var trackpollBootstrap = {...}` or similar patterns.
    """
    flights = []

    # FlightAware uses several patterns over the years
    patterns = [
        # Modern pattern (2024+)
        r'var\s+trackpollBootstrap\s*=\s*({.+?});',
        r'window\.flightAwareDataBootstrap\s*=\s*({.+?});',
        # JSON-LD or data attribute
        r'<script[^>]*type=[\'"]application/json[\'"][^>]*>(.+?)</script>',
        # Data within JS object
        r'"flights"\s*:\s*(\[.+?\])',
        r'data:\s*({"\w+":.+?})\s*[,}]',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, html, re.DOTALL)
        if not matches:
            continue
        for raw in matches:
            try:
                data = json.loads(raw)
                # Recursively find flight-shaped objects
                found = find_flights_in_obj(data, is_departure)
                if found:
                    flights.extend(found)
                    print(f"  ✓ Pattern matched, found {len(found)} flights")
                    return flights
            except json.JSONDecodeError:
                continue

    # Fallback — parse the visible HTML table
    print("  No JSON found, parsing HTML table...")
    return parse_flightaware_table(html, is_departure)


def find_flights_in_obj(obj, is_departure):
    """Recursively scan a parsed JSON object for things that look like flights."""
    flights = []
    if isinstance(obj, dict):
        # Check if this dict has flight data fields
        keys = set(obj.keys())
        if {'ident', 'origin', 'destination'} & keys or 'flightId' in keys:
            f = extract_flight_fields(obj, is_departure)
            if f:
                flights.append(f)
        # Recurse
        for v in obj.values():
            flights.extend(find_flights_in_obj(v, is_departure))
    elif isinstance(obj, list):
        for item in obj:
            flights.extend(find_flights_in_obj(item, is_departure))
    return flights


def extract_flight_fields(obj, is_departure):
    """Pull out the fields we care about from a flight object."""
    try:
        flight_no = obj.get('ident') or obj.get('flightNumber') or obj.get('displayIdent') or ''
        airline   = obj.get('airline', {})
        if isinstance(airline, dict):
            airline = airline.get('name') or airline.get('callsign') or airline.get('code') or ''

        origin_obj = obj.get('origin', {})
        dest_obj   = obj.get('destination', {})
        origin_city = origin_obj.get('friendlyName') if isinstance(origin_obj, dict) else (origin_obj or '')
        dest_city   = dest_obj.get('friendlyName')   if isinstance(dest_obj, dict)   else (dest_obj or '')

        # Time fields
        scheduled = (obj.get('takeoffTimes', {}).get('scheduled') if is_departure
                    else obj.get('landingTimes', {}).get('scheduled'))
        if not scheduled:
            scheduled = obj.get('scheduled') or obj.get('estimated') or obj.get('actual') or ''
        if isinstance(scheduled, (int, float)):
            scheduled = datetime.fromtimestamp(scheduled, tz=timezone.utc).strftime('%H:%M')

        status = obj.get('flightStatus') or obj.get('status') or 'Scheduled'

        result = {
            "flightNo":  str(flight_no).strip(),
            "airline":   str(airline).strip(),
            "scheduled": str(scheduled).strip()[:5] if scheduled else '',
            "status":    str(status).strip(),
        }
        if is_departure:
            result["destination"] = str(dest_city).strip()
        else:
            result["origin"] = str(origin_city).strip()

        if result["flightNo"]:
            return result
    except Exception as e:
        print(f"    Field extract error: {e}")
    return None


def parse_flightaware_table(html, is_departure):
    """Fallback HTML table parser for FlightAware airport pages."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    flights = []

    # FlightAware uses a table with class containing "prettyTable" or similar
    tables = soup.find_all("table")
    print(f"    Found {len(tables)} tables")
    
    for table in tables:
        # Check if this looks like a flight table
        thead = table.find("thead")
        if thead:
            head_text = thead.get_text().lower()
            if not any(k in head_text for k in ['flight', 'origin', 'destination', 'arrival', 'departure']):
                continue

        rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")[1:]

        for row in rows:
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) < 4:
                continue
            try:
                # FlightAware columns: Flight | Aircraft | Origin/Dest | Time | Status
                # but layout may vary
                flight_no = cols[0]
                place = cols[2] if len(cols) > 2 else ''
                time_  = cols[3] if len(cols) > 3 else ''
                status = cols[-1] if len(cols) > 4 else 'Scheduled'

                f = {
                    "flightNo":  flight_no,
                    "airline":   '',
                    "scheduled": time_,
                    "status":    status,
                }
                if is_departure:
                    f["destination"] = place
                else:
                    f["origin"] = place
                if flight_no and not flight_no.lower().startswith('flight'):
                    flights.append(f)
            except Exception as e:
                continue

    return flights


def categorize_status(status):
    s = status.lower()
    if "cancel"   in s: return "cancelled"
    if "delay"    in s: return "delayed"
    if "boarding" in s: return "boarding"
    if "departed" in s or "en route" in s: return "departed"
    if "arrived"  in s or "landed" in s: return "arrived"
    if "expected" in s: return "expected"
    if "on-time"  in s or "on time" in s: return "ontime"
    return "scheduled"


def main():
    os.makedirs("docs", exist_ok=True)

    print("\n=== Fetching DEPARTURES ===")
    dep_html = fetch(DEPARTURES_URL)
    departures = extract_flightaware_data(dep_html, True) if dep_html else []

    print("\n=== Fetching ARRIVALS ===")
    arr_html = fetch(ARRIVALS_URL)
    arrivals = extract_flightaware_data(arr_html, False) if arr_html else []

    # Add status types
    for f in departures + arrivals:
        f["statusType"] = categorize_status(f.get("status", ""))

    if departures or arrivals:
        data = {
            "success":     True,
            "fetchedAt":   datetime.now(timezone.utc).isoformat(),
            "lastUpdated": datetime.now(timezone.utc).strftime("%H:%M UTC"),
            "departures":  departures,
            "arrivals":    arrivals,
            "totalCount":  len(departures) + len(arrivals),
            "source":      "FlightAware EGNS",
        }
        print(f"\n✓ SUCCESS — {len(departures)} departures, {len(arrivals)} arrivals")
    else:
        # Save debug HTML
        os.makedirs("docs/_debug", exist_ok=True)
        if dep_html:
            with open("docs/_debug/departures.html", "w", encoding="utf-8") as f:
                f.write(dep_html[:100000])
        if arr_html:
            with open("docs/_debug/arrivals.html", "w", encoding="utf-8") as f:
                f.write(arr_html[:100000])

        data = {
            "success":     False,
            "error":       "Could not extract flight data. FlightAware may have changed their HTML. Check docs/_debug/",
            "fetchedAt":   datetime.now(timezone.utc).isoformat(),
            "departures":  [],
            "arrivals":    [],
        }
        print("\n✗ FAILED — debug HTML saved")

    with open("docs/flights.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("✓ Saved docs/flights.json")


if __name__ == "__main__":
    main()
