# Portfolio Analyzer

A Flask app to track **stocks** (Excel upload + FIFO capital gains), **mutual funds**, **fixed income**, and **property / fixed assets**, with a **dashboard** that rolls up yearly totals and current holdings.

## Features

- **Dashboard** (`/`) — Yearly realized capital by asset class, dividend/coupon income, open positions
- **Stocks** (`/stocks`) — Upload broker Excel; FIFO gains, short/long-term split, yearly table, detailed lots, exports, and link to **Charts** (all on one page)
- **Mutual funds** — Manual purchases/redemptions + dividends; optional MF gains report
- **Fixed income** — Trades (FIFO) + coupon/interest income
- **Property** — Cost basis and disposition (proceeds − cost in sale year)
- **Excel exports** — Capital gains, transaction ledgers, MF/FI ledgers

## Installation

```bash

##### create virtual environment
- python -m venv env_stock_app

###### if you want to deactivate virtual environment
- deactivate 

###### delete virtual environment


# activate virtual environment
- venv\Scripts\activate

- pip install -r requirements.txt
```

## Usage

```bash
python app.py
```

Open **http://localhost:5000** (dashboard). Use the nav bar to open each asset class.

### Stocks Excel format

Required columns include: `Trx date`, `ISIN Code`, `ISIN Name`, `Dr Cr` (DR/CR), `DP Qty`, `Closing price`, `Amt`. Optional broker columns are ignored if present.

After upload you are sent to **Stocks** with the **Capital gains analysis** section (`#stock-results`). The legacy path **`/summary`** redirects there.

## Project structure

```
stock_gains_analyzer/
├── app.py                      # Routes: dashboard, stocks, MF, FI, property, APIs, exports
├── modules/
│   ├── transaction_reader.py   # Excel → normalized DataFrame
│   ├── gains_calculator.py     # FIFO, CapitalGain, Position
│   ├── excel_exporter.py       # Excel reports
│   ├── mutual_fund_transactions.py
│   ├── fixed_income_transactions.py
│   ├── property_assets.py
│   └── dashboard_aggregator.py # Unified dashboard numbers
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── stocks.html             # Upload + gains (includes partial when data exists)
│   ├── partials/
│   │   └── stock_gains_summary.html
│   ├── charts.html
│   ├── mutual_funds.html, mf_summary.html
│   ├── fixed_income.html, fi_summary.html
│   └── property.html
├── data/                       # Uploaded files
├── output/                     # Generated Excel
├── requirements.txt
├── sample_data.py
└── test_system.py
```

Data is held **in memory** until the server restarts.

## License / disclaimer

For personal organization only; not tax or legal advice. Verify rules in your jurisdiction.
