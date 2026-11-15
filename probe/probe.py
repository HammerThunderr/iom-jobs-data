import json, requests, pathlib
out = pathlib.Path("probe/out"); out.mkdir(parents=True, exist_ok=True)
U = "https://images.gov.im/webcams/PortErin.jpg"
CH = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1"
CW = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
log = {}
for name, h in {
    "iphone_app_referer": {"User-Agent": CH, "Referer": "https://manxone.hammerlabs.app/", "Accept": "image/*"},
    "chrome_app_referer": {"User-Agent": CW, "Referer": "https://manxone.hammerlabs.app/", "Sec-Fetch-Dest": "image", "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"},
    "chrome_no_referer": {"User-Agent": CW, "Accept": "image/*"},
    "chrome_other_referer": {"User-Agent": CW, "Referer": "https://example.com/"},
}.items():
    try:
        r = requests.get(U, headers=h, timeout=20)
        log[name] = {"status": r.status_code, "type": r.headers.get("content-type"), "len": len(r.content), "jpeg": r.content[:3] == b"\xff\xd8\xff"}
    except Exception as e:
        log[name] = str(e)
(out / "cam2.json").write_text(json.dumps(log, indent=1))
