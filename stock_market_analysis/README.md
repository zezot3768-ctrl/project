# MarketLens: Stock Market Analysis Web App

A first-year Computer Science project that combines **real market data**, **Python data analysis**, **interactive charts** and an
**educational trading simulator with virtual money**.

> Educational use only. Nothing in this project is investment advice. Simulated trades are never sent to any exchange.

## Features

| Page | What it does |
|---|---|
| **Dashboard** | Live / latest-available quotes for **Apple (AAPL)** and **NVIDIA (NVDA)** plus MSFT, AMZN, GOOGL, TSLA; market indices; auto and manual refresh; best/worst performers; performance comparison |
| **Stock Analysis** | Candlestick/line charts (daily, weekly, monthly, yearly), SMA, EMA, RSI, MACD, volume analysis, statistics (returns, volatility, max/min, drawdown), company financials, explanations of every indicator |
| **Simulator** | $10,000 virtual portfolio (SQLite), buy/sell with validation, portfolio dashboard, transaction history, **historical market replay** (day-by-day vs. buy & hold) and a clearly-labelled **hypothetical market** |
| **Market Overview** | S&P 500, NASDAQ, Dow Jones, trends, top/worst performers, trading volume |
| **Watchlist** | Add/remove stocks (Apple and NVIDIA by default), see price changes, jump to analysis |
| **About** | Purpose, technologies, how each part works, limitations, sources |

### Data honesty

Every price is labelled with one of four data types and the app never confuses them:

| Label | Meaning |
|---|---|
| **Real-time** | Only if the chosen provider supplies real-time prices (neither built-in provider does) |
| **Delayed** | Market is open; the provider's price may be delayed (Yahoo: usually up to ~15 minutes) |
| **Historical (latest close)** | Past prices, including the latest close when the market is closed or on holidays |
| **Hypothetical** | Generated from assumptions (simulation tab). Never real data |

If the API fails, the app shows the last saved data marked **STALE** with the time of the last successful update, or a clear error.
It never generates fake live prices. Simulated trades are refused when no price exists, and require an explicit confirmation when the price is historical or stale.

## Installation

Requires **Python 3.10 or newer**.

