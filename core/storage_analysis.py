"""Analiza zajętości pamięci — skanowanie w tle + grupowanie wg typu."""

from __future__ import annotations

import mimetypes
import os
from collections import defaultdict
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal

CATEGORIES = {
    "Obrazy": ("image/",),
    "Wideo": ("video/",),
    "Audio": ("audio/",),
    "Dokumenty": ("text/", "application/pdf", "application/msword",
                  "application/vnd.openxmlformats", "application/epub"),
    "Archiwa": ("application/zip", "application/x-tar", "application/gzip",
                "application/x-xz", "application/x-bzip2", "application/x-7z"),
}

# Pseudosystemy plików — nie zajmują realnej pamięci dyskowej (np. /proc/kcore
# "ma" rozmiar równy RAM i zafałszowuje analizę największych plików).
_VIRTUAL_FS_TYPES = (
    "proc", "sysfs", "devtmpfs", "devpts", "tmpfs",
    "cgroup", "cgroup2", "binfmt_misc", "securityfs",
    "pstore", "bpf", "mqueue", "hugetlbfs", "configfs",
    "debugfs", "tracefs", "fusectl", "autofs", "nsfs", "rpc_pipefs",
)


def virtual_mount_points() -> set:
    """Punkty montowania pseudosystemów plików (np. /proc, /sys, /dev, /run).

    Parsujemy /proc/mounts, żeby nie pomijać np. katalogu użytkownika, który
    przypadkiem nazywa się "proc", a jednocześnie wycinać wszystkie wirtualne
    montowania.
    """
    mounts: set[str] = set()
    try:
        with open("/proc/mounts", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3 and parts[2] in _VIRTUAL_FS_TYPES:
                    mounts.add(parts[1].rstrip("/") or "/")
    except OSError:
        pass
    return mounts


def is_virtual_mount(path: str, mounts: Optional[set] = None) -> bool:
    """Czy ścieżka wskazuje dokładnie na wirtualny punkt montowania?"""
    if mounts is None:
        mounts = virtual_mount_points()
    if not mounts:
        return False
    real = os.path.realpath(path).rstrip("/") or "/"
    return real in mounts


def categorize(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or ""
    for category, prefixes in CATEGORIES.items():
        if any(mime.startswith(p) or mime == p for p in prefixes):
            return category
    return "Inne"


class StorageAnalyzer(QThread):
    """Skanuje katalog w tle; emituje wyniki zbiorcze."""

    progressed = Signal(int, str)          # przeskanowane pliki, bieżąca ścieżka
    finished_scan = Signal(dict, list, int)  # {kategoria: bajty}, największe pliki, total

    def __init__(self, root: str, top_n: int = 20, parent=None):
        super().__init__(parent)
        self._root = Path(root)
        self._top_n = top_n
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        by_category: dict[str, int] = defaultdict(int)
        largest: list[tuple[int, str]] = []
        total = 0
        scanned = 0

        mounts = virtual_mount_points()
        # Jeśli analizujemy sam pseudosystem (np. /proc) — nie ma czego skanować.
        if is_virtual_mount(str(self._root), mounts):
            self.finished_scan.emit({}, [], 0)
            return

        for dirpath, dirnames, filenames in os.walk(self._root):
            if self._cancelled:
                break
            # pomijamy katalogi ukryte oraz pseudosystemy plików (/proc, /sys,
            # /dev, /run…), żeby np. /proc/kcore nie fałszował analizy
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(".")
                           and not is_virtual_mount(os.path.join(dirpath, d), mounts)]
            for fname in filenames:
                if self._cancelled:
                    break
                fpath = Path(dirpath) / fname
                try:
                    size = fpath.lstat().st_size
                except OSError:
                    continue
                total += size
                scanned += 1
                by_category[categorize(fpath)] += size
                largest.append((size, str(fpath)))
                largest.sort(key=lambda x: x[0], reverse=True)
                del largest[self._top_n:]
                if scanned % 500 == 0:
                    self.progressed.emit(scanned, str(fpath))

        self.finished_scan.emit(dict(by_category), largest, total)


def human_size(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"
