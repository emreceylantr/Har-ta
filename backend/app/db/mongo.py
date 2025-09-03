from __future__ import annotations
import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()
_MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
_DB_NAME = os.getenv("MONGO_DB", "HaydiGo")

_client = MongoClient(_MONGO_URI)
db = _client[_DB_NAME]
