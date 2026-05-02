"""
IOM Jobs Scraper with Full Job Details
---------------------------------------
Scrapes services.gov.im/job-search every 4 hours.
For EACH job, also fetches the detail page with full description,
salary, requirements, contact info, etc.

Saves to docs/jobs.json on GitHub Pages.

Place at: scripts/scrape_jobs.py in your iom-jobs-data repo.
"""

import requests
import json
import os
import time
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup

BASE_URL      = "https://services.gov.im/job-search/results"
JOB_BASE_URL  = "https://services.gov.im"
JOB_VIEW_PATH = "/job-search/viewjob?Id="

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

DELAY_BETWEEN_DETAILS = 1   # 1 second between job detail fetches (polite)


def fetch(url, retries=2):
    """Fetch URL with retry on failure."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(3)
                continue
            print(f"  ✗ Fetch failed: {e}")
            return None
    return None


def scrape_job_list():
    """Scrape the main jobs listing page."""
    print("Fetching main jobs list...")

    params = {
        "AreaId": "",
        "ClassificationId": "",
        "SearchText": "",
        "LastThreeDays": "False",
        "JobHoursOption": "",
    }

    try:
        resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"✗ Failed to fetch jobs list: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    jobs = []
    current_category = ""

    for el in soup.select("h2, table.table"):
        if el.name == "h2":
            current_category = el.get_text(strip=True)
        elif el.name == "table":
            for row in el.select("tr"):
                tds = row.select("td")
                if len(tds) < 4:
                    continue

                job_id   = tds[0].get_text(strip=True)
                title_el = tds[1].find("a")
                title    = title_el.get_text(strip=True) if title_el else tds[1].get_text(strip=True)
                href     = title_el.get("href", "") if title_el else ""
                job_url  = (JOB_BASE_URL + href) if href.startswith("/") else href
                employer = tds[2].get_text(strip=True)
                job_hrs  = tds[3].get_text(strip=True)

                if not job_id or not title:
                    continue

                jobs.append({
                    "jobId":    job_id,
                    "title":    title,
                    "employer": employer,
                    "hours":    job_hrs,
                    "category": current_category,
                    "url":      job_url,
                })

    print(f"  ✓ Found {len(jobs)} jobs in listing")
    return jobs


def scrape_job_detail(job_id):
    """Scrape the detail page for a specific job."""
    url = JOB_BASE_URL + JOB_VIEW_PATH + job_id
    html = fetch(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    # Remove unwanted elements
    for tag in soup.select("header, footer, .breadcrumb, nav, script, style, form"):
        tag.decompose()

    # Extract main content
    content = soup.select_one(".content")
    if not content:
        content = soup.body
    if not content:
        return None

    # Remove collapsible sections and notice boxes
    for el in content.select(".section--collapsible, .noticebox"):
        el.decompose()

    # Build structured detail
    detail = {
        "fullDescription": "",
        "salary":          "",
        "location":        "",
        "closingDate":     "",
        "contactName":     "",
        "contactEmail":    "",
        "contactPhone":    "",
        "applicationInfo": "",
        "duties":          "",
        "requirements":    "",
        "rawText":         "",
    }

    # Get all text for raw fallback
    raw_text = content.get_text(separator="\n", strip=True)
    raw_text = re.sub(r'\n{3,}', '\n\n', raw_text)
    detail["rawText"] = raw_text
    detail["fullDescription"] = raw_text  # alias

    # Try to extract specific fields by looking for labels
    text_lower = raw_text.lower()

    # Salary
    salary_match = re.search(r'salary[:\s]*([£$€\d,.\s\-toperday/peryear]+(?:per\s+annum)?)',
                             raw_text, re.IGNORECASE)
    if salary_match:
        detail["salary"] = salary_match.group(1).strip()[:150]

    # Closing date
    close_match = re.search(r'closing\s*date[:\s]*([^\n]+)', raw_text, re.IGNORECASE)
    if close_match:
        detail["closingDate"] = close_match.group(1).strip()[:80]

    # Location
    loc_match = re.search(r'location[:\s]*([^\n]+)', raw_text, re.IGNORECASE)
    if loc_match:
        detail["location"] = loc_match.group(1).strip()[:100]

    # Email — find all emails in the text
    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', raw_text)
    if emails:
        detail["contactEmail"] = emails[0]

    # Phone — IOM phone pattern (e.g. 01624 685555)
    phones = re.findall(r'(?:0\d{4}\s?\d{6}|\+44\s?\d{4}\s?\d{6})', raw_text)
    if phones:
        detail["contactPhone"] = phones[0]

    # Try to extract sections by common headers
    sections = {}
    current_section = None
    section_buffer = []

    for line in raw_text.split('\n'):
        line = line.strip()
        if not line:
            continue
        # Detect section headers (usually short, end with colon, or all caps)
        if re.match(r'^(Job\s*)?Description[:\s]*$', line, re.IGNORECASE):
            if current_section:
                sections[current_section] = '\n'.join(section_buffer).strip()
            current_section = "description"
            section_buffer = []
        elif re.match(r'^(Main\s*)?Duties[:\s]*$', line, re.IGNORECASE):
            if current_section:
                sections[current_section] = '\n'.join(section_buffer).strip()
            current_section = "duties"
            section_buffer = []
        elif re.match(r'^Requirements[:\s]*$', line, re.IGNORECASE):
            if current_section:
                sections[current_section] = '\n'.join(section_buffer).strip()
            current_section = "requirements"
            section_buffer = []
        elif re.match(r'^How\s+to\s+Apply[:\s]*$', line, re.IGNORECASE):
            if current_section:
                sections[current_section] = '\n'.join(section_buffer).strip()
            current_section = "application"
            section_buffer = []
        else:
            section_buffer.append(line)

    if current_section and section_buffer:
        sections[current_section] = '\n'.join(section_buffer).strip()

    if "duties" in sections:
        detail["duties"] = sections["duties"][:2000]
    if "requirements" in sections:
        detail["requirements"] = sections["requirements"][:2000]
    if "application" in sections:
        detail["applicationInfo"] = sections["application"][:2000]

    return detail


def main():
    os.makedirs("docs", exist_ok=True)

    # Step 1: Fetch the main listing
    jobs = scrape_job_list()
    if not jobs:
        # Don't overwrite existing data on failure
        if os.path.exists("docs/jobs.json"):
            print("⚠ Listing fetch failed — keeping existing data")
            return
        data = {
            "success": False,
            "error":   "Failed to fetch jobs listing",
            "lastUpdated": datetime.now(timezone.utc).isoformat(),
            "lastUpdatedHuman": datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
            "jobs": [],
        }
        with open("docs/jobs.json", "w") as f:
            json.dump(data, f, indent=2)
        return

    # Step 2: Fetch detail page for each job
    print(f"\nFetching details for {len(jobs)} jobs...")
    success_count = 0
    fail_count = 0

    for i, job in enumerate(jobs):
        print(f"  [{i+1}/{len(jobs)}] {job['title'][:60]}...")
        detail = scrape_job_detail(job["jobId"])

        if detail:
            # Merge detail fields into the job
            job.update(detail)
            success_count += 1
        else:
            fail_count += 1
            # Add empty detail fields so app doesn't break
            job.update({
                "fullDescription": "",
                "salary":          "",
                "location":        "",
                "closingDate":     "",
                "contactName":     "",
                "contactEmail":    "",
                "contactPhone":    "",
                "applicationInfo": "",
                "duties":          "",
                "requirements":    "",
                "rawText":         "",
            })

        # Polite delay between detail fetches
        if i < len(jobs) - 1:
            time.sleep(DELAY_BETWEEN_DETAILS)

    print(f"\n✓ Fetched {success_count} details, {fail_count} failed")

    # Step 3: Build categories index
    categories = {}
    for j in jobs:
        cat = j.get("category", "")
        if cat:
            categories[cat] = categories.get(cat, 0) + 1

    # Step 4: Save
    data = {
        "success":          True,
        "lastUpdated":      datetime.now(timezone.utc).isoformat(),
        "lastUpdatedHuman": datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
        "totalCount":       len(jobs),
        "categories":       categories,
        "jobs":             jobs,
    }

    with open("docs/jobs.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n✓ Saved {len(jobs)} jobs to docs/jobs.json")


if __name__ == "__main__":
    main()
