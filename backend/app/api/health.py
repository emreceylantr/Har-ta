from __future__ import annotations
from fastapi import APIRouter
from ..services.geo import geocode
from ..db.mongo import db

router = APIRouter()

@router.get("/")
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

@router.get("/api/geocode")
def api_geocode(q: str):
    ll = geocode(q)
    if not ll:
        return {"ok": False, "error": "Geocode başarısız"}
    lat, lon = ll
    return {"ok": True, "lat": lat, "lon": lon}

@router.get("/debug/counts")
def debug_counts():
    cols = ["stopss", "routes", "trips", "stop_times", "hat_guzergah_lite"]
    return {k: db[k].count_documents({}) for k in cols}
