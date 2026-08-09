"""
Operacje na plikach wykonywane w tle (QThread) z raportowaniem postępu.

UI tworzy FileOperation i podpina sygnały — wątek nie dotyka widgetów.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QThread, Signal

from core.fs_base import FileSystemError, FileSystemProvider


class FileOperation(QThread):
    """Bazowa operacja wsadowa na liście (provider, ścieżka)."""

    progressed = Signal(int, int, str)      # bajty_done, bajty_total, bieżący plik
    item_done = Signal(str)                 # zakończona pozycja
    failed = Signal(str, str)               # ścieżka, komunikat
    finished_all = Signal(int, int)         # liczba OK, liczba błędów

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def _progress(self, done: int, total: int, name: str) -> None:
        if not self._cancelled:
            self.progressed.emit(done, total, name)


class CopyOperation(FileOperation):
    """Kopiowanie między dowolnymi providerami (też chmura -> FTP)."""

    def __init__(self, items: List[tuple[FileSystemProvider, str]],
                 dst_provider: FileSystemProvider, dst_dir: str, parent=None):
        super().__init__(parent)
        self._items = items
        self._dst = dst_provider
        self._dst_dir = dst_dir.rstrip("/")

    def run(self) -> None:
        ok = errors = 0
        for provider, path in self._items:
            if self._cancelled:
                break
            name = path.rstrip("/").rsplit("/", 1)[-1]
            try:
                self._dst.copy(provider, path, f"{self._dst_dir}/{name}",
                               self._progress)
                self.item_done.emit(path)
                ok += 1
            except FileSystemError as exc:
                self.failed.emit(path, str(exc))
                errors += 1
        self.finished_all.emit(ok, errors)


class MoveOperation(FileOperation):
    def __init__(self, items: List[tuple[FileSystemProvider, str]],
                 dst_provider: FileSystemProvider, dst_dir: str, parent=None):
        super().__init__(parent)
        self._items = items
        self._dst = dst_provider
        self._dst_dir = dst_dir.rstrip("/")

    def run(self) -> None:
        ok = errors = 0
        for provider, path in self._items:
            if self._cancelled:
                break
            name = path.rstrip("/").rsplit("/", 1)[-1]
            try:
                provider.move(self._dst, path, f"{self._dst_dir}/{name}",
                              self._progress)
                self.item_done.emit(path)
                ok += 1
            except FileSystemError as exc:
                self.failed.emit(path, str(exc))
                errors += 1
        self.finished_all.emit(ok, errors)


class DeleteOperation(FileOperation):
    def __init__(self, items: List[tuple[FileSystemProvider, str]], parent=None):
        super().__init__(parent)
        self._items = items

    def run(self) -> None:
        ok = errors = 0
        for provider, path in self._items:
            if self._cancelled:
                break
            try:
                provider.delete(path, self._progress)
                self.item_done.emit(path)
                ok += 1
            except FileSystemError as exc:
                self.failed.emit(path, str(exc))
                errors += 1
        self.finished_all.emit(ok, errors)
