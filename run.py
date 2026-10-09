"""Daily dashboard: score each ticker and write site/index.html.

Run:  .venv/Scripts/python.exe run.py
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from html import escape
from pathlib import Path

import plotly
import yaml

from charts import decomposition_chart, span_chart, year_chart
from score import ticker_scores

HERE = Path(__file__).parent
OUT = HERE / "site" / "index.html"
PLOTLY_CDN = f"https://cdn.plot.ly/plotly-{plotly.offline.get_plotlyjs_version()}.min.js"
FIG_CONFIG = {"responsive": True, "displaylogo": False}


def load_config() -> dict:
    with open(HERE / "tickers.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_descriptions() -> dict:
    """TickerDescription.txt: comma-separated, header row first, Ticker in column 1."""
    path = HERE / "TickerDescription.txt"
    if not path.exists():
        return {}
    lines = [ln for ln in path.read_text(encoding="utf-8-sig").splitlines() if ln.strip()]
    header = [h.strip() for h in lines[0].split(",")]
    out = {}
    for ln in lines[1:]:
        cells = [c.strip() for c in ln.split(",", len(header) - 1)]
        cells += [""] * (len(header) - len(cells))
        out[cells[0]] = dict(zip(header[1:], cells[1:]))
    return out


def ath_class(ratio: float) -> str:
    """% of ATH color band: >= 97% green, 94-97% yellow, < 94% dark red."""
    return "ath-high" if ratio >= 0.97 else "ath-mid" if ratio >= 0.94 else "ath-low"


def info_panel(threshold: float) -> str:
    """Static explanation tab (last tab)."""
    return f"""
<section class="panel" id="panel-info">
  <h2>About this site</h2>
  <div class="info">
    <h3>Purpose</h3>
    <p>Each year a required minimum distribution (RMD) must be taken from each fund by
    December 31. This site tracks each fund's price and a <b>Sell Score</b> so the owner can
    see when conditions look favorable for that year's sale. It is informational only: it
    does not tell anyone to buy or sell.</p>
    <p>Historical testing showed that selling around <b>December 22</b> each year did as well
    as or better than acting on the score, on average. That date is marked on the first chart
    as the default sale. The scores help judge whether a different day looks reasonable, for
    example if cash is needed earlier in the year.</p>

    <h3>Overview tab</h3>
    <ul>
      <li><b>Adj Close</b>: the latest closing price, adjusted for dividends and capital-gain
        distributions so prices are comparable over time.</li>
      <li><b>% of ATH</b>: the price as a percentage of the fund's all-time high (ATH).
        <span class="swatch ath-high">&ge; 97%</span> near the top,
        <span class="swatch ath-mid">94&ndash;97%</span> somewhat below,
        <span class="swatch ath-low">&lt; 94%</span> well below.</li>
      <li><b>Score</b> and <b>ScoreSmooth</b>: today's Sell Score and Smoothed Sell Score
        (explained below). Rows are highlighted when ScoreSmooth is {threshold:g} or more.</li>
    </ul>

    <h3>Sell Score</h3>
    <p>A daily number combining five ingredients, each multiplied by a weight fitted to that
    fund's price history:</p>
    <ul>
      <li><b>Price vs. all-time high</b>: the largest part. It is higher when the price is
        at or near its all-time high.</li>
      <li><b>Time of year</b>: rises steadily from January to December, reflecting that these
        funds have most often reached their yearly high in late December.</li>
      <li><b>Velocity</b>: is the price rising or falling right now? Rising adds to the score.</li>
      <li><b>Acceleration</b>: is the rise speeding up or slowing down? Slowing down adds to
        the score, because a rally that is losing steam is often near its peak.</li>
      <li><b>Jerk</b>: how suddenly the acceleration is changing; an early warning of a
        sharp turn.</li>
    </ul>
    <p>Velocity, acceleration and jerk are measured against the previous 60 trading days, so
    they show unusual moves rather than normal day-to-day noise. A higher score means a better
    time to consider selling. The <b>Target Score</b> line is drawn at {threshold:g}.</p>

    <h3>Smoothed Sell Score (ScoreSmooth)</h3>
    <p>The average of the Sell Score over the last 7 trading days. The daily score can jump
    around from one day to the next; the smoothed score shows the underlying trend and is the
    one compared with the Target Score. It restarts each January 1, so each year stands on
    its own.</p>

    <h3>Fund tabs</h3>
    <ul>
      <li><b>Sell Score for the current year</b>: daily score (gray dotted), smoothed score
        (dark red), Target Score line, and price (blue, right-hand scale). From February 1,
        dotted trend lines show the direction of the score and price so far this year.</li>
      <li><b>Sell Score since January of two years ago</b>: the same view over a longer span,
        to compare this year with recent years.</li>
      <li><b>Decomposition of Score Drivers</b>: how much each of the five ingredients
        contributes to the score each day.</li>
    </ul>
    <p class="note">Hover over any chart to read exact values; drag to zoom, double-click to
    reset. Prices come from Yahoo Finance and update after each trading day's fund prices
    are published, usually in the evening.</p>
  </div>
