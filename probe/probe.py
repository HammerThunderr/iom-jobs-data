import requests, pathlib
out = pathlib.Path("probe/out"); out.mkdir(parents=True, exist_ok=True)
r = requests.get("https://desc.gov.im/media/mjbffqyc/school-holidays-and-term-dates-2025-2028.pdf", headers={"User-Agent": "ManxOneBot/1.0 (+https://manxone.hammerlabs.app)"}, timeout=60)
(out / "terms.pdf").write_bytes(r.content); (out / "terms.status").write_text(f"{r.status_code} {r.headers.get('content-type')} {len(r.content)}")
