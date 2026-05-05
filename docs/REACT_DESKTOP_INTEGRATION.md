# Connecting the React frontend to the Python backend

This document explains how to:

1. Talk to the FastAPI backend from a ReactJS app.
2. Package both halves as a single double-clickable desktop application
   that ships with an icon on the user's desktop / Start menu.
3. Stay within typical bank-laptop download restrictions (no admin
   rights, restricted package managers, no Docker).

---

## 1. Calling the backend from React

The backend speaks plain JSON over HTTP, so any HTTP client works. The
default development URL is `http://127.0.0.1:8765`.

### 1.1 Vite + React (recommended dev setup)

```bash
# In a separate folder, e.g. ./frontend
npm create vite@latest restriction-limits-ui -- --template react-ts
cd restriction-limits-ui
npm install
```

Add a thin API wrapper:

```ts
// src/api.ts
const BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8765";

export async function getReport(date?: string) {
  const url = new URL(`${BASE}/api/report`);
  if (date) url.searchParams.set("date", date);
  const res = await fetch(url, { credentials: "omit" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getLimitDates() {
  const res = await fetch(`${BASE}/api/limits/dates`);
  return res.json();
}

export async function getSummary(date?: string) {
  const url = new URL(`${BASE}/api/report/summary`);
  if (date) url.searchParams.set("date", date);
  return (await fetch(url)).json();
}
```

Use it from a component:

```tsx
import { useEffect, useState } from "react";
import { getReport } from "./api";

export function Dashboard() {
  const [report, setReport] = useState<any>(null);
  useEffect(() => { getReport().then(setReport); }, []);
  if (!report) return <p>Loading…</p>;
  return (
    <div>
      <h1>As of {report.as_of}</h1>
      <p>{report.breached_count} breach(es) on {report.buckets.length} buckets</p>
      <table>
        <thead><tr><th>Axis</th><th>Key</th><th>Limit</th><th>Exposure</th><th>%</th></tr></thead>
        <tbody>
          {report.buckets.map((b: any, i: number) => (
            <tr key={i} style={{ background: b.breached ? "#fee" : "" }}>
              <td>{b.axis}</td>
              <td>{Object.values(b.key).join(" / ")}</td>
              <td>{b.limit?.toLocaleString()}</td>
              <td>{b.exposure.toLocaleString()}</td>
              <td>{b.utilization_pct?.toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

### 1.2 CORS

`backend/config.py` already whitelists:

* `http://localhost:5173` (Vite default)
* `http://localhost:3000` (CRA default)
* `tauri://localhost` (used by the desktop wrapper, see §2)

Override at runtime through the `RL_CORS_ORIGINS` env var
(comma-separated).

### 1.3 Single-port deployment

When you build the React app (`npm run build`) you obtain a static
`dist/` folder. To serve it from FastAPI alongside the API (no CORS, one
port), add to `backend/app.py`:

```python
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="ui")
```

This is what the packaged desktop binary does.

---

## 2. Shipping it as a desktop app

The user wants a clickable icon, no terminal, no VS Code, no Python
prompts. There are two solid recipes — pick the one that fits the
restrictions of the target machine.

### Option A — PyInstaller + bundled web UI (lightest, recommended)

Best when the target laptop already has a modern browser (Edge / Chrome)
and you can't install Node-based desktop runtimes.

1. **Build the React app once** on a developer machine:
   ```bash
   cd frontend && npm run build      # outputs frontend/dist
   ```
   Copy `frontend/dist` into `backend/static/` (or any path) and mount
   it as shown in §1.3.

2. **Freeze the backend with PyInstaller**:
   ```bash
   pip install pyinstaller
   pyinstaller \
       --name "RestrictionLimits" \
       --onefile --noconsole \
       --add-data "backend/static;backend/static" \
       --icon assets/icon.ico \
       backend/launcher.py
   ```
   On Linux/macOS replace the `;` with `:`.

