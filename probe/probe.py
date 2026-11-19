import json, requests, pathlib
out = pathlib.Path("probe/out"); out.mkdir(parents=True, exist_ok=True)
CW = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
log = {}
urls = set()
for pat in ["gov.im/categories/travel-traffic-and-motoring/harbours/tides-and-flapgates/*", "gov.im/*tide*"]:
    try:
        r = requests.get("https://web.archive.org/cdx/search/cdx", params={"url": pat, "output": "json", "collapse": "urlkey", "limit": "400", "filter": "statuscode:200"}, timeout=90)
        rows = r.json()[1:] if r.text.strip() else []
        for x in rows: urls.add(x[2].split("?")[0])
    except Exception as e:
        log["cdx_err_" + pat] = str(e)
log["urls"] = sorted(urls)[:80]
tests = [u for u in sorted(urls) if "tide" in u.lower() and not u.lower().endswith(".pdf")][:12]
tests += ["https://www.gov.im/weather/RssCurrentForecast"]
for u in tests:
    if not u.startswith("http"): u = "https://" + u
    try:
        r = requests.get(u, headers={"User-Agent": CW}, timeout=25)
        log[u] = {"status": r.status_code, "len": len(r.content), "challenge": "Just a moment" in r.text, "tideTable": "tideTable" in r.text}
    except Exception as e:
        log[u] = str(e)
(out / "tides2.json").write_text(json.dumps(log, indent=1))
