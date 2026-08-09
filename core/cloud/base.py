"""
Wspólna baza dla providerów chmurowych:
- przepływ OAuth2 Authorization Code przez przeglądarkę + localhost redirect,
- cache tokenów na dysku,
- pomocnicze operacje REST z automatycznym odświeżaniem tokena.

Klucze aplikacji (client_id/secret) użytkownik wpisuje w
config/cloud_keys.json — każdy provider wymaga rejestracji aplikacji
u dostawcy (Google Cloud Console / Dropbox App Console / Azure Portal).
"""

from __future__ import annotations

import json
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests

from core.fs_base import FileSystemError, FileSystemProvider

CONFIG_DIR = Path.home() / ".config" / "File_Manager"
TOKENS_FILE = CONFIG_DIR / "cloud_tokens.json"
# Klucze trzymamy w katalogu użytkownika (katalog programu po instalacji
# .deb do /opt jest tylko do odczytu). Wzór: config/cloud_keys.example.json
KEYS_FILE = CONFIG_DIR / "cloud_keys.json"

REDIRECT_PORT = 8765
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback"


def load_app_keys() -> dict:
    if KEYS_FILE.exists():
        try:
            return json.loads(KEYS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_app_keys(keys: dict) -> None:
    """Zapisuje klucze aplikacji (wywoływane z dialogu ustawień w UI)."""
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEYS_FILE.write_text(json.dumps(keys, indent=2, ensure_ascii=False),
                         encoding="utf-8")


def has_app_keys(provider: str) -> bool:
    """Czy użytkownik wpisał prawdziwe klucze (nie placeholdery)?"""
    keys = load_app_keys().get(provider, {})
    cid, secret = keys.get("client_id", ""), keys.get("client_secret", "")
    return bool(cid and secret
                and not cid.startswith("WPISZ") and not secret.startswith("WPISZ"))


def _save_tokens(tokens: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOKENS_FILE.write_text(json.dumps(tokens, indent=2), encoding="utf-8")


def load_tokens() -> dict:
    if TOKENS_FILE.exists():
        try:
            return json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_token(provider: str, token: dict) -> None:
    tokens = load_tokens()
    tokens[provider] = token
    _save_tokens(tokens)


def get_saved_token(provider: str) -> Optional[dict]:
    return load_tokens().get(provider)


def remove_token(provider: str) -> None:
    tokens = load_tokens()
    tokens.pop(provider, None)
    _save_tokens(tokens)


class _CallbackHandler(BaseHTTPRequestHandler):
    code: Optional[str] = None
    state: Optional[str] = None

    def do_GET(self):  # noqa: N802 (nazwa wymuszona przez BaseHTTPRequestHandler)
        query = parse_qs(urlparse(self.path).query)
        _CallbackHandler.code = (query.get("code") or [None])[0]
        _CallbackHandler.state = (query.get("state") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            "<h3>Logowanie zakończone — możesz zamknąć tę kartę i wrócić do File Managera.</h3>"
            .encode("utf-8"))

    def log_message(self, *args):  # cisza w konsoli
        pass


def oauth2_authorize(auth_url: str, extra_params: dict,
                     cancel_event: Optional[threading.Event] = None,
                     timeout_s: int = 300) -> str:
    """
    Otwiera przeglądarkę ze stroną logowania i czeka na kod autoryzacyjny
    (lokalny serwer na REDIRECT_PORT). Zwraca "code".

    UWAGA: funkcja blokująca — wywołuj z wątku roboczego, nie z wątku UI!
    cancel_event pozwala przerwać oczekiwanie (przycisk Anuluj w UI).
    """
    state = secrets.token_urlsafe(16)
    params = {"redirect_uri": REDIRECT_URI, "state": state, **extra_params}
    url = auth_url + "?" + requests.compat.urlencode(params)

    _CallbackHandler.code = None
    _CallbackHandler.state = None
    server = HTTPServer(("127.0.0.1", REDIRECT_PORT), _CallbackHandler)
    server.timeout = 1.0  # krótki — żeby reagować na Anuluj

    webbrowser.open(url)
    deadline = time.monotonic() + timeout_s
    try:
        while time.monotonic() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                raise FileSystemError("Logowanie anulowane przez użytkownika.")
            server.handle_request()  # czeka maks. server.timeout
            if _CallbackHandler.code or _CallbackHandler.state:
                break
    finally:
        server.server_close()

    if not _CallbackHandler.code:
        raise FileSystemError(
            "Logowanie nie powiodło się (brak kodu autoryzacyjnego). "
            "Sprawdź redirect URI w konsoli dostawcy.")
    if _CallbackHandler.state != state:
        raise FileSystemError("Nieprawidłowy parametr state (ochrona CSRF).")
    return _CallbackHandler.code


class CloudFileSystem(FileSystemProvider):
    """Baza: sesja requests z nagłówkiem Bearer + odświeżanie tokena."""

    scheme = "cloud"

    def __init__(self, provider_key: str, token: dict):
        self.provider_key = provider_key
        self._token = token
        self._session = requests.Session()
        self._apply_token()

    # ----- do nadpisania -----
    def _apply_token(self) -> None:
        self._session.headers["Authorization"] = f"Bearer {self._token['access_token']}"

    def _refresh_token(self) -> None:
        """Domyślnie brak — providery z refresh_token nadpisują."""
        raise FileSystemError("Token wygasł — zaloguj ponownie.")

    def _request(self, method: str, url: str, retry: bool = True, **kw) -> requests.Response:
        resp = self._session.request(method, url, timeout=30, **kw)
        if resp.status_code == 401 and retry:
            self._refresh_token()
            self._apply_token()
            resp = self._session.request(method, url, timeout=30, **kw)
        return resp

    @staticmethod
    def _check(resp: requests.Response, what: str) -> requests.Response:
        if resp.status_code >= 400:
            raise FileSystemError(f"{what}: HTTP {resp.status_code} — {resp.text[:300]}")
        return resp
