# server.py (basitleştirilmiş: "en yakın durak" endpointi kaldırıldı)
from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple
from decimal import Decimal

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "HaydiGo")

IST_VIEWBOX = "28.40,41.30,29.45,40.80"
UA = "haydigo-demo/1.0"

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]

# Geo sorgular için indeks (bbox sorgularında da performans sağlar)
try:
    db.stops.create_index([("geometry", "2dsphere")])
except Exception:
    pass

app = FastAPI(title="HaydiGo (simple)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

def dedecimalize(x: Any) -> Any:
    """Decimal -> float (derin dönüştürme)"""
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, list):
        return [dedecimalize(i) for i in x]
    if isinstance(x, tuple):
        return tuple(dedecimalize(i) for i in x)
    if isinstance(x, dict):
        return {k: dedecimalize(v) for k, v in x.items()}
    return x

def geocode(text: str) -> Optional[Tuple[float, float]]:
    """Nominatim (İstanbul kutusu) -> (lat, lon)"""
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": text,
        "format": "json",
        "accept-language": "tr",
        "viewbox": IST_VIEWBOX,
        "bounded": 1,
        "limit": 1,
    }
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
    """Stop belgesini küçük bir GeoJSON Feature'a çevir."""
    return {
        "type": "Feature",
        "properties": {
            "id": str(doc.get("_id")),
            "name": doc.get("name"),
            "code": doc.get("code"),
            "direction": doc.get("direction"),
            "stop_type": doc.get("stop_type"),
        },
        "geometry": doc.get("geometry"),
    }

@app.get("/")
def root():
    return {
        "ok": True,
        "service": "HaydiGo API (simple)",
        "endpoints": [
            "/api/geocode",
            "/stops/geojson",
        ],
    }

@app.get("/api/geocode")
def api_geocode(q: str):
    """Adres/yer adı -> koordinat (İstanbul kutusunda arar)."""
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
    """Verilen kutu içindeki durakları GeoJSON FeatureCollection olarak döndür."""
    q = {"geometry": {"$geoWithin": {"$box": [[minLon, minLat], [maxLon, maxLat]]}}}
    cur = db.stops.find(
        q,
        {"geometry": 1, "name": 1, "code": 1, "direction": 1, "stop_type": 1}
    ).limit(limit)
    feats = [to_feature(dedecimalize(d)) for d in cur]
    return {"type": "FeatureCollection", "features": feats}
