"""
Pydantic data models exchanged between the backend and the React frontend.

The models mirror the columns of the limits workbook
(Collumns_Restriction_limits.xlsx) plus a small layer that captures the
exposure side coming from Bloomberg / Market Access.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Severity ladder used by the dashboard.
#   green : utilisation <= 80% of the cap
#   amber : 80% < utilisation <= 100%
#   red   : utilisation > 100% (hard breach)
#   none  : no cap defined for the bucket
Severity = Literal["green", "amber", "red", "none"]
AMBER_THRESHOLD = 0.80  # 80% of cap


# ---------------------------------------------------------------------------
# Limits side (Excel #1)
# ---------------------------------------------------------------------------

# Canonical column names of the limits workbook.
LIMIT_COLUMNS = [
    "Contraparte",
    "Tipo de linha",
    "Limite",
    "Utilizado",
    "% utilização",
    "País",
    "Tipo",
    "Numeração Rating Basileia",
    "Limites RAF globais",
    "Limites RAF Individual",
]

# Limit "axes" - the dimensions over which a limit is enforced.
LimitAxis = Literal["Contraparte", "País", "Tipo", "Tipo de linha", "RAF"]


class LimitRow(BaseModel):
    """A single row of the limits workbook (one defined limit)."""

    contraparte: Optional[str] = None
    tipo_de_linha: Optional[str] = Field(default=None, alias="tipo_de_linha")
    limite: Optional[float] = None
    utilizado: Optional[float] = None
    pct_utilizacao: Optional[float] = Field(default=None, alias="pct_utilizacao")
    pais: Optional[str] = None
    tipo: Optional[str] = None
    rating_basileia: Optional[str] = None
    raf_global: Optional[float] = None
    raf_individual: Optional[float] = None
    as_of: Optional[date] = None

    model_config = ConfigDict(populate_by_name=True)


class LimitSnapshot(BaseModel):
    """All limits for a given as-of date."""

    as_of: date
    source_file: str
    rows: List[LimitRow]


# ---------------------------------------------------------------------------
# Exposure side (Excel #2 / Bloomberg metadata)
# ---------------------------------------------------------------------------

class Position(BaseModel):
    """
    A single position. Columns mirror Bloomberg metadata so we can do
    look-ups by ticker / ISIN without translation.
    """

    ticker: Optional[str] = None
    isin: Optional[str] = None
    cusip: Optional[str] = None
    description: Optional[str] = None

    # Static Bloomberg fields
    issuer: Optional[str] = None
    country: Optional[str] = None             # ISSUE_CNTRY / COUNTRY_FULL_NAME
    currency: Optional[str] = None            # CRNCY
    industry_sector: Optional[str] = None     # INDUSTRY_SECTOR
    bb_composite: Optional[str] = None        # BB_COMPOSITE  (rating)
    maturity: Optional[date] = None           # MATURITY
    coupon: Optional[float] = None            # CPN
    amt_outstanding: Optional[float] = None   # AMT_OUTSTANDING

    # Dynamic / position fields
    notional: Optional[float] = None          # face / par held
    market_value: Optional[float] = None      # MV in reporting ccy
    px_last: Optional[float] = None
    source: Optional[Literal["Bloomberg", "MarketAccess", "Manual"]] = None
    book: Optional[str] = None
    counterparty: Optional[str] = None        # maps to "Contraparte"
    line_type: Optional[str] = None           # maps to "Tipo de linha"
    line_subtype: Optional[str] = None        # maps to "Tipo"


class ExposureSnapshot(BaseModel):
    as_of: date
    source_file: str
    positions: List[Position]


# ---------------------------------------------------------------------------
# Aggregated / breach output
# ---------------------------------------------------------------------------

class Bucket(BaseModel):
    """A unique combination of axis values for a given limit."""

    axis: LimitAxis
    key: Dict[str, Optional[str]]
    limit: Optional[float] = None
    raf_global: Optional[float] = None
    raf_individual: Optional[float] = None
    effective_cap: Optional[float] = None  # min(limit, raf_individual, raf_global)
    exposure: float = 0.0
    utilization_pct: Optional[float] = None
    severity: Severity = "none"
    breached: bool = False
    breach_amount: float = 0.0
    contributing_positions: int = 0


class BreachReport(BaseModel):
    as_of: date
    generated_at: datetime
    buckets: List[Bucket]
    total_exposure: float
    breached_count: int
    amber_count: int = 0
    # Sum of effective caps - WARNING: caps overlap across axes (a position
    # counted under Contraparte X may also count under País Y), so this is
    # *not* the headroom. Surface it as informational only.
    sum_effective_caps: Optional[float] = None

    @classmethod
    def empty(cls, as_of: date) -> "BreachReport":
        return cls(
            as_of=as_of,
            generated_at=datetime.utcnow(),
            buckets=[],
            total_exposure=0.0,
            breached_count=0,
            amber_count=0,
        )
