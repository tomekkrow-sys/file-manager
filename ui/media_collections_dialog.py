"""Okno zbiorów mediów — Muzyka / Wideo / Zdjęcia / Dokumenty z dysków.

Skanuje fizyczne dyski systemu (opcjonalnie również sshfs) w tle i grupuje
pliki wg typu. Kliknięcie/Enter otwiera plik wbudowanym podglądem.
"""

from __future__ import annotations

import mimetypes
from collections import defaultdict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QProgressBar, QVBoxLayout,
)

import core.archives as archives
from core.local_fs import LocalFileSystem
from core.media_collections import COLLECTIONS, MediaCollector
from core.storage_analysis import human_size, list_disks

_LOCAL = LocalFileSystem()


class MediaCollectionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Zbiory mediów")
        self.resize(780, 560)

        self._collector: MediaCollector | None = None
        self._items: dict[str, list] = defaultdict(list)

        self._collections = QListWidget(maximumWidth=220)
        self._collections.currentItemChanged.connect(self._show_collection)
        for name in COLLECTIONS:
            self._collections.addItem(QListWidgetItem(name))

        self._ssh_check = QCheckBox("Uwzględnij dyski SSH (sshfs)")
        self._ssh_check.toggled.connect(self._start_scan)

        self._files = QListWidget()
        self._files.itemDoubleClicked.connect(self._open_item)
        self._files.itemActivated.connect(self._open_item)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._status = QLabel("Skanowanie dysków…")

        left = QVBoxLayout()
        left.addWidget(QLabel("Zbiory:"))
        left.addWidget(self._collections, 1)
        left.addWidget(self._ssh_check)

        right = QVBoxLayout()
        right.addWidget(QLabel("Pliki (Enter lub dwuklik — podgląd):"))
        right.addWidget(self._files, 1)
        right.addWidget(self._progress)
        right.addWidget(self._status)

        layout = QHBoxLayout(self)
        layout.addLayout(left)
        layout.addLayout(right, 1)

        self._start_scan()

    def _start_scan(self) -> None:
        self._cancel_scan()
        self._items.clear()
        self._files.clear()
        for i, name in enumerate(COLLECTIONS):
            self._collections.item(i).setText(name)
        self._progress.setRange(0, 0)
        self._status.setText("Skanowanie dysków…")

        mounts = [d.mountpoint for d in list_disks(
            include_ssh=self._ssh_check.isChecked())]
        if not mounts:
            self._status.setText("Brak dysków do przeskanowania.")
            return
        self._collector = MediaCollector(mounts, parent=self)
        self._collector.progressed.connect(
            lambda n, path: self._status.setText(f"Skanowanie… {n} plików"))
        self._collector.disk_finished.connect(self._on_disk_finished)
        self._collector.finished_scan.connect(self._on_scan_finished)
        self._collector.start()

    def _on_disk_finished(self, batch: dict) -> None:
        for name, entries in batch.items():
            self._items[name].extend(entries)
            self._update_count(name)

    def _on_scan_finished(self) -> None:
        self._progress.setRange(0, 100)
        self._progress.setValue(100)
        self._status.setText("Gotowe.")
        self._refresh_files()

    def _update_count(self, name: str) -> None:
        idx = list(COLLECTIONS).index(name)
        self._collections.item(idx).setText(f"{name} ({len(self._items[name])})")

    def _show_collection(self, current: QListWidgetItem | None,
                         previous: QListWidgetItem | None) -> None:
        self._refresh_files()

    def _refresh_files(self) -> None:
        current = self._collections.currentItem()
        self._files.clear()
        if current is None:
            return
        name = current.text().split(" (")[0]
        entries = sorted(self._items.get(name, []),
                         key=lambda e: e[0].casefold())
        for fname, size, path in entries:
            item = QListWidgetItem(f"{human_size(size):>10}  {fname}")
            item.setToolTip(path)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self._files.addItem(item)

    def _open_item(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        name = path.rsplit("/", 1)[-1]
        mime = mimetypes.guess_type(name)[0] or ""
        if mime.startswith("image/"):
            from ui.viewers.image_viewer import ImageViewerDialog
            ImageViewerDialog(_LOCAL, path, self,
                              browse=self._browse_session("image/", path)).exec()
        elif mime.startswith("audio/") or mime.startswith("video/"):
            from ui.viewers.media_player import MediaPlayerDialog
            kind = "video/" if mime.startswith("video/") else "audio/"
            MediaPlayerDialog(_LOCAL, path, is_video=kind == "video/",
                              parent=self,
                              browse=self._browse_session(kind, path)).exec()
        elif mime.startswith("text/") or name.endswith(
                (".py", ".json", ".md", ".xml", ".csv", ".log", ".txt",
                 ".ini", ".cfg")):
            from ui.viewers.text_editor import TextEditorDialog
            TextEditorDialog(_LOCAL, path, self).exec()
        elif archives.is_archive(name):
            self._show_archive(path)
        else:
            QMessageBox.information(self, name,
                                    f"Brak wbudowanego podglądu dla typu: {mime}")

    def _browse_session(self, kind: str, path: str):
        """Sesja nawigacji: pliki bieżącego zbioru danego typu (np. zdjęcia)."""
        from core.media_collections import MediaBrowseSession
        current = self._collections.currentItem()
        name = current.text().split(" (")[0] if current else None
        paths = []
        if name:
            for fname, _size, p in self._items.get(name, []):
                if (mimetypes.guess_type(fname)[0] or "").startswith(kind):
                    paths.append(p)
        return MediaBrowseSession(paths, path)

    def _show_archive(self, path: str) -> None:
        try:
            entries = archives.list_archive(path)
        except archives.ArchiveError as exc:
            QMessageBox.critical(self, "Archiwum", str(exc))
            return
        preview = "\n".join(f"{human_size(s):>10}  {n}"
                            for n, s in entries[:200])
        QMessageBox.information(
            self, "Archiwum",
            f"{len(entries)} pozycji.\n\n{preview}" if entries
            else "Archiwum puste.")

    def _cancel_scan(self) -> None:
        if self._collector is not None:
            self._collector.cancel()
            self._collector.wait(500)
            self._collector = None

    def closeEvent(self, event) -> None:
        self._cancel_scan()
        super().closeEvent(event)
