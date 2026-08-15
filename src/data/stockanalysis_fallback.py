"""Fallback daily price history from stockanalysis.com.

Used as a drop-in fallback when Yahoo Finance (yfinance) is rate-limited
or otherwise unavailable. Returns a pandas DataFrame shaped like
``yfinance.Ticker.history()`` — a DatetimeIndex with OHLCV columns — so
callers in ``fetcher.py`` / ``smart_fetcher.py`` can swap sources transparently.

stockanalysis.com history API returns abbreviated field names per row:
    t = date, o = open, h = high, l = low, c = close, a = adjclose, v = volume
"""

import json
import logging
import urllib.request

import pandas as pd

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _range_for_period(period: str) -> str:
    """Map a yfinance-style period to a stockanalysis range token."""
    p = (period or "").lower()
    if "5y" in p or "10y" in p or "max" in p:
        return "5Y"
    if "2y" in p:
        return "2Y"
    # Default to 2Y (~500 trading days) so 200-SMA calculations always have
    # enough history; extra rows are harmless because callers slice the tail.
    return "2Y"


def fetch_price_history(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """Fetch daily OHLCV for ``ticker`` from stockanalysis.com.

    Args:
        ticker: Stock symbol (e.g. ``AAPL``).
        period: yfinance-style period; only used to pick the history window.
        interval: Only daily (``1d``) is supported upstream; other values
            fall back to daily data.

    Returns:
        DataFrame with a DatetimeIndex and columns
        ``Open, High, Low, Close, Adj Close, Volume``. Empty DataFrame on failure.
    """
    rng = _range_for_period(period)
    url = (
        f"https://stockanalysis.com/api/symbol/s/{ticker.lower()}/history"
        f"?range={rng}&period=Daily"
    )
    req = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            js = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"stockanalysis fallback request failed for {ticker}: {e}")
        return pd.DataFrame()

    rows = js.get("data") or []
    if not rows:
        logger.warning(f"stockanalysis returned no rows for {ticker}")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["t"] = pd.to_datetime(df["t"])
    df = df.set_index("t").sort_index()

    out = pd.DataFrame(index=df.index)
    out["Open"] = pd.to_numeric(df.get("o"), errors="coerce")
    out["High"] = pd.to_numeric(df.get("h"), errors="coerce")
    out["Low"] = pd.to_numeric(df.get("l"), errors="coerce")
    out["Close"] = pd.to_numeric(df.get("c"), errors="coerce")
    out["Adj Close"] = pd.to_numeric(df.get("a"), errors="coerce")
    out["Volume"] = pd.to_numeric(df.get("v"), errors="coerce")
    out = out.dropna(subset=["Close"]).loc[out["Close"] > 0]
    return out
