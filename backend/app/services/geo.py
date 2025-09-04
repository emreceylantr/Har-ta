from __future__ import annotations
from typing import Optional, Tuple
import requests
from ..utils.common import IST_VIEWBOX, UA

def geocode(text: str) -> Optional[Tuple[float, float]]:
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": text,
                "format": "json",
                "accept-language": "tr",
                "viewbox": IST_VIEWBOX,
                "bounded": 1,
                "limit": 1,
            },
            headers={"User-Agent": UA},
            timeout=8,
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except requests.RequestException:
        return None

def haversine(lat1, lon1, lat2, lon2) -> float:         
    from math import radians, sin, cos, asin, sqrt
    r_earth = 6371000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r_earth * asin(sqrt(a))
