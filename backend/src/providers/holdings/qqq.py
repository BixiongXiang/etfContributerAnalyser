"""
QQQ holdings parser — downloads and parses the Invesco daily holdings CSV.

Invesco publishes a CSV at a stable URL. The format is:
    Fund Name,Fund Holdings as of,Inception Date,Exchange,<blank header row>
    Name,Ticker,Identifier,SEDOL,Weight,CDI Indicator,Notional Value,Shares/Par Value,Price,Location,Exchange,Currency,FX Rate,Market Currency,Market Value

We skip header rows until we find the column headers, then parse the data.
"""

import io
import logging
from datetime import date

import httpx
import pandas as pd

from src.providers.base import HoldingRecord

logger = logging.getLogger(__name__)

# Invesco's direct CSV download URL for QQQ
_QQQ_URL = "https://www.invesco.com/us/financial/etfs/holdings/main/holdings/0?audienceType=Investor&action=download&ticker=QQQ"


async def fetch_qqq_holdings() -> tuple[list[HoldingRecord], date]:
    """Download and parse QQQ holdings from Invesco."""
    logger.info("Fetching QQQ holdings from Invesco…")
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(_QQQ_URL)
        resp.raise_for_status()
        raw = resp.text

    return _parse_invesco_csv(raw)


def _parse_invesco_csv(raw: str) -> tuple[list[HoldingRecord], date]:
    """
    Parse Invesco CSV text into HoldingRecord list.

    The CSV has a multi-row preamble before the actual column headers.
    We locate the header row by looking for 'Ticker' in the row.
    """
    lines = raw.splitlines()
    header_idx = None
    as_of_date = date.today()

    for i, line in enumerate(lines):
        # Extract the "as of" date from the preamble
        if "Holdings as of" in line or "as of" in line.lower():
            try:
                # Typical format: "Fund Holdings as of,07/29/2026"
                parts = line.split(",")
                for part in parts:
                    part = part.strip().strip('"')
                    if "/" in part and len(part) == 10:
                        as_of_date = date.fromisoformat(
                            "-".join(reversed(part.split("/")))
                            if part.count("/") == 2
                            else part
                        )
            except Exception:
                pass  # date parse is best-effort

        # Find the actual column header row
        if "Ticker" in line and "Weight" in line:
            header_idx = i
            break

    if header_idx is None:
        logger.error("QQQ CSV: could not find column header row. Raw snippet: %s", raw[:500])
        return [], as_of_date

    csv_body = "\n".join(lines[header_idx:])
    df = pd.read_csv(io.StringIO(csv_body))

    # Normalise column names (strip whitespace, lowercase for matching)
    df.columns = [c.strip() for c in df.columns]

    holdings: list[HoldingRecord] = []
    for _, row in df.iterrows():
        ticker = str(row.get("Ticker", "")).strip().upper()
        if not ticker or ticker in ("", "NAN", "CASH"):
            continue

        weight_raw = row.get("Weight")
        try:
            weight = float(str(weight_raw).replace("%", "").strip())
        except (ValueError, TypeError):
            continue

        holdings.append(
            HoldingRecord(
                symbol=ticker,
                company_name=str(row.get("Name", ticker)).strip(),
                weight=weight,
                sector=str(row.get("Sector", "")).strip() or None,
                shares=_to_int(row.get("Shares/Par Value")),
            )
        )

    logger.info("QQQ: parsed %d holdings as of %s", len(holdings), as_of_date)
    return holdings, as_of_date


def _to_int(value) -> int | None:
    try:
        return int(float(str(value).replace(",", "")))
    except (ValueError, TypeError):
        return None
