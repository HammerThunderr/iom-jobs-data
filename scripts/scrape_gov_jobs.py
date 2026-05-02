"""
IOM Government Jobs Scraper (JobTrain) — Robust Playwright Version
-------------------------------------------------------------------
JobTrain uses heavy JS rendering. Strategy:
1. Open page with Playwright
2. Wait for JS to complete + extra timeout
3. Scroll to load all jobs
4. Find ALL <a> tags pointing to JobDetail pages
5. Extract data from surrounding context

Saves to docs/gov_jobs.json on GitHub Pages.
"""

import json
import os
import re
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

LIST_URL = "https://www.jobtrain.co.uk/iomgovjobs/Home/Job"


def scrape():
    """Scrape all gov jobs using a network-aware Playwright approach."""
    jobs = []

    with sync_playwright() as p:
        print("Launching browser...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 1024},
        )
        page = context.new_page()

        # Capture all API calls so we can find the jobs endpoint
        api_responses = []

        def handle_response(response):
            url = response.url
            if "iomgovjobs" in url and (
                "json" in (response.headers.get("content-type") or "").lower()
                or "/api/" in url.lower()
                or "search" in url.lower()
                or "jobs" in url.lower()
                or "vacancies" in url.lower()
            ):
                try:
                    body = response.text()
                    if body and (body.startswith("[") or body.startswith("{")):
                        api_responses.append({"url": url, "body": body[:50000]})
                        print(f"  📡 API response: {url[:100]} ({len(body)} bytes)")
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            print(f"Navigating to {LIST_URL}...")
            page.goto(LIST_URL, wait_until="networkidle", timeout=60000)

            # Wait extra for any deferred JS
            page.wait_for_timeout(5000)

            # Scroll progressively to trigger lazy loading
            for i in range(15):
                page.evaluate(f"window.scrollTo(0, {(i+1) * 800})")
                page.wait_for_timeout(500)

            # Final scroll back to top
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(2000)

            # Try API responses first — most reliable
            for api in api_responses:
                try:
                    data = json.loads(api["body"])
                    candidates = []
                    if isinstance(data, list):
                        candidates = data
                    elif isinstance(data, dict):
                        # Look for arrays inside
                        for key in ["jobs", "data", "items", "results", "vacancies", "Jobs", "Items"]:
                            if key in data and isinstance(data[key], list):
                                candidates = data[key]
                                break

                    if candidates and isinstance(candidates[0], dict):
                        print(f"\n✓ Found {len(candidates)} jobs in API response!")
                        for item in candidates:
                            job = parse_api_item(item)
                            if job:
                                jobs.append(job)
                        if jobs:
                            return jobs
                except Exception as e:
                    pass

            # Fallback: parse rendered HTML
            print("\nNo API found, parsing rendered HTML...")

            # Strategy: find ALL links to JobDetail
            links = page.query_selector_all('a[href*="JobDetail"]')
            print(f"Found {len(links)} JobDetail links")

            seen_ids = set()
            for link in links:
                try:
                    href = link.get_attribute("href") or ""
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

                    # Dedupe
                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    # Get title from link text
                    title = (link.text_content() or "").strip()
                    title = re.sub(r'\s+', ' ', title)
                    title = re.sub(r'^(NEW|New|new)\s+', '', title).strip()

                    # If link text is empty, look at title attribute or aria-label
                    if not title or len(title) < 3:
                        title = (link.get_attribute("title") or
                                link.get_attribute("aria-label") or "").strip()
                        title = re.sub(r'^(NEW|New|new)\s+', '', title).strip()

                    # Get parent context for additional info
                    parent_text = ""
                    try:
                        parent_text = link.evaluate("""
                            el => {
                                let p = el.closest('article, li, div[class*="job"], div[class*="vacancy"], div[class*="card"], section');
                                return p ? p.innerText : el.parentElement?.innerText || '';
                            }
                        """) or ""
                    except Exception:
                        pass

                    parent_text = re.sub(r'\s+', ' ', parent_text).strip()

                    # If still no title, try first non-trivial line of parent text
                    if not title or len(title) < 3:
                        for line in parent_text.split('.'):
                            line = line.strip()
                            line = re.sub(r'^(NEW|New|new)\s+', '', line).strip()
                            if line and len(line) > 5 and len(line) < 200:
                                title = line
                                break

                    if not title:
                        continue

                    # Extract fields from parent text
                    location  = extract_field(parent_text, ["Location", "Where", "Based"])
                    salary    = extract_field(parent_text, ["Salary", "Pay", "Wage"])
                    hours     = extract_field(parent_text, ["Hours", "Type", "Working"])
                    closing   = extract_field(parent_text, ["Closing", "Deadline", "Apply by"])
                    department = extract_field(parent_text, ["Department", "Team", "Division"])

                    jobs.append({
                        "jobId":       job_id,
                        "title":       title,
                        "department":  department,
                        "location":    location,
                        "salary":      salary,
                        "hours":       hours,
                        "closingDate": closing,
                        "url":         full_url,
                        "rawText":     parent_text[:500] if parent_text else title,
                    })
                    print(f"  ✓ {job_id}: {title[:60]}")

                except Exception as e:
                    print(f"  ✗ Error: {e}")

        finally:
            browser.close()

    return jobs


def parse_api_item(item):
    """Parse a job from API response JSON."""
    if not isinstance(item, dict):
        return None

    # Try different field name patterns
    job_id = (item.get("Id") or item.get("id") or item.get("JobId") or
              item.get("jobId") or item.get("VacancyId") or "")
    title = (item.get("Title") or item.get("title") or item.get("JobTitle") or
             item.get("Name") or item.get("PositionTitle") or "")

    if not title or not job_id:
        return None

    title = re.sub(r'^(NEW|New|new)\s+', '', str(title)).strip()

    return {
        "jobId":       str(job_id),
        "title":       title,
        "department":  str(item.get("Department") or item.get("department") or ""),
        "location":    str(item.get("Location") or item.get("location") or ""),
        "salary":      str(item.get("Salary") or item.get("salary") or ""),
        "hours":       str(item.get("Hours") or item.get("EmploymentType") or
                          item.get("hours") or item.get("type") or ""),
        "closingDate": str(item.get("ClosingDate") or item.get("closingDate") or
                          item.get("Closing") or ""),
        "url":         f"https://www.jobtrain.co.uk/iomgovjobs/Job/JobDetail?jobid={job_id}",
        "rawText":     "",
    }


def extract_field(text, labels):
    """Extract a labelled field from text."""
    for label in labels:
        # Match "Label: value" up to next double-space, pipe, period or another label
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


def main():
    os.makedirs("docs", exist_ok=True)

    try:
        print("Starting gov jobs scrape...")
        jobs = scrape()

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

        print(f"\n✓ SUCCESS — {len(jobs)} gov jobs scraped")

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
