"""Wbudowany edytor/podgląd plików tekstowych."""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from core.fs_base import FileSystemError, FileSystemProvider

MAX_SIZE = 10 * 1024 * 1024  # 10 MB — powyżej tylko komunikat


class TextEditorDialog(QDialog):
    def __init__(self, provider: FileSystemProvider, path: str, parent=None):
        super().__init__(parent)
        self._provider, self._path = provider, path
        self.setWindowTitle(path.rsplit("/", 1)[-1])
        self.resize(800, 600)

        self._edit = QPlainTextEdit()
        self._edit.setFont(QFont("Monospace", 11))

        btn_save = QPushButton("Zapisz")
        btn_close = QPushButton("Zamknij")
        btn_save.clicked.connect(self._save)
        btn_close.clicked.connect(self.reject)
        bar = QHBoxLayout()
        bar.addStretch()
        bar.addWidget(btn_save)
        bar.addWidget(btn_close)

        layout = QVBoxLayout(self)
        layout.addWidget(self._edit, 1)
        layout.addLayout(bar)

        try:
            info = provider.stat(path)
            if info.size > MAX_SIZE:
                raise ValueError(f"plik zbyt duży ({info.size / 1e6:.1f} MB)")
            with provider.open_read(path) as f:
                data = f.read()
            self._edit.setPlainText(data.decode("utf-8", errors="replace"))
        except (FileSystemError, ValueError) as exc:
            self._edit.setPlainText(f"Nie można otworzyć pliku:\n{exc}")
            self._edit.setReadOnly(True)

    def _save(self) -> None:
        try:
            with self._provider.open_write(self._path) as f:
                f.write(self._edit.toPlainText().encode("utf-8"))
            self.accept()
        except FileSystemError as exc:
            QMessageBox.critical(self, "Błąd zapisu", str(exc))
