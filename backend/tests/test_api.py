"""End-to-end smoke test of the FastAPI app."""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend import config as cfg
from backend.app import app
from backend.services.cache import CACHE


@pytest.fixture
def configured(tmp_path, monkeypatch):
    """Point the backend at a synthetic limits + exposure pair."""
    # --- Limits file under <base>/<year>/<month>/DD-MM-YYYY.xlsx
    base = tmp_path / "share"
    month_dir = base / "2026" / "Maio"
    month_dir.mkdir(parents=True)
    limits_df = pd.DataFrame([
        {"Contraparte": None, "Tipo de linha": None, "Limite": 1_000_000,
         "Utilizado": None, "% utilização": None, "País": "Portugal",
         "Tipo": None, "Numeração Rating Basileia": None,
         "Limites RAF globais": None, "Limites RAF Individual": None},
        {"Contraparte": "ACME", "Tipo de linha": None, "Limite": 500_000,
         "Utilizado": None, "% utilização": None, "País": None,
         "Tipo": None, "Numeração Rating Basileia": None,
         "Limites RAF globais": None, "Limites RAF Individual": None},
    ])
    limits_path = month_dir / "05-05-2026.xlsx"
    limits_df.to_excel(limits_path, index=False)

    # --- Exposure file
    expo_df = pd.DataFrame([
        {"Ticker": "X", "Country": "PT", "Counterparty": "ACME",
         "Market_Value": 600_000},
        {"Ticker": "Y", "Country": "PT", "Counterparty": "Other",
         "Market_Value": 200_000},
    ])
    expo_path = tmp_path / "exposure.xlsx"
    expo_df.to_excel(expo_path, sheet_name="Exposure", index=False)

    monkeypatch.setattr(cfg.SETTINGS, "limits_base_dir", base)
    monkeypatch.setattr(cfg.SETTINGS, "exposure_file", expo_path)
    monkeypatch.setattr(cfg.SETTINGS, "exposure_sheet", "Exposure")
    CACHE.invalidate()
    yield
    CACHE.invalidate()


def test_health(configured):
    client = TestClient(app)
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"


def test_limits_dates_lists_synthetic_file(configured):
    client = TestClient(app)
    res = client.get("/api/limits/dates")
    assert res.status_code == 200
    body = res.json()
    assert any(d["date"] == "2026-05-05" for d in body)


def test_report_buckets_and_severities(configured):
    client = TestClient(app)
    res = client.get("/api/report")
    assert res.status_code == 200
    body = res.json()
    by_axis = {b["axis"]: b for b in body["buckets"]}
    assert by_axis["País"]["exposure"] == 800_000.0
    assert by_axis["País"]["severity"] == "amber"  # 80% of 1m
    assert by_axis["Contraparte"]["severity"] == "red"
    assert body["breached_count"] == 1
    assert body["amber_count"] == 1


def test_report_filters(configured):
    client = TestClient(app)
    res = client.get("/api/report", params={"breached_only": "true"})
    assert res.status_code == 200
    buckets = res.json()["buckets"]
    assert len(buckets) == 1
    assert buckets[0]["axis"] == "Contraparte"


def test_summary_endpoint(configured):
    client = TestClient(app)
    res = client.get("/api/report/summary")
    assert res.status_code == 200
    body = res.json()
    assert body["breached_count"] == 1
    assert "País" in body["by_axis"]


def test_timeseries(configured):
    client = TestClient(app)
    res = client.get("/api/report/timeseries")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["date"] == "2026-05-05"
    assert body[0]["breached_count"] == 1
