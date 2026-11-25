"""Charts. Plotly makes the interactive charts; Matplotlib makes the static ones.

All colours follow the app theme: navy background, green = up, red = down, blue accents.
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from matplotlib.figure import Figure
from plotly.subplots import make_subplots

BG, PANEL, GRID = "#0B1426", "#13203A", "#223A5E"
GREEN, RED, BLUE, AMBER, TEXT, MUTED = "#22C55E", "#EF4444", "#38BDF8", "#F59E0B", "#E2E8F0", "#94A3B8"
PALETTE = [BLUE, AMBER, "#A78BFA", GREEN, "#F472B6", "#2DD4BF"]


# ------------------------------------------------------------------ Plotly (interactive)
def _style(fig, height=420, title=None, legend=True):
    fig.update_layout(
        template="plotly_dark", height=height, title=dict(text=title or "", font=dict(size=16)),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT),
        margin=dict(l=10, r=10, t=45 if title else 15, b=10), showlegend=legend,
        legend=dict(orientation="h", y=1.08, x=0), hovermode="x unified")
    fig.update_xaxes(gridcolor=GRID, showgrid=False)
    fig.update_yaxes(gridcolor=GRID)
    return fig


def _skip_weekends(fig, daily: bool):
    if daily:
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])


def price_chart(df, title, kind="Candlestick", sma=None, ema=None, show_volume=True, daily=True):
    """Candlestick (or line) chart with optional SMA/EMA lines and a volume panel."""
    from .technical_indicators import ema as ema_fn, sma as sma_fn

    rows = 2 if show_volume else 1
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        row_heights=[0.75, 0.25] if show_volume else [1.0])
    if kind == "Candlestick":
        fig.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
                                     name="Price", increasing_line_color=GREEN, decreasing_line_color=RED), row=1, col=1)
        fig.update_layout(xaxis_rangeslider_visible=False)
    else:
        fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name="Close", line=dict(color=GREEN, width=2)), row=1, col=1)
    for i, w in enumerate(sma or []):
        fig.add_trace(go.Scatter(x=df.index, y=sma_fn(df["Close"], w), name=f"SMA {w}", line=dict(color=PALETTE[i % 6], width=1.5)), row=1, col=1)
    for i, w in enumerate(ema or []):
        fig.add_trace(go.Scatter(x=df.index, y=ema_fn(df["Close"], w), name=f"EMA {w}",
                                 line=dict(color=PALETTE[(i + 3) % 6], width=1.5, dash="dot")), row=1, col=1)
    if show_volume:
        colors = np.where(df["Close"] >= df["Open"], GREEN, RED)
        fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="Volume", marker_color=colors, opacity=0.7), row=2, col=1)
    _style(fig, 560 if show_volume else 440, title)
    fig.update_layout(xaxis_rangeslider_visible=False)
    _skip_weekends(fig, daily)
    return fig


def rsi_chart(rsi_series, daily=True):
    fig = go.Figure(go.Scatter(x=rsi_series.index, y=rsi_series, name="RSI", line=dict(color=BLUE, width=2)))
    fig.add_hrect(y0=70, y1=100, fillcolor=RED, opacity=0.08, line_width=0)
    fig.add_hrect(y0=0, y1=30, fillcolor=GREEN, opacity=0.08, line_width=0)
    fig.add_hline(y=70, line_dash="dash", line_color=RED, line_width=1)
    fig.add_hline(y=30, line_dash="dash", line_color=GREEN, line_width=1)
    _style(fig, 260, "RSI (14)", legend=False)
    fig.update_yaxes(range=[0, 100])
    _skip_weekends(fig, daily)
    return fig


def macd_chart(macd_df, daily=True):
    fig = go.Figure()
    colors = np.where(macd_df["Histogram"] >= 0, GREEN, RED)
    fig.add_trace(go.Bar(x=macd_df.index, y=macd_df["Histogram"], name="Histogram", marker_color=colors, opacity=0.6))
    fig.add_trace(go.Scatter(x=macd_df.index, y=macd_df["MACD"], name="MACD", line=dict(color=BLUE, width=2)))
    fig.add_trace(go.Scatter(x=macd_df.index, y=macd_df["Signal"], name="Signal", line=dict(color=AMBER, width=2)))
    _style(fig, 300, "MACD (12, 26, 9)")
    _skip_weekends(fig, daily)
    return fig


def volume_chart(vol_df, daily=True):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=vol_df.index, y=vol_df["Volume"], name="Volume", marker_color=BLUE, opacity=0.6))
    fig.add_trace(go.Scatter(x=vol_df.index, y=vol_df["Volume SMA"], name="20-period average", line=dict(color=AMBER, width=2)))
    _style(fig, 280, "Trading volume")
    _skip_weekends(fig, daily)
    return fig


def sparkline(close, height=90):
    """Tiny price line for cards. Green if the period ended higher than it started."""
    up = close.iloc[-1] >= close.iloc[0]
    color = GREEN if up else RED
    fig = go.Figure(go.Scatter(x=close.index, y=close, mode="lines", line=dict(color=color, width=2),
                               fill="tozeroy", fillcolor="rgba(34,197,94,0.08)" if up else "rgba(239,68,68,0.08)"))
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", showlegend=False, xaxis=dict(visible=False), yaxis=dict(visible=False, range=[close.min() * 0.995, close.max() * 1.005]))
    return fig


def comparison_chart(series_by_name: dict, title="Performance comparison (start = 100)"):
    fig = go.Figure()
    for i, (name, s) in enumerate(series_by_name.items()):
        fig.add_trace(go.Scatter(x=s.index, y=s, name=name, line=dict(color=PALETTE[i % 6], width=2)))
    fig.add_hline(y=100, line_dash="dot", line_color=MUTED, line_width=1)
    return _style(fig, 380, title)


def replay_chart(history: pd.DataFrame, trades: list, symbol: str):
    """Price up to the current replay day, with the player's BUY/SELL markers."""
    fig = go.Figure(go.Scatter(x=history["Date"], y=history["Price"], name=f"{symbol} close", line=dict(color=BLUE, width=2)))
    for side, color, symbol_shape in (("BUY", GREEN, "triangle-up"), ("SELL", RED, "triangle-down")):
        pts = [t for t in trades if t["Side"] == side]
        if pts:
            fig.add_trace(go.Scatter(x=[t["Date"] for t in pts], y=[t["Price"] for t in pts], mode="markers", name=side,
                                     marker=dict(color=color, size=12, symbol=symbol_shape)))
    return _style(fig, 340, f"{symbol} historical prices (replay)")


