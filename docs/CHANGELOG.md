# Changelog

## v0.2.0 — quality pass

### Bug fixes
* `exposure_loader._to_float`: fixed a tortured boolean
  (`not s.replace(",", "").isdigit() is False`) that always returned
  the wrong branch. European-format numbers (`1.234,56`) and
  percentage strings (`15%`) now parse correctly.
* `exposure_loader._resolve_field_map`: short keywords (`tipo`) no
  longer steal longer-headed columns (`Tipo de linha`). The matcher
  is now two-pass (exact tokens first, fuzzy fallback) and tracks
  which columns have already been claimed.
* `models.LimitRow`: switched from the deprecated Pydantic v1
  `class Config` to `model_config = ConfigDict(...)`.

### New behaviour
* **Severity tiers** on every bucket — `green` ≤ 80 %, `amber` 80–100 %,
  `red` > 100 %, `none` when no cap is defined. Threshold lives in
  `backend.models.AMBER_THRESHOLD`.
* **Effective cap** surfaced explicitly on each bucket (the tightest
  of `Limite`, `RAF Individual`, `RAF Global`).
* **Identifier canonicalisation** (`backend/services/normalize.py`):
  `PT` ≡ `PRT` ≡ `Portugal` ≡ `portugal`. ISO-2 / ISO-3 / English /
  Portuguese names of the common European sovereigns plus US/UK/BR/CH
  are pre-loaded; unknown values fall back to lowercase + accent strip.
* **Filterable `/api/report`**: `axis`, `severity`, `breached_only`,
  `min_utilization` query params (combinable; counts are recomputed
  on the filtered set).
* **`/api/report/timeseries`**: per-day headline metrics, or the
  utilisation history of one specific bucket.
* **Empty-row skip** in the aggregator.
* **`BreachReport.amber_count`** and `sum_effective_caps` (with a
  doc-comment warning that overlapping caps mean it is informational,
  not headroom).
* **Tauri CORS scheme variants** (`http://tauri.localhost`,
  `https://tauri.localhost`) added so the WebView2 build works on
  Windows / Linux / macOS without further config.

### Tests
* New `backend/tests/` suite (21 tests, ~1 s):
  * `test_normalize.py` — country aliases + accent stripping.
  * `test_aggregator.py` — severity ladder, country aliasing, breach
    arithmetic, RAF tightness, market_value/notional fallback.
  * `test_loaders.py` — float parsing, field-map collision, schema
    workbook round trip, exposure round trip.
  * `test_api.py` — full FastAPI round trip with a synthetic limits
    file laid out in the expected `<base>/<year>/<month>/DD-MM-YYYY.xlsx`
    structure.

### Packaging
* `packaging/RestrictionLimits.spec` — PyInstaller spec that bundles
  the backend, the React `dist/`, and the icon.
* `packaging/RestrictionLimits.iss` — Inno Setup script that produces a
  per-user installer (no admin), with Start-menu and optional desktop
  shortcut.
* `frontend/README.md` — suggested Vite + React + TS layout, severity
  colour key, endpoint cheat-sheet.

## v0.1.0 — initial scaffold

* `backend/`: FastAPI service, Pydantic models, limits + exposure
  loaders, aggregator, optional Bloomberg client, mtime+TTL Excel
  cache, env-overridable config, desktop launcher.
* `docs/BACKEND.md`, `docs/REACT_DESKTOP_INTEGRATION.md`.
