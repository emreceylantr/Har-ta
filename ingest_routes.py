# ingest_routes.py — güvenli, parçalayıcı, ilerleme log'lu
from __future__ import annotations
import os, math, time
from typing import Any, List
from decimal import Decimal
import ijson
from pymongo import MongoClient
from pymongo.errors import BulkWriteError
from dotenv import load_dotenv

load_dotenv()
MONGO_URI  = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB   = os.getenv("MONGO_DB",  "HaydiGo")
SRC_PATH   = os.getenv("ROUTES_GEOJSON", "Har-ta/routes.geojson")
DEST_COLL  = os.getenv("DEST_COLL", "hat_guzergah_lite")

# Performans/sağlamlık ayarları
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))     # küçük tut
MAX_FEATURES = int(os.getenv("MAX_FEATURES", "0"))   # 0 = sınırsız; test için 1000 yapabilirsin
MAX_POINTS_PER_SEG = int(os.getenv("MAX_POINTS_PER_SEG", "5000"))  # uzun segmentleri böl
LOG_EVERY = 1000  # ilerleme log aralığı

client = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=5000,  # hızlı ping
    socketTimeoutMS=600000,         # uzun yazmalara izin
    connectTimeoutMS=10000,
)
db = client[MONGO_DB]
col = db[DEST_COLL]

def _as_float(x: Any) -> Any:
    if isinstance(x, Decimal): return float(x)
    if isinstance(x, str):
        s = x.strip()
        try: return float(s)
        except: return x
    return x

def _dedecimalize(o: Any) -> Any:
    if isinstance(o, dict):  return {k: _dedecimalize(v) for k,v in o.items()}
    if isinstance(o, list):  return [_dedecimalize(v) for v in o]
    if isinstance(o, Decimal): return float(o)
    return o

def _chunk_line(line: List[List[float]], max_pts=MAX_POINTS_PER_SEG) -> List[List[List[float]]]:
    if len(line) <= max_pts: return [line]
    out = []
    for i in range(0, len(line), max_pts):
        part = line[i:i+max_pts]
        if len(part) >= 2: out.append(part)
    return out

def _normalize_geometry(geom: dict) -> List[dict]:
    """
    GeoJSON geometriyi normalize eder ve büyükleri parçalara böler.
    Geriye 1+ feature-geometry (dict) döndürüyoruz.
    """
    if not geom or "type" not in geom: return []
    t = geom.get("type")
    coords = geom.get("coordinates")

    if t == "LineString":
        line = []
        for pt in coords or []:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                line.append([_as_float(pt[0]), _as_float(pt[1])])
        return [{"type":"LineString","coordinates":c} for c in _chunk_line(line)]

    if t == "MultiLineString":
        geoms = []
        for seg in coords or []:
            line = []
            for pt in seg or []:
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    line.append([_as_float(pt[0]), _as_float(pt[1])])
            for c in _chunk_line(line):
                geoms.append({"type":"LineString","coordinates":c})
        return geoms

    # Diğer tipler olduğu gibi, ama Decimal temiz
    return [_dedecimalize(geom)]

def iter_features(path: str):
    with open(path, "rb") as f:
        for feat in ijson.items(f, "features.item"):
            yield feat

def main():
    # bağlantı testi
    client.admin.command("ping")
    print("Mongo OK. Yükleme başlıyor…")
    t0 = time.time()

    # boşaltıp başla (istemiyorsan yorum satırı yap)
    col.drop()

    batch, n_in, n_out = [], 0, 0
    for feat in iter_features(SRC_PATH):
        n_in += 1
        if not isinstance(feat, dict) or feat.get("type") != "Feature":
            continue

        feat = _dedecimalize(feat)
        geoms = _normalize_geometry(feat.get("geometry", {}))
        props = _dedecimalize(feat.get("properties", {}))

        for g in geoms:
            batch.append({"type":"Feature", "properties": props, "geometry": g})
            if len(batch) >= BATCH_SIZE:
                try:
                    col.insert_many(batch, ordered=False, bypass_document_validation=True)
                    n_out += len(batch)
                except BulkWriteError as e:
                    # problemli dokümanları atlayarak devam et
                    n_out += e.details.get("nInserted", 0)
                finally:
                    batch.clear()

        if LOG_EVERY and n_in % LOG_EVERY == 0:
            dt = time.time() - t0
            print(f"{n_in} feature okundu, {n_out} parça yazıldı ({dt:.1f}s)")

        if MAX_FEATURES and n_in >= MAX_FEATURES:
            print(f"MAX_FEATURES sınırı nedeniyle durduruldu: {MAX_FEATURES}")
            break

    if batch:
        try:
            col.insert_many(batch, ordered=False, bypass_document_validation=True)
            n_out += len(batch)
        except BulkWriteError as e:
            n_out += e.details.get("nInserted", 0)
        finally:
            batch.clear()

    # index en sonda
    try:
        col.create_index([("geometry","2dsphere")])
    except Exception:
        pass

    dt = time.time() - t0
    print(f"OK - input={n_in}, inserted={n_out}, coll={DEST_COLL}, {dt:.1f}s")

if __name__ == "__main__":
    main()
