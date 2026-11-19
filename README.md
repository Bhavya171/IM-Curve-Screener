# IM Curve Screener

Live inter-market STIR curve screener. Streams quarterly outrights over Lightstreamer and shows, for
SOFR (SR3), SONIA (SO3), Euribor (I), CORRA (CRA) and ASX bills (YBA) on one page:

- **Spread board** – calendar spreads (3M / 6M / 1Y / 2Y) along the strip, S1–S12
- **6M spreads**, **3M flies (3MF)**, **6M flies (6MF)** and **6MF − 2×3MF** (same front leg: −Q0 + 4Q3 − 4Q6 + Q12)
- **Dec–Dec table** – each year's Dec–Dec spread with every 6M spread, 3MF, 6MF and 6MF − 2×3MF starting in it
- **Floating curve charts** – click any cell to chart that structure for every market; open several at
  once, click a legend item to hide / show a market, drag and resize the panels

A second tab, **Curve simulator**, lets you reshape each market's curve and see every structure follow:

- One input tab per market: each year's Dec–Dec spread and every 3M spread (DM, MJ, JS, SD), 3MF (DMJ, MJS, JSD, SDM)
  and 6MF (DJD, MSM, JDJ, SMS) starting in it. Untouched inputs track live; the charts always show every market.
- Any box can be typed; the rest follow with the smallest change from live (least squares over the 3M spreads).
  A 3M spread moves only itself; a Dec–Dec is shared equally by the 3M spreads you haven't fixed; a fly moves its
  belly (3MF +2 → front spread +1, back −1). If a box is already decided by newer inputs, the oldest in the clash is
  released. Clear a box to go back to live.
- The simulated curve keeps the first contract at its live price and chains the 3M spreads, so 1Y / 6M / 3M spreads,
  3MF, 6MF and 6MF − 2×3MF are all rebuilt — shown as charts (solid = sim, dashed = live) and tables shaded by sim − live.
- "Hold live reference" freezes the live defaults while you work; inputs are remembered in the browser.

Values are in bp, from each leg's mid or last trade. Shading is the change since the previous
settlement (green = up, red = down); italic grey marks a stale leg.

## Setup

```bash
pip install -r requirements.txt
```

Sign in to Lightstreamer once (device-code Microsoft sign-in; the token then renews silently):

```bash
python "Lightstreamer - Shareable/LS_authenticate.py"
```

## Run

```bash
python server.py
```

or double-click `run_screener.cmd`. The page opens at http://127.0.0.1:8765 (local only).

## Files

| File | What it does |
|---|---|
| `config.py` | Markets, Lightstreamer server / adapters, port. Add a market with one line in `MARKETS`. |
| `instruments.py` | Finds each market's live quarterlies and their Lightstreamer IDs through QH's public instrument list (cached daily). |
| `feed.py` | One L1 subscription per leg (`<hg_instrument_id>-2`, MERGE, adapter MDS); renews the token. |
| `ls_auth.py` | Silent token renewal from the cached Microsoft sign-in. |
| `server.py` | Local web server: `/api/quotes` plus the page. |
| `static/index.html` | The screener page: builds every spread / fly from the leg quotes and draws the charts. |

## Notes

- Products your Lightstreamer login is not entitled to show as "Not on your Lightstreamer feed (Invalid group)".
- Secrets (`.env`, `.msal_token_cache.json`) live only on your machine and are excluded by `.gitignore`.
