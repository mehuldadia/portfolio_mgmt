# Stock Gains Analyzer - Code Explanation

## 📁 Project Structure

```
stock_gains_analyzer/
├── app.py                          # Flask app: dashboard, stocks, MF, FI, property, APIs
├── modules/
│   ├── transaction_reader.py      # Excel → DataFrame
│   ├── gains_calculator.py        # FIFO, short/long-term
│   ├── excel_exporter.py          # Excel exports
│   ├── mutual_fund_transactions.py
│   ├── fixed_income_transactions.py
│   ├── property_assets.py
│   └── dashboard_aggregator.py  # Combined yearly + holdings for dashboard
├── templates/
│   ├── base.html                  # Nav: Dashboard, Stocks, MF, FI, Property, Charts
│   ├── dashboard.html             # Cross-asset summary
│   ├── stocks.html                # Stock upload + gains on one page
│   ├── partials/stock_gains_summary.html  # Included when stock data exists
│   ├── charts.html                # Stock charts (needs upload)
│   ├── mutual_funds.html, mf_summary.html
│   ├── fixed_income.html, fi_summary.html
│   └── property.html
├── data/, output/, requirements.txt, sample_data.py, test_system.py
```

---

## 🔄 How Navigation Works

### **Flask Routing System**

The application uses Flask's routing system to handle navigation:

1. **URL Routes** → **Python Functions** → **HTML Templates**

### **Navigation Flow:**

```
User Browser
    ↓
http://localhost:5000/              → dashboard() → dashboard.html
    ↓
http://localhost:5000/stocks        → stocks() → stocks.html (upload + optional gains partial)
    ↓ (POST upload)
http://localhost:5000/upload        → upload_file() → redirect /stocks#stock-results
    ↓
http://localhost:5000/summary       → summary() → redirect /stocks#stock-results (legacy bookmark)
    ↓
http://localhost:5000/charts        → charts() → charts.html (requires stock data)
    ↓
/mutual-funds, /fixed-income, /property → respective pages
    ↓
http://localhost:5000/api/*         → JSON for charts and stock gains table
```

### **Template Inheritance:**

All pages extend `base.html` which provides:
- Navigation bar (Home, Summary, Charts)
- Common styling (Bootstrap CSS)
- Footer
- Flash message display

**Example:**
```html
{% extends "base.html" %}
{% block content %}
    <!-- Page-specific content; stocks page may {% include %} a partial -->
{% endblock %}
```

---

## 📄 File-by-File Explanation

### **1. app.py - Main Flask Application**

**Purpose:** The central web server that handles all HTTP requests and coordinates between modules.

**Key Components:**

#### **Initialization (Lines 16-43)**
- Creates Flask app instance
- Sets up configuration (upload folder, output folder)
- Initializes module instances (TransactionReader, GainsCalculator, ExcelExporter)
- Creates global variables to store current session data

#### **Route Handlers (overview)**

**`@app.route('/')` — Dashboard**
- Calls `_sync_fifo_analyses()` for MF/FI FIFO state
- Builds context via `build_dashboard_context(...)`
- Renders `dashboard.html`

**`@app.route('/stocks')` — Single stock workflow**
- Passes `stock_summary` (`current_summary`) and `stock_yearly` into `stocks.html`
- Template shows upload + format help always; includes `partials/stock_gains_summary.html` when `stock_summary` is set

**`@app.route('/upload', methods=['POST'])`**
- Reads Excel via `TransactionReader`, validates, `calculate_gains`, `get_gains_summary`
- Stores globals `current_transactions`, `current_gains`, `current_positions`, `current_summary`
- Redirects to `/stocks#stock-results` so upload and analysis stay on one screen

**`@app.route('/summary')` — Legacy URL**
- If no data → flash + redirect `/stocks`
- Else → redirect `/stocks#stock-results` (old bookmarks still work)

**`@app.route('/api/summary')`, `/api/yearly`, `/api/gains`**
- JSON for charts and the stock detailed-gains table (`api_gains`)