3. The output `dist/RestrictionLimits.exe` is a single `.exe` that, when
   double-clicked:
   * starts FastAPI on `127.0.0.1:8765`,
   * waits ~1 s,
   * opens the user's default browser at that URL (see
     `backend/launcher.py`).

4. **Desktop icon (Windows)**: right-click `RestrictionLimits.exe` →
   *Send to → Desktop (create shortcut)*. The shortcut already shows
   the icon embedded in the binary. To distribute it preconfigured,
   ship a `.lnk` next to the `.exe`, or use *Inno Setup* (free,
   single-file `setup.exe`, no admin rights required for "user-only"
   installs) to add Start-menu and desktop shortcuts at install time.

### Option B — Tauri (native window, smallest binary, no browser tab)

Tauri wraps the React build inside the OS WebView (Edge WebView2 on
Windows, already present on every Windows 10/11 machine) and embeds a
Rust supervisor that spawns the Python backend as a sidecar.

1. Scaffold:
   ```bash
   npm create tauri-app@latest -- --template react-ts
   ```
2. Drop the FastAPI binary built in **Option A step 2** (`onefile` is
   fine) inside `src-tauri/binaries/` and declare it as a sidecar in
   `tauri.conf.json`:
   ```json
   {
     "tauri": {
       "bundle": {
         "externalBin": ["binaries/RestrictionLimits"],
         "icon": ["icons/icon.ico"]
       },
       "allowlist": { "shell": { "sidecar": true, "scope": [
           { "name": "binaries/RestrictionLimits", "sidecar": true }
       ]}}
     }
   }
   ```
3. Spawn the backend on app start (Rust side, `src-tauri/src/main.rs`):
   ```rust
   use tauri::api::process::Command;
   fn main() {
     tauri::Builder::default()
       .setup(|_app| {
         Command::new_sidecar("RestrictionLimits")?.spawn()?;
         Ok(())
       })
       .run(tauri::generate_context!())
       .expect("error while running tauri application");
   }
   ```
4. `npm run tauri build` produces an `.msi` (Windows) / `.dmg` (macOS) /
   `.AppImage` (Linux) installer with the icon and Start-menu entry
   already wired.

The React app talks to `http://127.0.0.1:8765` exactly as in §1.

### Option C — Pywebview (middle ground, pure-Python)

If Node is not available at all:

```bash
pip install pywebview
```

```python
# desktop.py
import threading, webview
from backend.launcher import main as start_backend
threading.Thread(target=start_backend, daemon=True).start()
webview.create_window("Restriction Limits", "http://127.0.0.1:8765")
webview.start()
```

Freeze with PyInstaller as in Option A. On Windows pywebview uses the
preinstalled Edge WebView2.

---

## 3. What needs to be downloadable on the target machine

Bank laptops typically allow:

* Browsers (Edge / Chrome) — required for Options A and C.
* Python 3.11 from the corporate software portal — required to *build*
  the binary on at least one developer machine, **not** required on end
  users' laptops once the `.exe` is built (PyInstaller bundles
  Python).
* Bloomberg Terminal — required only on machines that will *enrich*
  data via `pdblp` / `blpapi`. The Desktop API SDK ships with the
  terminal install.

The packaged binary itself has **no runtime dependencies**: PyInstaller
embeds Python, the standard library, FastAPI, pandas, openpyxl, and the
React `dist/`. End users just double-click.

| Component | Needed on dev box | Needed on user box |
| --- | --- | --- |
| Python 3.11 | ✅ | ❌ (bundled) |
| Node 18+ / npm | ✅ (to build React) | ❌ |
| PyInstaller | ✅ | ❌ |
| Edge / Chrome | optional | ✅ |
| Bloomberg Terminal + Desktop API | only if you call BBG | only if user runs live enrichment |
| Network share `M:\Mapas Gestao\…` | ✅ | ✅ (read-only is enough) |

