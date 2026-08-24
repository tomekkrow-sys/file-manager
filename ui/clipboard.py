"""Schowek — inteligentny clipboard z historią i między sesjami."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, Signal


@dataclass
class ClipboardItem:
    timestamp: datetime
    type: str  # "text", "files", "image", "html"
    content: str
    metadata: Dict = field(default_factory=dict)


class SmartClipboard(QObject):
    """Schowek z historią i wsparciem dla różnych typów zawartości."""
    changed = Signal()

    def __init__(self, storage_path: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.storage_path = storage_path or Path.home() / ".filemanager" / "clipboard.json"
        self.history: List[ClipboardItem] = []
        self.current: Optional[ClipboardItem] = None
        self.max_history = 50
        self._load()

    def set_text(self, text: str, label: Optional[str] = None) -> None:
        item = ClipboardItem(
            timestamp=datetime.now(),
            type="text",
            content=text,
            metadata={"label": label or "text"},
        )
        self._add(item)

    def set_files(self, paths: List[str]) -> None:
        item = ClipboardItem(
            timestamp=datetime.now(),
            type="files",
            content=json.dumps(paths),
            metadata={"paths": paths},
        )
        self._add(item)

    def set_html(self, html: str) -> None:
        item = ClipboardItem(
            timestamp=datetime.now(),
            type="html",
            content=html,
            metadata={},
        )
        self._add(item)

    def _add(self, item: ClipboardItem) -> None:
        self.history.insert(0, item)
        if len(self.history) > self.max_history:
            self.history.pop()
        self.current = item
        self.changed.emit()

    def get_text(self) -> Optional[str]:
        if self.current and self.current.type == "text":
            return self.current.content
        return None

    def get_files(self) -> List[str]:
        if self.current and self.current.type == "files":
            return json.loads(self.current.content)
        return []

    def history_items(self, limit: int = 20) -> List[ClipboardItem]:
        return self.history[:limit]

    def clear_history(self, older_than: Optional[datetime] = None) -> None:
        if older_than:
            self.history = [i for i in self.history if i.timestamp >= older_than]
        else:
            self.history.clear()
        self._save()

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "current": self.current.__dict__ if self.current else None,
            "history": [i.__dict__ for i in self.history],
        }
        self.storage_path.write_text(json.dumps(data, indent=2, default=str))

    def _load(self) -> None:
        if self.storage_path.exists():
            data = json.loads(self.storage_path.read_text())
            if data.get("current"):
                self.current = ClipboardItem(**data["current"])
            self.history = [ClipboardItem(**i) for i in data.get("history", [])]


class MultiSessionClipboard:
    """Schowek między sesjami — trwa po zamykaniu aplikacji."""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path.home() / ".filemanager" / "clipboard_sessions.json"
        self.sessions: Dict[str, List[Dict]] = {}
        self._load()

    def add_session(self, label: str) -> None:
        self.sessions[label] = []
        self._save()

    def add_to_session(self, session_label: str, item: Dict) -> None:
        if session_label not in self.sessions:
            self.sessions[session_label] = []
        self.sessions[session_label].append(item)
        self._save()

    def get_session_items(self, session_label: str) -> List[Dict]:
        return self.sessions.get(session_label, [])

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(json.dumps(self.sessions, indent=2, default=str))

    def _load(self) -> None:
        if self.storage_path.exists():
            self.sessions = json.loads(self.storage_path.read_text())