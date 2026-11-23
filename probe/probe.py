import os, subprocess, json, re, requests
OUT = "probe/out/prop4"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "ManxOneBot/1.0 (+https://manxone.hammerlabs.app)"}
for k, u in {
  "rent_plain": "https://www.garforthgray.im/assets/inc/ajax.php?submitform=1&order=latest&keyword=&ajaxGetRentalsResults=1",
  "rent_excl": "https://www.garforthgray.im/assets/inc/ajax.php?submitform=1&order=latest&page=1&keyword=&ajaxGetRentalsResults=1&excludeRented=1",
}.items():
    r = requests.get(u, headers=UA, timeout=30)
    open(f"{OUT}/{k}.txt", "w").write(re.sub(r"[A-Za-z0-9_\-]{32,}", "[x]", r.text[:200000]))
env = dict(os.environ, PROPERTY_AGENTS="cg,gg", OUTPUT_PATH=os.path.abspath(f"{OUT}/out.json"))
p = subprocess.run(["python", "run.py"], cwd="scripts/property", env=env, capture_output=True, text=True, timeout=3000)
open(f"{OUT}/log.txt", "w").write(p.stdout[-30000:] + "\n---STDERR---\n" + p.stderr[-8000:])
