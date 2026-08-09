"""Provider SFTP (przez SSH, port 22) oparty o paramiko."""

from __future__ import annotations

import mimetypes
import stat as statmod
from datetime import datetime
from typing import Iterator, Optional

import paramiko

from core.fs_base import (
    FileInfo,
    FileSystemError,
    FileSystemProvider,
    FileType,
    ProgressCallback,
    copy_stream,
)


class SftpFileSystem(FileSystemProvider):
    scheme = "sftp"

    def __init__(self, host: str, port: int = 22,
                 user: str = "", password: str = "",
                 timeout: int = 15):
        self.host, self.port = host, port
        self._user, self._password = user, password
        self._timeout = timeout
        self._ssh: Optional[paramiko.SSHClient] = None
        self._sftp: Optional[paramiko.SFTPClient] = None
        self._connect()

    def display_name(self) -> str:
        return f"SSH: {self.host}"

    def _connect(self) -> None:
        try:
            self._ssh = paramiko.SSHClient()
            # Accept-new: pierwszy kontakt akceptuje klucz hosta (jak OpenSSH)
            self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._ssh.connect(
                self.host, port=self.port,
                username=self._user or None,
                password=self._password or None,
                timeout=self._timeout,
                look_for_keys=True,   # spróbuje też kluczy z ~/.ssh
                allow_agent=True,     # i ssh-agent
            )
            self._sftp = self._ssh.open_sftp()
        except paramiko.AuthenticationException as exc:
            raise FileSystemError(
                f"SSH {self.host}: błąd uwierzytelnienia — "
                "sprawdź użytkownika/hasło lub klucz SSH.") from exc
        except (paramiko.SSHException, OSError) as exc:
            raise FileSystemError(
                f"Nie można połączyć z SSH {self.host}:{self.port}: {exc}") from exc

    def _ensure(self) -> paramiko.SFTPClient:
        assert self._sftp is not None
        return self._sftp

    def _info(self, path: str, attr: paramiko.SFTPAttributes) -> FileInfo:
        name = path.rstrip("/").rsplit("/", 1)[-1] or path
        is_dir = statmod.S_ISDIR(attr.st_mode or 0)
        is_link = statmod.S_ISLNK(attr.st_mode or 0)
        ftype = (FileType.DIRECTORY if is_dir
                 else FileType.SYMLINK if is_link else FileType.FILE)
        return FileInfo(
            name=name,
            path=path,
            type=ftype,
            size=0 if is_dir else (attr.st_size or 0),
            modified=(datetime.fromtimestamp(attr.st_mtime)
                      if attr.st_mtime else None),
            mime="inode/directory" if is_dir else (
                mimetypes.guess_type(name)[0] or "application/octet-stream"),
            hidden=name.startswith("."),
        )

    # ----- API -----
    def list_dir(self, path: str) -> Iterator[FileInfo]:
        sftp = self._ensure()
        try:
            attrs = sftp.listdir_attr(path or "/")
        except (OSError, paramiko.SSHException) as exc:
            raise FileSystemError(f"Nie można odczytać katalogu SSH: {path} ({exc})") from exc

        infos = []
        for attr in attrs:
            if attr.filename in (".", ".."):
                continue
            full = f"{(path or '/').rstrip('/')}/{attr.filename}"
            infos.append(self._info(full, attr))
        yield from sorted(infos, key=lambda i: (not i.is_dir, i.name.lower()))

    def stat(self, path: str) -> FileInfo:
        try:
            return self._info(path, self._ensure().stat(path))
        except (OSError, paramiko.SSHException) as exc:
            raise FileSystemError(f"Ścieżka nie istnieje na SSH: {path} ({exc})") from exc

    def mkdir(self, path: str) -> None:
        sftp = self._ensure()
        current = ""
        try:
            for part in [p for p in path.split("/") if p]:
                current += "/" + part
                try:
                    sftp.mkdir(current)
                except OSError:
                    pass  # już istnieje
        except (OSError, paramiko.SSHException) as exc:
            raise FileSystemError(f"Nie można utworzyć katalogu SSH: {path} ({exc})") from exc

    def delete(self, path: str, progress: Optional[ProgressCallback] = None) -> None:
        sftp = self._ensure()
        try:
            info = self.stat(path)
            if info.is_dir:
                for child in self.list_dir(path):
                    self.delete(child.path, progress)
                sftp.rmdir(path)
            else:
                sftp.remove(path)
        except FileSystemError:
            raise
        except (OSError, paramiko.SSHException) as exc:
            raise FileSystemError(f"Nie można usunąć na SSH: {path} ({exc})") from exc

    def rename(self, path: str, new_name: str) -> None:
        parent = self.parent(path) or "/"
        try:
            self._ensure().rename(path, f"{parent.rstrip('/')}/{new_name}")
        except (OSError, paramiko.SSHException) as exc:
            raise FileSystemError(f"Nie można zmienić nazwy na SSH: {exc}") from exc

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
        try:
            return self._ensure().open(path, "rb")
        except (OSError, paramiko.SSHException) as exc:
            raise FileSystemError(f"Nie można odczytać z SSH: {path} ({exc})") from exc

    def open_write(self, path: str):
        parent = self.parent(path)
        if parent and parent != "/":
            self.mkdir(parent)
        try:
            return self._ensure().open(path, "wb")
        except (OSError, paramiko.SSHException) as exc:
            raise FileSystemError(f"Nie można zapisać na SSH: {path} ({exc})") from exc

    def disconnect(self) -> None:
        if self._sftp:
            self._sftp.close()
            self._sftp = None
        if self._ssh:
            self._ssh.close()
            self._ssh = None