**`@app.route('/export/excel')`, `/export/transactions`**
- Excel downloads; on error redirect back to `/stocks#stock-results`

**`@app.route('/charts')`**
- Requires `current_summary`; else redirect `/stocks`

**Other routes:** mutual funds, fixed income, property pages, their exports, and `dashboard_aggregator`-related behavior live in the same `app.py` file.

---

### **2. modules/transaction_reader.py - Excel File Reader**

**Purpose:** Handles reading and parsing stock transaction data from Excel files.

**Class: `TransactionReader`**

#### **`read_transactions(file_path)` (Lines 18-78)**
**What it does:**
1. Checks if file exists
2. Reads Excel using pandas
3. Validates required columns: Date, Type, Symbol, Quantity, Price
4. Standardizes column names (case-insensitive)
5. Converts data types:
   - Date → datetime
   - Type → uppercase (BUY/SELL)
   - Quantity, Price, Fees → numeric
6. Validates transaction types (must be BUY or SELL)
7. Calculates `Total_Value = Quantity × Price`
8. Sorts by date and symbol

**Returns:** pandas DataFrame with cleaned transaction data

#### **`validate_transactions(df)` (Lines 80-112)**
**What it checks:**
- Negative or zero quantities
- Negative or zero prices
- Future dates
- Duplicate transactions

**Returns:** List of warning messages

#### **`get_transaction_summary(df)` (Lines 114-138)**
**What it calculates:**
- Total transactions count
- Date range
- Number of unique symbols
- Buy vs Sell counts
- Total values and fees

**Returns:** Dictionary with summary statistics

---

### **3. modules/gains_calculator.py - Capital Gains Calculator**

**Purpose:** Calculates capital gains using FIFO method and classifies as short-term or long-term.

**Data Classes:**

#### **`Position` (Lines 11-22)**
Represents a stock holding:
- symbol, quantity, price, date, fees
- `total_cost` property: calculates total cost including fees

#### **`CapitalGain` (Lines 25-47)**
Represents a completed gain/loss transaction:
- Buy and sell details
- Gain/loss amount
- Tax classification (short-term/long-term)
- Holding period in days
- Properties: `sell_total`, `buy_total`

**Class: `GainsCalculator`**

#### **`calculate_gains(transactions_df)` (Lines 62-157)**
**FIFO Algorithm Explained:**

1. **Sort transactions by date** (oldest first)

2. **Process each transaction:**
   - **BUY transactions:**
     - Add to positions queue (FIFO) for that symbol
     - Store: quantity, price, date, fees
   
   - **SELL transactions:**
     - Match against oldest BUY positions (FIFO)
     - Calculate gain/loss:
       ```
       Gain = (Sell Price × Quantity) - (Buy Price × Quantity) - Fees
       ```
     - Determine holding period:
       ```
       Holding Days = Sell Date - Buy Date
       ```
     - Classify:
       - **Short-term:** ≤ 365 days
       - **Long-term:** > 365 days
     - Create `CapitalGain` object
     - Update position (reduce quantity, remove if fully sold)

3. **Return:**
   - List of `CapitalGain` objects
   - List of remaining `Position` objects (unsold stocks)

**Example:**
```
Buy: 100 shares AAPL @ $150 on Jan 1, 2023
Sell: 50 shares AAPL @ $200 on Dec 1, 2023 (334 days later)
→ Short-term gain: 50 × ($200 - $150) = $2,500
```

#### **`get_gains_summary(capital_gains)` (Lines 159-226)**
**What it calculates:**
- Total gains vs losses
- Net gain
- Short-term vs long-term breakdown
- Transaction counts
- Yearly breakdown

**Returns:** Dictionary with comprehensive statistics

#### **`get_yearly_summary(capital_gains)` (Lines 228-276)**
**What it does:**
- Groups gains by year
- Calculates yearly statistics
- Separates short-term and long-term by year

