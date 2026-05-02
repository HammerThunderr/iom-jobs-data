"""
IOM Government Jobs Scraper (JobTrain)
---------------------------------------
Scrapes IOM government jobs from jobtrain.co.uk/iomgovjobs.
Saves to docs/gov_jobs.json on GitHub Pages.

Place at: scripts/scrape_gov_jobs.py in your iom-jobs-data repo.
"""

import requests
import json
import os
import re
import time
from datetime import datetime, timezone
from bs4 import BeautifulSoup

BASE_URL = "https://www.jobtrain.co.uk/iomgovjobs/Vacancies/Index/2"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}


def fetch_page(skip=0):
    """Fetch one page of job results."""
    url = f"{BASE_URL}?Skip={skip}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"  ✗ Fetch failed: {e}")
        return None


def parse_jobs(html):
    """Parse jobs from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    # Each job is a _JobCard partial render
    cards = soup.select(".vacancy-card, [class*='_JobCard']")
    if not cards:
        # Try alternative selectors
        cards = soup.select(".card.vacancy, .row.vacancy")

    print(f"  Found {len(cards)} cards on page")

    for card in cards:
        try:
            # Title
            title_el = card.find(["h3", "h4", "h5"]) or card.select_one(".vacancy-title")
            title_text = title_el.get_text(strip=True) if title_el else ""

            # Skip "NEW" badge text
            title_text = re.sub(r'^NEW\s+', '', title_text, flags=re.IGNORECASE).strip()

            # Link
            link_el = card.find("a")
            url = ""
            if link_el:
                href = link_el.get("href", "")
                if href.startswith("/"):
                    url = "https://www.jobtrain.co.uk" + href
                elif href.startswith("http"):
                    url = href

            # Other fields
            text = card.get_text(separator="\n", strip=True)

            # Try to extract reference, location, salary, type, closing
            ref_match    = re.search(r'(?:Ref(?:erence)?:?\s*)([A-Z0-9\-/]+)', text, re.IGNORECASE)
            location     = ""
            salary       = ""
            job_type     = ""
            closing      = ""

            for label in card.select(".vacancy-detail, .detail-item, dt, dd, span, div"):
                t = label.get_text(strip=True)
                low = t.lower()
                if "location" in low:
                    parent = label.parent
                    if parent:
                        location = parent.get_text(strip=True).replace(t, '').strip()
                if "salary" in low:
                    parent = label.parent
                    if parent:
                        salary = parent.get_text(strip=True).replace(t, '').strip()
                if "closing" in low:
                    parent = label.parent
                    if parent:
                        closing = parent.get_text(strip=True).replace(t, '').strip()

            if not title_text:
                continue

            job = {
                "title":       title_text,
                "url":         url,
                "reference":   ref_match.group(1) if ref_match else "",
                "location":    location[:100],
                "salary":      salary[:150],
                "type":        job_type,
                "closingDate": closing[:80],
                "rawText":     text[:500],
            }
            jobs.append(job)

        except Exception as e:
            print(f"  Card parse error: {e}")

    return jobs


def main():
    os.makedirs("docs", exist_ok=True)

    all_jobs = []
    skip = 0
    max_pages = 10

    for page in range(max_pages):
        print(f"\n[Page {page + 1}] Skip={skip}")
        html = fetch_page(skip)
        if not html:
            break

        page_jobs = parse_jobs(html)
        if not page_jobs:
            print("  No more jobs found")
            break

        all_jobs.extend(page_jobs)
        skip += len(page_jobs)
        time.sleep(2)  # polite delay

    print(f"\n=== Total: {len(all_jobs)} jobs ===")

    if not all_jobs:
        # Don't overwrite existing data on failure
        if os.path.exists("docs/gov_jobs.json"):
            print("⚠ Scrape failed — keeping existing data")
            return

    data = {
        "success":     True if all_jobs else False,
        "fetchedAt":   datetime.now(timezone.utc).isoformat(),
        "lastUpdated": datetime.now(timezone.utc).strftime("%H:%M UTC"),
        "totalCount":  len(all_jobs),
        "jobs":        all_jobs,
        "source":      "jobtrain.co.uk/iomgovjobs",
    }

    with open("docs/gov_jobs.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✓ Saved docs/gov_jobs.json")


if __name__ == "__main__":
    main()
