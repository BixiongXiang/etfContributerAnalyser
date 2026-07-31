"""
Unit tests for the attribution engine.

Run with:
    cd backend
    source .venv/bin/activate
    pytest tests/test_attribution.py -v
"""

import pytest
from src.core.attribution import (
    AttributionRecord,
    calculate_attribution,
    calculate_sector_attribution,
    validate_attribution,
)
from src.providers.base import HoldingRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _holding(symbol: str, weight: float, sector: str = "Technology") -> HoldingRecord:
    return HoldingRecord(symbol=symbol, company_name=f"{symbol} Inc.", weight=weight, sector=sector)


def _price(close: float, prev_close: float) -> tuple[float, float]:
    return (close, prev_close)


# ---------------------------------------------------------------------------
# calculate_attribution
# ---------------------------------------------------------------------------


class TestCalculateAttribution:
    def test_basic_contribution(self):
        """AAPL weight=7.5%, return=+2.63% → contribution ≈ +0.197 pp"""
        holdings = [_holding("AAPL", weight=7.5)]
        prices = {"AAPL": _price(close=195.0, prev_close=190.0)}

        result = calculate_attribution(holdings, prices)

        assert len(result) == 1
        assert result[0].symbol == "AAPL"
        assert abs(result[0].return_pct - 2.6316) < 0.01
        # contribution = 7.5 * (195-190)/190 = 7.5 * 0.026316 = 0.19737
        assert abs(result[0].contribution - 0.19737) < 0.001

    def test_negative_contribution(self):
        """NVDA weight=8.2%, return=-3.0% → contribution ≈ -0.246 pp"""
        holdings = [_holding("NVDA", weight=8.2)]
        prices = {"NVDA": _price(close=97.0, prev_close=100.0)}

        result = calculate_attribution(holdings, prices)

        assert len(result) == 1
        assert result[0].return_pct == pytest.approx(-3.0, abs=0.01)
        assert result[0].contribution == pytest.approx(-0.246, abs=0.001)

    def test_sorted_by_absolute_contribution(self):
        """Results must be sorted by |contribution| descending."""
        holdings = [
            _holding("SMALL",  weight=1.0),
            _holding("LARGE",  weight=10.0),
            _holding("MEDIUM", weight=5.0),
        ]
        prices = {
            "SMALL":  _price(110.0, 100.0),   # +10%, contrib = +0.100
            "LARGE":  _price(95.0,  100.0),   # -5%,  contrib = -0.500
            "MEDIUM": _price(106.0, 100.0),   # +6%,  contrib = +0.300
        }

        result = calculate_attribution(holdings, prices)
        contribs = [abs(r.contribution) for r in result]

        assert contribs == sorted(contribs, reverse=True)
        assert result[0].symbol == "LARGE"
        assert result[1].symbol == "MEDIUM"
        assert result[2].symbol == "SMALL"

    def test_missing_price_skipped(self):
        """Holdings with no price entry are silently excluded."""
        holdings = [_holding("AAPL", 7.5), _holding("MISSING", 3.0)]
        prices = {"AAPL": _price(195.0, 190.0)}

        result = calculate_attribution(holdings, prices)

        assert len(result) == 1
        assert result[0].symbol == "AAPL"

    def test_zero_weight_holding(self):
        """Zero-weight holding has zero contribution."""
        holdings = [_holding("CASH", weight=0.0)]
        prices = {"CASH": _price(1.0, 1.0)}

        result = calculate_attribution(holdings, prices)

        assert len(result) == 1
        assert result[0].contribution == 0.0

    def test_single_holding_etf(self):
        """ETF with a single holding — contribution should equal weight × return."""
        holdings = [_holding("SPY", weight=100.0)]
        prices = {"SPY": _price(510.0, 500.0)}  # +2%

        result = calculate_attribution(holdings, prices)

        assert len(result) == 1
        assert result[0].contribution == pytest.approx(2.0, abs=0.001)  # 100 * 0.02 = 2.0 pp

    def test_empty_holdings(self):
        holdings = []
        prices = {"AAPL": _price(195.0, 190.0)}

        result = calculate_attribution(holdings, prices)

        assert result == []

    def test_empty_prices(self):
        holdings = [_holding("AAPL", 7.5)]
        prices = {}

        result = calculate_attribution(holdings, prices)

        assert result == []


