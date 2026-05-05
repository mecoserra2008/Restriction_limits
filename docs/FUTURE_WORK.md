# Future work / known gaps

A running backlog of things that are intentionally **not** done in the
current scaffold so the next pass can pick them up without re-deriving
the context.

## Data plumbing

* **Multiple exposure files.** Today `RL_EXPOSURE_FILE` points at a
  single workbook. When desks split positions across books, accept a
  glob (`RL_EXPOSURE_FILES=...book1.xlsx,book2.xlsx`) and concatenate
  in `exposure_loader`.
* **In-flight reconciliation.** Bloomberg + Market Access can have
  *the same trade twice* with slightly different MV. Add a duplicate
  detector keyed on `(isin, book, trade_date)` and surface mismatches
  as a separate dashboard tile.
* **FX normalisation.** Exposures arrive in many currencies. The
  current aggregator sums them blindly. Add a `report_ccy`
  configuration plus a daily FX file (Bloomberg `BDP` `PX_LAST` on
  EURUSD, EURGBP, …) and convert on the way in.
* **Trade-date as-of.** Each `Position` should carry the trade's
  effective date so we can replay a *T-1* report after a late book
  update.

## Limit semantics

* **Compound limits.** A row with both `Contraparte` and `País` is
  treated as a conjunction. Some desks use *the most restrictive*
  semantics (whichever cap is hit first wins). Make this configurable
  per `Tipo de linha`.
* **Rating-bucket limits.** `Numeração Rating Basileia` is parsed but
  not used in the matcher. Add `rating_basileia` matching once the
  exposure file standardises that column.
* **Soft vs hard caps.** Today every cap is hard. Some firms run a
  soft (warning) and a hard (block) cap. Extend `LimitRow` with
  `limite_soft` / `limite_hard` and adjust `_severity`.
* **RAF-utilisation rebalancing.** The RAF caps are global. When a new
  position is added we should *project* the breach instead of waiting
  for tomorrow's file. Add a `POST /api/whatif` endpoint that takes a
  hypothetical `Position` and returns the resulting `BreachReport`.

## Bloomberg

* **B-PIPE / SAPI authentication.** `BloombergClient._ensure()` only
  speaks to the Desktop API. Add an `Identity`-based auth path for
  shared servers.
* **Field caching.** Static fields rarely change. Persist `ref()`
  results in a local SQLite (e.g. via `diskcache`) keyed by
  `(ticker, field, asof_date)` to stay under the SAPI volume cap.
* **Streaming subscriptions.** `MarketDataRequest` would let the
  dashboard react to price moves in real time. Wire it through a
  WebSocket endpoint (`/ws/positions`) and a `useWebSocket` hook on
  the React side.
* **CDS curves.** `Universe_construction.py` already pulls CDS
  spreads. Once the consolidated workbook includes a CDS column,
  extend `aggregator.build_report` with a credit-spread limit axis.

## UI / UX

* **Drill-down.** Clicking a bucket in the React table should open a
  panel listing the contributing positions. Backend already exposes
  the `Position` rows; the UI just needs `/api/exposure?bucket=...`
  filter parameters (axis + key) — analogue of the report filters.
* **Export.** A "Download Excel" button that renders the current
  filtered report through `pandas.ExcelWriter`. Expose at
  `/api/report.xlsx`.
* **Audit trail.** Persist every breach overnight in a small SQLite
  next to the cache so we can answer "when did this limit first
  break?".

## Packaging

* **Code signing.** The unsigned `.exe` triggers SmartScreen on bank
  laptops. Once we have a code-signing certificate, add `signtool` to
  the PyInstaller post-build step.
* **Auto-update.** For Tauri, enable the built-in updater pointing at
  an internal HTTPS share. For PyInstaller, wrap the launcher with a
  small "check for newer version on startup" probe.
* **Service mode.** Some users want the backend to run on login, not
  on click. Add a Windows scheduled task (or a per-user service via
  `nssm`) that starts `RestrictionLimits.exe --headless` at logon.

## Testing

* **Property tests** for `_to_float` (random PT / EN number formats).
* **Schema diffing** test that fails CI if the limits workbook gains
  a column we do not handle.
* **End-to-end UI test** with Playwright once the React app exists.
