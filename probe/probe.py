import json, requests, pathlib
out = pathlib.Path("probe/out"); out.mkdir(parents=True, exist_ok=True)
CW = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
log = {}
for name, u in {
  "tides_index": "https://www.gov.im/categories/travel-traffic-and-motoring/harbours/tides-and-flapgates/",
  "bank_hol": "https://www.gov.im/about-the-government/departments/cabinet-office/bank-holidays/",
}.items():
    try:
        r = requests.get(u, headers={"User-Agent": CW, "Referer": "https://www.gov.im/"}, timeout=25)
        log[name] = {"status": r.status_code, "len": len(r.content), "rejected": "Request Rejected" in r.text, "challenge": "Just a moment" in r.text}
    except Exception as e:
        log[name] = str(e)
(out / "tides.json").write_text(json.dumps(log, indent=1))
