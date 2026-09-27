"""Motywy UI — Material Design 3 inspired."""

from __future__ import annotations

from typing import Dict

from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication


class ThemeManager:
    """Menadżer motywów UI w stylu Material Design 3."""

    themes: Dict[str, Dict[str, str]] = {
        "light": {
            "bg": "#fafafa",
            "surface": "#ffffff",
            "text": "#1a1a1a",
            "text_secondary": "#666666",
            "accent": "#1a73e8",
            "accent_hover": "#1557b0",
            "accent_text": "#ffffff",
            "secondary": "#f1f3f4",
            "tertiary": "#e8eaed",
            "border": "#dadce0",
            "sidebar_bg": "#f1f3f4",
            "sidebar_hover": "#e8eaed",
            "selected_bg": "#e8f0fe",
            "selected_border": "#1a73e8",
            "hover_bg": "#f1f3f4",
            "folder": "#5f6368",
            "file_icon": "#1a73e8",
            "scrollbar": "#c4c7cc",
            "scrollbar_hover": "#9aa0a6",
        },
        "dark": {
            "bg": "#1a1a2e",
            "surface": "#222240",
            "text": "#e8eaed",
            "text_secondary": "#9aa0a6",
            "accent": "#8ab4f8",
            "accent_hover": "#aecbfa",
            "accent_text": "#1a1a2e",
            "secondary": "#2d2d50",
            "tertiary": "#3c3c6e",
            "border": "#3c3c6e",
            "sidebar_bg": "#16162b",
            "sidebar_hover": "#2d2d50",
            "selected_bg": "#1a3a5c",
            "selected_border": "#8ab4f8",
            "hover_bg": "#2d2d50",
            "folder": "#fdd663",
            "file_icon": "#8ab4f8",
            "scrollbar": "#3c3c6e",
            "scrollbar_hover": "#5f5fa0",
        },
        "midnight": {
            "bg": "#0d1117",
            "surface": "#161b22",
            "text": "#e6edf3",
            "text_secondary": "#8b949e",
            "accent": "#58a6ff",
            "accent_hover": "#79c0ff",
            "accent_text": "#0d1117",
            "secondary": "#161b22",
            "tertiary": "#21262d",
            "border": "#30363d",
            "sidebar_bg": "#0d1117",
            "sidebar_hover": "#161b22",
            "selected_bg": "#1a3a5c",
            "selected_border": "#58a6ff",
            "hover_bg": "#21262d",
            "folder": "#d2a8ff",
            "file_icon": "#58a6ff",
            "scrollbar": "#30363d",
            "scrollbar_hover": "#484f58",
        },
        "sunset": {
            "bg": "#fef7ed",
            "surface": "#ffffff",
            "text": "#3c1518",
            "text_secondary": "#6d4c41",
            "accent": "#e8600a",
            "accent_hover": "#c44e08",
            "accent_text": "#ffffff",
            "secondary": "#fff3e0",
            "tertiary": "#ffe0b2",
            "border": "#ffcc80",
            "sidebar_bg": "#fff3e0",
            "sidebar_hover": "#ffe0b2",
            "selected_bg": "#fff3e0",
            "selected_border": "#e8600a",
            "hover_bg": "#ffe0b2",
            "folder": "#e8600a",
            "file_icon": "#bf360c",
            "scrollbar": "#ffcc80",
            "scrollbar_hover": "#ffb74d",
        },
    }

    @classmethod
    def apply_theme(cls, app, theme_name: str = "dark") -> None:
        """Zastosuj motyw do aplikacji."""
        colors = cls.themes.get(theme_name, cls.themes["dark"])
        style = cls._generate_style(colors)
        app.setStyleSheet(style)

    @classmethod
    def _generate_style(cls, c: dict) -> str:
        """Wygeneruj CSS w stylu Material Design 3."""
        return f"""
        /* ====== OKNA ====== */
        QMainWindow, QDialog {{
            background-color: {c["bg"]};
            color: {c["text"]};
            font-family: "Segoe UI", "Noto Sans", "Ubuntu", sans-serif;
            font-size: 14px;
        }}
        QWidget {{
            font-family: "Segoe UI", "Noto Sans", "Ubuntu", sans-serif;
            font-size: 14px;
        }}

        /* ====== MENU BAR ====== */
        QMenuBar {{
            background-color: {c["surface"]};
            color: {c["text"]};
            padding: 6px 8px;
            spacing: 2px;
            border-bottom: 1px solid {c["border"]};
        }}
        QMenuBar::item {{
            padding: 8px 16px;
            border-radius: 8px;
            color: {c["text"]};
            font-weight: 500;
        }}
        QMenuBar::item:selected {{
            background-color: {c["hover_bg"]};
        }}

        /* ====== MENU ====== */
        QMenu {{
            background-color: {c["surface"]};
            color: {c["text"]};
            padding: 6px;
            border: 1px solid {c["border"]};
            border-radius: 12px;
        }}
        QMenu::item {{
            padding: 10px 32px 10px 16px;
            border-radius: 8px;
            font-weight: 400;
        }}
        QMenu::item:selected {{
            background-color: {c["hover_bg"]};
        }}
        QMenu::separator {{
            height: 1px;
            background: {c["border"]};
            margin: 4px 8px;
        }}

        /* ====== TOOLBAR ====== */
        QToolBar {{
            background-color: {c["surface"]};
            border-bottom: 1px solid {c["border"]};
            spacing: 4px;
            padding: 6px 8px;
        }}
        QToolBar QToolButton {{
            background-color: transparent;
            color: {c["text"]};
            border: none;
            padding: 10px 16px;
            border-radius: 10px;
            font-size: 14px;
            font-weight: 500;
        }}
        QToolBar QToolButton:hover {{
            background-color: {c["hover_bg"]};
        }}
        QToolBar QToolButton:pressed {{
            background-color: {c["tertiary"]};
        }}

        /* ====== PRZYCISKI ====== */
        QPushButton {{
            background-color: {c["accent"]};
            color: {c["accent_text"]};
            border: none;
            padding: 10px 24px;
            border-radius: 10px;
            font-size: 14px;
            font-weight: 600;
            min-height: 20px;
        }}
        QPushButton:hover {{
            background-color: {c["accent_hover"]};
        }}
        QPushButton:pressed {{
            padding: 11px 23px 9px 25px;
        }}

        /* ====== LISTA PLIKÓW — GŁÓWNY ELEMENT ====== */
        QTableView {{
            background-color: {c["bg"]};
            color: {c["text"]};
            border: none;
            border-radius: 12px;
            padding: 4px;
            outline: 0;
            font-size: 14px;
            gridline-color: transparent;
        }}
        QTableView::item {{
            padding: 6px 12px;
            border-radius: 10px;
            min-height: 48px;
        }}
        QTableView::item:selected {{
            background-color: {c["selected_bg"]};
            color: {c["text"]};
        }}
        QTableView::item:hover {{
            background-color: {c["hover_bg"]};
        }}

        /* ====== LISTA (sidebar,etc) ====== */
        QListView, QListWidget {{
            background-color: transparent;
            color: {c["text"]};
            border: none;
            outline: 0;
            font-size: 14px;
        }}
        QListView::item, QListWidget::item {{
            padding: 12px 16px;
            border-radius: 10px;
            min-height: 40px;
            margin: 2px 4px;
        }}
        QListView::item:selected, QListWidget::item:selected {{
            background-color: {c["selected_bg"]};
            color: {c["text"]};
        }}
        QListView::item:hover, QListWidget::item:hover {{
            background-color: {c["hover_bg"]};
        }}

        /* ====== SIDEBAR ====== */
        QListWidget {{
            background-color: {c["sidebar_bg"]};
            font-size: 13px;
        }}

        /* ====== PASEK ŚCIEŻKI ====== */
        QLabel {{
            font-size: 15px;
            font-weight: 600;
            color: {c["text"]};
        }}

        /* ====== STATUS BAR ====== */
        QStatusBar {{
            background-color: {c["surface"]};
            color: {c["text_secondary"]};
            border-top: 1px solid {c["border"]};
            padding: 6px 16px;
            font-size: 13px;
            font-weight: 400;
        }}

        /* ====== INPUTY ====== */
        QLineEdit, QComboBox, QSpinBox, QTextEdit {{
            background-color: {c["secondary"]};
            color: {c["text"]};
            border: 2px solid {c["border"]};
            padding: 10px 14px;
            border-radius: 10px;
            font-size: 14px;
            selection-background-color: {c["accent"]};
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {{
            border-color: {c["accent"]};
        }}
        QComboBox QAbstractItemView {{
            background-color: {c["surface"]};
            color: {c["text"]};
            selection-background-color: {c["hover_bg"]};
            border: 1px solid {c["border"]};
            border-radius: 10px;
            padding: 4px;
        }}

        /* ====== SCROLLBAR — Material style ====== */
        QScrollBar:vertical {{
            background: transparent;
            border: none;
            width: 10px;
            margin: 0;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            border: none;
            height: 10px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {c["scrollbar"]};
            border-radius: 5px;
            min-height: 40px;
        }}
        QScrollBar::handle:horizontal {{
            background: {c["scrollbar"]};
            border-radius: 5px;
            min-width: 40px;
        }}
        QScrollBar::handle:hover {{
            background: {c["scrollbar_hover"]};
        }}
        QScrollBar::add-line, QScrollBar::sub-line {{
            background: none;
            height: 0;
            width: 0;
        }}
        QScrollBar::add-page, QScrollBar::sub-page {{
            background: none;
        }}

        /* ====== SPLITTER ====== */
        QSplitter::handle {{
            background-color: {c["border"]};
            border-radius: 2px;
        }}
        QSplitter::handle:horizontal {{ width: 2px; }}
        QSplitter::handle:vertical {{ height: 2px; }}

        /* ====== NAGŁÓWKI TABELI ====== */
        QHeaderView::section {{
            background-color: {c["secondary"]};
            color: {c["text_secondary"]};
            border: none;
            border-bottom: 2px solid {c["border"]};
            border-right: 1px solid {c["border"]};
            padding: 10px 14px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
        }}

        /* ====== TOOLTIP ====== */
        QToolTip {{
            background-color: {c["surface"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 13px;
        }}

        /* ====== PROGRESS BAR ====== */
        QProgressBar {{
            background-color: {c["secondary"]};
            border: none;
            border-radius: 6px;
            text-align: center;
            padding: 2px;
            max-height: 12px;
        }}
        QProgressBar::chunk {{
            background-color: {c["accent"]};
            border-radius: 6px;
        }}

        /* ====== TAB WIDGET ====== */
        QTabWidget::pane {{
            border: 1px solid {c["border"]};
            border-radius: 8px;
            background-color: {c["surface"]};
        }}
        QTabBar::tab {{
            background-color: {c["secondary"]};
            color: {c["text_secondary"]};
            padding: 8px 20px;
            border: none;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            margin-right: 2px;
            font-weight: 500;
        }}
        QTabBar::tab:selected {{
            background-color: {c["surface"]};
            color: {c["accent"]};
            font-weight: 600;
        }}
        QTabBar::tab:hover {{
            background-color: {c["hover_bg"]};
        }}
        """


def get_theme_names() -> list[str]:
    """Zwróć listę dostępnych motywów."""
    return ["dark", "light", "midnight", "sunset"]
