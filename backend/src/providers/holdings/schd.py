"""
SCHD holdings parser.

Strategy:
  1. Try to download live CSV from Schwab (daily updates)
  2. Fall back to bundled static CSV on any failure
"""

import io
import logging
from datetime import date, datetime

import httpx
import pandas as pd

from src.providers.base import HoldingRecord
from src.providers.holdings.static_loader import load_static_holdings

logger = logging.getLogger(__name__)

# Schwab SCHD holdings CSV — URL may need updating periodically
_SCHD_URLS = [
    "https://www.schwabassetmanagement.com/sites/g/files/pcvezn656/files/2024-02/SCHD_HOldings.csv",
    "https://www.schwabassetmanagement.com/resource/schd-fund-downloads",
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv, text/plain, */*",
    "Referer": "https://www.schwabassetmanagement.com/",
}


async def fetch_schd_holdings() -> tuple[list[HoldingRecord], date]:
    """Fetch SCHD holdings — live Schwab CSV with static file fallback."""
    try:
        holdings, as_of = await _fetch_live()
        if holdings:
            logger.info("SCHD: using live holdings (%d rows, as of %s)", len(holdings), as_of)
            return holdings, as_of
        logger.warning("SCHD: live fetch returned 0 holdings — falling back to static file.")
    except Exception as exc:
        logger.warning("SCHD: live fetch failed (%s) — falling back to static file.", exc)

    return load_static_holdings("SCHD")


async def _fetch_live() -> tuple[list[HoldingRecord], date]:
    """Try each known URL until one returns a valid CSV."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for url in _SCHD_URLS:
            try:
                resp = await client.get(url, headers=_HEADERS)
                if resp.status_code != 200:
                    continue
                raw = resp.text
                if raw.strip().startswith("<") or "<!DOCTYPE" in raw[:200]:
                    continue
                holdings, as_of = _parse_schwab_csv(raw)
                if holdings:
                    return holdings, as_of
            except Exception as exc:
                logger.debug("SCHD URL %s failed: %s", url, exc)

    raise ValueError("All Schwab URLs failed or returned HTML.")


def _parse_schwab_csv(raw: str) -> tuple[list[HoldingRecord], date]:
    """Parse Schwab CSV text → (HoldingRecord list, as_of_date)."""
    lines = raw.splitlines()
    header_idx = None
    as_of_date = date.today()

    for i, line in enumerate(lines):
        low = line.lower()
        if "as of" in low:
            try:
                date_part = line.split(":", 1)[-1].strip().strip('"').strip()
                for fmt in ("%m/%d/%Y", "%B %d, %Y"):
                    try:
                        as_of_date = datetime.strptime(date_part, fmt).date()
                        break
                    except ValueError:
                        continue
            except Exception:
                pass

        if "symbol" in low and ("% of net" in low or "weight" in low):
            header_idx = i
            break

    if header_idx is None:
        return [], as_of_date

    df = pd.read_csv(io.StringIO("\n".join(lines[header_idx:])))
    df.columns = [c.strip().strip('"') for c in df.columns]

    weight_col = next(
        (c for c in df.columns if "%" in c and "net" in c.lower()),
        next((c for c in df.columns if "weight" in c.lower()), None),
    )
    if weight_col is None:
        return [], as_of_date

    holdings: list[HoldingRecord] = []
    for _, row in df.iterrows():
        ticker = str(row.get("Symbol", "")).strip().strip('"').upper()
        if not ticker or ticker.lower() == "nan":
            continue
        try:
            weight = float(str(row[weight_col]).replace("%", "").strip())
        except (ValueError, TypeError):
            continue

        holdings.append(HoldingRecord(
            symbol=ticker,
            company_name=str(row.get("Security Name", ticker)).strip().strip('"'),
            weight=weight,
            sector=str(row.get("Sector", "")).strip() or None,
            shares=_to_int(row.get("Shares Held")),
        ))

    return holdings, as_of_date


def _to_int(value) -> int | None:
    try:
        return int(float(str(value).replace(",", "")))
    except (ValueError, TypeError):
        return None
