"""
IOM Jobs Scraper
----------------
Run by GitHub Actions every 4 hours.

Saves two types of files to docs/:
  docs/jobs.json          — full list of all jobs
  docs/job/218478.json    — detail page for each individual job
  docs/job/219042.json
  ... etc.

The Android app fetches:
  - jobs.json on app open (job list)
  - job/XXXXX.json when user taps a job (detail)
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import time
from datetime import datetime, timezone

BASE_URL      = "https://services.gov.im/job-search/results"
JOB_BASE_URL  = "https://services.gov.im"
JOB_VIEW_PATH = "/job-search/viewjob?Id="

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}


# ─────────────────────────────────────────────────────────
# Scrape the main jobs list
# ─────────────────────────────────────────────────────────

def scrape_all_jobs():
    params = {
        "AreaId": "", "ClassificationId": "",
        "SearchText": "", "LastThreeDays": "False", "JobHoursOption": "",
    }
    print(f"Fetching job list from {BASE_URL}...")
    resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()

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


# ─────────────────────────────────────────────────────────
# Scrape a single job detail page
# ─────────────────────────────────────────────────────────

def scrape_job_detail(job_id):
    url  = JOB_BASE_URL + JOB_VIEW_PATH + job_id
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    detail = {
        "jobId":      job_id,
        "title":      "",
        "employer":   "",
        "fields":     {},   # label → value (salary, closing date, etc.)
        "description":"",
        "howToApply": "",
        "url":        url,
    }

    # Title
    h1 = soup.find("h1")
    if h1:
        detail["title"] = h1.get_text(strip=True)

    # Key/value table rows
    for row in soup.select("table tr"):
        th = row.find("th")
        td = row.find("td")
        if th and td:
            key   = th.get_text(strip=True)
            value = td.get_text(strip=True)
            if key and value:
                detail["fields"][key] = value
                if "employer" in key.lower():
                    detail["employer"] = value

    # Definition lists (dl/dt/dd)
    for dt in soup.select("dl dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            key   = dt.get_text(strip=True)
            value = dd.get_text(strip=True)
            if key and value and key not in detail["fields"]:
                detail["fields"][key] = value

    # Job description — strip nav/form noise from .content
    content = soup.select_one(".content")
    if content:
        for tag in content.select(
            "header, footer, nav, form, .breadcrumb, "
            ".noticebox, .section--collapsible, script, style, table"
        ):
            tag.decompose()

        parts = []
        # Paragraphs
        for p in content.select("p"):
            text = p.get_text(strip=True)
            if len(text) > 20:
                parts.append(text)
        # Lists
        for ul in content.select("ul, ol"):
            for li in ul.select("li"):
                text = li.get_text(strip=True)
                if text:
                    parts.append("• " + text)

        detail["description"] = "\n\n".join(parts).strip()

        # Fallback
        if not detail["description"]:
            detail["description"] = content.get_text(separator="\n", strip=True)

    # How to apply
    for el in soup.select("h2, h3, h4, strong, b"):
        text = el.get_text(strip=True).lower()
        if "how to apply" in text or "application" in text:
            nxt = el.find_next_sibling()
            if nxt:
                detail["howToApply"] = nxt.get_text(strip=True)
            break

    return detail


# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────

def main():
    # ── Step 1: Scrape job list ────────────────────────
    jobs = scrape_all_jobs()
    print(f"Scraped {len(jobs)} jobs")

    os.makedirs("docs/job", exist_ok=True)

    now = datetime.now(timezone.utc)
    jobs_output = {
        "success":          True,
        "total":            len(jobs),
        "lastUpdated":      now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lastUpdatedHuman": now.strftime("%d %b %Y at %H:%M UTC"),
        "nextUpdate":       "Every 4 hours",
        "source":           "services.gov.im",
        "jobs":             jobs,
    }

    with open("docs/jobs.json", "w", encoding="utf-8") as f:
        json.dump(jobs_output, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Saved docs/jobs.json ({os.path.getsize('docs/jobs.json') / 1024:.1f} KB)")

    # ── Step 2: Scrape each job's detail page ──────────
    # Load existing job IDs so we skip ones already scraped
    existing = set(
        f.replace(".json", "")
        for f in os.listdir("docs/job")
        if f.endswith(".json")
    )

    # Get current job IDs from list
    current_ids = {job["jobId"] for job in jobs}

    # Delete detail files for jobs no longer in the list
    stale = existing - current_ids
    for job_id in stale:
        path = f"docs/job/{job_id}.json"
        if os.path.exists(path):
            os.remove(path)
            print(f"  Removed stale: {path}")

    # Only scrape new jobs we don't have yet
    new_ids = current_ids - existing
    print(f"\nScraping {len(new_ids)} new job detail pages "
          f"({len(existing)} already cached, {len(stale)} stale removed)...")

    success = 0
    failed  = 0

    for i, job in enumerate(jobs):
        job_id = job["jobId"]

        if job_id not in new_ids:
            continue  # already have this detail

        try:
            detail = scrape_job_detail(job_id)
            out_path = f"docs/job/{job_id}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(detail, f, ensure_ascii=False, separators=(",", ":"))
            success += 1
            print(f"  [{i+1}/{len(jobs)}] ✓ {job_id} — {job['title'][:50]}")

            # Small delay to be polite to the server
            time.sleep(0.3)

        except Exception as e:
            failed += 1
            print(f"  [{i+1}/{len(jobs)}] ✗ {job_id} — {e}")

    print(f"\nDone! {success} new details scraped, {failed} failed")
    print(f"Total detail files: {len(os.listdir('docs/job'))}")


if __name__ == "__main__":
    main()
