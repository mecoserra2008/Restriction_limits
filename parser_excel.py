from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
from dateutil.parser import parse as parse_date
import json
import sys
import re

CHARACTERISTIC_CANDIDATES = [
    "Contraparte", "Tipo de linha", "País", "Numeração Rating Basileia", 
    "Limites RAF globais", "Limites RAF Individual", "Limite"
]

DATE_CANDIDATES = [
    "Date", "Data", "EffectiveDate", "Effective Date", "Timestamp", "Datetime", "DateTime"
]

LIMIT_CANDIDATES = [
    "Limite", "Limit", "Limite RAF", "Limit Value", "Value"
]

BASE_DIR = Path(r"M:\Mapas Gestao\Linhas - Risco de Credito")

# --- Utility functions ---

def normalize_col(col: str) -> str:
    return col.strip().lower()


def find_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    norm_map = {normalize_col(c): c for c in df.columns}
    for cand in candidates:
        nc = normalize_col(cand)
        if nc in norm_map:
            return norm_map[nc]
    for col in df.columns:
        for cand in candidates:
            if cand.strip().lower() in normalize_col(col):
                return col
    return None


def detect_date_column(df: pd.DataFrame) -> Optional[str]:
    col = find_column(df, DATE_CANDIDATES)
    if col:
        return col
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            return c
        sample = df[c].dropna().astype(str).head(10).tolist()
        parsed = 0
        for s in sample:
            try:
                parse_date(s)
                parsed += 1
            except Exception:
                pass
        if parsed >= max(1, len(sample) // 2):
            return c
    return None


def detect_limit_column(df: pd.DataFrame) -> Optional[str]:
    col = find_column(df, LIMIT_CANDIDATES)
    if col:
        return col
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols:
        best_col, best_count = None, 0
        for c in df.columns:
            coerced = pd.to_numeric(df[c], errors="coerce")
            count = coerced.notna().sum()
            if count > best_count:
                best_count = count
                best_col = c
        return best_col
    for c in numeric_cols:
        if "limit" in normalize_col(c) or "limite" in normalize_col(c):
            return c
    return numeric_cols[0]


def build_characteristic_key(row: pd.Series, characteristic_cols: List[str]) -> Tuple[Tuple[str, Any], ...]:
    pairs = []
    for c in characteristic_cols:
        val = row.get(c, None)
        if pd.isna(val):
            val = None
        pairs.append((c, val))
    return tuple(pairs)


# --- Main parsing function ---

def parse_excel_to_restriction_set(
    file_path: str,
    sheet_name: Optional[str] = None,
    explicit_characteristics: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    df = pd.read_excel(p, sheet_name=sheet_name, engine="openpyxl", dtype=object)
    df.columns = [str(c) for c in df.columns]

    date_col = detect_date_column(df)
    limit_col = detect_limit_column(df)

    if explicit_characteristics:
        characteristic_cols = [c for c in explicit_characteristics if c in df.columns]
    else:
        exclude = set()
        if date_col:
            exclude.add(date_col)
        if limit_col:
            exclude.add(limit_col)
        for name in ["Utilizado", "% utilização", "% utilizacao", "Utilization", "Utilizado (%)", "Used"]:
            for col in df.columns:
                if normalize_col(name) == normalize_col(col) or name.strip().lower() in normalize_col(col):
                    exclude.add(col)
        found = []
        for cand in CHARACTERISTIC_CANDIDATES:
            for col in df.columns:
                if normalize_col(cand) == normalize_col(col) or cand.strip().lower() in normalize_col(col):
                    if col not in exclude and col not in found:
                        found.append(col)
        if not found:
            characteristic_cols = [c for c in df.columns if c not in exclude]
        else:
            extras = [c for c in df.columns if c not in exclude and c not in found and not pd.api.types.is_numeric_dtype(df[c])]
            characteristic_cols = found + extras

    if not characteristic_cols:
        characteristic_cols = [c for c in df.columns if c not in {date_col, limit_col}]

    if date_col:
        try:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        except Exception:
            df[date_col] = df[date_col].astype(str).apply(lambda s: pd.to_datetime(s, errors="coerce"))

    groups = {}
    for idx, row in df.iterrows():
        key = build_characteristic_key(row, characteristic_cols)

        if date_col:
            dt = row.get(date_col)
            if pd.isna(dt):
                dt_val = None
            else:
                try:
                    dt_val = pd.to_datetime(dt).isoformat()
                except Exception:
                    dt_val = str(dt)
        else:
            dt_val = f"row-{idx}"

        limit_val = None
        if limit_col:
            raw = row.get(limit_col)
            try:
                if pd.isna(raw):
                    limit_val = None
                else:
                    limit_val = float(raw)
            except Exception:
                s = str(raw).replace(",", "").replace(" ", "")
                try:
                    limit_val = float(s)
                except Exception:
                    limit_val = None

        entry = {"date": dt_val, "limit": limit_val, "row_index": int(idx)}
        groups.setdefault(key, []).append(entry)

    restriction_set = []
    for key, history in groups.items():
        characteristics = {k: v for (k, v) in key}

        def sort_key(h):
            d = h["date"]
            if d is None:
                return pd.Timestamp.max
            if isinstance(d, str) and d.startswith("row-"):
                return int(d.split("-", 1)[1])
            try:
                return pd.to_datetime(d)
            except Exception:
                return pd.Timestamp.max

        history_sorted = sorted(history, key=sort_key)
        history_clean = [{"date": h["date"], "limit": h["limit"]} for h in history_sorted]
        restriction_set.append({"characteristics": characteristics, "history": history_clean})

    return restriction_set



def discover_2026_files() -> List[Tuple[str, Path]]:
    year_dir = BASE_DIR / "2026"
    if not year_dir.exists():
        raise FileNotFoundError("Year folder 2026 not found.")

    month_files = []

    date_pattern = re.compile(r"^\d{2}-\d{2}-\d{4}\.xlsx$")

    for month_dir in sorted(year_dir.iterdir()):
        if not month_dir.is_dir():
            continue

        for f in month_dir.iterdir():
            if f.is_file() and date_pattern.match(f.name):
                month_files.append((month_dir.name, f))

    return month_files


def parse_all_2026():
    month_files = discover_2026_files()
    results = []

    for month_name, file_path in month_files:
        print(f"Parsing {file_path} ...")
        try:
            restriction_set = parse_excel_to_restriction_set(str(file_path))
            results.append({
                "month": month_name,
                "file": str(file_path),
                "restriction_set": restriction_set
            })
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")

    return results


# Example

def main():
    # If user provides a file manually, keep original behavior
    if len(sys.argv) >= 2:
        file_path = sys.argv[1]
        sheet = sys.argv[2] if len(sys.argv) > 2 else None
        restriction_set = parse_excel_to_restriction_set(file_path, sheet_name=sheet)
        print(json.dumps(restriction_set[:3], indent=2, ensure_ascii=False))
        return

    # Otherwise parse all DD-MM-YYYY files inside 2026
    print("No file provided. Parsing all DD-MM-YYYY Excel files inside 2026...")
    all_data = parse_all_2026()

    with open("all_limits_2026.json", "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)

    print("Finished parsing all files for 2026.")


if __name__ == "__main__":
    main()
