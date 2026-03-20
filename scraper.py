"""
IOM Jobs Scraper — Combined
----------------------------
Scrapes BOTH job sources and merges into a single docs/jobs.json:
  1. services.gov.im          (plain HTML, fast)
  2. jobtrain.co.uk/iomgovjobs (JS-rendered, uses Playwright)

Run by GitHub Actions every 4 hours.
"""

import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timezone

BASE_URL_IOM  = "https://services.gov.im/job-search/results"
JOB_BASE_IOM  = "https://services.gov.im"
BASE_URL_GOVT = "https://www.jobtrain.co.uk/iomgovjobs"
JOBS_URL_GOVT = f"{BASE_URL_GOVT}/Home/Job"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-GB,en;q=0.9",
}


def scrape_iom_jobs():
    params = {
        "AreaId": "", "ClassificationId": "",
        "SearchText": "", "LastThreeDays": "False", "JobHoursOption": "",
    }
    print("Fetching services.gov.im jobs...")
    resp = requests.get(BASE_URL_IOM, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    print(f"  HTTP {resp.status_code}, {len(resp.text)} bytes")

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
                job_url  = (JOB_BASE_IOM + href) if href.startswith("/") else href
                employer = tds[2].get_text(strip=True)
                hours    = tds[3].get_text(strip=True)
                if not job_id or not title:
                    continue
                jobs.append({
                    "jobId": job_id, "title": title, "employer": employer,
                    "hours": hours, "category": current_category,
                    "url": job_url, "source": "services.gov.im",
                })

    print(f"  Found {len(jobs)} jobs")
    return jobs


def scrape_govt_jobs():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  Playwright not installed — skipping gov jobs")
        return []

    import time
    jobs = []
    api_responses = []

    print("Fetching jobtrain.co.uk jobs (headless browser)...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()

        def handle_response(response):
            try:
                url = response.url
                if "jobtrain" in url and response.status == 200:
                    ct = response.headers.get("content-type", "")
                    if "json" in ct:
                        body = response.json()
                        api_responses.append({"url": url, "body": body})
                        print(f"  Captured JSON: {url}")
            except Exception:
                pass

        page.on("response", handle_response)
        page.goto(JOBS_URL_GOVT, wait_until="networkidle", timeout=30000)

        try:
            page.wait_for_selector(
                "[data-jobid], .job-item, .vacancy-item, [class*='vacancy']",
                timeout=10000)
        except Exception:
            pass

        time.sleep(2)
        html = page.content()
        browser.close()

    # Try API responses first
    for api in api_responses:
        body = api["body"]
        job_list = (body.get("Jobs") or body.get("jobs") or
                    body.get("Vacancies") or body.get("vacancies") or [])
        if job_list:
            print(f"  {len(job_list)} jobs in API: {api['url']}")
            for j in job_list:
                job_id  = str(j.get("JobId") or j.get("jobId") or j.get("id") or "")
                title   = (j.get("JobTitle") or j.get("jobTitle") or j.get("title") or "").strip()
                dept    = (j.get("Department") or j.get("department") or j.get("Category") or "Government").strip()
                hours   = str(j.get("HoursPerWeek") or j.get("hoursPerWeek") or j.get("hours") or "")
                closing = str(j.get("ClosingDate") or j.get("closingDate") or "")
                salary  = str(j.get("Salary") or j.get("salary") or "")
                if not title:
                    continue
                jobs.append({
                    "jobId": f"gov-{job_id}", "title": title,
                    "employer": "Isle of Man Government",
                    "hours": hours, "category": dept or "Government",
                    "url": f"{BASE_URL_GOVT}/Home/JobDetail?jobId={job_id}",
                    "salary": salary, "closing": closing,
                    "source": "jobtrain.co.uk/iomgovjobs",
                })
            if jobs:
                print(f"  Parsed {len(jobs)} gov jobs")
                return jobs

    # HTML fallback
    print("  Falling back to HTML parsing...")
    soup = BeautifulSoup(html, "html.parser")
    selectors = ["[data-jobid]", ".job-item", ".vacancy-item",
                 ".job-listing", "li[class*='job']", "div[class*='vacancy']"]
    items = []
    for sel in selectors:
        items = soup.select(sel)
        if items:
            print(f"  {len(items)} items with: {sel}")
            break

    for item in items:
        job_id   = item.get("data-jobid") or item.get("data-id") or ""
        title_el = (item.select_one("h2") or item.select_one("h3") or
                    item.select_one(".job-title") or item.select_one("a"))
        title    = title_el.get_text(strip=True) if title_el else ""
        link_el  = item.select_one("a[href]")
        href     = link_el["href"] if link_el else ""
        if href and not href.startswith("http"):
            href = BASE_URL_GOVT + href
        if not href and job_id:
            href = f"{BASE_URL_GOVT}/Home/JobDetail?jobId={job_id}"
        dept_el  = item.select_one(".department, .category, [class*='dept']")
        dept     = dept_el.get_text(strip=True) if dept_el else "Government"
        hours_el = item.select_one(".hours, [class*='hours']")
        hours    = hours_el.get_text(strip=True) if hours_el else ""
        if not title:
            continue
        jobs.append({
            "jobId": f"gov-{job_id}" if job_id else f"gov-html-{len(jobs)+1}",
            "title": title, "employer": "Isle of Man Government",
            "hours": hours, "category": dept, "url": href,
            "source": "jobtrain.co.uk/iomgovjobs",
        })

    print(f"  HTML found {len(jobs)} gov jobs")
    return jobs


def main():
    iom_jobs  = scrape_iom_jobs()
    govt_jobs = scrape_govt_jobs()
    all_jobs  = iom_jobs + govt_jobs

    print(f"\nTotal: {len(all_jobs)} ({len(iom_jobs)} IOM + {len(govt_jobs)} Gov)")

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

    os.makedirs("docs", exist_ok=True)
    out_path = "docs/jobs.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    print(f"Saved to {out_path} ({os.path.getsize(out_path)/1024:.1f} KB)")


if __name__ == "__main__":
    main()
