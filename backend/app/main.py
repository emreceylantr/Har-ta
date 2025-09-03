from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Router'lar
from .api import health, stops, routes

app = FastAPI(title="HaydiGo API", version="1.0")

# CORS (prod'da allow_origins'i domaine kısıtla)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Endpoint grupları
app.include_router(health.router)
app.include_router(stops.router)
app.include_router(routes.router)
