from __future__ import annotations
import os
from typing import Any, Dict, Optional, Tuple, List
from decimal import Decimal

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient, ASCENDING
import re

# -------------------- Config --------------------
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "HaydiGo")
client = MongoClient(MONGO_URI)
db = client[MONGO_DB]

IST_VIEWBOX = "28.40,41.30,29.45,40.80"
UA = "haydigo-demo/1.0"

# -------------------- Helpers --------------------
def _variants(value: Any) -> list:
    out, seen = [], set()
    for v in (value, str(value) if not isinstance(value, str) else None):
        if v is None:
            continue
        if isinstance(v, str):
            v = v.strip()
            if v.isdigit():
                try:
                    out.extend([int(v), float(v)])
                except:
                    pass
        out.append(v)
    res = []
    for v in out:
        k = (type(v), v)
        if k not in seen:
            seen.add(k)
            res.append(v)
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

def to_feature(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {
            "id": str(doc.get("stop_id")),
            "name": doc.get("stop_name"),
            "code": doc.get("stop_code"),
            "direction": doc.get("stop_desc"),
            "stop_type": doc.get("location_type"),
        },
        "geometry": {"type": "Point",
                     "coordinates": [doc.get("stop_lon"), doc.get("stop_lat")]},
    }

# -------------------- FastAPI --------------------
app = FastAPI(title="HaydiGo API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

@app.get("/")
def root():
    return {
        "ok": True,
        "service": "HaydiGo API",
        "endpoints": [
            "/api/geocode",
            "/stops/geojson",
            "/stops/{stop_id}/lines",
            "/routes/search?q=HAT",
            "/routes/between?from=STOP_ID&to=STOP_ID",
            "/debug/counts",
        ],
    }

# -------------------- Geocode --------------------
@app.get("/api/geocode")
def api_geocode(q: str):
    ll = geocode(q)
    if not ll: return {"ok": False, "error": "Geocode başarısız"}
    lat, lon = ll
    return {"ok": True, "lat": lat, "lon": lon}

# -------------------- Stops --------------------
@app.get("/stops/geojson")
def stops_geojson(
    minLon: float = Query(...), minLat: float = Query(...),
    maxLon: float = Query(...), maxLat: float = Query(...),
    limit: int = Query(2000, ge=1, le=10000),
):
    q = {"stop_lon": {"$gte": minLon, "$lte": maxLon},
         "stop_lat": {"$gte": minLat, "$lte": maxLat}}
    cur = db.stopss.find(q, {
        "stop_id":1, "stop_name":1, "stop_code":1, "stop_desc":1,
        "location_type":1, "stop_lat":1, "stop_lon":1
    }).limit(limit)
    feats = [to_feature(dedecimalize(d)) for d in cur]
    return {"type":"FeatureCollection","features":feats}

@app.get("/stops/{stop_id}/lines")
def get_lines_by_stop(stop_id: str):
    stop_keys = _variants(stop_id)
    trips_ids_cur = db.stop_times.find({"stop_id":{"$in":stop_keys}}, {"trip_id":1,"_id":0})
    trip_ids = [t["trip_id"] for t in trips_ids_cur]
    if not trip_ids: return {"stop_id": stop_id, "lines": []}

    trips_cur = db.trips.find({"trip_id":{"$in":trip_ids}}, {"route_id":1,"trip_headsign":1,"_id":0})
    route_to_headsigns: Dict[str, set] = {}
    route_keys: set = set()
    for t in trips_cur:
        rid_raw = t.get("route_id"); rid = str(rid_raw)
        route_keys.add(rid_raw)
        route_to_headsigns.setdefault(rid, set())
        if t.get("trip_headsign"): route_to_headsigns[rid].add(t["trip_headsign"])

    routes_cur = db.routes.find({
        "$or":[{"route_id":{"$in":list(route_keys)}},
               {"route_id":{"$in":[str(x) for x in route_keys]}}]
    }, {"route_id":1, "route_short_name":1, "route_long_name":1, "_id":0})

    lines=[]
    for r in routes_cur:
        rid=str(r["route_id"])
        lines.append({"route_id":rid,
                      "code":r.get("route_short_name"),
                      "name":r.get("route_long_name"),
                      "headsigns":sorted(route_to_headsigns.get(rid,[]))})
    lines.sort(key=lambda x:(x["code"] is None, str(x["code"])))
    return {"stop_id": stop_id, "lines": lines}

# -------------------- Routes Search --------------------
@app.get("/routes/search")
def routes_search(q: str, limit: int = 10):
    term = (q or "").strip()
    if not term:
        return {"ok": False, "results": []}

    # Case-insensitive search in properties.HAT_KODU
    cur = db.hat_guzergah_lite.find(
        {"properties.HAT_KODU": {"$regex": f"^{term}$", "$options": "i"}},
        {"_id": 0}
    ).limit(limit)

    results = []
    for d in cur:
        props = d.get("properties", {})
        geom = d.get("geometry", {})
        hat_kodu = props.get("HAT_KODU")
        hat_adi = props.get("HAT_ADI")

        coords = geom.get("coordinates", [])
        guzergah = []
        for c in coords:
            if isinstance(c, list) and len(c) == 2:
                guzergah.append({"lat": c[1], "lon": c[0]})

        results.append({
            "hat_kodu": hat_kodu,
            "hat_adi": hat_adi,
            "guzergah": guzergah
        })

    return {"ok": bool(results), "results": results}

# -------------------- Routes Between --------------------
@app.get("/routes/between")
def routes_between(from_stop: str, to_stop: str, limit: int = 5):
    # 1. Başlangıç durağından geçen tripler
    trips_from = db.stop_times.find({"stop_id": from_stop}, {"trip_id": 1, "_id": 0})
    trips_from_ids = {t["trip_id"] for t in trips_from}

    # 2. Hedef durağından geçen tripler
    trips_to = db.stop_times.find({"stop_id": to_stop}, {"trip_id": 1, "_id": 0})
    trips_to_ids = {t["trip_id"] for t in trips_to}

    # 3. Ortak tripler
    common_trips = list(trips_from_ids & trips_to_ids)
    if not common_trips:
        return {"ok": True, "results": []}

    # 4. Bu triplerin route_id’lerini al
    trips_cur = db.trips.find(
        {"trip_id": {"$in": common_trips}},
        {"route_id": 1, "_id": 0}
    )
    route_ids = {str(t["route_id"]) for t in trips_cur}

    # 5. Route bilgilerini al
    routes_cur = db.routes.find(
        {"route_id": {"$in": list(route_ids)}},
        {"route_id": 1, "route_short_name": 1, "route_long_name": 1, "_id": 0}
    )

    results = []
    for r in routes_cur:
        hat_kodu = r.get("route_short_name") or r.get("route_id")
        hat_adi = r.get("route_long_name")

        # 6. Güzergahı hat_guzergah_lite koleksiyonundan bul
        guz = db.hat_guzergah_lite.find_one(
            {"properties.HAT_KODU": hat_kodu},
            {"geometry.coordinates": 1, "properties.HAT_ADI": 1, "_id": 0}
        )
        coords = guz.get("geometry", {}).get("coordinates", []) if guz else []
        guzergah = [{"lat": c[1], "lon": c[0]} for c in coords if isinstance(c, list) and len(c) == 2]

        results.append({
            "hat_kodu": hat_kodu,
            "hat_adi": hat_adi,
            "guzergah": guzergah,
        })

    return {"ok": True, "results": results[:limit]}

# -------------------- Debug --------------------
@app.get("/debug/counts")
def debug_counts():
    return {
        "stopss": db.stopss.count_documents({}),
        "routes": db.routes.count_documents({}),
        "trips": db.trips.count_documents({}),
        "stop_times": db.stop_times.count_documents({}),
        "hat_guzergah_lite": db.hat_guzergah_lite.count_documents({}),
    }
