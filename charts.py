"""Plotly versions of the baseline charts.

Order on the page: year_chart, span_chart, decomposition_chart.
year_chart and span_chart share one style (_score_chart); span_chart covers
START_DATE to today and has no trendlines.
"""
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go

HEIGHT = 560
BASE_LAYOUT = dict(
    template="plotly_white",
    height=HEIGHT,
    hovermode="x unified",
    margin=dict(l=60, r=60, t=70, b=50),
    legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0),
)


def _trend(dates: pd.Series, values: pd.Series, full_dates: pd.DatetimeIndex) -> np.ndarray:
    x = dates.map(pd.Timestamp.toordinal).to_numpy(dtype=float)
    slope, intercept = np.polyfit(x, values.to_numpy(dtype=float), 1)
    return slope * full_dates.map(pd.Timestamp.toordinal).to_numpy(dtype=float) + intercept


def _score_chart(df: pd.DataFrame, settings: dict, title: str, x_range: list,
                 show_trend: bool, dtick: str, tickformat: str) -> go.Figure:
    """Sell Score + Smoothed Score (left axis), Adj Close (right axis), target line."""
    threshold = settings.get("threshold", 30)
    axis_max = settings.get("score_axis_max", 35)
    full_dates = pd.date_range(x_range[0], x_range[1], freq="D")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["Date"], y=df["Score"], name="Sell Score",
                             line=dict(color="gray", dash="dot", width=2)))
    fig.add_trace(go.Scatter(x=df["Date"], y=df["ScoreSmooth"], name="Smoothed Score",
                             line=dict(color="darkred", width=2.5)))

    adj = df["Adj Close"].astype(float)
    if show_trend:
        fig.add_trace(go.Scatter(x=full_dates, y=_trend(df["Date"], df["ScoreSmooth"], full_dates),
                                 name="Score Trend", line=dict(color="darkred", dash="dot", width=2),
                                 opacity=0.9, hoverinfo="skip"))
        adj_trend = _trend(df["Date"], adj, full_dates)
        fig.add_trace(go.Scatter(x=full_dates, y=adj_trend, name="Adj Close Trend", yaxis="y2",
                                 line=dict(color="blue", dash="dot", width=2), opacity=0.9,
                                 hoverinfo="skip"))
        y2_ref = float(adj_trend[-1])
    else:
        y2_ref = float(adj.max())

    fig.add_trace(go.Scatter(x=df["Date"], y=adj, name="Adj Close", yaxis="y2",
                             line=dict(color="blue", width=2)))

    # Same axis rule as baseline: bottom = 90% of min; top puts trend end (or max) mid-height
    y2_min = float(adj.min()) * 0.9
    y2_max = 2 * (y2_ref - y2_min) + y2_min

    smooth_max = float(df["ScoreSmooth"].max())
    y1_max = axis_max if smooth_max <= axis_max else 5 * math.ceil(smooth_max / 5)

    fig.add_hline(y=threshold, line=dict(color="darkgreen", dash="dash", width=2))
    fig.add_annotation(x=x_range[0] + pd.Timedelta(days=6), y=threshold, text="Target Score",
                       showarrow=False, yshift=12, xanchor="left",
                       font=dict(color="darkgreen", size=13))

    fig.update_layout(
        **BASE_LAYOUT,
        title=dict(text=f"<b>{title}</b>"),
        xaxis=dict(range=x_range, dtick=dtick, tickformat=tickformat, hoverformat="%m/%d/%Y"),
        yaxis=dict(title=dict(text="Sell Score", font=dict(color="darkred")),
                   range=[0, y1_max], dtick=5, tickfont=dict(color="darkred")),
        yaxis2=dict(title=dict(text="Adj Close ($)", font=dict(color="blue")),
                    overlaying="y", side="right", range=[y2_min, y2_max],
                    tickfont=dict(color="blue"), showgrid=False, tickprefix="$"),
    )
    return fig


