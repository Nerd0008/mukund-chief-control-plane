import json
p = r"runtime/career-ops/discovery/unified/uk/unified-uk-20261012T223002Z.json"
d = json.load(open(p, encoding="utf-8"))
s = d.get("semantic") or {}
print("semantic keys:", sorted(s.keys()))
for k in ("provider","provider_used","model","attempted","classified","accepted","errors","fallback","fallback_used","note"):
    v = s.get(k)
    if v is not None:
        print(" ", k, "=", str(v)[:400])
e = s.get("errors") or []
print("errors count:", len(e))
for x in e[:5]: print("  ", str(x)[:300])
f = d.get("funnel") or {}
print("funnel:", json.dumps({k: v for k, v in f.items() if not isinstance(v, dict)}, ensure_ascii=False)[:800])
