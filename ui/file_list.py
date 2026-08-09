"""Model i widok listy plików (ikony wg typu MIME, miniaturki obrazów lokalnych)."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QTableView

from core.fs_base import FileInfo, FileSystemProvider
from core.local_fs import LocalFileSystem
from core.storage_analysis import human_size

COLS = ["Nazwa", "Rozmiar", "Zmodyfikowano", "Typ"]

# Ikony tematu systemowego wg kategorii MIME
MIME_ICONS = {
    "image": "image-x-generic",
    "video": "video-x-generic",
    "audio": "audio-x-generic",
    "text": "text-x-generic",
    "pdf": "application-pdf",
    "zip": "package-x-generic",
}


def _icon_for(info: FileInfo) -> QIcon:
    style_icons = QIcon.fromTheme
    if info.is_dir:
        icon = style_icons("folder")
        return icon if not icon.isNull() else style_icons("folder-open")
    mime = info.mime or ""
    for key, theme_name in MIME_ICONS.items():
        if mime.startswith(key) or key in mime:
            icon = style_icons(theme_name)
            if not icon.isNull():
                return icon
    icon = style_icons("text-x-generic")
    return icon if not icon.isNull() else style_icons("application-octet-stream")


class FileListModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[FileInfo] = []
        self._provider: Optional[FileSystemProvider] = None
        self.show_hidden = False
        self._thumbs: dict[str, QIcon] = {}

    def set_content(self, provider: FileSystemProvider, items: List[FileInfo]) -> None:
        self.beginResetModel()
        self._provider = provider
        self._items = items
        self._thumbs.clear()
        self.endResetModel()

    def item_at(self, row: int) -> Optional[FileInfo]:
        return self._items[row] if 0 <= row < len(self._items) else None

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
                return "—" if info.is_dir else human_size(info.size)
            if col == 2:
                return info.modified.strftime("%Y-%m-%d %H:%M") if info.modified else ""
            if col == 3:
                return "Katalog" if info.is_dir else info.mime.split("/")[-1]

        if role == Qt.ItemDataRole.DecorationRole and col == 0:
            # Miniaturka dla lokalnych obrazów
            if (isinstance(self._provider, LocalFileSystem)
                    and info.mime.startswith("image/") and info.size < 50_000_000):
                if info.path not in self._thumbs:
                    pm = QPixmap(info.path)
                    self._thumbs[info.path] = QIcon(
                        pm.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
                        if not pm.isNull() else QPixmap(0, 0))
                if not self._thumbs[info.path].isNull():
                    return self._thumbs[info.path]
            return _icon_for(info)

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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModel(FileListModel(self))
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(28)
        self.setIconSize(QSize(22, 22))
        self.setSortingEnabled(True)
        self.setAlternatingRowColors(True)
        self.doubleClicked.connect(self._on_double)

        header = self.horizontalHeader()
        # Kolumna "Nazwa" zajmuje całą wolną przestrzeń — długie nazwy
        # nie są ucinane; pozostałe kolumny dopasowują się do treści.
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        for col in (1, 2, 3):
            header.setSectionResizeMode(col, header.ResizeMode.ResizeToContents)
        header.setMinimumSectionSize(70)

        self._double_handler = None

    def on_double_click(self, handler) -> None:
        self._double_handler = handler

    def _on_double(self, index: QModelIndex) -> None:
        if self._double_handler:
            info = index.data(Qt.ItemDataRole.UserRole)
            if info:
                self._double_handler(info)

    def selected_infos(self) -> List[FileInfo]:
        rows = {i.row() for i in self.selectionModel().selectedRows()}
        model: FileListModel = self.model()
        return [model.item_at(r) for r in sorted(rows) if model.item_at(r)]

    def refresh_column_sizes(self) -> None:
        # Kolumny 1-3 mają ResizeToContents — nic do robienia.
        # Metoda zostaje jako stabilny punkt API dla main_window.
        pass