def year_chart(df: pd.DataFrame, ticker: str, settings: dict) -> go.Figure:
    """Current-year Sell Score chart (baseline's last chart, shown first)."""
    # Year of the latest data: on Jan 1 (no new-year data yet) this is the prior year
    plot_year = df["Date"].max().year
    df_year = df[df["Date"].dt.year == plot_year]
    show_trend = df_year["Date"].max() >= pd.Timestamp(plot_year, 2, 1) and len(df_year) >= 2
    fig = _score_chart(
        df_year, settings,
        title=f"Sell Score for {ticker} — {df_year['Date'].max():%m/%d/%Y}",
        x_range=[pd.Timestamp(plot_year, 1, 1), pd.Timestamp(plot_year, 12, 31)],
        show_trend=show_trend, dtick="M1", tickformat="%m/%d",
    )
    # Default yearly sale date (see coefficients_review.md)
    sale = pd.Timestamp(plot_year, 12, 22)
    fig.add_shape(type="line", x0=sale, x1=sale, y0=0, y1=1, yref="paper",
                  line=dict(color="dimgray", dash="dot", width=2))
    fig.add_annotation(x=sale, y=1, yref="paper", text="Default sale<br>Dec 22", showarrow=False,
                       xanchor="right", yanchor="top", xshift=-4, font=dict(color="dimgray", size=12))
    return fig


def span_chart(df: pd.DataFrame, ticker: str, settings: dict) -> go.Figure:
    """Same as year_chart over START_DATE → latest data, without trendlines."""
    first, last = df["Date"].min(), df["Date"].max()
    return _score_chart(
        df, settings,
        title=f"Sell Score for {ticker} since {first:%m/%d/%Y} — {last:%m/%d/%Y}",
        x_range=[pd.Timestamp(first.year, 1, 1), last + pd.Timedelta(days=7)],
        show_trend=False, dtick="M3", tickformat="%m/%y",
    )


def decomposition_chart(df: pd.DataFrame, ticker: str) -> go.Figure:
    """The 5 weighted terms (baseline plot 2)."""
    fig = go.Figure()
    # Stacked hatched areas: Price from 0, Time on top of Price.
    fig.add_trace(go.Scatter(x=df["Date"], y=df["Term_Price"], name="Price (Ratio to Peak)",
                             fill="tozeroy", mode="lines", line=dict(color="#1f77b4", width=1),
                             fillcolor="rgba(0,0,0,0)",
                             fillpattern=dict(shape="/", fgcolor="#1f77b4", fgopacity=0.6)))
    fig.add_trace(go.Scatter(x=df["Date"], y=df["Term_Price"] + df["Term_Time"],
                             customdata=df["Term_Time"], name="Time (Year Bias)",
                             hovertemplate="%{customdata:.2f}",
                             fill="tonexty", mode="lines", line=dict(color="#ff7f0e", width=1),
                             fillcolor="rgba(0,0,0,0)",
                             fillpattern=dict(shape="\\", fgcolor="#ff7f0e", fgopacity=0.6)))
    fig.add_trace(go.Scatter(x=df["Date"], y=df["Term_Velocity"], name="Velocity Term",
                             line=dict(color="green", width=1.5)))
    fig.add_trace(go.Scatter(x=df["Date"], y=df["Term_Acceleration"], name="Acceleration Term",
                             line=dict(color="purple", width=1.5)))
    fig.add_trace(go.Scatter(x=df["Date"], y=df["Term_Jerk"], name="Jerk Term",
                             line=dict(color="black", dash="dot", width=1.5)))
    fig.add_hline(y=0, line=dict(color="black", width=1))
    fig.update_layout(
        **BASE_LAYOUT,
        title=dict(text=f"<b>{ticker}: Decomposition of Score Drivers</b>"),
        xaxis=dict(hoverformat="%m/%d/%Y"),
        yaxis=dict(title=dict(text="Score Contribution")),
    )
    return fig
