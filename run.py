"""Daily dashboard: score each ticker and write site/index.html.

Run:  .venv/Scripts/python.exe run.py
"""
import shutil
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
ASSETS = HERE / "assets"  # favicon files, copied next to the page
SITE_TITLE = "Fund Crest Tracker"
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
        dotted trend lines show the direction of the score and price so far this year. The
        gold dot marks the all-time high used for % of ATH, with its date; the dashed gray line
        carries that price across to the right-hand scale, so later dates can be compared with it.
        If the high came before the chart begins, the line spans the whole chart.</li>
      <li><b>Sell Score since January of two years ago</b>: the same view over a longer span,
        to compare this year with recent years.</li>
      <li><b>Decomposition of Score Drivers</b>: how much each of the five ingredients
        contributes to the score each day.</li>
    </ul>
    <p class="note">Hover over any chart to read exact values; drag to zoom, double-click to
    reset. On a phone, tap a chart to read values and use the buttons above it to change the
    date range. Prices come from Yahoo Finance and update after each trading day's fund prices
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
        desc_cells = "".join(f'<td class="c-desc" data-label="{escape(k)}">{escape(desc.get(k, ""))}</td>'
                             for k in desc_fields)
        desc_lines = "".join(f'<div><span class="label">{escape(k)}:</span> {escape(v)}</div>'
                             for k, v in desc.items() if v)
        tabs.append(f'<button class="tab" data-tab="{ticker}">{ticker}</button>')
        try:
            df = ticker_scores(ticker, info["weights"], settings)
            last = df.iloc[-1]
            hot = last["ScoreSmooth"] >= threshold
            rows.append(
                f'<tr class="{"hot" if hot else ""}" data-goto="{ticker}">'
                f'<td class="c-ticker"><a href="#{ticker}">{ticker}</a></td>'
                f'<td class="c-owner" data-label="Owner">{escape(owner)}</td>{desc_cells}'
                f'<td class="num c-date" data-label="Date">{last["Date"]:%m/%d/%Y}</td>'
                f'<td class="num" data-label="Adj Close">${last["Adj Close"]:,.2f}</td>'
                f'<td class="num ath {ath_class(last["Ratio_to_ATH"])}" data-label="% of ATH">{100 * last["Ratio_to_ATH"]:.1f}%</td>'
                f'<td class="num" data-label="Score">{last["Score"]:.2f}</td>'
                f'<td class="num" data-label="ScoreSmooth"><b>{last["ScoreSmooth"]:.2f}</b></td></tr>'
            )
            body = "".join(f'<div class="chart">{fig_html(f)}</div>' for f in (
                year_chart(df, ticker, settings),
                span_chart(df, ticker, settings),
                decomposition_chart(df, ticker),
            ))
        except Exception as e:  # keep the rest of the page working if one ticker fails
            rows.append(f'<tr class="err"><td class="c-ticker">{ticker}</td>'
                        f'<td class="c-owner" data-label="Owner">{escape(owner)}</td>{desc_cells}'
                        f'<td class="c-desc" colspan="5">Data unavailable: {escape(str(e))}</td></tr>')
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
  <p class="note only-desk">Highlighted rows: ScoreSmooth &ge; {threshold}. Click a row to open its charts.</p>
  <p class="note only-phone">Highlighted cards: ScoreSmooth &ge; {threshold}. Tap a card to open its charts.</p>
</section>"""

    html = TEMPLATE.format(
        title=SITE_TITLE,
        phone_detect=PHONE_DETECT,
        phone_css=PHONE_CSS,
        phone_js=PHONE_JS,
        plotly_cdn=PLOTLY_CDN,
        updated=datetime.now(ZoneInfo("America/New_York")).strftime("%m/%d/%Y %I:%M %p ET"),
        tabs="".join(tabs) + '<button class="tab" data-tab="info">Info</button>',
        panels=overview + "".join(panels) + info_panel(threshold),
    )
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    for f in ASSETS.iterdir():
        shutil.copy2(f, OUT.parent / f.name)
    return OUT


# Everything below applies only when <html> has class "phone": a touch screen whose short side
# is at most 600px. Windows browsers never get it, even in a narrow window.
PHONE_DETECT = """<script>
  if (matchMedia('(pointer:coarse)').matches && Math.min(screen.width, screen.height) <= 600)
    document.documentElement.classList.add('phone');
