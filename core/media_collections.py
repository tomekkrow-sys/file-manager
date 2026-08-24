"""Zbiory mediów — skanowanie dysków i grupowanie plików wg typu.

Muzyka / Wideo / Zdjęcia / Dokumenty zebrane z fizycznych dysków systemu.
"""

from __future__ import annotations

import os
import stat
from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from core.storage_analysis import (
    _real, is_virtual_mount, virtual_mount_points,
)
from core.storage_analysis import categorize


# nazwa zbioru -> kategoria z core.storage_analysis.CATEGORIES
COLLECTIONS = {
    "Muzyka": "Audio",
    "Wideo": "Wideo",
    "Zdjęcia": "Obrazy",
    "Dokumenty": "Dokumenty",
}


class MediaBrowseSession:
    """Nawigacja po plikach zbioru w podglądzie (strzałki ←/→, auto-oglądanie).

    Trzyma listę ścieżek danego typu (np. wszystkie zdjęcia ze zbioru) i bieżący
    indeks; ``next()``/``prev()`` zwracają kolejną ścieżkę lub ``None`` na końcu.
    """

    def __init__(self, paths, start_path: str):
        self._paths = list(paths)
        try:
            self._index = self._paths.index(start_path)
        except ValueError:
            self._index = 0

    def __len__(self) -> int:
        return len(self._paths)

    def current(self) -> str:
        return self._paths[self._index]

    def next(self):
        if self._index < len(self._paths) - 1:
            self._index += 1
            return self._paths[self._index]
        return None

    def prev(self):
        if self._index > 0:
            self._index -= 1
            return self._paths[self._index]
        return None

    def first(self) -> str:
        self._index = 0
        return self._paths[0]


class MediaCollector(QThread):
    """Skanuje dyski w tle i zbiera media według kategorii.

    Wynik: słownik {nazwa zbioru: [(nazwa, rozmiar, ścieżka), …]}.
    Emisje ``disk_finished`` przychodzą inkrementalnie po każdym dysku.
    """

    progressed = Signal(int, str)        # przeskanowane pliki, bieżąca ścieżka
    disk_finished = Signal(dict)         # {zbiór: [(name, size, path), …]}
    finished_scan = Signal()

    def __init__(self, mountpoints, parent=None):
        super().__init__(parent)
        self._mountpoints = [_real(m) for m in mountpoints]
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        mounts = virtual_mount_points()
        seen_paths: set[str] = set()
        scanned = 0
        for mp in self._mountpoints:
            if self._cancelled:
                break
            batch: dict[str, list] = defaultdict(list)
            skip = {m for m in self._mountpoints if m != mp}
            for dirpath, dirnames, filenames in os.walk(mp):
                if self._cancelled:
                    break
                dirnames[:] = [
                    d for d in dirnames
                    if not d.startswith(".")
                    and not is_virtual_mount(os.path.join(dirpath, d), mounts)
                    and _real(os.path.join(dirpath, d)) not in skip
                ]
                for fname in filenames:
                    if self._cancelled:
                        break
                    if fname.startswith("."):
                        continue
                    fpath = os.path.join(dirpath, fname)
                    try:
                        st = os.lstat(fpath)
                    except OSError:
                        continue
                    if not stat.S_ISREG(st.st_mode):
                        continue
                    real = os.path.realpath(fpath)
                    if real in seen_paths:
                        continue
                    seen_paths.add(real)
                    category = categorize(Path(fname))
                    for collection, key in COLLECTIONS.items():
                        if category == key:
                            batch[collection].append(
                                (fname, st.st_size, fpath))
                            break
                    scanned += 1
                    if scanned % 500 == 0:
                        self.progressed.emit(scanned, fpath)
            if batch and not self._cancelled:
                self.disk_finished.emit(dict(batch))
        self.finished_scan.emit()