**Returns:** Dictionary with year as key, statistics as value

---

### **4. modules/excel_exporter.py - Excel Report Generator**

**Purpose:** Exports calculated data to Excel files with multiple sheets.

**Class: `ExcelExporter`**

#### **`export_capital_gains(capital_gains, remaining_positions)` (Lines 25-66)**
**What it creates:**
Excel file with 4 sheets:

1. **Capital_Gains Sheet:**
   - All gain/loss transactions
   - Columns: Symbol, Sell Date, Buy Date, Quantities, Prices, Gain/Loss, Classification, Holding Days

2. **Remaining_Positions Sheet:**
   - Stocks still held (not sold)
   - Columns: Symbol, Quantity, Price, Date, Fees, Total Cost

3. **Summary Sheet:**
   - Overall statistics
   - Total gains, losses, net gain
   - Short-term vs long-term totals

4. **Yearly_Breakdown Sheet:**
   - Year-by-year summary
   - Gains, losses, transaction counts per year

**Returns:** File path to generated Excel file

#### **`export_transaction_summary(transactions_df)` (Lines 192-234)**
**What it creates:**
Excel file with 4 sheets:

1. **All_Transactions:** Complete transaction history
2. **Buy_Transactions:** Only BUY transactions
3. **Sell_Transactions:** Only SELL transactions
4. **Symbol_Summary:** Aggregated data by symbol

---

### **5. templates/base.html - Base Template**

**Purpose:** Common layout for all pages.

**Structure:**
- **Navigation Bar:**
  - Dashboard, Stocks, Mutual funds, Fixed income, Property, Charts
  - Uses Flask's `url_for()` to generate URLs
  
- **Flash Messages (Lines 71-80):**
  - Displays success/error messages
  - Uses Flask's flash messaging system

- **Content Block (Line 82):**
  - `{% block content %}` - replaced by child templates

- **Scripts Block (Line 92):**
  - `{% block scripts %}` - for page-specific JavaScript

**Styling:**
- Bootstrap 5 for responsive design
- Font Awesome for icons
- Chart.js for charts
- Custom CSS for metric cards

---

### **6. templates/stocks.html — Upload + stock gains**

**Purpose:** One menu entry for everything equity-related: upload broker Excel and view FIFO results.

**Structure:**
- **Top:** Breadcrumb, title, short description
- **`#stock-upload`:** Upload form (POST `/upload`), required-columns table
- **`#stock-results`:** Rendered only if `stock_summary` is not `None`
  - `{% include 'partials/stock_gains_summary.html' %}`

### **7. templates/partials/stock_gains_summary.html**

**Purpose:** Reusable block for net/total cards, short vs long-term cards, yearly table, detailed gains table.

- Uses variables `stock_summary` and `stock_yearly` (not the old `summary` / `yearly_data` names)
- Buttons: Charts, Export gains, Export transactions
- Inline script calls `/api/gains` to fill the detailed table

---

### **8. templates/charts.html — Charts visualization**

**Purpose:** Interactive charts for data visualization.

**Chart Types:**

1. **Yearly Trends Chart (Lines 42-55):**
   - Line chart showing net gain, short-term, long-term over years
   - Uses Chart.js library

2. **Gains vs Losses Chart (Lines 58-70):**
   - Doughnut chart comparing total gains vs losses

3. **Tax Classification Chart (Lines 71-83):**
   - Doughnut chart showing short-term vs long-term

4. **Symbols Chart (Lines 86-99):**
   - Bar chart showing gains/losses by stock symbol

**JavaScript Functions:**

- **`loadChartData()` (Lines 142-163):**
  - Fetches data from 3 API endpoints in parallel
  - Creates all charts

- **`createYearlyChart()` (Lines 165-229):**
  - Creates line chart with multiple datasets

- **`createGainsLossesChart()` (Lines 231-272):**
  - Creates doughnut chart

- **`createTaxClassificationChart()` (Lines 274-316):**
  - Creates doughnut chart for tax classification

