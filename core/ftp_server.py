"""
Serwer FTP — odpowiednik funkcji "Access from PC" z File Manager Plus.
Udostępnia wybrany katalog komputera po FTP, żeby dostać się do niego
z innego urządzenia w sieci lokalnej.
"""

from __future__ import annotations

import socket
from typing import Optional

from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer


class LocalFtpServer:
    def __init__(self):
        self._server: Optional[FTPServer] = None
        self.port = 2121
        self.directory = ""

    @staticmethod
    def local_ip() -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"

    def is_running(self) -> bool:
        return self._server is not None

    def start(self, directory: str, port: int = 2121,
              user: str = "user", password: str = "12345") -> tuple[str, int]:
        """Uruchamia serwer. Zwraca (adres, port) do pokazania użytkownikowi."""
        if self._server:
            self.stop()

        authorizer = DummyAuthorizer()
        authorizer.add_user(user, password, directory, perm="elradfmw")
        authorizer.add_anonymous(directory, perm="elr")

        handler = FTPHandler
        handler.authorizer = authorizer
        handler.banner = "File Manager — serwer FTP"

        self._server = FTPServer(("0.0.0.0", port), handler)
        self._server.max_cons = 10
        self.port, self.directory = port, directory

        import threading
        threading.Thread(target=self._server.serve_forever,
                         kwargs={"handle_exit": True}, daemon=True).start()
        return self.local_ip(), port

    def stop(self) -> None:
        if self._server:
            self._server.close_all()
            self._server = None
