"""Seeds the next N cities from queue.json: streams each city's Overture places through overture.py, writes
data/<cc>_<name>.jsonl and data/index.json ({cityId: {"n": rows, "updated": day}}). Skips cities already in the index.
usage: python3 -I places/seed.py 40"""
import json
import math
import os
import subprocess
import sys
import time

N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
HERE = os.path.dirname(os.path.abspath(__file__))
queue = json.load(open(os.path.join(HERE, "queue.json")))
idx_path = os.path.join(HERE, "data", "index.json")
index = json.load(open(idx_path)) if os.path.exists(idx_path) else {}
todo = [c for c in queue if c["id"] not in index][:N]
print(f"{len(index)} done, {len(todo)} this run, {len(queue) - len(index)} left", flush=True)
for c in todo:
    pop = c.get("population") or 0
    r = 0.10 if pop < 1_000_000 else 0.16 if pop < 5_000_000 else 0.24
    k = r / max(0.2, math.cos(math.radians(c["lat"])))
    bbox = f"{c['lng'] - k:.3f},{c['lat'] - r:.3f},{c['lng'] + k:.3f},{c['lat'] + r:.3f}"
    out = os.path.join(HERE, "data", c["id"].replace("/", "_", 1) + ".jsonl")
    t0 = time.time()
    dl = subprocess.Popen(["overturemaps", "download", f"--bbox={bbox}", "-f", "geojsonseq", "--type=place"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    with open(out + ".tmp", "w") as f:
        flt = subprocess.run([sys.executable, "-I", os.path.join(HERE, "overture.py"), c["id"], str(c["lat"]), str(c["lng"])], stdin=dl.stdout, stdout=f, stderr=subprocess.PIPE, text=True)
    dl.wait()
    if dl.returncode != 0 or flt.returncode != 0:
        print(f"FAIL {c['id']} dl={dl.returncode} filter={flt.returncode} {flt.stderr[-200:]}", flush=True)
        os.remove(out + ".tmp")
        continue
    os.replace(out + ".tmp", out)
    n = sum(1 for _ in open(out))
    index[c["id"]] = {"n": n, "updated": time.strftime("%Y-%m-%d")}
    json.dump(index, open(idx_path, "w"), sort_keys=True)
    print(f"{c['id']} {n} rows {time.time() - t0:.0f}s", flush=True)
print("done", flush=True)
