"""
Flask web application: stocks, mutual funds, fixed income, property, unified dashboard.
"""

from flask import Flask, render_template, request, jsonify, send_file, flash, redirect, url_for
from io import BytesIO
import os
from datetime import datetime
import tempfile
import uuid
import json
import sqlite3
import pandas as pd
from werkzeug.utils import secure_filename

from modules.transaction_reader import TransactionReader
from modules.gains_calculator import GainsCalculator
from modules.excel_exporter import ExcelExporter
from modules.dashboard_aggregator import build_dashboard_context
from modules.mutual_fund_transactions import (
    build_dividend_record,
    build_trade_record,
    dividend_records_to_dataframe,
    trade_records_to_dataframe,
)
from modules.mutual_fund_excel import (
    create_mutual_fund_template,
    read_mutual_fund_transactions,
)
from modules.fixed_income_transactions import (
    build_fi_trade_record,
    build_interest_record,
    fi_interest_to_dataframe,
)
from modules.property_assets import build_property_asset, record_disposition
from modules.portfolio_store import PortfolioStore
from modules.currency import format_inr

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(APP_DIR)

app = Flask(
    __name__,
    template_folder=os.path.join(APP_DIR, "templates"),
    static_folder=os.path.join(APP_DIR, "static"),
)
app.secret_key = "your-secret-key-here"
app.jinja_env.filters["inr"] = format_inr

