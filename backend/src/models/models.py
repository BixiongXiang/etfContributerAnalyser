"""
SQLAlchemy ORM models — one class per database table.

All tables are created on startup via init_db() in database.py.
No Alembic migrations for MVP; schema is recreated from these definitions.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ETF(Base):
    """Supported ETFs and their metadata."""

    __tablename__ = "etfs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)  # "invesco" | "vanguard" | "schwab"
    last_holdings_update: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("symbol", name="uq_etfs_symbol"),)

    def __repr__(self) -> str:
        return f"<ETF {self.symbol}>"


class Holding(Base):
    """
    ETF holdings snapshot.  A new row is written each time holdings are refreshed.
    The most recent row for (etf_symbol, as_of_date) is considered current.
    """

    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    etf_symbol: Mapped[str] = mapped_column(Text, ForeignKey("etfs.symbol"), nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    sector: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # weight is stored as a percentage, e.g. 8.2 means 8.2%
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    # shares held by the fund (may be NULL if not published by provider)
    shares: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        Index("idx_holdings_etf_date", "etf_symbol", "as_of_date"),
    )

    def __repr__(self) -> str:
        return f"<Holding {self.etf_symbol}:{self.symbol} {self.as_of_date}>"


class DailyPrice(Base):
    """
    End-of-day OHLC prices per stock symbol.

    return_percent is NOT stored — it is computed as:
        (close - prev_close) / prev_close * 100
    where prev_close is fetched via LAG() or a self-join at query time.
    """

    __tablename__ = "daily_prices"

    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    high: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    low: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Adjusted close — used for return calculations
    close: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("symbol", "date", name="pk_daily_prices"),
    )

    def __repr__(self) -> str:
        return f"<DailyPrice {self.symbol} {self.date} close={self.close}>"


class Attribution(Base):
    """
    Pre-computed daily attribution for each ETF holding.

    contribution = weight * return_pct / 100
    Both weight (%) and contribution (percentage points) are stored.
    E.g. weight=8.2, return_pct=-3.1 → contribution=-0.2542
    """

    __tablename__ = "attribution"

    etf_symbol: Mapped[str] = mapped_column(Text, ForeignKey("etfs.symbol"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    sector: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # weight in percent (e.g. 8.2 for 8.2%)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    # daily return in percent (e.g. -3.1 for -3.1%)
    return_pct: Mapped[float] = mapped_column(Float, nullable=False)
    # contribution in percentage points (e.g. -0.2542)
    contribution: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("etf_symbol", "date", "symbol", name="pk_attribution"),
        Index("idx_attribution_etf_date", "etf_symbol", "date"),
    )

    def __repr__(self) -> str:
        return f"<Attribution {self.etf_symbol}:{self.symbol} {self.date} contrib={self.contribution:.4f}>"
