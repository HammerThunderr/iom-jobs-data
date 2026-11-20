import requests, pathlib
out = pathlib.Path("probe/out"); out.mkdir(parents=True, exist_ok=True)
for name, u in {"pharm": "https://www.gov.im/categories/health-and-wellbeing/pharmacy-services/community-pharmacies/"}.items():
    r = requests.get(u, headers={"User-Agent": "ManxOneBot/1.0 (+https://manxone.hammerlabs.app)"}, timeout=30)
    (out / f"{name}.html").write_bytes(r.content)
    (out / f"{name}.status").write_text(str(r.status_code))
