"""
server.py
=========
Spread Screener: streams quarterly outrights over Lightstreamer and serves the board.

    python server.py            # then open http://127.0.0.1:8765

GET /api/quotes returns every leg's live quote; the page builds the spreads and flies from them.
"""
from __future__ import annotations

import json
import logging
import sys
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import config
from feed import Feed
from instruments import load_legs

STATIC = config.HERE / "static"
feed: Feed | None = None


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] == "/api/quotes":
            body = json.dumps(feed.snapshot()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
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
