"""Motywy UI — ciemny/jasny, konfigurowalne style."""

from __future__ import annotations

from typing import Dict

from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication


class ThemeManager:
    """Menadżer motywów UI."""

    themes: Dict[str, Dict[str, str]] = {
        "light": {
            "bg": "#ffffff",
            "text": "#333333",
            "accent": "#2196f3",
            "accent_text": "#ffffff",
            "secondary": "#f5f5f5",
            "border": "#e0e0e0",
        },
        "dark": {
            "bg": "#1e1e1e",
            "text": "#e0e0e0",
            "accent": "#64b5f6",
            "accent_text": "#ffffff",
            "secondary": "#2d2d2d",
            "border": "#3d3d3d",
        },
        "midnight": {
            "bg": "#0f0f1a",
            "text": "#c0c0d0",
            "accent": "#7b68ee",
            "accent_text": "#ffffff",
            "secondary": "#1a1a2e",
            "border": "#2a2a4e",
        },
        "sunset": {
            "bg": "#fff8e1",
            "text": "#5d4037",
            "accent": "#ff7043",
            "accent_text": "#ffffff",
            "secondary": "#ffe0b2",
            "border": "#d7ccc8",
        },
    }

    @classmethod
    def apply_theme(cls, app, theme_name: str = "dark") -> None:
        """Zastosuj motyw do aplikacji."""
        colors = cls.themes.get(theme_name, cls.themes["dark"])
        style = cls._generate_style(colors)
        app.setStyleSheet(style)

    @classmethod
    def _generate_style(cls, colors: dict) -> str:
        """Wygeneruj CSS dla motywu."""
        return f"""
        QMainWindow, QDialog {{
            background-color: {colors["bg"]};
            color: {colors["text"]};
            font-size: 14px;
            font-weight: bold;
        }}
        QWidget {{
            font-size: 14px;
            font-weight: bold;
        }}
        QMenuBar {{
            background-color: {colors["secondary"]};
            color: {colors["text"]};
            padding: 5px;
            spacing: 3px;
            font-size: 14px;
            font-weight: bold;
        }}
        QMenuBar::item {{
            padding: 5px 12px;
            border-radius: 4px;
            color: {colors["text"]};
            font-weight: bold;
        }}
        QMenuBar::item:selected {{
            background-color: {colors["accent"]};
            color: {colors["accent_text"]};
        }}
        QMenu {{
            background-color: {colors["secondary"]};
            color: {colors["text"]};
            padding: 7px;
            border: 1px solid {colors["border"]};
            border-radius: 8px;
            font-size: 14px;
            font-weight: bold;
        }}
        QMenu::item {{
            padding: 7px 26px 7px 14px;
            border-radius: 5px;
            font-weight: bold;
        }}
        QMenu::item:selected {{
            background-color: {colors["accent"]};
            color: {colors["accent_text"]};
        }}
        QToolBar {{
            background-color: {colors["secondary"]};
            border-bottom: 1px solid {colors["border"]};
            spacing: 6px;
            padding: 5px;
        }}
        QToolBar QToolButton, QToolButton {{
            background-color: transparent;
            color: {colors["text"]};
            border: none;
            padding: 8px 14px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: bold;
        }}
        QToolBar QToolButton:hover, QToolButton:hover {{
            background-color: {colors["accent"]};
            color: {colors["accent_text"]};
        }}
        QToolBar QToolButton:pressed, QToolButton:pressed {{
            background-color: {colors["secondary"]};
        }}
        QPushButton {{
            background-color: {colors["accent"]};
            color: {colors["accent_text"]};
            border: none;
            padding: 9px 18px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {colors["accent_text"]};
            color: {colors["accent"]};
            border: 1px solid {colors["accent"]};
        }}
        QPushButton:pressed {{
            padding: 10px 17px 8px 19px;
        }}
        QListView, QTreeView, QTableView, QListWidget {{
            background-color: {colors["bg"]};
            color: {colors["text"]};
            alternate-background-color: {colors["secondary"]};
            border: 1px solid {colors["border"]};
            border-radius: 8px;
            padding: 5px;
            outline: 0;
            font-size: 14px;
            font-weight: bold;
        }}
        QListView::item, QListWidget::item {{
            padding: 10px 14px;
            border-radius: 5px;
            min-height: 26px;
            font-weight: bold;
        }}
        QTreeView::item, QTableView::item {{
            padding: 8px 12px;
            font-weight: bold;
        }}
        QListView::item:selected, QTreeView::item:selected,
        QListWidget::item:selected, QTableView::item:selected {{
            background-color: {colors["accent"]};
            color: {colors["accent_text"]};
        }}
        QListView::item:hover, QListWidget::item:hover,
        QTreeView::item:hover {{
            background-color: {colors["secondary"]};
        }}
        QStatusBar {{
            background-color: {colors["secondary"]};
            color: {colors["text"]};
            border-top: 1px solid {colors["border"]};
            padding: 5px 12px;
            font-size: 14px;
            font-weight: bold;
        }}
        QLineEdit, QComboBox, QSpinBox, QTextEdit {{
            background-color: {colors["bg"]};
            color: {colors["text"]};
            border: 1px solid {colors["border"]};
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: bold;
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
        QTextEdit:focus {{
            border-color: {colors["accent"]};
        }}
        QComboBox QAbstractItemView {{
            background-color: {colors["secondary"]};
            color: {colors["text"]};
            selection-background-color: {colors["accent"]};
            border: 1px solid {colors["border"]};
            border-radius: 8px;
            font-size: 14px;
            font-weight: bold;
        }}
        QScrollBar:vertical, QScrollBar:horizontal {{
            background: {colors["secondary"]};
            border: none;
            border-radius: 6px;
            width: 14px;
            height: 14px;
        }}
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
            background: {colors["border"]};
            border-radius: 6px;
            min-height: 30px;
            min-width: 30px;
        }}
        QScrollBar::handle:hover {{
            background: {colors["accent"]};
        }}
        QScrollBar::add-line, QScrollBar::sub-line {{
            background: none;
        }}
        QSplitter::handle {{
            background-color: {colors["border"]};
            border-radius: 3px;
        }}
        QSplitter::handle:horizontal {{ width: 6px; }}
        QSplitter::handle:vertical {{ height: 6px; }}
        QHeaderView::section {{
            background-color: {colors["secondary"]};
            color: {colors["text"]};
            border: none;
            border-right: 1px solid {colors["border"]};
            border-bottom: 1px solid {colors["border"]};
            padding: 8px 12px;
            font-size: 14px;
            font-weight: bold;
        }}
        QToolTip {{
            background-color: {colors["secondary"]};
            color: {colors["text"]};
            border: 1px solid {colors["border"]};
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 13px;
            font-weight: bold;
        }}
        QProgressBar {{
            background-color: {colors["secondary"]};
            border: 1px solid {colors["border"]};
            border-radius: 8px;
            text-align: center;
            padding: 1px;
        }}
        QProgressBar::chunk {{
            background-color: {colors["accent"]};
            border-radius: 6px;
        }}
        QLabel {{
            font-size: 14px;
            font-weight: bold;
        }}
        """


def get_theme_names() -> list[str]:
    """Zwróć listę dostępnych motywów."""
    return ["light", "dark", "midnight", "sunset"]