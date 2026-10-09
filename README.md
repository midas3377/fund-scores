# Fund Sell Scores dashboard

Builds a static page of daily Sell Score charts for a few mutual funds and publishes it
with GitHub Pages. A GitHub Actions workflow runs each weekday evening (and on demand).

- `run.py` builds `site/index.html`
- `score.py` calculates the score; `charts.py` draws the Plotly charts
- `tickers.yaml` lists funds, owners, and score weights
- `TickerDescription.txt` supplies the fund descriptions

Local run: `pip install -r requirements.txt`, then `python run.py`.
Informational only; not investment advice.