- **`createSymbolsChart()` (Lines 318-377):**
  - Groups gains by symbol
  - Creates bar chart with color coding (green for gains, red for losses)

- **`showChart()` (Lines 126-140):**
  - Toggles visibility of chart sections
  - Updates active button state

---

## 🔄 Complete Data Flow

### **User Uploads File:**

```
1. User selects Excel file → stocks.html form submission
   ↓
2. POST /upload → upload_file()
   ↓
3. File saved under data/
   ↓
4. TransactionReader.read_transactions() → DataFrame
5. validate_transactions() → warnings
6. GainsCalculator.calculate_gains() → FIFO CapitalGain list + open Position list
7. get_gains_summary() → dict stored in current_summary
8. Redirect GET /stocks#stock-results
```

### **User opens Stocks (with data already loaded):**

```
1. GET /stocks → stocks()
   ↓
2. stock_yearly = get_yearly_summary(current_gains)
3. Renders stocks.html with stock_summary + stock_yearly
4. Partial shows cards, yearly table; script loads /api/gains for detail grid
```

### **User Views Charts:**

```
1. GET request to /charts → app.py: charts()
   ↓
2. Renders charts.html template
   ↓
3. JavaScript: loadChartData()
   - Fetches /api/summary
   - Fetches /api/yearly
   - Fetches /api/gains
   ↓
4. Creates Chart.js charts:
   - Yearly trends (line chart)
   - Gains vs losses (doughnut)
   - Tax classification (doughnut)
   - By symbol (bar chart)
```

### **User Exports Excel:**

```
1. Click "Export Gains" → GET /export/excel
   ↓
2. ExcelExporter.export_capital_gains()
   - Creates Excel file with 4 sheets
   - Saves to output/ folder
   ↓
3. send_file() sends file to browser
   - User downloads file
```

---

## 🎯 Key Concepts

### **FIFO (First In, First Out)**
- When selling stocks, match against oldest purchases first
- Ensures accurate cost basis calculation
- Required for tax reporting

### **Short-term vs Long-term**
- **Short-term:** Holding period ≤ 365 days
- **Long-term:** Holding period > 365 days
- Different tax rates apply

### **Template Inheritance**
- `base.html` provides common structure
- Child templates extend and override blocks
- Reduces code duplication

### **RESTful API Design**
- `/api/*` endpoints return JSON
- Separates data from presentation
- Enables dynamic content loading

### **Global State Management**
- Current session data stored in global variables
- Simple but effective for single-user sessions
- Could be improved with database for multi-user

---

## 🚀 Running the Application

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the application:**
   ```bash
   python app.py
   ```

3. **Open browser:** `http://localhost:5000` (dashboard)

4. **Stocks:** Open **Stocks** in the nav, upload Excel (broker columns as in README)

5. **View results:** Same **Stocks** page scrolls to **Capital gains analysis**; use **Charts** in nav for graphs; exports are on the stocks section when data exists

---

## 📊 Example Excel File Format

| Date       | Type | Symbol | Quantity | Price  | Fees  |
|------------|------|--------|----------|--------|-------|
| 2023-01-15 | BUY  | AAPL   | 100      | 150.25 | 9.99  |
| 2023-06-20 | SELL | AAPL   | 50       | 175.50 | 9.99  |
| 2023-03-10 | BUY  | MSFT   | 200      | 300.00 | 9.99  |

This will create:
- 1 capital gain transaction (AAPL: 50 shares sold)
- 1 remaining position (AAPL: 50 shares, MSFT: 200 shares)

---

## 🔧 Extending the Application

**To add new features:**

1. **New route:** Add `@app.route()` in `app.py`
2. **New calculation:** Add method to `GainsCalculator`
3. **New export:** Add method to `ExcelExporter`
4. **New page:** Create template extending `base.html`
5. **New API:** Add `/api/*` route returning JSON

The modular design makes it easy to extend!

