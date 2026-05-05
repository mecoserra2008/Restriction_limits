"""
Tiny launcher that boots the FastAPI server and (optionally) opens the
packaged React UI in the user's default browser.

Use this entry point when packaging the application as a desktop binary
with PyInstaller. See docs/REACT_DESKTOP_INTEGRATION.md.
"""
from __future__ import annotations

import os
import threading
import time
import webbrowser

import uvicorn

from .config import SETTINGS


def _open_browser():
    time.sleep(1.2)
    url = f"http://{SETTINGS.api_host}:{SETTINGS.api_port}/"
    # When the React build is bundled and served by uvicorn, hitting "/"
    # returns index.html; otherwise the user lands on FastAPI's docs.
    webbrowser.open(url)


def main():
    if os.environ.get("RL_OPEN_BROWSER", "1") == "1":
        threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(
        "backend.app:app",
        host=SETTINGS.api_host,
        port=SETTINGS.api_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
