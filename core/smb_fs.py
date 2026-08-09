"""Provider NAS/SMB oparty o smbprotocol (SMB2/3 — działa z nowoczesnymi NAS)."""

from __future__ import annotations

import mimetypes
from typing import Iterator, Optional

from smbclient import (
    ClientConfig,
    listdir,
    mkdir,
    open_file,
    register_session,
    remove,
    rmdir,
    rename,
    stat,
)
from smbprotocol.file_info import FileDirectoryInformation

from core.fs_base import (
    FileInfo,
    FileSystemError,
    FileSystemProvider,
    FileType,
    ProgressCallback,
    copy_stream,
)


class SmbFileSystem(FileSystemProvider):
    """
    Ścieżki w formacie: "/udział/katalog/plik" (bez hosta — host jest
    własnością połączenia, jak w reszcie providerów).
    """

    scheme = "smb"

    def __init__(self, host: str, user: str = "", password: str = "",
                 port: int = 445):
        self.host, self.port = host, port
        self._user, self._password = user, password
        ClientConfig(username=user or None, password=password or None)
        try:
            register_session(host, username=user or None,
                             password=password or None, port=port)
        except Exception as exc:  # smbprotocol rzuca różne typy
            raise FileSystemError(f"Nie można połączyć z NAS {host}: {exc}") from exc

    def display_name(self) -> str:
        return f"NAS: {self.host}"

    def _unc(self, path: str) -> str:
        return f"\\\\{self.host}{path.replace('/', '\\')}"

    def _info(self, path: str, st) -> FileInfo:
        from smbprotocol.file_info import FileAttributes
        name = path.rstrip("/").rsplit("/", 1)[-1] or path
        is_dir = bool(st.st_file_attributes & FileAttributes.FILE_ATTRIBUTE_DIRECTORY)
        return FileInfo(
            name=name,
            path=path,
            type=FileType.DIRECTORY if is_dir else FileType.FILE,
            size=0 if is_dir else st.st_size,
            mime="inode/directory" if is_dir else (
                mimetypes.guess_type(name)[0] or "application/octet-stream"),
            hidden=name.startswith("."),
        )

    # ----- API -----
    def list_dir(self, path: str) -> Iterator[FileInfo]:
        if path in ("", "/"):
            # korzeń = lista udziałów serwera
            from smbclient import list_shares
            try:
                for share in list_shares(self.host):
                    name = share.rstrip("$")
                    yield FileInfo(name=name, path=f"/{name}",
                                   type=FileType.DIRECTORY, mime="inode/directory")
                return
            except Exception as exc:
                raise FileSystemError(f"Nie można wylistować udziałów NAS: {exc}") from exc

        try:
            names = sorted(listdir(self._unc(path)), key=str.lower)
        except Exception as exc:
            raise FileSystemError(f"Nie można odczytać katalogu NAS: {path} ({exc})") from exc

        dirs, files = [], []
        for name in names:
            if name in (".", ".."):
                continue
            full = f"{path.rstrip('/')}/{name}"
            try:
                info = self._info(full, stat(self._unc(full)))
            except Exception:
                continue
            (dirs if info.is_dir else files).append(info)
        yield from dirs + files

    def stat(self, path: str) -> FileInfo:
        try:
            return self._info(path, stat(self._unc(path)))
        except Exception as exc:
            raise FileSystemError(f"Ścieżka nie istnieje na NAS: {path} ({exc})") from exc

    def mkdir(self, path: str) -> None:
        try:
            current = ""
            for part in [p for p in path.split("/") if p]:
                current += "/" + part
                try:
                    mkdir(self._unc(current))
                except Exception:
                    pass  # istnieje
        except Exception as exc:
            raise FileSystemError(f"Nie można utworzyć katalogu NAS: {path} ({exc})") from exc

    def delete(self, path: str, progress: Optional[ProgressCallback] = None) -> None:
        try:
            info = self.stat(path)
            if info.is_dir:
                for child in self.list_dir(path):
                    self.delete(child.path, progress)
                rmdir(self._unc(path))
            else:
                remove(self._unc(path))
        except FileSystemError:
            raise
        except Exception as exc:
            raise FileSystemError(f"Nie można usunąć z NAS: {path} ({exc})") from exc

    def rename(self, path: str, new_name: str) -> None:
        parent = self.parent(path) or "/"
        try:
            rename(self._unc(path), self._unc(f"{parent.rstrip('/')}/{new_name}"))
        except Exception as exc:
            raise FileSystemError(f"Nie można zmienić nazwy na NAS: {exc}") from exc

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
            return open_file(self._unc(path), mode="rb")
        except Exception as exc:
            raise FileSystemError(f"Nie można odczytać z NAS: {path} ({exc})") from exc

    def open_write(self, path: str):
        parent = self.parent(path)
        if parent and parent != "/":
            self.mkdir(parent)
        try:
            return open_file(self._unc(path), mode="wb")
        except Exception as exc:
            raise FileSystemError(f"Nie można zapisać na NAS: {path} ({exc})") from exc
