"""
Weather RSS Scraper
-------------------
Run by GitHub Actions every 30 minutes.
Fetches IOM gov.im RSS feeds and saves as JSON to docs/ folder (GitHub Pages).

Add this file to your iom-jobs-data repo at:
  scripts/scrape_weather.py
"""

import requests
import json
import re
import os
from datetime import datetime, timezone

FEEDS = {
    "weather_current.json": "https://www.gov.im/weather/RssCurrentForecast",
    "weather_shipping.json": "https://www.gov.im/weather/current-shipping-forecast/RssCurrentShippingForecast",
    "weather_5day.json": "https://www.gov.im/weather/5-day-forecast/Rss5DayForecast",
    "weather_coastal.json": "https://www.gov.im/weather/5-day-coastal-forecast/Rss5DayShippingForecast",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

def clean(s):
    s = re.sub(r'<!\[CDATA\[', '', s, flags=re.IGNORECASE)
    s = s.replace(']]>', '')
    s = re.sub(r'<[^>]+>', '', s)
    s = s.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    s = s.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
    s = s.replace('&deg;', '°')
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
        feed_title = clean(m.group(1))

    m = re.search(r'<lastBuildDate[^>]*>(.*?)</lastBuildDate>', text)
    if m:
        last_updated = m.group(1).strip()

    for item_match in re.finditer(r'<item>(.*?)</item>', text, re.DOTALL):
        block = item_match.group(1)
        title = clean(extract(block, 'title'))
        desc  = clean(extract(block, 'description'))
        pub   = extract(block, 'pubDate').strip()
        link  = extract(block, 'link').strip()
        if title or desc:
            items.append({
                'title': title,
                'description': desc,
                'pubDate': pub,
                'link': link,
            })

    return {
        'success': True,
        'feedTitle': feed_title,
        'lastUpdated': last_updated,
        'fetchedAt': datetime.now(timezone.utc).isoformat(),
        'items': items,
    }

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

    # Also scrape webcam — save list of working webcam URLs
    webcam_data = {
        'webcams': [
            {'name': 'Bungalow (A18 North)',    'url': 'https://images.gov.im/webcams/bungalow3.jpg'},
            {'name': 'Bungalow (A18 South)',    'url': 'https://images.gov.im/webcams/bungalow1.jpg'},
            {'name': 'Bungalow (Laxey Valley)', 'url': 'https://images.gov.im/webcams/bungalow2.jpg'},
            {'name': 'Douglas Marina',          'url': 'https://images.gov.im/webcams/douglas_00001.jpg'},
            {'name': 'Douglas Promenade',       'url': 'https://images.gov.im/webcams/DTL_00001.jpg'},
            {'name': 'Peel Breakwater',         'url': 'https://images.gov.im/webcams/peel_00001.jpg'},
            {'name': 'Port Erin Bay',           'url': 'https://images.gov.im/webcams/PortErin.jpg'},
            {'name': 'Douglas Outer Harbour',   'url': 'https://images.gov.im/webcams/ed_tower.jpg'},
            {'name': 'Ramsey',                  'url': 'https://images.gov.im/webcams/Ramsey_00001.jpg'},
            {'name': 'Castletown Bay',          'url': 'https://images.gov.im/webcams/Castletown_Bay.jpg'},
        ]
    }
    with open('docs/webcams.json', 'w') as f:
        json.dump(webcam_data, f, indent=2)
    print("✓ Saved webcams.json")

if __name__ == '__main__':
    main()
