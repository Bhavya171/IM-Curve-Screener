"""
config.py
=========
Settings for the Spread Screener. Add a market by adding a line to MARKETS.
"""
import os
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Lightstreamer (same server / adapters as the Volume Burst screener)
LS_SERVER = "https://ls.prod-live.hertshtengroup.com/"
LS_ADAPTER_SET = "MARKET_DATA"
LS_DATA_ADAPTER = "MDS"
L1_FIELDS = ["instrumentId", "bidPrice", "askPrice", "tradePrice", "settlementPrice",
             "exchangeTimeNs", "totalTradedQuantity", "state"]

# Microsoft sign-in used for the Lightstreamer token. Reuses the folder of the shareable scripts,
# so one `python LS_authenticate.py` there signs in both tools.
#   Default: the "Lightstreamer - Shareable" folder next to this file. Set LS_AUTH_DIR to use another one.
AUTH_DIR = Path(os.environ.get("LS_AUTH_DIR") or HERE / "Lightstreamer - Shareable")

# QH public instrument look-up (no token needed): QH code -> hg_instrument_id (= Lightstreamer ID)
QH_INSTRUMENTS_URL = "https://qh-api.corp.hertshtengroup.com/apis/common/instruments/"
INSTRUMENT_CACHE = HERE / "instruments_cache.json"

HOST = "127.0.0.1"   # keep the page private to this computer
PORT = 8765


@dataclass(frozen=True)
class Market:
    key: str            # short label shown on the board
    name: str           # description under the label
    qh_product: str     # QH product code: outrights are <qh_product><month><yy>, e.g. SRAZ26
    months: str = "HMUZ"  # contract months to load (quarterlies)
    years: int = 7      # how many years of contracts to look up (12 columns of 2Y spreads need ~6)
    bp_per_point: float = 100.0  # price points -> basis points (100 - rate contracts: 1.00 = 100 bp)


MARKETS = [
    Market("SR3", "SOFR 3M · CME", "SRA"),
    Market("SO3", "SONIA 3M · ICE", "SON"),
    Market("I", "Euribor 3M · ICE", "ER"),
    Market("CRA", "CORRA 3M · MX", "CRA"),
    Market("YBA", "ASX 90D Bills", "YBA"),
]

STALE_MINUTES = 30   # a leg whose last trade is this much older than the freshest leg is flagged
