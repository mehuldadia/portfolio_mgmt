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

###### if virtual environment is giving problem then you can deactivate virtual environment and reinstall
- deactivate 

###### Delete the incomplete virtual environment; From your project directory, run this in PowerShell:
- Remove-Item -Recurse -Force .\env_stock_app

####### then recreate the virtual environment as mentioned above

# activate virtual environment
- .\env_stock_app\Scripts\activate.bat

- pip install -r requirements.txt
```

## Usage

```bash
python .\src\app.py
```

Open **http://localhost:5000**. Configure an investor with a unique PAN on the Investors screen, then open that investor's portfolio from the navigation. Add more investors and switch portfolios from the same screen.

### Stocks Excel format

Required columns include: `Trx date`, `ISIN Code`, `ISIN Name`, `Dr Cr` (DR/CR), `DP Qty`, `Closing price`, `Amt`. Optional broker columns are ignored if present.

The mutual-fund template has one `Transactions` sheet with these columns: `MF_NAME`, `INVESTOR_NAME`, `PAN`, `FOLIO_NUMBER`, `PRODUCT_CODE`, `SCHEME_NAME`, `Scheme Type`, `TRADE_DATE`, `TRANSACTION_TYPE`, `DIVIDEND_RATE`, `AMOUNT`, `UNITS`, `PRICE`, `BROKER`. Purchase/redemption and dividend rows are selected by `TRANSACTION_TYPE`.

After upload, review the parsed transactions and analysis, then choose **Save to portfolio** or **Discard**. Saved stock imports appear on **Stocks** with the **Capital gains analysis** section (`#stock-results`). The legacy path **`/summary`** redirects there.

## Project structure
```
portfolio_mgmt/
├── src/
│   ├── app.py                  # Flask routes and app initialization
│   ├── modules/                # Readers, calculations, exports, SQLite store
│   ├── templates/              # Jinja pages and import review
│   └── static/                 # CSS and JavaScript
├── data/                       # portfolio.sqlite3 and accepted source workbooks
├── output/                     # Generated Excel reports
├── test/                       # Test scripts and sample data
├── requirements.txt
└── README.md
```

Portfolio records are stored locally in `data/portfolio.sqlite3`, keyed by investor PAN, and restored on startup. Valuations and reports are displayed in INR (₹). Stock and mutual-fund Excel uploads are shown for review before saving; accepted imports update the selected investor's portfolio and retain the source workbook under `data/uploads/`, while discarded imports are not stored. Database and upload files are excluded from Git. The app has one active investor selection for the local running process; it is not a multi-user authenticated service.

## License / disclaimer

For personal organization only; not tax or legal advice. Verify rules in your jurisdiction.
