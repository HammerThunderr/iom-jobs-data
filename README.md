# iom-jobs-data

Auto-scrapes Isle of Man job listings every 4 hours and serves them as a free, fast JSON API via GitHub Pages.

---

## Setup (5 minutes)

### Step 1 — Create the GitHub repo

1. Go to [github.com](https://github.com) and create a **new public repo** called `iom-jobs-data`
2. Upload all files from this folder into it (or push via git)

### Step 2 — Enable GitHub Pages

1. Go to your repo → **Settings** → **Pages**
2. Under *Source*, select **Deploy from a branch**
3. Branch: `main`, Folder: `/docs`
4. Click **Save**

Your JSON will be live at:
```
https://YOUR_USERNAME.github.io/iom-jobs-data/jobs.json
```

### Step 3 — Run the first scrape

1. Go to your repo → **Actions** tab
2. Click **Scrape IOM Jobs** → **Run workflow** → **Run workflow**
3. Wait ~30 seconds — it will scrape and commit `jobs.json`

After that it runs **automatically every 4 hours**.

### Step 4 — Update the Android app

In `JobScraper.java`, replace:
```java
private static final String GITHUB_USERNAME = "YOUR_GITHUB_USERNAME";
```
with your actual GitHub username.

---

## How it works

```
GitHub Actions (every 4 hours)
    → runs scraper.py
    → fetches services.gov.im
    → parses HTML with BeautifulSoup
    → saves docs/jobs.json
    → commits & pushes to repo

Android App
    → fetches jobs.json from GitHub Pages CDN
    → fast, cached, no server needed
    → shows "last updated" time in UI
```

## Why this beats Render.com

| | Render (free) | GitHub Pages |
|---|---|---|
| Cost | Free (but slow cold start) | **Completely free** |
| Speed | 30–60s cold start | **~200ms (CDN)** |
| Updates | Real-time (but slow) | **Every 4 hours** |
| Reliability | Sleeps after inactivity | **Always on** |
| Setup | Deploy a server | **Just push files** |

## Files

```
iom-jobs-data/
├── .github/workflows/scrape.yml  ← GitHub Action (runs every 4 hours)
├── scraper.py                    ← Scrapes services.gov.im → docs/jobs.json
├── requirements.txt              ← Python deps (requests, beautifulsoup4)
└── docs/
    ├── index.html                ← Status page at your GitHub Pages URL
    └── jobs.json                 ← The actual data (auto-updated)
```

## JSON format

```json
{
  "success": true,
  "total": 245,
  "lastUpdated": "2026-03-15T08:00:00Z",
  "lastUpdatedHuman": "15 Mar 2026 at 08:00 UTC",
  "nextUpdate": "Every 4 hours",
  "source": "services.gov.im",
  "jobs": [
    {
      "jobId": "218478",
      "title": "Hair Stylist",
      "employer": "Port Hair Inn",
      "hours": "Various (Flexible)",
      "category": "Beauty",
      "url": "https://services.gov.im/job-search/viewjob?Id=218478"
    }
  ]
}
```
