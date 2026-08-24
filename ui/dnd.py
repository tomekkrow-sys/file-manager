"""Drag & Drop — zewnętrzne pliki, przesuwanie między panelami."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QDropEvent


class DnDHandler:
    """Obsługa Drag & Drop dla panelu."""

    def __init__(self, widget):
        self.widget = widget
        self.widget.setAcceptDrops(True)
        self._drop_pos = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            self._drop_pos = event.pos()
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            files = [u.toLocalFile() for u in urls if u.isLocalFile()]
            folders = [u.toLocalFile() for u in urls if u.isLocalFile() and u.isDir()]
            event.acceptProposedAction()
            if files or folders:
                self.widget.handle_dropped_files(files + folders)

    def set_drop_target(self, pos):
        self._drop_pos = pos


class DropTarget:
    """Cel dropnięcia — może być panel lub folder."""

    def __init__(self, path: str, is_panel: bool = False):
        self.path = path
        self.is_panel = is_panel
        self.items: List[str] = []

    def add_items(self, items: List[str]):
        self.items.extend(items)


class DropMIMEData(QMimeData):
    """Dane MIME z obsługą wielu źródeł."""

    def __init__(self, items: List[str], source: Optional[str] = None):
        super().__init__()
        self.items = items
        self.source = source or ""
        self.setUrls([item if item.startswith("file://") else f"file://{item}" for item in items])

    def formats(self) -> List[str]:
        return ["text/uri-list", "application/x-qabstractitemmodeldatalist", "text/plain"]

    def hasUrls(self) -> bool:
        return True

    def urls(self) -> List[str]:
        return self.items