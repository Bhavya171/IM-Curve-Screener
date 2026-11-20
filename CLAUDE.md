# IM Curve Screener – notes for Claude

Live inter-market STIR screener (SR3, SO3, I/Euribor, CRA, YBA). See README.md for features and files.
Repo: https://github.com/Bhavya171/IM-Curve-Screener

## Rules

- Commit or push only when the user asks.
- Commit as `Bhavya171 <Bhavya171@users.noreply.github.com>`. Never put the user's work email in commits or pushed files.
- Never commit `.env`, `.msal_token_cache.json` or any token (they're gitignored; keep it that way).
- Don't read the QH MCP's install / credential folder (`AppData\Local\Hertshten\QH-MCP-Pilot`) and don't reuse the
  Lightstreamer MSAL token for QH. The user supplies `QH_API_TOKEN` in `.env` themself.

## Running

- `python server.py` (port 8765). In the desktop app: preview_start `screener` (`.claude/launch.json`, gitignored).
- No Node on this machine: test JS in the browser preview, not with node.

## Data

- **Live:** Lightstreamer `https://ls.prod-live.hertshtengroup.com/`, adapter set MARKET_DATA, data adapter MDS,
  item `<hg_instrument_id>-2`, MERGE, one subscription per leg. Token renewed by `ls_auth.get_token()`.
  CRA and YBA fail with "Invalid group" (not entitled) – expected.
- Values in bp: (100 − price) × 100 for outrights; structures are Σw·price × 100.
- **History:** `qh_history.py` → `https://qh-api.corp.hertshtengroup.com/apis/ohlc/` (instruments, interval
  1M/5M/1H/1D, count, end). Newest first, paginated with `end`. Rate limit 30/min. QH rounds prices to 3 dp,
  so they're snapped to the 0.0025 tick. QH codes look like `SRAM27` (not `SR3M7`). Served as `/api/ohlc`.
- **Daily closes:** `/api/daily` (`qh_history.daily_closes`), no paging, codes batched so instruments × count ≤ 6000
  (QH answers 400 above that). 1D bars are last-trade closes, so back contracts only have bars on days they traded.

## Page (`static/index.html`) – key ideas

- Tabs: Screener (quoted grid on top, custom-strategy grid below; resizable, layout in localStorage `screenerLayout`),
  Strips, Curve simulator, Strategy builder.
- Percentile subscripts in Screener cells: live value's percentile among the strategy's daily closes over the window
  picked in the Percentile select (`DL.pct`, 10/30/60/120/240/560 trading days, 0 = off); the tooltip lists every
  window. Closes = Σ w × leg close × bp with missing leg days forward-filled. Covers custom strategies too.
- Clicks: a structure name / header (`[data-curve]`) opens the curve chart for all markets; a number (`td.v`)
  opens that market's candle chart for that one strategy.
- Candles: built from leg bars one step finer (1D←1H, 1H←5M, 5M←1M). O/C exact, H/L estimated from the finer
  bars' opens/closes; missing leg bars forward-filled; the last candle follows live.
- Custom strategies: localStorage `customStrategies`, `{key:"u…", name, legs:[{off,w}], parts, desc}`;
  `syncStructs()` adds them to `STRUCT` so they appear in every tab (screener group, strip, charts, simulator).
- Simulator: variables are each market's 3M spreads, first contract anchored at live. Every input is a linear
  constraint; least-change solve s = base + Aᵀλ with (AAᵀ)λ = v − A·base. Newest input wins; a dependent older
  input is released (Gram–Schmidt rank test) and named in a message.
