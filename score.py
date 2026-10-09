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
    df = df.reset_index()[["Date", "Adj Close"]].dropna()
    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
    return df.sort_values("Date").reset_index(drop=True)


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
    return df[df["Date"] >= start].reset_index(drop=True)
