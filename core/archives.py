"""
Obsługa archiwów: kompresja do ZIP, dekompresja ZIP/TAR/GZ/XZ
(zakres zgodny z File Manager Plus; wzorowane na podejściu archivetools —
wyłącznie biblioteka standardowa Pythona).
"""

from __future__ import annotations

import gzip
import lzma
import os
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Callable, List, Optional

ProgressCallback = Callable[[int, int, str], None]

# Rozszerzenia rozpoznawane jako archiwa (do podglądu/wypakowania)
ARCHIVE_EXTENSIONS = {
    ".zip", ".tar", ".gz", ".tgz", ".tar.gz", ".xz", ".txz", ".tar.xz",
    ".tar.bz2", ".tbz2", ".bz2",
}


class ArchiveError(Exception):
    pass


def is_archive(path: str) -> bool:
    lower = path.lower()
    return any(lower.endswith(ext) for ext in ARCHIVE_EXTENSIONS)


def _report(progress: Optional[ProgressCallback], done: int, total: int, name: str) -> None:
    if progress:
        progress(done, total, name)


def compress_zip(sources: List[str], output: str,
                 progress: Optional[ProgressCallback] = None) -> None:
    """Pakuje pliki/katalogi do ZIP (deflate)."""
    total = sum(_tree_size(Path(s)) for s in sources)
    done = 0
    try:
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            for src in sources:
                base = Path(src)
                for file in _walk(base):
                    arcname = file.relative_to(base.parent)
                    zf.write(file, arcname)
                    done += file.stat().st_size
                    _report(progress, done, total, str(file))
    except (OSError, zipfile.BadZipFile) as exc:
        raise ArchiveError(f"Błąd kompresji do ZIP: {exc}") from exc


def extract(archive: str, output_dir: str,
            progress: Optional[ProgressCallback] = None) -> None:
    """Wypakowuje archiwum (ZIP/TAR/TAR.GZ/TAR.XZ/TAR.BZ2/GZ/XZ)."""
    path = Path(archive)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    lower = path.name.lower()

    try:
        if lower.endswith(".zip"):
            _extract_zip(path, out, progress)
        elif any(lower.endswith(e) for e in
                 (".tar", ".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar.bz2", ".tbz2")):
            _extract_tar(path, out, progress)
        elif lower.endswith(".gz"):
            _extract_single(path, out / path.stem, gzip.open, progress)
        elif lower.endswith(".xz"):
            _extract_single(path, out / path.stem, lzma.open, progress)
        elif lower.endswith(".bz2"):
            import bz2
            _extract_single(path, out / path.stem, bz2.open, progress)
        else:
            raise ArchiveError(f"Nieobsługiwany format archiwum: {path.name}")
    except ArchiveError:
        raise
    except (OSError, tarfile.TarError, zipfile.BadZipFile, EOFError) as exc:
        raise ArchiveError(f"Błąd dekompresji {path.name}: {exc}") from exc


def list_archive(archive: str) -> List[tuple[str, int]]:
    """Zwraca listę (nazwa, rozmiar) zawartości archiwum — do podglądu."""
    path = Path(archive)
    lower = path.name.lower()
    try:
        if lower.endswith(".zip"):
            with zipfile.ZipFile(path) as zf:
                return [(i.filename, i.file_size) for i in zf.infolist()]
        if any(lower.endswith(e) for e in
               (".tar", ".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar.bz2", ".tbz2")):
            with tarfile.open(path, "r:*") as tf:
                return [(m.name, m.size) for m in tf.getmembers()]
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        raise ArchiveError(f"Nie można odczytać archiwum: {exc}") from exc
    return []


# ----- wewnętrzne -----

def _walk(base: Path):
    if base.is_dir():
        for root, _, files in os.walk(base):
            for f in files:
                yield Path(root) / f
    else:
        yield base


def _tree_size(base: Path) -> int:
    return sum(f.stat().st_size for f in _walk(base) if f.is_file())


def _safe_target(out_dir: Path, member_name: str) -> Path:
    """Chroni przed path traversal (zip-slip)."""
    target = (out_dir / member_name).resolve()
    if not str(target).startswith(str(out_dir.resolve())):
        raise ArchiveError(f"Niebezpieczna ścieżka w archiwum: {member_name}")
    return target


def _extract_zip(path: Path, out: Path, progress: Optional[ProgressCallback]) -> None:
    with zipfile.ZipFile(path) as zf:
        infos = zf.infolist()
        total = sum(i.file_size for i in infos)
        done = 0
        for info in infos:
            target = _safe_target(out, info.filename)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as r, open(target, "wb") as w:
                shutil.copyfileobj(r, w)
            done += info.file_size
            _report(progress, done, total, info.filename)


def _extract_tar(path: Path, out: Path, progress: Optional[ProgressCallback]) -> None:
    with tarfile.open(path, "r:*") as tf:
        members = tf.getmembers()
        total = sum(m.size for m in members)
        done = 0
        for member in members:
            _safe_target(out, member.name)
            tf.extract(member, out, filter="data")
            done += member.size
            _report(progress, done, total, member.name)


def _extract_single(path: Path, target: Path, opener,
                    progress: Optional[ProgressCallback]) -> None:
    """Pojedynczy plik spakowany gz/xz/bz2 (bez struktury katalogów)."""
    total = path.stat().st_size
    with opener(path, "rb") as r, open(target, "wb") as w:
        shutil.copyfileobj(r, w)
    _report(progress, total, total, path.name)
