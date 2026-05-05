# Restriction_limits

Dashboard that consolidates credit-risk **limits** (per Contraparte /
País / Tipo / RAF) against **exposure** sourced from Bloomberg and the
Market Access platform, and flags any breaches.

## Layout

```
backend/                 FastAPI service (Python)
  app.py                  HTTP API
  config.py               settings (env-overridable)
  models.py               Pydantic schemas
  launcher.py             desktop entry point (PyInstaller)
  services/
    limits_loader.py      parses the daily limits workbooks
    exposure_loader.py    parses the consolidated exposure workbook
    aggregator.py         builds the breach report
    bloomberg_client.py   optional pdblp/blpapi wrapper
    cache.py              mtime + TTL Excel cache
  requirements.txt
docs/
  BACKEND.md                       backend reference
  REACT_DESKTOP_INTEGRATION.md     how to wire React + ship as a desktop app
Collumns_Restriction_limits.xlsx   schema reference for file #1
```

## Quick start

```bash
pip install -r backend/requirements.txt
python -m backend.app           # http://127.0.0.1:8765/docs
```

See `docs/BACKEND.md` for the full API and `docs/REACT_DESKTOP_INTEGRATION.md`
for the React + desktop packaging story (PyInstaller / Tauri / pywebview)
and the Bloomberg setup checklist.