import os, subprocess, pathlib
out = pathlib.Path("probe/out"); out.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, PROPERTY_AGENTS="bgc,grays,pre", OUTPUT_PATH="probe/out/prop_test2.json")
r = subprocess.run(["python", "probe/property/run.py"], env=env, capture_output=True, text=True, timeout=3000)
lines = [l for l in r.stdout.splitlines() if not l.strip().startswith("[")]
(out / "prop_test2.log").write_text("\n".join(lines)[-20000:] + "\n---STDERR---\n" + r.stderr[-5000:])
