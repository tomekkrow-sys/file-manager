"""Provider OneDrive (Microsoft Graph API, OAuth2 przez localhost redirect)."""

from __future__ import annotations

import io
import json
import mimetypes
from datetime import datetime
from typing import Iterator, Optional
from urllib.parse import quote

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

GRAPH = "https://graph.microsoft.com/v1.0"
AUTH = "https://login.microsoftonline.com/common/oauth2/v2.0"
SCOPES = "Files.ReadWrite.All offline_access"


def connect_onedrive() -> "OneDriveFileSystem":
    keys = load_app_keys().get("onedrive", {})
    client_id = keys.get("client_id")
    client_secret = keys.get("client_secret")
    if not client_id or not client_secret:
        raise FileSystemError(
            "Brak kluczy aplikacji OneDrive (Azure).\n"
            "Uzupełnij config/cloud_keys.json (patrz: config/cloud_keys.example.json).")

    saved = get_saved_token("onedrive")
    if saved and saved.get("refresh_token"):
        fs = OneDriveFileSystem(saved)
        try:
            fs._refresh_token()
            return fs
        except FileSystemError:
            pass

    code = oauth2_authorize(f"{AUTH}/authorize", {
        "client_id": client_id, "response_type": "code", "scope": SCOPES,
    })
    resp = requests.post(f"{AUTH}/token", data={
        "code": code, "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id, "client_secret": client_secret,
        "scope": SCOPES,
    }, timeout=30)
    if resp.status_code != 200:
        raise FileSystemError(f"Logowanie OneDrive nieudane: {resp.text[:300]}")
    token = resp.json()
    save_token("onedrive", token)
    return OneDriveFileSystem(token)


class OneDriveFileSystem(CloudFileSystem):
    scheme = "onedrive"

    def __init__(self, token: dict):
        super().__init__("onedrive", token)

    def display_name(self) -> str:
        return "OneDrive"

    def _refresh_token(self) -> None:
        keys = load_app_keys().get("onedrive", {})
        refresh = self._token.get("refresh_token")
        if not refresh:
            raise FileSystemError("Brak refresh tokena OneDrive — zaloguj ponownie.")
        resp = requests.post(f"{AUTH}/token", data={
            "refresh_token": refresh, "grant_type": "refresh_token",
            "client_id": keys.get("client_id"),
            "client_secret": keys.get("client_secret"),
            "redirect_uri": REDIRECT_URI, "scope": SCOPES,
        }, timeout=30)
        if resp.status_code != 200:
            raise FileSystemError("Odświeżenie tokena OneDrive nieudane.")
        self._token.update(resp.json())
        save_token("onedrive", self._token)

    @staticmethod
    def _item_url(path: str) -> str:
        """Graph: /me/drive/root dla '/', /me/drive/root:/ścieżka: inaczej."""
        if path in ("", "/"):
            return f"{GRAPH}/me/drive/root"
        encoded = "/".join(quote(p) for p in path.strip("/").split("/"))
        return f"{GRAPH}/me/drive/root:/{encoded}:"

    @staticmethod
    def _entry_info(item: dict, base_path: str) -> FileInfo:
        is_dir = "folder" in item
        name = item["name"]
        modified = None
        if item.get("lastModifiedDateTime"):
            modified = datetime.fromisoformat(
                item["lastModifiedDateTime"].replace("Z", "+00:00"))
        return FileInfo(
            name=name,
            path=f"{base_path.rstrip('/')}/{name}" if base_path != "/" else f"/{name}",
            type=FileType.DIRECTORY if is_dir else FileType.FILE,
            size=0 if is_dir else item.get("size", 0),
            modified=modified,
            mime="inode/directory" if is_dir else (
                mimetypes.guess_type(name)[0] or "application/octet-stream"),
            hidden=name.startswith("."),
        )

    # ----- API -----
    def list_dir(self, path: str) -> Iterator[FileInfo]:
        url = self._item_url(path) + "/children"
        resp = self._check(self._request("GET", url), "OneDrive list")
        entries = [self._entry_info(i, path) for i in resp.json().get("value", [])]
        for info in sorted(entries, key=lambda i: (not i.is_dir, i.name.lower())):
            yield info

    def stat(self, path: str) -> FileInfo:
        resp = self._check(self._request("GET", self._item_url(path)),
                           "OneDrive stat")
        info = self._entry_info(resp.json(), self.parent(path) or "/")
        info.path = path
        return info

    def mkdir(self, path: str) -> None:
        current = ""
        for part in [p for p in path.split("/") if p]:
            current += "/" + part
            parent_url = self._item_url(self.parent(current) or "/") + "/children"
            resp = self._request("POST", parent_url, json={
                "name": part, "folder": {},
                "@microsoft.graph.conflictBehavior": "fail",
            })
            if resp.status_code == 409:
                continue  # już istnieje
            self._check(resp, "OneDrive mkdir")

    def delete(self, path: str, progress: Optional[ProgressCallback] = None) -> None:
        self._check(self._request("DELETE", self._item_url(path)),
                    "OneDrive delete")

    def rename(self, path: str, new_name: str) -> None:
        self._check(self._request("PATCH", self._item_url(path),
                                  json={"name": new_name}), "OneDrive rename")

    def copy(self, src: FileSystemProvider, src_path: str,
             dst_path: str, progress: Optional[ProgressCallback] = None) -> None:
        src_info = src.stat(src_path)
        if src_info.is_dir:
            self.mkdir(dst_path)
            for child in src.list_dir(src_path):
                self.copy(src, child.path, f"{dst_path.rstrip('/')}/{child.name}", progress)
            return
        copy_stream(src, src_path, self, dst_path, progress, total=src_info.size)

    def open_read(self, path: str):
        resp = self._request("GET", self._item_url(path) + "/content",
                             allow_redirects=True)
        self._check(resp, "OneDrive download")
        return _BytesCtx(io.BytesIO(resp.content))

    def open_write(self, path: str):
        return _OneDriveUploadCtx(self, path)


class _BytesCtx:
    def __init__(self, buf): self._buf = buf
    def __enter__(self): return self._buf
    def __exit__(self, *a): self._buf.close()


class _OneDriveUploadCtx:
    """Bufor + PUT content przy zamknięciu (limit prostego uploadu: 250 MB)."""

    def __init__(self, fs: OneDriveFileSystem, path: str):
        self._fs, self._path = fs, path
        self._buf = io.BytesIO()

    def __enter__(self): return self._buf

    def __exit__(self, exc_type, *a):
        if exc_type is None:
            resp = self._fs._request(
                "PUT", self._fs._item_url(self._path) + "/content",
                headers={"Content-Type": "application/octet-stream"},
                data=self._buf.getvalue())
            self._fs._check(resp, "OneDrive upload")
        self._buf.close()