```bash
cd stock_market_analysis
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration (API provider and keys)

The provider is chosen with the `DATA_PROVIDER` setting. API keys are **never** stored in the code.

1. Copy `.env.example` to `.env` and edit it (or use `.streamlit/secrets.toml`, see `.streamlit/secrets.toml.example`).
2. Settings:

| Setting | Default | Meaning |
|---|---|---|
| `DATA_PROVIDER` | `yahoo` | `yahoo` (no key needed) or `alphavantage` |
| `ALPHA_VANTAGE_API_KEY` | none | Required only for `alphavantage` (free key: https://www.alphavantage.co/support/#api-key) |
| `REFRESH_SECONDS` | `60` | Auto-refresh interval on the dashboard (minimum 15) |
| `QUOTE_CACHE_SECONDS` / `HISTORY_CACHE_SECONDS` | `60` / `900` | How long data is cached to limit API requests |
| `DATABASE_PATH` | `data/portfolio.db` | Where the SQLite database is stored |

Notes on providers:
* **Yahoo (via `yfinance`)**: unofficial library, free, no key; intended for personal/research use; may rate-limit or change without notice. Provides real index values.
* **Alpha Vantage**: free tier is limited (about 5 requests/minute and 25/day), so auto-refresh starts **off**; index values are replaced by tracking ETFs (SPY, QQQ, DIA), and the app says so.

## Run the web app

```bash
streamlit run app.py
```

Then open the address shown in the terminal (usually http://localhost:8501).

## Run the Jupyter notebook

```bash
jupyter lab
```

Open `notebooks/stock_analysis.ipynb` and choose *Run > Run All Cells*. It downloads real Apple and NVIDIA prices (and keeps a CSV copy in `data/`), cleans them with Pandas,
calculates returns, moving averages and volatility with NumPy/Pandas, draws Matplotlib charts, and compares the two stocks.
The notebook is saved without outputs because the results depend on the day you run it.

## Project structure

```
stock_market_analysis/
├── app.py                    # entry point: page setup + top navigation
├── requirements.txt  .env.example  README.md
├── .streamlit/               # dark theme (config.toml) and secrets example
├── pages/
│   ├── dashboard.py  stock_analysis.py  simulator.py
│   └── market_overview.py  watchlist.py  about.py
├── modules/
│   ├── config.py             # settings from env vars / .env / Streamlit secrets
│   ├── data_fetcher.py       # providers, caching, rate limiting, error handling, market hours
│   ├── data_processor.py     # cleaning, resampling, returns, statistics, hypothetical simulation
│   ├── technical_indicators.py   # SMA, EMA, RSI, MACD, volume analysis + explanations
│   ├── portfolio.py          # holdings maths, trade validation, historical replay engine
│   ├── database.py           # SQLite: accounts, transactions, watchlist
│   ├── visualization.py      # Plotly (interactive) and Matplotlib (static) charts
│   ├── ui.py  formatting.py  constants.py  errors.py
├── notebooks/stock_analysis.ipynb
├── tests/                    # automated tests (unittest)
├── assets/logo.svg
└── data/                     # SQLite database and downloaded CSV copies
```

How the pieces connect: `pages/*` (screens) → `modules/ui.py` and `modules/data_fetcher.py` (data) → `modules/data_processor.py` / `technical_indicators.py` (calculations) → `modules/visualization.py` (charts). Calculation modules do not depend on Streamlit, so the notebook and the tests reuse them.

### Adding another data provider

1. Create a class in `modules/data_fetcher.py` that extends `BaseProvider` and implements `get_history`, `get_quote`, `get_fundamentals` (set `label`, `delay_note`, `is_realtime`, `rate_limit_per_minute`).
2. Register it in `PROVIDERS` and in `build_provider`.
3. Set `DATA_PROVIDER` to its name.

## Tests

```bash
python -m unittest discover -s tests -t .
```

The tests cover the indicators, data cleaning, statistics, simulation, portfolio rules, the replay engine, the database (including rejected trades), caching, stale-data fallback, rate limiting, market-hours logic, and Alpha Vantage response parsing (with mocked HTTP). Test data is synthetic and used **only** in tests.

## Known limitations

* Free data can be delayed, incomplete or unavailable; rate limits apply.
* Simulated trades ignore fees, taxes, spreads and order-book depth; shares are whole numbers only.
* Market holidays are detected from the data (a weekday with no new price bar), not from an official calendar.
* There are no passwords: the profile name only separates saved portfolios on one computer.
* The web pages could not be run against a live Streamlit server and live API in the environment where this code was written (no internet access). Calculation modules are unit-tested and the pages were smoke-tested with a stand-in for Streamlit, so do a first run and report any issue.

## Sources and references

| Source | Used for |
|---|---|
| [Yahoo Finance](https://finance.yahoo.com/) | Default market data (prices, volume, company figures) |
| [yfinance on GitHub](https://github.com/ranaroussi/yfinance) | Python library used to retrieve Yahoo Finance data |
| [Alpha Vantage documentation](https://www.alphavantage.co/documentation/) | Optional alternative data provider and its API format |
| [Finnhub documentation](https://finnhub.io/docs/api) | Example of another financial API that could be added as a provider |
| [pandas documentation](https://pandas.pydata.org/docs/) | DataFrames, cleaning, resampling, rolling and exponential windows |
| [NumPy documentation](https://numpy.org/doc/) | Numerical calculations, random numbers for the hypothetical simulation |
| [Matplotlib documentation](https://matplotlib.org/stable/) | Static charts (histogram, bar charts, notebook charts) |
| [Plotly for Python](https://plotly.com/python/) | Interactive charts |
| [Streamlit documentation](https://docs.streamlit.io/) | Web interface, navigation, fragments (auto-refresh) |
| [U.S. SEC, Investor.gov](https://www.investor.gov/) | Investor education and risk background |
| [Nasdaq](https://www.nasdaq.com/) | Background on exchanges and markets |
