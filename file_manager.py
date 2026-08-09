#!/usr/bin/env python3
"""
File Manager — punkt wejścia.

Menedżer plików inspirowany File Manager Plus (Android): lokalne pliki,
FTP (klient + serwer), NAS/SMB, chmury (Google Drive / Dropbox / OneDrive),
archiwa ZIP/TAR/GZ/XZ, wbudowane podglądy mediów i analiza pamięci.
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("File Manager")
    app.setOrganizationName("FileManager")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
