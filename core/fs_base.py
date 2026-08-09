"""
Abstrakcja systemu plików — wspólny kontrakt dla wszystkich backendów
(lokalny, FTP, SMB/NAS, chmury).

Inspirowane architekturą libfm (GVFS/FmFileInfo): każdy provider zwraca
obiekty FileInfo i implementuje ten sam zestaw operacji, dzięki czemu UI
nie wie, z jakim źródłem pracuje.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterator, Optional


class FileType(enum.Enum):
    FILE = "file"
    DIRECTORY = "directory"
    SYMLINK = "symlink"
    UNKNOWN = "unknown"


@dataclass
class FileInfo:
    """Metadane pojedynczego pliku/katalogu (odpowiednik FmFileInfo z libfm)."""

    name: str
    path: str                      # pełna ścieżka w przestrzeni providera
    type: FileType
    size: int = 0                  # bajty (0 dla katalogów)
    modified: Optional[datetime] = None
    mime: str = "application/octet-stream"
    hidden: bool = False

    @property
    def is_dir(self) -> bool:
        return self.type is FileType.DIRECTORY


# Postęp długich operacji: (przetworzone_bajty, całość_bajtów, bieżący_plik)
ProgressCallback = Callable[[int, int, str], None]


class FileSystemError(Exception):
    """Błąd operacji na systemie plików (czytelny komunikat dla UI)."""


class FileSystemProvider(ABC):
    """
    Wspólny interfejs backendów plików.

    Ścieżki są zawsze w formacie POSIX-owym wewnątrz providera
    (np. "/Dokumenty/foto.jpg"), niezależnie od platformy backendu.
    """

    #: krótki identyfikator schematu, np. "file", "ftp", "smb", "gdrive"
    scheme: str = "abstract"

    @abstractmethod
    def display_name(self) -> str:
        """Nazwa pokazywana w panelu źródeł."""

    @abstractmethod
    def list_dir(self, path: str) -> Iterator[FileInfo]:
        """Zwraca zawartość katalogu."""

    @abstractmethod
    def stat(self, path: str) -> FileInfo:
        """Metadane pojedynczego obiektu."""

    @abstractmethod
    def mkdir(self, path: str) -> None:
        """Tworzy katalog (wraz z rodzicami, jeśli to możliwe)."""

    @abstractmethod
    def delete(self, path: str, progress: Optional[ProgressCallback] = None) -> None:
        """Usuwa plik lub katalog (rekurencyjnie)."""

    @abstractmethod
    def rename(self, path: str, new_name: str) -> None:
        """Zmienia nazwę w obrębie tego samego katalogu."""

    @abstractmethod
    def copy(self, src: "FileSystemProvider", src_path: str,
             dst_path: str, progress: Optional[ProgressCallback] = None) -> None:
        """
        Kopiuje plik/katalog z innego (lub tego samego) providera.
        Implementacja domyślna w klasie bazowej — streaming przez open_read/open_write.
        """

    @abstractmethod
    def open_read(self, path: str):
        """Zwraca binarny strumień do odczytu (context manager)."""

    @abstractmethod
    def open_write(self, path: str):
        """Zwraca binarny strumień do zapisu (context manager)."""

    # ----- API opcjonalne -----

    def move(self, dst: "FileSystemProvider", src_path: str,
             dst_path: str, progress: Optional[ProgressCallback] = None) -> None:
        """Przenosi (domyślnie: copy + delete; providery mogą nadpisać)."""
        dst.copy(self, src_path, dst_path, progress)
        self.delete(src_path)

    def parent(self, path: str) -> Optional[str]:
        """Katalog nadrzędny lub None dla korzenia."""
        path = path.rstrip("/")
        if not path or path == "/":
            return None
        idx = path.rfind("/")
        return path[:idx] if idx > 0 else "/"

    def exists(self, path: str) -> bool:
        try:
            self.stat(path)
            return True
        except FileSystemError:
            return False

    def supports_trash(self) -> bool:
        return False

    def disconnect(self) -> None:
        """Sprzątanie połączenia (dla backendów sieciowych)."""


def copy_stream(src_provider: FileSystemProvider, src_path: str,
                dst_provider: FileSystemProvider, dst_path: str,
                progress: Optional[ProgressCallback] = None,
                total: int = 0, offset: int = 0,
                chunk_size: int = 256 * 1024) -> int:
    """
    Pomocnicza kopia strumieniowa między providerami
    (działa też dla transferów chmura -> FTP itd.).
    Zwraca liczbę skopiowanych bajtów.
    """
    done = offset
    with src_provider.open_read(src_path) as r, dst_provider.open_write(dst_path) as w:
        while True:
            chunk = r.read(chunk_size)
            if not chunk:
                break
            w.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total, src_path)
    return done - offset
