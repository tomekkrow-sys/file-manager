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
        }}
        QMenuBar {{
            background-color: {colors["secondary"]};
            color: {colors["text"]};
        }}
        QMenuBar::item:selected {{
            background-color: {colors["accent"]};
            color: {colors["accent_text"]};
        }}
        QToolBar {{
            background-color: {colors["secondary"]};
            border-bottom: 1px solid {colors["border"]};
        }}
        QPushButton {{
            background-color: {colors["accent"]};
            color: {colors["accent_text"]};
            border: 1px solid {colors["border"]};
            padding: 6px 12px;
            border-radius: 4px;
        }}
        QPushButton:hover {{
            background-color: {colors["accent_text"]};
            color: {colors["accent"]};
        }}
        QListView, QTreeView, QTableView {{
            background-color: {colors["bg"]};
            color: {colors["text"]};
            alternate-background-color: {colors["secondary"]};
        }}
        QListView::item:selected, QTreeView::item:selected {{
            background-color: {colors["accent"]};
            color: {colors["accent_text"]};
        }}
        QStatusBar {{
            background-color: {colors["secondary"]};
            border-top: 1px solid {colors["border"]};
        }}
        QLineEdit {{
            background-color: {colors["bg"]};
            color: {colors["text"]};
            border: 1px solid {colors["border"]};
            padding: 4px 8px;
            border-radius: 3px;
        }}
        QLineEdit:focus {{
            border-color: {colors["accent"]};
        }}
        """


def get_theme_names() -> list[str]:
    """Zwróć listę dostępnych motywów."""
    return ["light", "dark", "midnight", "sunset"]