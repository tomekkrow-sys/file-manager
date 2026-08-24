"""Zewnętrzne narzędzia — "Open With", kontekstowe polecenia."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from core.fs_base import FileInfo


@dataclass
class ExternalTool:
    name: str
    command: str
    description: str = ""
    file_patterns: List[str] = None
    mime_types: List[str] = None


class ExternalToolsManager:
    """Menadżer zewnętrznych narzędzi — "Open With", kontekstowe polecenia."""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path.home() / ".filemanager" / "external_tools.json"
        self.tools: List[ExternalTool] = []
        self._load()

    def _load(self) -> None:
        if self.storage_path.exists():
            data = json.loads(self.storage_path.read_text())
            self.tools = [ExternalTool(**t) for t in data.get("tools", [])]

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "tools": [{"name": t.name, "command": t.command, "description": t.description,
                       "file_patterns": t.file_patterns or [], "mime_types": t.mime_types or []}
                      for t in self.tools],
        }
        self.storage_path.write_text(json.dumps(data, indent=2, default=str))

    def add_tool(self, name: str, command: str, description: str = "",
                 file_patterns: Optional[List[str]] = None,
                 mime_types: Optional[List[str]] = None) -> ExternalTool:
        tool = ExternalTool(name=name, command=command, description=description,
                           file_patterns=file_patterns or [], mime_types=mime_types or [])
        self.tools.append(tool)
        self._save()
        return tool

    def remove_tool(self, name: str) -> None:
        self.tools = [t for t in self.tools if t.name != name]
        self._save()

    def get_tools_for_file(self, file_info: FileInfo) -> List[ExternalTool]:
        """Znajdź narzędzia pasujące do pliku."""
        result = []
        for tool in self.tools:
            if tool.file_patterns:
                matches = any(file_info.name.endswith(p) for p in tool.file_patterns)
                if matches:
                    result.append(tool)
        return result

    def execute(self, tool: ExternalTool, file_path: str) -> bool:
        """Wykonaj narzędzie dla pliku."""
        cmd = tool.command.replace("{path}", file_path)
        cmd = cmd.replace("{name}", Path(file_path).name)
        try:
            subprocess.Popen(cmd, shell=True)
            return True
        except Exception:
            return False

    def list_available(self) -> List[Dict]:
        """Zwróć dostępne narzędzia systemowe."""
        return [
            {"name": "Code", "command": "code {path}", "description": "VS Code", "mime_types": ["text/*"]},
            {"name": "Chrome", "command": "google-chrome {path}", "description": "Google Chrome", "mime_types": ["text/*", "image/*", "application/pdf"]},
            {"name": "GIMP", "command": "gimp {path}", "description": "GIMP", "mime_types": ["image/*"]},
            {"name": "VLC", "command": "vlc {path}", "description": "VLC Media Player", "mime_types": ["video/*", "audio/*"]},
            {"name": "LibreOffice", "command": "libreoffice {path}", "description": "LibreOffice", "mime_types": ["application/vnd.openxmlformats-officedocument", "application/vnd.oasis"]},
        ]


def get_context_menu_items(file_info: FileInfo, tools: List[ExternalTool]) -> List[Dict]:
    """Zwróć pozycje kontekstowego menu dla pliku."""
    result = []
    for tool in tools:
        if not tool.file_patterns or any(file_info.name.endswith(p) for p in tool.file_patterns):
            result.append({
                "label": f"Open with {tool.name}",
                "command": tool.command,
                "description": tool.description,
            })
    return result