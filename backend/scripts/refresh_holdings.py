#!/usr/bin/env python3
"""
Refresh the bundled static holdings CSV files.

Run this manually whenever you want to update the holdings data:

    cd backend
    source .venv/bin/activate
    python scripts/refresh_holdings.py

    # Refresh only one ETF:
    python scripts/refresh_holdings.py --etf QQQ

What it does:
  1. Calls the live holdings fetcher for each ETF (Invesco, Vanguard, Schwab)
  2. If the live fetch succeeds, overwrites the static CSV
  3. If it fails, keeps the existing static CSV and reports the error

The static CSVs are used as fallback when live sources are unavailable.
"""

import argparse
import asyncio
import logging
import sys
from datetime import date
from pathlib import Path

# Make sure we can import from src/
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent.parent / "src" / "providers" / "holdings" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

SUPPORTED = ["QQQ", "VOO", "SCHD"]


async def refresh_etf(etf_symbol: str) -> bool:
    """
    Attempt to download live holdings and save to static CSV.
    Returns True on success, False on failure.
    """
    import pandas as pd
    from src.providers.base import HoldingRecord

    # Import the specific live fetcher (bypass the static fallback)
    if etf_symbol == "QQQ":
        from src.providers.holdings.qqq import _fetch_live as fetch_live
    elif etf_symbol == "VOO":
        from src.providers.holdings.voo import _fetch_live as fetch_live
    elif etf_symbol == "SCHD":
        from src.providers.holdings.schd import _fetch_live as fetch_live
    else:
        logger.error("Unknown ETF: %s", etf_symbol)
        return False

    logger.info("Refreshing %s holdings from live source…", etf_symbol)
    try:
        holdings, as_of = await fetch_live()
        if not holdings:
            logger.warning("%s: live source returned 0 holdings — skipping.", etf_symbol)
            return False
    except Exception as exc:
        logger.error("%s: live fetch failed: %s", etf_symbol, exc)
        return False

    # Build DataFrame and save
    rows = [
        {
            "symbol": h.symbol,
            "company_name": h.company_name,
            "sector": h.sector or "",
            "weight": h.weight,
            "as_of_date": str(as_of),
        }
        for h in holdings
    ]
    df = pd.DataFrame(rows)
    df = df.sort_values("weight", ascending=False).reset_index(drop=True)

    out_path = STATIC_DIR / f"{etf_symbol}.csv"
    df.to_csv(out_path, index=False)
    logger.info(
        "%s: saved %d holdings (as of %s) → %s",
        etf_symbol, len(df), as_of, out_path,
    )
    return True


async def main(etfs: list[str]) -> None:
    results = {}
    for etf in etfs:
        ok = await refresh_etf(etf)
        results[etf] = "✓ updated" if ok else "✗ failed (existing static file kept)"

    print("\n── Refresh summary ─────────────────────────")
    for etf, status in results.items():
        print(f"  {etf}: {status}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Refresh static ETF holdings CSVs.")
    parser.add_argument(
        "--etf",
        choices=SUPPORTED,
        default=None,
        help="Refresh a single ETF (default: all)",
    )
    args = parser.parse_args()

    etfs_to_refresh = [args.etf] if args.etf else SUPPORTED
    asyncio.run(main(etfs_to_refresh))
