import json, requests, pathlib
UA = "ManxOneBot/1.0 (+https://manxone.hammerlabs.app)"
out = pathlib.Path("probe/out"); out.mkdir(parents=True, exist_ok=True)
log = {}
urls = {
 "pdf2024": "https://www.gov.im/media/1384484/iom-upcoming-ttrns-6-july-19-july-2024.pdf",
 "pdf2025": "https://www.gov.im/media/1385989/iom-upcoming-ttrns-4-january-2025-17-january-2025.pdf",
 "robots": "https://www.gov.im/robots.txt",
 "rss": "https://www.gov.im/news/rss/",
 "rss2": "https://www.gov.im/rss/news/",
 "nogov": "https://gov.im/roadwatch",
}
for k, u in urls.items():
    try:
        r = requests.get(u, headers={"User-Agent": UA}, timeout=30, allow_redirects=False)
        log[k] = [r.status_code, r.headers.get("location"), len(r.content), r.headers.get("content-type"), r.headers.get("server"), r.headers.get("cf-mitigated")]
        (out / f"p2_{k}.bin").write_bytes(r.content[:200000])
    except Exception as e:
        log[k] = str(e)
(out / "log2.json").write_text(json.dumps(log, indent=1))
