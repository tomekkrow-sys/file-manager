"""Analiza zajętości pamięci — skanowanie w tle + grupowanie wg typu."""

from __future__ import annotations

import mimetypes
import os
from collections import defaultdict
from dataclasses import dataclass
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


def _real(path: str) -> str:
    """Rzeczywista ścieżka bez końcowego ukośnika ('/' pozostaje '/').
    """
    return os.path.realpath(path).rstrip("/") or "/"


def is_virtual_mount(path: str, mounts: Optional[set] = None) -> bool:
    """Czy ścieżka wskazuje dokładnie na wirtualny punkt montowania?"""
    if mounts is None:
        mounts = virtual_mount_points()
    if not mounts:
        return False
    return _real(path) in mounts


@dataclass
class DiskInfo:
    device: str        # np. /dev/nvme0n1p2 lub user@host:/path (sshfs)
    mountpoint: str    # np. /, /home, /mnt/dane
    fstype: str        # np. ext4, btrfs, fuse.sshfs
    total: int         # bajty
    used: int          # bajty
    free: int          # wolne bajty (dla zwykłego użytkownika)


def _parse_mounts(mounts_file: str = "/proc/mounts") -> list:
    """(device, mountpoint, fstype) z /proc/mounts — osobno do testów."""
    records: list = []
    try:
        with open(mounts_file, encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3:
                    records.append((parts[0], parts[1], parts[2]))
    except OSError:
        pass
    return records


_statvfs = os.statvfs  # osobno do testów


def _is_sshfs(device: str, fstype: str) -> bool:
    """Czy to montowanie sshfs (zewnętrzny dysk widziany przez SSH)?"""
    return fstype.startswith("fuse.sshfs") or (
        fstype == "fuse" and "@" in device and ":" in device)


def list_disks(include_ssh: bool = False,
               mounts_file: str = "/proc/mounts") -> list[DiskInfo]:
    """Fizyczne dyski systemu, każdy osobno.

    Domyślnie tylko urządzenia blokowe na dysku (/dev/*). Z ``include_ssh``
    dołączane są również montowania sshfs. Każdy punkt montowania liczony jest
    raz; pseudosystemy (proc, sysfs, tmpfs…) są pomijane.
    """
    disks: list[DiskInfo] = []
    seen: set[str] = set()
    for device, mountpoint, fstype in _parse_mounts(mounts_file):
        if fstype in _VIRTUAL_FS_TYPES:
            continue
        if _is_sshfs(device, fstype):
            if not include_ssh:
                continue
        elif not device.startswith("/dev/"):
            continue  # np. overlay, network — tylko dyski fizyczne / SSH
        real = _real(mountpoint)
        if real in seen:
            continue
        seen.add(real)
        try:
            st = _statvfs(mountpoint)
        except OSError:
            continue
        total = st.f_frsize * st.f_blocks
        free = st.f_frsize * st.f_bavail
        disks.append(DiskInfo(device, mountpoint, fstype,
                              total, total - free, free))
    disks.sort(key=lambda d: d.mountpoint)
    return disks


class DiskDirectoryScanner(QThread):
    """Skanuje w tle rozmiary katalogów top-level na wskazanym dysku.

    Nie schodzi do katalogów należących do innych dysków (każdy dysk
    rozpatrywany osobno) ani do pseudosystemów plików.
    """

    dir_size = Signal(str, int)     # nazwa katalogu top-level, bajty
    skipped_mount = Signal(str)     # katalog będący osobnym dyskiem
    progressed = Signal(int, str)   # przeskanowane pliki, bieżąca ścieżka
    finished_scan = Signal()

    def __init__(self, mountpoint: str, skip_mountpoints: Optional[set] = None,
                 parent=None):
        super().__init__(parent)
        self._root = Path(mountpoint)
        self._skip = {_real(p) for p in (skip_mountpoints or ())}
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        mounts = virtual_mount_points()
        root_real = _real(str(self._root))
        try:
            entries = sorted(os.scandir(self._root), key=lambda e: e.name)
        except OSError:
            self.finished_scan.emit()
            return

        for entry in entries:
            if self._cancelled:
                break
            if entry.name.startswith(".") or not entry.is_dir():
                continue
            real = _real(entry.path)
            if is_virtual_mount(real, mounts):
                continue
            if real in self._skip and real != root_real:
                self.skipped_mount.emit(entry.name)
                continue
            size, files = self._walk(entry.path, mounts)
            if self._cancelled:
                break
            self.dir_size.emit(entry.name, size)
        self.finished_scan.emit()

    def _walk(self, start: str, mounts: set) -> tuple:
        total = 0
        files = 0
        for dirpath, dirnames, filenames in os.walk(start):
            if self._cancelled:
                break
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".")
                and not is_virtual_mount(os.path.join(dirpath, d), mounts)
                and _real(os.path.join(dirpath, d)) not in self._skip
            ]
            for fname in filenames:
                if self._cancelled:
                    break
                fpath = os.path.join(dirpath, fname)
                try:
                    total += os.lstat(fpath).st_size
                except OSError:
                    continue
                files += 1
                if files % 500 == 0:
                    self.progressed.emit(files, fpath)
        return total, files


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