# ---------------------------------------------------------------------------
# calculate_sector_attribution
# ---------------------------------------------------------------------------


class TestCalculateSectorAttribution:
    def _make_attribution(self, symbol, sector, contribution) -> AttributionRecord:
        return AttributionRecord(
            symbol=symbol,
            company_name=f"{symbol} Inc.",
            sector=sector,
            weight=5.0,
            return_pct=contribution / 5.0 * 100,
            contribution=contribution,
        )

    def test_groups_by_sector(self):
        attributions = [
            self._make_attribution("NVDA", "Semiconductors", -0.25),
            self._make_attribution("AMD",  "Semiconductors", -0.15),
            self._make_attribution("AAPL", "Technology",     +0.10),
        ]

        result = calculate_sector_attribution(attributions)
        sector_map = {s.sector: s for s in result}

        assert "Semiconductors" in sector_map
        assert sector_map["Semiconductors"].contribution == pytest.approx(-0.40, abs=0.001)
        assert sector_map["Semiconductors"].num_stocks == 2
        assert sector_map["Technology"].contribution == pytest.approx(+0.10, abs=0.001)

    def test_pct_of_total_move(self):
        attributions = [
            self._make_attribution("A", "Tech", -0.80),
            self._make_attribution("B", "Finance", -0.20),
        ]

        result = calculate_sector_attribution(attributions)
        sector_map = {s.sector: s for s in result}

        assert sector_map["Tech"].pct_of_total_move == pytest.approx(80.0, abs=0.1)
        assert sector_map["Finance"].pct_of_total_move == pytest.approx(20.0, abs=0.1)

    def test_none_sector_becomes_unknown(self):
        attributions = [
            AttributionRecord("X", "X Corp", None, 5.0, 2.0, 0.10),
        ]

        result = calculate_sector_attribution(attributions)

        assert result[0].sector == "Unknown"

    def test_sorted_by_absolute_contribution(self):
        attributions = [
            self._make_attribution("A", "Small",  -0.05),
            self._make_attribution("B", "Big",    -0.50),
            self._make_attribution("C", "Medium", +0.20),
        ]

        result = calculate_sector_attribution(attributions)
        abs_contribs = [abs(s.contribution) for s in result]

        assert abs_contribs == sorted(abs_contribs, reverse=True)


# ---------------------------------------------------------------------------
# validate_attribution
# ---------------------------------------------------------------------------


class TestValidateAttribution:
    def _make_attribution(self, contribution: float) -> AttributionRecord:
        return AttributionRecord("X", "X", None, 5.0, contribution / 5.0 * 100, contribution)

    def test_valid_within_tolerance(self):
        attributions = [self._make_attribution(-0.50), self._make_attribution(-0.74)]
        is_valid, mismatch = validate_attribution(attributions, etf_return_pct=-1.24, tolerance=0.05)

        assert is_valid is True
        assert mismatch < 0.05

    def test_invalid_outside_tolerance(self):
        attributions = [self._make_attribution(-0.50)]
        is_valid, mismatch = validate_attribution(attributions, etf_return_pct=-1.24, tolerance=0.05)

        assert is_valid is False
        assert mismatch > 0.05

    def test_exact_match(self):
        attributions = [self._make_attribution(-1.24)]
        is_valid, mismatch = validate_attribution(attributions, etf_return_pct=-1.24, tolerance=0.05)

        assert is_valid is True
        assert mismatch == pytest.approx(0.0, abs=1e-10)
