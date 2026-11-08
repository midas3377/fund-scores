"""Sell Score calculation (adapted from codebase.txt).

Changes from the baseline:
- Dates are computed from the run date instead of hard-coded.
- Each trading day is one step (no division by calendar days).
- Weights come from tickers.yaml per ticker.
- Full price history is fetched, so "ATH" is a true all-time high (FETCH_START retired).
"""
from datetime import date

import pandas as pd
import yfinance as yf


def start_date(today: date | None = None) -> pd.Timestamp:
    """START_DATE (first date plotted) = Jan 1 of (year - 2)."""
    today = today or date.today()
    return pd.Timestamp(today.year - 2, 1, 1)


def fetch_prices(ticker: str) -> pd.DataFrame:
    """Full available history."""
    df = yf.download(ticker, period="max", auto_adjust=False,
                     progress=False, multi_level_index=False)
    if df is None or df.empty:
        raise RuntimeError(f"No price data returned for {ticker}")
    df = df.reset_index()[["Date", "High", "Low", "Close", "Adj Close"]].dropna()
    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
    # Put High/Low/Close on the same adjusted basis as Adj Close
    f = df["Adj Close"] / df["Close"]
    df["High"], df["Low"], df["Close"] = df["High"] * f, df["Low"] * f, df["Adj Close"]
    return df.sort_values("Date").reset_index(drop=True)


MA_WINDOWS = (5, 10, 20, 50, 100)  # trading days
ADX_N = 14


def add_indicators(df: pd.DataFrame, n: int = ADX_N) -> pd.DataFrame:
    """Simple moving averages of Adj Close, and Wilder's ADX / +DI / -DI from High/Low/Close.
    Mutual funds report one price a day (High = Low = Close), so for them the ranges collapse
    to close-to-close moves and +DI + -DI = 100."""
    df = df.copy()
    for w in MA_WINDOWS:
        df[f"MA{w}"] = df["Adj Close"].rolling(w).mean()
    h, l, c = df["High"], df["Low"], df["Close"]
    up, down = h.diff(), -l.diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    wilder = lambda s: s.ewm(alpha=1 / n, adjust=False).mean()
    atr = wilder(tr)
    df["+DI"] = 100 * wilder(plus_dm) / atr
    df["-DI"] = 100 * wilder(minus_dm) / atr
    dx = 100 * (df["+DI"] - df["-DI"]).abs() / (df["+DI"] + df["-DI"])
    df["ADX"] = wilder(dx)
    df["OnePrice"] = bool((h == l).all())
    return df


FEATURES = ["Ratio_to_ATH", "DayOfYear", "v_z", "a_z", "j_z"]
WEIGHT_KEYS = ["price", "time", "velocity", "acceleration", "jerk"]  # same order as FEATURES


def compute_features(prices: pd.DataFrame, z_window: int = 60, dt: str = "trading") -> pd.DataFrame:
    """The five unweighted inputs to the Score. dt: "trading" (1 step/day) or "calendar"."""
    df = prices.copy()
    adj = df["Adj Close"]
    step = 1 if dt == "trading" else df["Date"].diff().dt.days.fillna(1)

    df["v"] = adj.diff() / step
    df["a"] = df["v"].diff() / step
    df["j"] = df["a"].diff() / step

    def z_score(s: pd.Series) -> pd.Series:
        return (s - s.rolling(z_window).mean()) / (s.rolling(z_window).std() + 1e-9)

    df["v_z"] = z_score(df["v"])
    df["a_z"] = z_score(df["a"])
    df["j_z"] = z_score(df["j"])

    # "ATH" = running max of the fetched prices (a true ATH when full history is fetched)
    df["ATH"] = adj.cummax()
    df["ATH_Date"] = df["Date"].where(adj >= df["ATH"]).ffill()  # date of the latest ATH
    df["Ratio_to_ATH"] = adj / df["ATH"]
    df["DayOfYear"] = df["Date"].dt.dayofyear / 366.0
    return df


def compute_score(prices: pd.DataFrame, weights: dict, z_window: int = 60,
                  smooth_window: int = 7) -> pd.DataFrame:
    df = compute_features(prices, z_window)

    df["Term_Price"] = weights["price"] * df["Ratio_to_ATH"]
    df["Term_Time"] = weights["time"] * df["DayOfYear"]
    df["Term_Velocity"] = weights["velocity"] * df["v_z"]
    df["Term_Acceleration"] = weights["acceleration"] * df["a_z"]
    df["Term_Jerk"] = weights["jerk"] * df["j_z"]

    df["Score"] = (df["Term_Price"] + df["Term_Time"] + df["Term_Velocity"]
                   + df["Term_Acceleration"] + df["Term_Jerk"])

    # Smoothing restarts each calendar year
    df["ScoreSmooth"] = (
        df.groupby(df["Date"].dt.year)["Score"]
        .transform(lambda s: s.rolling(window=smooth_window, min_periods=1).mean())
    )
    return df


def ticker_scores(ticker: str, weights: dict, settings: dict,
                  today: date | None = None) -> pd.DataFrame:
    """Fetch, score, and trim to the plotting period (Date >= START_DATE)."""
    start = start_date(today)
    df = compute_score(fetch_prices(ticker), weights,
                       settings.get("z_window", 60), settings.get("smooth_window", 7))
    df = add_indicators(df)  # on full history, so every value is warmed up
    return df[df["Date"] >= start].reset_index(drop=True)
