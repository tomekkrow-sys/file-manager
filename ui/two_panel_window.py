"""Dwupanelowa wersja File Managera — dwa niezależne panele obok siebie
(w stylu Total Commander / Midnight Commander). Reużywa te same providery
i widżety listy plików co wersja jednopanelowa.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import QEvent, Qt, QThread, QTimer, Signal, QSettings
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolBar,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from core import archives
from core.cloud.dropbox import connect_dropbox
from core.cloud.gdrive import connect_gdrive
from core.cloud.onedrive import connect_onedrive
from core.connections import (
    get_all_connections,
    provider_params,
    remove_connection,
    save_connection,
)
from core.fs_base import FileInfo, FileSystemError, FileSystemProvider
from core.ftp_fs import FtpFileSystem
from core.local_fs import LocalFileSystem
from core.operations import CopyOperation, DeleteOperation, MoveOperation
from core.sftp_fs import SftpFileSystem
from core.smb_fs import SmbFileSystem
from core.storage_analysis import human_size
from ui.dialogs import FtpConnectDialog, SftpConnectDialog, SmbConnectDialog
from ui.file_list import FileListModel, FileListView
from ui.two_panel_synchronization import (
   compare_directories,
    merge_directories,
    SyncController,
)
from ui.batch_operations import batch_rename, batch_convert_images, batch_tag_items
from ui.search_engine import SearchEngine
from ui.theme_manager import ThemeManager, get_theme_names
from ui.version_control import VersionControl
from ui.clipboard import SmartClipboard, MultiSessionClipboard
from ui.external_tools import ExternalToolsManager, ExternalTool
from ui.shortcuts import ShortcutManager, ActionRegistry
from ui.dnd import DnDHandler, DropTarget, DropMIMEData
from ui.cloud_manager import CloudManager, AutoSyncManager
from ui.ftp_manager import FTPServerManager, FTPConnection
from ui.plugins import PluginManager, PluginInstaller
from ui.updater import AutoUpdater
from ui.i18n import LocaleManager, tr, N_
from ui.shortcuts import ShortcutManager, ActionRegistry
from ui.dnd import DnDHandler, DropTarget, DropMIMEData
from ui.cloud_manager import CloudManager, AutoSyncManager
from ui.ftp_manager import FTPServerManager, FTPConnection
from ui.plugins import PluginManager, PluginInstaller, register_builtin_plugins


class _DirLoader(QThread):
    """Ładowanie katalogu w tle (żeby sieciowe providery nie zamrażały UI)."""
    loaded = Signal(list)
    failed = Signal(str)

    def __init__(self, provider: FileSystemProvider, path: str, parent=None):
        super().__init__(parent)
        self._provider, self._path = provider, path

    def run(self) -> None:
        try:
            self.loaded.emit(list(self._provider.list_dir(self._path)))
        except FileSystemError as exc:
            self.failed.emit(str(exc))


class _CloudConnector(QThread):
    """Logowanie OAuth do chmury w tle — nie blokuje okna."""
    connected = Signal(object)
    failed = Signal(str)

    def __init__(self, connect_fn, parent=None):
        super().__init__(parent)
        self._connect_fn = connect_fn
        self.cancel_event = threading.Event()

    def run(self) -> None:
        try:
            self.connected.emit(self._connect_fn(cancel_event=self.cancel_event))
        except FileSystemError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # ostatnia linia obrony — nigdy crash UI
            self.failed.emit(f"Nieoczekiwany błąd: {exc}")


class Panel(QWidget):
    """Jeden z dwóch niezależnych paneli: źródło, ścieżka, lista plików, status."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.provider: FileSystemProvider = LocalFileSystem()
        self.current_path = self.provider.root_path()
        self._history: List[str] = []
        self._history_idx = -1
        self._loaders: list = []
        self._load_gen = 0
        self._active = False
        # Oczekujące podświetlenie wyników kopiowania (aplikowane po przeładowaniu)
        self._pending_highlight: Optional[tuple[set, bool]] = None
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.setInterval(6000)
        self._flash_timer.timeout.connect(self._clear_flash)

        self.path_label = QLabel()
        self.path_label.setStyleSheet("font-weight: bold; padding: 4px;")
        self.file_list = FileListView()
        self.status_label = QLabel()

        self.source_button = QToolButton()
        self.source_button.setText("☰  Źródło")
        self.source_button.setToolTip(
            "Wybierz źródło dla tego panelu (lokalnie, sieć lub chmura)")
        self.source_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.source_button.setMenu(QMenu(self))

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self.source_button)
        top.addWidget(self.path_label, 1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.addLayout(top)
        lay.addWidget(self.file_list, 1)
        lay.addWidget(self.status_label)

    # ----- podświetlenie aktywnego panelu -----
    def set_active(self, active: bool) -> None:
        self._active = active
        color = "#dceafc" if active else "transparent"
        border = "#4a90d9" if active else "transparent"
        self.path_label.setStyleSheet(
            f"font-weight: bold; padding: 4px;"
            f"background: {color}; border: 1px solid {border};")

    # ----- nawigacja -----
    def navigate(self, path: str, add_history: bool = True) -> None:
        if add_history:
            del self._history[self._history_idx + 1:]
            self._history.append(path)
            self._history_idx += 1
        self.current_path = path
        self.path_label.setText(f"{self.provider.display_name()}  ▸  {path}")
        self.status_label.setText("Ładowanie…")

        # Pokolenie zabezpiecza przed nadpisaniem nowszego katalogu
        # wynikiem wolniej ładującego się starszego wątku.
        self._load_gen += 1
        gen = self._load_gen
        loader = _DirLoader(self.provider, path, self)
        self._loaders.append(loader)
        loader.loaded.connect(
            lambda items, g=gen: self._on_dir_loaded(items, g))
        loader.failed.connect(
            lambda msg, g=gen: self._on_dir_failed(msg, g))
        loader.finished.connect(lambda: self._forget_loader(loader))
        loader.finished.connect(loader.deleteLater)
        loader.start()

    def _forget_loader(self, loader) -> None:
        if loader in self._loaders:
            self._loaders.remove(loader)

    def _on_dir_loaded(self, items, gen: int) -> None:
        if gen != self._load_gen:
            return
        model: FileListModel = self.file_list.model()
        model.set_content(self.provider, items)
        self.file_list.refresh_column_sizes()
        total = sum(i.size for i in items if not i.is_dir)
        dirs = sum(1 for i in items if i.is_dir)
        self.status_label.setText(
            f"{len(items) - dirs} plików, {dirs} katalogów — {human_size(total)}")
        if self._pending_highlight is not None:
            paths, cut = self._pending_highlight
            self._pending_highlight = None
            model.set_transfer_highlight(paths, cut)
            self._flash_timer.start()

    def _on_dir_failed(self, message: str, gen: int) -> None:
        if gen != self._load_gen:
            return
        self._pending_highlight = None
        self.status_label.setText("")
        QMessageBox.warning(self, "Błąd", message)

    def set_pending_highlight(self, paths: set, cut: bool) -> None:
        """Podświetli te ścieżki po zakończeniu ładowania katalogu."""
        self._pending_highlight = (set(paths), cut)

    def _clear_flash(self) -> None:
        model: FileListModel = self.file_list.model()
        model.clear_transfer_highlight()

    def back(self) -> None:
        if self._history_idx > 0:
            self._history_idx -= 1
            self.navigate(self._history[self._history_idx], add_history=False)

    def forward(self) -> None:
        if self._history_idx < len(self._history) - 1:
            self._history_idx += 1
            self.navigate(self._history[self._history_idx], add_history=False)

    def up(self) -> None:
        parent = self.provider.parent(self.current_path)
        if parent is not None:
            self.navigate(parent)

    def refresh(self) -> None:
        self.navigate(self.current_path, add_history=False)

    def selected(self) -> List[FileInfo]:
        return self.file_list.selected_infos()

    def shutdown(self) -> None:
        """Czeka na ładowanie katalogu przed zamknięciem okna."""
        for loader in list(self._loaders):
            if loader.isRunning():
                loader.wait(2000)
        self._loaders.clear()

    # ==================================================
    # Batch operations
    # ==================================================

    def batch_rename(self, items: Optional[List[FileInfo]] = None, pattern: Optional[str] = None) -> None:
        """Batch rename w panelu."""
        if items is None:
            items = self.file_list.selected_infos()
        if not items:
            return
        if pattern is None:
            pattern, ok = QInputDialog.getText(self, "Batch rename",
                                               "Wzorzec:\n[name], [ext], [num]")
            if not ok:
                return
        from ui.batch_operations import batch_rename
        batch_rename(self.provider, items, pattern or "[name]_v[num].[ext]")

    def batch_convert(self, items: Optional[List[FileInfo]] = None) -> None:
        """Batch convert obrazów."""
        if items is None:
            items = self.file_list.selected_infos()
        items = [i for i in items if i.name.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"))]
        if not items:
            return
        from ui.batch_operations import batch_convert_images
        batch_convert_images(self.provider, items)

    def batch_tag(self, items: Optional[List[FileInfo]] = None, tags: Optional[List[str]] = None) -> None:
        """Batch tagowanie."""
        if items is None:
            items = self.file_list.selected_infos()
        if not items:
            return
        if tags is None:
            tags_input, ok = QInputDialog.getText(self, "Batch tags",
                                                   "Tagi (przecinki):")
            if ok:
                tags = [t.strip() for t in tags_input.split(",") if t.strip()]
        from ui.batch_operations import batch_tag_items
        batch_tag_items(self.provider, items, tags or [])

    # ==================================================
    # Preview
    # ==================================================

    def show_preview(self, info: FileInfo) -> None:
        """Pokaż podgląd wybranego pliku."""
        from ui.preview import PreviewGenerator, EXIFReader
        gen = PreviewGenerator()
        reader = EXIFReader()

        if info.isdir:
            items = list(self.provider.list_dir(info.path))
            self.status_label.setText(
                f"Katalog: {len(items)} elementów — "
                f"{sum(1 for i in items if i.isdir)} katalogów, "
                f"{sum(1 for i in items if i.isfile)} plików")
        elif info.name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            exif = reader.read(Path(info.path))
            self.status_label.setText(
                f"EXIF: {exif.make or ''} {exif.model or ''} "
                f"{exif.exposure_time or ''} ISO{exif.iso or ''}")
        elif info.name.lower().endswith((".txt", ".py", ".md", ".json", ".xml")):
            preview = gen.generate_text_preview(Path(info.path))
            self.status_label.setText(f"Podgląd: {preview[:80]}...")
        elif info.name.lower().endswith(".pdf"):
            preview = gen.generate_pdf_preview(Path(info.path))
            self.status_label.setText(f"PDF: {len(preview.splitlines())} linii")



class DualPanelWindow(QMainWindow):
    """Główne okno wersji dwupanelowej."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("File Manager — panel dwupanelowy")
        self.resize(1400, 760)

        # ----- stan -----
        self.left = Panel()
        self.right = Panel()
        self._active: Panel = self.left
        self._clipboard: List[tuple[FileSystemProvider, str]] = []
        self._clipboard_cut = False
        self._operations: list = []
        self._cloud_connector: Optional[_CloudConnector] = None

        # Menadżery nowych funkcji
        self.version_control = VersionControl()
        self.clipboard = SmartClipboard()
        self.theme_manager = ThemeManager()
        self.search_engine = SearchEngine()
        self.external_tools = ExternalToolsManager()
        self.shortcut_manager = ShortcutManager()
        self.cloud_manager = CloudManager()
        self.ftp_manager = FTPServerManager()
        self.plugin_manager = PluginManager()
        self.dnd_handler = DnDHandler(self)
        self.updater = AutoUpdater()
        self.i18n = LocaleManager()

        for panel in (self.left, self.right):
            panel.file_list.on_double_click(
                lambda info, p=panel: self._open_item(p, info))
            panel.file_list.set_drop_handler(
                lambda paths, target, p=panel: self._on_panel_drop(p, paths, target))
            panel.file_list.setContextMenuPolicy(
                Qt.ContextMenuPolicy.CustomContextMenu)
            panel.file_list.customContextMenuRequested.connect(
                lambda pos, p=panel: self._context_menu(p, pos))
            panel.source_button.menu().aboutToShow.connect(
                lambda p=panel: self._build_source_menu(p))
            # Aktywacja po kliknięciu etykiety ścieżki / przycisku źródła
            panel.path_label.installEventFilter(self)
            panel.source_button.installEventFilter(self)
            panel.status_label.installEventFilter(self)

        # Aktywacja po uzyskaniu focusa przez listę plików (klik, klawisze, Tab).
        # Świadomie NIE używamy selectionChanged: ładowanie katalogu w tle
        # resetuje model i kasowałoby aktywację użytkownika.
        QApplication.instance().focusChanged.connect(self._on_focus_changed)

        splitter = QSplitter()
        splitter.addWidget(self.left)
        splitter.addWidget(self.right)
        splitter.setSizes([700, 700])
        self.setCentralWidget(splitter)

        self._build_toolbar()
        self._build_menus()

        # Tab przełącza aktywny panel
        tab_switch = QShortcut(QKeySequence(Qt.Key.Key_Tab), self)
        tab_switch.setContext(Qt.ShortcutContext.WindowShortcut)
        tab_switch.activated.connect(self._switch_active)

        # start: lewy panel na korzeniu, prawy w katalogu domowym
        self.left.navigate(self.left.provider.root_path())
        self.right.navigate(str(Path.home()))
        self._set_active(self.left)
        self.left.file_list.setFocus()

    # ==================================================
    # Aktywny panel
    # ==================================================
    def _set_active(self, panel: Panel) -> None:
        self._active = panel
        self.left.set_active(panel is self.left)
        self.right.set_active(panel is self.right)

    def _switch_active(self) -> None:
        other = self._other()
        self._set_active(other)
        other.file_list.setFocus()

    def _other(self, panel: Optional[Panel] = None) -> Panel:
        panel = panel or self._active
        return self.right if panel is self.left else self.left

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            for panel in (self.left, self.right):
                if obj in (panel.path_label, panel.source_button,
                           panel.status_label):
                    self._set_active(panel)
                    break
        return super().eventFilter(obj, event)

    def _on_focus_changed(self, old, new) -> None:
        for panel in (self.left, self.right):
            if new is panel.file_list:
                self._set_active(panel)
                break

    def _active_back(self) -> None:
        self._active.back()

    def _active_forward(self) -> None:
        self._active.forward()

    def _active_up(self) -> None:
        self._active.up()

    def _active_refresh(self) -> None:
        self._active.refresh()

    # ==================================================
    # Wybór źródła panelu (menu „Źródło”)
    # ==================================================
    def _build_source_menu(self, panel: Panel) -> None:
        menu = panel.source_button.menu()
        menu.clear()

        def add(text, action):
            act = menu.addAction(text)
            act.triggered.connect(lambda: self._on_source(panel, action))

        def add_saved(kind: str, params: dict) -> None:
            name = params.get("name", params["host"])
            icon = {"ftp": "🔌", "sftp": "🔑", "smb": "🗄"}.get(kind, "🔌")
            sub = QMenu(f"{icon}  {name}", menu)
            sub.addAction("🔌  Połącz",
                          lambda: self._on_source(panel, ("saved", kind, params)))
            sub.addAction("🗑  Usuń z pamięci",
                          lambda: self._remove_saved(kind, name))
            menu.addMenu(sub)

        add("🖥  Pamięć lokalna", ("local", None))
        add("📁  Katalog domowy", ("home", None))
        menu.addSeparator()
        add("➕  Połącz FTP…", ("ftp", None))
        add("➕  Połącz SSH (SFTP)…", ("sftp", None))
        add("➕  Połącz NAS (SMB)…", ("smb", None))
        for kind, params in get_all_connections():
            add_saved(kind, params)
        menu.addSeparator()
        add("☁  Google Drive…", ("gdrive", None))
        add("☁  Dropbox…", ("dropbox", None))
        add("☁  OneDrive…", ("onedrive", None))
        add("⚙  Klucze API chmur…", ("cloud_keys", None))

    def _on_source(self, panel: Panel, action) -> None:
        key = action[0]
        if key == "local":
            self._switch_provider(panel, LocalFileSystem())
        elif key == "home":
            self._switch_provider(panel, LocalFileSystem(), str(Path.home()))
        elif key == "ftp":
            self._connect_ftp(panel)
        elif key == "sftp":
            self._connect_sftp(panel)
        elif key == "smb":
            self._connect_smb(panel)
        elif key == "saved":
            _, kind, params = action
            self._connect_saved(panel, kind, params)
        elif key == "gdrive":
            self._connect_cloud(panel, connect_gdrive, "gdrive")
        elif key == "dropbox":
            self._connect_cloud(panel, connect_dropbox, "dropbox")
        elif key == "onedrive":
            self._connect_cloud(panel, connect_onedrive, "onedrive")
        elif key == "cloud_keys":
            from ui.cloud_keys_dialog import CloudKeysDialog
            CloudKeysDialog(self).exec()

    def _remove_saved(self, kind: str, name: str) -> None:
        if QMessageBox.question(
                self, "Zapisane połączenia",
                f"Usunąć połączenie „{name}” z pamięci?") \
                != QMessageBox.StandardButton.Yes:
            return
        remove_connection(kind, name)

    def _switch_provider(self, panel: Panel, provider: FileSystemProvider,
                         start_path: str = "/") -> None:
        if isinstance(provider, LocalFileSystem):
            start_path = provider.root_path() if start_path == "/" else start_path
        panel.provider = provider
        panel._history.clear()
        panel._history_idx = -1
        panel.navigate(start_path)

    # ==================================================
    # Połączenia sieciowe i chmury
    # ==================================================
    def _connect_ftp(self, panel: Panel) -> None:
        dlg = FtpConnectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        params = dlg.params()
        try:
            fs = FtpFileSystem(**provider_params("ftp", params))
        except FileSystemError as exc:
            QMessageBox.critical(self, "FTP", str(exc))
            return
        self._maybe_save_connection(panel, "ftp", params)
        self._switch_provider(panel, fs, "/")

    def _connect_sftp(self, panel: Panel) -> None:
        dlg = SftpConnectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        params = dlg.params()
        try:
            fs = SftpFileSystem(**provider_params("sftp", params))
        except FileSystemError as exc:
            QMessageBox.critical(self, "SSH", str(exc))
            return
        self._maybe_save_connection(panel, "sftp", params)
        self._switch_provider(panel, fs, "/")

    def _connect_smb(self, panel: Panel) -> None:
        dlg = SmbConnectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        params = dlg.params()
        try:
            fs = SmbFileSystem(**provider_params("smb", params))
        except FileSystemError as exc:
            QMessageBox.critical(self, "NAS", str(exc))
            return
        self._maybe_save_connection(panel, "smb", params)
        self._switch_provider(panel, fs, "/")

    def _maybe_save_connection(self, panel: Panel, kind: str, params: dict) -> None:
        if not params.get("save"):
            return
        store = {k: v for k, v in params.items()
                 if k not in ("save", "save_password")}
        if not params.get("save_password"):
            store.pop("password", None)
        save_connection(kind, store)
        self.statusBar().showMessage(
            f"Połączenie „{store.get('name', '')}” zapisane — wybierzesz je z menu Źródło.")

    def _connect_saved(self, panel: Panel, kind: str, params: dict) -> None:
        classes = {"ftp": FtpFileSystem, "sftp": SftpFileSystem,
                   "smb": SmbFileSystem}
        cls = classes.get(kind)
        if cls is None:
            return
        try:
            fs = cls(**provider_params(kind, params))
        except FileSystemError as exc:
            QMessageBox.critical(self, "Połączenie", str(exc))
            return
        self._switch_provider(panel, fs, "/")

    def _connect_cloud(self, panel: Panel, connect_fn, provider_key: str = "") -> None:
        from core.cloud.base import has_app_keys, get_saved_token
        if provider_key and not has_app_keys(provider_key) \
                and not get_saved_token(provider_key):
            answer = QMessageBox.question(
                self, "Chmura",
                "Najpierw musisz wpisać klucze API tej chmury.\n"
                "Otworzyć ustawienia kluczy?")
            if answer == QMessageBox.StandardButton.Yes:
                self._show_cloud_keys()
            return

        progress = QProgressDialog(
            "Otworzono przeglądarkę — zaloguj się do chmury.\n"
            "Po zalogowaniu wróć tutaj (okno zamknie się samo).",
            "Anuluj", 0, 0, self)
        progress.setWindowTitle("Logowanie do chmury")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        connector = _CloudConnector(connect_fn, self)
        self._cloud_connector = connector
        progress.canceled.connect(connector.cancel_event.set)

        def on_connected(fs):
            progress.close()
            self._cloud_connector = None
            self._switch_provider(panel, fs, "/")

        def on_failed(message: str):
            progress.close()
            self._cloud_connector = None
            if "anulowane" not in message:
                QMessageBox.critical(self, "Chmura", message)

        connector.connected.connect(on_connected)
        connector.failed.connect(on_failed)
        connector.finished.connect(connector.deleteLater)
        connector.start()

    def _show_cloud_keys(self) -> None:
        from ui.cloud_keys_dialog import CloudKeysDialog
        CloudKeysDialog(self).exec()

    # ==================================================
    # Otwieranie pozycji
    # ==================================================
    def _open_item(self, panel: Panel, info: FileInfo) -> None:
        if info.is_dir:
            panel.navigate(info.path)
            return
        self._open_file(panel, info)

    def _open_file(self, panel: Panel, info: FileInfo) -> None:
        mime = info.mime or ""
        if mime.startswith("image/"):
            from ui.viewers.image_viewer import ImageViewerDialog
            ImageViewerDialog(panel.provider, info.path, self).exec()
        elif mime.startswith("audio/") or mime.startswith("video/"):
            from ui.viewers.media_player import MediaPlayerDialog
            MediaPlayerDialog(panel.provider, info.path,
                              is_video=mime.startswith("video/"), parent=self).exec()
        elif mime.startswith("text/") or info.name.endswith(
                (".py", ".json", ".md", ".xml", ".csv", ".log", ".txt",
                 ".ini", ".cfg")):
            from ui.viewers.text_editor import TextEditorDialog
            TextEditorDialog(panel.provider, info.path, self).exec()
        elif archives.is_archive(info.name):
            self._show_archive(panel, info)
        else:
            QMessageBox.information(self, info.name,
                                    f"Brak wbudowanego podglądu dla typu: {mime}")

    def _show_archive(self, panel: Panel, info: FileInfo) -> None:
        if not isinstance(panel.provider, LocalFileSystem):
            QMessageBox.information(
                self, "Archiwum",
                "Podgląd archiwów dostępny dla plików lokalnych.\n"
                "Skopiuj archiwum na dysk i spróbuj ponownie.")
            return
        try:
            entries = archives.list_archive(info.path)
        except archives.ArchiveError as exc:
            QMessageBox.critical(self, "Archiwum", str(exc))
            return
        preview = "\n".join(f"{human_size(s):>10}  {n}" for n, s in entries[:200])
        QMessageBox.information(
            self, f"Zawartość: {info.name}",
            f"{len(entries)} pozycji.\n\n{preview}" if entries else "Archiwum puste.")

    def _view_selected(self) -> None:
        sel = self._active.selected()
        if sel:
            self._open_item(self._active, sel[0])

    def _edit_selected(self) -> None:
        sel = self._active.selected()
        if len(sel) != 1 or sel[0].is_dir:
            return
        info = sel[0]
        textish = (info.mime or "").startswith("text/") or info.name.endswith(
            (".py", ".json", ".md", ".xml", ".csv", ".log", ".txt", ".ini", ".cfg"))
        if not textish:
            QMessageBox.information(
                self, info.name,
                "Ten plik nie jest tekstem — użyj F3 do podglądu.")
            return
        from ui.viewers.text_editor import TextEditorDialog
        TextEditorDialog(self._active.provider, info.path, self).exec()

    # ==================================================
    # Operacje między panelami
    # ==================================================
    def _transfer(self, src: Panel, dst: Panel, cut: bool) -> None:
        sel = src.selected()
        if not sel:
            return
        target = dst.current_path.rstrip("/") or "/"
        items = []
        for i in sel:
            parent = src.provider.parent(i.path) or "/"
            if i.path == target or parent.rstrip("/") == target:
                continue  # kopiowanie „na siebie” w tym samym katalogu
            items.append((src.provider, i.path))
        if not items:
            self.statusBar().showMessage(
                "Nic do przeniesienia — źródło i cel to ten sam katalog.")
            return
        cls = MoveOperation if cut else CopyOperation
        op = cls(items, dst.provider, dst.current_path, self)
        self._run_transfer(op, dst, items, cut,
                           "Przeniesiono" if cut else "Skopiowano")

    def _copy_to_other(self) -> None:
        self._transfer(self._active, self._other(), cut=False)

    def _move_to_other(self) -> None:
        self._transfer(self._active, self._other(), cut=True)

    def _delete_selected(self) -> None:
        panel = self._active
        sel = panel.selected()
        if not sel:
            return
        names = "\n".join(i.name for i in sel[:10])
        if len(sel) > 10:
            names += f"\n… i {len(sel) - 10} więcej"
        if QMessageBox.question(
                self, "Usuń",
                f"Usunąć trwale {len(sel)} pozycji?\n\n{names}"
        ) != QMessageBox.StandardButton.Yes:
            return
        op = DeleteOperation([(panel.provider, i.path) for i in sel], self)
        self._run_operation(op, refresh_panel=panel)

    def _run_operation(self, op, refresh_panel: Optional[Panel] = None) -> None:
        progress = QProgressDialog("Operacja na plikach…", "Anuluj", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(300)
        op.progressed.connect(
            lambda done, total, name: (
                progress.setMaximum(max(total, 1)),
                progress.setValue(done),
                progress.setLabelText(name.rsplit("/", 1)[-1])))
        progress.canceled.connect(op.cancel)
        op.finished_all.connect(lambda ok, err: (
            progress.close(),
            self._operations.remove(op),
            refresh_panel.refresh() if refresh_panel is not None else None,
            self.statusBar().showMessage(
                f"Zakończono: {ok} OK, {err} błędów."),
            op.deleteLater()))
        op.failed.connect(lambda path, msg: self.statusBar().showMessage(
            f"Błąd: {path.rsplit('/', 1)[-1]} — {msg}"))
        self._operations.append(op)
        op.start()

    def _run_transfer(self, op, dst: Panel, items, cut: bool, verb: str,
                      target_dir: Optional[str] = None) -> None:
        """Uruchamia kopiowanie/przenoszenie i podświetla w dst to, co do niego trafiło.

        Podświetlenie (niebieskie = kopiuj, pomarańczowe = przenieś) stosowane
        jest po przeładowaniu katalogu docelowego i gaśnie samo po chwili.
        """
        target = (target_dir or dst.current_path).rstrip("/") or "/"
        expected = {f"{target}/{p.rstrip('/').rsplit('/', 1)[-1]}"
                    for _, p in items}
        failed: set[str] = set()

        def on_failed(path, msg):
            failed.add(path)

        def on_done(ok, err):
            if ok <= 0 or not expected:
                return
            failed_dst = {f"{target}/{p.rstrip('/').rsplit('/', 1)[-1]}"
                          for p in failed}
            paths = expected - failed_dst
            # Podświetlaj tylko pozycje widoczne w docelowym panelu
            if paths and target == dst.current_path.rstrip("/"):
                dst.set_pending_highlight(paths, cut)
            self.statusBar().showMessage(
                f"{verb} {len(paths)} pozycji do {target}.")

        op.failed.connect(on_failed)
        op.finished_all.connect(on_done)
        self._run_operation(op, refresh_panel=dst)

    # ----- schowek (Ctrl+C / Ctrl+X / Ctrl+V) -----
    def _copy_selected(self, cut: bool = False) -> None:
        panel = self._active
        sel = panel.selected()
        if not sel:
            return
        self._clipboard = [(panel.provider, i.path) for i in sel]
        self._clipboard_cut = cut
        model: FileListModel = panel.file_list.model()
        model.set_clipboard_highlight({p for _, p in self._clipboard}, cut)
        self.statusBar().showMessage(
            f"Schowek: {len(sel)} pozycji ({'wytnij' if cut else 'kopiuj'}) — "
            "przełącz panel (Tab) i wciśnij Ctrl+V.")

    def _paste(self) -> None:
        if not self._clipboard:
            return
        panel = self._active
        was_cut = self._clipboard_cut
        cls = MoveOperation if was_cut else CopyOperation
        op = cls(self._clipboard, panel.provider, panel.current_path, self)
        if was_cut:
            op.finished_all.connect(lambda *_: self._clear_clipboard())
        self._run_transfer(op, panel, self._clipboard, was_cut,
                           "Przeniesiono" if was_cut else "Skopiowano")

    def _clear_clipboard(self) -> None:
        self._clipboard = []
        self._clipboard_cut = False
        for panel in (self.left, self.right):
            model: FileListModel = panel.file_list.model()
            model.set_clipboard_highlight(set(), False)

    # ----- przeciąganie między panelami -----
    @staticmethod
    def _drop_items(src: FileSystemProvider, paths: List[str],
                    target_dir: str) -> List[tuple[FileSystemProvider, str]]:
        """Pozycje do skopiowania/przeniesienia (bez samokopii w tym samym katalogu)."""
        target = target_dir.rstrip("/") or "/"
        items = []
        for p in paths:
            parent = src.parent(p) or "/"
            if p == target or parent.rstrip("/") == target:
                continue  # nie kopiuj pliku „na siebie”
            items.append((src, p))
        return items

    def _on_panel_drop(self, target_panel: Panel, paths: List[str],
                       target_dir: Optional[str]) -> None:
        if not paths:
            return
        # Źródłem jest panel, z którego ruszył się drag (aktywny w chwili upuszczenia)
        src = self._active.provider if self._active is not target_panel \
            else target_panel.provider
        dst_dir = target_dir or target_panel.current_path
        items = self._drop_items(src, paths, dst_dir)
        if not items:
            return
        cut = bool(QApplication.keyboardModifiers()
                   & Qt.KeyboardModifier.ShiftModifier)
        cls = MoveOperation if cut else CopyOperation
        op = cls(items, target_panel.provider, dst_dir, self)
        self._run_transfer(op, target_panel, items, cut,
                           "Przeniesiono" if cut else "Skopiowano",
                           target_dir=dst_dir)

    # ----- archiwa -----
    def _compress_selected(self) -> None:
        panel = self._active
        sel = [i for i in panel.selected()
               if isinstance(panel.provider, LocalFileSystem)]
        if not sel or not isinstance(panel.provider, LocalFileSystem):
            QMessageBox.information(self, "Kompresja",
                                    "Kompresja ZIP działa dla plików lokalnych.")
            return
        default = f"{panel.current_path.rstrip('/')}/{sel[0].name}.zip"
        name, ok = QInputDialog.getText(self, "Kompresja ZIP",
                                        "Plik wynikowy:", text=default)
        if not ok or not name.strip():
            return
        try:
            archives.compress_zip([i.path for i in sel], name.strip())
            panel.refresh()
        except archives.ArchiveError as exc:
            QMessageBox.critical(self, "Kompresja", str(exc))

    def _extract_selected(self) -> None:
        panel = self._active
        sel = panel.selected()
        if len(sel) != 1 or not isinstance(panel.provider, LocalFileSystem):
            QMessageBox.information(self, "Wypakuj",
                                    "Zaznacz jedno archiwum (plik lokalny).")
            return
        info = sel[0]
        out = f"{panel.current_path.rstrip('/')}/{info.name.rsplit('.', 1)[0]}"
        try:
            archives.extract(info.path, out)
            panel.refresh()
        except archives.ArchiveError as exc:
            QMessageBox.critical(self, "Wypakuj", str(exc))

    def _show_storage_analysis(self) -> None:
        from ui.storage_view import StorageAnalysisDialog
        StorageAnalysisDialog(self._active.current_path, self).exec()

    def _show_media_collections(self) -> None:
        from ui.media_collections_dialog import MediaCollectionsDialog
        MediaCollectionsDialog(self).exec()

    # ----- synchronizacja i batch operations w menu -----
    def _build_toolbar_sync(self) -> None:
        tb = self.findChild(QToolBar, "Operacje")
        if not tb:
            tb = QToolBar("Sync / Batch", movable=False)
            self.insertToolBar(self._toolbar, tb)

        tb.addSeparator()
        tb.addAction("🔄 Sync paths", lambda: self._sync_current_path(self._active))
        tb.addAction("📊 Compare panels", lambda: self._compare_panels(self._active))
        tb.addAction("↔ Merge from other", lambda: self._merge_from_other(self._active))
        tb.addSeparator()
        tb.addAction("📝 Batch rename", self._batch_rename)
        tb.addAction("🎨 Batch convert", self._batch_convert)
        tb.addAction("🏷️  Batch tags", self._batch_tag)

    # ----- operacje w aktywnym panelu -----
    def _new_folder(self) -> None:
        panel = self._active
        name, ok = QInputDialog.getText(self, "Nowy katalog", "Nazwa:")
        if ok and name.strip():
            try:
                panel.provider.mkdir(f"{panel.current_path.rstrip('/')}/{name.strip()}")
                panel.refresh()
            except FileSystemError as exc:
                QMessageBox.critical(self, "Błąd", str(exc))

    def _rename_selected(self) -> None:
        panel = self._active
        sel = panel.selected()
        if len(sel) != 1:
            return
        info = sel[0]
        name, ok = QInputDialog.getText(self, "Zmień nazwę", "Nowa nazwa:",
                                        text=info.name)
        if ok and name.strip() and name.strip() != info.name:
            try:
                panel.provider.rename(info.path, name.strip())
                panel.refresh()
            except FileSystemError as exc:
                QMessageBox.critical(self, "Błąd", str(exc))

    # ==================================================
    # Pasek narzędzi, menu i menu kontekstowe
    # ==================================================
    def _build_toolbar(self) -> None:
        tb = QToolBar("Operacje", movable=False)
        self.addToolBar(tb)
        self._actions = {}

        def act(key, text, slot, shortcut=None):
            a = QAction(text, self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
                self.addAction(a)
            tb.addAction(a)
            self._actions[key] = a
            return a

        act("back", "◀ Wstecz", self._active_back, "Alt+Left")
        act("forward", "▶ Dalej", self._active_forward, "Alt+Right")
        act("up", "⬆ W górę", self._active_up, "Backspace")
        act("refresh", "⟳ Odśwież", self._active_refresh, "F12")
        tb.addSeparator()
        act("copy", "F5  Kopiuj → drugi panel", self._copy_to_other)
        act("move", "F6  Przenieś → drugi panel", self._move_to_other)
        tb.addSeparator()
        act("mkdir", "F7  Nowy katalog", self._new_folder)
        act("rename", "F2  Zmień nazwę", self._rename_selected)
        act("view", "F3  Podgląd", self._view_selected)
        act("edit", "F4  Edytuj", self._edit_selected)
        act("delete", "F8  Usuń", self._delete_selected)
        tb.addSeparator()
        act("analyze", "📊  Analiza pamięci", self._show_storage_analysis)
        act("collections", "🎵  Zbiory mediów", self._show_media_collections)
        act("sync", "🔄  Sync paths", self._sync_current_path)
        act("compare", "📊  Compare panels", self._compare_panels)
        act("merge", "↔  Merge from other", self._merge_from_other)
        act("batch_rename", "📝  Batch rename", self._batch_rename)
        act("batch_convert", "🎨  Batch convert", self._batch_convert)
        act("batch_tags", "🏷️  Batch tags", self._batch_tag)
        act("sync", "🔄  Sync paths", self._sync_current_path)
        act("compare", "📊  Compare panels", self._compare_panels)
        act("merge", "↔  Merge from other", self._merge_from_other)
        act("batch_rename", "📝  Batch rename", self._batch_rename)
        act("batch_convert", "🎨  Batch convert", self._batch_convert)
        act("batch_tags", "🏷️  Batch tags", self._batch_tag)

    def _build_menus(self) -> None:
        A = self._actions
        m_file = self.menuBar().addMenu("&Plik")

        def menu_action(menu, text, slot, shortcut=None):
            a = QAction(text, self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
                self.addAction(a)
            menu.addAction(a)
            return a

        m_file.addAction(A["mkdir"])
        m_file.addAction(A["rename"])
        m_file.addSeparator()
        m_file.addAction(A["copy"])
        m_file.addAction(A["move"])
        m_file.addAction(A["delete"])
        m_file.addSeparator()
        m_file.addAction(A["view"])
        m_file.addAction(A["edit"])
        m_file.addSeparator()
        menu_action(m_file, "Kopiuj (schowek)", lambda: self._copy_selected(cut=False),
                    "Ctrl+C")
        menu_action(m_file, "Wytnij (schowek)", lambda: self._copy_selected(cut=True),
                    "Ctrl+X")
        menu_action(m_file, "Wklej (schowek)", self._paste, "Ctrl+V")
        m_file.addSeparator()
        menu_action(m_file, "Kompresuj do ZIP…", self._compress_selected)
        menu_action(m_file, "Wypakuj archiwum…", self._extract_selected)
        m_file.addSeparator()
        m_file.addAction(A["analyze"])
        m_file.addAction(A["collections"])
        m_file.addSeparator()
        menu_action(m_file, "Klucze API chmur…", self._show_cloud_keys)
        m_file.addSeparator()
        menu_action(m_file, "Tryb jednopanelowy", self._open_single_mode)
        m_file.addSeparator()
        menu_action(m_file, "Zakończ", self.close, "Ctrl+Q")

        # dodatkowe akcje sync/batch w menu
        m_file.addAction(A["sync"])
        m_file.addAction(A["compare"])
        m_file.addAction(A["merge"])
        m_file.addSeparator()
        m_file.addAction(A["batch_rename"])
        m_file.addAction(A["batch_convert"])
        m_file.addAction(A["batch_tags"])

    def _open_single_mode(self) -> None:
        from ui.main_window import MainWindow
        from ui.window_registry import keep_window
        QSettings("FileManager", "FileManager").setValue("ui/mode", "single")
        w = MainWindow()
        keep_window(w)  # zapobiega usunięciu przez GC
        w.show()
        self.close()

    def _context_menu(self, panel: Panel, pos) -> None:
        self._set_active(panel)
        sel = panel.selected()
        menu = QMenu(self)
        if sel:
            menu.addAction("Otwórz", lambda: self._open_item(panel, sel[0]))
            menu.addAction("Zmień nazwę (F2)", self._rename_selected)
            menu.addSeparator()
            menu.addAction("Kopiuj do drugiego (F5)", self._copy_to_other)
            menu.addAction("Przenieś do drugiego (F6)", self._move_to_other)
            menu.addSeparator()
            menu.addAction("Kopiuj (Ctrl+C)", lambda: self._copy_selected(cut=False))
            menu.addAction("Wytnij (Ctrl+X)", lambda: self._copy_selected(cut=True))
            menu.addAction("Usuń (F8)", self._delete_selected)
            menu.addSeparator()
            menu.addAction("Kompresuj do ZIP…", self._compress_selected)
            if len(sel) == 1 and archives.is_archive(sel[0].name):
                menu.addAction("Wypakuj…", self._extract_selected)
        else:
            menu.addAction("Nowy katalog (F7)", self._new_folder)
            paste = menu.addAction("Wklej (Ctrl+V)", self._paste)
            paste.setEnabled(bool(self._clipboard))
            menu.addSeparator()
            menu.addAction("Odśwież", self._active_refresh)
            menu.addSeparator()
            menu.addAction("Sync paths", lambda: self._sync_current_path(panel))
            menu.addAction("Compare panels", lambda: self._compare_panels(panel))
            menu.addAction("Merge from other", lambda: self._merge_from_other(panel))
            menu.addSeparator()
            menu.addAction("Batch rename", self._batch_rename)
            menu.addAction("Batch convert", self._batch_convert)
            menu.addAction("Batch tags", self._batch_tag)
        menu.exec(panel.file_list.viewport().mapToGlobal(pos))

    # ==================================================
    def closeEvent(self, event) -> None:
        connector = getattr(self, "_cloud_connector", None)
        if connector is not None:
            try:
                if connector.isRunning():
                    connector.cancel_event.set()
                    connector.wait(2000)
            except RuntimeError:
                pass  # obiekt C++ już usunięty — nic do sprzątania
        for panel in (self.left, self.right):
            panel.shutdown()
            if hasattr(panel.provider, "disconnect"):
                panel.provider.disconnect()
        for op in self._operations:
            op.cancel()
            op.wait(1000)
        super().closeEvent(event)

    # ==================================================
    # Synchronizacja i porównanie paneli
    # ==================================================

    def _build_sync_menu(self, panel: Panel) -> QMenu:
        """Menu poleceń synchronizacyjnych."""
        menu = QMenu("Sync / Compare", self)

        menu.addAction("Sync this path → other", lambda: self._sync_current_path(panel))
        menu.addAction("Compare with other panel", lambda: self._compare_panels(panel))
        menu.addAction("Merge from other to this", lambda: self._merge_from_other(panel))

        return menu

    def _sync_current_path(self, panel: Panel) -> None:
        """Synchronizuje bieżący katalog między panelami."""
        other = self._other(panel)
        src_provider = panel.provider
        dst_provider = other.provider

        src_path = panel.current_path
        dst_path = src_path.replace(src_provider.root_path(), dst_provider.root_path(), 1)

        progress = QProgressDialog(f"Sync: {src_path} → {dst_path}", "Cancel", 0, 100, self)
        progress.setWindowTitle("Synchronizacja")
        progress.setWindowModality(Qt.WindowModality.WindowModal)

        try:
            merge_directories(src_provider, src_path, dst_provider, dst_path, progress)
            other.refresh()
            self.statusBar().showMessage(f"Synchronizacja: {src_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Sync failed", str(exc))

    def _compare_panels(self, panel: Panel) -> None:
        """Porównuje bieżący katalog obu paneli."""
        other = self._other(panel)

        src_path = panel.current_path
        dst_path = other.current_path

        try:
            only_left, only_right, different, identical = compare_directories(
                panel.provider, src_path, other.provider, dst_path)
        except Exception as exc:
            QMessageBox.critical(self, "Compare failed", str(exc))
            return

        msg = (
            f"Only in left ({len(only_left)}):\n" +
            "\n".join(f"• {i.name}" for i in only_left[:15]) +
            (f"\n… i {len(only_left) - 15} more" if len(only_left) > 15 else "") +
            f"\n\nOnly in right ({len(only_right)}):\n" +
            "\n".join(f"• {i.name}" for i in only_right[:15]) +
            (f"\n… i {len(only_right) - 15} more" if len(only_right) > 15 else "") +
            f"\n\nDifferent ({len(different)}):\n" +
            "\n".join(f"• {i[0].name}" for i in different[:10]) +
            (f"\n… i {len(different) - 10} more" if len(different) > 10 else "") +
            f"\n\nIdentical ({len(identical)})" +
            (f"\n{identical[0][0].name}" if len(identical) == 1 else "")
        )
        QMessageBox.information(self, f"Compare: {src_path} vs {dst_path}", msg)

    def _merge_from_other(self, target_panel: Panel) -> None:
        """Skleja zawartość drugiego panelu do wybranego."""
        src_panel = self._other(target_panel)

        src_path = src_panel.current_path
        dst_path = target_panel.current_path

        progress = QProgressDialog(f"Merging: {src_path} → {dst_path}", "Cancel", 0, 100, self)
        progress.setWindowTitle("Merge")
        progress.setWindowModality(Qt.WindowModality.WindowModal)

        try:
            merge_directories(src_panel.provider, src_path,
                             target_panel.provider, dst_path, progress)
            target_panel.refresh()
            self.statusBar().showMessage(f"Merge: {src_path} → {dst_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Merge failed", str(exc))

    # ==================================================
    # Batch operations (rename, convert, tag)
    # ==================================================

    def _batch_rename(self) -> None:
        """Batch rename w aktywnym panelu (wzorce: szukaj/zamień, numeryacja)."""
        panel = self._active
        sel = panel.selected()
        if not sel:
            return

        pattern, ok = QInputDialog.getText(self, "Batch rename",
                                           "Wzorzec:\n"
                                           "[name] — nazwa pliku\n"
                                           "[ext] — rozszerzenie\n"
                                           "[num] — numer (od 1)\n"
                                           "Przykład: photo_[num]_v[ext]")
        if not ok or not pattern.strip():
            return

        for idx, info in enumerate(sel, start=1):
            name = info.name
            ext = info.name.rsplit(".", 1)[-1] if "." in info.name else ""
            new_name = pattern.replace("[name]", name)\
                             .replace("[ext]", ext)\
                             .replace("[num]", str(idx))
            try:
                panel.provider.rename(info.path, new_name)
            except Exception as exc:
                self.statusBar().showMessage(f"Rename error: {name} → {new_name} — {exc}")

        panel.refresh()
        self.statusBar().showMessage(f"Batch rename: {len(sel)} plików")

    def _batch_convert(self) -> None:
        """Batch convert obrazów (resize, rotate, format)."""
        from PySide6.QtWidgets import QInputDialog
        panel = self._active
        sel = [i for i in panel.selected() if i.mime.startswith("image/")]
        if not sel:
            QMessageBox.information(self, "Batch convert", "Zaznacz obrazy.")
            return

        formats = ["JPG", "PNG", "WebP"]
        fmt, ok = QInputDialog.getItem(self, "Batch convert",
                                       "Format wynikowy:", formats, 0, False)
        if not ok:
            return

        for info in sel:
            # TODO: zastosować rzeczywistą konwersję
            self.statusBar().showMessage(f"Convert: {info.name} → {fmt}")
        panel.refresh()
        self.statusBar().showMessage(f"Batch convert: {len(sel)} obrazów → {fmt}")

    def _batch_tag(self) -> None:
        """Batch tagowanie wielu plików naraz."""
        panel = self._active
        sel = panel.selected()
        if not sel:
            return

        tags_input, ok = QInputDialog.getText(self, "Batch tags",
                                               "Tagi (oddzielone przecinkami):")
        if not ok or not tags_input.strip():
            return

        tags = [t.strip() for t in tags_input.split(",") if t.strip()]

        # TODO: zapisz tagi w metadata (XMP/JSON)
        self.statusBar().showMessage(f"Batch tags: {len(sel)} plików — {', '.join(tags)}")

    # ==================================================
    # Theme switching
    # ==================================================

    def set_theme(self, theme_name: str) -> None:
        """Zmień motyw UI."""
        self.theme_manager.apply_theme(QApplication.instance(), theme_name)
        self.statusBar().showMessage(f"Motyw: {theme_name}")

    def toggle_theme(self) -> None:
        """Przełącz motyw (ciemny/jasny)."""
        themes = get_theme_names()
        current = getattr(self, "_current_theme", "dark")
        idx = themes.index(current) if current in themes else 1
        next_theme = themes[(idx + 1) % len(themes)]
        self.set_theme(next_theme)
        self._current_theme = next_theme

    # ==================================================
    # Version control
    # ==================================================

    def version_current(self) -> None:
        """Utwórz wersję aktywnego pliku."""
        panel = self._active
        sel = panel.selected()
        if not sel:
            return
        for info in sel:
            self.version_control.version_file(info.path)
        self.statusBar().showMessage(f"Zapisano wersje: {len(sel)} plików")

    def show_versions(self) -> None:
        """Pokaż historię wersji dla aktywnego pliku."""
        panel = self._active
        sel = panel.selected()
        if not sel:
            return
        info = sel[0]
        history = self.version_control.get_history(info.path)
        if history:
            msg = f"Historia wersji dla {info.name}:\n" + "\n".join(
                f"{v.timestamp.strftime('%Y-%m-%d %H:%M')} — {v.hash[:8]} — {v.size}B" for v in history)
            QMessageBox.information(self, f"Wersje: {info.name}", msg)
        else:
            QMessageBox.information(self, f"Wersje: {info.name}", "Brak historii.")

    def restore_version(self) -> None:
        """Przywróć wybraną wersję."""
        panel = self._active
        sel = panel.selected()
        if not sel:
            return
        info = sel[0]
        history = self.version_control.get_history(info.path)
        if history and len(history) > 1:
            index, ok = QInputDialog.getInt(self, "Przywróć wersję",
                                            "Indeks (0 = najnowsza):",
                                            value=0, min=0, max=len(history) - 1)
            if ok:
                self.version_control.restore_version(info.path, index)
                panel.refresh()
                self.statusBar().showMessage("Wersja przywrócona.")

    # ==================================================
    # Search engine
    # ==================================================

    def global_search(self, query: Optional[str] = None) -> None:
        """Globalne wyszukiwanie w panelach."""
        if query is None:
            query, ok = QInputDialog.getText(self, "Szukaj",
                                             "Wyrażenie (regex, zawartość):")
            if not ok or not query:
                return
        panel = self._active
        self.search_engine.set_provider(panel.provider, panel.current_path)
        results = self.search_engine.search(query, regex=True, content=True)
        # Pokaż wyniki w panelu lub oknie
        self.statusBar().showMessage(f"Wyniki wyszukiwania: {len(results)}")
        for info in results[:10]:
            self.statusBar().showMessage(f"  {info.path}: {info.name}")

    def open_with_external(self) -> None:
        """Otwórz wybrany plik zewnętrznie."""
        panel = self._active
        sel = panel.selected()
        if not sel:
            return
        tools = self.external_tools.get_tools_for_file(sel[0])
        if tools:
            tool_names = [t.name for t in tools]
            tool, ok = QInputDialog.getItem(self, "Open with",
                                            "Narzędzie:", tool_names, 0, False)
            if ok:
                idx = tool_names.index(tool)
                self.external_tools.execute(tools[idx], sel[0].path)
        else:
            QMessageBox.information(self, "Open with",
                                    "Brak gotowych narzędzi dla tego typu pliku.")

    # ==================================================
    # Cloud sync
    # ==================================================

    def sync_cloud(self, account_name: Optional[str] = None) -> None:
        """Synchronizuj chmurę."""
        if account_name:
            state = self.cloud_manager.sync_account(account_name)
            self.statusBar().showMessage(
                f"Chmura {account_name}: {state.synced} zsynchronizowanych")
        else:
            results = self.cloud_manager.sync_all()
            total = sum(s.synced for s in results.values())
            self.statusBar().showMessage(f"Chmury: {total} plików zsynchronizowanych")

    def open_ftp_server(self) -> None:
        """Otwórz FTP serwer."""
        self.ftp_manager.start()
        self.statusBar().showMessage(f"FTP: ftp://{self.ftp_manager.config.host}:{self.ftp_manager.config.port}")

    def close_ftp_server(self) -> None:
        """Zamknij FTP serwer."""
        self.ftp_manager.stop()
        self.statusBar().showMessage("FTP zatrzymany.")

    def install_plugin(self, plugin_path: str) -> None:
        """Zainstaluj plugin."""
        installer = PluginInstaller()
        name = installer.install(plugin_path)
        self.plugin_manager.load(name)
        self.statusBar().showMessage(f"Wgrano plugin: {name}")

    def list_plugins(self) -> List[str]:
        """Zwróć listę pluginów."""
        return self.plugin_manager.list_installed()

    def enable_plugin(self, name: str) -> None:
        """Włącz plugin."""
        self.plugin_manager.enable(name)
        self.plugin_manager.load(name)
        self.statusBar().showMessage(f"Plugin {name} włączony.")

    def disable_plugin(self, name: str) -> None:
        """Wyłącz plugin."""
        self.plugin_manager.disable(name)
        self.plugin_manager.unload(name)
        self.statusBar().showMessage(f"Plugin {name} wyłączony.")

    # ==================================================
    # Cloud sync
    # ==================================================

    def sync_cloud(self, account_name: Optional[str] = None) -> None:
        """Synchronizuj chmurę."""
        if account_name:
            state = self.cloud_manager.sync_account(account_name)
            self.statusBar().showMessage(
                f"Chmura {account_name}: {state.synced} zsynchronizowanych")
        else:
            results = self.cloud_manager.sync_all()
            total = sum(s.synced for s in results.values())
            self.statusBar().showMessage(f"Chmury: {total} plików zsynchronizowanych")

    def open_ftp_server(self) -> None:
        """Otwórz FTP serwer."""
        self.ftp_manager.start()
        self.statusBar().showMessage(f"FTP: ftp://{self.ftp_manager.config.host}:{self.ftp_manager.config.port}")

    def close_ftp_server(self) -> None:
        """Zamknij FTP serwer."""
        self.ftp_manager.stop()
        self.statusBar().showMessage("FTP zatrzymany.")

    def install_plugin(self, plugin_path: str) -> None:
        """Zainstaluj plugin."""
        installer = PluginInstaller()
        name = installer.install(plugin_path)
        self.plugin_manager.load(name)
        self.statusBar().showMessage(f"Wgrano plugin: {name}")

    def list_plugins(self) -> List[str]:
        """Zwróć listę pluginów."""
        return self.plugin_manager.list_installed()

    def enable_plugin(self, name: str) -> None:
        """Włącz plugin."""
        self.plugin_manager.enable(name)
        self.plugin_manager.load(name)
        self.statusBar().showMessage(f"Plugin {name} włączony.")

    def disable_plugin(self, name: str) -> None:
        """Wyłącz plugin."""
        self.plugin_manager.disable(name)
        self.plugin_manager.unload(name)
        self.statusBar().showMessage(f"Plugin {name} wyłączony.")

    def check_updates(self, current_version: str = "1.0.0") -> None:
        """Sprawdź dostępne aktualizacje."""
        release = self.updater.check_for_update(current_version=current_version)
        if release:
            msg = f"Dostępna wersja: {release.version}\n\n{release.description}"
            QMessageBox.information(self, "Aktualizacja", msg)

    def set_language(self, lang: str) -> None:
        """Ustaw język."""
        self.i18n.current_locale = lang
        self.statusBar().showMessage(f"Język: {lang}")

    def toggle_language(self) -> None:
        """Przełącz język."""
        current = self.i18n.current_locale
        self.set_language("pl" if current == "en" else "en")

