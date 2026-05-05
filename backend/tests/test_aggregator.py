from datetime import date

import pytest

from backend.models import ExposureSnapshot, LimitRow, LimitSnapshot, Position
from backend.services.aggregator import (
    _is_empty_row,
    _severity,
    build_report,
    summarise_by_axis,
)


D = date(2026, 5, 5)


def L(**kw) -> LimitRow:
    return LimitRow(as_of=D, **kw)


def P(**kw) -> Position:
    return Position(**kw)


def test_severity_thresholds():
    assert _severity(0, 100) == "green"
    assert _severity(79, 100) == "green"
    assert _severity(80, 100) == "amber"
    assert _severity(99, 100) == "amber"
    assert _severity(100, 100) == "amber"   # exactly at the cap is not yet red
    assert _severity(101, 100) == "red"
    assert _severity(50, None) == "none"


def test_empty_row_is_skipped():
    snap = LimitSnapshot(
        as_of=D, source_file="x",
        rows=[L(), L(pais="Portugal", limite=100.0)],
    )
    expo = ExposureSnapshot(as_of=D, source_file="y", positions=[])
    rep = build_report(snap, expo)
    assert len(rep.buckets) == 1


def test_country_alias_matches_iso_and_pt_name():
    snap = LimitSnapshot(as_of=D, source_file="x",
                         rows=[L(pais="Portugal", limite=1000.0)])
    expo = ExposureSnapshot(as_of=D, source_file="y", positions=[
        P(country="PT", market_value=400.0),
        P(country="portugal", market_value=300.0),
        P(country="ES", market_value=999.0),     # excluded
    ])
    rep = build_report(snap, expo)
    bucket = rep.buckets[0]
    assert bucket.exposure == 700.0
    assert bucket.severity == "green"
    assert bucket.contributing_positions == 2


def test_breach_red_and_breach_amount():
    snap = LimitSnapshot(as_of=D, source_file="x",
                         rows=[L(contraparte="ACME", limite=500.0)])
    expo = ExposureSnapshot(as_of=D, source_file="y", positions=[
        P(counterparty="acme", market_value=600.0),
        P(counterparty="ACME ", market_value=200.0),
    ])
    rep = build_report(snap, expo)
    bucket = rep.buckets[0]
    assert bucket.severity == "red"
    assert bucket.breached
    assert bucket.exposure == 800.0
    assert bucket.breach_amount == 300.0
    assert rep.breached_count == 1


def test_effective_cap_uses_tightest_of_limit_raf():
    snap = LimitSnapshot(as_of=D, source_file="x", rows=[
        L(pais="Portugal", limite=1000.0,
          raf_global=2000.0, raf_individual=400.0),
    ])
    expo = ExposureSnapshot(as_of=D, source_file="y", positions=[
        P(country="PT", market_value=450.0),
    ])
    rep = build_report(snap, expo)
    bucket = rep.buckets[0]
    assert bucket.effective_cap == 400.0
    assert bucket.severity == "red"


def test_market_value_falls_back_to_notional_times_price():
    snap = LimitSnapshot(as_of=D, source_file="x",
                         rows=[L(pais="Portugal", limite=10_000.0)])
    expo = ExposureSnapshot(as_of=D, source_file="y", positions=[
        P(country="PT", notional=10_000.0, px_last=99.5),
    ])
    rep = build_report(snap, expo)
    # 10000 * 99.5/100 = 9950
    assert rep.buckets[0].exposure == pytest.approx(9950.0)


def test_summarise_by_axis_counts_severities():
    snap = LimitSnapshot(as_of=D, source_file="x", rows=[
        L(pais="Portugal", limite=100.0),
        L(pais="Spain", limite=100.0),
        L(contraparte="X", limite=100.0),
    ])
    expo = ExposureSnapshot(as_of=D, source_file="y", positions=[
        P(country="PT", market_value=50.0),    # green
        P(country="ES", market_value=90.0),    # amber
        P(counterparty="X", market_value=200.0),  # red
    ])
    rep = build_report(snap, expo)
    summary = summarise_by_axis(rep)
    assert summary["País"]["green"] == 1
    assert summary["País"]["amber"] == 1
    assert summary["Contraparte"]["red"] == 1
