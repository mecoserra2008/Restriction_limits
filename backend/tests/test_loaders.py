from pathlib import Path

import pandas as pd
import pytest

from backend.services.exposure_loader import (
    _resolve_field_map,
    _to_float,
    load_exposure_file,
)
from backend.services.limits_loader import load_limits_file


def test_to_float_handles_pt_format_and_percent():
    assert _to_float("1.234.567,89") == 1234567.89
    assert _to_float("1234,56") == 1234.56
    assert _to_float("15%") == 15.0
    assert _to_float("") is None
    assert _to_float(None) is None
    assert _to_float("not a number") is None


def test_field_map_does_not_let_tipo_steal_tipo_de_linha():
    fm = _resolve_field_map(["Tipo de linha", "Tipo", "TICKER", "MV"])
    assert fm["line_type"] == "Tipo de linha"
    assert fm["line_subtype"] == "Tipo"
    assert fm["ticker"] == "TICKER"
    assert fm["market_value"] == "MV"


def test_field_map_is_accent_and_case_insensitive():
    fm = _resolve_field_map(["PAIS", "Contraparte", "Ticker", "Notional"])
    assert fm["country"] == "PAIS"
    assert fm["counterparty"] == "Contraparte"
    assert fm["notional"] == "Notional"


def test_limits_loader_reads_schema_file_without_rows():
    repo_root = Path(__file__).resolve().parents[2]
    snap = load_limits_file(repo_root / "Collumns_Restriction_limits.xlsx")
    assert snap.rows == []


def test_exposure_loader_round_trip(tmp_path: Path):
    df = pd.DataFrame([
        {"Ticker": "PORTUG 4 25", "ISIN": "PT0001", "Country": "PT",
         "Crncy": "EUR", "Notional": 1_000_000, "Market_Value": 950_000,
         "Counterparty": "ACME", "Tipo de linha": "Governo - OT's",
         "Tipo": "Sovereign", "Maturity": "2030-01-15"},
        {"Ticker": "BUNDES 0 30", "ISIN": "DE0002", "Country": "DE",
         "Crncy": "EUR", "Notional": 500_000, "Market_Value": 480_000,
         "Counterparty": "Bund", "Tipo de linha": "Governo - OT's",
         "Tipo": "Sovereign", "Maturity": "2030-08-15"},
    ])
    p = tmp_path / "exposures.xlsx"
    df.to_excel(p, sheet_name="Exposure", index=False)

    snap = load_exposure_file(p, sheet_name="Exposure")
    assert len(snap.positions) == 2
    pt = snap.positions[0]
    assert pt.ticker == "PORTUG 4 25"
    assert pt.country == "PT"
    assert pt.market_value == 950_000.0
    assert pt.line_type == "Governo - OT's"
    assert pt.line_subtype == "Sovereign"
