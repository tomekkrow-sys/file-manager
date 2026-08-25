"""Automatyczna aktualizacja z GitHub Releases.

Sprawdza najnowszy release w repo, porównuje wersję z bieżącą i — jeśli jest
nowsza — pobiera pakiet dla bieżącej platformy oraz instaluje go (Linux: .deb
przez pkexec/sudo). Działa niezależnie od tego, czy apka uruchomiona jest z
kodu, czy z zainstalowanego pakietu.
"""

from __future__ import annotations

import os
import platform
import shlex
import shutil
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


def _install_via_terminal(path: str) -> bool:
    """Otwórz terminal graficzny i uruchom `sudo dpkg -i` (pyta o hasło)."""
    term = (shutil.which("konsole")
            or shutil.which("gnome-terminal")
            or shutil.which("xterm")
            or shutil.which("mate-terminal")
            or shutil.which("xfce4-terminal"))
    if not term:
        return False
    script = (
        f"sudo dpkg -i {shlex.quote(path)}; "
        f"c=$?; "
        f"if [ $c -eq 0 ]; then echo 'Zainstalowano pomyślnie.'; "
        f"else echo \"Błąd instalacji (kod $c).\"; fi; "
        f"echo; echo 'Naciśnij Enter, aby zamknąć to okno.'; read"
    )
    subprocess.run([term, "-e", f"bash -c {shlex.quote(script)}"])
    return True


def install_linux_deb(path: str) -> bool:
    """Zainstaluj .deb, podnosząc uprawnienia najlepszą dostępną metodą.

    Kolejność: gdebi (hasło przez polkit) -> terminal + sudo (najbardziej
    niezawodne w sesji graficznej) -> xdg-open (menedżer pakietów) ->
    sudo bez tty (rzadko zadziała).
    """
    # 1) gdebi — instaluje razem z zależnościami, hasło przez polkit
    for tool in ("gdebi-gtk", "gdebi"):
        if shutil.which(tool):
            if subprocess.run([tool, path]).returncode == 0:
                return True
    # 2) terminal + sudo — działa wszędzie, gdzie jest terminal i hasło sudo
    if _install_via_terminal(path):
        return True
    # 3) xdg-open — przekazanie pliku do systemowego instalatora
    if shutil.which("xdg-open"):
        subprocess.run(["xdg-open", path])
        return True
    # 4) sudo bez tty — ostateczność (z GUI zwykle nie zadziała)
    if shutil.which("sudo"):
        return subprocess.run(["sudo", "dpkg", "-i", path]).returncode == 0
    return False


def installed_deb_version() -> str:
    """Zwróć wersję zainstalowanego pakietu `file-manager` (puste = brak)."""
    try:
        out = subprocess.run(["dpkg", "-s", "file-manager"],
                             capture_output=True, text=True)
        for line in out.stdout.splitlines():
            if line.startswith("Version:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return ""


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
            return {"status": "update", "version": tag, "asset": asset,
                    "current": current_version}
        return {"status": "current", "version": tag, "asset": None,
                "current": current_version}
    except Exception as exc:
        return {"status": "error", "version": None, "asset": None,
                "error": str(exc), "current": current_version}
