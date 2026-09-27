"""Model i widok listy plików — Material Design style.

Duże ikony (40px), czytelne wiersze (56px), podtytuł z rozmiarem/datą.
"""

from __future__ import annotations

import collections
import json
from typing import List, Optional

from PySide6.QtCore import (QAbstractTableModel, QModelIndex, QSize, Qt,
                             QTimer, QThreadPool, QRunnable, Signal, QObject)
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QStyle, QStyledItemDelegate,
                                QTableView, QHeaderView)

from core.fs_base import FileInfo, FileSystemProvider
from core.local_fs import LocalFileSystem
from core.storage_analysis import human_size

COLS = ["Nazwa", "Rozmiar", "Zmodyfikowano", "Typ"]

# Typ MIME przenoszonych pozycji (kopiowanie/przenoszenie myszką)
FILE_MIME = "application/x-file-manager-paths"

# Kolory podświetlenia schowka
CLIPBOARD_COPY_COLOR = QColor("#d3e3fd")   # niebieski
CLIPBOARD_CUT_COLOR = QColor("#fce8b2")    # żółty

# ---- Kolory ikon wg typu (Material Design) ----
ICON_COLORS = {
    "folder":  "#f9ab00",
    "image":   "#1a73e8",
    "video":   "#e8453c",
    "audio":   "#f06292",
    "text":    "#5f6368",
    "pdf":     "#e8453c",
    "zip":     "#5f6368",
    "code":    "#1a73e8",
    "default": "#5f6368",
}

# ---- Ikony systemowe wg MIME ----
MIME_ICONS = {
    "image": "image-x-generic",
    "video": "video-x-generic",
    "audio": "audio-x-generic",
    "text":  "text-x-generic",
    "pdf":   "application-pdf",
    "zip":   "package-x-generic",
}

# ---- Cache ikon MIME (LRU) ----
_mime_icon_cache: collections.OrderedDict[str, QIcon] = collections.OrderedDict()
_MIME_CACHE_MAX = 500


def _icon_for(info: FileInfo) -> QIcon:
    """Zwróć ikonę typu pliku (z cache'em LRU)."""
    style_icons = QIcon.fromTheme
    if info.is_dir:
        cache_key = "__folder__"
        if cache_key in _mime_icon_cache:
            _mime_icon_cache.move_to_end(cache_key)
            return _mime_icon_cache[cache_key]
        icon = style_icons("folder")
        if icon.isNull():
            icon = style_icons("folder-open")
        _mime_icon_cache[cache_key] = icon
        if len(_mime_icon_cache) > _MIME_CACHE_MAX:
            _mime_icon_cache.popitem(last=False)
        return icon

    mime = info.mime or ""
    cache_key = mime
    if cache_key in _mime_icon_cache:
        _mime_icon_cache.move_to_end(cache_key)
        return _mime_icon_cache[cache_key]

    for key, theme_name in MIME_ICONS.items():
        if mime.startswith(key) or key in mime:
            icon = style_icons(theme_name)
            if not icon.isNull():
                _mime_icon_cache[cache_key] = icon
                if len(_mime_icon_cache) > _MIME_CACHE_MAX:
                    _mime_icon_cache.popitem(last=False)
                return icon

    icon = style_icons("text-x-generic")
    if icon.isNull():
        icon = style_icons("application-octet-stream")
    _mime_icon_cache[cache_key] = icon
    if len(_mime_icon_cache) > _MIME_CACHE_MAX:
        _mime_icon_cache.popitem(last=False)
    return icon


