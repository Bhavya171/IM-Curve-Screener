"""
server.py
=========
Spread Screener: streams quarterly outrights over Lightstreamer and serves the board.

    python server.py            # then open http://127.0.0.1:8765

GET /api/quotes returns every leg's live quote; the page builds the spreads and flies from them.
GET /api/ohlc?codes=SRAZ26,SRAM27&interval=1H&count=500 returns each contract's history from QH (see qh_history.py).
GET /api/daily?codes=SRAZ26,SRAM27&count=600 returns each contract's daily closes (for the Percentiles tab).
"""
from __future__ import annotations

import json
import logging
import sys
import urllib.parse
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import config
import qh_history
from feed import Feed
from instruments import load_legs

STATIC = config.HERE / "static"
feed: Feed | None = None


class Handler(SimpleHTTPRequestHandler):
    def _json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path == "/api/quotes":
            self._json(feed.snapshot())
            return
        if path == "/api/ohlc":
            q = urllib.parse.parse_qs(query)
            try:
                bars = qh_history.bars((q.get("codes", [""])[0]).split(","), q.get("interval", ["1H"])[0],
                                       int(q.get("count", ["500"])[0]))
                self._json({"bars": bars})
            except qh_history.HistoryError as e:
                self._json({"error": str(e), "need_token": e.need_token}, e.status)
            except ValueError:
                self._json({"error": "Bad request"}, 400)
            return
        if path == "/api/daily":
            q = urllib.parse.parse_qs(query)
            try:
                closes = qh_history.daily_closes((q.get("codes", [""])[0]).split(","), int(q.get("count", ["600"])[0]))
                self._json({"closes": closes})
            except qh_history.HistoryError as e:
                self._json({"error": str(e), "need_token": e.need_token}, e.status)
            except ValueError:
                self._json({"error": "Bad request"}, 400)
            return
        super().do_GET()

    def log_message(self, *args):  # keep the console quiet
        pass


def main() -> None:
    global feed
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    legs = load_legs()
    for key, ls in legs.items():
        logging.info("%-4s %2d contracts  %s", key, len(ls), " ".join(l.label for l in ls))
    feed = Feed(legs)
    feed.start()
    if feed.error:
        logging.error(feed.error)
    server = ThreadingHTTPServer((config.HOST, config.PORT), partial(Handler, directory=str(STATIC)))
    url = f"http://{config.HOST}:{config.PORT}/"
    logging.info("Spread Screener running at %s  (Ctrl+C to stop)", url)
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        feed.stop()


if __name__ == "__main__":
    main()
