"""Batch operations — rename, convert, tagi."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from PySide6.QtWidgets import QProgressDialog

from core.fs_base import FileInfo, FileSystemProvider


def batch_rename(
    provider: FileSystemProvider,
    items: List[FileInfo],
    pattern: str,
) -> None:
    """Batch rename z wzorcem: [name], [ext], [num]."""
    for idx, info in enumerate(items, start=1):
        name = info.name
        ext = name.rsplit(".", 1)[-1] if "." in name else ""
        new_name = pattern\
            .replace("[name]", name)\
            .replace("[ext]", ext)\
            .replace("[num]", str(idx))
        provider.rename(info.path, new_name)


def batch_convert_images(
    provider: FileSystemProvider,
    items: List[FileInfo],
    target_format: str = "JPG",
) -> None:
    """Batch convert obrazów (symulacja — przemianowuje rozszerzenia)."""
    format_ext = {"JPG": "jpg", "PNG": "png", "WebP": "webp"}.get(target_format, "jpg")

    for info in items:
        if info.name.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")):
            stem = Path(info.name).stem
            new_name = f"{stem}.{format_ext}"
            provider.rename(info.path, new_name)


def batch_tag_items(
    provider: FileSystemProvider,
    items: List[FileInfo],
    tags: List[str],
) -> None:
    """Batch tagowanie plików."""
    for info in items:
        metadata_path = Path(info.path) / ".tags.json" if info.isdir else Path(info.path + ".tags.json")
        # TODO: zapisz tagi w metadata
        pass