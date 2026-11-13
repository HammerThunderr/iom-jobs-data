import re, json, requests, pathlib, urllib.parse
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
H = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8", "Accept-Language": "en-GB,en;q=0.9"}
out = pathlib.Path("probe/out"); out.mkdir(parents=True, exist_ok=True)
log = {}
pages = {
 "upcoming": "https://www.gov.im/about-the-government/departments/infrastructure/highway-services/upcoming-roadworks-and-events-on-roads/",
 "roadwatch": "https://www.gov.im/roadwatch",
 "highways": "https://www.gov.im/about-the-government/departments/infrastructure/highway-services/",
 "news": "https://www.gov.im/news/?page=1",
}
for k, u in pages.items():
    try:
        r = requests.get(u, headers=H, timeout=30, allow_redirects=True)
        log[k] = [r.status_code, r.url, len(r.content), r.headers.get("content-type")]
        (out / f"{k}.html").write_bytes(r.content)
    except Exception as e:
        log[k] = str(e)
html = (out / "upcoming.html").read_text(errors="ignore") if (out / "upcoming.html").exists() else ""
links = sorted(set(re.findall(r'href="([^"]+\.pdf[^"]*)"', html, re.I)))
log["pdf_links"] = links
for l in links[:6]:
    u = urllib.parse.urljoin(pages["upcoming"], l)
    try:
        r = requests.get(u, headers=H, timeout=60)
        name = re.sub(r"[^a-z0-9.-]", "_", u.rsplit("/", 1)[-1].lower())[:80]
        (out / name).write_bytes(r.content)
        log[name] = [r.status_code, len(r.content), r.headers.get("content-type")]
    except Exception as e:
        log[u] = str(e)
# one.network public map check (not used unless allowed)
(out / "log.json").write_text(json.dumps(log, indent=1))
print(json.dumps(log, indent=1))
