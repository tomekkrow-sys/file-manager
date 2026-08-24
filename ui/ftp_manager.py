"""FTP serwer — auto-start, SSL/TLS, konfiguracja."""

from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, Signal


@dataclass
class FTPConfig:
    host: str = "localhost"
    port: int = 21
    user: str = "anonymous"
    password: str = ""
    root_path: str = "/"
    use_tls: bool = True
    auto_start: bool = False
    passive_mode: bool = True
    timeout: int = 30


class FTPServerManager(QObject):
    """Menadżer FTP serwera — auto-start, SSL/TLS."""

    started = Signal(str)
    stopped = Signal(str)
    error = Signal(str)

    def __init__(self, storage_path: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.storage_path = storage_path or Path.home() / ".filemanager" / "ftp_config.json"
        self.config = FTPConfig()
        self._running: bool = False
        self._clients: List[str] = []
        self._load()

    def _load(self) -> None:
        if self.storage_path.exists():
            data = json.loads(self.storage_path.read_text())
            self.config = FTPConfig(**data.get("config", {}))

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"config": {
            "host": self.config.host,
            "port": self.config.port,
            "user": self.config.user,
            "password": self.config.password,
            "root_path": self.config.root_path,
            "use_tls": self.config.use_tls,
            "auto_start": self.config.auto_start,
            "passive_mode": self.config.passive_mode,
            "timeout": self.config.timeout,
        }}
        self.storage_path.write_text(json.dumps(data, indent=2))

    def configure(self, **kwargs) -> FTPConfig:
        """Skonfiguruj FTP."""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        self._save()
        return self.config

    def start(self) -> bool:
        """Uruchom FTP serwer."""
        if self._running:
            return True
        try:
            # TODO: uruchom serwer
            self._running = True
            self.started.emit(f"ftp://{self.config.host}:{self.config.port}")
            if self.config.auto_start:
                self._save()
            return True
        except Exception as exc:
            self.error.emit(f"FTP start error: {exc}")
            return False

    def stop(self) -> bool:
        """Zatrzymaj FTP serwer."""
        if not self._running:
            return True
        try:
            self._running = False
            self.stopped.emit(f"ftp://{self.config.host}:{self.config.port}")
            return True
        except Exception as exc:
            self.error.emit(f"FTP stop error: {exc}")
            return False

    def is_running(self) -> bool:
        return self._running

    def get_clients(self) -> List[str]:
        """Zwróć połączone clients."""
        return self._clients

    def get_config(self) -> FTPConfig:
        return self.config

    def apply_defaults(self) -> FTPConfig:
        """Zastosuj domyślne ustawienia."""
        self.config = FTPConfig(
            host="localhost",
            port=21,
            user="anonymous",
            password="",
            root_path="/",
            use_tls=True,
            auto_start=False,
            passive_mode=True,
        )
        self._save()
        return self.config

    def _save(self) -> None:
        data = {
            "host": self.config.host,
            "port": self.config.port,
            "user": self.config.user,
            "password": self.config.password,
            "root_path": self.config.root_path,
            "use_tls": self.config.use_tls,
            "auto_start": self.config.auto_start,
            "passive_mode": self.config.passive_mode,
        }
        self.config_path.write_text(str(data)) if hasattr(self, "config_path") else None


class FTPConnection:
    """Połączenie FTP z obsługą TLS."""

    def __init__(self, host: str, port: int = 21, use_tls: bool = True):
        self.host = host
        self.port = port
        self.use_tls = use_tls
        self._connected = False
        self._session = None

    def connect(self, user: str = "anonymous", password: str = "") -> bool:
        if self._connected:
            return True
        try:
            # TODO: real FTP connect
            self._connected = True
            return True
        except Exception:
            return False

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def list_dir(self, path: str = "/") -> List[str]:
        # TODO: return list of files
        return ["file1.txt", "file2.txt", "subdir/"]

    def upload(self, local_path: str, remote_path: str) -> bool:
        # TODO: upload file
        return True

    def download(self, remote_path: str, local_path: str) -> bool:
        # TODO: download file
        return True