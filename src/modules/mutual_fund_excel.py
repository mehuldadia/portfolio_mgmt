"""Create and read Excel workbooks for mutual-fund transactions."""

from io import BytesIO
import math

import pandas as pd

from .mutual_fund_transactions import build_dividend_record, build_trade_record


STATEMENT_COLUMNS = [
    "MF_NAME",
    "INVESTOR_NAME",
    "PAN",
    "FOLIO_NUMBER",
    "PRODUCT_CODE",
    "SCHEME_NAME",
    "Scheme Type",
    "TRADE_DATE",
    "TRANSACTION_TYPE",
    "DIVIDEND_RATE",
    "AMOUNT",
    "UNITS",
    "PRICE",
    "BROKER",
]


def create_mutual_fund_template() -> BytesIO:
    """Return an empty workbook using the user's mutual-fund statement columns."""
    workbook = BytesIO()
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        pd.DataFrame(columns=STATEMENT_COLUMNS).to_excel(
            writer, sheet_name="Transactions", index=False
        )
    workbook.seek(0)
    return workbook


def _normalize_header(header) -> str:
    return "_".join(str(header).strip().lower().replace("-", " ").split())


def _canonicalize_columns(frame, aliases, required, sheet_name):
    source_columns = {_normalize_header(column): column for column in frame.columns}
    selected = {}
    for canonical, alternatives in aliases.items():
        for alternative in alternatives:
            source = source_columns.get(_normalize_header(alternative))
            if source is not None:
                selected[source] = canonical
                break

    missing = [column for column in required if column not in selected.values()]
    if missing:
        raise ValueError(
            f"Sheet '{sheet_name}' is missing required columns: {', '.join(missing)}"
        )

    return frame.rename(columns=selected)[list(selected.values())]


def _required_text(value, label, sheet_name, row_number):
    if pd.isna(value) or not str(value).strip():
        raise ValueError(f"Sheet '{sheet_name}', row {row_number}: {label} is required")
    return str(value).strip()


def _optional_text(value):
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _number(value, label, sheet_name, row_number, *, optional=False):
    if optional and (pd.isna(value) or not str(value).strip()):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"Sheet '{sheet_name}', row {row_number}: {label} must be a number"
        ) from None
    if not math.isfinite(number):
        raise ValueError(
            f"Sheet '{sheet_name}', row {row_number}: {label} must be a finite number"
        )
    return number


def _date(value, label, sheet_name, row_number):
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"Sheet '{sheet_name}', row {row_number}: invalid {label}")
    return parsed.to_pydatetime()


def _optional_number(value, label, sheet_name, row_number):
    if pd.isna(value) or not str(value).strip():
        return None
    return _number(value, label, sheet_name, row_number)


