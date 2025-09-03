from __future__ import annotations
import os
from typing import Any, Dict, Optional, Tuple
from decimal import Decimal

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient

# ---------- Config ----------
load_dotenv()
client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
db = client[os.getenv("MONGO_DB", "HaydiGo")]
IST_VIEWBOX = "28.40,41.30,29.45,40.80"
UA = "haydigo-demo/1.0"

# ---------- Helpers ----------
def _variants(v: Any) -> list:
    """'123' -> ['123', 123, 123.0] gibi varyantlar üretir, tekrarsız."""
    out, seen = [], set()
    cands = [v] if isinstance(v, str) else [v, str(v)]
    for x in cands:
        if x is None: 
            continue
        if isinstance(x, str):
            s = x.strip()
            if s.isdigit():
                try:
                    out += [int(s), float(s)]
                except Exception:
                    pass
            out.append(s)
        else:
            out.append(x)
    res = []
    for x in out:
        k = (type(x), x)
        if k not in seen:
            seen.add(k); res.append(x)
    return res

def dedecimalize(x: Any) -> Any:
    if isinstance(x, Decimal): return float(x)
    if isinstance(x, list): return [dedecimalize(i) for i in x]
    if isinstance(x, dict): return {k: dedecimalize(v) for k, v in x.items()}
    return x

def geocode(text: str) -> Optional[Tuple[float, float]]:
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": text, "format": "json", "accept-language": "tr",
              "viewbox": IST_VIEWBOX, "bounded": 1, "limit": 1}
    try:
        r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=8)
        r.raise_for_status()
    except requests.RequestException:
        return None
    data = r.json()
    if not data: return None
    return float(data[0]["lat"]), float(data[0]["lon"])

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

# ---------- App ----------
app = FastAPI(title="HaydiGo API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

@app.get("/")
def root():
    return {"ok": True, "service": "HaydiGo API", "endpoints": [
        "/api/geocode",
        "/stops/geojson",
        "/stops/{stop_id}/lines",
        "/routes/search?q=HAT",
        "/routes/between?from=STOP_ID&to=STOP_ID",
        "/debug/counts",
    ]}

# ---------- Geocode ----------
@app.get("/api/geocode")
def api_geocode(q: str):
    ll = geocode(q)
    if not ll: return {"ok": False, "error": "Geocode başarısız"}
    lat, lon = ll
    return {"ok": True, "lat": lat, "lon": lon}

# ---------- Stops ----------
@app.get("/stops/geojson")
def stops_geojson(
    minLon: float = Query(...), minLat: float = Query(...),
    maxLon: float = Query(...), maxLat: float = Query(...),
    limit: int = Query(2000, ge=1, le=10000),
):
    q = {"stop_lon": {"$gte": minLon, "$lte": maxLon}, "stop_lat": {"$gte": minLat, "$lte": maxLat}}
    cur = db.stopss.find(q, {
        "_id": 0, "stop_id":1, "stop_name":1, "stop_code":1, "stop_desc":1, "location_type":1, "stop_lat":1, "stop_lon":1
    }).limit(limit)
    return {"type":"FeatureCollection","features":[to_feature(dedecimalize(d)) for d in cur]}

@app.get("/stops/{stop_id}/lines")
def get_lines_by_stop(stop_id: str):
    trip_ids = [t["trip_id"] for t in db.stop_times.find({"stop_id":{"$in":_variants(stop_id)}},{"_id":0,"trip_id":1})]
    if not trip_ids: return {"stop_id": stop_id, "lines": []}

    trips = db.trips.find({"trip_id":{"$in":trip_ids}}, {"_id":0,"route_id":1,"trip_headsign":1})
    route_to_head, route_keys = {}, set()
    for t in trips:
        rid_raw = t.get("route_id"); rid = str(rid_raw)
        route_keys.add(rid_raw)
        route_to_head.setdefault(rid, set())
        if t.get("trip_headsign"): route_to_head[rid].add(t["trip_headsign"])

    routes = db.routes.find({
        "$or":[{"route_id":{"$in":list(route_keys)}},{"route_id":{"$in":[str(x) for x in route_keys]}}]
    }, {"_id":0,"route_id":1,"route_short_name":1,"route_long_name":1})

    lines = [{
        "route_id": str(r["route_id"]),
        "code": r.get("route_short_name"),
        "name": r.get("route_long_name"),
        "headsigns": sorted(route_to_head.get(str(r["route_id"]), []))
    } for r in routes]
    lines.sort(key=lambda x:(x["code"] is None, str(x["code"])))
    return {"stop_id": stop_id, "lines": lines}

# ---------- Routes Search ----------
@app.get("/routes/search")
def routes_search(q: str, limit: int = 10):
    term = (q or "").strip()
    if not term: return {"ok": False, "results": []}

    cur = db.hat_guzergah_lite.find(
        {"properties.HAT_KODU": {"$regex": f"^{term}$", "$options": "i"}}, {"_id":0}
    ).limit(limit)

    results = []
    for d in cur:
        props, geom = d.get("properties", {}), d.get("geometry", {})
        coords = geom.get("coordinates", [])
        guzergah = [{"lat": c[1], "lon": c[0]} for c in coords if isinstance(c, list) and len(c)==2]
        results.append({"hat_kodu": props.get("HAT_KODU"), "hat_adi": props.get("HAT_ADI"), "guzergah": guzergah})
    return {"ok": bool(results), "results": results}

# ---------- Routes Between ----------
@app.get("/routes/between")
def routes_between(from_stop: str, to_stop: str, limit: int = 5):
    trips_from = {t["trip_id"] for t in db.stop_times.find({"stop_id": from_stop},{"_id":0,"trip_id":1})}
    trips_to   = {t["trip_id"] for t in db.stop_times.find({"stop_id": to_stop},{"_id":0,"trip_id":1})}
    common = list(trips_from & trips_to)
    if not common: return {"ok": True, "results": []}

    route_ids = {str(t["route_id"]) for t in db.trips.find({"trip_id":{"$in":common}}, {"_id":0,"route_id":1})}
    routes = db.routes.find({"route_id":{"$in":list(route_ids)}},
                            {"_id":0,"route_id":1,"route_short_name":1,"route_long_name":1})

    results = []
    for r in routes:
        hat_kodu = r.get("route_short_name") or r.get("route_id")
        guz = db.hat_guzergah_lite.find_one(
            {"properties.HAT_KODU": hat_kodu},
            {"_id":0, "geometry.coordinates":1, "properties.HAT_ADI":1},
        )
        coords = (guz or {}).get("geometry", {}).get("coordinates", [])
        guzergah = [{"lat": c[1], "lon": c[0]} for c in coords if isinstance(c, list) and len(c)==2]
        results.append({"hat_kodu": hat_kodu, "hat_adi": r.get("route_long_name"), "guzergah": guzergah})
    return {"ok": True, "results": results[:limit]}

# ---------- Debug ----------
@app.get("/debug/counts")
def debug_counts():
    return {
        "stopss": db.stopss.count_documents({}),
        "routes": db.routes.count_documents({}),
        "trips": db.trips.count_documents({}),
        "stop_times": db.stop_times.count_documents({}),
        "hat_guzergah_lite": db.hat_guzergah_lite.count_documents({}),
    }
