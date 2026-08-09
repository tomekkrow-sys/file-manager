"""Główne okno File Managera — jednopanelowy układ w stylu File Manager Plus."""

from __future__ import annotations

import threading
from typing import List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QProgressDialog, QSplitter, QToolBar,
    QVBoxLayout, QWidget,
)

from core import archives
from core.cloud.dropbox import connect_dropbox
from core.cloud.gdrive import connect_gdrive
from core.cloud.onedrive import connect_onedrive
from core.fs_base import FileInfo, FileSystemError, FileSystemProvider
from core.ftp_fs import FtpFileSystem
from core.ftp_server import LocalFtpServer
from core.local_fs import LocalFileSystem
from core.operations import CopyOperation, DeleteOperation, MoveOperation
from core.sftp_fs import SftpFileSystem
from core.smb_fs import SmbFileSystem
from core.storage_analysis import human_size
from ui.dialogs import (
    FtpConnectDialog, FtpServerDialog, SftpConnectDialog, SmbConnectDialog,
)
from ui.file_list import FileListModel, FileListView


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
            self.failed.emit(f"Nieoczekiwany błąd: {exc}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("File Manager")
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
        self.places = QListWidget(maximumWidth=220)
        self.places.currentRowChanged.connect(self._on_place_changed)
        self._rebuild_places()

        # ----- lista plików -----
        self.file_list = FileListView()
        self.file_list.on_double_click(self._open_item)
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

    # ==================================================
    # Sidebar źródeł
    # ==================================================
    def _rebuild_places(self) -> None:
        self.places.blockSignals(True)
        self.places.clear()
        self._places_map: list[tuple[str, object]] = []

        def add(label: str, action) -> None:
            QListWidgetItem(label, self.places)
            self._places_map.append((label, action))

        add("🖥  Pamięć lokalna", lambda: LocalFileSystem())
        add("📁  Katalog domowy", "home")
        add("📊  Analiza pamięci", "analyze")
        self.places.addItem("── Sieć ──")
        self._places_map.append(("sep", None))
        add("➕  Połącz FTP…", "ftp")
        add("➕  Połącz SSH (SFTP)…", "sftp")
        add("➕  Połącz NAS (SMB)…", "smb")
        add("📡  Udostępnij przez FTP…", "ftp_server")
        self.places.addItem("── Chmury ──")
        self._places_map.append(("sep", None))
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
        elif action == "home":
            self._switch_provider(LocalFileSystem(), "/home")
        elif action == "analyze":
            self._show_storage_analysis()
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

    # ==================================================
    # Połączenia sieciowe
    # ==================================================
    def _connect_ftp(self) -> None:
        dlg = FtpConnectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            fs = FtpFileSystem(**dlg.params())
        except FileSystemError as exc:
            QMessageBox.critical(self, "FTP", str(exc))
            return
        self._switch_provider(fs, "/")

    def _connect_sftp(self) -> None:
        dlg = SftpConnectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            fs = SftpFileSystem(**dlg.params())
        except FileSystemError as exc:
            QMessageBox.critical(self, "SSH", str(exc))
            return
        self._switch_provider(fs, "/")

    def _connect_smb(self) -> None:
        dlg = SmbConnectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            fs = SmbFileSystem(**dlg.params())
        except FileSystemError as exc:
            QMessageBox.critical(self, "NAS", str(exc))
            return
        self._switch_provider(fs, "/")

    def _connect_cloud(self, connect_fn, provider_key: str = "") -> None:
        # Brak kluczy? Od razu zaproponuj otwarcie ustawień.
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
            self._switch_provider(fs, "/")

        def on_failed(message: str):
            progress.close()
            self._cloud_connector = None
            if "anulowane" not in message:
                QMessageBox.critical(self, "Chmura", message)
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
                    self, "Serwer FTP",
                    f"Serwer działa (ftp://{self.ftp_server.local_ip()}:"
                    f"{self.ftp_server.port}). Zatrzymać?"
            ) == QMessageBox.StandardButton.Yes:
                self.ftp_server.stop()
                self.status_label.setText("Serwer FTP zatrzymany.")
            return
        dlg = FtpServerDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            ip, port = self.ftp_server.start(**dlg.params())
        except OSError as exc:
            QMessageBox.critical(self, "Serwer FTP", f"Nie można uruchomić: {exc}")
            return
        QMessageBox.information(
            self, "Serwer FTP",
            f"Serwer działa!\n\nZ innego urządzenia połącz się z:\n"
            f"  ftp://{ip}:{port}\n\n"
            f"Użytkownik i hasło jak w konfiguracji (lub anonimowo, tylko odczyt).")

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
        self.path_label.setText(f"{self.provider.display_name()}  ▸  {path}")
        self.status_label.setText("Ładowanie…")

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
            f"{len(items) - dirs} plików, {dirs} katalogów — {human_size(total)}")

    def _on_dir_failed(self, message: str) -> None:
        self.status_label.setText("")
        QMessageBox.warning(self, "Błąd", message)

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
            self._navigate_to(str(__import__("pathlib").Path.home()))
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
                                    f"Brak wbudowanego podglądu dla typu: {mime}")

    def _show_archive(self, info: FileInfo) -> None:
        if not isinstance(self.provider, LocalFileSystem):
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

    # ==================================================
    # Operacje na plikach
    # ==================================================
    def _selected(self) -> List[FileInfo]:
        return self.file_list.selected_infos()

    def _refresh(self) -> None:
        self._navigate_to(self.current_path, add_history=False)

    def _new_folder(self) -> None:
        name, ok = QInputDialog.getText(self, "Nowy katalog", "Nazwa:")
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
        name, ok = QInputDialog.getText(self, "Zmień nazwę", "Nowa nazwa:",
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
        self.status_label.setText(
            f"Schowek: {len(sel)} pozycji ({'wytnij' if cut else 'kopiuj'}) — "
            "przejdź do celu i wciśnij Wklej.")

    def _paste(self) -> None:
        if not self._clipboard:
            return
        cls = MoveOperation if self._clipboard_cut else CopyOperation
        self._run_operation(cls(self._clipboard, self.provider, self.current_path, self))

    def _delete_selected(self) -> None:
        sel = self._selected()
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
        self._run_operation(
            DeleteOperation([(self.provider, i.path) for i in sel], self))

    def _run_operation(self, op) -> None:
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
            self._refresh(),
            self.status_label.setText(
                f"Zakończono: {ok} OK, {err} błędów."),
            op.deleteLater()))
        op.failed.connect(lambda path, msg: self.status_label.setText(
            f"Błąd: {path.rsplit('/', 1)[-1]} — {msg}"))
        self._operations.append(op)
        op.start()

    # ----- archiwa -----
    def _compress_selected(self) -> None:
        sel = [i for i in self._selected() if isinstance(self.provider, LocalFileSystem)]
        if not sel or not isinstance(self.provider, LocalFileSystem):
            QMessageBox.information(self, "Kompresja",
                                    "Kompresja ZIP działa dla plików lokalnych.")
            return
        default = f"{self.current_path.rstrip('/')}/{sel[0].name}.zip"
        name, ok = QInputDialog.getText(self, "Kompresja ZIP",
                                        "Plik wynikowy:", text=default)
        if not ok or not name.strip():
            return
        try:
            archives.compress_zip([i.path for i in sel], name.strip())
            self._refresh()
        except archives.ArchiveError as exc:
            QMessageBox.critical(self, "Kompresja", str(exc))

    def _extract_selected(self) -> None:
        sel = self._selected()
        if len(sel) != 1 or not isinstance(self.provider, LocalFileSystem):
            QMessageBox.information(self, "Wypakuj",
                                    "Zaznacz jedno archiwum (plik lokalny).")
            return
        info = sel[0]
        out = f"{self.current_path.rstrip('/')}/{info.name.rsplit('.', 1)[0]}"
        try:
            archives.extract(info.path, out)
            self._refresh()
        except archives.ArchiveError as exc:
            QMessageBox.critical(self, "Wypakuj", str(exc))

    # ----- analiza pamięci -----
    def _show_storage_analysis(self) -> None:
        from ui.storage_view import StorageAnalysisDialog
        StorageAnalysisDialog(self.current_path, self).exec()

    # ==================================================
    # Pasek narzędzi i menu
    # ==================================================
    def _build_toolbar(self) -> None:
        tb = QToolBar("Nawigacja", movable=False)
        self.addToolBar(tb)

        def act(text, slot, shortcut=None):
            a = QAction(text, self)
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

    def _build_menus(self) -> None:
        menu = self.menuBar().addMenu("&Plik")

        def add(text, slot, shortcut=None):
            a = QAction(text, self)
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
        menu.addSeparator()
        add("Klucze API chmur…", self._show_cloud_keys)
        menu.addSeparator()
        add("Zakończ", self.close, "Ctrl+Q")

    def _context_menu(self, pos) -> None:
        sel = self._selected()
        menu = QMenu(self)
        if sel:
            menu.addAction("Otwórz", lambda: self._open_item(sel[0]))
            menu.addAction("Zmień nazwę", self._rename_selected)
            menu.addSeparator()
            menu.addAction("Kopiuj", lambda: self._copy_selected(cut=False))
            menu.addAction("Wytnij", lambda: self._copy_selected(cut=True))
            menu.addAction("Usuń", self._delete_selected)
            menu.addSeparator()
            menu.addAction("Kompresuj do ZIP…", self._compress_selected)
            if len(sel) == 1 and archives.is_archive(sel[0].name):
                menu.addAction("Wypakuj…", self._extract_selected)
        else:
            menu.addAction("Nowy katalog", self._new_folder)
            menu.addAction("Wklej", self._paste,
                           enabled=bool(self._clipboard))
            menu.addSeparator()
            menu.addAction("Odśwież", self._refresh)
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
