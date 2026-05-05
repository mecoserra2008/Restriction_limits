"""
FastAPI application that powers the Restriction Limits dashboard.

Endpoints
---------
GET  /api/health                 -> liveness check
GET  /api/limits/dates           -> available daily files
GET  /api/limits/latest          -> latest LimitSnapshot
GET  /api/limits/{date}          -> LimitSnapshot for a given date (DD-MM-YYYY)
GET  /api/exposure               -> ExposureSnapshot from the consolidated file
GET  /api/report                 -> BreachReport (limits x exposures)
GET  /api/report/summary         -> roll-up by axis (used by the dashboard cards)
POST /api/cache/invalidate       -> drop the in-memory cache

The CORS middleware is configured to accept the React dev server and the
``tauri://localhost`` origin used when the app is packaged as a desktop
binary (see docs/REACT_DESKTOP_INTEGRATION.md).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import SETTINGS
from .models import BreachReport, ExposureSnapshot, LimitSnapshot
from .services import aggregator
from .services.cache import CACHE
from .services.exposure_loader import load_exposure_file
from .services.limits_loader import (
    discover_files,
    latest_snapshot,
    load_limits_file,
    snapshot_for_date,
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s | %(message)s")
log = logging.getLogger("restriction_limits")

app = FastAPI(
    title="Restriction Limits Dashboard API",
    version="0.1.0",
    description=(
        "Backend service that consolidates exposure (Bloomberg + Market "
        "Access) against the credit-risk limits workbook."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=SETTINGS.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cached_limits(path: Path) -> LimitSnapshot:
    return CACHE.get_or_load(path, load_limits_file)


def _cached_exposure(path: Path) -> ExposureSnapshot:
    return CACHE.get_or_load(path, lambda p: load_exposure_file(p))


def _resolve_limit_snapshot(target: Optional[date]) -> LimitSnapshot:
    if target is None:
        snap = latest_snapshot()
        if snap is None:
            raise HTTPException(404, "No limit files found under "
                                     f"{SETTINGS.limits_base_dir}")
        return snap
    snap = snapshot_for_date(target)
    if snap is None:
        raise HTTPException(404, f"No limit file for {target.isoformat()}")
    return snap


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "now": datetime.utcnow().isoformat() + "Z",
        "limits_base_dir": str(SETTINGS.limits_base_dir),
        "exposure_file": str(SETTINGS.exposure_file),
        "bloomberg_enabled": SETTINGS.bloomberg_enabled,
    }


@app.get("/api/limits/dates")
def limits_dates():
    files = discover_files()
    return [{"date": d.isoformat(), "file": str(p)} for d, p in files]


@app.get("/api/limits/latest", response_model=LimitSnapshot)
def limits_latest():
    return _resolve_limit_snapshot(None)


@app.get("/api/limits/{target}", response_model=LimitSnapshot)
def limits_for_date(target: date):
    return _resolve_limit_snapshot(target)


@app.get("/api/exposure", response_model=ExposureSnapshot)
def exposure(file: Optional[str] = Query(default=None)):
    path = Path(file) if file else Path(SETTINGS.exposure_file)
    if not path.exists():
        raise HTTPException(
            404,
            f"Exposure file not found: {path}. "
            "Set RL_EXPOSURE_FILE or pass ?file=...",
        )
    return _cached_exposure(path)


@app.get("/api/report", response_model=BreachReport)
def report(target: Optional[date] = Query(default=None, alias="date")):
    limits = _resolve_limit_snapshot(target)
    expo_path = Path(SETTINGS.exposure_file)
    if not expo_path.exists():
        # Still useful: return limits-only report with zero exposures
        empty = ExposureSnapshot(as_of=limits.as_of,
                                 source_file=str(expo_path), positions=[])
        return aggregator.build_report(limits, empty)
    return aggregator.build_report(limits, _cached_exposure(expo_path))


@app.get("/api/report/summary")
def report_summary(target: Optional[date] = Query(default=None, alias="date")):
    rep = report(target)  # type: ignore[arg-type]
    return {
        "as_of": rep.as_of.isoformat(),
        "total_exposure": rep.total_exposure,
        "total_limit": rep.total_limit,
        "breached_count": rep.breached_count,
        "by_axis": aggregator.summarise_by_axis(rep),
    }


@app.post("/api/cache/invalidate")
def cache_invalidate():
    CACHE.invalidate()
    return {"ok": True}


def main():  # entry point for `python -m backend.app`
    import uvicorn

    uvicorn.run(
        "backend.app:app",
        host=SETTINGS.api_host,
        port=SETTINGS.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