def _read_statement_rows(frame, sheet_name):
    aliases = {
        "mf_name": ("MF_NAME",),
        "investor_name": ("INVESTOR_NAME",),
        "pan": ("PAN",),
        "folio_number": ("FOLIO_NUMBER",),
        "product_code": ("PRODUCT_CODE",),
        "scheme_name": ("SCHEME_NAME", "Fund_Name", "ISIN_Name"),
        "scheme_type": ("Scheme Type", "Scheme_Type"),
        "txn_date": ("TRADE_DATE", "Txn_Date", "Transaction Date", "Date"),
        "txn_type": ("TRANSACTION_TYPE", "Type", "Action"),
        "dividend_rate": ("DIVIDEND_RATE", "Dividend Rate"),
        "amount": ("AMOUNT", "Amount"),
        "quantity": ("UNITS", "Quantity", "Qty"),
        "price": ("PRICE", "NAV", "Unit Price"),
        "broker": ("BROKER",),
        "legacy_isin": ("ISIN", "ISIN Code", "Symbol"),
        "fees": ("Fees", "Charges"),
    }
    frame = _canonicalize_columns(
        frame,
        aliases,
        ("txn_date", "txn_type"),
        sheet_name,
    )
    records = []
    dividends = []
    trade_kinds = {
        "buy": "purchase",
        "purchase": "purchase",
        "sip": "purchase",
        "switch in": "purchase",
        "switch-in": "purchase",
        "allotment": "purchase",
        "sell": "redemption",
        "redemption": "redemption",
        "switch out": "redemption",
        "switch-out": "redemption",
        "withdrawal": "redemption",
    }
    dividend_kinds = {"dividend", "dividend payout", "idcw", "idcw payout"}
    metadata_fields = {
        "MF_Name": "mf_name",
        "Investor_Name": "investor_name",
        "PAN": "pan",
        "Folio_Number": "folio_number",
        "Product_Code": "product_code",
        "Scheme_Name": "scheme_name",
        "Scheme_Type": "scheme_type",
        "Dividend_Rate": "dividend_rate",
        "Broker": "broker",
    }

    for row_number, row in enumerate(frame.itertuples(index=False, name=None), start=2):
        if all(pd.isna(value) for value in row):
            continue
        values = dict(zip(frame.columns, row))
        txn_type = _required_text(
            values["txn_type"], "TRANSACTION_TYPE", sheet_name, row_number
        )
        normalized_type = " ".join(txn_type.strip().lower().replace("_", " ").split())
        scheme_name = _optional_text(values.get("scheme_name"))
        mf_name = _optional_text(values.get("mf_name"))
        fund_name = scheme_name or mf_name
        if not fund_name:
            raise ValueError(
                f"Sheet '{sheet_name}', row {row_number}: SCHEME_NAME or MF_NAME is required"
            )
        product_code = _optional_text(values.get("product_code"))
        isin = product_code or _optional_text(values.get("legacy_isin"))
        txn_date = _date(values["txn_date"], "TRADE_DATE", sheet_name, row_number)

        if normalized_type in dividend_kinds:
            amount = _number(values.get("amount"), "AMOUNT", sheet_name, row_number)
            record = build_dividend_record(txn_date, fund_name, amount, isin)
            for record_field, value_field in metadata_fields.items():
                value = values.get(value_field)
                record[record_field] = (
                    _optional_number(value, value_field, sheet_name, row_number)
                    if value_field == "dividend_rate"
                    else _optional_text(value)
                )
            dividends.append(record)
            continue

        kind = trade_kinds.get(normalized_type)
        if kind is None:
            raise ValueError(
                f"Sheet '{sheet_name}', row {row_number}: unsupported TRANSACTION_TYPE '{txn_type}'"
            )
        quantity = _number(values.get("quantity"), "UNITS", sheet_name, row_number)
        price = _number(values.get("price"), "PRICE", sheet_name, row_number)
        fees = _number(values.get("fees", 0), "Fees", sheet_name, row_number, optional=True)
        if fees < 0:
            raise ValueError(f"Sheet '{sheet_name}', row {row_number}: Fees cannot be negative")
        record = build_trade_record(txn_date, fund_name, isin, kind, quantity, price, fees)
        amount = _optional_number(values.get("amount"), "AMOUNT", sheet_name, row_number)
        if amount is not None:
            record["Amount"] = amount
        for record_field, value_field in metadata_fields.items():
            value = values.get(value_field)
            record[record_field] = (
                _optional_number(value, value_field, sheet_name, row_number)
                if value_field == "dividend_rate"
                else _optional_text(value)
            )
        records.append(record)

    return records, dividends


