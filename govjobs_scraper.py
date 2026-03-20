"""
IOM Government Jobs Scraper (jobtrain.co.uk)
---------------------------------------------
Scrapes https://www.jobtrain.co.uk/iomgovjobs/Home/Job
The site renders via JavaScript, so we use Playwright (headless browser)
to load the page and wait for jobs to appear, then parse the DOM.

Run locally:
    pip install playwright beautifulsoup4 requests
    playwright install chromium
    python govjobs_scraper.py

GitHub Actions installs playwright automatically via requirements.txt
"""

import json
import os
import time
from datetime import datetime, timezone
from bs4 import BeautifulSoup

BASE_URL  = "https://www.jobtrain.co.uk/iomgovjobs"
JOBS_URL  = f"{BASE_URL}/Home/Job"
SOURCE    = "jobtrain.co.uk/iomgovjobs"


def scrape_with_playwright():
    """Use headless Chromium to load the JS-rendered jobs page."""
    from playwright.sync_api import sync_playwright

    jobs = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Intercept XHR/fetch calls to find the jobs API endpoint
        api_responses = []

        def handle_response(response):
            url = response.url
            # Jobtrain loads jobs via internal API calls — capture JSON responses
            if "jobtrain" in url and response.status == 200:
                content_type = response.headers.get("content-type", "")
                if "json" in content_type or "javascript" in content_type:
                    try:
                        body = response.json()
                        api_responses.append({"url": url, "body": body})
                        print(f"  Captured JSON from: {url}")
                    except Exception:
                        pass

        page.on("response", handle_response)

        print(f"Loading: {JOBS_URL}")
        page.goto(JOBS_URL, wait_until="networkidle", timeout=30000)

        # Wait for job cards to appear in the DOM
        try:
            page.wait_for_selector(".job-item, .vacancy-item, [class*='job'], [class*='vacancy']",
                                   timeout=15000)
        except Exception:
            print("  Selector timeout — trying to parse whatever loaded")

        # Extra wait for any lazy loading
        time.sleep(3)

        html = page.content()
        browser.close()

        # ── Try to extract from captured API responses first ──────────
        for api in api_responses:
            body = api["body"]
            # Jobtrain API typically returns {Jobs: [...]} or {jobs: [...]}
            job_list = (body.get("Jobs") or body.get("jobs") or
                        body.get("Vacancies") or body.get("vacancies") or [])
            if job_list:
                print(f"  Found {len(job_list)} jobs in API response: {api['url']}")
                for j in job_list:
                    job_id  = str(j.get("JobId") or j.get("jobId") or j.get("id") or "")
                    title   = j.get("JobTitle") or j.get("jobTitle") or j.get("title") or ""
                    dept    = j.get("Department") or j.get("department") or j.get("category") or ""
                    loc     = j.get("Location") or j.get("location") or "Isle of Man"
                    hours   = j.get("HoursPerWeek") or j.get("hoursPerWeek") or j.get("hours") or ""
                    closing = j.get("ClosingDate") or j.get("closingDate") or ""
                    salary  = j.get("Salary") or j.get("salary") or ""

                    if not job_id or not title:
                        continue

                    detail_url = f"{BASE_URL}/Home/JobDetail?jobId={job_id}"
                    jobs.append({
                        "jobId":    f"gov-{job_id}",
                        "title":    title.strip(),
                        "employer": "Isle of Man Government",
                        "hours":    f"{hours}",
                        "category": dept.strip() if dept else "Government",
                        "url":      detail_url,
                        "salary":   salary,
                        "closing":  closing,
                        "location": loc,
                        "source":   SOURCE,
                    })
                if jobs:
                    return jobs

        # ── Fallback: parse rendered HTML ─────────────────────────────
        print("  Falling back to HTML parsing...")
        jobs = parse_html(html)

    return jobs


def parse_html(html):
    """Parse job listings from the rendered HTML DOM."""
    jobs = []
    soup = BeautifulSoup(html, "html.parser")

    # Jobtrain typically renders jobs in a list with class patterns like:
    # .job-item, .vacancy-row, [data-jobid], etc.
    # Try several selectors
    selectors = [
        "[data-jobid]",
        ".job-item",
        ".vacancy-item",
        ".job-listing",
        "li[class*='job']",
        "div[class*='vacancy']",
    ]

    items = []
    for sel in selectors:
        items = soup.select(sel)
        if items:
            print(f"  Found {len(items)} items with selector: {sel}")
            break

    for item in items:
        # Job ID
        job_id = (item.get("data-jobid") or
                  item.get("data-id") or
                  item.get("id", "").replace("job-", ""))

        # Title — look for heading elements inside the item
        title_el = (item.select_one("h2") or item.select_one("h3") or
                    item.select_one(".job-title") or item.select_one("a"))
        title = title_el.get_text(strip=True) if title_el else ""

        # Link
        link_el = item.select_one("a[href]")
        href = link_el["href"] if link_el else ""
        if href and not href.startswith("http"):
            href = BASE_URL + href
        if not href and job_id:
            href = f"{BASE_URL}/Home/JobDetail?jobId={job_id}"

        # Department / category
        dept_el = item.select_one(".department, .category, [class*='dept']")
        dept = dept_el.get_text(strip=True) if dept_el else "Government"

        # Hours / salary
        hours_el = item.select_one(".hours, .salary, [class*='hours'], [class*='salary']")
        hours = hours_el.get_text(strip=True) if hours_el else ""

        if not title:
            continue

        jobs.append({
            "jobId":    f"gov-{job_id}" if job_id else f"gov-{len(jobs)+1}",
            "title":    title,
            "employer": "Isle of Man Government",
            "hours":    hours,
            "category": dept,
            "url":      href,
            "source":   SOURCE,
        })

    print(f"  HTML parsing found {len(jobs)} jobs")
    return jobs


def main():
    print("Scraping IOM Government Jobs (jobtrain.co.uk)...")
    gov_jobs = scrape_with_playwright()
    print(f"Found {len(gov_jobs)} government jobs")

    if not gov_jobs:
        print("No jobs found — skipping merge")
        return

    # ── Load existing jobs.json ───────────────────────────────────────
    out_path = "docs/jobs.json"
    os.makedirs("docs", exist_ok=True)

    existing = {"jobs": [], "total": 0}
    if os.path.exists(out_path):
        with open(out_path, "r", encoding="utf-8") as f:
            try:
                existing = json.load(f)
            except Exception:
                pass

    # ── Remove old gov jobs, add fresh ones ──────────────────────────
    other_jobs = [j for j in existing.get("jobs", [])
                  if not str(j.get("jobId", "")).startswith("gov-")]
    all_jobs = other_jobs + gov_jobs

    now = datetime.now(timezone.utc)
    output = {
        "success":          True,
        "total":            len(all_jobs),
        "lastUpdated":      now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lastUpdatedHuman": now.strftime("%d %b %Y at %H:%M UTC"),
        "nextUpdate":       "Every 4 hours",
        "source":           "services.gov.im + jobtrain.co.uk/iomgovjobs",
        "jobs":             all_jobs,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    print(f"Saved {len(all_jobs)} total jobs ({len(gov_jobs)} gov + {len(other_jobs)} other)")
    print(f"File: {out_path} ({os.path.getsize(out_path)/1024:.1f} KB)")


if __name__ == "__main__":
    main()
