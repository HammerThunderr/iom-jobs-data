"""
IOM Government Jobs Scraper (JobTrain) — Direct API Version
------------------------------------------------------------
Uses the internal _JobCard endpoint that JobTrain itself uses for pagination.
Returns HTML fragments which we parse with BeautifulSoup.

URL pattern:
  /iomgovjobs/Home/_JobCard?Skip=0
  /iomgovjobs/Home/_JobCard?Skip=12
  /iomgovjobs/Home/_JobCard?Skip=24
  ...

Each request returns 12 job cards as HTML.
"""

import requests
import json
import os
import re
import time
from datetime import datetime, timezone
from bs4 import BeautifulSoup

API_URL = "https://www.jobtrain.co.uk/iomgovjobs/Home/_JobCard"
JOBS_PER_PAGE = 12
MAX_PAGES = 30  # safety: 30 * 12 = 360 jobs max

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://www.jobtrain.co.uk/iomgovjobs/Home/Job",
    "X-Requested-With": "XMLHttpRequest",
}


def fetch_page(skip):
    """Fetch one page of jobs from the _JobCard endpoint."""
    params = {
        "Skip":             skip,
        "what":             "",
        "Miles":            "",
        "Salary":           "",
        "LocationId":       "",
        "Regions":          "",
        "DivisionIds":      "",
        "ClientCategory":   "",
        "Departments":      "",
        "SchoolLocationId": "",
        "JobLevels":        "",
        "SchoolSubjectId":  "",
        "JobTypeIds":       "",
        "lat":              "",
        "long":             "",
        "EmploymentType":   "",
        "postedDate":       "",
    }

    try:
        resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"  ✗ Fetch failed at Skip={skip}: {e}")
        return None


def parse_jobs_from_html(html):
    """Extract job cards from HTML fragment."""
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    # Find all links that point to JobDetail — each represents one job card
    links = soup.find_all("a", href=re.compile(r"JobDetail", re.IGNORECASE))

    seen_in_this_page = set()

    for link in links:
        try:
            href = link.get("href", "")
            if not href:
                continue

            # Build absolute URL
            if href.startswith("/"):
                full_url = "https://www.jobtrain.co.uk" + href
            elif href.startswith("http"):
                full_url = href
            else:
                full_url = "https://www.jobtrain.co.uk/iomgovjobs/" + href.lstrip("./")

            # Extract job ID
            id_match = re.search(r'jobid=(\d+)', full_url, re.IGNORECASE)
            if not id_match:
                continue
            job_id = id_match.group(1)

            # Skip if duplicate within same page (same job linked multiple times)
            if job_id in seen_in_this_page:
                continue
            seen_in_this_page.add(job_id)

            # Get the parent card container for richer text context
            card = (link.find_parent("article") or
                    link.find_parent("div", class_=re.compile(r"job", re.IGNORECASE)) or
                    link.find_parent("div", class_=re.compile(r"card", re.IGNORECASE)) or
                    link.find_parent("li") or
                    link.parent)

            # Get title from link text
            title = link.get_text(strip=True)
            title = re.sub(r'\s+', ' ', title)
            title = re.sub(r'^(NEW|New|new)\s+', '', title).strip()

            # Fallback to card heading if link text is empty
            if not title or len(title) < 3:
                if card:
                    h = (card.find("h2") or card.find("h3") or
                         card.find("h4") or card.find("h5"))
                    if h:
                        title = re.sub(r'\s+', ' ', h.get_text(strip=True))
                        title = re.sub(r'^(NEW|New|new)\s+', '', title).strip()

            if not title:
                continue

            # Get full card text for field extraction
            card_text = ""
            if card:
                card_text = re.sub(r'\s+', ' ', card.get_text(separator=" ", strip=True))

            # Extract structured fields
            location   = extract_field(card_text, ["Location", "Where", "Based"])
            salary     = extract_field(card_text, ["Salary", "Pay", "Wage"])
            hours      = extract_field(card_text, ["Hours", "Type", "Working"])
            closing    = extract_field(card_text, ["Closing", "Deadline", "Apply by"])
            department = extract_field(card_text, ["Department", "Team", "Division"])

            jobs.append({
                "jobId":       job_id,
                "title":       title,
                "department":  department,
                "location":    location,
                "salary":      salary,
                "hours":       hours,
                "closingDate": closing,
                "url":         full_url,
                "rawText":     card_text[:500] if card_text else title,
            })

        except Exception as e:
            print(f"    ✗ Card parse error: {e}")

    return jobs


def extract_field(text, labels):
    """Extract a labelled field from card text."""
    for label in labels:
        pattern = (
            rf'{label}[:\s]+([^|.]{{1,150}}?)'
            rf'(?:\s{{2,}}|\||$|\s(?:Location|Salary|Hours|Closing|Department)\b)'
        )
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            value = m.group(1).strip()
            if value and len(value) > 1:
                return value[:120]
    return ""


def scrape_all():
    """Loop through all pages until we run out of jobs."""
    all_jobs = []
    seen_ids = set()

    for page_num in range(MAX_PAGES):
        skip = page_num * JOBS_PER_PAGE
        print(f"\n[Page {page_num + 1}] Fetching Skip={skip}")

        html = fetch_page(skip)
        if not html:
            print("  ✗ Empty response — stopping")
            break

        # Sanity check — if HTML is super short, probably no jobs
        if len(html) < 200:
            print(f"  Tiny response ({len(html)} bytes) — end of jobs")
            break

        page_jobs = parse_jobs_from_html(html)
        new_count = 0

        for job in page_jobs:
            if job["jobId"] in seen_ids:
                continue
            seen_ids.add(job["jobId"])
            all_jobs.append(job)
            new_count += 1
            print(f"    ✓ {job['jobId']}: {job['title'][:60]}")

        print(f"  Page {page_num + 1}: {new_count} new jobs (total: {len(all_jobs)})")

        # If we got fewer than expected or nothing new, we're done
        if new_count == 0:
            print(f"  No new jobs on page {page_num + 1} — stopping pagination")
            break

        if len(page_jobs) < JOBS_PER_PAGE:
            print(f"  Only {len(page_jobs)} jobs on this page (less than {JOBS_PER_PAGE}) — last page")
            break

        # Polite delay between requests
        time.sleep(1)

    return all_jobs


def main():
    os.makedirs("docs", exist_ok=True)

    try:
        print("Starting gov jobs scrape (using direct _JobCard API)...")
        jobs = scrape_all()

        if not jobs:
            print("⚠ No jobs found")
            if os.path.exists("docs/gov_jobs.json"):
                print("Keeping existing data — not overwriting")
                return

        data = {
            "success":     True if jobs else False,
            "fetchedAt":   datetime.now(timezone.utc).isoformat(),
            "lastUpdated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "totalCount":  len(jobs),
            "jobs":        jobs,
            "source":      "jobtrain.co.uk/iomgovjobs",
        }

        print(f"\n✓ SUCCESS — {len(jobs)} TOTAL gov jobs scraped")

    except Exception as e:
        print(f"\n✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        data = {
            "success":     False,
            "error":       str(e)[:200],
            "fetchedAt":   datetime.now(timezone.utc).isoformat(),
            "jobs":        [],
        }

    with open("docs/gov_jobs.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("✓ Saved docs/gov_jobs.json")


if __name__ == "__main__":
    main()
