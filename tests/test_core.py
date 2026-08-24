"""Testy jednostkowe warstwy core (bez sieci — local + archiwa + operacje)."""

from __future__ import annotations

import os
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import archives
from core.fs_base import FileSystemError, FileType
from core.local_fs import LocalFileSystem
from core.storage_analysis import categorize, human_size


# ---------- LocalFileSystem ----------

@pytest.fixture()
def fs(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "raport.txt").write_text("zażółć gęślą jaźń", encoding="utf-8")
    (tmp_path / "foto.jpg").write_bytes(b"\xff\xd8fake-jpeg")
    (tmp_path / ".ukryty").write_text("x")
    return LocalFileSystem()


def test_list_dir_sorted_dirs_first(fs, tmp_path):
    items = list(fs.list_dir(str(tmp_path)))
    names = [i.name for i in items]
    assert names[0] == ".ukryty" or "docs" in names
    # katalogi przed plikami
    dirs = [i for i in items if i.is_dir]
    assert dirs and dirs[0].name == "docs"
    assert all(items.index(d) < items.index(f)
               for d in dirs for f in items if not f.is_dir)


def test_stat_file(fs, tmp_path):
    info = fs.stat(str(tmp_path / "docs" / "raport.txt"))
    assert info.type is FileType.FILE
    assert info.size > 0
    assert info.mime == "text/plain"


def test_mkdir_rename_delete(fs, tmp_path):
    fs.mkdir(str(tmp_path / "a" / "b" / "c"))
    assert (tmp_path / "a" / "b" / "c").is_dir()

    fs.rename(str(tmp_path / "foto.jpg"), "zdjecie.jpg")
    assert (tmp_path / "zdjecie.jpg").exists()

    fs.delete(str(tmp_path / "a"))
    assert not (tmp_path / "a").exists()
    with pytest.raises(FileSystemError):
        fs.delete(str(tmp_path / "nie_ma_takiego"))


def test_copy_local_to_local(fs, tmp_path):
    src = str(tmp_path / "docs" / "raport.txt")
    dst_dir = tmp_path / "backup"
    fs.copy(fs, src, str(dst_dir / "raport.txt"))
    assert (dst_dir / "raport.txt").read_text(encoding="utf-8").startswith("zażółć")


def test_copy_directory_recursive(fs, tmp_path):
    fs.copy(fs, str(tmp_path / "docs"), str(tmp_path / "docs_copy"))
    assert (tmp_path / "docs_copy" / "raport.txt").exists()


def test_move(fs, tmp_path):
    fs.move(fs, str(tmp_path / "foto.jpg"), str(tmp_path / "docs" / "foto.jpg"))
    assert (tmp_path / "docs" / "foto.jpg").exists()
    assert not (tmp_path / "foto.jpg").exists()


def test_copy_self_raises_clean_error(fs, tmp_path):
    """Kopiowanie na siebie ma dać FileSystemError, a nie zawiesić wątek."""
    f = tmp_path / "docs" / "raport.txt"
    with pytest.raises(FileSystemError, match="skopiować"):
        fs.copy(fs, str(f), str(f))


def test_copy_dir_into_own_subtree_raises(fs, tmp_path):
    """Katalog nie może być skopiowany w swój podkatalog (nieskończona pętla)."""
    with pytest.raises(FileSystemError, match="do samego siebie"):
        fs.copy(fs, str(tmp_path / "docs"), str(tmp_path / "docs" / "pod"))


