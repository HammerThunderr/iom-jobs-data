"""
IOM Government Jobs Scraper (JobTrain) — Playwright Version
------------------------------------------------------------
Site is JS-rendered. Uses Playwright + flexible parsing.
Saves to docs/gov_jobs.json on GitHub Pages.
"""

import json
import os
import re
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

LIST_URL = "https://www.jobtrain.co.uk/iomgovjobs/Home/Job"


def extract_job_from_card(card):
    """Extract job data from a single card element. Returns dict or None."""
    # Get full text and inner HTML for fallback parsing
    full_text = (card.text_content() or "").strip()
    full_text = re.sub(r'\s+', ' ', full_text)

    # Look for ANY link inside the card — could be h3 > a, button, etc.
    links = card.query_selector_all("a")

    href = ""
    title = ""
    job_id = ""

    for link in links:
        link_href = link.get_attribute("href") or ""
        # We want links that go to job details
        if "JobDetail" in link_href or "jobid=" in link_href.lower():
            href = link_href
            link_text = (link.text_content() or "").strip()
            link_text = re.sub(r'\s+', ' ', link_text)
            link_text = re.sub(r'^(NEW|New|new)\s+', '', link_text).strip()
            if link_text and len(link_text) > 2:
                title = link_text
            break

    # If no JobDetail link, take first non-empty link
    if not title and links:
        for link in links:
            link_text = (link.text_content() or "").strip()
            link_text = re.sub(r'\s+', ' ', link_text)
            link_text = re.sub(r'^(NEW|New|new)\s+', '', link_text).strip()
            if link_text and len(link_text) > 2 and not link_text.lower() in ("apply", "view", "more", "details"):
                title = link_text
                href = link.get_attribute("href") or ""
                break

    # Build absolute URL
    full_url = ""
    if href:
        if href.startswith("/"):
            full_url = "https://www.jobtrain.co.uk" + href
        elif href.startswith("http"):
            full_url = href
        else:
            full_url = "https://www.jobtrain.co.uk/iomgovjobs/" + href.lstrip("./")

        # Extract job ID
        id_match = re.search(r'jobid=(\d+)', full_url, re.IGNORECASE)
        if id_match:
            job_id = id_match.group(1)

    # Try heading element if title still empty
    if not title:
        for tag in ["h2", "h3", "h4", "h5"]:
            h = card.query_selector(tag)
            if h:
                t = (h.text_content() or "").strip()
                t = re.sub(r'\s+', ' ', t)
                t = re.sub(r'^(NEW|New|new)\s+', '', t).strip()
                if t:
                    title = t
                    break

    # Last resort: first line of text
    if not title and full_text:
        first_line = full_text.split('.')[0]
        if len(first_line) > 5 and len(first_line) < 200:
            title = re.sub(r'^(NEW|New|new)\s+', '', first_line).strip()

    if not title:
        return None

    # Extract fields from text using flexible patterns
    location = ""
    salary   = ""
    hours    = ""
    closing  = ""
    department = ""

    patterns = [
        ("location",   r'(?:Location|Where|Based\s+in)[:\s]+([^|.]+?)(?:\s{2,}|\||$|\s(?:Salary|Hours|Closing|Department))'),
        ("salary",     r'(?:Salary|Pay|Wage)[:\s]+([£$€]?[\d,]+[^|.]*?)(?:\s{2,}|\||$|\s(?:Location|Hours|Closing|Department))'),
        ("hours",      r'(?:Hours|Type|Working\s+Hours)[:\s]+([^|.]+?)(?:\s{2,}|\||$|\s(?:Location|Salary|Closing|Department))'),
        ("closing",    r'(?:Closing\s+Date|Deadline|Apply\s+by)[:\s]+([^|.]+?)(?:\s{2,}|\||$|\s(?:Location|Salary|Hours|Department))'),
        ("department", r'(?:Department|Team|Division)[:\s]+([^|.]+?)(?:\s{2,}|\||$|\s(?:Location|Salary|Hours|Closing))'),
    ]

    for key, pattern in patterns:
        m = re.search(pattern, full_text, re.IGNORECASE)
        if m:
            value = m.group(1).strip()[:120]
            if key == "location": location = value
            elif key == "salary": salary = value
            elif key == "hours": hours = value
            elif key == "closing": closing = value
            elif key == "department": department = value

    return {
        "jobId":       job_id,
        "title":       title,
        "department":  department,
        "location":    location,
        "salary":      salary,
        "hours":       hours,
        "closingDate": closing,
        "url":         full_url,
        "rawText":     full_text[:500],
    }


def scrape():
    """Main scrape function using Playwright."""
    jobs = []

    with sync_playwright() as p:
        print("Launching browser...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 1024},
        )
        page = context.new_page()

        try:
            print(f"Navigating to {LIST_URL}...")
            page.goto(LIST_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(3000)

            # Try to load all jobs by scrolling and clicking "Load more"
            for i in range(30):
                try:
                    # Click any "Load more" / "Show all" / "View more" buttons
                    selectors_to_click = [
                        'button:has-text("Load more")',
                        'button:has-text("Show more")',
                        'button:has-text("View more")',
                        'a:has-text("Next")',
                        'button:has-text("Show all")',
                        '.load-more',
                        '[aria-label*="more" i]',
                    ]
                    clicked = False
                    for sel in selectors_to_click:
                        elem = page.query_selector(sel)
                        if elem and elem.is_visible():
                            elem.click()
                            page.wait_for_timeout(1500)
                            clicked = True
                            break
                    if not clicked:
                        # Scroll to bottom to trigger lazy load
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(800)
                        break
                except Exception:
                    break

            # Find job cards using the selector that worked before
            cards = page.query_selector_all(".job-card")
            print(f"Found {len(cards)} cards with .job-card")

            if not cards:
                cards = page.query_selector_all(".job-list-item, .vacancy-item, [class*='job'][class*='card'], [class*='vacancy']")
                print(f"Fallback found {len(cards)} cards")

            if not cards:
                # Diagnostic: dump first 500 chars of page so we can see structure
                html = page.content()
                print("\n=== HTML snippet for diagnosis ===")
                # Try to find any element that looks like a job
                for keyword in ["jobid", "JobDetail", "vacancy", "job-card"]:
                    idx = html.lower().find(keyword.lower())
                    if idx > -1:
                        print(f"Found '{keyword}' at offset {idx}:")
                        print(html[max(0,idx-100):idx+400])
                        print("---")
                        break

            # Parse each card
            seen_ids = set()
            for i, card in enumerate(cards):
                job = extract_job_from_card(card)
                if job and job["title"]:
                    # Dedupe by jobId
                    if job["jobId"] and job["jobId"] in seen_ids:
                        continue
                    if job["jobId"]:
                        seen_ids.add(job["jobId"])
                    jobs.append(job)
                    print(f"  ✓ [{i+1}] {job['title']}")
                else:
                    # Debug: show what we got
                    text_preview = (card.text_content() or "").strip()[:100]
                    print(f"  ✗ [{i+1}] Could not parse — text: {text_preview!r}")

        finally:
            browser.close()

    return jobs


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
