from __future__ import annotations
from typing import Any, Dict, List
from decimal import Decimal

# Sabitler
IST_VIEWBOX = "28.40,41.30,29.45,40.80"
UA = "haydigo-demo/1.0"

def _variants(v: Any) -> List[Any]:
    out: list = []
    seen: set = set()
    candidates = [v] if isinstance(v, str) else [v, str(v)]
    for x in candidates:
        if x is None:
            continue
        if isinstance(x, str):
            s = x.strip()
            if s.isdigit():
                try:
                    out.append(int(s))
                    out.append(float(s))
                except Exception:
                    pass
            out.append(s)
        else:
            out.append(x)
    res: list = []
    for x in out:
        k = (type(x), x)
        if k not in seen:
            seen.add(k)
            res.append(x)
    return res

def dedecimalize(x: Any) -> Any:
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, list):
        return [dedecimalize(i) for i in x]
    if isinstance(x, dict):
        return {k: dedecimalize(v) for k, v in x.items()}
    return x

def to_feature(d: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {
            "id": str(d.get("stop_id")),
            "name": d.get("stop_name"),
            "code": d.get("stop_code"),
            "direction": d.get("stop_desc"),
            "stop_type": d.get("location_type"),
        },
        "geometry": {"type": "Point", "coordinates": [d.get("stop_lon"), d.get("stop_lat")]},
    }