def test_copy_operation_reports_errors_and_finishes(fs, tmp_path):
    """Nieudana pozycja kończy operację finished_all z błędem (zamiast wieszać UI)."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from core.operations import CopyOperation

    f = tmp_path / "docs" / "raport.txt"
    op = CopyOperation([(fs, str(f)), (fs, str(f))], fs, str(tmp_path / "docs"),
                        None)
    result = []
    # DirectConnection — slot wykonuje się w wątku roboczym, wynik gotowy po wait()
    op.finished_all.connect(
        lambda ok, err: result.append((ok, err)),
        Qt.ConnectionType.DirectConnection)
    op.start()
    assert op.wait(5000)
    assert op.isFinished()
    assert result == [(0, 2)]  # obie pozycje zgłoszone jako błędy, bez wiszącego wątku


def test_parent(fs):
    assert fs.parent("/a/b/c") == "/a/b"
    assert fs.parent("/a") == "/"
    assert fs.parent("/") is None


# ---------- Archiwa ----------

def test_zip_roundtrip(tmp_path):
    src = tmp_path / "dane"
    src.mkdir()
    (src / "a.txt").write_text("AAA", encoding="utf-8")
    (src / "b.txt").write_text("BBB", encoding="utf-8")

    out = tmp_path / "dane.zip"
    archives.compress_zip([str(src)], str(out))
    assert zipfile.is_zipfile(out)

    dest = tmp_path / "wypakowane"
    archives.extract(str(out), str(dest))
    assert (dest / "dane" / "a.txt").read_text() == "AAA"


def test_extract_tar_gz(tmp_path):
    src_file = tmp_path / "plik.txt"
    src_file.write_text("tar test", encoding="utf-8")
    tar_path = tmp_path / "paczka.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tf:
        tf.add(src_file, arcname="plik.txt")

    dest = tmp_path / "out"
    archives.extract(str(tar_path), str(dest))
    assert (dest / "plik.txt").read_text() == "tar test"


def test_extract_single_gz(tmp_path):
    import gzip
    gz_path = tmp_path / "log.txt.gz"
    with gzip.open(gz_path, "wb") as f:
        f.write(b"log content")
    archives.extract(str(gz_path), str(tmp_path / "out"))
    assert (tmp_path / "out" / "log.txt").read_bytes() == b"log content"


def test_zip_slip_protection(tmp_path):
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../../etc/evil.txt", "x")
    with pytest.raises(archives.ArchiveError):
        archives.extract(str(evil), str(tmp_path / "out"))


def test_is_archive():
    assert archives.is_archive("a.zip")
    assert archives.is_archive("b.TAR.GZ")
    assert not archives.is_archive("c.txt")


def test_list_archive(tmp_path):
    zp = tmp_path / "t.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("x.txt", "12345")
    entries = archives.list_archive(str(zp))
    assert entries == [("x.txt", 5)]


# ---------- Pomocnicze ----------

def test_human_size():
    assert human_size(512) == "512 B"
    assert human_size(2048) == "2.0 KB"
    assert human_size(5 * 1024**3) == "5.0 GB"


def test_categorize():
    assert categorize(Path("a.jpg")) == "Obrazy"
    assert categorize(Path("b.mp4")) == "Wideo"
    assert categorize(Path("c.pdf")) == "Dokumenty"
    assert categorize(Path("d.zip")) == "Archiwa"
    assert categorize(Path("e.bin")) == "Inne"


# ---------- FTP: obsługa błędów połączenia ----------

def test_ftp_connection_refused_gives_filesystemerror():
    """Odrzucone połączenie ma dać FileSystemError, a nie TypeError/crash."""
    from core.ftp_fs import FtpFileSystem
    with pytest.raises(FileSystemError, match="FTP"):
        FtpFileSystem("127.0.0.1", port=1, timeout=2)  # port 1 — nic nie nasłuchuje


def test_sftp_connection_refused_gives_filesystemerror():
    """To samo dla SFTP/SSH."""
    from core.sftp_fs import SftpFileSystem
    with pytest.raises(FileSystemError, match="SSH"):
        SftpFileSystem("127.0.0.1", port=1, timeout=2)


# ---------- Chmury: klucze i OAuth ----------

def test_has_app_keys_detects_placeholders(tmp_path, monkeypatch):
    from core.cloud import base
    keys_file = tmp_path / "cloud_keys.json"
    monkeypatch.setattr(base, "KEYS_FILE", keys_file)

    assert not base.has_app_keys("gdrive")  # plik nie istnieje

    base.save_app_keys({"gdrive": {"client_id": "WPISZ_CLIENT_ID",
                                   "client_secret": "WPISZ_SECRET"}})
    assert not base.has_app_keys("gdrive")  # placeholdery

    base.save_app_keys({"gdrive": {"client_id": "123.apps.googleusercontent.com",
                                   "client_secret": "GOCSPX-real"}})
    assert base.has_app_keys("gdrive")  # prawdziwe klucze


def test_oauth_cancel_event(tmp_path, monkeypatch):
    """Anulowanie podczas oczekiwania przerywa przepływ OAuth."""
    import threading
    from core.cloud import base

    cancel = threading.Event()
    cancel.set()  # od razu anulowane
    monkeypatch.setattr(base, "webbrowser", type("W", (), {"open": staticmethod(lambda u: True)}))
    monkeypatch.setattr(base, "REDIRECT_PORT", 18765)  # wolny port testowy

    with pytest.raises(FileSystemError, match="anulowane"):
        base.oauth2_authorize("https://example.com/auth", {"client_id": "x"},
                              cancel_event=cancel)


# ---------- Zbiory mediów ----------

def test_media_browse_session_navigation():
    from core.media_collections import MediaBrowseSession

    paths = ["/a/1.jpg", "/a/2.jpg", "/a/3.jpg"]
    s = MediaBrowseSession(paths, "/a/2.jpg")
    assert s.current() == "/a/2.jpg"
    assert s.next() == "/a/3.jpg"
    assert s.next() is None          # koniec listy
    assert s.prev() == "/a/2.jpg"
    assert s.prev() == "/a/1.jpg"
    assert s.prev() is None          # początek listy
    assert s.first() == "/a/1.jpg"
    assert len(s) == 3

    # startowa ścieżka poza listą -> indeks 0
    s2 = MediaBrowseSession(paths, "/brak/pliku.jpg")
    assert s2.current() == "/a/1.jpg"


def test_image_viewer_close_goes_to_previous(tmp_path):
    """X na przeglądarce zdjęć wraca do poprzedniego; na pierwszym zamyka."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])

    from core.local_fs import LocalFileSystem
    from core.media_collections import MediaBrowseSession
    from ui.viewers.image_viewer import ImageViewerDialog

    imgs = []
    for i in range(3):
        p = tmp_path / f"f{i}.png"
        im = QImage(10, 10, QImage.Format.Format_RGB32)
        im.fill(0xFFFFFF)
        im.save(str(p))
        imgs.append(str(p))

    s = MediaBrowseSession(imgs, imgs[1])
    dlg = ImageViewerDialog(LocalFileSystem(), imgs[1], browse=s)
    dlg.show()
    dlg.close()                       # X -> powrót do poprzedniego
    assert dlg.windowTitle() == "f0.png"
    assert not dlg.isHidden()
    dlg.close()                       # na pierwszym X zamyka
    assert dlg.isHidden()


