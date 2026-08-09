"""Provider lokalnego systemu plików."""

from __future__ import annotations

import mimetypes
import os
import shutil
import stat as statmod
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from core.fs_base import (
    FileInfo,
    FileSystemError,
    FileSystemProvider,
    FileType,
    ProgressCallback,
    copy_stream,
)


class LocalFileSystem(FileSystemProvider):
    scheme = "file"

    def __init__(self, root: str = "/"):
        self._root = Path(root)

    def display_name(self) -> str:
        return "Pamięć lokalna"

    def root_path(self) -> str:
        return str(self._root)

    # ----- mapowanie ścieżek -----
    def _to_native(self, path: str) -> Path:
        return Path(path)

    def _info(self, p: Path) -> FileInfo:
        try:
            st = p.lstat()
        except OSError as exc:
            raise FileSystemError(f"Brak dostępu: {p} ({exc.strerror})") from exc

        if statmod.S_ISDIR(st.st_mode):
            ftype = FileType.DIRECTORY
        elif statmod.S_ISLNK(st.st_mode):
            ftype = FileType.SYMLINK
        else:
            ftype = FileType.FILE

        mime = "inode/directory" if ftype is FileType.DIRECTORY else (
            mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        )
        return FileInfo(
            name=p.name or str(p),
            path=str(p),
            type=ftype,
            size=0 if ftype is FileType.DIRECTORY else st.st_size,
            modified=datetime.fromtimestamp(st.st_mtime),
            mime=mime,
            hidden=p.name.startswith("."),
        )

    # ----- API -----
    def list_dir(self, path: str) -> Iterator[FileInfo]:
        native = self._to_native(path)
        try:
            with os.scandir(native) as it:
                entries = sorted(it, key=lambda e: (not e.is_dir(follow_symlinks=False),
                                                    e.name.lower()))
                for entry in entries:
                    try:
                        yield self._info(Path(entry.path))
                    except FileSystemError:
                        continue  # pomijamy pozycje bez dostępu
        except OSError as exc:
            raise FileSystemError(f"Nie można otworzyć katalogu: {path} ({exc.strerror})") from exc

    def stat(self, path: str) -> FileInfo:
        return self._info(self._to_native(path))

    def mkdir(self, path: str) -> None:
        try:
            self._to_native(path).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise FileSystemError(f"Nie można utworzyć katalogu: {path} ({exc.strerror})") from exc

    def delete(self, path: str, progress: Optional[ProgressCallback] = None) -> None:
        native = self._to_native(path)
        try:
            if native.is_dir() and not native.is_symlink():
                shutil.rmtree(native)
            else:
                native.unlink()
        except OSError as exc:
            raise FileSystemError(f"Nie można usunąć: {path} ({exc.strerror})") from exc

    def rename(self, path: str, new_name: str) -> None:
        native = self._to_native(path)
        try:
            native.rename(native.with_name(new_name))
        except OSError as exc:
            raise FileSystemError(f"Nie można zmienić nazwy: {path} ({exc.strerror})") from exc

    def copy(self, src: FileSystemProvider, src_path: str,
             dst_path: str, progress: Optional[ProgressCallback] = None) -> None:
        dst_native = self._to_native(dst_path)
        src_info = src.stat(src_path)

        if src_info.is_dir:
            dst_native.mkdir(parents=True, exist_ok=True)
            for child in src.list_dir(src_path):
                self.copy(src, child.path, str(dst_native / child.name), progress)
            return

        # Szybka ścieżka: lokalne -> lokalne
        if isinstance(src, LocalFileSystem):
            dst_native.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_native)
            if progress:
                progress(src_info.size, src_info.size, src_path)
            return

        dst_native.parent.mkdir(parents=True, exist_ok=True)
        copy_stream(src, src_path, self, dst_path, progress,
                    total=src_info.size)

    def move(self, dst: FileSystemProvider, src_path: str,
             dst_path: str, progress: Optional[ProgressCallback] = None) -> None:
        if isinstance(dst, LocalFileSystem):
            try:
                Path(dst_path).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(src_path, dst_path)
                return
            except OSError as exc:
                raise FileSystemError(f"Nie można przenieść: {src_path} ({exc.strerror})") from exc
        super().move(dst, src_path, dst_path, progress)

    def open_read(self, path: str):
        try:
            return open(self._to_native(path), "rb")
        except OSError as exc:
            raise FileSystemError(f"Nie można odczytać: {path} ({exc.strerror})") from exc

    def open_write(self, path: str):
        try:
            native = self._to_native(path)
            native.parent.mkdir(parents=True, exist_ok=True)
            return open(native, "wb")
        except OSError as exc:
            raise FileSystemError(f"Nie można zapisać: {path} ({exc.strerror})") from exc