UPLOAD_FOLDER = os.path.join(PROJECT_DIR, "data")
OUTPUT_FOLDER = os.path.join(PROJECT_DIR, "output")
ALLOWED_EXTENSIONS = {"xlsx", "xls"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(os.path.join(APP_DIR, "templates"), exist_ok=True)
os.makedirs(os.path.join(APP_DIR, "static", "css"), exist_ok=True)
os.makedirs(os.path.join(APP_DIR, "static", "js"), exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["OUTPUT_FOLDER"] = OUTPUT_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

transaction_reader = TransactionReader()
gains_calculator = GainsCalculator()
excel_exporter = ExcelExporter(OUTPUT_FOLDER)

current_transactions = None
current_gains = None
current_positions = None
current_summary = None

mf_trade_records = []
mf_dividend_records = []
mf_gains = None
mf_positions = None
mf_summary = None

fi_trade_records = []
fi_interest_records = []
fi_gains = None
fi_positions = None
fi_summary = None

property_portfolio = []

portfolio_store = PortfolioStore(os.path.join(UPLOAD_FOLDER, "portfolio.sqlite3"))
pending_imports = {}
active_investor = portfolio_store.get_active_investor()
active_investor_pan = active_investor["pan"] if active_investor else None


def _restore_record_dates(records, fields):
    for record in records:
        for field in fields:
            value = record.get(field)
            if value:
                record[field] = datetime.fromisoformat(value)
    return records


def _load_saved_portfolio():
    global current_transactions, current_gains, current_positions, current_summary

    current_transactions = current_gains = current_positions = current_summary = None
    mf_trade_records.clear()
    mf_dividend_records.clear()
    fi_trade_records.clear()
    fi_interest_records.clear()
    property_portfolio.clear()

    if not active_investor_pan:
        _sync_fifo_analyses()
        return

    stock_records = portfolio_store.load("stock_transactions", active_investor_pan)
    if stock_records:
        current_transactions = pd.DataFrame(stock_records)
        current_transactions["Txn_Date"] = pd.to_datetime(current_transactions["Txn_Date"])
        current_gains, current_positions = gains_calculator.calculate_gains(
            current_transactions
        )
        current_summary = gains_calculator.get_gains_summary(current_gains)

    mf_trade_records.extend(_restore_record_dates(portfolio_store.load("mf_trades", active_investor_pan), ("Txn_Date",)))
    mf_dividend_records.extend(_restore_record_dates(portfolio_store.load("mf_dividends", active_investor_pan), ("Date",)))
    fi_trade_records.extend(_restore_record_dates(portfolio_store.load("fi_trades", active_investor_pan), ("Txn_Date",)))
    fi_interest_records.extend(_restore_record_dates(portfolio_store.load("fi_interest", active_investor_pan), ("Date",)))
    property_portfolio.extend(
        _restore_record_dates(
            portfolio_store.load("property_assets", active_investor_pan),
            ("acquisition_date", "disposition_date"),
        )
    )
    _sync_fifo_analyses()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _sync_fifo_analyses():
    """Recompute FIFO gains/positions for MF and FI from trade lists."""
    global mf_gains, mf_positions, mf_summary, fi_gains, fi_positions, fi_summary
    dfm = trade_records_to_dataframe(mf_trade_records)
    if dfm.empty:
        mf_gains, mf_positions, mf_summary = None, None, None
    else:
        mf_gains, mf_positions = gains_calculator.calculate_gains(dfm)
        mf_summary = gains_calculator.get_gains_summary(mf_gains)

    dfi = trade_records_to_dataframe(fi_trade_records)
    if dfi.empty:
        fi_gains, fi_positions, fi_summary = None, None, None
    else:
        fi_gains, fi_positions = gains_calculator.calculate_gains(dfi)
        fi_summary = gains_calculator.get_gains_summary(fi_gains)


def _activate_investor(pan):
    global active_investor, active_investor_pan
    portfolio_store.set_active_investor(pan)
    active_investor = portfolio_store.get_active_investor()
    active_investor_pan = active_investor["pan"] if active_investor else None
    _load_saved_portfolio()


_load_saved_portfolio()


@app.before_request
def require_active_investor():
    if request.endpoint in {"static", "investors", "create_investor", "switch_investor"}:
        return None
    if not active_investor_pan:
        flash("Create or select an investor to open a portfolio.", "info")
        return redirect(url_for("investors"))
    return None


@app.context_processor
def inject_investor_navigation():
    return {
        "active_investor": active_investor,
        "available_investors": portfolio_store.list_investors(),
    }


@app.route("/investors")
def investors():
    return render_template(
        "investors.html",
        investors=portfolio_store.list_investors(),
        active_pan=active_investor_pan,
    )


@app.route("/investors/create", methods=["POST"])
def create_investor():
    try:
        investor = portfolio_store.create_investor(
            request.form.get("pan", ""), request.form.get("name", "")
        )
        if active_investor_pan is None:
            _activate_investor(investor["pan"])
        flash(f"Investor {investor['name']} ({investor['pan']}) added.", "success")
    except sqlite3.IntegrityError:
        flash("An investor with this PAN already exists.", "error")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("investors"))


@app.route("/investors/select", methods=["POST"])
def switch_investor():
    try:
        _activate_investor(request.form.get("pan", ""))
        flash(f"Switched to {active_investor['name']} ({active_investor_pan}).", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("investors"))


def _parse_date(s: str) -> datetime:
    if not s:
        raise ValueError("Date is required")
    return datetime.strptime(s.strip(), "%Y-%m-%d")


def _gains_to_json(gains):
    if gains is None:
        return []
    out = []
    for gain in gains:
        out.append(
            {
                "symbol": gain.symbol,
                "sell_date": gain.sell_date.strftime("%Y-%m-%d"),
                "sell_quantity": gain.sell_quantity,
                "sell_price": gain.sell_price,
                "sell_total": gain.sell_total,
                "buy_date": gain.buy_date.strftime("%Y-%m-%d"),
                "buy_quantity": gain.buy_quantity,
                "buy_price": gain.buy_price,
                "buy_total": gain.buy_total,
                "gain_loss": gain.gain_loss,
                "tax_classification": "Short-term"
                if gain.is_short_term
                else "Long-term",
                "holding_period_days": gain.holding_period_days,
            }
        )
    return out


def _pending_import_page(token):
    if token not in pending_imports:
        flash("This import preview has expired. Please upload the file again.", "error")
        return redirect(url_for("dashboard"))
    return render_template("import_review.html", **pending_imports[token]["view"])


def _save_pending_import(token):
    global current_transactions, current_gains, current_positions, current_summary

    pending = pending_imports.get(token)
    if pending is None:
        raise ValueError("This import preview has expired. Please upload the file again.")
    if pending["investor_pan"] != active_investor_pan:
        raise ValueError("This preview belongs to another investor. Switch investors and retry.")

    batch_id = uuid.uuid4().hex
    uploads_dir = os.path.join(app.config["UPLOAD_FOLDER"], "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    stored_filename = f"{batch_id}_{secure_filename(pending['filename'])}"
    stored_path = os.path.join(uploads_dir, stored_filename)
    with open(stored_path, "xb") as saved_file:
        saved_file.write(pending["file_bytes"])

    batch = {
        "batch_id": batch_id,
        "asset_type": pending["asset_type"],
        "original_filename": pending["filename"],
        "stored_filename": stored_filename,
        "imported_at": datetime.now().isoformat(timespec="seconds"),
        "record_count": pending["record_count"],
    }
    try:
        if pending["asset_type"] == "stocks":
            transactions = pd.DataFrame(pending["records"])
            transactions["Txn_Date"] = pd.to_datetime(transactions["Txn_Date"])
            gains, positions = gains_calculator.calculate_gains(transactions)
            summary = gains_calculator.get_gains_summary(gains)
            portfolio_store.replace_many(
                {"stock_transactions": pending["records"]},
                import_batch=batch,
                investor_pan=pending["investor_pan"],
            )
            current_transactions = transactions
            current_gains, current_positions, current_summary = gains, positions, summary
            destination = "stocks"
        else:
            trades = mf_trade_records + pending["records"].get("mf_trades", [])
            dividends = mf_dividend_records + pending["records"].get("mf_dividends", [])
            portfolio_store.replace_many(
                {"mf_trades": trades, "mf_dividends": dividends},
                import_batch=batch,
                investor_pan=pending["investor_pan"],
            )
            mf_trade_records[:] = trades
            mf_dividend_records[:] = dividends
            _sync_fifo_analyses()
            destination = "mutual_funds"
    except Exception:
        os.remove(stored_path)
        raise

    pending_imports.pop(token, None)
    return destination


@app.route("/imports/<token>")
def review_import(token):
    return _pending_import_page(token)


@app.route("/imports/<token>/save", methods=["POST"])
def save_import(token):
    try:
        destination = _save_pending_import(token)
    except Exception as exc:
        flash(f"Could not save import: {exc}", "error")
        return redirect(url_for("review_import", token=token))
    flash("Import saved to the local portfolio database.", "success")
    return redirect(url_for(destination))


@app.route("/imports/<token>/discard", methods=["POST"])
def discard_import(token):
    pending = pending_imports.pop(token, None)
    flash("Import discarded; saved portfolio data was not changed.", "info")
    destination = "mutual_funds" if pending and pending["asset_type"] == "mutual_funds" else "stocks"
    return redirect(url_for(destination))


@app.route("/")
def dashboard():
    _sync_fifo_analyses()
    ctx = build_dashboard_context(
        current_gains,
        current_positions,
        mf_gains,
        mf_positions,
        mf_dividend_records,
        fi_gains,
        fi_positions,
        fi_interest_records,
        property_portfolio,
    )
    ctx["has_stocks"] = current_summary is not None
    ctx["mf_trade_count"] = len(mf_trade_records)
    return render_template("dashboard.html", **ctx)


@app.route("/stocks")
def stocks():
    stock_yearly = (
        gains_calculator.get_yearly_summary(current_gains)
        if current_gains is not None
        else {}
    )
    return render_template(
        "stocks.html",
        stock_summary=current_summary,
        stock_yearly=stock_yearly,
    )


@app.route("/upload", methods=["POST"])
def upload_file():
    global current_transactions, current_gains, current_positions, current_summary

    if "file" not in request.files:
        flash("No file selected")
        return redirect(url_for("stocks"))

    file = request.files["file"]
    if file.filename == "":
        flash("No file selected")
        return redirect(url_for("stocks"))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename) or "stock-transactions.xlsx"
        file_bytes = file.stream.read()
        suffix = os.path.splitext(filename)[1].lower()
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
                temp_path = temp_file.name
                temp_file.write(file_bytes)
            transactions = transaction_reader.read_transactions(temp_path)
            if transactions.empty:
                raise ValueError("The workbook contains no stock transactions")
            warnings = transaction_reader.validate_transactions(transactions)
            preview_gains, preview_positions = gains_calculator.calculate_gains(
                transactions
            )
            preview_summary = gains_calculator.get_gains_summary(preview_gains)

            records = json.loads(
                transactions.to_json(orient="records", date_format="iso")
            )
            token = uuid.uuid4().hex
            pending_imports[token] = {
                "asset_type": "stocks",
                "investor_pan": active_investor_pan,
                "filename": filename,
                "file_bytes": file_bytes,
                "records": records,
                "record_count": len(records),
                "view": {
                    "title": "Review stock import",
                    "filename": filename,
                    "collections": [
                        {"name": "Stock transactions", "count": len(records), "records": records[:25]}
                    ],
                    "warnings": warnings,
                    "preview_summary": preview_summary,
                    "position_count": len(preview_positions),
                    "token": token,
                },
            }
            return redirect(url_for("review_import", token=token))
        except Exception as e:
            flash(f"Error processing file: {str(e)}", "error")
            return redirect(url_for("stocks"))
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    flash("Invalid file type. Please upload an Excel file (.xlsx or .xls)")
    return redirect(url_for("stocks"))


@app.route("/summary")
def summary():
    """Legacy URL: same content as /stocks (capital gains section)."""
    if current_summary is None:
        flash("No stock data. Upload a file below.")
        return redirect(url_for("stocks"))
    return redirect(url_for("stocks") + "#stock-results")


@app.route("/api/summary")
def api_summary():
    if current_summary is None:
        return jsonify({"error": "No data available"}), 400
    return jsonify(current_summary)


@app.route("/api/yearly")
def api_yearly():
    if current_gains is None:
        return jsonify({"error": "No data available"}), 400
    return jsonify(gains_calculator.get_yearly_summary(current_gains))


@app.route("/api/gains")
def api_gains():
    if current_gains is None:
        return jsonify({"error": "No data available"}), 400
    return jsonify(_gains_to_json(current_gains))


@app.route("/export/excel")
def export_excel():
    if current_gains is None:
        flash("No data available to export")
        return redirect(url_for("stocks"))
    try:
        filepath = excel_exporter.export_capital_gains(current_gains, current_positions)
        return send_file(filepath, as_attachment=True)
    except Exception as e:
        flash(f"Error exporting file: {str(e)}", "error")
        return redirect(url_for("stocks") + "#stock-results")


@app.route("/export/transactions")
def export_transactions():
    if current_transactions is None:
        flash("No transaction data available to export")
        return redirect(url_for("stocks"))
    try:
        filepath = excel_exporter.export_transaction_summary(current_transactions)
        return send_file(filepath, as_attachment=True)
    except Exception as e:
        flash(f"Error exporting file: {str(e)}", "error")
        return redirect(url_for("stocks") + "#stock-results")


@app.route("/charts")
def charts():
    if current_summary is None:
        flash("Charts need stock data. Upload from the Stocks page.")
        return redirect(url_for("stocks"))
    return render_template("charts.html")


# --- Mutual funds ---


@app.route("/mutual-funds")
def mutual_funds():
    _sync_fifo_analyses()
    div_df = dividend_records_to_dataframe(mf_dividend_records)
    dividend_total = float(div_df["Amount"].sum()) if not div_df.empty else 0.0
    return render_template(
        "mutual_funds.html",
        mf_trades=mf_trade_records,
        mf_dividends=mf_dividend_records,
        mf_trade_count=len(mf_trade_records),
        mf_dividend_count=len(mf_dividend_records),
        dividend_total=dividend_total,
        has_mf_analysis=bool(mf_trade_records),
    )


@app.route("/mutual-funds/template")
def mutual_funds_template():
    """Download an Excel template with the supported mutual-fund columns."""
    return send_file(
        create_mutual_fund_template(),
        as_attachment=True,
        download_name="mutual_fund_transactions_template.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/mutual-funds/upload", methods=["POST"])
def mutual_funds_upload():
    """Validate and import a mutual-fund transaction workbook."""
    if "file" not in request.files:
        flash("Select a mutual-fund Excel file to upload.", "error")
        return redirect(url_for("mutual_funds"))

    uploaded_file = request.files["file"]
    if not uploaded_file.filename:
        flash("Select a mutual-fund Excel file to upload.", "error")
        return redirect(url_for("mutual_funds"))
    if not allowed_file(uploaded_file.filename):
        flash("Invalid file type. Upload an Excel file (.xlsx or .xls).", "error")
        return redirect(url_for("mutual_funds"))

    try:
        file_bytes = uploaded_file.stream.read()
        trades, dividends = read_mutual_fund_transactions(BytesIO(file_bytes))
        filename = secure_filename(uploaded_file.filename) or "mutual-fund-transactions.xlsx"
        trade_preview = json.loads(
            pd.DataFrame(trades).to_json(orient="records", date_format="iso")
        ) if trades else []
        dividend_preview = json.loads(
            pd.DataFrame(dividends).to_json(orient="records", date_format="iso")
        ) if dividends else []
        token = uuid.uuid4().hex
        pending_imports[token] = {
            "asset_type": "mutual_funds",
            "investor_pan": active_investor_pan,
            "filename": filename,
            "file_bytes": file_bytes,
            "records": {"mf_trades": trades, "mf_dividends": dividends},
            "record_count": len(trades) + len(dividends),
            "view": {
                "title": "Review mutual-fund import",
                "filename": filename,
                "collections": [
                    {"name": "Mutual-fund trades", "count": len(trade_preview), "records": trade_preview[:25]},
                    {"name": "Dividends", "count": len(dividend_preview), "records": dividend_preview[:25]},
                ],
                "warnings": [],
                "token": token,
            },
        }
        return redirect(url_for("review_import", token=token))
    except Exception as exc:
        flash(f"Could not import workbook: {exc}", "error")
    return redirect(url_for("mutual_funds"))


@app.route("/mutual-funds/trade", methods=["POST"])
def mutual_funds_add_trade():
    try:
        txn_date = _parse_date(request.form.get("txn_date", ""))
        fund_name = request.form.get("fund_name", "").strip()
        isin = request.form.get("isin", "").strip() or None
        txn_kind = request.form.get("txn_kind", "purchase")
        units = float(request.form.get("units", "") or 0)
        nav = float(request.form.get("nav", "") or 0)
        fees = float(request.form.get("fees", "") or 0)
        if not fund_name:
            raise ValueError("Fund / scheme name is required")
        rec = build_trade_record(
            txn_date, fund_name, isin, txn_kind, units, nav, fees
        )
        portfolio_store.replace_many({"mf_trades": mf_trade_records + [rec]})
        mf_trade_records.append(rec)
        _sync_fifo_analyses()
        flash("Mutual fund transaction added.", "success")
    except Exception as e:
        flash(f"Could not add transaction: {e}", "error")
    return redirect(url_for("mutual_funds"))


@app.route("/mutual-funds/dividend", methods=["POST"])
def mutual_funds_add_dividend():
    try:
        div_date = _parse_date(request.form.get("div_date", ""))
        fund_name = request.form.get("div_fund_name", "").strip()
        amount = float(request.form.get("div_amount", "") or 0)
        isin = request.form.get("div_isin", "").strip() or None
        notes = request.form.get("div_notes", "").strip() or None
        if not fund_name:
            raise ValueError("Fund / scheme name is required")
        rec = build_dividend_record(div_date, fund_name, amount, isin, notes)
        portfolio_store.replace_many({"mf_dividends": mf_dividend_records + [rec]})
        mf_dividend_records.append(rec)
        flash("Dividend recorded.", "success")
    except Exception as e:
        flash(f"Could not add dividend: {e}", "error")
    return redirect(url_for("mutual_funds"))


@app.route("/mutual-funds/delete-trade/<int:index>", methods=["POST"])
def mutual_funds_delete_trade(index: int):
    if 0 <= index < len(mf_trade_records):
        records = mf_trade_records.copy()
        records.pop(index)
        portfolio_store.replace_many({"mf_trades": records})
        mf_trade_records[:] = records
        _sync_fifo_analyses()
        flash("Transaction removed.", "success")
    else:
        flash("Invalid row index.", "error")
    return redirect(url_for("mutual_funds"))


@app.route("/mutual-funds/delete-dividend/<int:index>", methods=["POST"])
def mutual_funds_delete_dividend(index: int):
    if 0 <= index < len(mf_dividend_records):
        records = mf_dividend_records.copy()
        records.pop(index)
        portfolio_store.replace_many({"mf_dividends": records})
        mf_dividend_records[:] = records
        flash("Dividend removed.", "success")
    else:
        flash("Invalid row index.", "error")
    return redirect(url_for("mutual_funds"))


@app.route("/mutual-funds/clear", methods=["POST"])
def mutual_funds_clear():
    which = request.form.get("which", "trades")
    if which == "trades":
        portfolio_store.replace_many({"mf_trades": []})
        mf_trade_records.clear()
        flash("All mutual fund trades cleared.", "success")
    elif which == "dividends":
        portfolio_store.replace_many({"mf_dividends": []})
        mf_dividend_records.clear()
        flash("All dividends cleared.", "success")
    else:
        portfolio_store.replace_many({"mf_trades": [], "mf_dividends": []})
        mf_trade_records.clear()
        mf_dividend_records.clear()
        flash("All mutual fund data cleared.", "success")
    _sync_fifo_analyses()
    return redirect(url_for("mutual_funds"))


@app.route("/mutual-funds/analyze", methods=["POST"])
def mutual_funds_analyze():
    _sync_fifo_analyses()
    if not mf_trade_records:
        flash("Add at least one purchase or redemption first.", "error")
        return redirect(url_for("mutual_funds"))
    return redirect(url_for("mutual_funds_summary"))


@app.route("/mutual-funds/summary")
def mutual_funds_summary():
    _sync_fifo_analyses()
    if mf_summary is None:
        flash("Add mutual fund trades first.", "warning")
        return redirect(url_for("mutual_funds"))
    return render_template(
        "mf_summary.html",
        summary=mf_summary,
        yearly_data=gains_calculator.get_yearly_summary(mf_gains),
    )


@app.route("/export/mf-ledger")
def export_mf_ledger():
    trades_df = trade_records_to_dataframe(mf_trade_records)
    div_df = dividend_records_to_dataframe(mf_dividend_records)
    if trades_df.empty and div_df.empty:
        flash("No mutual fund data to export.", "error")
        return redirect(url_for("mutual_funds"))
    try:
        filepath = excel_exporter.export_mutual_fund_ledger(trades_df, div_df)
        return send_file(filepath, as_attachment=True)
    except Exception as e:
        flash(f"Export failed: {e}", "error")
        return redirect(url_for("mutual_funds"))


@app.route("/export/mf-gains")
def export_mf_gains():
    _sync_fifo_analyses()
    if mf_gains is None:
        flash("No mutual fund gains to export.", "error")
        return redirect(url_for("mutual_funds"))
    try:
        filepath = excel_exporter.export_capital_gains(mf_gains, mf_positions)
        return send_file(filepath, as_attachment=True)
    except Exception as e:
        flash(f"Export failed: {e}", "error")
        return redirect(url_for("mutual_funds_summary"))


@app.route("/api/mf/gains")
def api_mf_gains():
    _sync_fifo_analyses()
    if mf_gains is None:
        return jsonify({"error": "No mutual fund gains data"}), 400
    return jsonify(_gains_to_json(mf_gains))


# --- Fixed income ---


@app.route("/fixed-income")
def fixed_income():
    _sync_fifo_analyses()
    int_df = fi_interest_to_dataframe(fi_interest_records)
    interest_total = float(int_df["Amount"].sum()) if not int_df.empty else 0.0
    return render_template(
        "fixed_income.html",
        fi_trades=fi_trade_records,
        fi_interest=fi_interest_records,
        fi_trade_count=len(fi_trade_records),
        fi_interest_count=len(fi_interest_records),
        interest_total=interest_total,
    )


@app.route("/fixed-income/trade", methods=["POST"])
def fixed_income_add_trade():
    try:
        txn_date = _parse_date(request.form.get("txn_date", ""))
        name = request.form.get("instrument_name", "").strip()
        isin = request.form.get("isin", "").strip() or None
        txn_kind = request.form.get("txn_kind", "purchase")
        units = float(request.form.get("units", "") or 0)
        nav = float(request.form.get("nav", "") or 0)
        fees = float(request.form.get("fees", "") or 0)
        if not name:
            raise ValueError("Instrument name is required")
        rec = build_fi_trade_record(txn_date, name, isin, txn_kind, units, nav, fees)
        portfolio_store.replace_many({"fi_trades": fi_trade_records + [rec]})
        fi_trade_records.append(rec)
        _sync_fifo_analyses()
        flash("Fixed income trade added.", "success")
    except Exception as e:
        flash(f"Could not add trade: {e}", "error")
    return redirect(url_for("fixed_income"))


@app.route("/fixed-income/interest", methods=["POST"])
def fixed_income_add_interest():
    try:
        d = _parse_date(request.form.get("int_date", ""))
        name = request.form.get("int_name", "").strip()
        amount = float(request.form.get("int_amount", "") or 0)
        isin = request.form.get("int_isin", "").strip() or None
        notes = request.form.get("int_notes", "").strip() or None
        if not name:
            raise ValueError("Instrument name is required")
        rec = build_interest_record(d, name, amount, isin, notes)
        portfolio_store.replace_many({"fi_interest": fi_interest_records + [rec]})
        fi_interest_records.append(rec)
        flash("Interest recorded.", "success")
    except Exception as e:
        flash(f"Could not add interest: {e}", "error")
    return redirect(url_for("fixed_income"))


@app.route("/fixed-income/delete-trade/<int:index>", methods=["POST"])
def fixed_income_delete_trade(index: int):
    if 0 <= index < len(fi_trade_records):
        records = fi_trade_records.copy()
        records.pop(index)
        portfolio_store.replace_many({"fi_trades": records})
        fi_trade_records[:] = records
        _sync_fifo_analyses()
        flash("Trade removed.", "success")
    else:
        flash("Invalid index.", "error")
    return redirect(url_for("fixed_income"))


@app.route("/fixed-income/delete-interest/<int:index>", methods=["POST"])
def fixed_income_delete_interest(index: int):
    if 0 <= index < len(fi_interest_records):
        records = fi_interest_records.copy()
        records.pop(index)
        portfolio_store.replace_many({"fi_interest": records})
        fi_interest_records[:] = records
        flash("Removed.", "success")
    else:
        flash("Invalid index.", "error")
    return redirect(url_for("fixed_income"))


@app.route("/fixed-income/clear", methods=["POST"])
def fixed_income_clear():
    which = request.form.get("which", "trades")
    if which == "trades":
        portfolio_store.replace_many({"fi_trades": []})
        fi_trade_records.clear()
    elif which == "interest":
        portfolio_store.replace_many({"fi_interest": []})
        fi_interest_records.clear()
    else:
        portfolio_store.replace_many({"fi_trades": [], "fi_interest": []})
        fi_trade_records.clear()
        fi_interest_records.clear()
    _sync_fifo_analyses()
    flash("Cleared.", "success")
    return redirect(url_for("fixed_income"))


@app.route("/fixed-income/analyze", methods=["POST"])
def fixed_income_analyze():
    _sync_fifo_analyses()
    if not fi_trade_records:
        flash("Add trades first.", "error")
        return redirect(url_for("fixed_income"))
    return redirect(url_for("fixed_income_summary"))


@app.route("/fixed-income/summary")
def fixed_income_summary():
    _sync_fifo_analyses()
    if fi_summary is None:
        flash("Add fixed income trades first.", "warning")
        return redirect(url_for("fixed_income"))
    return render_template(
        "fi_summary.html",
        summary=fi_summary,
        yearly_data=gains_calculator.get_yearly_summary(fi_gains),
    )


@app.route("/export/fi-ledger")
def export_fi_ledger():
    trades_df = trade_records_to_dataframe(fi_trade_records)
    int_df = fi_interest_to_dataframe(fi_interest_records)
    if trades_df.empty and int_df.empty:
        flash("Nothing to export.", "error")
        return redirect(url_for("fixed_income"))
    try:
        fp = excel_exporter.export_fixed_income_ledger(trades_df, int_df)
        return send_file(fp, as_attachment=True)
    except Exception as e:
        flash(f"Export failed: {e}", "error")
        return redirect(url_for("fixed_income"))


@app.route("/export/fi-gains")
def export_fi_gains():
    _sync_fifo_analyses()
    if fi_gains is None:
        flash("No FI gains.", "error")
        return redirect(url_for("fixed_income"))
    try:
        fp = excel_exporter.export_capital_gains(fi_gains, fi_positions)
        return send_file(fp, as_attachment=True)
    except Exception as e:
        flash(f"Export failed: {e}", "error")
        return redirect(url_for("fixed_income_summary"))


@app.route("/api/fi/gains")
def api_fi_gains():
    _sync_fifo_analyses()
    if fi_gains is None:
        return jsonify({"error": "No FI gains"}), 400
    return jsonify(_gains_to_json(fi_gains))


# --- Property ---


@app.route("/property")
def property_page():
    return render_template(
        "property.html",
        property_assets=property_portfolio,
    )


@app.route("/property/add", methods=["POST"])
def property_add():
    try:
        asset = build_property_asset(
            request.form.get("p_name", ""),
            request.form.get("p_type", "other"),
            _parse_date(request.form.get("p_acq", "")),
            float(request.form.get("p_cost", "") or 0),
            request.form.get("p_notes", "").strip() or None,
        )
        portfolio_store.replace_many({"property_assets": property_portfolio + [asset]})
        property_portfolio.append(asset)
        flash("Asset saved.", "success")
    except Exception as e:
        flash(f"Could not save: {e}", "error")
    return redirect(url_for("property_page"))


@app.route("/property/dispose/<int:index>", methods=["POST"])
def property_dispose(index: int):
    if index < 0 or index >= len(property_portfolio):
        flash("Invalid asset.", "error")
        return redirect(url_for("property_page"))
    a = property_portfolio[index]
    if a.get("disposition_date"):
        flash("Already disposed.", "warning")
        return redirect(url_for("property_page"))
    try:
        updated_asset = a.copy()
        record_disposition(
            updated_asset,
            _parse_date(request.form.get("disp_date", "")),
            float(request.form.get("disp_proceeds", "") or 0),
        )
        records = property_portfolio.copy()
        records[index] = updated_asset
        portfolio_store.replace_many({"property_assets": records})
        property_portfolio[index] = updated_asset
        flash("Sale recorded.", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("property_page"))


@app.route("/property/delete/<int:index>", methods=["POST"])
def property_delete(index: int):
    if 0 <= index < len(property_portfolio):
        records = property_portfolio.copy()
        records.pop(index)
        portfolio_store.replace_many({"property_assets": records})
        property_portfolio[:] = records
        flash("Removed.", "success")
    else:
        flash("Invalid index.", "error")
    return redirect(url_for("property_page"))


@app.route("/property/clear", methods=["POST"])
def property_clear():
    portfolio_store.replace_many({"property_assets": []})
    property_portfolio.clear()
    flash("All property records cleared.", "success")
    return redirect(url_for("property_page"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