def test_media_collector_groups_by_collection(tmp_path, monkeypatch):
    """Pliki trafiają do właściwych zbiorów; inne i ukryte są pomijane."""
    from core import media_collections
    from core.media_collections import MediaCollector

    (tmp_path / "muzyka").mkdir()
    (tmp_path / "muzyka" / "utwor.mp3").write_bytes(b"\x00" * 5)
    (tmp_path / "film.mp4").write_bytes(b"\x00" * 10)
    (tmp_path / "zdjecia").mkdir()
    (tmp_path / "zdjecia" / "foto.png").write_bytes(b"\x00" * 7)
    (tmp_path / "raport.txt").write_text("x")
    (tmp_path / "dane.bin").write_bytes(b"\x00" * 3)      # "Inne" — pominięte
    (tmp_path / ".ukryty.mp3").write_bytes(b"\x00" * 2)   # ukryty — pominięty

    monkeypatch.setattr(media_collections, "virtual_mount_points", lambda: set())
    collector = MediaCollector([str(tmp_path)])
    batches = {}
    collector.disk_finished.connect(batches.update)
    collector.run()

    def names(collection):
        return {n for n, s, p in batches.get(collection, [])}

    assert names("Muzyka") == {"utwor.mp3"}
    assert names("Wideo") == {"film.mp4"}
    assert names("Zdjęcia") == {"foto.png"}
    assert names("Dokumenty") == {"raport.txt"}

    all_names = {n for entries in batches.values() for n, s, p in entries}
    assert "dane.bin" not in all_names
    assert ".ukryty.mp3" not in all_names
    # rozmiary zapamiętane
    muzyka = next(entries for entries in batches["Muzyka"])
    assert muzyka[1] == 5


