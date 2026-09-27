#!/usr/bin/env python3
"""File Manager — punkt wejścia.

Menedżer plików inspirowany File Manager Plus (Android): lokalne pliki,
FTP (klient + serwer), NAS/SMB, chmury (Google Drive / Dropbox / OneDrive),
archiwa ZIP/TAR/GZ/XZ, wbudowane podglądy mediów i analiza pamięci.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QFont, QIcon, QKeySequence
from PySide6.QtWidgets import QApplication

from core.i18n import set_language
from ui.main_window import MainWindow
from ui.theme_manager import ThemeManager

_ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "resources", "icons", "file_manager.png")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


VERSION = "0.1.0"

# Globalne skalowanie UI
_BASE_FONT_SIZE = 13
_zoom_level = 0  # offset od bazowej (0 = normal, +1 = więszy, -1 = mniejszy)


def _resolve_version() -> str:
    for cand in (os.path.join(os.getcwd(), "version.txt"),
                 os.path.join(os.getcwd(), "_internal", "version.txt")):
        try:
            if os.path.exists(cand):
                with open(cand, encoding="utf-8") as fh:
                    v = fh.read().strip().lstrip("v")
                    if v:
                        return v
        except Exception:
            pass
    try:
        out = subprocess.run(
            ["git", "describe", "--tags", "--exact-match"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip().lstrip("v")
    except Exception:
        pass
    return VERSION


VERSION = _resolve_version()


def _apply_zoom(app: QApplication) -> None:
    """Zastosuj bieżący poziom zoom do fonta i stylu."""
    size = _BASE_FONT_SIZE + _zoom_level
    size = max(8, min(24, size))  # clamp 8–24
    font = QFont("Segoe UI", size)
    font.setWeight(QFont.Weight.Medium)
    app.setFont(font)
    # Przeładuj styl z nowym fontem
    saved = str(QSettings("FileManager", "FileManager").value("ui/theme", "dark"))
    ThemeManager.apply_theme(app, saved, font_size=size)
    # Zapisz zoom
    QSettings("FileManager", "FileManager").setValue("ui/zoom", _zoom_level)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("File Manager")
    app.setOrganizationName("FileManager")
    app.setApplicationVersion(VERSION)

    set_language(str(QSettings("FileManager", "FileManager").value("language", "pl")))

    # Wczytaj zapisany zoom
    global _zoom_level
    _zoom_level = int(QSettings("FileManager", "FileManager").value("ui/zoom", 0))

    _apply_zoom(app)

    if os.path.exists(_ICON):
        app.setWindowIcon(QIcon(_ICON))

    mode = str(QSettings("FileManager", "FileManager").value("ui/mode", "single"))
    if mode == "dual":
        try:
            from ui.two_panel_window import DualPanelWindow
            window = DualPanelWindow()
        except Exception as exc:
            logging.warning("Nie udało się uruchomić trybu dwupanelowego: %s — "
                            "powrót do trybu jednopanelowego.", exc)
            QSettings("FileManager", "FileManager").setValue("ui/mode", "single")
            window = MainWindow()
    else:
        window = MainWindow()
    window.setWindowTitle(f"File Manager v{VERSION}")

    # Globalne skróty Ctrl+/Ctrl-/Ctrl+0
    def zoom_in():
        global _zoom_level
        _zoom_level = min(11, _zoom_level + 1)
        _apply_zoom(app)

    def zoom_out():
        global _zoom_level
        _zoom_level = max(-5, _zoom_level - 1)
        _apply_zoom(app)

    def zoom_reset():
        global _zoom_level
        _zoom_level = 0
        _apply_zoom(app)

    from PySide6.QtGui import QShortcut
    sc_in = QShortcut(QKeySequence("Ctrl+="), window)
    sc_in.activated.connect(zoom_in)
    sc_in2 = QShortcut(QKeySequence("Ctrl++"), window)
    sc_in2.activated.connect(zoom_in)
    sc_out = QShortcut(QKeySequence("Ctrl+-"), window)
    sc_out.activated.connect(zoom_out)
    sc_reset = QShortcut(QKeySequence("Ctrl+0"), window)
    sc_reset.activated.connect(zoom_reset)

    window.show()
    return app.exec()


if __name__ == "__main__":
    print(f"File Manager v{VERSION}")
    sys.exit(main())
