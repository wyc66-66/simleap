"""SimLeap interactive dashboard.

Serves the fidelity sweep + cliff analysis as a live UI: per-axis reliability
curves on the budget axis, the failure-mode breakdown, and the budget-stretch
summary (how much of each fidelity budget can be sacrificed before the policy
stops transferring).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from simleap.analysis import summarize

ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "ui" / "static"
RESULTS = ROOT / "results"

app = FastAPI(title="SimLeap", description="Fidelity-budget transfer-reliability dashboard")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/summary")
def api_summary():
    sweep_path = RESULTS / "sweep.json"
    if not sweep_path.exists():
        return JSONResponse({"error": "no sweep data found; run scripts/run_sweep.py first"}, status_code=404)
    return summarize(sweep_path)


@app.get("/sweep.json")
def sweep_json():
    sweep_path = RESULTS / "sweep.json"
    if not sweep_path.exists():
        return JSONResponse({"error": "no sweep data found"}, status_code=404)
    return FileResponse(sweep_path)


app.mount("/static", StaticFiles(directory=STATIC), name="static")