def portfolio_vs_hold_chart(history: pd.DataFrame):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=history["Date"], y=history["Portfolio"], name="Your portfolio", line=dict(color=GREEN, width=2.5)))
    fig.add_trace(go.Scatter(x=history["Date"], y=history["Buy & hold"], name="Buy & hold", line=dict(color=AMBER, width=2, dash="dash")))
    return _style(fig, 320, "Portfolio value: you vs. buy & hold ($)")


def gbm_chart(paths: pd.DataFrame, max_lines=40):
    """HYPOTHETICAL simulated price paths (random numbers, not real prices)."""
    fig = go.Figure()
    for col in paths.columns[:max_lines]:
        fig.add_trace(go.Scatter(y=paths[col], mode="lines", line=dict(width=1, color="rgba(56,189,248,0.25)"), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(y=paths.median(axis=1), name="Median path", line=dict(color=AMBER, width=3)))
    fig.update_xaxes(title="Trading day")
    return _style(fig, 380, "HYPOTHETICAL simulated prices (not real data)")


def donut_chart(labels, values, title="Allocation"):
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.6, marker=dict(colors=PALETTE), textinfo="label+percent"))
    return _style(fig, 300, title, legend=False)


# ------------------------------------------------------------------ Matplotlib (static)
def _mpl_axes(width=6.5, height=3.4):
    fig = Figure(figsize=(width, height), facecolor=BG)
    ax = fig.subplots()
    ax.set_facecolor(PANEL)
    ax.tick_params(colors=MUTED)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.grid(color=GRID, alpha=0.5)
    return fig, ax


def returns_histogram(returns: pd.Series, title="Distribution of daily returns"):
    """Histogram of daily returns (in %), with the average marked."""
    fig, ax = _mpl_axes()
    pct = returns * 100
    ax.hist(pct, bins=40, color=BLUE, alpha=0.85, edgecolor=BG)
    ax.axvline(pct.mean(), color=AMBER, linewidth=2, label=f"Average {pct.mean():.2f}%")
    ax.set_title(title, color=TEXT)
    ax.set_xlabel("Daily return (%)", color=MUTED)
    ax.set_ylabel("Number of days", color=MUTED)
    ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT)
    fig.tight_layout()
    return fig


def volume_bars(volumes: pd.Series, title="Latest trading volume (millions of shares)"):
    """Horizontal bar chart comparing the latest volume of several stocks."""
    fig, ax = _mpl_axes(6.5, 0.45 * max(len(volumes), 3) + 1.2)
    ax.barh(volumes.index, volumes.values / 1e6, color=BLUE)
    ax.invert_yaxis()
    ax.set_title(title, color=TEXT)
    ax.tick_params(axis="y", colors=TEXT)
    fig.tight_layout()
    return fig
