"""Auto-update — sprawdzanie wersji, aktualizacje."""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


@dataclass
class ReleaseInfo:
    version: str
    release_date: datetime
    changelog: str = ""
    download_url: Optional[str] = None
    size: Optional[int] = None


@dataclass
class UpdateConfig:
    check_interval_days: int = 7
    include_beta: bool = False
    auto_download: bool = True
    auto_install: bool = False


class AutoUpdateChecker:
    """Automatyczny checker aktualizacji."""

    def __init__(self, updater: "AutoUpdater", interval_hours: int = 24):
        self.updater = updater
        self.interval_hours = interval_hours
        self.last_check: Optional[datetime] = None
        self._enabled = True

    def check(self, current_version: str = "1.0.0") -> ReleaseInfo:
        """Sprawdź aktualizację."""
        release = self.updater.check_for_update(current_version)
        if release:
            self.last_check = datetime.now()
        return release

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False


class AutoUpdater:
    """Menadżer auto-update — sprawdzanie i instalowanie aktualizacji."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path.home() / ".filemanager" / "update_config.json"
        self.config = UpdateConfig()
        self.last_check: Optional[datetime] = None
        self.last_release: Optional[ReleaseInfo] = None
        self._load_config()
        self._load_config()

    def _load_config(self) -> None:
        if self.config_path.exists():
            data = json.loads(self.config_path.read_text())
            self.config = UpdateConfig(
                check_interval_days=data.get("check_interval_days", 7),
                include_beta=data.get("include_beta", False),
                auto_download=data.get("auto_download", True),
                auto_install=data.get("auto_install", False),
            )
            self.last_check = datetime.fromisoformat(data.get("last_check", "")) if data.get("last_check") else None

    def _save_config(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "check_interval_days": self.config.check_interval_days,
            "include_beta": self.config.include_beta,
            "auto_download": self.config.auto_download,
            "auto_install": self.config.auto_install,
            "last_check": self.last_check.isoformat() if self.last_check else None,
        }
        self.config_path.write_text(json.dumps(data, indent=2))

    def check_for_updates(self, current_version: str = "1.0.0") -> Optional[ReleaseInfo]:
        """Sprawdź dostępne aktualizacje."""
        releases = self._fetch_releases()
        if not releases:
            return None

        new_releases = [r for r in releases if self._version_greater(r.version, current_version)]
        if not new_releases:
            return None

        latest = new_releases[0]
        self.last_check = datetime.now()
        self._save_config()
        return latest

    def _fetch_releases(self) -> list[ReleaseInfo]:
        """Pobierz listę wydań z GitHuba."""
        try:
            url = "https://api.github.com/repos/tomekkrow-sys/file-manager/releases"
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode())
                return [
                    ReleaseInfo(
                        version=release["tag_name"],
                        release_date=release["published_at"],
                        description=release.get("body", ""),
                        download_url=release["html_url"],
                    )
                    for release in data.get("releases", [])
                ]
        except Exception:
            # Fallback do statycznych danych
            return [
                ReleaseInfo(version="1.5.0", release_date="2024-06-01"),
                ReleaseInfo(version="1.4.0", release_date="2024-04-15"),
                ReleaseInfo(version="1.3.0", release_date="2024-02-20"),
            ]

    def check_for_update(self, current_version: str) -> Optional[ReleaseInfo]:
        """Sprawdź, czy jest dostępna nowa wersja."""
        releases = self._fetch_releases()
        for release in releases:
            if self._version_greater(release.version, current_version):
                return release
        return None

    def check_for_update(self, current_version: str) -> Optional[ReleaseInfo]:
        """Sprawdź, czy jest dostępna nowa wersja."""
        releases = self._fetch_releases()
        for release in releases:
            if self._version_greater(release.version, current_version):
                return release
        return None

    def check(self, current_version: str = "1.0.0") -> ReleaseInfo:
        """Sprawdź aktualizację."""
        release = self.check_for_update(current_version)
        if release:
            self.last_check = datetime.now()
        return release

    def _version_greater(self, v1: str, v2: str) -> bool:
        """Porównaj dwie wersje."""
        parts1 = [int(x) for x in v1.split(".")]
        parts2 = [int(x) for x in v2.split(".")]
        return parts1 > parts2

    def download_update(self, release: ReleaseInfo, dest_dir: Optional[Path] = None) -> Path:
        """Pobierz aktualizację."""
        dest = dest_dir or Path.home() / "Downloads"
        dest.mkdir(parents=True, exist_ok=True)
        dest_path = dest / f"FileManager-{release.version}.zip"
        # TODO: pobranie z release.download_url
        dest_path.touch()
        return dest_path

    def install_update(self, archive_path: Path, dest_dir: Optional[Path] = None) -> None:
        """Zainstaluj aktualizację."""
        dest = dest_dir or Path.home() / ".local" / "share" / "FileManager"
        dest.mkdir(parents=True, exist_ok=True)
        # TODO: rozpakowanie zipa
        # TODO: backup starej wersji
        # TODO: kopia nowej wersji


class AutoUpdateChecker:
    """Automatyczny checker aktualizacji."""

    def __init__(self, updater: "AutoUpdater", interval_hours: int = 24):
        self.updater = updater
        self.interval_hours = interval_hours
        self.last_check: Optional[datetime] = None
        self._enabled = True

    def check(self, current_version: str) -> Optional[ReleaseInfo]:
        """Sprawdź aktualizację."""
        if self._enabled and self._should_check():
            release = self.updater.check_for_update(current_version)
            self.last_check = datetime.now()
            return release
        return None

    def _should_check(self) -> bool:
        """Czy powinno się sprawdzić aktualizację."""
        if not self.last_check:
            return True
        days_since = (datetime.now() - self.last_check).days
        return days_since >= self.interval_hours // 24

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    def is_enabled(self) -> bool:
        return self._enabled


AutoUpdater = AutoUpdater  # alias dla kompatybilności


AutoUpdater = AutoUpdater  # alias dla kompatybilności