"""Wbudowana przeglądarka obrazów (jak w FM+) z zoomem i obracaniem."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QTransform
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from core.fs_base import FileSystemProvider


class ImageViewerDialog(QDialog):
    def __init__(self, provider: FileSystemProvider, path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(path.rsplit("/", 1)[-1])
        self.resize(900, 650)

        self._rotation = 0
        self._scale = 1.0

        self._label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._label.setMinimumSize(200, 200)
        scroll = QScrollArea(widgetResizable=True)
        scroll.setWidget(self._label)

        btn_zoom_in = QPushButton("＋")
        btn_zoom_out = QPushButton("－")
        btn_fit = QPushButton("Dopasuj")
        btn_rotate = QPushButton("Obróć")
        btn_zoom_in.clicked.connect(lambda: self._zoom(1.25))
        btn_zoom_out.clicked.connect(lambda: self._zoom(0.8))
        btn_fit.clicked.connect(self._fit)
        btn_rotate.clicked.connect(self._rotate)

        bar = QHBoxLayout()
        for b in (btn_zoom_in, btn_zoom_out, btn_fit, btn_rotate):
            bar.addWidget(b)
        bar.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(scroll, 1)
        layout.addLayout(bar)

        try:
            with provider.open_read(path) as f:
                data = f.read()
            self._pixmap = QPixmap()
            self._pixmap.loadFromData(data)
            if self._pixmap.isNull():
                raise ValueError("nieobsługiwany format")
            self._fit()
        except Exception as exc:
            self._label.setText(f"Nie można wyświetlić obrazu:\n{exc}")

    def _render(self) -> None:
        if not hasattr(self, "_pixmap") or self._pixmap.isNull():
            return
        pm = self._pixmap.transformed(QTransform().rotate(self._rotation))
        self._label.setPixmap(pm.scaled(
            pm.size() * self._scale,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    def _zoom(self, factor: float) -> None:
        self._scale = max(0.05, min(self._scale * factor, 20.0))
        self._render()

    def _fit(self) -> None:
        if not hasattr(self, "_pixmap") or self._pixmap.isNull():
            return
        area = self.size()
        w = max(area.width() - 60, 100)
        h = max(area.height() - 140, 100)
        self._scale = min(w / self._pixmap.width(), h / self._pixmap.height(), 1.0)
        self._render()

    def _rotate(self) -> None:
        self._rotation = (self._rotation + 90) % 360
        self._render()
