from __future__ import annotations
from typing import Any, Dict
from fastapi import APIRouter, Query
from ..db.mongo import db
from ..utils.common import dedecimalize, to_feature, _variants

router = APIRouter()

@router.get("/stops/geojson")
def stops_geojson(
    minLon: float = Query(...),
    minLat: float = Query(...),
    maxLon: float = Query(...),
    maxLat: float = Query(...),
    limit: int = Query(2000, ge=1, le=10000),
):
    query: Dict[str, Any] = {
        "stop_lon": {"$gte": minLon, "$lte": maxLon},
        "stop_lat": {"$gte": minLat, "$lte": maxLat},
    }
    proj = {
        "_id": 0,
        "stop_id": 1,
        "stop_name": 1,
        "stop_code": 1,
        "stop_desc": 1,
        "location_type": 1,
        "stop_lat": 1,
        "stop_lon": 1,
    }
    cur = db.stopss.find(query, proj).limit(limit)
    feats = [to_feature(dedecimalize(d)) for d in cur]
    return {"type": "FeatureCollection", "features": feats}

@router.get("/stops/{stop_id}/lines")
def get_lines_by_stop(stop_id: str):
    # Tek aggregation: stop_times -> trips -> routes
    pipe = [
        {"$match": {"stop_id": {"$in": _variants(stop_id)}}},
        {"$lookup": {"from": "trips", "localField": "trip_id", "foreignField": "trip_id", "as": "t"}},
        {"$unwind": "$t"},
        {"$group": {"_id": "$t.route_id", "head": {"$addToSet": "$t.trip_headsign"}}},
        {"$lookup": {"from": "routes", "localField": "_id", "foreignField": "route_id", "as": "r"}},
        {"$unwind": "$r"},
        {
            "$project": {
                "_id": 0,
                "route_id": {"$toString": "$r.route_id"},
                "code": "$r.route_short_name",
                "name": "$r.route_long_name",
                "headsigns": {"$setDifference": ["$head", [None, ""]]},
            }
        },
    ]
    lines = list(db.stop_times.aggregate(pipe))
    lines.sort(key=lambda x: (x["code"] is None, str(x["code"])))
    return {"stop_id": stop_id, "lines": lines}
