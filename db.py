import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB", "HaydiGo")

_client = None
_db = None

def get_db():
    global _client, _db
    if _db:
        return _db
    try:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        _client.admin.command("ping") 
        _db = _client[MONGO_DB]
        return _db
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        raise SystemExit(f"MongoDB bağlantı hatası: {e}")