def _read_trade_rows(frame, sheet_name):
    aliases = {
        "txn_date": ("Txn_Date", "Transaction Date", "Date"),
        "fund_name": ("Fund_Name", "Fund Name", "Scheme", "ISIN_Name"),
        "isin": ("ISIN", "ISIN Code", "Symbol"),
        "txn_type": ("Type", "Transaction Type", "Action"),
        "quantity": ("Quantity", "Units", "Qty"),
        "price": ("Price", "NAV", "Unit Price"),
        "fees": ("Fees", "Charges"),
    }
    frame = _canonicalize_columns(
        frame,
        aliases,
        ("txn_date", "fund_name", "txn_type", "quantity", "price"),
        sheet_name,
    )
    records = []
    for row_number, row in enumerate(frame.itertuples(index=False, name=None), start=2):
        if all(pd.isna(value) for value in row):
            continue
        values = dict(zip(frame.columns, row))
        kind_value = _required_text(values["txn_type"], "Type", sheet_name, row_number)
        kind = kind_value.strip().lower()
        if kind in {"buy", "purchase"}:
            kind = "purchase"
        elif kind in {"sell", "redemption"}:
            kind = "redemption"
        else:
            raise ValueError(
                f"Sheet '{sheet_name}', row {row_number}: Type must be Purchase/Buy or Redemption/Sell"
            )

        fees = _number(
            values.get("fees", 0), "Fees", sheet_name, row_number, optional=True
        )
        if fees < 0:
            raise ValueError(f"Sheet '{sheet_name}', row {row_number}: Fees cannot be negative")

        records.append(
            build_trade_record(
                _date(values["txn_date"], "date", sheet_name, row_number),
                _required_text(values["fund_name"], "Fund_Name", sheet_name, row_number),
                _optional_text(values.get("isin")),
                kind,
                _number(values["quantity"], "Quantity", sheet_name, row_number),
                _number(values["price"], "Price/NAV", sheet_name, row_number),
                fees,
            )
        )
    return records


def _read_dividend_rows(frame, sheet_name):
    aliases = {
        "date": ("Date", "Dividend Date"),
        "fund_name": ("Fund_Name", "Fund Name", "Scheme", "ISIN_Name"),
        "isin": ("ISIN", "ISIN Code", "Symbol"),
        "amount": ("Amount", "Dividend Amount"),
        "notes": ("Notes", "Description"),
    }
    frame = _canonicalize_columns(
        frame, aliases, ("date", "fund_name", "amount"), sheet_name
    )
    records = []
    for row_number, row in enumerate(frame.itertuples(index=False, name=None), start=2):
        if all(pd.isna(value) for value in row):
            continue
        values = dict(zip(frame.columns, row))
        records.append(
            build_dividend_record(
                _date(values["date"], "date", sheet_name, row_number),
                _required_text(values["fund_name"], "Fund_Name", sheet_name, row_number),
                _number(values["amount"], "Amount", sheet_name, row_number),
                _optional_text(values.get("isin")),
                _optional_text(values.get("notes")),
            )
        )
    return records


def read_mutual_fund_transactions(file_obj):
    """Read a mutual-fund workbook and return (trade_records, dividend_records)."""
    try:
        sheets = pd.read_excel(file_obj, sheet_name=None)
    except Exception as exc:
        raise ValueError(f"Could not read mutual-fund workbook: {exc}") from exc
    if not sheets:
        raise ValueError("The workbook contains no worksheets")

    statement_sheet = next(
        (
            name
            for name, frame in sheets.items()
            if {"trade_date", "transaction_type"}.issubset(
                {_normalize_header(column) for column in frame.columns}
            )
        ),
        None,
    )
    if statement_sheet is not None:
        trades, dividends = _read_statement_rows(
            sheets[statement_sheet], statement_sheet
        )
        if not trades and not dividends:
            raise ValueError("The workbook contains no mutual-fund transactions or dividends")
        return trades, dividends

    trade_names = {"transactions", "trades", "mf_trades"}
    dividend_names = {"dividends", "mf_dividends"}
    trade_sheet = next(
        (name for name in sheets if _normalize_header(name) in trade_names), None
    )
    dividend_sheet = next(
        (name for name in sheets if _normalize_header(name) in dividend_names), None
    )

    if trade_sheet is None:
        trade_sheet = next(
            (name for name in sheets if _normalize_header(name) not in dividend_names),
            None,
        )

    trades = _read_trade_rows(sheets[trade_sheet], trade_sheet) if trade_sheet else []
    dividends = (
        _read_dividend_rows(sheets[dividend_sheet], dividend_sheet)
        if dividend_sheet
        else []
    )
    if not trades and not dividends:
        raise ValueError("The workbook contains no mutual-fund transactions or dividends")
    return trades, dividends