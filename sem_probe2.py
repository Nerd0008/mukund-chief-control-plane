import json
p = r"runtime/career-ops/discovery/unified/uk/unified-uk-20261012T223002Z.json"
d = json.load(open(p, encoding="utf-8"))
print(json.dumps(d.get("semantic"), indent=1, ensure_ascii=False)[:2500])
print("=== counts ===")
print(json.dumps(d.get("counts"), indent=1, ensure_ascii=False)[:1500])