def test_media_collector_skips_nonregular_and_dedup(tmp_path, monkeypatch):
    """Pliki niebędące zwykłymi plikami są pomijane, powtórki usuwane."""
    import os
    from core import media_collections
    from core.media_collections import MediaCollector

    (tmp_path / "a.mp3").write_bytes(b"\x00" * 4)
    os.symlink(tmp_path / "a.mp3", tmp_path / "link.mp3")

    monkeypatch.setattr(media_collections, "virtual_mount_points", lambda: set())
    # ten sam katalog podany dwa razy — plik liczony raz
    collector = MediaCollector([str(tmp_path), str(tmp_path)])
    batches = {}
    collector.disk_finished.connect(batches.update)
    collector.run()

    muzyka = batches.get("Muzyka", [])
    assert {n for n, s, p in muzyka} == {"a.mp3"}


# ---------- Analiza pamięci: pomijanie pseudosystemów (/proc/kcore) ----------

def test_list_disks_filters_virtual_and_ssh(tmp_path, monkeypatch):
    """Lista dysków: pseudosystemy pominięte, SSH tylko po włączeniu opcji."""
    from core import storage_analysis
    from core.storage_analysis import list_disks

    mounts_file = tmp_path / "mounts"
    mounts_file.write_text(
        "/dev/sda1 / ext4 rw 0 0\n"
        "proc /proc proc rw 0 0\n"
        "tmpfs /dev/shm tmpfs rw 0 0\n"
        "user@10.0.0.5:/home/user /mnt/ssh fuse.sshfs rw 0 0\n"
        "/dev/sda2 /home ext4 rw 0 0\n")

    class FakeStatvfs:
        def __init__(self, total, free):
            self.f_frsize = 1
            self.f_blocks = total
            self.f_bavail = free

    monkeypatch.setattr(
        storage_analysis, "_statvfs",
        lambda path: FakeStatvfs(1000, 250) if path == "/"
        else FakeStatvfs(400, 100))

    disks = list_disks(mounts_file=str(mounts_file))
    # /proc i /dev/shm (wirtualne) oraz sshfs pominięte
    assert [d.mountpoint for d in disks] == ["/", "/home"]
    root = next(d for d in disks if d.mountpoint == "/")
    assert (root.total, root.used, root.free) == (1000, 750, 250)

    disks_ssh = list_disks(include_ssh=True, mounts_file=str(mounts_file))
    ssh = next(d for d in disks_ssh if d.mountpoint == "/mnt/ssh")
    assert ssh.fstype == "fuse.sshfs"
    assert (ssh.total, ssh.used, ssh.free) == (400, 300, 100)


def test_disk_directory_scanner_top_level(tmp_path, monkeypatch):
    """Skaner liczy tylko katalogi top-level (bez ukrytych i plików)."""
    from core import storage_analysis
    from core.storage_analysis import DiskDirectoryScanner

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.txt").write_text("aaaa")
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "b.bin").write_bytes(b"\x00" * 10)
    hidden = tmp_path / ".cache"
    hidden.mkdir()
    (hidden / "x").write_text("x")
    (tmp_path / "plik.txt").write_text("zzz")  # plik na poziomie 0 — pomijany

    monkeypatch.setattr(storage_analysis, "virtual_mount_points", lambda: set())
    scanner = DiskDirectoryScanner(str(tmp_path))
    dirs = {}
    scanner.dir_size.connect(lambda n, s: dirs.__setitem__(n, s))
    scanner.run()
    assert dirs == {"docs": 4, "media": 10}


