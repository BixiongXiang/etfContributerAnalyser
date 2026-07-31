"""
VOO holdings parser.

Strategy:
  1. Try to download live CSV from Vanguard (monthly updates)
  2. Fall back to bundled static CSV on any failure

VOO weights are published monthly by Vanguard. The static file is
refreshed by scripts/refresh_holdings.py.
"""

import io
import logging
from datetime import date, datetime

import httpx
import pandas as pd

from src.providers.base import HoldingRecord
from src.providers.holdings.static_loader import load_static_holdings

logger = logging.getLogger(__name__)

# Vanguard holdings CSV for VOO (fund ID 0968)
_VOO_URL = "https://advisors.vanguard.com/web/ecs/fas-portals-holdings/0968/csv"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv, text/plain, */*",
    "Referer": "https://advisors.vanguard.com/",
}


async def fetch_voo_holdings() -> tuple[list[HoldingRecord], date]:
    """Fetch VOO holdings — live Vanguard CSV with static file fallback."""
    try:
        holdings, as_of = await _fetch_live()
        if holdings:
            logger.info("VOO: using live holdings (%d rows, as of %s)", len(holdings), as_of)
            return holdings, as_of
        logger.warning("VOO: live fetch returned 0 holdings — falling back to static file.")
    except Exception as exc:
        logger.warning("VOO: live fetch failed (%s) — falling back to static file.", exc)

    return load_static_holdings("VOO")


async def _fetch_live() -> tuple[list[HoldingRecord], date]:
    """Attempt to download and parse the live Vanguard CSV."""
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(_VOO_URL, headers=_HEADERS)
        resp.raise_for_status()
        raw = resp.text

    if raw.strip().startswith("<") or "<!DOCTYPE" in raw[:200]:
        raise ValueError("Response is HTML, not CSV — Vanguard URL may have changed.")

    return _parse_vanguard_csv(raw)


def _parse_vanguard_csv(raw: str) -> tuple[list[HoldingRecord], date]:
    """Parse Vanguard CSV text → (HoldingRecord list, as_of_date)."""
    lines = raw.splitlines()
    header_idx = None
    as_of_date = date.today()

    for i, line in enumerate(lines):
        low = line.lower()
        if "as of date" in low or "as of:" in low:
            try:
                date_part = line.split(":", 1)[-1].strip().strip('"')
                for fmt in ("%m/%d/%Y", "%B %d, %Y"):
                    try:
                        as_of_date = datetime.strptime(date_part, fmt).date()
                        break
                    except ValueError:
                        continue
            except Exception:
                pass

        if "ticker" in low and ("% of funds" in low or "weight" in low):
            header_idx = i
            break

    if header_idx is None:
        return [], as_of_date

    df = pd.read_csv(io.StringIO("\n".join(lines[header_idx:])))
    df.columns = [c.strip() for c in df.columns]

    weight_col = next(
        (c for c in df.columns if "%" in c and "fund" in c.lower()),
        next((c for c in df.columns if "weight" in c.lower()), None),
    )
    if weight_col is None:
        return [], as_of_date

    holdings: list[HoldingRecord] = []
    for _, row in df.iterrows():
        ticker = str(row.get("Ticker", "")).strip().upper()
        if not ticker or ticker.lower() == "nan":
            continue
        try:
            weight = float(str(row[weight_col]).replace("%", "").strip())
        except (ValueError, TypeError):
            continue

        holdings.append(HoldingRecord(
            symbol=ticker,
            company_name=str(row.get("Security name", ticker)).strip(),
            weight=weight,
            sector=str(row.get("Sector", "")).strip() or None,
            shares=_to_int(row.get("Shares")),
        ))

    return holdings, as_of_date


def _to_int(value) -> int | None:
    try:
        return int(float(str(value).replace(",", "")))
    except (ValueError, TypeError):
        return None
