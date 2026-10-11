"""
Build unified dashboard: yearly capital/income by asset class and current holdings.
"""

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from .gains_calculator import CapitalGain, Position


def _yearly_capital_net(gains: Optional[List[CapitalGain]]) -> Dict[int, float]:
    out: Dict[int, float] = defaultdict(float)
    for g in gains or []:
        y = g.sell_date.year if hasattr(g.sell_date, "year") else datetime.fromisoformat(str(g.sell_date)).year
        out[y] += float(g.gain_loss)
    return dict(out)


def _yearly_income_from_records(records: List[Dict[str, Any]], date_field: str) -> Dict[int, float]:
    out: Dict[int, float] = defaultdict(float)
    for r in records or []:
        d = r.get(date_field)
        if d is None:
            continue
        y = d.year if hasattr(d, "year") else datetime.fromisoformat(str(d)[:10]).year
        amt = float(r.get("Amount", 0) or 0)
        out[y] += amt
    return dict(out)


def _yearly_property_gains(assets: List[Dict[str, Any]]) -> Dict[int, float]:
    out: Dict[int, float] = defaultdict(float)
    for a in assets or []:
        dd = a.get("disposition_date")
        if dd is None or a.get("disposition_proceeds") is None:
            continue
        y = dd.year if hasattr(dd, "year") else int(str(dd)[:4])
        proceeds = float(a["disposition_proceeds"])
        cost = float(a["cost_basis"])
        out[y] += proceeds - cost
    return dict(out)


def merge_years(*dicts: Dict[int, Any]) -> List[int]:
    keys = set()
    for d in dicts:
        keys.update(d.keys())
    return sorted(keys)


def build_dashboard_context(
    stock_gains: Optional[List[CapitalGain]],
    stock_positions: Optional[List[Position]],
    mf_gains: Optional[List[CapitalGain]],
    mf_positions: Optional[List[Position]],
    mf_dividend_records: List[Dict[str, Any]],
    fi_gains: Optional[List[CapitalGain]],
    fi_positions: Optional[List[Position]],
    fi_interest_records: List[Dict[str, Any]],
    property_assets: List[Dict[str, Any]],
) -> Dict[str, Any]:
    y_stocks = _yearly_capital_net(stock_gains)
    y_mf = _yearly_capital_net(mf_gains)
    y_mf_div = _yearly_income_from_records(mf_dividend_records, "Date")
    y_fi = _yearly_capital_net(fi_gains)
    y_fi_int = _yearly_income_from_records(fi_interest_records, "Date")
    y_prop = _yearly_property_gains(property_assets)

    years = merge_years(
        y_stocks, y_mf, y_mf_div, y_fi, y_fi_int, y_prop
    )

    yearly_rows = []
    for y in years:
        s_net = y_stocks.get(y, 0.0)
        mf_net = y_mf.get(y, 0.0)
        mf_inc = y_mf_div.get(y, 0.0)
        fi_net = y_fi.get(y, 0.0)
        fi_inc = y_fi_int.get(y, 0.0)
        p_net = y_prop.get(y, 0.0)
        cap_total = s_net + mf_net + fi_net + p_net
        yearly_rows.append(
            {
                "year": y,
                "stocks_capital": s_net,
                "mf_capital": mf_net,
                "mf_income": mf_inc,
                "fi_capital": fi_net,
                "fi_income": fi_inc,
                "property_capital": p_net,
                "capital_total": cap_total,
                "income_total": mf_inc + fi_inc,
            }
        )

    def pos_rows(positions: Optional[List[Position]], asset_class: str) -> List[Dict[str, Any]]:
        rows = []
        for p in positions or []:
            rows.append(
                {
                    "asset_class": asset_class,
                    "symbol": p.symbol,
                    "name": "",
                    "quantity": p.quantity,
                    "price": p.price,
                    "date": p.date,
                    "total_cost": p.total_cost,
                }
            )
        return rows

    holdings_stock = pos_rows(stock_positions, "Stocks")
    holdings_mf = pos_rows(mf_positions, "Mutual funds")
    holdings_fi = pos_rows(fi_positions, "Fixed income")

    holdings_property = []
    for a in property_assets or []:
        if a.get("disposition_date") is not None:
            continue
        holdings_property.append(
            {
                "asset_class": "Property / assets",
                "symbol": "",
                "name": a.get("name", ""),
                "type": a.get("asset_type", ""),
                "quantity": None,
                "price": None,
                "date": a.get("acquisition_date"),
                "total_cost": float(a.get("cost_basis", 0)),
                "notes": a.get("notes", ""),
            }
        )

    total_capital_all_years = sum(r["capital_total"] for r in yearly_rows)
    total_income_all_years = sum(r["income_total"] for r in yearly_rows)

    return {
        "years": years,
        "yearly_rows": yearly_rows,
        "holdings_stock": holdings_stock,
        "holdings_mf": holdings_mf,
        "holdings_fi": holdings_fi,
        "holdings_property": holdings_property,
        "has_any_data": bool(
            years
            or holdings_stock
            or holdings_mf
            or holdings_fi
            or holdings_property
        ),
        "totals": {
            "capital_realized": total_capital_all_years,
            "income_coupon_dividend": total_income_all_years,
        },
    }
