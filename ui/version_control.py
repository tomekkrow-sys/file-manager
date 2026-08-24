"""Historia wersji / cofanie zmian (version control)."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Version:
    timestamp: datetime
    hash: str
    path: str
    size: int
    action: str = "edit"
    message: str = ""


@dataclass
class VersionHistory:
    path: str
    versions: List[Version] = field(default_factory=list)

    def add_version(self, version: Version) -> None:
        self.versions.append(version)
        self.versions.sort(key=lambda v: v.timestamp, reverse=True)

    def get_version(self, index: int = 0) -> Optional[Version]:
        if index < len(self.versions):
            return self.versions[index]
        return None

    def get_versions_before(self, timestamp: datetime) -> List[Version]:
        return [v for v in self.versions if v.timestamp <= timestamp]

    def get_versions_after(self, timestamp: datetime) -> List[Version]:
        return [v for v in self.versions if v.timestamp >= timestamp]

    def count(self) -> int:
        return len(self.versions)

    def latest(self) -> Optional[Version]:
        return self.versions[0] if self.versions else None


class VersionControl:
    """Version Control — śledzenie zmian w plikach."""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path.home() / ".filemanager" / "versions.json"
        self.histories: Dict[str, VersionHistory] = {}
        self._load()

    def _load(self) -> None:
        if self.storage_path.exists():
            data = json.loads(self.storage_path.read_text())
            for path, history_data in data.items():
                history = VersionHistory(path=path)
                for v_data in history_data.get("versions", []):
                    history.versions.append(Version(
                        timestamp=datetime.fromisoformat(v_data["timestamp"]),
                        hash=v_data["hash"],
                        path=v_data["path"],
                        size=v_data["size"],
                        action=v_data.get("action", "edit"),
                        message=v_data.get("message", ""),
                    ))
                self.histories[path] = history

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        for path, history in self.histories.items():
            data[path] = {
                "path": history.path,
                "versions": [
                    {
                        "timestamp": v.timestamp.isoformat(),
                        "hash": v.hash,
                        "path": v.path,
                        "size": v.size,
                        "action": v.action,
                        "message": v.message,
                    }
                    for v in history.versions
                ],
            }
        self.storage_path.write_text(json.dumps(data, indent=2, default=str))

    def record_version(self, path: str, file_hash: str, action: str = "edit", message: str = "") -> Version:
        """Zarejestruj nową wersję pliku."""
        if path not in self.histories:
            self.histories[path] = VersionHistory(path=path)

        version = Version(
            timestamp=datetime.now(),
            hash=file_hash or hash,
            path=path,
            size=getattr(file, "size", 0),
        )

        if path not in self.histories:
            self.histories[path] = VersionHistory(path=path)

        self.histories[path].add_version(version)

        if self.auto_save:
            self._save()

        return version

    def get_history(self, path: str) -> List[Version]:
        """Zwróć historię zmian dla ścieżki."""
        return self.histories.get(path, VersionHistory(path=path)).versions

    def restore_version(self, path: str, index: int = 0) -> Optional[Version]:
        """Przywróć wersję pliku po indeksie."""
        history = self.histories.get(path)
        if history and index < len(history.versions):
            version = history.versions[index]
            # restore logic here
            return version
        return None

    def compare_versions(self, path: str, idx1: int, idx2: int) -> Dict:
        """Porównaj dwie wersje pliku."""
        history = self.histories.get(path)
        if not history or idx1 >= len(history.versions) or idx2 >= len(history.versions):
            return {}

        v1 = history.versions[idx1]
        v2 = history.versions[idx2]

        return {
            "version1": v1,
            "version2": v2,
            "size_diff": v2.size - v1.size,
            "time_diff": v2.timestamp - v1.timestamp,
        }

    def _save(self) -> None:
        data = {"versions": {}}
        for path, history in self.histories.items():
            data["versions"][path] = {
                "path": history.path,
                "versions": [
                    {
                        "timestamp": v.timestamp.isoformat(),
                        "hash": v.hash,
                        "path": v.path,
                        "size": v.size,
                    }
                    for v in history.versions
                ],
            }
        self._data = data

    def _load(self) -> None:
        self.histories = {}
        for path, data in self._data.get("versions", {}).items():
            history = VersionHistory(path=data["path"])
            for v_data in data.get("versions", []):
                history.add_version(Version(
                    timestamp=datetime.fromisoformat(v_data["timestamp"]),
                    hash=v_data["hash"],
                    path=v_data["path"],
                    size=v_data.get("size", 0),
                ))
            self.histories[path] = history

    def __init__(self, auto_save: bool = True):
        self.auto_save = auto_save
        self.histories: Dict[str, VersionHistory] = {}
        self._data = {"versions": {}}

    def version_file(self, path: str, file_hash: Optional[str] = None, file_size: Optional[int] = None) -> Version:
        """Utwórz wersję pliku."""
        hash_value = file_hash or self._compute_hash(path)
        size = file_size or self._get_size(path)

        version = Version(
            timestamp=datetime.now(),
            hash=hash_value,
            path=path,
            size=size,
        )

        if path not in self.histories:
            self.histories[path] = VersionHistory(path=path)

        self.histories[path].add_version(version)

        if self.auto_save:
            self._save()

        return version

    def get_history(self, path: str) -> List[Version]:
        """Zwróć historię zmian dla ścieżki."""
        return self.histories.get(path, VersionHistory(path=path)).versions

    def restore_version(self, path: str, index: int = 0) -> Optional[Version]:
        """Przywróć wersję pliku po indeksie."""
        history = self.histories.get(path)
        if history and index < len(history.versions):
            version = history.versions[index]
            return version
        return None

    def compare_versions(self, path: str, idx1: int, idx2: int) -> Dict:
        """Porównaj dwie wersje pliku."""
        history = self.histories.get(path)
        if not history or idx1 >= len(history.versions) or idx2 >= len(history.versions):
            return {}

        v1 = history.versions[idx1]
        v2 = history.versions[idx2]

        return {
            "version1": v1,
            "version2": v2,
            "size_diff": v2.size - v1.size,
            "time_diff": v2.timestamp - v1.timestamp,
        }

    def _save(self) -> None:
        data = {"versions": {}}
        for path, history in self.histories.items():
            data["versions"][path] = {
                "path": history.path,
                "versions": [
                    {
                        "timestamp": v.timestamp.isoformat(),
                        "hash": v.hash,
                        "path": v.path,
                        "size": v.size,
                    }
                    for v in history.versions
                ],
            }
        self._data = data

    def _load(self) -> None:
        self.histories = {}
        for path, data in self._data.get("versions", {}).items():
            history = VersionHistory(path=data["path"])
            for v_data in data.get("versions", []):
                history.add_version(Version(
                    timestamp=datetime.fromisoformat(v_data["timestamp"]),
                    hash=v_data["hash"],
                    path=v_data["path"],
                    size=v_data.get("size", 0),
                ))
            self.histories[path] = history

    def _compute_hash(self, path: str) -> str:
        import hashlib
        try:
            with open(path, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return ""

    def _get_size(self, path: str) -> int:
        try:
            return Path(path).stat().st_size
        except Exception:
            return 0

    def clear_history(self, path: Optional[str] = None) -> None:
        """Wyczyść historię (całą lub dla konkretnej ścieżki)."""
        if path:
            self.histories.pop(path, None)
        else:
            self.histories.clear()
        if self.auto_save:
            self._save()


@dataclass
class VersionHistory:
    path: str
    versions: List[Version] = field(default_factory=list)

    def add_version(self, version: Version) -> None:
        self.versions.append(version)

    def get_version(self, index: int) -> Optional[Version]:
        return self.versions[index] if index < len(self.versions) else None


@dataclass
class Version:
    timestamp: datetime
    hash: str
    path: str
    size: int = 0


class VersionControl:
    """Version Control — zarządza historią zmian plików."""

    def __init__(self, auto_save: bool = True):
        self.auto_save = auto_save
        self.histories: Dict[str, VersionHistory] = {}
        self._data = {"versions": {}}

    def version_file(self, path: str, file_hash: Optional[str] = None, file_size: Optional[int] = None) -> Version:
        """Utwórz wersję pliku."""
        hash_value = file_hash or self._compute_hash(path)
        size = file_size or self._get_size(path)

        version = Version(
            timestamp=datetime.now(),
            hash=hash_value,
            path=path,
            size=size,
        )

        if path not in self.histories:
            self.histories[path] = VersionHistory(path=path)

        self.histories[path].add_version(version)

        if self.auto_save:
            self._save()

        return version

    def get_history(self, path: str) -> List[Version]:
        """Zwróć historię zmian dla ścieżki."""
        return self.histories.get(path, VersionHistory(path=path)).versions

    def restore_version(self, path: str, index: int = 0) -> Optional[Version]:
        """Przywróć wersję pliku po indeksie."""
        history = self.histories.get(path)
        if history and index < len(history.versions):
            version = history.versions[index]
            return version
        return None

    def compare_versions(self, path: str, idx1: int, idx2: int) -> Dict:
        """Porównaj dwie wersje pliku."""
        history = self.histories.get(path)
        if not history or idx1 >= len(history.versions) or idx2 >= len(history.versions):
            return {}

        v1 = history.versions[idx1]
        v2 = history.versions[idx2]

        return {
            "version1": v1,
            "version2": v2,
            "size_diff": v2.size - v1.size,
            "time_diff": v2.timestamp - v1.timestamp,
        }

    def _save(self) -> None:
        data = {"versions": {}}
        for path, history in self.histories.items():
            data["versions"][path] = {
                "path": history.path,
                "versions": [
                    {
                        "timestamp": v.timestamp.isoformat(),
                        "hash": v.hash,
                        "path": v.path,
                        "size": v.size,
                    }
                    for v in history.versions
                ],
            }
        self._data = data

    def _load(self) -> None:
        self.histories = {}
        for path, data in self._data.get("versions", {}).items():
            history = VersionHistory(path=data["path"])
            for v_data in data.get("versions", []):
                history.add_version(Version(
                    timestamp=datetime.fromisoformat(v_data["timestamp"]),
                    hash=v_data["hash"],
                    path=v_data["path"],
                    size=v_data.get("size", 0),
                ))
            self.histories[path] = history

    def _compute_hash(self, path: str) -> str:
        import hashlib
        try:
            with open(path, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return ""

    def _get_size(self, path: str) -> int:
        try:
            return Path(path).stat().st_size
        except Exception:
            return 0

    def clear_history(self, path: Optional[str] = None) -> None:
        """Wyczyść historię (całą lub dla konkretnej ścieżki)."""
        if path:
            self.histories.pop(path, None)
        else:
            self.histories.clear()
        if self.auto_save:
            self._save()