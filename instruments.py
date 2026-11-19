"""
instruments.py
==============
Finds the live quarterly outrights of each market and their Lightstreamer IDs.

Candidate QH codes (e.g. SRAZ26) are looked up through QH's public instrument list; codes QH does not
know are simply not returned. The result is cached for the day in instruments_cache.json, and that cache
is used as a fallback if QH cannot be reached.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date
from typing import Dict, List

import config

MONTH_CODES = "FGHJKMNQUVXZ"
MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@dataclass(frozen=True)
class Leg:
    market: str      # board key, e.g. "SR3"
    code: str        # QH code, e.g. "SRAZ26"
    id: str          # hg_instrument_id; Lightstreamer L1 item is "<id>-2"
    year: int
    month: int
    expiry: str

    @property
    def label(self) -> str:
        return f"{MONTH_NAMES[self.month - 1]}{self.year % 100:02d}"

    @property
    def l1_item(self) -> str:
        return f"{self.id}-2"


def _lookup(codes: List[str]) -> List[dict]:
    url = config.QH_INSTRUMENTS_URL + "?" + urllib.parse.urlencode({"qh_codes": ",".join(codes), "limit": 1000})
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "spread-screener"})
    last = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except Exception as exc:  # network blip: retry
            last = exc
    raise RuntimeError(f"QH instrument look-up failed ({last}). Check the corporate network / VPN.")


def _build(today: date) -> Dict[str, List[Leg]]:
    cand = {}
    for m in config.MARKETS:
        for yy in range(today.year % 100, today.year % 100 + m.years):
            for mc in m.months:
                cand[f"{m.qh_product}{mc}{yy:02d}"] = (m.key, 2000 + yy, MONTH_CODES.index(mc) + 1)
    codes = list(cand)
    rows = []
    for i in range(0, len(codes), 50):
        rows += _lookup(codes[i:i + 50])
    out: Dict[str, List[Leg]] = {m.key: [] for m in config.MARKETS}
    for r in rows:
        if r["quant_code"] not in cand or (r.get("expiry_date") or "9999") < today.isoformat():
            continue
        key, y, mo = cand[r["quant_code"]]
        out[key].append(Leg(key, r["quant_code"], str(r["hg_instrument_id"]), y, mo, r.get("expiry_date") or ""))
    for legs in out.values():
        legs.sort(key=lambda l: (l.year, l.month))
    return out


def load_legs(today: date | None = None) -> Dict[str, List[Leg]]:
    today = today or date.today()
    cache = None
    if config.INSTRUMENT_CACHE.exists():
        try:
            cache = json.loads(config.INSTRUMENT_CACHE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache = None
    markets = sorted(m.key for m in config.MARKETS)
    if cache and cache.get("date") == today.isoformat() and sorted(cache["legs"]) == markets:
        return {k: [Leg(**x) for x in v] for k, v in cache["legs"].items()}
    try:
        legs = _build(today)
    except RuntimeError:
        if cache:  # QH unreachable: yesterday's list is still good enough to stream
            return {k: [Leg(**x) for x in v if x["expiry"] >= today.isoformat()] for k, v in cache["legs"].items()}
        raise
    config.INSTRUMENT_CACHE.write_text(json.dumps(
        {"date": today.isoformat(), "legs": {k: [asdict(x) for x in v] for k, v in legs.items()}}, indent=1),
        encoding="utf-8")
    return legs


if __name__ == "__main__":
    for key, legs in load_legs().items():
        print(f"{key:<5} {len(legs):>2} legs  {' '.join(l.label for l in legs)}")
