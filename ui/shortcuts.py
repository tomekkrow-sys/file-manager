"""Skróty klawiaturowe — konfigurowalne skróty."""
from __future__ import annotations

from typing import Dict, List, Tuple

from PySide6.QtGui import QKeySequence, QAction
from PySide6.QtWidgets import QWidget


class ShortcutManager:
    """Menadżer skrótów klawiaturowych."""

    DEFAULT_SHORTCUTS: Dict[str, Tuple[str, QKeySequence]] = {
        "back": ("Wstecz", QKeySequence("Alt+Left")),
        "forward": ("Dalej", QKeySequence("Alt+Right")),
        "up": ("W górę", QKeySequence("Backspace")),
        "refresh": ("Odśwież", QKeySequence("F5")),
        "copy": ("Kopiuj", QKeySequence("Ctrl+C")),
        "paste": ("Wklej", QKeySequence("Ctrl+V")),
        "cut": ("Wytnij", QKeySequence("Ctrl+X")),
        "delete": ("Usuń", QKeySequence("Delete")),
        "rename": ("Zmień nazwę", QKeySequence("F2")),
        "create_folder": ("Nowy folder", QKeySequence("Ctrl+Shift+N")),
        "search": ("Wyszukaj", QKeySequence("Ctrl+F")),
        "toggle_view": ("Przełącz widok", QKeySequence("Ctrl+V")),
        "properties": ("Właściwości", QKeySequence("Alt+Enter")),
        "select_all": ("Zaznacz wszystko", QKeySequence("Ctrl+A")),
        "invert_selection": ("Odwróć zaznaczenie", QKeySequence("Ctrl+I")),
        "next_panel": ("Następny panel", QKeySequence("Tab")),
        "prev_panel": ("Poprzedni panel", QKeySequence("Shift+Tab")),
        "focus_left": ("Focus lewy panel", QKeySequence("F7")),
        "focus_right": ("Focus prawy panel", QKeySequence("F8")),
        "compare": ("Porównaj panele", QKeySequence("Ctrl+Shift+C")),
        "sync": ("Synchronizuj", QKeySequence("Ctrl+Shift+S")),
        "batch_rename": ("Batch rename", QKeySequence("Alt+F2")),
        "tags": ("Tagi", QKeySequence("Ctrl+Shift+T")),
        "history": ("Historia", QKeySequence("Ctrl+H")),
    }

    def __init__(self):
        self.shortcuts: Dict[str, QKeySequence] = {
            name: seq for name, (_, seq) in self.DEFAULT_SHORTCUTS.items()
        }

    def register_shortcut(self, action: QAction, name: str) -> None:
        """Zarejestruj skrót do akcji."""
        if name in self.shortcuts:
            action.setShortcut(self.shortcuts[name])

    def register_all(self, widget: QWidget, actions: Dict[str, QAction]) -> None:
        """Zarejestruj wszystkie skróty do widgetu."""
        for name, action in actions.items():
            self.register_shortcut(action, name)

    def get_sequence(self, name: str) -> QKeySequence:
        """Zwróć QKeySequence dla nazwy."""
        return self.shortcuts.get(name, QKeySequence())

    def set_sequence(self, name: str, sequence: QKeySequence) -> None:
        """Ustaw QKeySequence dla nazwy."""
        self.shortcuts[name] = sequence

    def as_dict(self) -> Dict[str, str]:
        """Zwróć jako dict dla zapisu."""
        return {name: seq.toString() for name, seq in self.shortcuts.items()}

    def apply_dict(self, data: Dict[str, str]) -> None:
        """Zastosuj dane z dict."""
        for name, seq_str in data.items():
            self.shortcuts[name] = QKeySequence(seq_str)


class ActionRegistry:
    """Rejestr akcji z skrótami."""

    def __init__(self):
        self._actions: Dict[str, QAction] = {}

    def create_action(self, name: str, text: str, shortcut: QKeySequence) -> QAction:
        """Utwórz akcję z skrótem."""
        action = QAction(text)
        action.setShortcut(shortcut)
        self._actions[name] = action
        return action

    def get(self, name: str) -> QAction:
        """Zwróć akcję."""
        return self._actions[name]

    def all(self) -> Dict[str, QAction]:
        """Zwróć wszystkie akcje."""
        return self._actions
