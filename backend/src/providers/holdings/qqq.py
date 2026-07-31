"""
QQQ holdings parser.

Strategy:
  1. Try to download live CSV from Invesco (daily updates)
  2. If that fails for any reason, fall back to bundled static CSV

Invesco's download URL has historically changed. If it returns HTML instead
of CSV (their site is a JS SPA), we detect that and fall through to the static file.
"""

import io
import logging
from datetime import date

import httpx
import pandas as pd

from src.providers.base import HoldingRecord
from src.providers.holdings.static_loader import load_static_holdings

logger = logging.getLogger(__name__)

# Current Invesco direct CSV download URL (may need periodic updating)
_QQQ_URL = (
    "https://www.invesco.com/us/financial/etfs/holdings/main/holdings/0"
    "?audienceType=Investor&action=download&ticker=QQQ"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv, text/plain, */*",
    "Referer": "https://www.invesco.com/us/financial/etfs/product-detail"
               "?audienceType=Investor&ticker=QQQ",
}


async def fetch_qqq_holdings() -> tuple[list[HoldingRecord], date]:
    """Fetch QQQ holdings — live Invesco CSV with static file fallback."""
    try:
        holdings, as_of = await _fetch_live()
        if holdings:
            logger.info("QQQ: using live holdings (%d rows, as of %s)", len(holdings), as_of)
            return holdings, as_of
        logger.warning("QQQ: live fetch returned 0 holdings — falling back to static file.")
    except Exception as exc:
        logger.warning("QQQ: live fetch failed (%s) — falling back to static file.", exc)

    return load_static_holdings("QQQ")


async def _fetch_live() -> tuple[list[HoldingRecord], date]:
    """Attempt to download and parse the live Invesco CSV."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(_QQQ_URL, headers=_HEADERS)
        resp.raise_for_status()
        raw = resp.text

    # Detect HTML response (Invesco serves their SPA instead of CSV sometimes)
    if raw.strip().startswith("<") or "<!DOCTYPE" in raw[:200]:
        raise ValueError("Response is HTML, not CSV — Invesco URL may have changed.")

    return _parse_invesco_csv(raw)


def _parse_invesco_csv(raw: str) -> tuple[list[HoldingRecord], date]:
    """Parse Invesco CSV text → (HoldingRecord list, as_of_date)."""
    lines = raw.splitlines()
    header_idx = None
    as_of_date = date.today()

    for i, line in enumerate(lines):
        if "holdings as of" in line.lower() or "as of" in line.lower():
            try:
                parts = line.split(",")
                for part in parts:
                    part = part.strip().strip('"')
                    if "/" in part and len(part) == 10:
                        m, d_, y = part.split("/")
                        as_of_date = date(int(y), int(m), int(d_))
                        break
            except Exception:
                pass

        if "ticker" in line.lower() and "weight" in line.lower():
            header_idx = i
            break

    if header_idx is None:
        return [], as_of_date

    df = pd.read_csv(io.StringIO("\n".join(lines[header_idx:])))
    df.columns = [c.strip() for c in df.columns]

    holdings: list[HoldingRecord] = []
    for _, row in df.iterrows():
        ticker = str(row.get("Ticker", "")).strip().upper()
        if not ticker or ticker in ("", "NAN", "CASH"):
            continue
        try:
            weight = float(str(row.get("Weight", 0)).replace("%", "").strip())
        except (ValueError, TypeError):
            continue

        holdings.append(HoldingRecord(
            symbol=ticker,
            company_name=str(row.get("Name", ticker)).strip(),
            weight=weight,
            sector=str(row.get("Sector", "")).strip() or None,
            shares=_to_int(row.get("Shares/Par Value")),
        ))

    return holdings, as_of_date


def _to_int(value) -> int | None:
    try:
        return int(float(str(value).replace(",", "")))
    except (ValueError, TypeError):
        return None