If the bank blocks `pip` from the public PyPI, mirror the wheels listed
in `backend/requirements.txt` to the internal Artifactory and run
`pip install --index-url=<internal>`.

---

## 4. Bloomberg connection — what the dashboard uses and how to extend it

The current scope of the dashboard does **not require a live Bloomberg
session at runtime**. The consolidated exposure workbook already
contains the Bloomberg metadata for every transaction (Ticker, ISIN,
Country, Sector, Rating, Maturity, Coupon, Px_Last, etc.). The backend
simply reads those columns.

`backend/services/bloomberg_client.py` is provided so the system can be
extended in two directions:

### 4.1 Static enrichment (`ref` / `bdp`)

When a position arrives without complete metadata (e.g. only the
ticker), `enrich_positions()` calls Bloomberg's *reference* API to fill
in:

```
SECURITY_DES, ID_ISIN, ISSUER, CNTRY_OF_RISK, ISSUE_CNTRY,
CRNCY, INDUSTRY_SECTOR, BB_COMPOSITE, MATURITY, CPN, AMT_OUTSTANDING
```

Equivalent Bloomberg Excel formula: `=BDP("XS1234567890 Corp", "MATURITY")`.

### 4.2 Live re-pricing (`bdh`)

For intraday refreshes the client wraps `bdh()` so we can pull
`PX_LAST`, `YLD_YTM_MID`, `OAS_SPREAD_MID`, `DUR_ADJ_MID` for any
ticker between two dates and recompute exposures on the fly. This is
the same call already used by `Universe_construction.py`.

### 4.3 Setup checklist

1. Install **Bloomberg Terminal** and log in at least once on the
   machine that runs the backend.
2. From the terminal, install the **Desktop API SDK** (`WAPI<GO>` →
   *API Download Center* → *Desktop API*). This lays down the C++
   libraries that `blpapi` binds to.
3. On the same machine, install the Python wrappers (uncomment the
   relevant lines in `backend/requirements.txt`):
   ```
   pip install blpapi --index-url https://blpapi.bloomberg.com/repository/releases/python/simple/
   pip install pdblp
   ```
4. Confirm port `8194` is reachable (default Desktop API port). If you
   are using B-PIPE or Server API the port and host change — adjust
   `RL_BBG_HOST` / `RL_BBG_PORT`.
5. Set `RL_BBG_ENABLED=1` (or unset). On laptops without the terminal,
   set `RL_BBG_ENABLED=0` to turn the client into a no-op.

### 4.4 What is *not* covered yet (future work)

* **Authentication for B-PIPE / SAPI** — needs an explicit `Identity`
  on the `blpapi.Session`. Add a wrapper around
  `BloombergClient._ensure()` that calls
  `session.createAuthorizationRequest()`.
* **CDS curves and survival probabilities** — present in
  `Universe_construction.py` but not yet wired into the dashboard.
  Once the exposure file includes CDS tickers we can extend
  `aggregator.build_report` to add a credit-spread limit axis.
* **Streaming subscriptions (`MarketDataRequest`)** — would let the
  dashboard react to price moves in real time. Wire it through a
  WebSocket endpoint in `backend/app.py` and a `useWebSocket` hook on
  the React side.
* **Caching layer** — for SAPI volume limits, persist `ref()` results
  in a local SQLite (e.g. via `diskcache`) keyed by `(ticker, field,
  date)`.

---

## 5. End-to-end checklist

- [ ] Backend runs (`python -m backend.app`) and `/api/health` returns 200.
- [ ] `Collumns_Restriction_limits.xlsx` parses without errors.
- [ ] `RL_EXPOSURE_FILE` points at the consolidated workbook.
- [ ] React app calls `/api/report` and renders breaches.
- [ ] PyInstaller produces a single `.exe`.
- [ ] Desktop shortcut + icon present on user machines.
- [ ] (Optional) Bloomberg Terminal installed on at least one machine
      and `RL_BBG_ENABLED=1` works.
