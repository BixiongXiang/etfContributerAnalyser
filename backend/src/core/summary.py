"""
Rule-based text summary generator (no LLM required).

Produces human-readable summaries like:
    "Today's QQQ decline of -1.24% was primarily driven by Semiconductors
    (-0.78%, 63% of move). NVDA was the single largest contributor at -0.25%."
"""

from datetime import date

from src.core.attribution import AttributionRecord, SectorAttribution


def generate_summary(
    etf_symbol: str,
    trade_date: date,
    etf_return_pct: float,
    attributions: list[AttributionRecord],
    sector_attributions: list[SectorAttribution],
    top_n: int = 10,
) -> str:
    """
    Generate a plain-English summary of today's ETF attribution.

    Args:
        etf_symbol:          e.g. "QQQ"
        trade_date:          the trading date
        etf_return_pct:      ETF daily return in %, e.g. -1.24
        attributions:        sorted by |contribution| descending
        sector_attributions: sorted by |contribution| descending
        top_n:               how many top contributors to mention

    Returns:
        Multi-sentence summary string.
    """
    if not attributions:
        return f"No attribution data available for {etf_symbol} on {trade_date}."

    direction = "gain" if etf_return_pct >= 0 else "decline"
    sign = "+" if etf_return_pct >= 0 else ""
    lines: list[str] = []

    # Opening sentence
    lines.append(
        f"Today's {etf_symbol} {direction} of {sign}{etf_return_pct:.2f}%"
        f" on {trade_date.strftime('%B %d, %Y')}."
    )

    # Top sector
    if sector_attributions:
        top_sector = sector_attributions[0]
        sector_sign = "+" if top_sector.contribution >= 0 else ""
        lines.append(
            f"The largest sector driver was {top_sector.sector} "
            f"({sector_sign}{top_sector.contribution:.2f} pp, "
            f"{abs(top_sector.pct_of_total_move):.0f}% of the total move)."
        )

    # Top individual contributor
    top = attributions[0]
    contrib_sign = "+" if top.contribution >= 0 else ""
    lines.append(
        f"The single largest contributor was {top.symbol} ({top.company_name}): "
        f"weight {top.weight:.1f}%, return {top.return_pct:+.1f}%, "
        f"contribution {contrib_sign}{top.contribution:.3f} pp."
    )

    # Count of negative vs positive contributors in top_n
    top_slice = attributions[:top_n]
    n_negative = sum(1 for a in top_slice if a.contribution < 0)
    n_positive = sum(1 for a in top_slice if a.contribution > 0)

    if n_negative > 0 and n_positive > 0:
        lines.append(
            f"Among the top {len(top_slice)} contributors by impact, "
            f"{n_negative} dragged the index lower and {n_positive} pushed it higher."
        )
    elif n_negative == len(top_slice):
        lines.append(
            f"All top {len(top_slice)} contributors by impact were negative."
        )
    elif n_positive == len(top_slice):
        lines.append(
            f"All top {len(top_slice)} contributors by impact were positive."
        )

    # Technology-sector note (common for QQQ)
    if etf_symbol in ("QQQ", "VOO"):
        tech_attributions = [a for a in top_slice if (a.sector or "").lower() in ("technology", "information technology")]
        if len(tech_attributions) >= 5:
            lines.append(
                f"Notable: {len(tech_attributions)} of the top {len(top_slice)} contributors "
                f"are in the Technology sector."
            )

    return " ".join(lines)
