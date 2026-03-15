"""
IOM Jobs Scraper
----------------
Run by GitHub Actions every 4 hours.
Saves jobs.json to docs/ folder which is served by GitHub Pages.
"""

import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timezone

BASE_URL = "https://services.gov.im/job-search/results"
JOB_BASE = "https://services.gov.im"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-GB,en;q=0.9",
}


def scrape_all_jobs():
    params = {
        "AreaId": "",
        "ClassificationId": "",
        "SearchText": "",
        "LastThreeDays": "False",
        "JobHoursOption": "",
    }

    print(f"Fetching jobs from {BASE_URL}...")
    resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    print(f"Got response: HTTP {resp.status_code}, {len(resp.text)} bytes")

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
                job_url  = (JOB_BASE + href) if href.startswith("/") else href
                employer = tds[2].get_text(strip=True)
                hours    = tds[3].get_text(strip=True)

                if not job_id or not title:
                    continue

                jobs.append({
                    "jobId":    job_id,
                    "title":    title,
                    "employer": employer,
                    "hours":    hours,
                    "category": current_category,
                    "url":      job_url,
                })

    return jobs


def scrape_job_detail(job_id):
    url  = f"{JOB_BASE}/job-search/viewjob?Id={job_id}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup.select("header, footer, .breadcrumb, nav, script, style, form, .section--collapsible, .noticebox"):
        tag.decompose()

    content = soup.select_one(".content")
    return content.get_text(separator="\n", strip=True) if content else ""


def main():
    jobs = scrape_all_jobs()
    print(f"Scraped {len(jobs)} jobs")

    # Build output
    now = datetime.now(timezone.utc)
    output = {
        "success":      True,
        "total":        len(jobs),
        "lastUpdated":  now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lastUpdatedHuman": now.strftime("%d %b %Y at %H:%M UTC"),
        "nextUpdate":   "Every 4 hours",
        "source":       "services.gov.im",
        "jobs":         jobs,
    }

    # Write to docs/jobs.json (served by GitHub Pages)
    os.makedirs("docs", exist_ok=True)
    out_path = "docs/jobs.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    print(f"Saved {len(jobs)} jobs to {out_path}")
    print(f"File size: {os.path.getsize(out_path) / 1024:.1f} KB")
    print(f"Last updated: {output['lastUpdatedHuman']}")


if __name__ == "__main__":
    main()
