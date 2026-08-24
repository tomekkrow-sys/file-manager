"""Chmury — multi-account, auto-sync, synchronizacja z chmurami."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, Signal


@dataclass
class CloudAccount:
    name: str
    provider: str  # "gdrive", "dropbox", "onedrive"
    auth_token: str = ""
    refresh_token: str = ""
    expires_at: Optional[datetime] = None
    last_sync: Optional[datetime] = None
    root_path: str = "/"
    enabled: bool = True


@dataclass
class CloudSyncState:
    synced: int = 0
    failed: int = 0
    skipped: int = 0
    last_run: Optional[datetime] = None


class CloudManager(QObject):
    """Menadżer chmury — multi-account, auto-sync."""

    sync_started = Signal(str)
    sync_progress = Signal(int, int)
    sync_completed = Signal(str, CloudSyncState)
    error = Signal(str, str)

    def __init__(self, storage_path: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.storage_path = storage_path or Path.home() / ".filemanager" / "cloud_accounts.json"
        self.accounts: Dict[str, CloudAccount] = {}
        self.sync_states: Dict[str, CloudSyncState] = {}
        self._running: Dict[str, threading.Event] = {}
        self._load()

    def _load(self) -> None:
        if self.storage_path.exists():
            data = json.loads(self.storage_path.read_text())
            for name, acc_data in data.get("accounts", {}).items():
                expires = acc_data.get("expires_at")
                last_sync = acc_data.get("last_sync")
                self.accounts[name] = CloudAccount(
                    name=name,
                    provider=acc_data.get("provider", "gdrive"),
                    auth_token=acc_data.get("auth_token", ""),
                    refresh_token=acc_data.get("refresh_token", ""),
                    expires_at=datetime.fromisoformat(expires) if expires else None,
                    last_sync=datetime.fromisoformat(last_sync) if last_sync else None,
                    root_path=acc_data.get("root_path", "/"),
                    enabled=acc_data.get("enabled", True),
                )
                self.sync_states[name] = CloudSyncState()

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "accounts": {
                name: {
                    "provider": acc.provider,
                    "auth_token": acc.auth_token,
                    "refresh_token": acc.refresh_token,
                    "expires_at": acc.expires_at.isoformat() if acc.expires_at else None,
                    "last_sync": acc.last_sync.isoformat() if acc.last_sync else None,
                    "root_path": acc.root_path,
                    "enabled": acc.enabled,
                }
                for name, acc in self.accounts.items()
            }
        }
        self.storage_path.write_text(json.dumps(data, indent=2, default=str))

    def add_account(self, name: str, provider: str, root_path: str = "/") -> CloudAccount:
        """Dodaj konto chmury."""
        account = CloudAccount(name=name, provider=provider, root_path=root_path)
        self.accounts[name] = account
        self.sync_states[name] = CloudSyncState()
        self._save()
        return account

    def remove_account(self, name: str) -> None:
        """Usuń konto chmury."""
        self.accounts.pop(name, None)
        self.sync_states.pop(name, None)
        self._running.pop(name, None)
        self._save()

    def enable_account(self, name: str) -> None:
        """Włącz konto."""
        if name in self.accounts:
            self.accounts[name].enabled = True
            self._save()

    def disable_account(self, name: str) -> None:
        """Wyłącz konto."""
        if name in self.accounts:
            self.accounts[name].enabled = False
            self._save()

    def get_enabled_accounts(self) -> List[CloudAccount]:
        """Zwróć włączone konta."""
        return [acc for acc in self.accounts.values() if acc.enabled]

    def sync_account(self, name: str, cancel_event: Optional[threading.Event] = None) -> CloudSyncState:
        """Synchronizuj jedno konto."""
        self.sync_started.emit(name)
        state = self.sync_states.get(name, CloudSyncState())
        cancel = cancel_event or threading.Event()
        self._running[name] = cancel

        # Symulacja synchronizacji
        try:
            items = self._list_remote(name)
            for i, item in enumerate(items):
                if cancel.is_set():
                    break
                # upload/download item
                self.sync_progress.emit(i + 1, len(items))
                if i % 10 == 0:
                    state.synced += 1
                else:
                    state.synced += 1
            state.last_run = datetime.now()
            self.sync_completed.emit(name, state)
        except Exception as exc:
            self.error.emit(name, str(exc))

        return state

    def sync_all(self, cancel_event: Optional[threading.Event] = None) -> Dict[str, CloudSyncState]:
        """Synchronizuj wszystkie włączone konta."""
        results: Dict[str, CloudSyncState] = {}
        for account in self.get_enabled_accounts():
            results[account.name] = self.sync_account(account.name, cancel_event)
        return results

    def _list_remote(self, name: str) -> List[str]:
        """Listuj pliki zdalne (symulacja)."""
        account = self.accounts[name]
        if account.provider == "gdrive":
            return [f"gdrive://{account.root_path}/file_{i}.txt" for i in range(20)]
        elif account.provider == "dropbox":
            return [f"dropbox://{account.root_path}/doc_{i}.pdf" for i in range(15)]
        elif account.provider == "onedrive":
            return [f"onedrive://{account.root_path}/sheet_{i}.xlsx" for i in range(12)]
        return []

    def get_account(self, name: str) -> Optional[CloudAccount]:
        """Zwróć konto."""
        return self.accounts.get(name)

    def refresh_token(self, name: str, new_token: str) -> None:
        """Odśwież token autoryzacji."""
        if name in self.accounts:
            self.accounts[name].auth_token = new_token
            self._save()


class AutoSyncManager:
    """Menadżer auto-sync — harmonogram synchronizacji."""

    def __init__(self, cloud_manager: CloudManager):
        self.cloud = cloud_manager
        self._enabled: bool = True
        self._interval_minutes: int = 30
        self._timer = None

    def start(self) -> None:
        """Rozpocznij auto-sync."""
        self._enabled = True
        # TODO: uruchom timer

    def stop(self) -> None:
        """Zatrzymaj auto-sync."""
        self._enabled = False
        if self._timer:
            self._timer.cancel()

    def sync_now(self) -> None:
        """Synchronizuj teraz."""
        self.cloud.sync_all()

    def set_interval(self, minutes: int) -> None:
        """Ustaw interwał (minuty)."""
        self._interval_minutes = minutes
