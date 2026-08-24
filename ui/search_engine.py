"""Wyszukiwarka globalna — filtry, regex, zawartość."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, Signal

from core.fs_base import FileInfo, FileSystemProvider


class SearchEngine(QObject):
    """Silnik wyszukiwarki globalnej z wsparciem dla regex i zawartości."""
    results_ready = Signal(list)
    progress = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._provider: Optional[FileSystemProvider] = None
        self._current_path: str = "/"

    def set_provider(self, provider: FileSystemProvider, path: str = "/") -> None:
        self._provider = provider
        self._current_path = path

    def search(self, query: str, regex: bool = False, content: bool = False) -> List[FileInfo]:
        """Szukaj w katalogu i podkatalogach."""
        items = self._provider.list_dir(self._current_path)
        results: List[FileInfo] = []

        for item in items:
            if regex:
                if re.search(query, item.name):
                    results.append(item)
            else:
                if query.lower() in item.name.lower():
                    results.append(item)

            if content and item.isfile:
                try:
                    with self._provider.open_read(item.path) as f:
                        text = f.read()
                        if query.lower() in text.lower():
                            if item not in results:
                                results.append(item)
                except Exception:
                    pass

        return results


def search_in_content(
    provider: FileSystemProvider,
    path: str,
    query: str,
    pattern: Optional[str] = None,
) -> List[tuple[str, int, str]]:
    """Szukaj w zawartości plików. Zwraca (path, line_no, line_text)."""
    results: List[tuple[str, int, str]] = []
    items = provider.list_dir(path)

    for item in items:
        if item.isfile and item.name.endswith((".txt", ".py", ".md", ".json", ".xml")):
            try:
                with provider.open_read(item.path) as f:
                    for line_no, line in enumerate(f, start=1):
                        if query.lower() in line.lower():
                            results.append((item.path, line_no, line.strip()))
            except Exception:
                pass

    return results