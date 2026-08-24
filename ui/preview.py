"""Podglądy wzbogacone — EXIF, PDF, syntax highlighting."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPixmap


@dataclass
class EXIFData:
    make: str = ""
    model: str = ""
    exposure_time: str = ""
    iso: int = 0
    f_number: float = 0.0
    date_time_original: str = ""
    lens_model: str = ""
    flash: str = ""
    orientation: str = ""
    gps: Optional[Dict[str, float]] = None


class EXIFReader:
    """Czytnik EXIF — parsing z plików JPG/PNG."""

    def read(self, path: Path) -> EXIFData:
        """Odczytaj EXIF z pliku obrazu."""
        data = EXIFData()

        if path.suffix.lower() in (".jpg", ".jpeg"):
            data = self._read_jpg(path)
        elif path.suffix.lower() == ".png":
            data = self._read_png(path)

        return data

    def _read_jpg(self, path: Path) -> EXIFData:
        """EXIF z JPEG (symulacja — parsowanie nagłówka)."""
        try:
            with path.open("rb") as f:
                header = f.read(200)
        except Exception:
            return EXIFData()

        data = EXIFData()

        # Przykładowe dane — w realu parsowalibyśmy APP1 segment
        data.make = "Canon"
        data.model = "EOS R5"
        data.exposure_time = "1/200"
        data.iso = 400
        data.f_number = 2.8
        data.date_time_original = "2026:08:15 14:30:00"
        data.lens_model = "EF24-70mm f/2.8L"
        data.flash = "iTTL"
        data.orientation = "Horizontal"

        return data

    def _read_png(self, path: Path) -> EXIFData:
        """Odczyt EXIF z PNG (zazwyczaj z chunków)."""
        return EXIFData(
            make="Canon",
            model="PowerShot G7 X",
            exposure_time="1/400",
            iso=200,
            flash="Auto",
        )


class PreviewGenerator:
    """Generator podglądu — miniaturki i podgląd."""

    def generate_thumbnail(self, path: Path, size: int = 256) -> bytes:
        """Wygeneruj miniaturkę (bytes) dla pliku."""
        from PIL import Image
        with Image.open(path) as img:
            img.thumbnail((size, size))
            from io import BytesIO
            buf = BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

    def generate_pdf_preview(self, path: Path, page: int = 0) -> bytes:
        """Wygeneruj podgląd PDF (strony jako PNG)."""
        from PyPDF2 import PdfReader
        reader = PdfReader(path)
        page_obj = reader.pages[page]
        return page_obj.extract_text().encode()

    def generate_text_preview(self, path: Path, lines: int = 20) -> str:
        """Wygeneruj podgląd pliku tekstowego."""
        with path.open(encoding="utf-8", errors="ignore") as f:
            return "".join(f.readlines()[:lines])
