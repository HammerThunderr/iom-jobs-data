"""
IOM Government Jobs Scraper (JobTrain) — Playwright Version
------------------------------------------------------------
The site is JS-rendered, so requests + BeautifulSoup won't work.
Uses Playwright to wait for the JS to load all jobs.

Saves to docs/gov_jobs.json on GitHub Pages.
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

LIST_URL = "https://www.jobtrain.co.uk/iomgovjobs/Home/Job"


def scrape():
    """Use Playwright to scrape the JS-rendered jobs page."""
    jobs = []

    with sync_playwright() as p:
        print("Launching browser...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        try:
            print(f"Navigating to {LIST_URL}...")
            page.goto(LIST_URL, wait_until="networkidle", timeout=45000)

            # Wait extra for JS to populate
            page.wait_for_timeout(3000)

            # Try clicking "Load more" / "Show all" if it exists
            for _ in range(20):
                try:
                    # Look for common "load more" patterns
                    load_more = page.query_selector('button:has-text("Load more")') or \
                                page.query_selector('button:has-text("Show more")') or \
                                page.query_selector('a:has-text("Next")') or \
                                page.query_selector('.load-more')
                    if load_more and load_more.is_visible():
                        load_more.click()
                        page.wait_for_timeout(1500)
                    else:
                        break
                except Exception:
                    break

            # Get the full HTML after JS has rendered
            html = page.content()
            print(f"Page loaded ({len(html)} bytes)")

            # Try multiple selector patterns
            selectors = [
                ".job-list-item",
                ".vacancy-list-item",
                "[class*='job-item']",
                "[class*='vacancy']",
                "article",
                "li.list-group-item",
                ".job-card",
            ]

            cards = []
            for sel in selectors:
                cards = page.query_selector_all(sel)
                if cards and len(cards) > 1:
                    print(f"Found {len(cards)} items with selector: {sel}")
                    break

            if not cards:
                # Fallback: look for any links to JobDetail
                print("No cards found, looking for JobDetail links...")
                links = page.query_selector_all('a[href*="JobDetail"]')
                print(f"Found {len(links)} JobDetail links")

                for link in links:
                    try:
                        href = link.get_attribute("href") or ""
                        title = link.text_content().strip()

                        if not href or not title or len(title) < 3:
                            continue

                        # Build full URL
                        if href.startswith("/"):
                            full_url = "https://www.jobtrain.co.uk" + href
                        elif href.startswith("http"):
                            full_url = href
                        else:
                            full_url = "https://www.jobtrain.co.uk/iomgovjobs/" + href

                        # Extract job ID
                        id_match = re.search(r'jobid=(\d+)', full_url, re.IGNORECASE)
                        job_id = id_match.group(1) if id_match else ""

                        # Get parent container for more context
                        parent_text = ""
                        try:
                            parent = link.evaluate("el => el.closest('article, li, div.job-item, [class*=card]')?.innerText || ''")
                            parent_text = parent if isinstance(parent, str) else ""
                        except Exception:
                            pass

                        # Strip "NEW" badge
                        title_clean = re.sub(r'^(NEW|New)\s+', '', title).strip()

                        if job_id and title_clean:
                            jobs.append({
                                "jobId":       job_id,
                                "title":       title_clean,
                                "department":  "",
                                "location":    "",
                                "salary":      "",
                                "hours":       "",
                                "closingDate": "",
                                "url":         full_url,
                                "rawText":     parent_text[:500] if parent_text else title_clean,
                            })
                            print(f"  ✓ {title_clean}")
                    except Exception as e:
                        print(f"  ✗ Link parse error: {e}")
            else:
                # Process found cards
                for card in cards:
                    try:
                        # Title
                        title_el = card.query_selector("h2, h3, h4, .title, [class*='title']")
                        title = title_el.text_content().strip() if title_el else ""
                        title = re.sub(r'^(NEW|New)\s+', '', title).strip()

                        # URL
                        link = card.query_selector('a[href*="JobDetail"]') or card.query_selector("a")
                        href = link.get_attribute("href") if link else ""
                        full_url = ""
                        job_id = ""
                        if href:
                            if href.startswith("/"):
                                full_url = "https://www.jobtrain.co.uk" + href
                            elif href.startswith("http"):
                                full_url = href
                            else:
                                full_url = "https://www.jobtrain.co.uk/iomgovjobs/" + href
                            id_match = re.search(r'jobid=(\d+)', full_url, re.IGNORECASE)
                            if id_match:
                                job_id = id_match.group(1)

                        # Other fields — extract from text content
                        full_text = card.text_content()
                        full_text = re.sub(r'\s+', ' ', full_text).strip()

                        location = ""
                        salary   = ""
                        hours    = ""
                        closing  = ""

                        # Try to find labelled fields
                        loc_m   = re.search(r'(?:Location|Where)[:\s]+([^|\n]+?)(?:\s{2,}|\||$)', full_text, re.IGNORECASE)
                        sal_m   = re.search(r'(?:Salary)[:\s]+([^|\n]+?)(?:\s{2,}|\||$)', full_text, re.IGNORECASE)
                        hour_m  = re.search(r'(?:Hours)[:\s]+([^|\n]+?)(?:\s{2,}|\||$)', full_text, re.IGNORECASE)
                        close_m = re.search(r'(?:Closing\s+Date)[:\s]+([^|\n]+?)(?:\s{2,}|\||$)', full_text, re.IGNORECASE)

                        if loc_m:   location = loc_m.group(1).strip()[:100]
                        if sal_m:   salary   = sal_m.group(1).strip()[:150]
                        if hour_m:  hours    = hour_m.group(1).strip()[:80]
                        if close_m: closing  = close_m.group(1).strip()[:80]

                        if title and job_id:
                            jobs.append({
                                "jobId":       job_id,
                                "title":       title,
                                "department":  "",
                                "location":    location,
                                "salary":      salary,
                                "hours":       hours,
                                "closingDate": closing,
                                "url":         full_url,
                                "rawText":     full_text[:500],
                            })
                            print(f"  ✓ {title}")
                    except Exception as e:
                        print(f"  ✗ Card parse error: {e}")

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
                print("Keeping existing data")
                return

        data = {
            "success":    True if jobs else False,
            "fetchedAt":  datetime.now(timezone.utc).isoformat(),
            "lastUpdated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "totalCount": len(jobs),
            "jobs":       jobs,
            "source":     "jobtrain.co.uk/iomgovjobs",
        }

        print(f"\n✓ SUCCESS — {len(jobs)} gov jobs scraped")

    except Exception as e:
        print(f"\n✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        data = {
            "success":    False,
            "error":      str(e)[:200],
            "fetchedAt":  datetime.now(timezone.utc).isoformat(),
            "jobs":       [],
        }

    with open("docs/gov_jobs.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("✓ Saved docs/gov_jobs.json")


if __name__ == "__main__":
    main()
