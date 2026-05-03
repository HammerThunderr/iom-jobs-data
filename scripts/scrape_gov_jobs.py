"""
IOM Government Jobs Scraper (JobTrain) — With Full Details
-----------------------------------------------------------
Two-phase scrape:
1. List phase: Hit /Home/_JobCard?Skip=N to get all jobs (basic info)
2. Detail phase: For each job, fetch /Job/JobDetail?jobid=X for full info

Saves to docs/gov_jobs.json on GitHub Pages.
"""

import requests
import json
import os
import re
import time
from datetime import datetime, timezone
from bs4 import BeautifulSoup

API_URL    = "https://www.jobtrain.co.uk/iomgovjobs/Home/_JobCard"
DETAIL_URL = "https://www.jobtrain.co.uk/iomgovjobs/Job/JobDetail"
JOBS_PER_PAGE = 12
MAX_PAGES = 30
DELAY_BETWEEN_DETAILS = 0.7   # be polite — 0.7s between detail fetches

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://www.jobtrain.co.uk/iomgovjobs/Home/Job",
    "X-Requested-With": "XMLHttpRequest",
}


# ─────────────────────────────────────────────────────────────────────────
# PHASE 1: GET LIST OF JOBS (just title + URL)
# ─────────────────────────────────────────────────────────────────────────

def fetch_list_page(skip):
    """Fetch one page of basic jobs from the _JobCard endpoint."""
    params = {
        "Skip": skip, "what": "", "Miles": "", "Salary": "",
        "LocationId": "", "Regions": "", "DivisionIds": "",
        "ClientCategory": "", "Departments": "", "SchoolLocationId": "",
        "JobLevels": "", "SchoolSubjectId": "", "JobTypeIds": "",
        "lat": "", "long": "", "EmploymentType": "", "postedDate": "",
    }
    try:
        resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"  ✗ Fetch failed at Skip={skip}: {e}")
        return None


def parse_list_html(html):
    """Extract basic jobs (id + title + url) from list HTML fragment."""
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    seen = set()

    for link in soup.find_all("a", href=re.compile(r"JobDetail", re.IGNORECASE)):
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

        # Extract job ID (case-insensitive)
        id_match = re.search(r'jobid=(\d+)', full_url, re.IGNORECASE)
        if not id_match:
            continue
        job_id = id_match.group(1)
        if job_id in seen:
            continue
        seen.add(job_id)

        # Title from link
        title = link.get_text(strip=True)
        title = re.sub(r'\s+', ' ', title)
        title = re.sub(r'^(NEW|New|new)\s+', '', title).strip()

        if not title:
            continue

        jobs.append({
            "jobId": job_id,
            "title": title,
            "url":   full_url,
        })

    return jobs


def scrape_list():
    """Loop through all pages to get all jobs (basic info)."""
    all_jobs = []
    seen_ids = set()

    print("=== PHASE 1: Fetching job list ===")

    for page_num in range(MAX_PAGES):
        skip = page_num * JOBS_PER_PAGE
        print(f"\n[Page {page_num + 1}] Skip={skip}")

        html = fetch_list_page(skip)
        if not html or len(html) < 200:
            print(f"  Empty/tiny response — end of jobs")
            break

        page_jobs = parse_list_html(html)
        new_count = 0

        for job in page_jobs:
            if job["jobId"] in seen_ids:
                continue
            seen_ids.add(job["jobId"])
            all_jobs.append(job)
            new_count += 1

        print(f"  Found {len(page_jobs)} jobs on page, {new_count} new (total: {len(all_jobs)})")

        if new_count == 0:
            print(f"  No new jobs — stopping pagination")
            break

        if len(page_jobs) < JOBS_PER_PAGE:
            print(f"  Less than {JOBS_PER_PAGE} jobs on this page — last page")
            break

        time.sleep(0.5)

    return all_jobs


