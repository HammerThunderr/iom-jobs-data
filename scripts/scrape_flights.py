"""
Isle of Man Airport Flight Scraper
-----------------------------------
Scrapes departures + arrivals from airport.im/live-flight-information/
Saves to docs/flights.json on GitHub Pages every 5 minutes.

Place at: scripts/scrape_flights.py in your iom-jobs-data repo.
"""

import requests
import urllib3
import json
import os
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL = "https://www.airport.im/live-flight-information/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}


def fetch():
    """Fetch the live flight information page."""
    for verify in [True, False]:
        try:
            print(f"Fetching {URL} (verify={verify})...")
            resp = requests.get(URL, headers=HEADERS, timeout=25, verify=verify)
            resp.raise_for_status()
            print(f"  ✓ Got {len(resp.text)} bytes")
            return resp.text
        except Exception as e:
            print(f"  ✗ {type(e).__name__}: {str(e)[:80]}")
    raise Exception("All fetch attempts failed")


def parse_flight_section(soup, tab_id, is_departure):
    """
    Parse one tab pane (#pills-departures or #pills-arrivals).
    Each flight is a <div class="d-flex flex-wrap flex-md-nowrap...">
    containing 4 main child elements: airport, flightNo+airline, time, status.
    """
    flights = []

    tab = soup.find("div", id=tab_id)
    if not tab:
        print(f"  ✗ Could not find #{tab_id}")
        return flights

    # Each flight row has class "flight-information__airport" inside it
    # We'll find all the rows that contain an airport span
    airport_spans = tab.find_all("span", class_="flight-information__airport")
    print(f"  Found {len(airport_spans)} flights in #{tab_id}")

    for airport_span in airport_spans:
        try:
            # The flight row is the parent div containing this airport span
            row = airport_span.find_parent("div", class_=re.compile(r"d-flex.*flex-wrap"))
            if not row:
                continue

            airport = airport_span.get_text(strip=True)

            # Flight number
            flight_no_div = row.find("div", class_="flight-information__flight-no")
            flight_no = flight_no_div.get_text(strip=True) if flight_no_div else ""

            # Airline — the sibling div of flight-no inside flight-airline container
            airline = ""
            airline_container = row.find("div", class_=re.compile(r"flight-information__flight-airline"))
            if airline_container:
                # Find the div that doesn't have flight-no class
                divs = airline_container.find_all("div", recursive=False)
                for d in divs:
                    classes = d.get("class", [])
                    if "flight-information__flight-no" not in classes:
                        airline = d.get_text(strip=True)
                        break

            # Scheduled time — inside a span with bi-clock-history svg
            scheduled = ""
            time_span = row.find("span", class_=re.compile(r"d-inline-flex.*align-items-center"))
            if time_span:
                # Get text but strip out the SVG content
                for svg in time_span.find_all("svg"):
                    svg.decompose()
                scheduled = time_span.get_text(strip=True)

            # Status — the badge at the end
            status = "Scheduled"
            status_badge = row.find("span", class_=re.compile(r"flight-information__status-badge"))
            if status_badge:
                status = status_badge.get_text(strip=True)

            flight = {
                "flightNo":  flight_no,
                "airline":   airline,
                "scheduled": scheduled,
                "status":    status,
            }
            if is_departure:
                flight["destination"] = airport
            else:
                flight["origin"] = airport

            if flight_no:
                flights.append(flight)
                print(f"    ✓ {flight_no} {airport} {scheduled} - {status}")

        except Exception as e:
            print(f"    ✗ Row parse error: {e}")

    return flights


def categorize_status(status):
    s = status.lower()
    if "cancel"   in s: return "cancelled"
    if "delay"    in s: return "delayed"
    if "boarding" in s: return "boarding"
    if "gate closed" in s: return "boarding"
    if "departed" in s: return "departed"
    if "arrived"  in s or "landed" in s: return "arrived"
    if "expected" in s: return "expected"
    if "on-time"  in s or "on time" in s: return "ontime"
    return "scheduled"


def get_last_updated(soup):
    """Find the data-last-updated-time attribute."""
    span = soup.find("span", class_="last-updated-time")
    if span:
        ts = span.get("data-last-updated-time", "")
        if ts:
            try:
                # Parse ISO format e.g. 2026-04-26T16:13:05Z
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                return dt.strftime("%H:%M UTC")
            except Exception:
                return ts
    return ""


def main():
    os.makedirs("docs", exist_ok=True)

    try:
        html = fetch()
        soup = BeautifulSoup(html, "html.parser")

        print("\n=== Parsing DEPARTURES ===")
        departures = parse_flight_section(soup, "pills-departures", is_departure=True)

        print("\n=== Parsing ARRIVALS ===")
        arrivals = parse_flight_section(soup, "pills-arrivals", is_departure=False)

        # Add status types
        for f in departures + arrivals:
            f["statusType"] = categorize_status(f.get("status", ""))

        last_updated = get_last_updated(soup)

        data = {
            "success":     True,
            "fetchedAt":   datetime.now(timezone.utc).isoformat(),
            "lastUpdated": last_updated,
            "departures":  departures,
            "arrivals":    arrivals,
            "totalCount":  len(departures) + len(arrivals),
            "source":      "airport.im",
        }
        print(f"\n✓ SUCCESS — {len(departures)} departures, {len(arrivals)} arrivals")
        print(f"  Last updated on site: {last_updated}")

    except Exception as e:
        print(f"\n✗ FAILED: {e}")
        data = {
            "success":     False,
            "error":       str(e)[:200],
            "fetchedAt":   datetime.now(timezone.utc).isoformat(),
            "departures":  [],
            "arrivals":    [],
        }

    with open("docs/flights.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("\n✓ Saved docs/flights.json")


if __name__ == "__main__":
    main()
