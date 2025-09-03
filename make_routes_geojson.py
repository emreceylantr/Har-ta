import json
from pathlib import Path

in_path = Path("Har-ta/raw_routes.txt")
out_path = Path("Har-ta/routes.geojson")

features = []

# Her satırı ayrı JSON olarak oku
with in_path.open(encoding="utf-8", errors="ignore") as f:
    for line in f:
        line = line.strip().rstrip(",")
        if not line:
            continue
        try:
            feat = json.loads(line)
            if feat.get("type") == "Feature":
                features.append(feat)
        except Exception:
            # bazen birden çok Feature aynı satırda olabilir
            if '"type"' in line and '"Feature"' in line:
                parts = line.split("}{")
                for i, p in enumerate(parts):
                    if not p.startswith("{"):
                        p = "{" + p
                    if not p.endswith("}"):
                        p = p + "}"
                    try:
                        feat = json.loads(p)
                        if feat.get("type") == "Feature":
                            features.append(feat)
                    except:
                        pass

fc = {"type": "FeatureCollection", "features": features}

out_path.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
print(f"OK: {out_path} yazıldı. features={len(features)}")
