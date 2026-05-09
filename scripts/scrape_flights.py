"""
Isle of Man Airport Flight Scraper — Robust Version
-----------------------------------------------------
Scrapes departures + arrivals from airport.im/live-flight-information/
with multiple retry strategies (different URLs, headers, timing).
"""

import requests
import urllib3
import json
import os
import re
import time
import random
from datetime import datetime, timezone
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Try multiple URLs — sometimes airport.im responds to one but not the other
URLS = [
    "https://www.airport.im/live-flight-information/",
    "https://airport.im/live-flight-information/",
    "https://www.airport.im/live-flight-information",
]

# Multiple realistic browser User-Agents to rotate
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def make_headers(ua=None):
    """Build realistic browser headers."""
    return {
        "User-Agent": ua or random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }


def fetch():
    """Try multiple strategies to fetch the page."""
    last_error = None

    # Strategy 1: Try each URL with different UA, both verify modes
    for url in URLS:
        for ua in USER_AGENTS:
            for verify in [True, False]:
                try:
                    print(f"  Trying {url} (verify={verify}, UA={ua[:50]}...)")
                    session = requests.Session()
                    session.headers.update(make_headers(ua))
                    resp = session.get(url, timeout=30, verify=verify, allow_redirects=True)
                    resp.raise_for_status()
                    if len(resp.text) > 5000:  # sanity check — real page is big
                        print(f"  ✓ SUCCESS: {len(resp.text)} bytes from {url}")
                        return resp.text
                    else:
                        print(f"  ⚠ Got {len(resp.text)} bytes — too small, trying next")
                except Exception as e:
                    last_error = f"{type(e).__name__}: {str(e)[:100]}"
                    print(f"  ✗ Failed: {last_error}")
                # Small delay to avoid being flagged as a bot
                time.sleep(random.uniform(0.5, 1.5))

    raise Exception(f"All fetch attempts failed. Last: {last_error}")


def parse_flight_section(soup, tab_id, is_departure):
    """Parse one tab pane (#pills-departures or #pills-arrivals)."""
    flights = []
    tab = soup.find("div", id=tab_id)
    if not tab:
        print(f"  ✗ Could not find #{tab_id}")
        return flights

    airport_spans = tab.find_all("span", class_="flight-information__airport")
    print(f"  Found {len(airport_spans)} flights in #{tab_id}")

    for airport_span in airport_spans:
        try:
            row = airport_span.find_parent(
                "div", class_=re.compile(r"d-flex.*flex-wrap"))
            if not row:
                continue

            airport = airport_span.get_text(strip=True)

            flight_no_div = row.find("div", class_="flight-information__flight-no")
            flight_no = flight_no_div.get_text(strip=True) if flight_no_div else ""

            airline = ""
            airline_container = row.find(
                "div", class_=re.compile(r"flight-information__flight-airline"))
            if airline_container:
                divs = airline_container.find_all("div", recursive=False)
                for d in divs:
                    classes = d.get("class", [])
                    if "flight-information__flight-no" not in classes:
                        airline = d.get_text(strip=True)
                        break

            scheduled = ""
            time_span = row.find(
                "span", class_=re.compile(r"d-inline-flex.*align-items-center"))
            if time_span:
                for svg in time_span.find_all("svg"):
                    svg.decompose()
                scheduled = time_span.get_text(strip=True)

            status = "Scheduled"
            status_badge = row.find(
                "span", class_=re.compile(r"flight-information__status-badge"))
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
    if "cancel" in s: return "cancelled"
    if "delay" in s: return "delayed"
    if "boarding" in s or "gate closed" in s: return "boarding"
    if "departed" in s: return "departed"
    if "arrived" in s or "landed" in s: return "arrived"
    if "expected" in s: return "expected"
    if "on-time" in s or "on time" in s: return "ontime"
    return "scheduled"


def get_last_updated(soup):
    span = soup.find("span", class_="last-updated-time")
    if span:
        ts = span.get("data-last-updated-time", "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                return dt.strftime("%H:%M UTC")
            except Exception:
                return ts
    return ""


def main():
    os.makedirs("docs", exist_ok=True)

    try:
        print("Starting flight scrape with multi-strategy fetcher...")
        html = fetch()
        soup = BeautifulSoup(html, "html.parser")

        print("\n=== Parsing DEPARTURES ===")
        departures = parse_flight_section(soup, "pills-departures", is_departure=True)

        print("\n=== Parsing ARRIVALS ===")
        arrivals = parse_flight_section(soup, "pills-arrivals", is_departure=False)

        for f in departures + arrivals:
            f["statusType"] = categorize_status(f.get("status", ""))

        last_updated = get_last_updated(soup)

        # Don't overwrite good data with empty if parsing somehow failed
        if not departures and not arrivals:
            print("⚠ Got page but parsed 0 flights — keeping existing data")
            if os.path.exists("docs/flights.json"):
                return

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

    except Exception as e:
        print(f"\n✗ FAILED: {e}")
        # Don't overwrite — keep last working data
        if os.path.exists("docs/flights.json"):
            print("Keeping existing data (last successful scrape)")
            return

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