def test_disk_directory_scanner_skips_other_mount(tmp_path, monkeypatch):
    """Katalog będący osobnym dyskiem jest zgłaszany, ale nie skanowany."""
    from core import storage_analysis
    from core.storage_analysis import DiskDirectoryScanner

    other = tmp_path / "inne_dysk"
    other.mkdir()
    (other / "big").write_bytes(b"\x00" * 999)
    own = tmp_path / "wlasne"
    own.mkdir()
    (own / "f").write_text("x")

    monkeypatch.setattr(storage_analysis, "virtual_mount_points", lambda: set())
    scanner = DiskDirectoryScanner(str(tmp_path),
                                   skip_mountpoints={str(other)})
    dirs = {}
    skipped = []
    scanner.dir_size.connect(lambda n, s: dirs.__setitem__(n, s))
    scanner.skipped_mount.connect(skipped.append)
    scanner.run()
    assert dirs == {"wlasne": 1}
    assert skipped == ["inne_dysk"]


def test_is_virtual_mount():
    from core.storage_analysis import is_virtual_mount
    mounts = {"/proc", "/sys"}
    assert is_virtual_mount("/proc", mounts)
    assert is_virtual_mount("/proc/", mounts)      # końcowy ukośnik nie szkodzi
    assert is_virtual_mount("/sys", mounts)
    assert not is_virtual_mount("/home/user", mounts)
    assert not is_virtual_mount("/proc", set())    # brak mountów -> False


def test_storage_analyzer_skips_virtual_root(tmp_path, monkeypatch):
    """Analiza samego /proc (lub innego pseudosystemu) nie liczy niczego."""
    from core import storage_analysis
    from core.storage_analysis import StorageAnalyzer

    monkeypatch.setattr(storage_analysis, "virtual_mount_points",
                        lambda: {str(tmp_path)})
    analyzer = StorageAnalyzer(str(tmp_path))
    results = []
    analyzer.finished_scan.connect(
        lambda cat, large, total: results.append((cat, large, total)))
    analyzer.run()
    by_category, largest, total = results[0]
    assert total == 0
    assert largest == []


def test_storage_analyzer_skips_virtual_subdir(tmp_path, monkeypatch):
    """Katalog pseudosystemu jest pomijany — /proc/kcore nie fałszuje analizy."""
    from core import storage_analysis
    from core.storage_analysis import StorageAnalyzer

    virtual = tmp_path / "proc"
    virtual.mkdir()
    (virtual / "kcore").write_bytes(b"\x00" * (1024 * 1024))  # "wielki" plik
    normal = tmp_path / "dokumenty"
    normal.mkdir()
    (normal / "raport.txt").write_text("x", encoding="utf-8")

    monkeypatch.setattr(storage_analysis, "virtual_mount_points",
                        lambda: {str(virtual)})
    analyzer = StorageAnalyzer(str(tmp_path))
    results = []
    analyzer.finished_scan.connect(
        lambda cat, large, total: results.append((cat, large, total)))
    analyzer.run()
    by_category, largest, total = results[0]
    assert total == 1  # tylko raport.txt
    assert not any("kcore" in p for _, p in largest)


# ---------- Zapisane połączenia ----------

def test_connections_save_overwrite_remove(tmp_path, monkeypatch):
    from core import connections
    monkeypatch.setattr(connections, "CONNECTIONS_FILE",
                        tmp_path / "connections.json")
    assert connections.get_connections("sftp") == []

    connections.save_connection("sftp", {"name": "serwer", "host": "1.2.3.4",
                                         "port": 22, "user": "root"})
    conns = connections.get_connections("sftp")
    assert len(conns) == 1 and conns[0]["host"] == "1.2.3.4"

    # ta sama nazwa = nadpisanie, bez duplikatów
    connections.save_connection("sftp", {"name": "serwer", "host": "9.9.9.9"})
    conns = connections.get_connections("sftp")
    assert len(conns) == 1 and conns[0]["host"] == "9.9.9.9"

    # pusta nazwa jest ignorowana
    connections.save_connection("sftp", {"name": "", "host": "x"})
    assert len(connections.get_connections("sftp")) == 1

    connections.remove_connection("sftp", "serwer")
    assert connections.get_connections("sftp") == []


