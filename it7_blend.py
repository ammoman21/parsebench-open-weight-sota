# Box-side: it7 blend = ALL real EDGAR bold + synthetic strike/sup/sub + negatives.
# Rationale: EDGAR replaces synthetic bold (real texture); synthetic remains sole
# source of strike/sup/sub (verified absent from EDGAR corpus); negatives teach restraint.
import json, random
rows, seen = [], set()
def add(d, keep):
    for l in open(f"/workspace/{d}/data.jsonl"):
        r = json.loads(l)
        if not r["image"].startswith(d): r["image"] = f"{d}/{r['image']}"
        if keep(r) and r["image"] not in seen:
            seen.add(r["image"]); rows.append(r)
add("data_edgar", lambda r: True)
add("data5k",  lambda r: any(m in r["target"] for m in ("~~","<sup>","<sub>")))
add("data_t",  lambda r: any(m in r["target"] for m in ("~~","<sup>","<sub>")) or "【" in r["target"])
neg = []
for l in open("/workspace/data5k/data.jsonl"):
    r = json.loads(l)
    if not r["styled"]:
        r["image"] = f"data5k/{r['image']}"
        if r["image"] not in seen: neg.append(r)
random.Random(0).shuffle(neg)
rows += neg[:1200]
random.Random(1).shuffle(rows)
open("/workspace/data.jsonl","w").write("\n".join(json.dumps(x) for x in rows))
import collections
mk = collections.Counter()
for r in rows:
    for m in ("**","~~","<sup>","<sub>"): mk[m] += r["target"].count(m)
print(f"it7 blend: {len(rows)} rows | markers {dict(mk)}")
