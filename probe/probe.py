import requests, pathlib
out = pathlib.Path("probe/out"); out.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
r = requests.get("https://www.steam-packet.com/sailing-status", headers={"User-Agent": UA}, timeout=30)
(out / "sp.html").write_bytes(r.content); (out / "sp.status").write_text(str(r.status_code))
w = requests.get("https://manxone-sailings.hammerpunch786.workers.dev", timeout=30)
(out / "worker.json").write_bytes(w.content)
