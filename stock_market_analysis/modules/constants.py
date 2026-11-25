"""Fixed values used across the app (tickers, labels, sources)."""

START_CASH = 10_000.0  # starting virtual balance for every user

DEFAULT_WATCHLIST = ["AAPL", "NVDA"]
FEATURED = ["AAPL", "NVDA"]
POPULAR = ["MSFT", "AMZN", "GOOGL", "TSLA"]

# Names are only used for display. Unknown tickers are shown by symbol.
COMPANY_NAMES = {
    "AAPL": "Apple Inc.",
    "NVDA": "NVIDIA Corporation",
    "MSFT": "Microsoft Corporation",
    "AMZN": "Amazon.com, Inc.",
    "GOOGL": "Alphabet Inc. (Class A)",
    "TSLA": "Tesla, Inc.",
}

# Real index values (Yahoo Finance symbols).
INDICES_YAHOO = {"S&P 500": "^GSPC", "NASDAQ Composite": "^IXIC", "Dow Jones": "^DJI"}
# Some providers do not offer index values, so ETFs that track an index are used as proxies.
INDICES_ETF_PROXY = {"S&P 500 (SPY ETF)": "SPY", "NASDAQ-100 (QQQ ETF)": "QQQ", "Dow Jones (DIA ETF)": "DIA"}

PERIOD_OPTIONS = ["1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max"]
# Chart view -> pandas resampling rule (None = keep daily data)
VIEW_OPTIONS = {"Daily": None, "Weekly": "W-FRI", "Monthly": "ME", "Yearly": "YE"}

SOURCES = [
    ("Yahoo Finance", "https://finance.yahoo.com/", "Default market data source (accessed through the yfinance library)."),
    ("yfinance (GitHub)", "https://github.com/ranaroussi/yfinance", "Python library used to download Yahoo Finance data. Intended for personal and research use."),
    ("Alpha Vantage documentation", "https://www.alphavantage.co/documentation/", "Optional alternative data provider (requires a free API key)."),
    ("Finnhub documentation", "https://finnhub.io/docs/api", "Another financial API. Not built in, but can be added as a provider (see README)."),
    ("pandas documentation", "https://pandas.pydata.org/docs/", "Data cleaning, resampling and calculations."),
    ("NumPy documentation", "https://numpy.org/doc/", "Numerical calculations (returns, volatility, simulation)."),
    ("Matplotlib documentation", "https://matplotlib.org/stable/", "Static charts such as histograms and comparisons."),
    ("Plotly for Python", "https://plotly.com/python/", "Interactive candlestick and simulation charts."),
    ("Streamlit documentation", "https://docs.streamlit.io/", "Web application framework."),
    ("U.S. SEC - Investor.gov", "https://www.investor.gov/", "Investor education: how stock markets work, and risks of investing."),
    ("Nasdaq", "https://www.nasdaq.com/", "Stock market and exchange background information."),
]