</script>"""

PHONE_CSS = """
  .only-phone { display:none; }
  html.phone .only-phone { display:block; }
  html.phone .only-desk { display:none; }
  html.phone main { padding:12px 8px; }
  html.phone header { padding:14px 12px 0; }
  html.phone nav { padding:0 8px; }
  html.phone .tab { padding:10px 7px; font-size:14px; }
  html.phone .chart { padding:2px; overflow:hidden; }
  html.phone .modebar-container { display:none; }
  html.phone .desc { margin:-6px 4px 12px; }
  html.phone .info { padding:4px 14px 12px; }
  .ranges { display:none; }
  html.phone .ranges { display:flex; gap:6px; padding:6px 6px 2px; }
  .ranges button { flex:1; min-height:36px; border:1px solid var(--line); border-radius:6px;
                   background:var(--card); color:var(--ink); font:inherit; font-size:13px; }
  .ranges button.on { background:var(--accent); border-color:var(--accent); color:#fff; font-weight:600; }
  html.phone .table-wrap { overflow:visible; }
  html.phone table, html.phone tbody { display:block; border:0; background:none; }
  html.phone thead { display:none; }
  html.phone tbody tr { display:grid; grid-template-columns:1fr 1fr; gap:8px 14px; padding:12px 14px;
                        margin-bottom:10px; background:var(--card); border:1px solid var(--line); border-radius:10px; }
  html.phone tbody tr.hot { background:var(--hot); }
  html.phone tbody td { display:block; border:0; padding:0; font-size:15px; text-align:left; white-space:normal; }
  html.phone td[data-label]::before { content:attr(data-label); display:block; font-size:11px; font-weight:400; color:var(--muted); }
  html.phone td.c-ticker { font-size:18px; }
  html.phone td.c-owner { text-align:right; }
  html.phone td.c-date { order:5; }
  html.phone td.c-desc { order:6; grid-column:1 / -1; font-size:13px; }
  html.phone td.ath { padding:3px 8px; border-radius:6px; }
  html.phone td.ath::before { color:inherit; }
"""

PHONE_JS = """
  const PHONE = document.documentElement.classList.contains('phone');
  const iso = ms => new Date(ms).toISOString().slice(0, 10);

  function setRange(el, months, btn) {
    const ph = el._phone;
    btn.parentNode.querySelectorAll('button').forEach(b => b.classList.toggle('on', b === btn));
    if (months === null) return Plotly.relayout(el, ph.all);
    const end = el.calcdata[0][el.calcdata[0].length - 1].x;
    const d = new Date(end);
    if (months === 'ytd') { d.setUTCMonth(0, 1); } else { d.setUTCMonth(d.getUTCMonth() - months); }
    const start = d.getTime();
    const span = end - start;
    const upd = {'xaxis.range': [iso(start), iso(end + span * 0.03)],
                 'xaxis.dtick': months === 1 ? 7 * 864e5 : (months === 'ytd' ? 'M2' : 'M1'),
                 'xaxis.tickformat': '%m/%d', 'xaxis.nticks': null};
    // Rescale price to the visible dates so small moves can be seen (same lower-half layout)
    const price = el.calcdata.find(cd => cd[0].trace.name === 'Adj Close');
    if (price) {
      const ys = price.filter(p => p.x >= start && p.x <= end).map(p => p.y);
      if (ys.length) {
        const lo = Math.min(...ys), hi = Math.max(...ys), h = Math.max(hi - lo, lo * 0.005);
        upd['yaxis2.range'] = [lo - h * 0.1, lo + h * 2];
      }
    }
    Plotly.relayout(el, upd);
  }

  function phonify(el) {
    const fl = el._fullLayout, isScore = !!fl.yaxis2;
    const title = fl.title.text.replace('Sell Score for ', '');
    const dtick = {M1: 'M2', M3: 'M6'}[fl.xaxis.dtick];
    const upd = {
      dragmode: false, 'title.text': title, 'title.font.size': 13, 'title.x': 0.02,
      'title.xanchor': 'left', margin: {l: 34, r: isScore ? 48 : 10, t: 36, b: 28},
      'legend.orientation': 'h', 'legend.x': 0, 'legend.xanchor': 'left', 'legend.y': -0.07,
      'legend.yanchor': 'top', 'legend.font.size': 10, 'legend.entrywidth': 74,
      'xaxis.fixedrange': true, 'yaxis.fixedrange': true, 'xaxis.tickfont.size': 10,
      'yaxis.tickfont.size': 10, 'yaxis.title.text': '',
      annotations: (fl.annotations || []).map(a => {
        const c = Object.assign({}, a._input); c.font = Object.assign({}, c.font, {size: 10}); return c;
      }),
    };
    if (dtick) upd['xaxis.dtick'] = dtick; else upd['xaxis.nticks'] = 6;
    if (isScore) Object.assign(upd, {'yaxis2.fixedrange': true, 'yaxis2.title.text': '', 'yaxis2.tickfont.size': 10, 'yaxis2.tickformat': ',.0f'});
    el._phone = {all: {'xaxis.range': fl.xaxis.range.slice(), 'xaxis.dtick': dtick || null,
                       'xaxis.tickformat': fl.xaxis.tickformat || '', 'xaxis.nticks': dtick ? null : 6}};
    if (isScore) el._phone.all['yaxis2.range'] = fl.yaxis2.range.slice();
    el.layout.height = 480;  // set directly: relayout on height would freeze the width
    el.style.height = '480px';
    const bar = document.createElement('div');
    bar.className = 'ranges';
    [['1M', 1], ['3M', 3], ['6M', 6], ['YTD', 'ytd'], ['All', null]].forEach(([label, months]) => {
      const b = document.createElement('button');
      b.textContent = label;
      b.className = months === null ? 'on' : '';
      b.addEventListener('click', () => setRange(el, months, b));
      bar.appendChild(b);
    });
    el.closest('.chart').insertBefore(bar, el.closest('.chart').firstChild);
    const smooth = el.data.findIndex(t => t.name === 'Smoothed Score');
    if (smooth >= 0) Plotly.restyle(el, {name: 'Smoothed'}, [smooth]);  // fits the narrow legend
    return Plotly.relayout(el, upd);
  }

  function prepare(el) {
    if (PHONE && !el._phone) phonify(el).then(() => Plotly.Plots.resize(el));
    else Plotly.Plots.resize(el);
  }
"""

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="icon" href="favicon-32.png" type="image/png" sizes="32x32">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="manifest" href="site.webmanifest">
<meta name="theme-color" content="#1f4e8c">
{phone_detect}
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
{phone_css}</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <div class="updated">Updated {updated}</div>
</header>
<nav><button class="tab" data-tab="overview">Overview</button>{tabs}</nav>
<main>{panels}</main>
<script>{phone_js}
  function show(name) {{
    const panel = document.getElementById('panel-' + name) ? name : 'overview';
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === panel));
    document.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.id === 'panel-' + panel));
    // Charts drawn while hidden need a resize once visible
    document.querySelectorAll('#panel-' + panel + ' .js-plotly-plot').forEach(prepare);
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