# ─────────────────────────────────────────────────────────────────────────
# PHASE 2: FETCH DETAILS FOR EACH JOB
# ─────────────────────────────────────────────────────────────────────────

def fetch_job_detail(job_id):
    """Fetch the detail page for one job."""
    try:
        resp = requests.get(
            DETAIL_URL,
            params={"jobid": job_id},
            headers={**HEADERS, "X-Requested-With": ""},  # not AJAX for detail page
            timeout=20,
        )
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"    ✗ Detail fetch failed: {e}")
        return None


def parse_detail(html):
    """Parse detail page to extract structured fields."""
    soup = BeautifulSoup(html, "html.parser")

    # Strip nav/footer/script
    for tag in soup.find_all(["nav", "footer", "header", "script", "style"]):
        tag.decompose()

    detail = {
        "department":      "",
        "location":        "",
        "salary":          "",
        "hours":           "",
        "closingDate":     "",
        "fullDescription": "",
        "duties":          "",
        "requirements":    "",
        "applicationInfo": "",
        "contactEmail":    "",
        "contactPhone":    "",
    }

    # ─── Try to find the main content area ───
    main = (soup.find("main") or
            soup.find("div", class_=re.compile(r"job.detail|vacancy.detail|main.content", re.IGNORECASE)) or
            soup.find("article") or
            soup)

    # Get all text
    full_text = main.get_text(separator="\n", strip=True)
    full_text = re.sub(r'\n{3,}', '\n\n', full_text)
    full_text = re.sub(r'[ \t]+', ' ', full_text)

    detail["fullDescription"] = full_text[:5000]

    # ─── Extract from definition lists / labelled fields ───
    # JobTrain often uses <dt>/<dd> or label/value patterns
    for dl in main.find_all(["dl", "div"]):
        dts = dl.find_all(["dt", "label", "strong", "b"])
        for dt in dts:
            label = dt.get_text(strip=True).lower().rstrip(":").strip()
            # Find the value next to it
            value = ""
            sibling = dt.find_next_sibling(["dd", "span", "div", "p"])
            if sibling:
                value = sibling.get_text(strip=True)
                value = re.sub(r'\s+', ' ', value)
                value = value[:200]

            if not value:
                continue

            if "location" in label or "where" in label:
                if not detail["location"]:
                    detail["location"] = value
            elif "salary" in label or "pay" in label:
                if not detail["salary"]:
                    detail["salary"] = value
            elif "hour" in label or "type" in label or "employment" in label:
                if not detail["hours"]:
                    detail["hours"] = value
            elif "closing" in label or "deadline" in label:
                if not detail["closingDate"]:
                    detail["closingDate"] = value
            elif "department" in label or "division" in label or "team" in label:
                if not detail["department"]:
                    detail["department"] = value

    # ─── Fallback: regex on full text for things we missed ───
    text_one_line = re.sub(r'\s+', ' ', full_text)

    if not detail["location"]:
        m = re.search(r'(?:Location|Where|Based\s+in)[:\s]+([^|.\n]{2,150}?)(?:\s{2,}|\||\n|$)', text_one_line, re.IGNORECASE)
        if m: detail["location"] = m.group(1).strip()[:120]

    if not detail["salary"]:
        m = re.search(r'(?:Salary|Pay)[:\s]+([£$€]?[\w\s,.\-/&()]+?)(?:\s{2,}|\||\n|$)', text_one_line, re.IGNORECASE)
        if m: detail["salary"] = m.group(1).strip()[:150]

    if not detail["hours"]:
        m = re.search(r'(?:Hours|Type|Employment\s*Type)[:\s]+([\w\s,/&\-]+?)(?:\s{2,}|\||\n|$)', text_one_line, re.IGNORECASE)
        if m: detail["hours"] = m.group(1).strip()[:80]

    if not detail["closingDate"]:
        m = re.search(r'(?:Closing\s+Date|Deadline|Apply\s+by)[:\s]+([\w\s,/\-]+?)(?:\s{2,}|\||\n|$)', text_one_line, re.IGNORECASE)
        if m: detail["closingDate"] = m.group(1).strip()[:80]

    if not detail["department"]:
        m = re.search(r'(?:Department|Division)[:\s]+([\w\s,&\-]+?)(?:\s{2,}|\||\n|$)', text_one_line, re.IGNORECASE)
        if m: detail["department"] = m.group(1).strip()[:120]

    # Email/phone extraction
    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', full_text)
    if emails:
        detail["contactEmail"] = emails[0]

    phones = re.findall(r'(?:0\d{4}\s?\d{3,6}|\+44\s?\d{4}\s?\d{3,6})', full_text)
    if phones:
        detail["contactPhone"] = phones[0]

    # Section extraction (Duties / Requirements / How to Apply)
    sections = {}
    current = None
    buffer = []

    for line in full_text.split('\n'):
        line = line.strip()
        if not line:
            continue
        if re.match(r'^(Job\s*)?Description[:\s]*$', line, re.IGNORECASE):
            if current: sections[current] = '\n'.join(buffer).strip()
            current, buffer = "description", []
        elif re.match(r'^(Main\s*)?Duties|Responsibilities[:\s]*$', line, re.IGNORECASE):
            if current: sections[current] = '\n'.join(buffer).strip()
            current, buffer = "duties", []
        elif re.match(r'^Requirements?|Person\s+Specification[:\s]*$', line, re.IGNORECASE):
            if current: sections[current] = '\n'.join(buffer).strip()
            current, buffer = "requirements", []
        elif re.match(r'^How\s+to\s+Apply[:\s]*$', line, re.IGNORECASE):
            if current: sections[current] = '\n'.join(buffer).strip()
            current, buffer = "application", []
        else:
            buffer.append(line)

    if current and buffer:
        sections[current] = '\n'.join(buffer).strip()

    if "duties" in sections:
        detail["duties"] = sections["duties"][:2000]
    if "requirements" in sections:
        detail["requirements"] = sections["requirements"][:2000]
    if "application" in sections:
        detail["applicationInfo"] = sections["application"][:2000]

    return detail


