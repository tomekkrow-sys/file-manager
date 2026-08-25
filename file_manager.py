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

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QIcon
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


def _resolve_version() -> str:
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


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("File Manager")
    app.setOrganizationName("FileManager")
    app.setApplicationVersion(VERSION)

    set_language(str(QSettings("FileManager", "FileManager").value("language", "pl")))

    font = QFont()
    font.setPointSize(12)
    app.setFont(font)

    if os.path.exists(_ICON):
        app.setWindowIcon(QIcon(_ICON))

    ThemeManager.apply_theme(app, "dark")

    mode = str(QSettings("FileManager", "FileManager").value("ui/mode", "single"))
    if mode == "dual":
        from ui.two_panel_window import DualPanelWindow
        window = DualPanelWindow()
    else:
        window = MainWindow()
    window.setWindowTitle(f"File Manager v{VERSION}")
    window.show()
    return app.exec()


if __name__ == "__main__":
    print(f"File Manager v{VERSION}")
    sys.exit(main())
