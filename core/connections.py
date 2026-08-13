"""Zapisane połączenia (SSH/FTP/SMB) w katalogu konfiguracyjnym użytkownika.

Po udanym połączeniu można je zapamiętać — potem wybiera się je jednym
kliknięciem z panelu bocznego, zamiast wpisywać dane za każdym razem.
Hasło zapisujemy tylko wtedy, gdy użytkownik wyraźnie zaznaczy "Zapisz hasło".
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "File_Manager"
CONNECTIONS_FILE = CONFIG_DIR / "connections.json"

CONNECTION_KINDS = {
    "ftp": "FTP",
    "sftp": "SSH (SFTP)",
    "smb": "NAS (SMB)",
}


def _save(connections: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONNECTIONS_FILE.write_text(
        json.dumps(connections, indent=2, ensure_ascii=False), encoding="utf-8")


def load_connections() -> dict:
    if CONNECTIONS_FILE.exists():
        try:
            return json.loads(CONNECTIONS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def get_connections(kind: str) -> list:
    """Zapisane połączenia danego typu, np. get_connections("sftp")."""
    return load_connections().get(kind, [])


def get_all_connections() -> list:
    """Wszystkie zapisane połączenia jako listy (kind, params) do panelu bocznego."""
    conns = load_connections()
    result = []
    for kind in ("ftp", "sftp", "smb"):
        for params in conns.get(kind, []):
            result.append((kind, params))
    return result


def save_connection(kind: str, params: dict) -> None:
    """Zapisuje (lub nadpisuje po nazwie) połączenie danego typu."""
    name = (params.get("name") or "").strip()
    if not name:
        return
    conns = load_connections()
    items = conns.setdefault(kind, [])
    for existing in items:
        if existing.get("name") == name:
            existing.update(params)
            break
    else:
        items.append(dict(params))
    _save(conns)


def remove_connection(kind: str, name: str) -> None:
    conns = load_connections()
    conns.setdefault(kind, [])
    conns[kind] = [c for c in conns[kind] if c.get("name") != name]
    _save(conns)


def provider_params(kind: str, params: dict) -> dict:
    """Dane potrzebne do utworzenia providera z zapisanego połączenia."""
    if kind == "smb":
        return {"host": params["host"], "user": params.get("user", ""),
                "password": params.get("password", "")}
    return {"host": params["host"], "port": int(params.get("port", 22)),
            "user": params.get("user", ""),
            "password": params.get("password", "")}
