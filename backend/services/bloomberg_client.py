"""
Thin wrapper around the Bloomberg Desktop API (``blpapi``) and the
``pdblp`` convenience layer.

The dashboard does NOT require a live Bloomberg session: the consolidated
exposure workbook (file #2) already ships with the Bloomberg metadata for
every transaction. The client below is here for two optional use cases:

1. **Enrichment** - if a ticker shows up on the workbook without complete
   metadata, we call ``ref()`` to fill the gaps (country, sector, rating,
   maturity, ...).
2. **Live re-pricing** - on demand we can call ``bdh()`` / ``bdp()`` to
   refresh prices and recompute the exposures intra-day.

Both are guarded by ``SETTINGS.bloomberg_enabled`` and degrade gracefully
when ``blpapi`` is not installed (e.g. when running outside the Bloomberg
terminal host).
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import date
from typing import Dict, Iterable, List, Optional

from ..config import SETTINGS

log = logging.getLogger(__name__)

# Bloomberg fields we want for every bond ticker.
DEFAULT_STATIC_FIELDS: List[str] = [
    "SECURITY_DES",
    "ID_ISIN",
    "ISSUER",
    "CNTRY_OF_RISK",
    "ISSUE_CNTRY",
    "CRNCY",
    "INDUSTRY_SECTOR",
    "BB_COMPOSITE",
    "MATURITY",
    "CPN",
    "AMT_OUTSTANDING",
]

DEFAULT_DYNAMIC_FIELDS: List[str] = [
    "PX_LAST",
    "YLD_YTM_MID",
    "OAS_SPREAD_MID",
    "DUR_ADJ_MID",
]


class BloombergUnavailable(RuntimeError):
    """Raised when blpapi/pdblp is not importable or the desktop API is down."""


class BloombergClient:
    """Lazy, single-connection wrapper around ``pdblp.BCon``."""

    def __init__(
        self,
        host: str = SETTINGS.bloomberg_host,
        port: int = SETTINGS.bloomberg_port,
        timeout_ms: int = SETTINGS.bloomberg_timeout_ms,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout_ms = timeout_ms
        self._con = None

    # -- connection lifecycle -------------------------------------------------

    def _ensure(self):
        if not SETTINGS.bloomberg_enabled:
            raise BloombergUnavailable("Bloomberg is disabled (RL_BBG_ENABLED=0)")
        if self._con is not None:
            return self._con
        try:
            import pdblp  # type: ignore
        except ImportError as exc:
            raise BloombergUnavailable(
                "pdblp/blpapi not installed - install on a machine with the "
                "Bloomberg Terminal and the Desktop API SDK."
            ) from exc
        try:
            self._con = pdblp.BCon(
                debug=False, host=self.host, port=self.port,
                timeout=self.timeout_ms,
            )
            self._con.start()
        except Exception as exc:  # pragma: no cover - depends on local BBG
            raise BloombergUnavailable(
                f"Cannot reach Bloomberg Desktop API at {self.host}:{self.port}"
            ) from exc
        return self._con

    def close(self) -> None:
        if self._con is not None:
            try:
                self._con.stop()
            finally:
                self._con = None

    # -- queries --------------------------------------------------------------

    def ref(
        self,
        tickers: Iterable[str],
        fields: Optional[List[str]] = None,
    ):
        """Reference data (static fields). Returns a long-format DataFrame."""
        con = self._ensure()
        return con.ref(list(tickers), fields or DEFAULT_STATIC_FIELDS)

    def bdh(
        self,
        tickers: Iterable[str],
        fields: List[str],
        start: date,
        end: date,
    ):
        """Historical time series."""
        con = self._ensure()
        return con.bdh(
            list(tickers), fields,
            start.strftime("%Y%m%d"), end.strftime("%Y%m%d"),
        )

    def bdp(self, tickers: Iterable[str], fields: List[str]):
        """Snapshot ('Bloomberg Data Point')."""
        con = self._ensure()
        return con.ref(list(tickers), fields)


@contextmanager
def bloomberg_session():
    """Context manager that opens and closes a session cleanly."""
    client = BloombergClient()
    try:
        yield client
    finally:
        client.close()


def enrich_positions(positions: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """
    Fill missing static fields on a list of positions using Bloomberg.

    No-op (returns input unchanged) when Bloomberg is not available.
    """
    missing = [
        p for p in positions
        if p.get("ticker") and not all(
            p.get(k) for k in ("country", "currency", "industry_sector",
                                "maturity", "bb_composite")
        )
    ]
    if not missing:
        return positions
    try:
        with bloomberg_session() as bbg:
            df = bbg.ref([p["ticker"] for p in missing])
    except BloombergUnavailable as exc:
        log.warning("Skipping Bloomberg enrichment: %s", exc)
        return positions
    by_ticker = {}
    for _, row in df.iterrows():
        by_ticker.setdefault(row["ticker"], {})[row["field"]] = row["value"]
    for p in missing:
        meta = by_ticker.get(p["ticker"], {})
        p.setdefault("country", meta.get("CNTRY_OF_RISK") or meta.get("ISSUE_CNTRY"))
        p.setdefault("currency", meta.get("CRNCY"))
        p.setdefault("industry_sector", meta.get("INDUSTRY_SECTOR"))
        p.setdefault("bb_composite", meta.get("BB_COMPOSITE"))
        p.setdefault("maturity", meta.get("MATURITY"))
        p.setdefault("issuer", meta.get("ISSUER"))
        p.setdefault("isin", meta.get("ID_ISIN"))
    return positions
