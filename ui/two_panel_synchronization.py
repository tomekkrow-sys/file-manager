"""Panel dwupanelowy — synchronizacja nawigacji, porównanie i sklejanie katalogów."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QProgressDialog

from core.fs_base import FileInfo, FileSystemProvider


class _DirectoryHasher(QThread):
    """Oblicza hash katalogu (rekurencyjnie) do porównywania zawartości."""
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, provider: FileSystemProvider, path: str, parent=None):
        super().__init__(parent)
        self.provider = provider
        self.path = path

    def run(self) -> None:
        try:
            h = hashlib.sha256()
            self._hash_dir(h, self.path)
            self.finished.emit(h.hexdigest()[:16])
        except Exception as exc:
            self.failed.emit(str(exc))

    def _hash_dir(self, h: hashlib._hashlib.HASH, path: str) -> None:
        try:
            items = sorted(self.provider.list_dir(path), key=lambda i: i.name)
            for item in items:
                h.update(item.name.encode() + item.path.encode())
                if item.is_dir:
                    self._hash_dir(h, item.path)
                else:
                    with self.provider.open_read(item.path) as f:
                        while chunk := f.read(65536):
                            h.update(chunk)
        except Exception as exc:
            raise RuntimeError(f"Hashowanie: {path}") from exc


class SyncController:
    """Sterownik synchronizacji między panelami."""

    def __init__(self, left_provider: FileSystemProvider, right_provider: FileSystemProvider):
        self.left = left_provider
        self.right = right_provider

    def sync_path(self, path: str, from_left_to_right: bool = True) -> None:
        """Synchronizuje jeden katalog między panelami."""
        if from_left_to_right:
            src = self.left
            dst = self.right
        else:
            src = self.right
            dst = self.left

        src_path = src.root_path if hasattr(src, "root_path") else "/"
        dst_path = dst.root_path if hasattr(dst, "root_path") else "/"

    def compare_paths(self, path: str) -> dict:
        """Porównuje ten sam katalog w obu panelach."""
        result = {"in_left": [], "in_right": [], "only_left": [], "only_right": [], "common": []}
        return result


def compare_directories(
    provider1: FileSystemProvider, path1: str,
    provider2: FileSystemProvider, path2: str,
) -> Tuple[List[FileInfo], List[FileInfo], List[FileInfo], List[FileInfo]]:
    """
    Porównuje dwa katalogi.
    
    Zwraca:
    - only_in_left — tylko w pierwszym
    - only_in_right — tylko w drugim
    - common — w obu
    - identical — identyczne pliki
    """
    items1 = {i.name: i for i in provider1.list_dir(path1)}
    items2 = {i.name: i for i in provider2.list_dir(path2)}

    names1 = set(items1.keys())
    names2 = set(items2.keys())

    only_in_left = [items1[n] for n in names1 - names2]
    only_in_right = [items2[n] for n in names2 - names1]
    common = [items1[n] for n in names1 & names2]
    identical = [items1[n] for n in names1 & names2 if items1[n].size == items2[n].size and
                 items1[n].modified == items2[n].modified]

    return only_in_left, only_in_right, common, identical


def merge_directories(
    src_provider: FileSystemProvider, src_path: str,
    dst_provider: FileSystemProvider, dst_path: str,
) -> None:
    """Skopiuj brakujące pliki z src do dst (symulacja scalania)."""
    src_items = {i.name: i for i in src_provider.list_dir(src_path)}
    dst_items = {i.name: i for i in dst_provider.list_dir(dst_path)}

    names_src = set(src_items.keys())
    names_dst = set(dst_items.keys())

    missing = names_src - names_dst

    for name in missing:
        item = src_items[name]
        if not item.isdir:
            pass  # tutaj skopiuj plik z src do dst