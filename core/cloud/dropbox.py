"""Provider Dropbox (REST API v2, OAuth2 z PKCE-less flow przez localhost)."""

from __future__ import annotations

import io
import json
import mimetypes
from datetime import datetime
from typing import Iterator, Optional

import requests

from core.cloud.base import (
    CloudFileSystem,
    REDIRECT_URI,
    get_saved_token,
    load_app_keys,
    oauth2_authorize,
    save_token,
)
from core.fs_base import (
    FileInfo,
    FileSystemError,
    FileSystemProvider,
    FileType,
    ProgressCallback,
    copy_stream,
)

API = "https://api.dropboxapi.com/2"
CONTENT = "https://content.dropboxapi.com/2"


def connect_dropbox() -> "DropboxFileSystem":
    """Pełny przepływ logowania — zwraca gotowy provider."""
    keys = load_app_keys().get("dropbox", {})
    app_key = keys.get("client_id")
    app_secret = keys.get("client_secret")
    if not app_key or not app_secret:
        raise FileSystemError(
            "Brak kluczy aplikacji Dropbox.\n"
            "Uzupełnij config/cloud_keys.json (patrz: config/cloud_keys.example.json).")

    saved = get_saved_token("dropbox")
    if saved and saved.get("refresh_token"):
        fs = DropboxFileSystem(saved)
        try:
            fs._refresh_token()
            return fs
        except FileSystemError:
            pass  # token martwy — logujemy od nowa

    code = oauth2_authorize(
        "https://www.dropbox.com/oauth2/authorize",
        {"client_id": app_key, "response_type": "code", "token_access_type": "offline"},
    )
    resp = requests.post("https://api.dropboxapi.com/oauth2/token", data={
        "code": code, "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "client_id": app_key, "client_secret": app_secret,
    }, timeout=30)
    if resp.status_code != 200:
        raise FileSystemError(f"Logowanie Dropbox nieudane: {resp.text[:300]}")
    token = resp.json()
    save_token("dropbox", token)
    return DropboxFileSystem(token)


class DropboxFileSystem(CloudFileSystem):
    scheme = "dropbox"

    def __init__(self, token: dict):
        super().__init__("dropbox", token)

    def display_name(self) -> str:
        return "Dropbox"

    def _refresh_token(self) -> None:
        keys = load_app_keys().get("dropbox", {})
        refresh = self._token.get("refresh_token")
        if not refresh:
            raise FileSystemError("Brak refresh tokena Dropbox — zaloguj ponownie.")
        resp = requests.post("https://api.dropboxapi.com/oauth2/token", data={
            "refresh_token": refresh, "grant_type": "refresh_token",
            "client_id": keys.get("client_id"), "client_secret": keys.get("client_secret"),
        }, timeout=30)
        if resp.status_code != 200:
            raise FileSystemError("Odświeżenie tokena Dropbox nieudane.")
        self._token.update(resp.json())
        save_token("dropbox", self._token)

    def _api(self, endpoint: str, payload: dict, content_endpoint: bool = False) -> requests.Response:
        base = CONTENT if content_endpoint else API
        headers = {"Content-Type": "application/json"}
        return self._check(
            self._request("POST", f"{base}{endpoint}", headers=headers,
                          data=json.dumps(payload)),
            f"Dropbox {endpoint}")

    @staticmethod
    def _entry_info(e: dict) -> FileInfo:
        is_dir = e[".tag"] == "folder"
        name = e["name"]
        modified = None
        if e.get("server_modified"):
            modified = datetime.fromisoformat(e["server_modified"].replace("Z", "+00:00"))
        return FileInfo(
            name=name,
            path=e["path_display"] or f"/{name}",
            type=FileType.DIRECTORY if is_dir else FileType.FILE,
            size=0 if is_dir else e.get("size", 0),
            modified=modified,
            mime="inode/directory" if is_dir else (
                mimetypes.guess_type(name)[0] or "application/octet-stream"),
        )

    # ----- API -----
    def list_dir(self, path: str) -> Iterator[FileInfo]:
        resp = self._api("/files/list_folder", {
            "path": "" if path in ("", "/") else path,
            "include_deleted": False,
        })
        entries = resp.json().get("entries", [])
        for info in sorted((self._entry_info(e) for e in entries),
                           key=lambda i: (not i.is_dir, i.name.lower())):
            yield info

    def stat(self, path: str) -> FileInfo:
        resp = self._api("/files/get_metadata", {"path": path})
        return self._entry_info(resp.json())

    def mkdir(self, path: str) -> None:
        current = ""
        for part in [p for p in path.split("/") if p]:
            current += "/" + part
            resp = self._request("POST", f"{API}/files/create_folder_v2",
                                 headers={"Content-Type": "application/json"},
                                 data=json.dumps({"path": current, "autorename": False}))
            if resp.status_code == 409:
                continue  # już istnieje
            self._check(resp, "Dropbox mkdir")

    def delete(self, path: str, progress: Optional[ProgressCallback] = None) -> None:
        self._api("/files/delete_v2", {"path": path})

    def rename(self, path: str, new_name: str) -> None:
        parent = self.parent(path) or ""
        to = f"{parent.rstrip('/')}/{new_name}"
        self._api("/files/move_v2", {"from_path": path, "to_path": to,
                                     "autorename": False})

    def copy(self, src: FileSystemProvider, src_path: str,
             dst_path: str, progress: Optional[ProgressCallback] = None) -> None:
        # Szybka ścieżka wewnątrz Dropboxa (serwer-side copy)
        if isinstance(src, DropboxFileSystem):
            src_info = src.stat(src_path)
            if src_info.is_dir:
                self._api("/files/copy_v2", {"from_path": src_path, "to_path": dst_path,
                                             "autorename": False})
                return
        src_info = src.stat(src_path)
        if src_info.is_dir:
            self.mkdir(dst_path)
            for child in src.list_dir(src_path):
                self.copy(src, child.path, f"{dst_path.rstrip('/')}/{child.name}", progress)
            return
        copy_stream(src, src_path, self, dst_path, progress, total=src_info.size)

    def open_read(self, path: str):
        resp = self._request(
            "POST", f"{CONTENT}/files/download",
            headers={"Dropbox-API-Arg": json.dumps({"path": path})})
        self._check(resp, "Dropbox download")
        return _BytesCtx(io.BytesIO(resp.content))

    def open_write(self, path: str):
        return _DropboxUploadCtx(self, path)


class _BytesCtx:
    def __init__(self, buf): self._buf = buf
    def __enter__(self): return self._buf
    def __exit__(self, *a): self._buf.close()


class _DropboxUploadCtx:
    """Bufor + upload przy zamknięciu (limit prostego uploadu: 150 MB)."""

    def __init__(self, fs: DropboxFileSystem, path: str):
        self._fs, self._path = fs, path
        self._buf = io.BytesIO()

    def __enter__(self): return self._buf

    def __exit__(self, exc_type, *a):
        if exc_type is None:
            data = self._buf.getvalue()
            resp = self._fs._request(
                "POST", f"{CONTENT}/files/upload",
                headers={
                    "Dropbox-API-Arg": json.dumps(
                        {"path": self._path, "mode": "overwrite"}),
                    "Content-Type": "application/octet-stream",
                },
                data=data)
            self._fs._check(resp, "Dropbox upload")
        self._buf.close()
