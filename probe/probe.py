import os, subprocess, json, collections
os.makedirs("probe/out", exist_ok=True)
out = os.path.abspath("probe/out/prop6.json")
env = dict(os.environ, PROPERTY_AGENTS="gg,chp", OUTPUT_PATH=out)
r = subprocess.run(["python", "run.py"], cwd="scripts/property", env=env, capture_output=True, text=True)
log = r.stdout[-6000:] + "\n" + r.stderr[-4000:]
d = json.load(open(out))
c = collections.Counter((l["agent"], l["category"], l["listingType"], l.get("status")) for l in d["listings"])
lines = [f"{k}: {v}" for k, v in sorted(c.items(), key=str)]
for l in [x for x in d["listings"] if x["agent"] == "Chapman"][:60]:
    lines.append(json.dumps({k: l.get(k) for k in ("address", "locality", "listingType", "price", "priceQualifier", "priceNote", "status", "category")}, ensure_ascii=False))
open("probe/out/prop6_summary.txt", "w").write(log + "\n" + "\n".join(lines))
