import json, requests, pathlib
out = pathlib.Path("probe/out"); out.mkdir(parents=True, exist_ok=True)
U = "https://images.gov.im/webcams/PortErin.jpg"
log = {}
for name, h in {
    "plain": {"User-Agent": "ManxOneBot/1.0 (+https://manxone.hammerlabs.app)"},
    "app_referer": {"User-Agent": "Mozilla/5.0", "Referer": "https://manxone.hammerlabs.app/", "Origin": "https://manxone.hammerlabs.app"},
    "no_ua": {},
}.items():
    try:
        r = requests.get(U, headers=h, timeout=20)
        log[name] = {"status": r.status_code, "type": r.headers.get("content-type"), "len": len(r.content),
                     "jpeg": r.content[:3] == b"\xff\xd8\xff",
                     "headers": {k: v for k, v in r.headers.items() if k.lower() in ("access-control-allow-origin","cache-control","last-modified","expires","etag","server","age","x-cache")}}
    except Exception as e:
        log[name] = str(e)
(out / "cam.json").write_text(json.dumps(log, indent=1))
