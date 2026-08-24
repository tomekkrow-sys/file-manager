"""Okno analizy pamięci — fizyczne dyski systemu, każdy osobno.

Dla wybranego dysku pokazuje wolne miejsce oraz rozmiary katalogów
top-level. Opcjonalnie można dołączyć zewnętrzne dyski montowane przez SSH
(sshfs).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QProgressBar, QPushButton, QVBoxLayout,
)

from core.storage_analysis import (
    DiskDirectoryScanner, _real, human_size, list_disks,
)

_OTHER_MOUNT_COLOR = QColor("#808080")


class StorageAnalysisDialog(QDialog):
    def __init__(self, root_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Analiza pamięci — dyski systemu")
        self.resize(880, 560)

        self._scanner: DiskDirectoryScanner | None = None
        self._disks_list = []
        self._dir_sizes: dict[str, int] = {}
        self._skipped: list[str] = []

        self._disks = QListWidget()
        self._disks.setMaximumWidth(400)
        self._disks.currentItemChanged.connect(self._on_disk_selected)
        self._ssh_check = QCheckBox("Pokaż dyski SSH (sshfs)")
        self._ssh_check.toggled.connect(self._reload_disks)
        self._refresh = QPushButton("Odśwież")
        self._refresh.clicked.connect(self._reload_disks)

        left = QVBoxLayout()
        left.addWidget(QLabel("Dyski:"))
        left.addWidget(self._disks, 1)
        ssh_row = QHBoxLayout()
        ssh_row.addWidget(self._ssh_check)
        ssh_row.addWidget(self._refresh)
        left.addLayout(ssh_row)

        self._info = QLabel("Wybierz dysk…")
        self._info.setWordWrap(True)
        self._usage = QProgressBar()
        self._usage.setRange(0, 100)
        self._usage.setTextVisible(True)
        self._dirs = QListWidget()
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._status = QLabel("")

        right = QVBoxLayout()
        right.addWidget(self._info)
        right.addWidget(self._usage)
        right.addWidget(QLabel("Katalogi na dysku:"))
        right.addWidget(self._dirs, 1)
        right.addWidget(self._progress)
        right.addWidget(self._status)

        layout = QHBoxLayout(self)
        layout.addLayout(left)
        layout.addLayout(right, 1)

        self._root_path = root_path
        self._reload_disks()

    # ----- lista dysków -----

    def _reload_disks(self) -> None:
        self._cancel_scan()
        self._disks.clear()
        self._disks_list = list_disks(include_ssh=self._ssh_check.isChecked())
        if not self._disks_list:
            self._info.setText("Nie znaleziono dysków. Sprawdź /proc/mounts.")
            return
        for disk in self._disks_list:
            item = QListWidgetItem(
                f"{disk.mountpoint}\n{disk.device}  ({disk.fstype})\n"
                f"{human_size(disk.total)}  ·  wolne {human_size(disk.free)}")
            item.setData(Qt.ItemDataRole.UserRole, disk.mountpoint)
            self._disks.addItem(item)
        # podświetlenie dysku zawierającego bieżący katalog
        current = self._disk_for_path(self._root_path)
        for i, disk in enumerate(self._disks_list):
            if disk.mountpoint == current:
                self._disks.setCurrentRow(i)
                return

    def _disk_for_path(self, path: str) -> str | None:
        real = _real(path)
        best, best_len = None, -1
        for disk in self._disks_list:
            mount = _real(disk.mountpoint)
            if (real == mount or real.startswith(mount + "/")
                    or (mount == "/" and real.startswith("/"))):
                if len(mount) > best_len:
                    best, best_len = disk.mountpoint, len(mount)
        return best

    def _on_disk_selected(self, current: QListWidgetItem | None,
                          previous: QListWidgetItem | None) -> None:
        self._cancel_scan()
        self._dirs.clear()
        self._dir_sizes.clear()
        self._skipped.clear()
        self._info.setText("Wybierz dysk…")
        self._status.setText("")
        if current is None:
            return
        disk = self._disks_list[self._disks.row(current)]
        pct = int(disk.used / disk.total * 100) if disk.total else 0
        self._usage.setValue(pct)
        self._usage.setFormat(
            f"użyto {pct}%  ({human_size(disk.used)} z {human_size(disk.total)})")
        self._info.setText(
            f"💽 {disk.device}  ({disk.fstype})\n"
            f"Montaż: {disk.mountpoint}\n"
            f"Wolne: {human_size(disk.free)}")

        skip = {_real(m.mountpoint) for m in self._disks_list
                if m.mountpoint != disk.mountpoint}
        self._progress.setRange(0, 0)
        self._status.setText("Skanowanie katalogów…")
        self._scanner = DiskDirectoryScanner(disk.mountpoint, skip, parent=self)
        self._scanner.dir_size.connect(self._on_dir_size)
        self._scanner.skipped_mount.connect(self._on_skipped_mount)
        self._scanner.progressed.connect(
            lambda n, path: self._status.setText(
                f"Skanowanie… {n} plików"))
        self._scanner.finished_scan.connect(self._on_scan_finished)
        self._scanner.start()

    # ----- wyniki skanowania -----

    def _on_dir_size(self, name: str, size: int) -> None:
        self._dir_sizes[name] = size
        self._dirs.addItem(f"{human_size(size):>10}  {name}")

    def _on_skipped_mount(self, name: str) -> None:
        self._skipped.append(name)
        item = QListWidgetItem(f"{name}   (osobny dysk — wybierz z listy)")
        item.setForeground(_OTHER_MOUNT_COLOR)
        self._dirs.addItem(item)

    def _on_scan_finished(self) -> None:
        self._progress.setRange(0, 100)
        self._progress.setValue(100)
        self._status.setText("Gotowe.")
        self._dirs.clear()
        for name, size in sorted(self._dir_sizes.items(),
                                 key=lambda kv: kv[1], reverse=True):
            self._dirs.addItem(f"{human_size(size):>10}  {name}")
        for name in self._skipped:
            item = QListWidgetItem(f"{name}   (osobny dysk — wybierz z listy)")
            item.setForeground(_OTHER_MOUNT_COLOR)
            self._dirs.addItem(item)

    def _cancel_scan(self) -> None:
        if self._scanner is not None:
            self._scanner.cancel()
            self._scanner.wait(500)
            self._scanner = None

    def closeEvent(self, event) -> None:
        self._cancel_scan()
        super().closeEvent(event)
