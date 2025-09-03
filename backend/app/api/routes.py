from __future__ import annotations
from fastapi import APIRouter
from ..db.mongo import db

router = APIRouter()

@router.get("/routes/search")
def routes_search(q: str, limit: int = 10):
    term = (q or "").strip()
    if not term:
        return {"ok": False, "results": []}

    cur = db.hat_guzergah_lite.find(
        {"properties.HAT_KODU": {"$regex": f"^{term}$", "$options": "i"}},
        {"_id": 0},
    ).limit(limit)

    results = []
    for d in cur:
        props = d.get("properties", {})
        coords = d.get("geometry", {}).get("coordinates", [])
        guz = []
        for c in coords:
            if isinstance(c, list) and len(c) == 2:
                guz.append({"lat": c[1], "lon": c[0]})
        results.append(
            {"hat_kodu": props.get("HAT_KODU"),
             "hat_adi": props.get("HAT_ADI"),
             "guzergah": guz}
        )
    return {"ok": bool(results), "results": results}

@router.get("/routes/between")
def routes_between(from_stop: str, to_stop: str, limit: int = 5):
    trips_from = {
        t["trip_id"]
        for t in db.stop_times.find({"stop_id": from_stop}, {"_id": 0, "trip_id": 1})
    }
    trips_to = {
        t["trip_id"]
        for t in db.stop_times.find({"stop_id": to_stop}, {"_id": 0, "trip_id": 1})
    }
    common = list(trips_from & trips_to)
    if not common:
        return {"ok": True, "results": []}

    route_ids = {
        str(t["route_id"])
        for t in db.trips.find({"trip_id": {"$in": common}}, {"_id": 0, "route_id": 1})
    }
    routes = db.routes.find(
        {"route_id": {"$in": list(route_ids)}},
        {"_id": 0, "route_id": 1, "route_short_name": 1, "route_long_name": 1},
    )

    out = []
    for r in routes:
        hat_kodu = r.get("route_short_name") or r.get("route_id")
        guz = db.hat_guzergah_lite.find_one(
            {"properties.HAT_KODU": hat_kodu},
            {"_id": 0, "geometry.coordinates": 1, "properties.HAT_ADI": 1},
        )
        coords = (guz or {}).get("geometry", {}).get("coordinates", [])
        guzergah = [
            {"lat": c[1], "lon": c[0]}
            for c in coords
            if isinstance(c, list) and len(c) == 2
        ]
        out.append(
            {"hat_kodu": hat_kodu, "hat_adi": r.get("route_long_name"), "guzergah": guzergah}
        )
    return {"ok": True, "results": out[:limit]}
