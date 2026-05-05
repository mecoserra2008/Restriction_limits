"""
Load the *exposure* side of the dashboard.

The consolidated workbook (file #2) is expected to look exactly like a
Bloomberg metadata dump for a transaction. Real column names vary between
deliveries, so the loader is permissive: it inspects the headers and maps
whatever it can recognise onto :class:`Position`.

Mapping rules (case insensitive, accent-insensitive, partial match):

    TICKER, SECURITY              -> ticker
    ISIN                          -> isin
    CUSIP                         -> cusip
    SECURITY_DES, NAME            -> description
    ISSUER, ISSUER_NAME           -> issuer
    COUNTRY, ISSUE_CNTRY,
        CNTRY_OF_RISK             -> country
    CRNCY, CURRENCY               -> currency
    INDUSTRY_SECTOR, SECTOR       -> industry_sector
    BB_COMPOSITE, RATING          -> bb_composite
    MATURITY, MTY                 -> maturity
    CPN, COUPON                   -> coupon
    AMT_OUTSTANDING, AMT_OS       -> amt_outstanding
    NOTIONAL, FACE, PAR, POSITION -> notional
    MARKET_VALUE, MV, EXPOSURE    -> market_value
    PX_LAST, PRICE                -> px_last
    SOURCE, PLATFORM              -> source
    BOOK, PORTFOLIO               -> book
    COUNTERPARTY, CONTRAPARTE     -> counterparty
    TIPO DE LINHA, LINE_TYPE      -> line_type
    TIPO, LINE_SUBTYPE            -> line_subtype
"""
from __future__ import annotations

import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from ..config import SETTINGS
from ..models import ExposureSnapshot, Position

# Each tuple: (Position attribute, list of header keywords - any match wins)
_FIELD_MAP = [
    ("ticker",           ["ticker", "security"]),
    ("isin",             ["isin"]),
    ("cusip",            ["cusip"]),
    ("description",      ["security_des", "description", "name"]),
    ("issuer",           ["issuer"]),
    ("country",          ["country", "issue_cntry", "cntry_of_risk", "pais"]),
    ("currency",         ["crncy", "currency", "ccy"]),
    ("industry_sector",  ["industry_sector", "sector"]),
    ("bb_composite",     ["bb_composite", "rating"]),
    ("maturity",         ["maturity", "mty"]),
    ("coupon",           ["cpn", "coupon"]),
    ("amt_outstanding",  ["amt_outstanding", "amt_os"]),
    ("notional",         ["notional", "face", "par", "position", "quantity"]),
    ("market_value",     ["market_value", "mv", "exposure", "exposicao"]),
    ("px_last",          ["px_last", "price", "preco"]),
    ("source",           ["source", "platform", "origem"]),
    ("book",             ["book", "portfolio", "carteira"]),
    ("counterparty",     ["counterparty", "contraparte"]),
    ("line_type",        ["tipo de linha", "line_type", "linetype"]),
    ("line_subtype",     ["tipo", "line_subtype", "subtype"]),
]

_NUMERIC_FIELDS = {
    "coupon", "amt_outstanding", "notional", "market_value", "px_last"
}
_DATE_FIELDS = {"maturity"}


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _norm(s: str) -> str:
    return _strip_accents(str(s)).strip().lower()


def _resolve_field_map(columns) -> Dict[str, str]:
    """
    Return ``{position_attr: source_column}``.

    Two-pass to avoid the classic collision where a short keyword (``tipo``)
    matches a longer header (``tipo de linha``) and steals it from the
    correct attribute. Pass 1 only accepts exact-token matches; pass 2
    falls back to substring matches but skips any column already claimed.
    """
    norm_cols = {_norm(c): c for c in columns}
    out: Dict[str, str] = {}
    claimed: set[str] = set()

    def try_match(strict: bool):
        for attr, keywords in _FIELD_MAP:
            if attr in out:
                continue
            for kw in keywords:
                kwn = _norm(kw)
                # exact match always wins
                if kwn in norm_cols and norm_cols[kwn] not in claimed:
                    out[attr] = norm_cols[kwn]
                    claimed.add(norm_cols[kwn])
                    break
                if strict:
                    continue
                # fuzzy: token equality on word boundaries, then substring
                for n, original in norm_cols.items():
                    if original in claimed:
                        continue
                    tokens = n.replace("_", " ").split()
                    if kwn in tokens or kwn in n:
                        out[attr] = original
                        claimed.add(original)
                        break
                if attr in out:
                    break

    try_match(strict=True)
    try_match(strict=False)
    return out


def _to_float(x) -> Optional[float]:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace("\xa0", "").replace(" ", "").rstrip("%")
    if not s:
        return None
    # Portuguese / European thousands+decimal: "1.234.567,89"
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        # Pure "1234,56" -> swap comma for dot
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _to_date(x) -> Optional[date]:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    try:
        return pd.to_datetime(x).date()
    except Exception:
        return None


def load_exposure_file(
    file_path: str | Path | None = None,
    sheet_name: Optional[str] = None,
    as_of: Optional[date] = None,
) -> ExposureSnapshot:
    """Parse the consolidated exposure workbook into an :class:`ExposureSnapshot`."""
    p = Path(file_path or SETTINGS.exposure_file)
    if not p.exists():
        raise FileNotFoundError(
            f"Exposure file not found: {p}. "
            "Set RL_EXPOSURE_FILE to point at the consolidated workbook."
        )

    df = pd.read_excel(
        p, sheet_name=sheet_name or SETTINGS.exposure_sheet or 0,
        engine="openpyxl", dtype=object,
    )
    df.columns = [str(c) for c in df.columns]

    field_map = _resolve_field_map(df.columns)
    if not field_map:
        raise ValueError(
            f"Could not recognise any Bloomberg-style columns in {p.name}. "
            "Check the workbook headers."
        )

    positions: List[Position] = []
    for _, raw in df.iterrows():
        kwargs: Dict[str, object] = {}
        for attr, src in field_map.items():
            val = raw.get(src)
            if val is None or (isinstance(val, float) and pd.isna(val)):
                continue
            if attr in _NUMERIC_FIELDS:
                kwargs[attr] = _to_float(val)
            elif attr in _DATE_FIELDS:
                kwargs[attr] = _to_date(val)
            else:
                kwargs[attr] = str(val).strip()
        if not kwargs:
            continue
        positions.append(Position(**kwargs))

    return ExposureSnapshot(
        as_of=as_of or date.today(),
        source_file=str(p),
        positions=positions,
    )
