"""Okno analizy pamięci — wykres kołowy kategorii + lista największych plików."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QProgressBar, QVBoxLayout, QWidget,
)

from core.storage_analysis import StorageAnalyzer, human_size

COLORS = {
    "Obrazy": "#4e9aef",
    "Wideo": "#cc0000",
    "Audio": "#f57900",
    "Dokumenty": "#73d216",
    "Archiwa": "#75507b",
    "Inne": "#888a85",
}


class _PieWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(240, 240)
        self._data: dict[str, int] = {}

    def set_data(self, data: dict[str, int]) -> None:
        self._data = data
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(12, 12, -12, -12)
        total = sum(self._data.values())
        if total == 0:
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Brak danych")
            return
        start = 0
        for category, size in sorted(self._data.items(),
                                     key=lambda x: x[1], reverse=True):
            span = int(size / total * 5760)  # 16 * 360
            painter.setBrush(QColor(COLORS.get(category, "#888a85")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPie(rect, start, span)
            start += span
        painter.end()


class StorageAnalysisDialog(QDialog):
    def __init__(self, root_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Analiza pamięci — {root_path}")
        self.resize(720, 520)

        self._pie = _PieWidget()
        self._legend = QListWidget(maximumWidth=260)
        self._largest = QListWidget()
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # busy
        self._status = QLabel("Skanowanie…")

        top = QHBoxLayout()
        top.addWidget(self._pie)
        top.addWidget(self._legend, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(top, 1)
        layout.addWidget(QLabel("Największe pliki:"))
        layout.addWidget(self._largest, 1)
        layout.addWidget(self._progress)
        layout.addWidget(self._status)

        self._analyzer = StorageAnalyzer(root_path, parent=self)
        self._analyzer.progressed.connect(
            lambda n, path: self._status.setText(f"Skanowanie… {n} plików"))
        self._analyzer.finished_scan.connect(self._on_finished)
        self._analyzer.start()

    def _on_finished(self, by_category: dict, largest: list, total: int) -> None:
        self._progress.setRange(0, 100)
        self._progress.setValue(100)
        self._status.setText(f"Całkowity rozmiar: {human_size(total)}")
        self._pie.set_data(by_category)

        self._legend.clear()
        for category, size in sorted(by_category.items(),
                                     key=lambda x: x[1], reverse=True):
            pct = size / total * 100 if total else 0
            self._legend.addItem(
                f"■ {category}: {human_size(size)} ({pct:.1f}%)")
            item = self._legend.item(self._legend.count() - 1)
            item.setForeground(QColor(COLORS.get(category, "#888a85")))

        self._largest.clear()
        for size, path in largest:
            self._largest.addItem(f"{human_size(size):>10}  {path}")

    def closeEvent(self, event) -> None:
        self._analyzer.cancel()
        self._analyzer.wait(500)
        super().closeEvent(event)
