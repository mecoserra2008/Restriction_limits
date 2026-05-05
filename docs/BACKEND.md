# Restriction Limits — Backend

Python service that reads two Excel workbooks, consolidates them, and
serves a JSON API for the dashboard.

## Architecture

```
                ┌────────────────────────┐
 limits .xlsx ─►│  limits_loader         │
 (file #1)      │  (one file per day)    │
                └──────────┬─────────────┘
                           │ LimitSnapshot
                           ▼
                ┌────────────────────────┐
                │  aggregator            │── BreachReport ──► /api/report
                └──────────▲─────────────┘
                           │ ExposureSnapshot
                ┌──────────┴─────────────┐
exposure .xlsx ►│  exposure_loader       │
 (file #2)      │  Bloomberg-style cols  │
                └──────────▲─────────────┘
                           │ optional enrichment
                ┌──────────┴─────────────┐
                │  bloomberg_client      │── pdblp / blpapi
                │  (Desktop API)         │
                └────────────────────────┘
```

| Module | Responsibility |
| --- | --- |
| `backend/config.py` | Settings (paths, ports, BBG host); env-var overridable. |
| `backend/models.py` | Pydantic schemas: `LimitRow`, `LimitSnapshot`, `Position`, `ExposureSnapshot`, `Bucket`, `BreachReport`. |
| `backend/services/limits_loader.py` | Walk the share `M:\Mapas Gestao\Linhas - Risco de Credito\<YYYY>\<MMM>\<DD-MM-YYYY>.xlsx`, parse, normalise, infer date from filename. |
| `backend/services/exposure_loader.py` | Read the consolidated workbook (Bloomberg metadata + Market Access). Header detection is fuzzy and accent-insensitive. |
| `backend/services/aggregator.py` | For each limit row: pick its axis (`Contraparte`, `País`, `Tipo`, `Tipo de linha`, `RAF`), match the positions, compare against the tightest cap (`Limite`, `RAF Individual`, `RAF Global`), flag breaches. |
| `backend/services/bloomberg_client.py` | Optional `pdblp.BCon` wrapper for `ref()` / `bdh()` enrichment. |
| `backend/services/cache.py` | mtime + TTL cache to avoid reparsing Excel on every request. |
| `backend/app.py` | FastAPI app + routes + CORS for the React frontend. |
| `backend/launcher.py` | Desktop-friendly entry point used by PyInstaller. |

## Limits workbook (file #1)

Columns expected (verified against `Collumns_Restriction_limits.xlsx`):

```
Contraparte | Tipo de linha | Limite | Utilizado | % utilização |
País | Tipo | Numeração Rating Basileia |
Limites RAF globais | Limites RAF Individual
```

Every row defines a limit. The aggregator decides the axis from which
non-empty columns the row contains:

* `Contraparte` set → counterparty limit
* `País` set → country limit
* `Tipo` set → instrument-type limit
* `Tipo de linha` set → line-type limit
* otherwise the row is treated as a portfolio-wide RAF limit

When several axes are set on the same row the limit is enforced as a
conjunction (e.g. *Contraparte X in País Y*).

## Exposure workbook (file #2)

We do not have the file yet, but its columns are expected to mirror the
Bloomberg metadata of a transaction. The loader recognises (case- and
accent-insensitive):

| Position attribute | Bloomberg/Market Access column |
| --- | --- |
| `ticker` | `TICKER`, `SECURITY` |
| `isin` | `ISIN`, `ID_ISIN` |
| `country` | `CNTRY_OF_RISK`, `ISSUE_CNTRY`, `País` |
| `currency` | `CRNCY`, `CURRENCY` |
| `industry_sector` | `INDUSTRY_SECTOR`, `SECTOR` |
| `bb_composite` | `BB_COMPOSITE`, `RATING` |
| `maturity` | `MATURITY`, `MTY` |
| `coupon` | `CPN`, `COUPON` |
| `amt_outstanding` | `AMT_OUTSTANDING`, `AMT_OS` |
| `notional` | `NOTIONAL`, `FACE`, `PAR`, `POSITION`, `QUANTITY` |
| `market_value` | `MARKET_VALUE`, `MV`, `EXPOSURE`, `Exposição` |
| `px_last` | `PX_LAST`, `PRICE` |
| `source` | `SOURCE`, `PLATFORM` (Bloomberg / MarketAccess / Manual) |
| `counterparty` | `COUNTERPARTY`, `Contraparte` |
| `line_type` | `Tipo de linha`, `LINE_TYPE` |
| `line_subtype` | `Tipo`, `LINE_SUBTYPE` |

Add columns over time — the loader will pick them up if the header
matches one of the keywords above. Anything unrecognised is silently
ignored.

## Configuration (env vars)

| Variable | Default | Purpose |
| --- | --- | --- |
| `RL_LIMITS_BASE_DIR` | `M:\Mapas Gestao\Linhas - Risco de Credito` | Root of the daily limits files. |
| `RL_EXPOSURE_FILE` | `~/exposures/consolidated_exposure.xlsx` | Consolidated Bloomberg + Market Access workbook. |
| `RL_EXPOSURE_SHEET` | `Exposure` | Sheet name (or numeric index). |
| `RL_BBG_HOST` / `RL_BBG_PORT` | `localhost:8194` | Bloomberg Desktop API endpoint. |
| `RL_BBG_ENABLED` | `1` | Set `0` when running on a machine without the terminal. |
| `RL_API_HOST` / `RL_API_PORT` | `127.0.0.1:8765` | FastAPI bind. |
| `RL_CORS_ORIGINS` | `http://localhost:5173,...,tauri://localhost` | Browser origins allowed to call the API. |
| `RL_CACHE_TTL` | `300` | Seconds to keep parsed Excel data in memory. |

## Running

```
pip install -r backend/requirements.txt
python -m backend.app           # dev
python -m backend.launcher      # opens browser too (used by the desktop app)
```

OpenAPI docs: <http://127.0.0.1:8765/docs>.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Liveness + effective configuration. |
| GET | `/api/limits/dates` | List every daily file discovered on the share. |
| GET | `/api/limits/latest` | Most recent `LimitSnapshot`. |
| GET | `/api/limits/{date}` | Snapshot for a given ISO date. |
| GET | `/api/exposure` | `ExposureSnapshot` from the consolidated workbook. |
| GET | `/api/report?date=YYYY-MM-DD` | Full `BreachReport`. |
| GET | `/api/report/summary` | Roll-up by axis (cards on the dashboard). |
| POST | `/api/cache/invalidate` | Force Excel re-parse. |