def _make_colored_folder_icon(color_hex: str, size: int = 40) -> QIcon:
    """Stwórz ikonę folderu z kolorowym tłem (styl Material)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    # Zaokrąglone tło
    bg = QColor(color_hex)
    painter.setBrush(bg)
    painter.setPen(Qt.PenStyle.NoPen)
    radius = size * 0.22
    painter.drawRoundedRect(2, 2, size - 4, size - 4, radius, radius)
    # Folder emoji
    painter.setPen(QColor("#ffffff"))
    font = QFont("Segoe UI Emoji", int(size * 0.38))
    painter.setFont(font)
    painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "📁")
    painter.end()
    return QIcon(pm)


class FileListModel(QAbstractTableModel):
    _THUMB_CACHE_MAX = 300

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[FileInfo] = []
        self._provider: Optional[FileSystemProvider] = None
        self.show_hidden = False
        self._thumbs: collections.OrderedDict[str, QIcon] = collections.OrderedDict()
        self._clipboard_paths: set[str] = set()
        self._clipboard_cut = False
        self._flash_paths: set[str] = set()
        self._flash_cut = False

    def set_clipboard_highlight(self, paths: set[str], cut: bool) -> None:
        self._clipboard_paths = paths
        self._clipboard_cut = cut
        if self._items:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._items) - 1, len(COLS) - 1),
                [Qt.ItemDataRole.BackgroundRole])

    def set_transfer_highlight(self, paths: set[str], cut: bool) -> None:
        self._flash_paths = set(paths)
        self._flash_cut = cut
        if self._items:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._items) - 1, len(COLS) - 1),
                [Qt.ItemDataRole.BackgroundRole])

    def clear_transfer_highlight(self) -> None:
        if not self._flash_paths:
            return
        self._flash_paths = set()
        if self._items:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._items) - 1, len(COLS) - 1),
                [Qt.ItemDataRole.BackgroundRole])

    def set_content(self, provider: FileSystemProvider, items: List[FileInfo]) -> None:
        self.beginResetModel()
        self._provider = provider
        self._items = items
        self._thumbs.clear()
        self._flash_paths = set()
        self.endResetModel()

    def item_at(self, row: int) -> Optional[FileInfo]:
        return self._items[row] if 0 <= row < len(self._items) else None

    # ----- drag & drop -----
    def mimeTypes(self) -> List[str]:
        return [FILE_MIME]

    def mimeData(self, indexes) -> 'QMimeData':
        from PySide6.QtCore import QMimeData
        mime = QMimeData()
        paths: List[str] = []
        seen = set()
        for idx in indexes:
            if idx.column() != 0 or not idx.isValid():
                continue
            path = self._items[idx.row()].path
            if path not in seen:
                seen.add(path)
                paths.append(path)
        mime.setData(FILE_MIME, json.dumps(paths).encode("utf-8"))
        return mime

    def canDropMimeData(self, data, action, row, column, parent) -> bool:
        return data.hasFormat(FILE_MIME)

    # ----- QAbstractTableModel -----
    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._items)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return COLS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        info = self._items[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return info.name
            if col == 1:
                return "📁" if info.is_dir else human_size(info.size)
            if col == 2:
                return info.modified.strftime("%d.%m.%Y %H:%M") if info.modified else ""
            if col == 3:
                return "Folder" if info.is_dir else (info.mime.split("/")[-1].upper() if info.mime else "")

        if role == Qt.ItemDataRole.DecorationRole and col == 0:
            # Duże miniaturki (48px) dla obrazów lokalnych
            if (isinstance(self._provider, LocalFileSystem)
                    and info.mime.startswith("image/") and info.size < 50_000_000):
                if info.path not in self._thumbs:
                    pm = QPixmap(info.path)
                    if not pm.isNull():
                        scaled = pm.scaled(48, 48,
                                           Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation)
                        self._thumbs[info.path] = QIcon(scaled)
                    else:
                        self._thumbs[info.path] = QIcon()
                self._thumbs.move_to_end(info.path)
                if len(self._thumbs) > self._THUMB_CACHE_MAX:
                    self._thumbs.popitem(last=False)
                if not self._thumbs[info.path].isNull():
                    return self._thumbs[info.path]
            return _icon_for(info)

        if role == Qt.ItemDataRole.ToolTipRole:
            if info.is_dir:
                return f"📁 {info.name}"
            size = human_size(info.size) if info.size else ""
            mime = info.mime or ""
            date = info.modified.strftime("%d.%m.%Y %H:%M") if info.modified else ""
            parts = [info.name]
            if size:
                parts.append(size)
            if mime:
                parts.append(mime)
            if date:
                parts.append(date)
            return "  |  ".join(parts)

        if role == Qt.ItemDataRole.FontRole and col == 0:
            f = QFont()
            if info.is_dir:
                f.setBold(True)
                f.setPointSize(12)
            else:
                f.setPointSize(11)
            return f

        if role == Qt.ItemDataRole.ForegroundRole:
            if info.is_dir:
                return QColor(ICON_COLORS["folder"])
            return None

        if role == Qt.ItemDataRole.BackgroundRole:
            if info.path in self._clipboard_paths:
                color = (CLIPBOARD_CUT_COLOR if self._clipboard_cut
                         else CLIPBOARD_COPY_COLOR)
                return QBrush(color)
            if info.path in self._flash_paths:
                color = (CLIPBOARD_CUT_COLOR if self._flash_cut
                         else CLIPBOARD_COPY_COLOR)
                return QBrush(color)

        if role == Qt.ItemDataRole.TextAlignmentRole and col == 1:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

        if role == Qt.ItemDataRole.UserRole:
            return info
        return None

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        reverse = order == Qt.SortOrder.DescendingOrder
        self.layoutAboutToBeChanged.emit()

        def key(i: FileInfo):
            if column == 1:
                return (not i.is_dir, i.size)
            if column == 2:
                return (not i.is_dir, i.modified.isoformat() if i.modified else "")
            if column == 3:
                return (not i.is_dir, i.mime)
            return (not i.is_dir, i.name.lower())

        self._items.sort(key=key, reverse=reverse)
        self.layoutChanged.emit()


class FileListView(QTableView):
    _ZOOM_MIN = 20
    _ZOOM_MAX = 80
    _ZOOM_STEP = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModel(FileListModel(self))
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self._icon_size = 36
        self._row_height = 56
        self.verticalHeader().setDefaultSectionSize(self._row_height)
        self.setIconSize(QSize(self._icon_size, self._icon_size))
        self.setSortingEnabled(True)
        self.setAlternatingRowColors(False)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QTableView.DragDropMode.DragDrop)
        self.doubleClicked.connect(self._on_double)
        self.setFrameShape(QTableView.Shape.NoFrame)

        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        for col in (1, 2, 3):
            header.setSectionResizeMode(col, header.ResizeMode.ResizeToContents)
        header.setMinimumSectionSize(80)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._double_handler = None
        self._drop_handler = None

    def on_double_click(self, handler) -> None:
        self._double_handler = handler

    def set_drop_handler(self, handler) -> None:
        self._drop_handler = handler

    def _on_double(self, index: QModelIndex) -> None:
        if self._double_handler:
            info = index.data(Qt.ItemDataRole.UserRole)
            if info:
                self._double_handler(info)

    @staticmethod
    def _paths_from(event) -> List[str]:
        mime = event.mimeData()
        if not mime.hasFormat(FILE_MIME):
            return []
        try:
            return json.loads(bytes(mime.data(FILE_MIME)).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return []

    def _drop_target_dir(self, pos) -> Optional[str]:
        idx = self.indexAt(pos)
        if idx.isValid():
            info = idx.data(Qt.ItemDataRole.UserRole)
            if info and info.is_dir:
                return info.path
        return None

    def dragEnterEvent(self, event) -> None:
        if self._paths_from(event):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if self._paths_from(event):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        paths = self._paths_from(event)
        if not paths or self._drop_handler is None:
            super().dropEvent(event)
            return
        self._drop_handler(paths, self._drop_target_dir(event.position().toPoint()))
        event.acceptProposedAction()

    # ----- Ctrl+Scroll zoom -----
    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self._icon_size = min(self._ZOOM_MAX, self._icon_size + self._ZOOM_STEP)
                self._row_height = min(96, self._row_height + 8)
            elif delta < 0:
                self._icon_size = max(self._ZOOM_MIN, self._icon_size - self._ZOOM_STEP)
                self._row_height = max(36, self._row_height - 8)
            self.setIconSize(QSize(self._icon_size, self._icon_size))
            self.verticalHeader().setDefaultSectionSize(self._row_height)
            self.viewport().update()
            event.accept()
        else:
            super().wheelEvent(event)

    def selected_infos(self) -> List[FileInfo]:
        rows = {i.row() for i in self.selectionModel().selectedRows()}
        model: FileListModel = self.model()
        return [model.item_at(r) for r in sorted(rows) if model.item_at(r)]

    def refresh_column_sizes(self) -> None:
        pass