</section>"""


def fig_html(fig) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False, config=FIG_CONFIG)


def build() -> Path:
    cfg = load_config()
    settings = cfg.get("settings", {})
    threshold = settings.get("threshold", 30)
    descriptions = load_descriptions()
    desc_fields = list(next(iter(descriptions.values()), {}).keys())

    rows, tabs, panels = [], [], []
    for ticker, info in cfg["tickers"].items():
        owner = info.get("owner", "")
        desc = descriptions.get(ticker, {})
        desc_cells = "".join(f"<td>{escape(desc.get(k, ''))}</td>" for k in desc_fields)
        desc_lines = "".join(f'<div><span class="label">{escape(k)}:</span> {escape(v)}</div>'
                             for k, v in desc.items() if v)
        tabs.append(f'<button class="tab" data-tab="{ticker}">{ticker}</button>')
        try:
            df = ticker_scores(ticker, info["weights"], settings)
            last = df.iloc[-1]
            hot = last["ScoreSmooth"] >= threshold
            rows.append(
                f'<tr class="{"hot" if hot else ""}" data-goto="{ticker}">'
                f'<td><a href="#{ticker}">{ticker}</a></td><td>{escape(owner)}</td>{desc_cells}'
                f'<td class="num">{last["Date"]:%m/%d/%Y}</td><td class="num">${last["Adj Close"]:,.2f}</td>'
                f'<td class="num ath {ath_class(last["Ratio_to_ATH"])}">{100 * last["Ratio_to_ATH"]:.1f}%</td>'
                f'<td class="num">{last["Score"]:.2f}</td><td class="num"><b>{last["ScoreSmooth"]:.2f}</b></td></tr>'
            )
            body = "".join(f'<div class="chart">{fig_html(f)}</div>' for f in (
                year_chart(df, ticker, settings),
                span_chart(df, ticker, settings),
                decomposition_chart(df, ticker),
            ))
        except Exception as e:  # keep the rest of the page working if one ticker fails
            rows.append(f'<tr class="err"><td>{ticker}</td><td>{escape(owner)}</td>{desc_cells}'
                        f'<td colspan="5">Data unavailable: {escape(str(e))}</td></tr>')
            body = f'<p class="err">Data unavailable for {ticker}: {escape(str(e))}</p>'
        panels.append(f'<section class="panel" id="panel-{ticker}">'
                      f'<h2>{ticker} <span class="owner">· {escape(owner)}</span></h2>'
                      f'<div class="desc">{desc_lines}</div>{body}</section>')

    overview = f"""
<section class="panel" id="panel-overview">
  <h2>Overview</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>Ticker</th><th>Owner</th>{''.join(f'<th>{escape(k)}</th>' for k in desc_fields)}
      <th class="num">Date</th><th class="num">Adj Close</th><th class="num">% of ATH</th>
      <th class="num">Score</th><th class="num">ScoreSmooth</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table></div>
  <p class="note">Highlighted rows: ScoreSmooth &ge; {threshold}. Click a row to open its charts.</p>
