"""Manual fixed-income trades and coupon/interest (FIFO trades use GainsCalculator)."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from .mutual_fund_transactions import (
    build_dividend_record,
    build_trade_record,
    dividend_records_to_dataframe,
)


def build_fi_trade_record(
    txn_date: datetime,
    instrument_name: str,
    isin: Optional[str],
    txn_kind: str,
    units: float,
    price: float,
    fees: float = 0.0,
) -> Dict[str, Any]:
    """Purchase / sale of bonds, CDs, etc. `units` × `price` = principal amount."""
    return build_trade_record(
        txn_date,
        instrument_name,
        isin,
        txn_kind,
        units,
        price,
        fees,
        slug_prefix="FI",
    )


def build_interest_record(
    paid_date: datetime,
    instrument_name: str,
    amount: float,
    isin: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Coupon, interest payment, or similar income (not capital gain)."""
    return build_dividend_record(paid_date, instrument_name, amount, isin, notes)


def fi_interest_to_dataframe(records: List[Dict[str, Any]]):
    return dividend_records_to_dataframe(records)
