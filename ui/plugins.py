"""Pluginy — system i plugin store."""

from __future__ import annotations

import importlib
import json
import pkgutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Type

from PySide6.QtCore import QObject, Signal


@dataclass
class PluginInfo:
    name: str
    version: str
    description: str = ""
    author: str = ""
    enabled: bool = True
    path: Optional[str] = None


@dataclass
class PluginMetadata:
    id: str
    name: str
    version: str
    description: str
    author: str
    type: str = "general"
    requirements: List[str] = field(default_factory=list)


class PluginManager(QObject):
    """Menadżer pluginów — dynamiczne ładowanie."""

    loaded = Signal(PluginInfo)
    unloaded = Signal(str)
    error = Signal(str, str)

    def __init__(self, plugins_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.plugins_dir = plugins_dir or Path.home() / ".filemanager" / "plugins"
        self.plugins: Dict[str, PluginInfo] = {}
        self._instances: Dict[str, object] = {}
        self._metadata: Dict[str, PluginMetadata] = {}
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self._load_manifest()

    def _load_manifest(self) -> None:
        manifest_path = self.plugins_dir / "manifest.json"
        if manifest_path.exists():
            data = json.loads(manifest_path.read_text())
            for name, info in data.get("plugins", {}).items():
                self.plugins[name] = PluginInfo(**info)

    def _save_manifest(self) -> None:
        manifest_path = self.plugins_dir / "manifest.json"
        data = {
            "plugins": {
                name: {"name": p.name, "version": p.version, "enabled": p.enabled, "path": p.path}
                for name, p in self.plugins.items()
            }
        }
        manifest_path.write_text(json.dumps(data, indent=2))

    def discover(self, path: Optional[Path] = None) -> List[str]:
        """Odnajdź pluginy w katalogu."""
        search_path = path or self.plugins_dir
        found = []
        for item in search_path.iterdir():
            if item.is_dir() or (item.suffix == ".py"):
                found.append(item.name)
                if item.name not in self.plugins:
                    self.plugins[item.name] = PluginInfo(
                        name=item.stem,
                        version="1.0.0",
                        path=str(item),
                    )
        self._save_manifest()
        return found

    def load(self, name: str) -> bool:
        """Załaduj plugin."""
        if name in self._instances:
            return True
        plugin_info = self.plugins.get(name)
        if not plugin_info:
            return False
        try:
            # Import plugin module
            module_path = plugin_info.path or str(self.plugins_dir / name)
            if Path(module_path).is_dir():
                spec = importlib.util.spec_from_file_location(
                    name, Path(module_path) / "__init__.py"
                )
            else:
                spec = importlib.util.spec_from_file_location(name, Path(module_path))
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self._instances[name] = module
                self.loaded.emit(plugin_info)
                return True
        except Exception as exc:
            self.error.emit(name, str(exc))
            return False

    def unload(self, name: str) -> bool:
        """Wyładuj plugin."""
        if name in self._instances:
            del self._instances[name]
            self.unloaded.emit(name)
            return True
        return False

    def enable(self, name: str) -> None:
        """Włącz plugin."""
        if name in self.plugins:
            self.plugins[name].enabled = True
            self._save_manifest()

    def disable(self, name: str) -> None:
        """Wyłącz plugin."""
        if name in self.plugins:
            self.plugins[name].enabled = False
            self._save_manifest()

    def get_enabled(self) -> List[PluginInfo]:
        """Zwróć włączone pluginy."""
        return [p for p in self.plugins.values() if p.enabled]

    def get_plugin(self, name: str) -> Optional[object]:
        """Zwróć instancję pluginu."""
        return self._instances.get(name)

    def list_installed(self) -> List[str]:
        """Zwróć listę zainstalowanych pluginów."""
        return list(self.plugins.keys())


class PluginInstaller:
    """Instalator pluginów."""

    def install(self, plugin_path: str) -> str:
        """Zainstaluj plugin z pliku."""
        # w przyszłości: zip, pyz, itp.
        return PluginInstaller._extract_plugin(plugin_path)

    @staticmethod
    def _extract_plugin(path: str) -> str:
        # TODO: obsłużyć zip, pyz
        return Path(path).stem


def register_builtin_plugins(plugin_mgr: "PluginManager") -> None:
    """Zarejestruj wbudowane pluginy."""
    # Tutaj można dodać więcej wbudowanych pluginów
    pass