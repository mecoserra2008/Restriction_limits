"""
Central configuration for the Restriction Limits backend.

All paths and runtime knobs live here so the rest of the code does not
hard-code any location. Override any value through environment variables
(useful when running inside a packaged desktop app or in CI).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


def _env_path(var: str, default: str) -> Path:
    return Path(os.environ.get(var, default))


@dataclass
class Settings:
    # ----- Limits Excel (file #1) -----
    # Network share where the monthly limit files live (one Excel per day,
    # named DD-MM-YYYY.xlsx, organised under <BASE>/<YEAR>/<MONTH>/).
    limits_base_dir: Path = field(
        default_factory=lambda: _env_path(
            "RL_LIMITS_BASE_DIR", r"M:\Mapas Gestao\Linhas - Risco de Credito"
        )
    )
    # Schema reference workbook (the empty header-only file we ship in the
    # repo). Used to validate the limits file structure on load.
    limits_schema_file: Path = field(
        default_factory=lambda: _env_path(
            "RL_LIMITS_SCHEMA",
            str(Path(__file__).resolve().parent.parent
                / "Collumns_Restriction_limits.xlsx"),
        )
    )

    # ----- Exposure Excel (file #2) -----
    # Consolidated workbook holding every position from both Bloomberg and
    # the Market Access platform. Each row is a transaction whose columns
    # mirror Bloomberg bond metadata (so we can join on TICKER / ISIN).
    exposure_file: Path = field(
        default_factory=lambda: _env_path(
            "RL_EXPOSURE_FILE",
            str(Path.home() / "exposures" / "consolidated_exposure.xlsx"),
        )
    )
    exposure_sheet: str = os.environ.get("RL_EXPOSURE_SHEET", "Exposure")

    # ----- Bloomberg connection (optional, only used for live enrichment) -----
    bloomberg_host: str = os.environ.get("RL_BBG_HOST", "localhost")
    bloomberg_port: int = int(os.environ.get("RL_BBG_PORT", "8194"))
    bloomberg_timeout_ms: int = int(os.environ.get("RL_BBG_TIMEOUT", "5000"))
    bloomberg_enabled: bool = os.environ.get("RL_BBG_ENABLED", "1") == "1"

    # ----- Server -----
    api_host: str = os.environ.get("RL_API_HOST", "127.0.0.1")
    api_port: int = int(os.environ.get("RL_API_PORT", "8765"))
    cors_origins: List[str] = field(
        default_factory=lambda: os.environ.get(
            "RL_CORS_ORIGINS",
            "http://localhost:5173,http://localhost:3000,tauri://localhost",
        ).split(",")
    )

    # Cache TTL for parsed Excel data (seconds). The Excel files are heavy
    # to parse so we keep them in memory until they change on disk.
    cache_ttl_seconds: int = int(os.environ.get("RL_CACHE_TTL", "300"))


SETTINGS = Settings()