# ─────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────

def main():
    os.makedirs("docs", exist_ok=True)

    try:
        # Phase 1: list
        basic_jobs = scrape_list()
        if not basic_jobs:
            print("\n⚠ No jobs found in listing")
            if os.path.exists("docs/gov_jobs.json"):
                print("Keeping existing data")
                return
            jobs = []
        else:
            # Phase 2: details
            print(f"\n=== PHASE 2: Fetching details for {len(basic_jobs)} jobs ===")
            jobs = []
            for i, basic in enumerate(basic_jobs):
                print(f"\n[{i+1}/{len(basic_jobs)}] {basic['title'][:60]}")
                html = fetch_job_detail(basic["jobId"])
                if html:
                    detail = parse_detail(html)
                    job = {**basic, **detail}
                    print(f"    ✓ Loc: {job.get('location','')[:30]:<30}  Sal: {job.get('salary','')[:30]:<30}")
                else:
                    job = {
                        **basic,
                        "department": "", "location": "", "salary": "",
                        "hours": "", "closingDate": "",
                        "fullDescription": "", "duties": "", "requirements": "",
                        "applicationInfo": "", "contactEmail": "", "contactPhone": "",
                    }
                    print(f"    ⚠ Detail fetch failed — basic info only")
                jobs.append(job)

                if i < len(basic_jobs) - 1:
                    time.sleep(DELAY_BETWEEN_DETAILS)

        data = {
            "success":     True if jobs else False,
            "fetchedAt":   datetime.now(timezone.utc).isoformat(),
            "lastUpdated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "totalCount":  len(jobs),
            "jobs":        jobs,
            "source":      "jobtrain.co.uk/iomgovjobs",
        }

        print(f"\n✓ SUCCESS — {len(jobs)} TOTAL gov jobs scraped (with details)")

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
