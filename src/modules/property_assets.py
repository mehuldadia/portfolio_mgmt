"""Property and other fixed-asset holdings (cost basis and optional disposition)."""

from datetime import datetime
from typing import Any, Dict, List, Optional


def build_property_asset(
    name: str,
    asset_type: str,
    acquisition_date: datetime,
    cost_basis: float,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    if not (name or "").strip():
        raise ValueError("Asset name is required")
    if cost_basis < 0:
        raise ValueError("Cost basis cannot be negative")
    return {
        "name": (name or "").strip(),
        "asset_type": (asset_type or "other").strip().lower(),
        "acquisition_date": acquisition_date,
        "cost_basis": float(cost_basis),
        "notes": (notes or "").strip(),
        "disposition_date": None,
        "disposition_proceeds": None,
    }


def record_disposition(
    asset: Dict[str, Any],
    disposition_date: datetime,
    disposition_proceeds: float,
) -> None:
    if disposition_proceeds < 0:
        raise ValueError("Proceeds cannot be negative")
    asset["disposition_date"] = disposition_date
    asset["disposition_proceeds"] = float(disposition_proceeds)


def realized_gain(asset: Dict[str, Any]) -> Optional[float]:
    if asset.get("disposition_date") is None or asset.get("disposition_proceeds") is None:
        return None
    return float(asset["disposition_proceeds"]) - float(asset["cost_basis"])


def is_held(asset: Dict[str, Any]) -> bool:
    return asset.get("disposition_date") is None
