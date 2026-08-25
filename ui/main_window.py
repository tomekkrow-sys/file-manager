"""Główne okno File Managera — jednopanelowy układ w stylu File Manager Plus."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QMessageBox, QProgressDialog,
    QSplitter, QToolBar, QVBoxLayout, QWidget,
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
from core.ftp_server import LocalFtpServer
from core.local_fs import LocalFileSystem
from core.operations import CopyOperation, DeleteOperation, MoveOperation
from core.sftp_fs import SftpFileSystem
from core.smb_fs import SmbFileSystem
from core.i18n import _, get_language, set_language
from core.storage_analysis import human_size
from core.updater import download, fetch_update, install, installed_deb_version
from ui.dialogs import (
    FtpConnectDialog, FtpServerDialog, SftpConnectDialog, SmbConnectDialog,
)
from ui.file_list import FILE_MIME, FileListModel, FileListView


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
    connected = Signal(object)   # gotowy FileSystemProvider
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
            self.failed.emit(_("Nieoczekiwany błąd: {exc}").format(exc=exc))


class _UpdateChecker(QThread):
    """Sprawdza nową wersję w tle (nie zamraża UI)."""
    result = Signal(dict)

    def __init__(self, current: str, parent=None):
        super().__init__(parent)
        self._current = current

    def run(self) -> None:
        self.result.emit(fetch_update(self._current))


class _PlacesList(QListWidget):
    """Panel boczny akceptujący przeciąganie plików (kopiowanie myszką)."""

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.setAcceptDrops(True)
        self.drop_handler = None  # callback(paths, row) -> bool (zaakceptowano?)

    @staticmethod
    def _paths(event) -> List[str]:
        mime = event.mimeData()
        if not mime.hasFormat(FILE_MIME):
            return []
        try:
            return json.loads(bytes(mime.data(FILE_MIME)).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return []

    def _row_at(self, pos) -> Optional[int]:
        item = self.itemAt(pos)
        return self.row(item) if item is not None else None

    def dragEnterEvent(self, event) -> None:
        if self._paths(event) and self._row_at(event.position().toPoint()) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if self._paths(event) and self._row_at(event.position().toPoint()) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        paths = self._paths(event)
        row = self._row_at(event.position().toPoint())
        if paths and row is not None and self.drop_handler is not None:
            if self.drop_handler(paths, row):
                event.acceptProposedAction()
                return
        event.ignore()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(_("File Manager"))
        self.resize(1100, 700)

        # ----- stan -----
        self.provider: FileSystemProvider = LocalFileSystem()
        self.current_path = self.provider.root_path()
        self._history: List[str] = []
        self._history_idx = -1
        self._clipboard: List[tuple[FileSystemProvider, str]] = []
        self._clipboard_cut = False
        self._operations: list = []
        self._loader: Optional[_DirLoader] = None
        self._cloud_connector: Optional[_CloudConnector] = None
        self.ftp_server = LocalFtpServer()

        # ----- sidebar źródeł -----
        self.places = _PlacesList(maximumWidth=220)
        self.places.currentRowChanged.connect(self._on_place_changed)
        self.places.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.places.customContextMenuRequested.connect(self._places_context_menu)
        self.places.drop_handler = self._on_sidebar_drop
        self._rebuild_places()

        # ----- lista plików -----
        self.file_list = FileListView()
        self.file_list.on_double_click(self._open_item)
        self.file_list.set_drop_handler(self._on_drop_items)
        self.file_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._context_menu)

        # ----- pasek ścieżki + status -----
        self.path_label = QLabel()
        self.path_label.setStyleSheet("font-weight: bold; padding: 4px;")
        self.status_label = QLabel()

        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.addWidget(self.path_label)
        rlay.addWidget(self.file_list, 1)
        rlay.addWidget(self.status_label)

        splitter = QSplitter()
        splitter.addWidget(self.places)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self._build_toolbar()
        self._build_menus()

        # start
        self._navigate_to(self.current_path, add_history=True)

        # automatyczne sprawdzenie aktualizacji po uruchomieniu
        QTimer.singleShot(2000, lambda: self._check_updates(manual=False))

    # ==================================================
    # Sidebar źródeł
    # ==================================================
    def _rebuild_places(self) -> None:
        self.places.blockSignals(True)
        self.places.clear()
        self._places_map: list[tuple[str, object]] = []

        def add(label: str, action) -> None:
            QListWidgetItem(_(label), self.places)
            self._places_map.append((label, action))

        def sep(label: str) -> None:
            self.places.addItem(_(label))
            self._places_map.append((label, None))

        add("🖥  Pamięć lokalna", lambda: LocalFileSystem())
        add("📁  Katalog domowy", "home")
        add("📊  Analiza pamięci", "analyze")
        add("🎵  Zbiory mediów", "collections")
        sep("── Sieć ──")
        add("➕  Połącz FTP…", "ftp")
        add("➕  Połącz SSH (SFTP)…", "sftp")
        add("➕  Połącz NAS (SMB)…", "smb")
        add("📡  Udostępnij przez FTP…", "ftp_server")

        # Zapisane połączenia — jedno kliknięcie i wybór z pamięci
        saved = get_all_connections()
        if saved:
            sep("── Zapisane połączenia ──")
            for kind, params in saved:
                icon = {"ftp": "🔌", "sftp": "🔑", "smb": "🗄"}.get(kind, "🔌")
                add(_("{icon}  {name}").format(
                    icon=icon, name=params.get('name', params['host'])),
                    ("saved", kind, params))

        sep("── Chmury ──")
        add("☁  Google Drive…", "gdrive")
        add("☁  Dropbox…", "dropbox")
        add("☁  OneDrive…", "onedrive")
        add("⚙  Klucze API chmur…", "cloud_keys")
        self.places.blockSignals(False)

    def _on_place_changed(self, row: int) -> None:
        if row < 0 or row >= len(self._places_map):
            return
        label, action = self._places_map[row]
        if action is None:
            return
        if callable(action):
            self._switch_provider(action())
        elif isinstance(action, tuple) and action[0] == "saved":
            _, kind, params = action
            self._connect_saved(kind, params)
        elif action == "home":
            self._switch_provider(LocalFileSystem(), str(Path.home()))
        elif action == "analyze":
            self._show_storage_analysis()
        elif action == "collections":
            self._show_media_collections()
        elif action == "ftp":
            self._connect_ftp()
        elif action == "sftp":
            self._connect_sftp()
        elif action == "smb":
            self._connect_smb()
        elif action == "ftp_server":
            self._manage_ftp_server()
        elif action == "gdrive":
            self._connect_cloud(connect_gdrive, "gdrive")
        elif action == "dropbox":
            self._connect_cloud(connect_dropbox, "dropbox")
        elif action == "onedrive":
            self._connect_cloud(connect_onedrive, "onedrive")
        elif action == "cloud_keys":
            self._show_cloud_keys()

    def _places_context_menu(self, pos) -> None:
        """Menu prawego przycisku na panelu bocznym (usuwanie zapisanych)."""
        item = self.places.itemAt(pos)
        if item is None:
            return
        row = self.places.row(item)
        if row < 0 or row >= len(self._places_map):
            return
        action = self._places_map[row][1]
        if not (isinstance(action, tuple) and action[0] == "saved"):
            return
        _, kind, params = action
        name = params.get("name", params["host"])
        menu = QMenu(self)
        menu.addAction(_("🔌  Nawiąż połączenie"),
                       lambda: self._connect_saved(kind, params))
        menu.addSeparator()
        menu.addAction(_("🗑  Usuń z pamięci"), lambda: self._forget_connection(kind, name))
        menu.exec(self.places.viewport().mapToGlobal(pos))

    def _forget_connection(self, kind: str, name: str) -> None:
        if QMessageBox.question(
                self, _("Zapisane połączenia"),
                _("Usunąć połączenie „{name}” z pamięci?").format(name=name)
        ) != QMessageBox.StandardButton.Yes:
            return
        remove_connection(kind, name)
        self._rebuild_places()

    # ==================================================
    # Połączenia sieciowe
    # ==================================================
    def _connect_ftp(self) -> None:
        dlg = FtpConnectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        params = dlg.params()
        try:
            fs = FtpFileSystem(**provider_params("ftp", params))
        except FileSystemError as exc:
            QMessageBox.critical(self, _("FTP"), str(exc))
            return
        self._maybe_save_connection("ftp", params)
        self._switch_provider(fs, "/")

    def _connect_sftp(self) -> None:
        dlg = SftpConnectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        params = dlg.params()
        try:
            fs = SftpFileSystem(**provider_params("sftp", params))
        except FileSystemError as exc:
            QMessageBox.critical(self, _("SSH"), str(exc))
            return
        self._maybe_save_connection("sftp", params)
        self._switch_provider(fs, "/")

    def _connect_smb(self) -> None:
        dlg = SmbConnectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        params = dlg.params()
        try:
            fs = SmbFileSystem(**provider_params("smb", params))
        except FileSystemError as exc:
            QMessageBox.critical(self, _("NAS"), str(exc))
            return
        self._maybe_save_connection("smb", params)
        self._switch_provider(fs, "/")

    def _maybe_save_connection(self, kind: str, params: dict) -> None:
        """Zapamiętuje połączenie, jeśli użytkownik zaznaczył opcję zapisu."""
        if not params.get("save"):
            return
        store = {k: v for k, v in params.items()
                 if k not in ("save", "save_password")}
        if not params.get("save_password"):
            store.pop("password", None)
        save_connection(kind, store)
        self._rebuild_places()
        self.status_label.setText(
            _("Połączenie „{name}” zapisane — wybierzesz je z listy.").format(
                name=store.get('name', '')))

    def _connect_saved(self, kind: str, params: dict) -> None:
        """Łączy z zapisanym połączeniem (panel boczny)."""
        classes = {"ftp": FtpFileSystem, "sftp": SftpFileSystem, "smb": SmbFileSystem}
        cls = classes.get(kind)
        if cls is None:
            return
        try:
            fs = cls(**provider_params(kind, params))
        except FileSystemError as exc:
            QMessageBox.critical(self, _("Połączenie"), str(exc))
            return
        self._switch_provider(fs, "/")

    def _connect_cloud(self, connect_fn, provider_key: str = "") -> None:
        # Brak kluczy? Od razu zaproponuj otwarcie ustawień.
        from core.cloud.base import has_app_keys, get_saved_token
        if provider_key and not has_app_keys(provider_key) \
                and not get_saved_token(provider_key):
            answer = QMessageBox.question(
                self, _("Chmura"),
                _("Najpierw musisz wpisać klucze API tej chmury.\n"
                  "Otworzyć ustawienia kluczy?"))
            if answer == QMessageBox.StandardButton.Yes:
                self._show_cloud_keys()
            return

        progress = QProgressDialog(
            _("Otworzono przeglądarkę — zaloguj się do chmury.\n"
              "Po zalogowaniu wróć tutaj (okno zamknie się samo)."),
            _("Anuluj"), 0, 0, self)
        progress.setWindowTitle(_("Logowanie do chmury"))
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        connector = _CloudConnector(connect_fn, self)
        self._cloud_connector = connector
        progress.canceled.connect(connector.cancel_event.set)

        def on_connected(fs):
            progress.close()
            self._cloud_connector = None
            self._switch_provider(fs, "/")

        def on_failed(message: str):
            progress.close()
            self._cloud_connector = None
            if "anulowane" not in message:
                QMessageBox.critical(self, _("Chmura"), message)
            self.status_label.setText("")

        connector.connected.connect(on_connected)
        connector.failed.connect(on_failed)
        connector.finished.connect(connector.deleteLater)
        connector.start()

    def _show_cloud_keys(self) -> None:
        from ui.cloud_keys_dialog import CloudKeysDialog
        CloudKeysDialog(self).exec()

    def _manage_ftp_server(self) -> None:
        if self.ftp_server.is_running():
            if QMessageBox.question(
                    self, _("Serwer FTP"),
                    _("Serwer działa (ftp://{ip}:{port}). Zatrzymać?").format(
                        ip=self.ftp_server.local_ip(),
                        port=self.ftp_server.port)
            ) == QMessageBox.StandardButton.Yes:
                self.ftp_server.stop()
                self.status_label.setText(_("Serwer FTP zatrzymany."))
            return
        dlg = FtpServerDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            ip, port = self.ftp_server.start(**dlg.params())
        except OSError as exc:
            QMessageBox.critical(self, _("Serwer FTP"),
                                 _("Nie można uruchomić: {exc}").format(exc=exc))
            return
        QMessageBox.information(
            self, _("Serwer FTP"),
            _("Serwer działa!\n\nZ innego urządzenia połącz się z:\n"
              "  ftp://{ip}:{port}\n\n"
              "Użytkownik i hasło jak w konfiguracji (lub anonimowo, tylko odczyt).").format(
                ip=ip, port=port))

    # ==================================================
    # Nawigacja
    # ==================================================
    def _switch_provider(self, provider: FileSystemProvider, start_path: str = "/") -> None:
        if isinstance(provider, LocalFileSystem):
            start_path = provider.root_path() if start_path == "/" else start_path
        self.provider = provider
        self._history.clear()
        self._history_idx = -1
        self._navigate_to(start_path, add_history=True)

    def _navigate_to(self, path: str, add_history: bool = True) -> None:
        if add_history:
            del self._history[self._history_idx + 1:]
            self._history.append(path)
            self._history_idx += 1
        self.current_path = path
        self.path_label.setText(
            _("{name}  ▸  {path}").format(
                name=self.provider.display_name(), path=path))
        self.status_label.setText(_("Ładowanie…"))

        self._loader = _DirLoader(self.provider, path, self)
        self._loader.loaded.connect(self._on_dir_loaded)
        self._loader.failed.connect(self._on_dir_failed)
        self._loader.start()

    def _on_dir_loaded(self, items: list) -> None:
        model: FileListModel = self.file_list.model()
        model.set_content(self.provider, items)
        self.file_list.refresh_column_sizes()
        total = sum(i.size for i in items if not i.is_dir)
        dirs = sum(1 for i in items if i.is_dir)
        self.status_label.setText(
            _("{files} plików, {dirs} katalogów — {size}").format(
                files=len(items) - dirs, dirs=dirs, size=human_size(total)))

    def _on_dir_failed(self, message: str) -> None:
        self.status_label.setText("")
        QMessageBox.warning(self, _("Błąd"), message)

    def _go_back(self) -> None:
        if self._history_idx > 0:
            self._history_idx -= 1
            self._navigate_to(self._history[self._history_idx], add_history=False)

    def _go_forward(self) -> None:
        if self._history_idx < len(self._history) - 1:
            self._history_idx += 1
            self._navigate_to(self._history[self._history_idx], add_history=False)

    def _go_up(self) -> None:
        parent = self.provider.parent(self.current_path)
        if parent is not None:
            self._navigate_to(parent)

    def _go_home(self) -> None:
        if isinstance(self.provider, LocalFileSystem):
            self._navigate_to(str(Path.home()))
        else:
            self._navigate_to("/")

    # ==================================================
    # Otwieranie pozycji
    # ==================================================
    def _open_item(self, info: FileInfo) -> None:
        if info.is_dir:
            self._navigate_to(info.path)
            return
        self._open_file(info)

    def _open_file(self, info: FileInfo) -> None:
        mime = info.mime or ""
        if mime.startswith("image/"):
            from ui.viewers.image_viewer import ImageViewerDialog
            ImageViewerDialog(self.provider, info.path, self).exec()
        elif mime.startswith("audio/") or mime.startswith("video/"):
            from ui.viewers.media_player import MediaPlayerDialog
            MediaPlayerDialog(self.provider, info.path,
                              is_video=mime.startswith("video/"), parent=self).exec()
        elif mime.startswith("text/") or info.name.endswith(
                (".py", ".json", ".md", ".xml", ".csv", ".log", ".txt", ".ini", ".cfg")):
            from ui.viewers.text_editor import TextEditorDialog
            TextEditorDialog(self.provider, info.path, self).exec()
        elif archives.is_archive(info.name):
            self._show_archive(info)
        else:
            QMessageBox.information(self, info.name,
                                    _("Brak wbudowanego podglądu dla typu: {mime}").format(
                                        mime=mime))

    def _show_archive(self, info: FileInfo) -> None:
        if not isinstance(self.provider, LocalFileSystem):
            QMessageBox.information(
                self, _("Archiwum"),
                _("Podgląd archiwów dostępny dla plików lokalnych.\n"
                  "Skopiuj archiwum na dysk i spróbuj ponownie."))
            return
        try:
            entries = archives.list_archive(info.path)
        except archives.ArchiveError as exc:
            QMessageBox.critical(self, _("Archiwum"), str(exc))
            return
        preview = "\n".join(f"{human_size(s):>10}  {n}" for n, s in entries[:200])
        QMessageBox.information(
            self, _("Zawartość: {name}").format(name=info.name),
            _("Archiwum puste.") if not entries else
            _("{count} pozycji.\n\n{preview}").format(
                count=len(entries), preview=preview))

    # ==================================================
    # Operacje na plikach
    # ==================================================
    def _selected(self) -> List[FileInfo]:
        return self.file_list.selected_infos()

    def _refresh(self) -> None:
        self._navigate_to(self.current_path, add_history=False)

    def _new_folder(self) -> None:
        name, ok = QInputDialog.getText(self, _("Nowy katalog"), _("Nazwa:"))
        if ok and name.strip():
            try:
                self.provider.mkdir(f"{self.current_path.rstrip('/')}/{name.strip()}")
                self._refresh()
            except FileSystemError as exc:
                QMessageBox.critical(self, "Błąd", str(exc))

    def _rename_selected(self) -> None:
        sel = self._selected()
        if len(sel) != 1:
            return
        info = sel[0]
        name, ok = QInputDialog.getText(self, _("Zmień nazwę"), _("Nowa nazwa:"),
                                        text=info.name)
        if ok and name.strip() and name.strip() != info.name:
            try:
                self.provider.rename(info.path, name.strip())
                self._refresh()
            except FileSystemError as exc:
                QMessageBox.critical(self, "Błąd", str(exc))

    def _copy_selected(self, cut: bool = False) -> None:
        sel = self._selected()
        if not sel:
            return
        self._clipboard = [(self.provider, i.path) for i in sel]
        self._clipboard_cut = cut
        # Graficzne oznaczenie pozycji w schowku
        model: FileListModel = self.file_list.model()
        model.set_clipboard_highlight({p for _, p in self._clipboard}, cut)
        action = _("wytnij") if cut else _("kopiuj")
        self.status_label.setText(
            _("Schowek: {count} pozycji ({action}) — "
              "przejdź do celu i wciśnij Wklej.").format(
                count=len(sel), action=action))

    def _paste(self) -> None:
        if not self._clipboard:
            return
        was_cut = self._clipboard_cut
        cls = MoveOperation if was_cut else CopyOperation
        op = cls(self._clipboard, self.provider, self.current_path, self)
        if was_cut:
            # Po przeniesieniu schowek się czyści (jak w innych menedżerach)
            op.finished_all.connect(self._clear_clipboard)
        self._run_operation(op)

    # ----- przeciąganie i upuszczanie (kopiowanie myszką) -----
    def _drop_copy(self, items, dst: FileSystemProvider, dst_dir: str,
                   cut: bool) -> None:
        cls = MoveOperation if cut else CopyOperation
        op = cls(items, dst, dst_dir, self)
        if cut:
            op.finished_all.connect(self._clear_clipboard)
        self._run_operation(op)

    @staticmethod
    def _drop_items(src: FileSystemProvider, paths: List[str],
                    target_dir: str) -> List[tuple[FileSystemProvider, str]]:
        """Pozycje do skopiowania/przeniesienia (bez samokopii w tym samym katalogu)."""
        target = target_dir.rstrip("/") or "/"
        items = []
        for p in paths:
            parent = src.parent(p) or "/"
            if p == target or parent.rstrip("/") == target:
                continue  # nie kopiuj pliku "na siebie"
            items.append((src, p))
        return items

    def _on_drop_items(self, paths: List[str], target_dir: Optional[str]) -> None:
        """Upuszczenie na listę plików — kopiuje do wskazanego katalogu."""
        if not paths:
            return
        target = target_dir or self.current_path
        items = self._drop_items(self.provider, paths, target)
        if not items:
            return
        cut = bool(QApplication.keyboardModifiers()
                   & Qt.KeyboardModifier.ShiftModifier)
        self._drop_copy(items, self.provider, target, cut=cut)

    def _drop_target(self, row: int) -> Optional[tuple[FileSystemProvider, str]]:
        """Cel upuszczenia w panelu bocznym: (provider, katalog) albo None."""
        if row < 0 or row >= len(self._places_map):
            return None
        action = self._places_map[row][1]
        if callable(action):
            return action(), "/"  # Pamięć lokalna
        if action == "home":
            return LocalFileSystem(), str(Path.home())
        if isinstance(action, tuple) and action[0] == "saved":
            _, kind, params = action
            classes = {"ftp": FtpFileSystem,
                       "sftp": SftpFileSystem,
                       "smb": SmbFileSystem}
            cls = classes.get(kind)
            if cls is None:
                return None
            try:
                return cls(**provider_params(kind, params)), "/"
            except FileSystemError:
                return None
        return None

    def _on_sidebar_drop(self, paths: List[str], row: int) -> bool:
        """Upuszczenie na panel boczny — kopiuje do wybranego celu."""
        if not paths:
            return False
        target = self._drop_target(row)
        if target is None:
            return False
        dst, dst_dir = target
        items = self._drop_items(self.provider, paths, dst_dir)
        if not items:
            return False
        cut = bool(QApplication.keyboardModifiers()
                   & Qt.KeyboardModifier.ShiftModifier)
        self._drop_copy(items, dst, dst_dir, cut=cut)
        return True

    def _clear_clipboard(self, *args) -> None:
        self._clipboard = []
        self._clipboard_cut = False
        model: FileListModel = self.file_list.model()
        model.set_clipboard_highlight(set(), False)

    def _delete_selected(self) -> None:
        sel = self._selected()
        if not sel:
            return
        names = "\n".join(i.name for i in sel[:10])
        if len(sel) > 10:
            names += _("\n… i {n} więcej").format(n=len(sel) - 10)
        if QMessageBox.question(
                self, _("Usuń"),
                _("Usunąć trwale {count} pozycji?\n\n{names}").format(
                    count=len(sel), names=names)
        ) != QMessageBox.StandardButton.Yes:
            return
        self._run_operation(
            DeleteOperation([(self.provider, i.path) for i in sel], self))

    def _run_operation(self, op) -> None:
        progress = QProgressDialog(_("Operacja na plikach…"), _("Anuluj"), 0, 100, self)
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
            self._refresh(),
            self.status_label.setText(
                _("Zakończono: {ok} OK, {err} błędów.").format(ok=ok, err=err)),
            op.deleteLater()))
        op.failed.connect(lambda path, msg: self.status_label.setText(
            _("Błąd: {path} — {msg}").format(
                path=path.rsplit('/', 1)[-1], msg=msg)))
        self._operations.append(op)
        op.start()

    # ----- archiwa -----
    def _compress_selected(self) -> None:
        sel = [i for i in self._selected() if isinstance(self.provider, LocalFileSystem)]
        if not sel or not isinstance(self.provider, LocalFileSystem):
            QMessageBox.information(self, _("Kompresja"),
                                    _("Kompresja ZIP działa dla plików lokalnych."))
            return
        default = f"{self.current_path.rstrip('/')}/{sel[0].name}.zip"
        name, ok = QInputDialog.getText(self, _("Kompresja ZIP"),
                                        _("Plik wynikowy:"), text=default)
        if not ok or not name.strip():
            return
        try:
            archives.compress_zip([i.path for i in sel], name.strip())
            self._refresh()
        except archives.ArchiveError as exc:
            QMessageBox.critical(self, _("Kompresja"), str(exc))

    def _extract_selected(self) -> None:
        sel = self._selected()
        if len(sel) != 1 or not isinstance(self.provider, LocalFileSystem):
            QMessageBox.information(self, _("Wypakuj"),
                                    _("Zaznacz jedno archiwum (plik lokalny)."))
            return
        info = sel[0]
        out = f"{self.current_path.rstrip('/')}/{info.name.rsplit('.', 1)[0]}"
        try:
            archives.extract(info.path, out)
            self._refresh()
        except archives.ArchiveError as exc:
            QMessageBox.critical(self, _("Wypakuj"), str(exc))

    # ----- analiza pamięci -----
    def _show_storage_analysis(self) -> None:
        from ui.storage_view import StorageAnalysisDialog
        StorageAnalysisDialog(self.current_path, self).exec()

    # ----- zbiory mediów -----
    def _show_media_collections(self) -> None:
        from ui.media_collections_dialog import MediaCollectionsDialog
        MediaCollectionsDialog(self).exec()

    # ==================================================
    # Pasek narzędzi i menu
    # ==================================================
    def _build_toolbar(self) -> None:
        tb = QToolBar(_("Nawigacja"), movable=False)
        self.addToolBar(tb)

        def act(text, slot, shortcut=None):
            a = QAction(_(text), self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
                self.addAction(a)
            tb.addAction(a)
            return a

        act("◀ Wstecz", self._go_back, "Alt+Left")
        act("▶ Dalej", self._go_forward, "Alt+Right")
        act("⬆ W górę", self._go_up, "Alt+Up")
        act("⌂ Start", self._go_home, "Ctrl+Home")
        tb.addSeparator()
        act("⟳ Odśwież", self._refresh, "F5")
        tb.addSeparator()
        # Kopiowanie myszką — przyciski widoczne zawsze (skróty z menu)
        act("📋  Kopiuj", lambda: self._copy_selected(cut=False))
        act("✂  Wytnij", lambda: self._copy_selected(cut=True))
        act("📥  Wklej", self._paste)
        act("🗑  Usuń", self._delete_selected)

    def _build_menus(self) -> None:
        menu = self.menuBar().addMenu(_("&Plik"))

        def add(text, slot, shortcut=None):
            a = QAction(_(text), self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            menu.addAction(a)

        add("Nowy katalog", self._new_folder, "Ctrl+Shift+N")
        add("Zmień nazwę", self._rename_selected, "F2")
        menu.addSeparator()
        add("Kopiuj", lambda: self._copy_selected(cut=False), "Ctrl+C")
        add("Wytnij", lambda: self._copy_selected(cut=True), "Ctrl+X")
        add("Wklej", self._paste, "Ctrl+V")
        add("Usuń", self._delete_selected, "Del")
        menu.addSeparator()
        add("Kompresuj do ZIP…", self._compress_selected)
        add("Wypakuj archiwum…", self._extract_selected)
        menu.addSeparator()
        add("Analiza pamięci…", self._show_storage_analysis)
        add("Zbiory mediów…", self._show_media_collections)
        menu.addSeparator()
        add("Klucze API chmur…", self._show_cloud_keys)
        menu.addSeparator()
        add("Zakończ", self.close, "Ctrl+Q")
        menu.addSeparator()
        add("Sprawdź aktualizacje…", self._check_updates, "Ctrl+U")

        lang_menu = menu.addMenu(_(u"Język"))
        lang_menu.addAction(_(u"Polski"), lambda: self._set_language("pl"))
        lang_menu.addAction(_(u"English"), lambda: self._set_language("en"))

    def _set_language(self, code: str) -> None:
        set_language(code)
        QSettings("FileManager", "FileManager").setValue("language", code)
        QMessageBox.information(
            self, _("Język"), _("Zmieniono język."))
        # przebuduj okno w nowym języku od razu (bez restartu programu)
        new_window = MainWindow()
        new_window.show()
        self.close()

    def _context_menu(self, pos) -> None:
        sel = self._selected()
        menu = QMenu(self)
        if sel:
            menu.addAction(_("Otwórz"), lambda: self._open_item(sel[0]))
            menu.addAction(_("Zmień nazwę"), self._rename_selected)
            menu.addSeparator()
            menu.addAction(_("Kopiuj"), lambda: self._copy_selected(cut=False))
            menu.addAction(_("Wytnij"), lambda: self._copy_selected(cut=True))
            menu.addAction(_("Usuń"), self._delete_selected)
            menu.addSeparator()
            menu.addAction(_("Kompresuj do ZIP…"), self._compress_selected)
            if len(sel) == 1 and archives.is_archive(sel[0].name):
                menu.addAction(_("Wypakuj…"), self._extract_selected)
        else:
            menu.addAction(_("Nowy katalog"), self._new_folder)
            menu.addAction(_("Wklej"), self._paste,
                           enabled=bool(self._clipboard))
            menu.addSeparator()
            menu.addAction(_("Odśwież"), self._refresh)
        menu.exec(self.file_list.viewport().mapToGlobal(pos))

    # ==================================================
    def closeEvent(self, event) -> None:
        self.ftp_server.stop()
        connector = getattr(self, "_cloud_connector", None)
        if connector is not None:
            try:
                if connector.isRunning():
                    connector.cancel_event.set()
                    connector.wait(2000)
            except RuntimeError:
                pass  # obiekt C++ już usunięty — nic do sprzątania
        if hasattr(self.provider, "disconnect"):
            self.provider.disconnect()
        for op in self._operations:
            op.cancel()
            op.wait(1000)
        super().closeEvent(event)

    # ==================================================
    # Aktualizacje (GitHub)
    # ==================================================
    def _check_updates(self, manual: bool = True) -> None:
        """Sprawdź nową wersję na GitHubie (w tle)."""
        self._update_auto = not manual
        current = QApplication.instance().applicationVersion()
        if manual:
            self._update_progress = QProgressDialog(
                _("Sprawdzanie aktualizacji…"), _("Anuluj"), 0, 0, self)
            self._update_progress.setWindowModality(Qt.WindowModality.WindowModal)
            self._update_progress.setMinimumDuration(0)
            self._update_progress.show()
        checker = _UpdateChecker(current, self)
        self._update_checker = checker
        if manual:
            checker.finished.connect(self._update_progress.close)
        checker.result.connect(self._on_update_result)
        checker.start()

    def _on_update_result(self, info: dict) -> None:
        status = info.get("status")
        if status == "update":
            # Przy auto-sprawdzaniu nie nękaj, gdy wersja to domyślny placeholder
            # (uruchomienie z kodu bez tagu git -> fałszywa wersja 0.1.0).
            if self._update_auto and info.get("current") in ("0.1.0", "0.0.0"):
                return
            self._offer_update(info)
            return
        if self._update_auto:
            return  # przy automatycznym sprawdzaniu milczmy, gdy brak nowości
        if status == "current":
            QMessageBox.information(
                self, _("Aktualizacja"),
                _("Masz najnowszą wersję ({version}).").format(
                    version=info.get('version')))
        elif status == "error":
            QMessageBox.warning(
                self, _("Aktualizacja"),
                _("Nie udało się sprawdzić aktualizacji:\n{error}").format(
                    error=info.get('error')))

    def _offer_update(self, info: dict) -> None:
        version = info.get("version")
        asset = info.get("asset")
        answer = QMessageBox.question(
            self, _("Aktualizacja"),
            _("Dostępna nowsza wersja: {version}.\n"
              "Pobrać i zainstalować teraz?").format(version=version),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes or not asset:
            return
        name, url = asset
        dest = os.path.join(tempfile.gettempdir(), name)
        progress = QProgressDialog(_("Pobieranie {name}…").format(name=name),
                                  _("Anuluj"), 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        try:
            download(url, dest, lambda done, total: (
                progress.setMaximum(max(total, 1)),
                progress.setValue(done)))
        except Exception as exc:
            progress.close()
            QMessageBox.critical(self, _("Aktualizacja"),
                                 _("Błąd pobierania: {exc}").format(exc=exc))
            return
        progress.close()
        ok = install(dest)
        if ok and installed_deb_version() == version:
            QMessageBox.information(
                self, _("Aktualizacja"),
                _("Zainstalowano nową wersję. Uruchom aplikację ponownie."))
        elif ok:
            QMessageBox.information(
                self, _("Aktualizacja"),
                _("Instalacja przekazana do menedżera pakietów systemu.\n"
                  "Ukończ ją, wpisując hasło, a potem uruchom aplikację ponownie."))
        else:
            QMessageBox.warning(
                self, _("Aktualizacja"),
                _("Nie udało się zainstalować automatycznie.\n"
                  "Pobrany plik: {dest}\nZainstaluj go ręcznie, np.: sudo dpkg -i {dest}").format(
                    dest=dest))
