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
API_RELEASES = f"https://api.github.com/repos/{REPO}/releases?per_page=100"


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
    """Zwróć (tag, {nazwa_pliku: url}) dla NAJNOWSZEJ wersji (najwyższy semver).

    Pomija drafty i pre-release. Ignorujemy flagę „latest" GitHuba, bo ta
    zależy od daty publikacji, a nie numeru wersji — co prowadziło do sytuacji,
    gdy nowsza wersja nie była wykrywalna.
    """
    resp = requests.get(API_RELEASES, timeout=20)
    resp.raise_for_status()
    best_tag = "0.0.0"
    best_assets: dict = {}
    for rel in resp.json():
        if rel.get("draft") or rel.get("prerelease"):
            continue
        tag = (rel.get("tag_name") or "").lstrip("vV") or "0.0.0"
        if _parse_version(tag) > _parse_version(best_tag):
            best_tag = tag
            best_assets = {
                a["name"]: a["browser_download_url"]
                for a in rel.get("assets", [])
            }
    return best_tag, best_assets


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


def _install_via_askpass(path: str) -> bool:
    """Zainstaluj przez `sudo -A` z graficznym oknem hasła (ksshaskpass).

    Nie wymaga terminala — hasło wpisuje się w oknie Qt. Działa w sesji
    graficznej bez otwartego terminala.
    """
    ask = shutil.which("ksshaskpass") or shutil.which("ssh-askpass")
    if not ask:
        return False
    env = dict(os.environ)
    env["SUDO_ASKPASS"] = ask
    try:
        r = subprocess.run(
            ["sudo", "-A", "dpkg", "-i", path],
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            print("[updater] sudo -A dpkg -i nie powiodło się:", r.stderr.strip())
        return r.returncode == 0
    except Exception as exc:
        print("[updater] _install_via_askpass wyjątek:", exc)
        return False


def _install_via_terminal(path: str) -> bool:
    """Ostatnia deska ratunku: otwórz terminal graficzny i `sudo dpkg -i`."""
    candidates = [
        "/usr/bin/konsole", "/usr/bin/gnome-terminal", "/usr/bin/xterm",
        "/usr/bin/mate-terminal", "/usr/bin/xfce4-terminal",
    ]
    term = next((c for c in candidates if os.path.exists(c)), None)
    if term is None:
        for name in ("konsole", "gnome-terminal", "xterm"):
            p = shutil.which(name)
            if p:
                term = p
                break
    if not term:
        return False
    script = (
        f"sudo dpkg -i {shlex.quote(path)}; "
        f"c=$?; "
        f"if [ $c -eq 0 ]; then echo 'Zainstalowano pomyślnie.'; "
        f"else echo \"Błąd instalacji (kod $c).\"; fi; "
        f"echo; echo 'Naciśnij Enter, aby zamknąć to okno.'; read"
    )
    try:
        if "gnome-terminal" in term:
            subprocess.run([term, "--", "bash", "-c", script])
        else:
            subprocess.run([term, "-e", "bash", "-c", script])
        return True
    except Exception:
        return False


def install_linux_deb(path: str) -> bool:
    """Zainstaluj .deb, podnosząc uprawnienia najlepszą dostępną metodą.

    Kolejność: gdebi (polkit) -> sudo -A + graficzne hasło (ksshaskpass)
    -> terminal + sudo (ostateczność) -> xdg-open -> sudo bez tty.
    """
    for tool in ("gdebi-gtk", "gdebi"):
        if shutil.which(tool):
            if subprocess.run([tool, path]).returncode == 0:
                return True
    if _install_via_askpass(path):
        return True
    # 3) terminal + sudo — ostateczność, gdy brak graficznego hasła
    if _install_via_terminal(path):
        return True
    # 4) xdg-open — przekazanie pliku do systemowego instalatora
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
