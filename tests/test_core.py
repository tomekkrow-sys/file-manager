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
