"""Wbudowana przeglądarka obrazów (jak w FM+) z zoomem, obracaniem
oraz nawigacją (←/→) i auto-oglądaniem, gdy podano sesję ``browse``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut, QTransform
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from core.fs_base import FileSystemProvider

_AUTO_INTERVAL_MS = 4000


class ImageViewerDialog(QDialog):
    def __init__(self, provider: FileSystemProvider, path: str, parent=None,
                 browse=None):
        super().__init__(parent)
        self._provider = provider
        self._browse = browse
        self._force_close_flag = False
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
        if browse is not None:
            btn_prev = QPushButton("◀ Poprzednie")
            btn_prev.clicked.connect(self._prev_item)
            btn_next = QPushButton("Następne ▶")
            btn_next.clicked.connect(self._next_item)
            bar.addWidget(btn_prev)
            bar.addWidget(btn_next)
            self._auto_btn = QPushButton("▶ Auto")
            self._auto_btn.setCheckable(True)
            self._auto_btn.clicked.connect(self._toggle_auto)
            bar.addWidget(self._auto_btn)
            self._auto_timer = QTimer(self)
            self._auto_timer.setInterval(_AUTO_INTERVAL_MS)
            self._auto_timer.timeout.connect(self._auto_advance)
            btn_close = QPushButton("Zamknij")
            btn_close.clicked.connect(self._force_close)
            bar.addWidget(btn_close)
            QShortcut(QKeySequence(Qt.Key.Key_Right), self, self._next_item)
            QShortcut(QKeySequence(Qt.Key.Key_Left), self, self._prev_item)
        bar.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(scroll, 1)
        layout.addLayout(bar)

        self._load(path)

    def _load(self, path: str) -> None:
        self.setWindowTitle(path.rsplit("/", 1)[-1])
        self._pixmap = QPixmap()
        try:
            with self._provider.open_read(path) as f:
                data = f.read()
            if not self._pixmap.loadFromData(data):
                raise ValueError("nieobsługiwany format")
            self._rotation = 0
            self._scale = 1.0
            self._fit()
        except Exception as exc:
            self._label.setText(f"Nie można wyświetlić obrazu:\n{exc}")

    def _render(self) -> None:
        if self._pixmap.isNull():
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
        if self._pixmap.isNull():
            return
        area = self.size()
        w = max(area.width() - 60, 100)
        h = max(area.height() - 140, 100)
        self._scale = min(w / self._pixmap.width(), h / self._pixmap.height(), 1.0)
        self._render()

    def _rotate(self) -> None:
        self._rotation = (self._rotation + 90) % 360
        self._render()

    # ----- nawigacja po zbiorze -----

    def _next_item(self) -> None:
        if self._browse:
            path = self._browse.next()
            if path:
                self._load(path)

    def _prev_item(self) -> None:
        if self._browse:
            path = self._browse.prev()
            if path:
                self._load(path)

    def _auto_advance(self) -> None:
        if not self._browse:
            return
        path = self._browse.next() or self._browse.first()
        self._load(path)

    def _toggle_auto(self, checked: bool) -> None:
        if checked:
            if not self._browse or len(self._browse) < 2:
                self._auto_btn.setChecked(False)
                return
            self._auto_timer.start()
            self._auto_btn.setText("■ Stop")
        else:
            self._auto_timer.stop()
            self._auto_btn.setText("▶ Auto")

    def closeEvent(self, event) -> None:
        if getattr(self, "_auto_timer", None):
            self._auto_timer.stop()
        # X na pasku tytułu nie zamyka przeglądarki — wraca do poprzedniego
        # zdjęcia (Esc i przycisk „Zamknij” zamykają normalnie).
        if (self._browse is not None and not self._force_close_flag
                and self._browse.prev()):
            self._toggle_auto(False)
            event.ignore()
            self._load(self._browse.current())
            return
        super().closeEvent(event)

    def _force_close(self) -> None:
        self._force_close_flag = True
        self.close()

    def reject(self) -> None:
        self._force_close_flag = True
        super().reject()
