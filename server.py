from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple
from decimal import Decimal

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient, ASCENDING

# config
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "HaydiGo")
IST_VIEWBOX = "28.40,41.30,29.45,40.80"
UA = "haydigo-demo/1.0"

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]

# helpers
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
                except Exception:
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
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, list):
        return [dedecimalize(i) for i in x]
    if isinstance(x, dict):
        return {k: dedecimalize(v) for k, v in x.items()}
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
    if not data:
        return None
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

# indexes
for coll, fields in [
    ("stopss", ["stop_lon", "stop_lat"]),
    ("stop_times", ["stop_id"]),
    ("trips", ["trip_id", "route_id"]),
    ("routes", ["route_id"]),
]:
    for f in fields:
        try:
            getattr(db, coll).create_index([(f, ASCENDING)])
        except Exception:
            pass

# api
app = FastAPI(title="HaydiGo (GTFS)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

@app.get("/")
def root():
    return {
        "ok": True,
        "service": "HaydiGo API (GTFS)",
        "endpoints": [
            "/api/geocode",
            "/stops/geojson",
            "/stops/{stop_id}/lines",
            "/debug/counts",
            "/debug/sample",
        ],
    }

@app.get("/api/geocode")
def api_geocode(q: str):
    ll = geocode(q)
    if not ll:
        return {"ok": False, "error": "Geocode başarısız"}
    lat, lon = ll
    return {"ok": True, "lat": lat, "lon": lon}

@app.get("/stops/geojson")
def stops_geojson(
    minLon: float = Query(..., description="BBox left"),
    minLat: float = Query(..., description="BBox bottom"),
    maxLon: float = Query(..., description="BBox right"),
    maxLat: float = Query(..., description="BBox top"),
    limit: int = Query(2000, ge=1, le=10000),
):
    q = {
        "stop_lon": {"$gte": minLon, "$lte": maxLon},
        "stop_lat": {"$gte": minLat, "$lte": maxLat},
    }
    cur = db.stopss.find(
        q,
        {
            "stop_id": 1,
            "stop_name": 1,
            "stop_code": 1,
            "stop_desc": 1,
            "location_type": 1,
            "stop_lat": 1,
            "stop_lon": 1,
        },
    ).limit(limit)
    feats = [to_feature(dedecimalize(d)) for d in cur]
    return {"type": "FeatureCollection", "features": feats}

@app.get("/stops/{stop_id}/lines")
def get_lines_by_stop(stop_id: str):
    stop_keys = _variants(stop_id)
    trips_ids_cur = db.stop_times.find(
        {"stop_id": {"$in": stop_keys}}, {"trip_id": 1, "_id": 0}
    )
    trip_ids = [t["trip_id"] for t in trips_ids_cur]
    if not trip_ids:
        return {"stop_id": stop_id, "lines": []}

    trips_cur = db.trips.find(
        {"trip_id": {"$in": trip_ids}}, {"route_id": 1, "trip_headsign": 1, "_id": 0}
    )
    route_to_headsigns: Dict[str, set] = {}
    route_keys: set = set()
    for t in trips_cur:
        rid_raw = t.get("route_id")
        rid = str(rid_raw)
        route_keys.add(rid_raw)
        if rid not in route_to_headsigns:
            route_to_headsigns[rid] = set()
        if t.get("trip_headsign"):
            route_to_headsigns[rid].add(t["trip_headsign"])

    routes_cur = db.routes.find(
        {
            "$or": [
                {"route_id": {"$in": list(route_keys)}},
                {"route_id": {"$in": [str(x) for x in route_keys]}},
            ]
        },
        {"route_id": 1, "route_short_name": 1, "route_long_name": 1, "_id": 0},
    )

    lines = []
    for r in routes_cur:
        rid = str(r["route_id"])
        lines.append(
            {
                "route_id": rid,
                "code": r.get("route_short_name"),
                "name": r.get("route_long_name"),
                "headsigns": sorted(route_to_headsigns.get(rid, [])),
            }
        )
    lines.sort(key=lambda x: (x["code"] is None, str(x["code"])))
    return {"stop_id": stop_id, "lines": lines}

@app.get("/debug/counts")   
def debug_counts():
    return {
        "stopss": db.stopss.count_documents({}),
        "routes": db.routes.count_documents({}),
        "trips": db.trips.count_documents({}),
        "stop_times": db.stop_times.count_documents({}),
    }

@app.get("/debug/sample")
def debug_sample():
    s = db.stopss.find_one({}, {"stop_id": 1, "stop_name": 1})
    if not s:
        return {"ok": False, "error": "stopss boş"}
    sid = str(s["stop_id"])
    lines = get_lines_by_stop(sid)["lines"][:5]
    return {"ok": True, "stop": {"id": sid, "name": s.get("stop_name")}, "lines": lines}