</section>"""

    html = TEMPLATE.format(
        plotly_cdn=PLOTLY_CDN,
        updated=datetime.now(ZoneInfo("America/New_York")).strftime("%m/%d/%Y %I:%M %p ET"),
        tabs="".join(tabs) + '<button class="tab" data-tab="info">Info</button>',
        panels=overview + "".join(panels) + info_panel(threshold),
    )
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    return OUT


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fund Sell Scores</title>
<script src="{plotly_cdn}"></script>
<style>
  :root {{ --bg:#f6f7f9; --card:#fff; --ink:#1d2330; --muted:#667085; --line:#e3e6eb;
          --accent:#1f4e8c; --hot:#fde8e8; --hot-ink:#9b1c1c; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
         font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
  header {{ padding:18px 16px 0; max-width:1200px; margin:0 auto; }}
  header h1 {{ margin:0; font-size:22px; }}
  header .updated {{ color:var(--muted); font-size:13px; }}
  nav {{ max-width:1200px; margin:12px auto 0; padding:0 16px; display:flex; gap:4px;
        flex-wrap:wrap; border-bottom:1px solid var(--line); }}
  .tab {{ border:1px solid transparent; border-bottom:none; background:none; padding:8px 14px;
         font:inherit; color:var(--muted); cursor:pointer; border-radius:6px 6px 0 0; }}
  .tab.active {{ background:var(--card); color:var(--ink); border-color:var(--line);
                font-weight:600; margin-bottom:-1px; }}
  main {{ max-width:1200px; margin:0 auto; padding:16px; }}
  .panel {{ display:none; }}
  .panel.active {{ display:block; }}
  h2 {{ margin:4px 0 12px; font-size:19px; }}
  .owner {{ color:var(--muted); font-weight:400; }}
  .chart {{ background:var(--card); border:1px solid var(--line); border-radius:8px;
           margin-bottom:16px; padding:4px; }}
  table {{ width:100%; border-collapse:collapse; background:var(--card);
          border:1px solid var(--line); border-radius:8px; overflow:hidden; }}
  th, td {{ padding:10px 12px; text-align:left; border-bottom:1px solid var(--line); }}
  th {{ font-size:13px; color:var(--muted); font-weight:600; background:#fafbfc; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
  .table-wrap {{ overflow-x:auto; border-radius:8px; }}
  td {{ vertical-align:top; }}
  .desc {{ margin:-6px 0 14px; color:var(--muted); font-size:14px; }}
  .desc .label {{ font-weight:600; color:var(--ink); }}
  tbody tr {{ cursor:pointer; }}
  tbody tr:hover {{ background:#f0f4fa; }}
  .ath {{ font-weight:600; }}
  .ath-high {{ background:#d8f0dc; color:#1d6b2f; }}
  .ath-mid {{ background:#fff1bf; color:#7a5800; }}
  .ath-low {{ background:#8b1a1a; color:#fff; }}
  tr.hot {{ background:var(--hot); color:var(--hot-ink); }}
  tr.err td, p.err {{ color:var(--hot-ink); }}
  a {{ color:var(--accent); font-weight:600; text-decoration:none; }}
  .note {{ color:var(--muted); font-size:13px; }}
  .info {{ background:var(--card); border:1px solid var(--line); border-radius:8px;
          padding:4px 20px 12px; max-width:820px; }}
  .info h3 {{ margin:18px 0 6px; font-size:16px; }}
  .info p, .info li {{ margin:4px 0; }}
  .info ul {{ padding-left:20px; margin:4px 0; }}
  .swatch {{ display:inline-block; padding:0 6px; border-radius:4px; font-weight:600; }}
  @media (max-width:600px) {{ th, td {{ padding:8px 6px; font-size:13px; }} }}
</style>
</head>
<body>
<header>
  <h1>Fund Sell Scores</h1>
  <div class="updated">Updated {updated}</div>
</header>
<nav><button class="tab" data-tab="overview">Overview</button>{tabs}</nav>
<main>{panels}</main>
<script>
  function show(name) {{
    const panel = document.getElementById('panel-' + name) ? name : 'overview';
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === panel));
    document.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.id === 'panel-' + panel));
    // Charts drawn while hidden need a resize once visible
    document.querySelectorAll('#panel-' + panel + ' .js-plotly-plot').forEach(el => Plotly.Plots.resize(el));
  }}
  document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => {{
    location.hash = t.dataset.tab === 'overview' ? '' : t.dataset.tab; show(t.dataset.tab);
  }}));
  document.querySelectorAll('tr[data-goto]').forEach(r => r.addEventListener('click', () => {{
    location.hash = r.dataset.goto;
  }}));
  window.addEventListener('hashchange', () => show(location.hash.slice(1) || 'overview'));
  show(location.hash.slice(1) || 'overview');
</script>
</body>
</html>
"""


if __name__ == "__main__":
    print(f"Wrote {build()}")