def test_get_all_connections(tmp_path, monkeypatch):
    from core import connections
    monkeypatch.setattr(connections, "CONNECTIONS_FILE",
                        tmp_path / "connections.json")
    connections.save_connection("sftp", {"name": "a", "host": "1"})
    connections.save_connection("ftp", {"name": "b", "host": "2"})
    kinds = [k for k, _ in connections.get_all_connections()]
    assert kinds == ["ftp", "sftp"]  # ustalona kolejność typów


def test_provider_params_filters_extras():
    from core.connections import provider_params
    raw = {"host": "h", "port": 22, "user": "u", "password": "x",
           "name": "n", "save": True, "save_password": False}
    assert provider_params("sftp", raw) == {"host": "h", "port": 22,
                                            "user": "u", "password": "x"}
    assert provider_params("ftp", raw) == {"host": "h", "port": 22,
                                           "user": "u", "password": "x"}
    assert provider_params("smb", raw) == {"host": "h", "user": "u",
                                           "password": "x"}


# ---------- Dialogi połączeń (smoke test UI) ----------

def test_connect_dialogs_smoke():
    """Dialogi FTP/SSH/NAS budują się i zwracają komplet parametrów."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from ui.dialogs import FtpConnectDialog, SftpConnectDialog, SmbConnectDialog

    dlg = SftpConnectDialog()
    dlg.host.setText("nas.local")
    dlg.user.setText("tomek")
    dlg.password.setText("sekret")
    dlg.save_box.setChecked(True)
    dlg.save_box.name.setText("mój serwer")
    dlg.save_box.save_password.setChecked(True)
    assert dlg.params() == {"host": "nas.local", "port": 22, "user": "tomek",
                            "password": "sekret", "name": "mój serwer",
                            "save": True, "save_password": True}

    dlg = SmbConnectDialog()
    dlg.host.setText("nas.local")
    assert dlg.params()["host"] == "nas.local"

    dlg = FtpConnectDialog()
    assert dlg.params()["save"] is False  # domyślnie bez zapisywania
    dlg.save_box.setChecked(True)
    assert dlg.params()["save"] is True


# ---------- Dwupanelowa wersja (smoke test UI) ----------

def test_transfer_highlight_in_model(tmp_path):
    """Podświetlenie wyników kopiowania/przenoszenia działa w modelu listy."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])

    from core.local_fs import LocalFileSystem
    from ui.file_list import (CLIPBOARD_COPY_COLOR, CLIPBOARD_CUT_COLOR,
                              FileListModel)

    fs = LocalFileSystem()
    (tmp_path / "a.txt").write_text("x")
    model = FileListModel()
    model.set_content(fs, list(fs.list_dir(str(tmp_path))))

    row = next(r for r in range(model.rowCount())
               if model.item_at(r).name == "a.txt")
    path = model.item_at(row).path

    model.set_transfer_highlight({path}, cut=False)
    brush = model.index(row, 0).data(Qt.ItemDataRole.BackgroundRole)
    assert brush is not None and brush.color() == CLIPBOARD_COPY_COLOR

    model.set_transfer_highlight({path}, cut=True)
    brush = model.index(row, 0).data(Qt.ItemDataRole.BackgroundRole)
    assert brush is not None and brush.color() == CLIPBOARD_CUT_COLOR

    model.clear_transfer_highlight()
    assert model.index(row, 0).data(Qt.ItemDataRole.BackgroundRole) is None

def test_dual_panel_window_smoke(tmp_path):
    """Dwupanelowe okno buduje się, ładuje oba panele i przełącza aktywny."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from ui.two_panel_window import DualPanelWindow

    win = DualPanelWindow()

    assert win.left.current_path == "/"
    assert win.right.current_path == str(Path.home())
    assert win._active is win.left

    # aktywacja po kliknięciu/zmianie zaznaczenia w prawym panelu
    win._set_active(win.right)
    assert win._active is win.right
    assert win._other() is win.left

    # przełączenie Tab-em przenosi aktywność na drugi panel
    # (focus wymaga pokazanego okna — tu testujemy sam przełącznik)
    win._switch_active()
    assert win._active is win.left

    # nawigacja do istniejącego katalogu
    win.right.navigate(str(tmp_path))
    assert win.right.current_path == str(tmp_path)

    win.close()
