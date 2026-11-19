"""
feed.py
=======
Live L1 quotes for every leg over Lightstreamer.

Feed facts this relies on (from the Volume Burst screener, checked again Nov 2026):
  * L1 item = "<hg_instrument_id>-2", MERGE mode, data adapter MDS.
  * Several items in ONE subscription can come back mislabelled, so each leg gets its own subscription.
  * exchangeTimeNs on L1 rows is in nanoseconds; it is the time of the latest update of ANY field, so the
    last-trade time is taken from the update where tradePrice changed (for the snapshot: the row's time).
  * "NaN" marks an empty price. settlementPrice is the previous settlement.
  * Products the login is not entitled to (seen: MX CORRA, ASX bills) fail with error 21 "Invalid group".
"""
from __future__ import annotations

import logging
import math
import threading
import time
from typing import Dict, List, Optional

import config
from instruments import Leg
from ls_auth import AuthRequired, Token, get_token

log = logging.getLogger("feed")


def _num(raw) -> Optional[float]:
    if raw in (None, ""):
        return None
    try:
        x = float(raw)
    except ValueError:
        return None
    return None if math.isnan(x) else x


def _epoch_ms(raw) -> Optional[float]:
    x = _num(raw)
    if not x:
        return None
    for limit, div in ((1e17, 1e6), (1e14, 1e3), (1e11, 1.0)):  # ns / us / ms -> ms
        if x > limit:
            return x / div
    return x * 1000.0  # seconds


class Feed:
    def __init__(self, legs: Dict[str, List[Leg]]):
        self.legs = legs
        self._lock = threading.Lock()
        self.quotes: Dict[str, dict] = {}       # leg id -> latest values
        self.sub_errors: Dict[str, str] = {}    # leg id -> error text
        self.status = "NOT STARTED"
        self.error: Optional[str] = None
        self.token: Optional[Token] = None
        self.client = None
        self.subscribed = 0
        self.last_update: Optional[float] = None
        self._stop = threading.Event()

    def start(self) -> None:
        try:
            self.token = get_token()
        except AuthRequired as exc:
            self.status, self.error = "AUTH REQUIRED", str(exc)
            return
        except Exception as exc:
            self.status, self.error = "AUTH FAILED", f"Could not get a Lightstreamer token: {exc}"
            return

        from lightstreamer.client import ClientListener, LightstreamerClient, Subscription, SubscriptionListener
        feed = self

        class _Client(ClientListener):
            def onStatusChange(self, status):
                feed.status = status

            def onServerError(self, code, message):
                feed.error = f"Lightstreamer server error {code}: {message}"
                log.error(feed.error)

        class _Leg(SubscriptionListener):
            def __init__(self, leg: Leg):
                self.leg = leg

            def onSubscription(self):
                feed.subscribed += 1

            def onSubscriptionError(self, code, message):
                with feed._lock:
                    feed.sub_errors[self.leg.id] = f"{code} {message}"

            def onItemUpdate(self, u):
                feed._on_update(self.leg, u)

        client = LightstreamerClient(config.LS_SERVER, config.LS_ADAPTER_SET)
        client.connectionOptions.setFirstRetryMaxDelay(5000)
        client.connectionOptions.setRetryDelay(5000)
        client.connectionDetails.setUser(self.token.username)
        client.connectionDetails.setPassword(self.token.access_token)
        client.addListener(_Client())
        for legs in self.legs.values():
            for leg in legs:
                sub = Subscription("MERGE", [leg.l1_item], config.L1_FIELDS)
                sub.setDataAdapter(config.LS_DATA_ADAPTER)
                sub.setRequestedSnapshot("yes")
                sub.addListener(_Leg(leg))
                client.subscribe(sub)
        self.client = client
        client.connect()
        threading.Thread(target=self._token_loop, name="ls-token", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        if self.client is not None:
            self.client.disconnect()

    def _token_loop(self) -> None:
        """Renew the token before it expires so reconnects keep working."""
        while not self._stop.wait(60):
            try:
                if self.token is not None and self.token.seconds_left > 600:
                    continue
                self.token = get_token(force_refresh=True)
                self.client.connectionDetails.setPassword(self.token.access_token)
                if self.error and "token" in self.error.lower():
                    self.error = None
            except AuthRequired as exc:
                self.error = f"Token renewal needs a sign-in: {exc}"
            except Exception as exc:
                self.error = f"Token renewal failed: {exc}"

    def _on_update(self, leg: Leg, u) -> None:
        try:
            ts = _epoch_ms(u.getValue("exchangeTimeNs"))
            with self._lock:
                q = self.quotes.setdefault(leg.id, {"trade_time": None})
                q["bid"] = _num(u.getValue("bidPrice"))
                q["ask"] = _num(u.getValue("askPrice"))
                q["last"] = _num(u.getValue("tradePrice"))
                q["settle"] = _num(u.getValue("settlementPrice"))
                q["volume"] = _num(u.getValue("totalTradedQuantity"))
                q["update_time"] = ts
                if u.isSnapshot() or u.isValueChanged("tradePrice") or u.isValueChanged("totalTradedQuantity"):
                    if q["last"] is not None:
                        q["trade_time"] = ts
                self.last_update = time.time()
        except Exception:
            log.exception("bad L1 update for %s", leg.code)

    def snapshot(self) -> dict:
        markets = []
        with self._lock:
            for m in config.MARKETS:
                legs = self.legs.get(m.key, [])
                rows, errors = [], set()
                for leg in legs:
                    if leg.id in self.sub_errors:
                        errors.add(self.sub_errors[leg.id])
                    q = self.quotes.get(leg.id, {})
                    rows.append({"code": leg.code, "label": leg.label, "y": leg.year, "m": leg.month,
                                 "bid": q.get("bid"), "ask": q.get("ask"), "last": q.get("last"),
                                 "settle": q.get("settle"), "volume": q.get("volume"),
                                 "trade_time": q.get("trade_time"), "update_time": q.get("update_time")})
                err = None
                if not legs:
                    err = "No live contracts found in QH."
                elif errors and len([l for l in legs if l.id in self.sub_errors]) == len(legs):
                    err = ("Not on your Lightstreamer feed" +
                           (" (Invalid group)" if any("Invalid group" in e for e in errors) else f" ({errors.pop()})"))
                markets.append({"key": m.key, "name": m.name, "bp": m.bp_per_point, "error": err, "legs": rows})
        return {"status": self.status, "error": self.error, "server_time": time.time() * 1000,
                "subscribed": self.subscribed,
                "seconds_since_update": None if self.last_update is None else time.time() - self.last_update,
                "stale_minutes": config.STALE_MINUTES, "markets": markets}
