import os
from fastapi import FastAPI

app = FastAPI(title="Pepeuch AI Scheduler", version="0.0.1")

@app.get("/health")
def health():
    return {
        "status": "ok",
        "component": "scheduler-skeleton",
        "ray_address": os.getenv("RAY_ADDRESS"),
    }

@app.get("/api/v1/status")
def status():
    return {
        "phase": "skeleton",
        "message": "Scheduler logic will be implemented during TODO phases 6 and 7.",
    }
