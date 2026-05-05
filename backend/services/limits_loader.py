"""
Load the *limits* side of the dashboard from the structured Excel workbook.

The workbook has a fixed schema (see Collumns_Restriction_limits.xlsx):

    Contraparte | Tipo de linha | Limite | Utilizado | % utilização |
    País | Tipo | Numeração Rating Basileia | Limites RAF globais |
    Limites RAF Individual

Every monthly file lives at:

    <BASE>/<YYYY>/<MMM>/<DD-MM-YYYY>.xlsx

so the date can be inferred straight from the filename.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from ..config import SETTINGS
from ..models import LIMIT_COLUMNS, LimitRow, LimitSnapshot

# canonical column -> attribute on LimitRow
_COL_MAP: Dict[str, str] = {
    "Contraparte": "contraparte",
    "Tipo de linha": "tipo_de_linha",
    "Limite": "limite",
    "Utilizado": "utilizado",
    "% utilização": "pct_utilizacao",
    "País": "pais",
    "Tipo": "tipo",
    "Numeração Rating Basileia": "rating_basileia",
    "Limites RAF globais": "raf_global",
    "Limites RAF Individual": "raf_individual",
}

_DATE_RE = re.compile(r"^(\d{2})-(\d{2})-(\d{4})\.xlsx$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    return str(s).strip().lower()


def _resolve_columns(df: pd.DataFrame) -> Dict[str, str]:
    """Map every canonical column name to the actual column in the file
    (tolerant to small renames / accent loss)."""
    norm = {_norm(c): c for c in df.columns}
    out: Dict[str, str] = {}
    for canon in LIMIT_COLUMNS:
        if _norm(canon) in norm:
            out[canon] = norm[_norm(canon)]
            continue
        # fuzzy: substring match without accents
        target = _norm(canon).replace("ç", "c").replace("ã", "a")
        for n, original in norm.items():
            cand = n.replace("ç", "c").replace("ã", "a")
            if target in cand or cand in target:
                out[canon] = original
                break
    return out


def _to_float(x) -> Optional[float]:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace("\xa0", "").replace(" ", "")
    if not s:
        return None
    # Portuguese number format: "1.234.567,89"
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    s = s.rstrip("%")
    try:
        return float(s)
    except ValueError:
        return None


def _date_from_filename(p: Path) -> Optional[date]:
    m = _DATE_RE.match(p.name)
    if not m:
        return None
    dd, mm, yyyy = m.groups()
    try:
        return date(int(yyyy), int(mm), int(dd))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_limits_file(
    file_path: str | Path, sheet_name: Optional[str] = None
) -> LimitSnapshot:
    """Parse a single limits workbook into a :class:`LimitSnapshot`."""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Limits file not found: {p}")

    df = pd.read_excel(p, sheet_name=sheet_name or 0, engine="openpyxl",
                       dtype=object)
    df.columns = [str(c) for c in df.columns]

    cols = _resolve_columns(df)
    if not cols:
        raise ValueError(
            f"No known columns recognised in {p.name}; expected {LIMIT_COLUMNS}"
        )

    as_of = _date_from_filename(p) or date.today()

    rows: List[LimitRow] = []
    for _, raw in df.iterrows():
        kwargs: Dict[str, object] = {"as_of": as_of}
        for canon, attr in _COL_MAP.items():
            if canon not in cols:
                continue
            val = raw.get(cols[canon])
            if attr in {"limite", "utilizado", "pct_utilizacao",
                        "raf_global", "raf_individual"}:
                kwargs[attr] = _to_float(val)
            else:
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    kwargs[attr] = None
                else:
                    kwargs[attr] = str(val).strip()
        # Skip empty rows
        if all(v in (None, "", as_of) for v in kwargs.values()):
            continue
        rows.append(LimitRow(**kwargs))

    return LimitSnapshot(as_of=as_of, source_file=str(p), rows=rows)


def discover_files(
    base_dir: Path | None = None, year: Optional[int] = None
) -> List[Tuple[date, Path]]:
    """Walk the network share and return ``(date, path)`` for every daily file."""
    base = Path(base_dir or SETTINGS.limits_base_dir)
    if not base.exists():
        return []

    years = [base / str(year)] if year else [
        d for d in base.iterdir() if d.is_dir() and d.name.isdigit()
    ]
    out: List[Tuple[date, Path]] = []
    for year_dir in years:
        if not year_dir.exists():
            continue
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            for f in month_dir.iterdir():
                if not f.is_file():
                    continue
                d = _date_from_filename(f)
                if d:
                    out.append((d, f))
    out.sort(key=lambda t: t[0])
    return out


def latest_snapshot(base_dir: Path | None = None) -> Optional[LimitSnapshot]:
    files = discover_files(base_dir)
    if not files:
        return None
    _, latest = files[-1]
    return load_limits_file(latest)


def snapshot_for_date(
    target: date, base_dir: Path | None = None
) -> Optional[LimitSnapshot]:
    for d, f in discover_files(base_dir):
        if d == target:
            return load_limits_file(f)
    return None
