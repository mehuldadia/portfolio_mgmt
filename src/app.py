"""
Flask web application: stocks, mutual funds, fixed income, property, unified dashboard.
"""

from flask import Flask, render_template, request, jsonify, send_file, flash, redirect, url_for
import os
from datetime import datetime
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

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(APP_DIR)

app = Flask(
    __name__,
    template_folder=os.path.join(APP_DIR, "templates"),
    static_folder=os.path.join(APP_DIR, "static"),
)
app.secret_key = "your-secret-key-here"

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
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        try:
            current_transactions = transaction_reader.read_transactions(filepath)
            warnings = transaction_reader.validate_transactions(current_transactions)
            for w in warnings:
                flash(f"Warning: {w}", "warning")

            current_gains, current_positions = gains_calculator.calculate_gains(
                current_transactions
            )
            current_summary = gains_calculator.get_gains_summary(current_gains)

            flash("File processed successfully!")
            return redirect(url_for("stocks") + "#stock-results")
        except Exception as e:
            flash(f"Error processing file: {str(e)}", "error")
            return redirect(url_for("stocks"))

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
        trades, dividends = read_mutual_fund_transactions(uploaded_file.stream)
        mf_trade_records.extend(trades)
        mf_dividend_records.extend(dividends)
        _sync_fifo_analyses()
        flash(
            f"Imported {len(trades)} mutual-fund trade(s) and "
            f"{len(dividends)} dividend(s).",
            "success",
        )
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
        mf_dividend_records.append(
            build_dividend_record(div_date, fund_name, amount, isin, notes)
        )
        flash("Dividend recorded.", "success")
    except Exception as e:
        flash(f"Could not add dividend: {e}", "error")
    return redirect(url_for("mutual_funds"))


@app.route("/mutual-funds/delete-trade/<int:index>", methods=["POST"])
def mutual_funds_delete_trade(index: int):
    if 0 <= index < len(mf_trade_records):
        mf_trade_records.pop(index)
        _sync_fifo_analyses()
        flash("Transaction removed.", "success")
    else:
        flash("Invalid row index.", "error")
    return redirect(url_for("mutual_funds"))


@app.route("/mutual-funds/delete-dividend/<int:index>", methods=["POST"])
def mutual_funds_delete_dividend(index: int):
    if 0 <= index < len(mf_dividend_records):
        mf_dividend_records.pop(index)
        flash("Dividend removed.", "success")
    else:
        flash("Invalid row index.", "error")
    return redirect(url_for("mutual_funds"))


@app.route("/mutual-funds/clear", methods=["POST"])
def mutual_funds_clear():
    which = request.form.get("which", "trades")
    if which == "trades":
        mf_trade_records.clear()
        flash("All mutual fund trades cleared.", "success")
    elif which == "dividends":
        mf_dividend_records.clear()
        flash("All dividends cleared.", "success")
    else:
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
        fi_trade_records.append(
            build_fi_trade_record(txn_date, name, isin, txn_kind, units, nav, fees)
        )
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
        fi_interest_records.append(build_interest_record(d, name, amount, isin, notes))
        flash("Interest recorded.", "success")
    except Exception as e:
        flash(f"Could not add interest: {e}", "error")
    return redirect(url_for("fixed_income"))


@app.route("/fixed-income/delete-trade/<int:index>", methods=["POST"])
def fixed_income_delete_trade(index: int):
    if 0 <= index < len(fi_trade_records):
        fi_trade_records.pop(index)
        _sync_fifo_analyses()
        flash("Trade removed.", "success")
    else:
        flash("Invalid index.", "error")
    return redirect(url_for("fixed_income"))


@app.route("/fixed-income/delete-interest/<int:index>", methods=["POST"])
def fixed_income_delete_interest(index: int):
    if 0 <= index < len(fi_interest_records):
        fi_interest_records.pop(index)
        flash("Removed.", "success")
    else:
        flash("Invalid index.", "error")
    return redirect(url_for("fixed_income"))


@app.route("/fixed-income/clear", methods=["POST"])
def fixed_income_clear():
    which = request.form.get("which", "trades")
    if which == "trades":
        fi_trade_records.clear()
    elif which == "interest":
        fi_interest_records.clear()
    else:
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
        property_portfolio.append(
            build_property_asset(
                request.form.get("p_name", ""),
                request.form.get("p_type", "other"),
                _parse_date(request.form.get("p_acq", "")),
                float(request.form.get("p_cost", "") or 0),
                request.form.get("p_notes", "").strip() or None,
            )
        )
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
        record_disposition(
            a,
            _parse_date(request.form.get("disp_date", "")),
            float(request.form.get("disp_proceeds", "") or 0),
        )
        flash("Sale recorded.", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("property_page"))


@app.route("/property/delete/<int:index>", methods=["POST"])
def property_delete(index: int):
    if 0 <= index < len(property_portfolio):
        property_portfolio.pop(index)
        flash("Removed.", "success")
    else:
        flash("Invalid index.", "error")
    return redirect(url_for("property_page"))


@app.route("/property/clear", methods=["POST"])
def property_clear():
    property_portfolio.clear()
    flash("All property records cleared.", "success")
    return redirect(url_for("property_page"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
