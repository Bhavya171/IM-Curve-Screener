"""
qh_history.py
=============
Historical OHLC bars per contract from QH (https://qh-api.corp.hertshtengroup.com/apis/ohlc/), for the
strategy candle charts. The page combines the legs' bars into the strategy's candles.

Needs a QH API token: put  QH_API_TOKEN=...  in the .env file next to server.py (gitignored), or set the
QH_API_TOKEN environment variable. Restart the server after adding it.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import config

QH_OHLC = "https://qh-api.corp.hertshtengroup.com/apis/ohlc/"
INTERVALS = {"1M": 60, "5M": 300, "1H": 3600, "1D": 86400}
PAGE = 1000            # candles asked per request (per instrument)
MAX_COUNT = 5000       # per instrument, per chart
TICK = 0.0025          # QH rounds prices to 3 dp (95.7325 -> 95.732); snap back to the quarter-tick grid
CACHE_SECONDS = {"1M": 20, "5M": 30, "1H": 60, "1D": 300}

log = logging.getLogger("qh_history")
_cache: dict[tuple, tuple[float, dict]] = {}
_lock = threading.Lock()
_scheme: str | None = None   # "Bearer" or "Token", whichever QH accepts


class HistoryError(Exception):
    def __init__(self, message: str, need_token: bool = False, status: int = 502):
        super().__init__(message)
        self.need_token = need_token
        self.status = status


def _token() -> str | None:
    tok = os.environ.get("QH_API_TOKEN")
    if tok:
        return tok.strip()
    env = config.HERE / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            k, sep, v = line.partition("=")
            if sep and k.strip() == "QH_API_TOKEN":
                return v.strip().strip('"').strip("'") or None
    return None


def _get(params: dict) -> list:
    global _scheme
    tok = _token()
    if not tok:
        raise HistoryError("No QH API token. Add a line  QH_API_TOKEN=<your token>  to the .env file next to "
                           "server.py, then restart the screener.", need_token=True, status=401)
    url = QH_OHLC + "?" + urllib.parse.urlencode(params)
    for scheme in ([_scheme] if _scheme else ["Bearer", "Token"]):
        req = urllib.request.Request(url, headers={"Authorization": f"{scheme} {tok}", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                _scheme = scheme
                body = json.loads(r.read().decode("utf-8"))
                return body if isinstance(body, list) else body.get("results", [])
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                continue
            if e.code == 429:
                raise HistoryError("QH rate limit reached (30 requests a minute). Try again shortly.", status=429)
            raise HistoryError(f"QH returned HTTP {e.code}.")
        except (urllib.error.URLError, TimeoutError) as e:
            raise HistoryError(f"Could not reach QH: {e}")
    _scheme = None
    raise HistoryError("QH rejected the API token (expired or wrong?). Update QH_API_TOKEN in .env and restart.",
                       need_token=True, status=401)


def _snap(px):
    return None if px is None else round(round(px / TICK) * TICK, 6)


def bars(codes: list[str], interval: str, count: int) -> dict:
    """{code: [[t_ms, o, h, l, c, v], ...] oldest first} for up to `count` bars per contract."""
    if interval not in INTERVALS:
        raise HistoryError(f"Unknown interval {interval}.", status=400)
    codes = sorted({c for c in codes if c and c.replace("_", "").isalnum()})[:50]
    if not codes:
        raise HistoryError("No contracts.", status=400)
    count = max(1, min(int(count), MAX_COUNT))
    key = (tuple(codes), interval, count)
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_SECONDS[interval]:
            return hit[1]

    out: dict[str, dict[int, list]] = {c: {} for c in codes}
    end = None
    while True:
        params = {"instruments": ",".join(codes), "interval": interval, "count": str(min(PAGE, count))}
        if end:
            params["end"] = str(end)
        rows = _get(params)
        if not rows:
            break
        oldest = None
        for r in rows:
            c, t = r.get("product"), r.get("time")
            if c not in out or t is None:
                continue
            out[c][int(t)] = [int(t), _snap(r.get("open")), _snap(r.get("high")), _snap(r.get("low")),
                              _snap(r.get("close")), r.get("volume")]
            oldest = t if oldest is None else min(oldest, t)
        have = min(len(v) for v in out.values())
        if have >= count or oldest is None or len(rows) < min(PAGE, count):
            break
        nxt = int(oldest // 1000) - 1
        if end is not None and nxt >= end:
            break
        end = nxt
    res = {c: sorted(v.values())[-count:] for c, v in out.items()}
    with _lock:
        _cache[key] = (time.time(), res)
    return res


DAILY_MAX = 800          # days of closes per contract
DAILY_BATCH_ROWS = 6000  # QH answers HTTP 400 when instruments x count gets much larger
DAILY_CACHE = 600        # seconds; daily closes only change once a day


def daily_closes(codes: list[str], count: int) -> dict:
    """{code: [[t_ms, close], ...] oldest first}: the last `count` daily closes per contract, one request per
    batch of contracts and no paging (a contract listed recently simply has fewer days)."""
    codes = sorted({c for c in codes if c and c.replace("_", "").isalnum()})[:80]
    if not codes:
        raise HistoryError("No contracts.", status=400)
    count = max(1, min(int(count), DAILY_MAX))
    key = ("daily", tuple(codes), count)
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < DAILY_CACHE:
            return hit[1]
    per = max(1, DAILY_BATCH_ROWS // count)
    out: dict[str, dict[int, float]] = {c: {} for c in codes}
    for i in range(0, len(codes), per):
        chunk = codes[i:i + per]
        for r in _get({"instruments": ",".join(chunk), "interval": "1D", "count": str(count)}):
            c, t, px = r.get("product"), r.get("time"), _snap(r.get("close"))
            if c in out and t is not None and px is not None:
                out[c][int(t)] = px
    res = {c: [[t, v[t]] for t in sorted(v)][-count:] for c, v in out.items()}
    with _lock:
        _cache[key] = (time.time(), res)
    return res
