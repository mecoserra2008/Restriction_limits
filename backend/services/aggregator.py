"""
Combine limits and exposures into a breach report.

For every limit row defined in the limits workbook we identify the axis
that the limit applies to (Contraparte, País, Tipo, Tipo de linha, RAF)
and aggregate the matching positions from the exposure snapshot. A breach
is flagged whenever the aggregated exposure exceeds the limit (or, when
applicable, the RAF cap).

The matching rules are intentionally explicit:

* A limit on **Contraparte** applies to every position with the same
  ``counterparty`` value.
* A limit on **País** applies to every position whose ``country``
  matches.
* A limit on **Tipo** / **Tipo de linha** applies to every position with
  the same ``line_subtype`` / ``line_type`` value.
* A limit on **RAF** applies portfolio-wide using ``raf_global`` /
  ``raf_individual``.

When several axes are populated on the same row (e.g. a limit defined for
"Contraparte X in País Y") all of them must match.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from ..models import (
    AMBER_THRESHOLD,
    Bucket,
    BreachReport,
    ExposureSnapshot,
    LimitRow,
    LimitSnapshot,
    Position,
    Severity,
)
from .normalize import canonical_country, canonical_text


def _exposure_value(p: Position) -> float:
    """Return the canonical exposure metric for a single position."""
    if p.market_value is not None:
        return float(p.market_value)
    if p.notional is not None and p.px_last is not None:
        return float(p.notional) * float(p.px_last) / 100.0
    if p.notional is not None:
        return float(p.notional)
    return 0.0


def _row_axes(row: LimitRow) -> Tuple[str, Dict[str, Optional[str]]]:
    """Decide which axis a limit row enforces and build its key."""
    key: Dict[str, Optional[str]] = {}
    if row.contraparte:
        key["Contraparte"] = row.contraparte
    if row.pais:
        key["País"] = row.pais
    if row.tipo:
        key["Tipo"] = row.tipo
    if row.tipo_de_linha:
        key["Tipo de linha"] = row.tipo_de_linha
    if not key and (row.raf_global is not None or row.raf_individual is not None):
        return "RAF", {"scope": "portfolio"}
    if not key:
        return "RAF", {"scope": "unspecified"}
    # Prefer the most specific axis as the primary label
    for axis in ("Contraparte", "Tipo", "Tipo de linha", "País"):
        if axis in key:
            return axis, key
    return "País", key


def _matches(pos: Position, key: Dict[str, Optional[str]]) -> bool:
    for axis, expected in key.items():
        if expected is None:
            continue
        actual: Optional[str]
        if axis == "Contraparte":
            actual = pos.counterparty
            if canonical_text(actual) != canonical_text(expected):
                return False
            continue
        if axis == "País":
            if canonical_country(pos.country) != canonical_country(expected):
                return False
            continue
        if axis == "Tipo":
            actual = pos.line_subtype
        elif axis == "Tipo de linha":
            actual = pos.line_type
        else:
            return True  # RAF / unspecified -> always matches
        if canonical_text(actual) != canonical_text(expected):
            return False
    return True


def _severity(exposure: float, cap: Optional[float]) -> Severity:
    if cap is None:
        return "none"
    if exposure > cap:
        return "red"
    if cap > 0 and (exposure / cap) >= AMBER_THRESHOLD:
        return "amber"
    return "green"


def _is_empty_row(row: LimitRow) -> bool:
    return all(v is None or v == "" for v in (
        row.contraparte, row.pais, row.tipo, row.tipo_de_linha,
        row.limite, row.raf_global, row.raf_individual,
    ))


def build_report(
    limits: LimitSnapshot,
    exposures: ExposureSnapshot,
) -> BreachReport:
    buckets: List[Bucket] = []
    breached = 0
    amber = 0
    total_exposure = sum(_exposure_value(p) for p in exposures.positions)
    sum_caps = 0.0
    has_total = False

    for row in limits.rows:
        if _is_empty_row(row):
            continue

        axis, key = _row_axes(row)
        matched = [p for p in exposures.positions if _matches(p, key)]
        exp_value = sum(_exposure_value(p) for p in matched)

        # Effective cap: tightest of (Limite, RAF individual, RAF global)
        caps = [c for c in (row.limite, row.raf_individual, row.raf_global)
                if c is not None]
        cap = min(caps) if caps else None

        utilization = (exp_value / cap * 100.0) if cap else None
        severity = _severity(exp_value, cap)
        is_breach = severity == "red"
        breach_amount = max(0.0, exp_value - cap) if cap else 0.0

        if cap is not None:
            sum_caps += cap
            has_total = True
        if severity == "red":
            breached += 1
        elif severity == "amber":
            amber += 1

        buckets.append(Bucket(
            axis=axis,            # type: ignore[arg-type]
            key=key,
            limit=row.limite,
            raf_global=row.raf_global,
            raf_individual=row.raf_individual,
            effective_cap=cap,
            exposure=exp_value,
            utilization_pct=utilization,
            severity=severity,
            breached=is_breach,
            breach_amount=breach_amount,
            contributing_positions=len(matched),
        ))

    return BreachReport(
        as_of=limits.as_of,
        generated_at=datetime.utcnow(),
        buckets=buckets,
        total_exposure=total_exposure,
        breached_count=breached,
        amber_count=amber,
        sum_effective_caps=sum_caps if has_total else None,
    )


def summarise_by_axis(report: BreachReport) -> Dict[str, Dict[str, float]]:
    """Quick roll-up used by the dashboard cards."""
    out: Dict[str, Dict[str, float]] = {}
    for b in report.buckets:
        bucket = out.setdefault(b.axis, {
            "exposure": 0.0, "limits": 0,
            "green": 0, "amber": 0, "red": 0, "no_cap": 0,
        })
        bucket["exposure"] += b.exposure
        bucket["limits"] += 1
        if b.severity == "red":
            bucket["red"] += 1
        elif b.severity == "amber":
            bucket["amber"] += 1
        elif b.severity == "green":
            bucket["green"] += 1
        else:
            bucket["no_cap"] += 1
    return out
