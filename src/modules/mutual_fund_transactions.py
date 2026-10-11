"""
Helpers for manual mutual fund trade and dividend entries (compatible with GainsCalculator).
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd


def symbol_for_fund(
    fund_name: str, isin: Optional[str] = None, slug_prefix: str = "MF"
) -> str:
    """Use ISIN when present; otherwise a stable slug from the name (e.g. MF_/FI_)."""
    raw = (isin or "").strip()
    if raw:
        return raw.upper()
    slug = re.sub(r"[^A-Za-z0-9]+", "_", (fund_name or "").strip()).strip("_")
    slug = slug[:36] if slug else "UNKNOWN"
    p = (slug_prefix or "MF").strip().rstrip("_")
    return f"{p}_{slug}"


def build_trade_record(
    txn_date: datetime,
    fund_name: str,
    isin: Optional[str],
    txn_kind: str,
    units: float,
    nav: float,
    fees: float = 0.0,
    slug_prefix: str = "MF",
) -> Dict[str, Any]:
    """
    Build one row matching TransactionReader / GainsCalculator expectations.

    txn_kind: 'purchase' -> BUY, 'redemption' -> SELL
    """
    kind = (txn_kind or "").strip().lower()
    if kind == "purchase":
        t = "BUY"
    elif kind == "redemption":
        t = "SELL"
    else:
        raise ValueError("Transaction type must be purchase or redemption")

    if units <= 0 or nav <= 0:
        raise ValueError("Units and NAV must be positive")

    sym = symbol_for_fund(fund_name, isin, slug_prefix=slug_prefix)
    total = units * nav
    amt = total if t == "BUY" else total

    return {
        "Txn_Date": txn_date,
        "Symbol": sym,
        "ISIN_Name": (fund_name or "").strip(),
        "Type": t,
        "Quantity": float(units),
        "Price": float(nav),
        "Amount": float(amt),
        "Fees": float(fees) if fees and fees > 0 else 0.0,
        "Total_Value": float(total),
    }


def trade_records_to_dataframe(records: List[Dict[str, Any]]) -> pd.DataFrame:
    cols = [
        "Txn_Date",
        "Symbol",
        "Type",
        "Quantity",
        "Price",
        "Amount",
        "ISIN_Name",
        "Fees",
        "Total_Value",
    ]
    if not records:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(records)
    df["Txn_Date"] = pd.to_datetime(df["Txn_Date"])
    for c in ("Quantity", "Price", "Amount", "Fees", "Total_Value"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values(["Txn_Date", "Symbol"]).reset_index(drop=True)


def build_dividend_record(
    div_date: datetime,
    fund_name: str,
    amount: float,
    isin: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    if amount <= 0:
        raise ValueError("Dividend amount must be positive")
    return {
        "Date": div_date,
        "Fund_Name": (fund_name or "").strip(),
        "ISIN": (isin or "").strip(),
        "Amount": float(amount),
        "Notes": (notes or "").strip(),
    }


def dividend_records_to_dataframe(records: List[Dict[str, Any]]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=["Date", "Fund_Name", "ISIN", "Amount", "Notes"])
    df = pd.DataFrame(records)
    df["Date"] = pd.to_datetime(df["Date"])
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")
    return df.sort_values("Date").reset_index(drop=True)
