from __future__ import annotations

import os
import sys
import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError
import ijson


def dedecimalize(x: Any) -> Any:
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, list):
        return [dedecimalize(i) for i in x]
    if isinstance(x, tuple):
        return tuple(dedecimalize(i) for i in x)
    if isinstance(x, dict):
        return {k: dedecimalize(v) for k, v in x.items()}
    return x


def tr_parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def to_int(x: Any) -> Optional[int]:
    try:
        return int(str(x).strip())
    except Exception:
        return None


def to_float_with_comma(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return None


def fallback_id(props: Dict[str, Any], geom: Dict[str, Any]) -> Optional[str]:
    code = props.get("DURAK_KODU") or props.get("code")
    if code:
        return f"code:{code}"

    if geom and geom.get("type") == "Point":
        coords = geom.get("coordinates")
        if isinstance(coords, (list, tuple)) and len(coords) == 2:
            try:
                lon = float(coords[0])
                lat = float(coords[1])
                return f"pt:{round(lon, 6)}:{round(lat, 6)}"
            except Exception:
                return None
    return None


def validate_point(geom: Dict[str, Any]) -> bool:
    if not geom or geom.get("type") != "Point":
        return True

    coords = geom.get("coordinates")
    if not (isinstance(coords, (list, tuple)) and len(coords) == 2):
        return False
    try:
        lon = float(coords[0])
        lat = float(coords[1])
        return (-180.0 <= lon <= 180.0) and (-90.0 <= lat <= 90.0)
    except Exception:
        return False


def normalize_feature(feature: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(feature, dict) or feature.get("type") != "Feature":
        return None

    feature = dedecimalize(feature)
    props = feature.get("properties") or {}
    geom = feature.get("geometry") or {}

    if not validate_point(geom):
        return None

    _id = props.get("ID") or props.get("Id") or props.get("id") or fallback_id(props, geom)
    if _id is None:
        return None

    return {
        "_id": str(_id),
        "name": props.get("ADI"),
        "code": props.get("DURAK_KODU"),
        "status": to_int(props.get("DURUMU")),
        "stop_type": props.get("DURAK_TIPI"),
        "direction": props.get("YON_BILGIS"),
        "last_updated": tr_parse_dt(props.get("SON_GUNCEL")),
        "built_at": tr_parse_dt(props.get("YAPILIS_TA")),
        "district_id": props.get("ILCEID"),
        "neighborhood_id": props.get("MAHALLEID"),
        "version": props.get("VERSIYON"),
        "version_num": to_float_with_comma(props.get("VERSIYON")),
        "has_shelter_flag": props.get("CEP_VAR"),
        "geometry": geom,
        "raw_properties": props,
    }


def stream_features_geojson(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, "rb") as f:
        parser = ijson.parse(f)
        mode = None
        for i, (prefix, event, value) in enumerate(parser):
            if i > 80:
                break
            if prefix == "type" and event == "string" and value == "FeatureCollection":
                mode = "fc"
                break
            if event == "start_array" and prefix == "":
                mode = "array"
                break

        f.seek(0)

        if mode == "fc":
            for feature in ijson.items(f, "features.item", use_float=True):
                yield feature
            return

        if mode == "array":
            for feature in ijson.items(f, "item", use_float=True):
                yield feature
            return

        obj = json.load(f)
        if isinstance(obj, dict) and obj.get("type") == "Feature":
            yield obj
        elif isinstance(obj, dict) and obj.get("type") == "FeatureCollection":
            for ft in obj.get("features", []):
                yield ft
        elif isinstance(obj, list):
            for ft in obj:
                yield ft
        else:
            raise ValueError("Invalid GeoJSON format.")


def stream_features(path: str) -> Iterable[Dict[str, Any]]:
    return stream_features_geojson(path)


def main() -> None:
    load_dotenv()
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db = os.getenv("MONGO_DB", "HaydiGo")
    mongo_coll = os.getenv("MONGO_COLL", "stops")
    json_path = sys.argv[1] if len(sys.argv) >= 2 else "duraklar.json"

    print(f"→ Import\n  file: {json_path}\n  uri: {mongo_uri}\n  db: {mongo_db}\n  coll: {mongo_coll}")

    client = MongoClient(mongo_uri)
    db = client[mongo_db]
    coll = db[mongo_coll]
    coll.create_index([("geometry", "2dsphere")])

    batch_ops: List[UpdateOne] = []
    batch_size = 500
    total = ok = skipped = 0

    try:
        for feature in stream_features(json_path):
            total += 1
            doc = normalize_feature(feature)
            if not doc:
                skipped += 1
                continue

            doc = dedecimalize(doc)
            batch_ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": doc}, upsert=True))

            if len(batch_ops) >= batch_size:
                coll.bulk_write(batch_ops, ordered=False)
                ok += len(batch_ops)
                batch_ops = []

        if batch_ops:
            coll.bulk_write(batch_ops, ordered=False)
            ok += len(batch_ops)

    except BulkWriteError as e:
        print("BulkWriteError:", e.details)
    except FileNotFoundError:
        print(f"missing file: {json_path}")
        return

    print(f"✓ done. total={total} ok_ops={ok} skipped={skipped}")


if __name__ == "__main__":
    main()
