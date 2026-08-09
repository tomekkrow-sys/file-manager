"""Provider FTP (klient) oparty o ftplib."""

from __future__ import annotations

import ftplib
import io
import mimetypes
from datetime import datetime
from typing import Iterator, Optional

from core.fs_base import (
    FileInfo,
    FileSystemError,
    FileSystemProvider,
    FileType,
    ProgressCallback,
    copy_stream,
)


class FtpFileSystem(FileSystemProvider):
    scheme = "ftp"

    def __init__(self, host: str, port: int = 21,
                 user: str = "anonymous", password: str = "",
                 timeout: int = 15):
        self.host, self.port = host, port
        self._user, self._password = user, password
        self._timeout = timeout
        self._ftp: Optional[ftplib.FTP] = None
        self._connect()

    def display_name(self) -> str:
        return f"FTP: {self.host}"

    def _connect(self) -> None:
        try:
            self._ftp = ftplib.FTP()
            self._ftp.connect(self.host, self.port, timeout=self._timeout)
            self._ftp.login(self._user, self._password)
        except (ftplib.all_errors, OSError) as exc:
            raise FileSystemError(f"Nie można połączyć z FTP {self.host}: {exc}") from exc

    def _ensure(self) -> ftplib.FTP:
        assert self._ftp is not None
        try:
            self._ftp.voidcmd("NOOP")
        except (ftplib.all_errors, OSError):
            self._connect()
        assert self._ftp is not None
        return self._ftp

    # ----- API -----
    def list_dir(self, path: str) -> Iterator[FileInfo]:
        ftp = self._ensure()
        entries: list[tuple[str, str]] = []
        try:
            ftp.retrlines(f"LIST {path}", lambda line: entries.append(_parse_list(line)))
        except ftplib.error_perm as exc:
            raise FileSystemError(f"Nie można odczytać katalogu FTP: {path} ({exc})") from exc
        except ftplib.all_errors as exc:
            raise FileSystemError(f"Błąd FTP: {exc}") from exc

        for name, raw in entries:
            if name in (".", ".."):
                continue
            is_dir = raw.startswith("d")
            size = _parse_size(raw)
            full = f"{path.rstrip('/')}/{name}"
            yield FileInfo(
                name=name,
                path=full,
                type=FileType.DIRECTORY if is_dir else FileType.FILE,
                size=0 if is_dir else size,
                modified=_parse_date(raw),
                mime="inode/directory" if is_dir else (
                    mimetypes.guess_type(name)[0] or "application/octet-stream"),
                hidden=name.startswith("."),
            )

    def stat(self, path: str) -> FileInfo:
        ftp = self._ensure()
        name = path.rstrip("/").rsplit("/", 1)[-1] or path
        try:
            size = ftp.size(path)
            return FileInfo(name=name, path=path, type=FileType.FILE, size=size or 0,
                            mime=mimetypes.guess_type(name)[0] or "application/octet-stream",
                            hidden=name.startswith("."))
        except ftplib.error_perm:
            pass
        try:
            ftp.cwd(path)
            ftp.cwd("/")
            return FileInfo(name=name, path=path, type=FileType.DIRECTORY,
                            mime="inode/directory", hidden=name.startswith("."))
        except ftplib.all_errors as exc:
            raise FileSystemError(f"Ścieżka nie istnieje na FTP: {path}") from exc

    def mkdir(self, path: str) -> None:
        ftp = self._ensure()
        current = ""
        try:
            for part in [p for p in path.split("/") if p]:
                current += "/" + part
                try:
                    ftp.mkd(current)
                except ftplib.error_perm:
                    pass  # katalog już istnieje
        except ftplib.all_errors as exc:
            raise FileSystemError(f"Nie można utworzyć katalogu FTP: {path} ({exc})") from exc

    def delete(self, path: str, progress: Optional[ProgressCallback] = None) -> None:
        ftp = self._ensure()
        try:
            ftp.delete(path)
            return
        except ftplib.error_perm:
            pass
        # katalog — usuń rekurencyjnie
        try:
            for child in list(self.list_dir(path)):
                self.delete(child.path, progress)
            ftp.rmd(path)
        except ftplib.all_errors as exc:
            raise FileSystemError(f"Nie można usunąć z FTP: {path} ({exc})") from exc

    def rename(self, path: str, new_name: str) -> None:
        ftp = self._ensure()
        parent = self.parent(path) or "/"
        try:
            ftp.rename(path, f"{parent.rstrip('/')}/{new_name}")
        except ftplib.all_errors as exc:
            raise FileSystemError(f"Nie można zmienić nazwy na FTP: {exc}") from exc

    def copy(self, src: FileSystemProvider, src_path: str,
             dst_path: str, progress: Optional[ProgressCallback] = None) -> None:
        src_info = src.stat(src_path)
        if src_info.is_dir:
            self.mkdir(dst_path)
            for child in src.list_dir(src_path):
                self.copy(src, child.path, f"{dst_path.rstrip('/')}/{child.name}", progress)
            return
        copy_stream(src, src_path, self, dst_path, progress, total=src_info.size)

    def open_read(self, path: str):
        ftp = self._ensure()
        buf = io.BytesIO()
        try:
            ftp.retrbinary(f"RETR {path}", buf.write)
        except ftplib.all_errors as exc:
            raise FileSystemError(f"Nie można pobrać z FTP: {path} ({exc})") from exc
        buf.seek(0)
        return _CtxWrapper(buf)

    def open_write(self, path: str):
        ftp = self._ensure()
        parent = self.parent(path)
        if parent:
            self.mkdir(parent)
        buf = io.BytesIO()
        return _FtpWriteCtx(ftp, path, buf)

    def disconnect(self) -> None:
        if self._ftp:
            try:
                self._ftp.quit()
            except ftplib.all_errors:
                pass
            self._ftp = None


class _CtxWrapper:
    def __init__(self, buf): self._buf = buf
    def __enter__(self): return self._buf
    def __exit__(self, *a): self._buf.close()


class _FtpWriteCtx:
    """Buforuje zapis i wysyła STOR przy zamknięciu."""
    def __init__(self, ftp: ftplib.FTP, path: str, buf: io.BytesIO):
        self._ftp, self._path, self._buf = ftp, path, buf

    def __enter__(self): return self._buf

    def __exit__(self, exc_type, *a):
        if exc_type is None:
            self._buf.seek(0)
            try:
                self._ftp.storbinary(f"STOR {self._path}", self._buf)
            except ftplib.all_errors as exc:
                raise FileSystemError(f"Nie można wysłać na FTP: {self._path} ({exc})") from exc
        self._buf.close()


# ----- parsowanie LIST (format Unix) -----

def _parse_list(line: str) -> tuple[str, str]:
    parts = line.split(None, 8)
    name = parts[8] if len(parts) >= 9 else ""
    return name, line


def _parse_size(line: str) -> int:
    try:
        return int(line.split(None, 8)[4])
    except (IndexError, ValueError):
        return 0


def _parse_date(line: str) -> Optional[datetime]:
    try:
        parts = line.split(None, 8)
        return datetime.strptime(" ".join(parts[5:8]), "%b %d %H:%M")
    except (IndexError, ValueError):
        return None
