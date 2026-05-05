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
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import SETTINGS
from .models import BreachReport, Bucket, ExposureSnapshot, LimitSnapshot, Severity
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


def _build_report(target: Optional[date]) -> BreachReport:
    limits = _resolve_limit_snapshot(target)
    expo_path = Path(SETTINGS.exposure_file)
    if not expo_path.exists():
        # Limits-only report with zero exposures (still useful to inspect caps)
        empty = ExposureSnapshot(as_of=limits.as_of,
                                 source_file=str(expo_path), positions=[])
        return aggregator.build_report(limits, empty)
    return aggregator.build_report(limits, _cached_exposure(expo_path))


@app.get("/api/report", response_model=BreachReport)
def report(
    target: Optional[date] = Query(default=None, alias="date"),
    axis: Optional[List[Literal["Contraparte", "País", "Tipo",
                                "Tipo de linha", "RAF"]]] = Query(default=None),
    severity: Optional[List[Severity]] = Query(default=None),
    breached_only: bool = Query(default=False),
    min_utilization: Optional[float] = Query(default=None,
                                              description="In percent (0-100+)"),
):
    rep = _build_report(target)
    buckets = rep.buckets
    if axis:
        buckets = [b for b in buckets if b.axis in axis]
    if severity:
        buckets = [b for b in buckets if b.severity in severity]
    if breached_only:
        buckets = [b for b in buckets if b.breached]
    if min_utilization is not None:
        buckets = [b for b in buckets
                   if b.utilization_pct is not None
                   and b.utilization_pct >= min_utilization]

    if buckets is rep.buckets:
        return rep
    # Recount headline metrics on the filtered set so the UI stays honest.
    return BreachReport(
        as_of=rep.as_of,
        generated_at=rep.generated_at,
        buckets=buckets,
        total_exposure=rep.total_exposure,
        breached_count=sum(1 for b in buckets if b.severity == "red"),
        amber_count=sum(1 for b in buckets if b.severity == "amber"),
        sum_effective_caps=sum(b.effective_cap or 0 for b in buckets) or None,
    )


@app.get("/api/report/summary")
def report_summary(target: Optional[date] = Query(default=None, alias="date")):
    rep = _build_report(target)
    return {
        "as_of": rep.as_of.isoformat(),
        "total_exposure": rep.total_exposure,
        "sum_effective_caps": rep.sum_effective_caps,
        "breached_count": rep.breached_count,
        "amber_count": rep.amber_count,
        "by_axis": aggregator.summarise_by_axis(rep),
    }


@app.get("/api/report/timeseries")
def report_timeseries(
    start: Optional[date] = Query(default=None),
    end: Optional[date] = Query(default=None),
    axis: Optional[Literal["Contraparte", "País", "Tipo",
                            "Tipo de linha", "RAF"]] = None,
    key: Optional[str] = Query(
        default=None,
        description="JSON of the bucket key, e.g. {\"País\":\"Portugal\"}. "
                    "If omitted, returns global aggregates per day.",
    ),
):
    """
    Return one row per available daily limits file with the headline
    utilisation metrics (or, if ``axis``+``key`` are given, the
    utilisation of a specific bucket).
    """
    import json as _json

    files = discover_files()
    if not files:
        return []
    if start:
        files = [f for f in files if f[0] >= start]
    if end:
        files = [f for f in files if f[0] <= end]

    target_key = _json.loads(key) if key else None
    out = []
    for d, _ in files:
        rep = _build_report(d)
        if axis is None or target_key is None:
            out.append({
                "date": d.isoformat(),
                "total_exposure": rep.total_exposure,
                "sum_effective_caps": rep.sum_effective_caps,
                "breached_count": rep.breached_count,
                "amber_count": rep.amber_count,
            })
            continue
        match = next(
            (b for b in rep.buckets
             if b.axis == axis and all(
                 (b.key.get(k) or "").lower() == str(v).lower()
                 for k, v in target_key.items())),
            None,
        )
        out.append({
            "date": d.isoformat(),
            "exposure": match.exposure if match else None,
            "effective_cap": match.effective_cap if match else None,
            "utilization_pct": match.utilization_pct if match else None,
            "severity": match.severity if match else "none",
        })
    return out


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
