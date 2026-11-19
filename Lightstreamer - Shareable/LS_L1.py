import getpass
import json
import time
from pathlib import Path

from lightstreamer.client import LightstreamerClient, Subscription, SubscriptionListener, ClientListener
from time import sleep
from datetime import datetime

ENV_FILE = Path(__file__).with_name(".env")
CACHE_FILE = Path(__file__).with_name(".msal_token_cache.json")


def get_lightstreamer_token() -> str:
    """Load LIGHTSTREAMER_TOKEN from this script's folder-local .env file."""
    if ENV_FILE.exists():
        for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            key, separator, value = line.partition("=")
            if separator and key.strip() == "LIGHTSTREAMER_TOKEN":
                token = value.strip().strip('"').strip("'")
                if token:
                    return token

    raise RuntimeError(f"LIGHTSTREAMER_TOKEN is missing from {ENV_FILE}")


def check_token_expiry(token: str) -> None:
    """Stop before connecting if the token in .env has expired."""
    if not CACHE_FILE.exists():
        raise RuntimeError(
            "Authentication cache not found. Run LS_authenticate.py to generate a token."
        )

    try:
        cache_data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "Authentication cache could not be read. Run LS_authenticate.py again."
        ) from exc

    matching_entry = next(
        (
            entry
            for entry in cache_data.get("AccessToken", {}).values()
            if entry.get("secret") == token
        ),
        None,
    )

    if matching_entry is None:
        raise RuntimeError(
            "The stored token could not be verified. Run LS_authenticate.py again."
        )

    try:
        expires_on = int(matching_entry["expires_on"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(
            "The token expiry could not be checked. Run LS_authenticate.py again."
        ) from exc

    if expires_on <= int(time.time()):
        expired_at = datetime.fromtimestamp(expires_on).astimezone().strftime(
            "%d %b %Y at %H:%M %Z"
        )
        raise RuntimeError(
            f"Lightstreamer token expired on {expired_at}. "
            "Run LS_authenticate.py to regenerate it."
        )


try:
    token = get_lightstreamer_token()
    check_token_expiry(token)
except RuntimeError as exc:
    print(f"\nAuthentication required: {exc}")
    raise SystemExit(1)

user = "first.lastname@hertshtengroup.com" # email id of user
server = "https://ls.prod-live.hertshtengroup.com/"
instruments = ["3761391845186607269-2",]

process_user = getpass.getuser()

l1fields = ["key", "command", "instrumentId", "exchangeTimeNs", "lsAdapterReceiveTimeNs", "lsAdapterSendTimeNs",
            "mdsSentTimeNs", "settlementTimeNs", "bidPrice", "bidQuantity", "askPrice", "askQuantity", "impliedBidPrice", "impliedBidQuantity",
            "impliedAskPrice", "impliedAskQuantity", "open", "close", "high", "low", "settlementPrice", "settlementType", "tradePrice",
            "tradeQuantity", "totalTradedQuantity", "state", "VWAP", "indicativeOpen", "cumLtq", "tradeSide"]

client = LightstreamerClient(server, "MARKET_DATA")
client.connectionOptions.setFirstRetryMaxDelay(5000)
client.connectionOptions.setRetryDelay(5000)
client.connectionDetails.setUser(user)
client.connectionDetails.setPassword(token)


class Listener(ClientListener):
    def onListenStart(self, client):
        print("Connection attempt started.")

    def onListenEnd(self, client):
        print("Connection attempt ended.")

    def onPropertyChange(self, property):
        print("Property changed: " + property)

    def onServerError(self, errorCode, errorMessage):
        print("Server error: " + errorCode + " : " + errorMessage)

    def onStatusChange(self, status):
        print("Connection status: " + status)


client.addListener(Listener())
client.connect()
sleep(10)
sub = Subscription("MERGE", instruments, l1fields)
sub.setDataAdapter("MDS")
sub.setRequestedSnapshot("yes")
sub.setRequestedMaxFrequency(1)


class SubListener(SubscriptionListener):
    def onItemUpdate(self, update):
        for k in l1fields:
            print(k + ": " + update.getValue(k))


sub.addListener(SubListener())
client.subscribe(sub)

try:
    while True:
        sleep(1)
except KeyboardInterrupt:
    client.disconnect()
