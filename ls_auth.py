"""
ls_auth.py
==========
Lightstreamer access token, renewed silently from the cached Microsoft sign-in.

Uses the sign-in made by "Lightstreamer - Shareable/LS_authenticate.py" (config.AUTH_DIR). If Microsoft
needs an interactive sign-in again, AuthRequired is raised: run LS_authenticate.py once.
"""
from __future__ import annotations

import importlib.util
import threading
import time
from dataclasses import dataclass

import config

_lock = threading.Lock()


class AuthRequired(RuntimeError):
    """Interactive Microsoft sign-in is needed (run LS_authenticate.py)."""


@dataclass(frozen=True)
class Token:
    access_token: str
    expires_at: float
    username: str

    @property
    def seconds_left(self) -> float:
        return self.expires_at - time.time()


def _auth_module():
    script = config.AUTH_DIR / "LS_authenticate.py"
    if not script.exists():
        raise AuthRequired(f"{script} not found. Set AUTH_DIR in config.py.")
    spec = importlib.util.spec_from_file_location("LS_authenticate", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_token(force_refresh: bool = False) -> Token:
    import msal

    with _lock:
        mod = _auth_module()
        cache = msal.SerializableTokenCache()
        if mod.CACHE_FILE.exists():
            cache.deserialize(mod.CACHE_FILE.read_text(encoding="utf-8"))
        app = msal.PublicClientApplication(mod.CLIENT_ID, authority=mod.AUTHORITY, token_cache=cache)
        accounts = app.get_accounts()
        if not accounts:
            raise AuthRequired("No Microsoft sign-in found. Run LS_authenticate.py once.")
        result = app.acquire_token_silent(scopes=mod.SCOPES, account=accounts[0], force_refresh=force_refresh)
        if cache.has_state_changed:
            mod.CACHE_FILE.write_text(cache.serialize(), encoding="utf-8")
        if not result or "access_token" not in result:
            raise AuthRequired("The Microsoft sign-in has expired. Run LS_authenticate.py again.")
        mod.store_access_token(result["access_token"])  # keeps the shareable scripts working too
        return Token(result["access_token"], time.time() + float(result.get("expires_in", 0)),
                     accounts[0].get("username", ""))
