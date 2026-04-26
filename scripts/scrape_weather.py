"""
Weather RSS Scraper
-------------------
Run by GitHub Actions every 30 minutes.
Saves clean JSON to docs/ folder (GitHub Pages).

Place at: scripts/scrape_weather.py in your iom-jobs-data repo.
"""

import requests
import json
import re
import os
from datetime import datetime, timezone

FEEDS = {
    "weather_current.json":  "https://www.gov.im/weather/RssCurrentForecast",
    "weather_shipping.json": "https://www.gov.im/weather/current-shipping-forecast/RssCurrentShippingForecast",
    "weather_5day.json":     "https://www.gov.im/weather/5-day-forecast/Rss5DayForecast",
    "weather_coastal.json":  "https://www.gov.im/weather/5-day-coastal-forecast/Rss5DayShippingForecast",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def clean_html(s):
    """
    Convert HTML to clean text with ##Section## markers.
    Keeps structure (headings, paragraphs, lists) but no raw HTML.
    """
    if not s:
        return ""

    # Strip CDATA
    s = re.sub(r'<!\[CDATA\[', '', s, flags=re.IGNORECASE)
    s = s.replace(']]>', '')

    # Decode HTML entities FIRST (so &lt;h2&gt; becomes <h2>)
    s = (s.replace('&amp;',   '&')
          .replace('&lt;',    '<')
          .replace('&gt;',    '>')
          .replace('&quot;',  '"')
          .replace('&apos;',  "'")
          .replace('&#39;',   "'")
          .replace('&nbsp;',  ' ')
          .replace('&deg;',   '°')
          .replace('&mdash;', '—')
          .replace('&ndash;', '–'))

    # Headings → "##Section##"
    s = re.sub(
        r'<h[1-6][^>]*>(.*?)</h[1-6]>',
        lambda m: f'\n##{m.group(1).strip()}##\n',
        s,
        flags=re.DOTALL | re.IGNORECASE
    )

    # Paragraphs
    s = re.sub(
        r'<p[^>]*>(.*?)</p>',
        lambda m: f'{m.group(1).strip()}\n\n',
        s,
        flags=re.DOTALL | re.IGNORECASE
    )

    # List items
    s = re.sub(
        r'<li[^>]*>(.*?)</li>',
        lambda m: f'• {m.group(1).strip()}\n',
        s,
        flags=re.DOTALL | re.IGNORECASE
    )

    # Line breaks
    s = re.sub(r'<br\s*/?>', '\n', s, flags=re.IGNORECASE)

    # Strip ALL remaining tags
    s = re.sub(r'<[^>]+>', '', s)

    # Clean whitespace
    s = s.replace('\r', '')
    s = re.sub(r'\n{3,}', '\n\n', s)
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r' *\n *', '\n', s)
    return s.strip()


def extract(xml, tag):
    m = re.search(f'<{tag}[^>]*>(.*?)</{tag}>', xml, re.DOTALL)
    return m.group(1).strip() if m else ''


def parse_rss(text):
    items = []
    feed_title = ''
    last_updated = ''

    before_items = text.split('<item>')[0]
    m = re.search(r'<title[^>]*>(.*?)</title>', before_items, re.DOTALL)
    if m:
        feed_title = clean_html(m.group(1))

    m = re.search(r'<lastBuildDate[^>]*>(.*?)</lastBuildDate>', text)
    if m:
        last_updated = format_date(m.group(1).strip())

    for item_match in re.finditer(r'<item>(.*?)</item>', text, re.DOTALL):
        block = item_match.group(1)
        title = clean_html(extract(block, 'title'))
        desc  = clean_html(extract(block, 'description'))
        pub   = format_date(extract(block, 'pubDate').strip())
        link  = extract(block, 'link').strip()
        if title or desc:
            items.append({
                'title': title,
                'description': desc,
                'pubDate': pub,
                'link': link,
            })

    return {
        'success':     True,
        'feedTitle':   feed_title,
        'lastUpdated': last_updated,
        'fetchedAt':   datetime.now(timezone.utc).isoformat(),
        'items':       items,
    }


def format_date(raw):
    """Format 'Mon, 15 Mar 2026 09:00:00 +0000' → 'Mon 15 Mar 2026, 09:00'"""
    if not raw:
        return ''
    try:
        parts = raw.split()
        if len(parts) >= 5:
            return f"{parts[0].rstrip(',')} {parts[1]} {parts[2]} {parts[3]}, {parts[4][:5]}"
    except Exception:
        pass
    return raw


def main():
    os.makedirs('docs', exist_ok=True)

    for filename, url in FEEDS.items():
        print(f"Fetching {url}...")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            data = parse_rss(resp.text)
            path = os.path.join('docs', filename)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"  ✓ Saved {len(data['items'])} items to {path}")
        except Exception as e:
            print(f"  ✗ Error: {e}")
            error_data = {'success': False, 'error': str(e), 'items': []}
            with open(os.path.join('docs', filename), 'w') as f:
                json.dump(error_data, f)


if __name__ == '__main__':
    main()
