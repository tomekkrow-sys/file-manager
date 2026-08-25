"""Automatyczna aktualizacja z GitHub Releases.

Sprawdza najnowszy release w repo, porównuje wersję z bieżącą i — jeśli jest
nowsza — pobiera pakiet dla bieżącej platformy oraz instaluje go (Linux: .deb
przez pkexec/sudo). Działa niezależnie od tego, czy apka uruchomiona jest z
kodu, czy z zainstalowanego pakietu.
"""

from __future__ import annotations

import os
import platform
import subprocess
import tempfile

import requests

REPO = "tomekkrow-sys/file-manager"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"


def _parse_version(version: str) -> tuple:
    """Rozbij '1.2.3' na krotkę liczb do porównań."""
    out = []
    for part in version.lstrip("vV").split("."):
        num = ""
        for ch in part:
            if ch.isdigit():
                num += ch
            else:
                break
        out.append(int(num) if num else 0)
    return tuple(out)


def is_newer(latest: str, current: str) -> bool:
    """True, gdy `latest` jest nowsze niż `current`."""
    try:
        return _parse_version(latest) > _parse_version(current)
    except Exception:
        return False


def latest_release() -> tuple:
    """Zwróć (tag, {nazwa_pliku: url}) dla najnowszego release'u."""
    resp = requests.get(API_LATEST, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    tag = (data.get("tag_name") or "").lstrip("vV") or "0.0.0"
    assets = {a["name"]: a["browser_download_url"] for a in data.get("assets", [])}
    return tag, assets


def _platform_asset(assets: dict) -> tuple:
    """Dobierz właściwy plik do systemu (linux/mac/windows)."""
    system = platform.system().lower()
    exts = {
        "linux": (".deb", ".tar.gz"),
        "darwin": (".zip",),
        "windows": (".zip", ".exe"),
    }.get(system, (".zip",))
    for e in exts:
        for name, url in assets.items():
            if name.lower().endswith(e):
                return name, url
    return None


def download(url: str, dest: str, progress_cb=None) -> str:
    """Pobierz plik ze śledzeniem postępu (progress_cb(done, total))."""
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0)) or 0
    done = 0
    with open(dest, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=1024 * 256):
            if not chunk:
                continue
            fh.write(chunk)
            done += len(chunk)
            if progress_cb:
                progress_cb(done, total)
    return dest


def install_linux_deb(path: str) -> bool:
    """Zainstaluj .deb wymagając podniesienia uprawnień (pkexec > sudo)."""
    for tool in ("pkexec", "sudo"):
        if subprocess.run(["which", tool], capture_output=True).returncode == 0:
            return subprocess.run([tool, "dpkg", "-i", path]).returncode == 0
    return False


def install(path: str) -> bool:
    """Zainstaluj pobrany pakiet dla bieżącej platformy."""
    system = platform.system().lower()
    if system == "linux" and path.endswith(".deb"):
        return install_linux_deb(path)
    return False


def fetch_update(current_version: str) -> dict:
    """Kompletna logika sprawdzenia: zwraca słownik ze statusem.

    Statusy: 'update' (jest nowsza), 'current' (na najnowszej),
    'error' (opis błędu).
    """
    try:
        tag, assets = latest_release()
        if is_newer(tag, current_version):
            asset = _platform_asset(assets)
            return {"status": "update", "version": tag, "asset": asset}
        return {"status": "current", "version": tag, "asset": None}
    except Exception as exc:
        return {"status": "error", "version": None, "asset": None,
                "error": str(exc)}
