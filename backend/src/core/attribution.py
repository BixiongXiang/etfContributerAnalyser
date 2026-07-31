"""
Attribution engine — core business logic.

Calculates each holding's contribution to the ETF's daily return:
    contribution (pp) = weight (%) × daily_return (%) / 100

All inputs and outputs use clear units:
    weight       — percentage, e.g. 8.2  means 8.2%
    return_pct   — percentage, e.g. -3.1 means -3.1%
    contribution — percentage points, e.g. -0.2542 pp
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Optional

from src.providers.base import HoldingRecord, PriceRecord

logger = logging.getLogger(__name__)


@dataclass
class AttributionRecord:
    symbol: str
    company_name: str
    sector: Optional[str]
    weight: float        # % of ETF (e.g. 8.2)
    return_pct: float    # daily stock return in % (e.g. -3.1)
    contribution: float  # weight * return_pct / 100  (percentage points)


@dataclass
class SectorAttribution:
    sector: str
    contribution: float        # summed contribution in pp
    pct_of_total_move: float   # contribution / total_etf_move * 100
    num_stocks: int


def calculate_attribution(
    holdings: list[HoldingRecord],
    prices: dict[str, tuple[float, float]],  # symbol → (close, prev_close)
) -> list[AttributionRecord]:
    """
    Compute per-holding attribution.

    Args:
        holdings: Current ETF holdings with weights.
        prices:   Dict mapping ticker → (close, prev_close).
                  Build this from two consecutive DailyPrice rows.

    Returns:
        List of AttributionRecord sorted by |contribution| descending.

    Skips holdings with no price data (logs a warning per missing symbol).
    """
    results: list[AttributionRecord] = []
    missing: list[str] = []

    for holding in holdings:
        price_pair = prices.get(holding.symbol)
        if price_pair is None:
            missing.append(holding.symbol)
            continue

        close, prev_close = price_pair
        if prev_close == 0:
            logger.warning("prev_close is 0 for %s — skipping", holding.symbol)
            continue

        daily_return = (close - prev_close) / prev_close  # decimal, e.g. -0.031
        # contribution in percentage points:
        #   weight=8.2  daily_return=-0.031  → contribution = 8.2 * (-0.031) / 100 = -0.002542 pp
        # Wait — weight is already in %, so:
        #   contribution (pp) = (weight/100) * daily_return * 100 = weight * daily_return
        contribution = holding.weight * daily_return  # pp

        results.append(
            AttributionRecord(
                symbol=holding.symbol,
                company_name=holding.company_name,
                sector=holding.sector,
                weight=holding.weight,
                return_pct=daily_return * 100,
                contribution=contribution,
            )
        )

    if missing:
        logger.warning(
            "Attribution: no price data for %d symbols: %s%s",
            len(missing),
            ", ".join(missing[:10]),
            " …" if len(missing) > 10 else "",
        )

    # Sort by absolute contribution descending (biggest movers first)
    results.sort(key=lambda x: abs(x.contribution), reverse=True)
    return results


def calculate_sector_attribution(
    attributions: list[AttributionRecord],
) -> list[SectorAttribution]:
    """
    Aggregate per-holding attribution into sector-level totals.

    Returns:
        List of SectorAttribution sorted by |contribution| descending.
    """
    buckets: dict[str, dict] = defaultdict(lambda: {"contribution": 0.0, "count": 0})
    total_move = sum(a.contribution for a in attributions)

    for a in attributions:
        sector = a.sector or "Unknown"
        buckets[sector]["contribution"] += a.contribution
        buckets[sector]["count"] += 1

    sector_list = [
        SectorAttribution(
            sector=name,
            contribution=data["contribution"],
            pct_of_total_move=(
                (data["contribution"] / total_move * 100) if total_move != 0 else 0.0
            ),
            num_stocks=data["count"],
        )
        for name, data in buckets.items()
    ]

    sector_list.sort(key=lambda x: abs(x.contribution), reverse=True)
    return sector_list


def validate_attribution(
    attributions: list[AttributionRecord],
    etf_return_pct: float,
    tolerance: float = 0.05,
) -> tuple[bool, float]:
    """
    Check that the sum of contributions approximately equals the ETF's daily return.

    Args:
        attributions:   Output of calculate_attribution().
        etf_return_pct: The ETF's actual daily return in % (from its own price).
        tolerance:      Acceptable mismatch in percentage points (default 0.05 pp).

    Returns:
        (is_valid, mismatch_pp) where mismatch = |sum_contributions - etf_return_pct|.
    """
    sum_contributions = sum(a.contribution for a in attributions)
    mismatch = abs(sum_contributions - etf_return_pct)
    is_valid = mismatch <= tolerance

    if not is_valid:
        logger.warning(
            "Attribution mismatch: sum=%.4f pp, ETF return=%.4f%%, diff=%.4f pp (tolerance=%.2f pp)",
            sum_contributions,
            etf_return_pct,
            mismatch,
            tolerance,
        )

    return is_valid, mismatch
