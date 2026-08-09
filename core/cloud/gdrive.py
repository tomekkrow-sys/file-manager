"""Provider Google Drive (API v3, OAuth2 przez localhost redirect)."""

from __future__ import annotations

import io
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

API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
FOLDER_MIME = "application/vnd.google-apps.folder"
SCOPES = ["https://www.googleapis.com/auth/drive"]


def connect_gdrive(cancel_event=None) -> "GDriveFileSystem":
    keys = load_app_keys().get("gdrive", {})
    client_id, client_secret = keys.get("client_id"), keys.get("client_secret")
    if not client_id or not client_secret or client_id.startswith("WPISZ"):
        raise FileSystemError(
            "Brak kluczy aplikacji Google Drive.\n"
            "Wpisz je w: Plik → Klucze API chmur…")

    saved = get_saved_token("gdrive")
    if saved and saved.get("refresh_token"):
        fs = GDriveFileSystem(saved)
        try:
            fs._refresh_token()
            return fs
        except FileSystemError:
            pass

    code = oauth2_authorize(
        "https://accounts.google.com/o/oauth2/v2/auth",
        {"client_id": client_id, "response_type": "code",
         "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent"},
        cancel_event=cancel_event,
    )
    resp = requests.post("https://oauth2.googleapis.com/token", data={
        "code": code, "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id, "client_secret": client_secret,
    }, timeout=30)
    if resp.status_code != 200:
        raise FileSystemError(f"Logowanie Google Drive nieudane: {resp.text[:300]}")
    token = resp.json()
    save_token("gdrive", token)
    return GDriveFileSystem(token)


class GDriveFileSystem(CloudFileSystem):
    """
    Ścieżki są wirtualne ("/Dokumenty/foto.jpg") — Drive operuje na ID,
    więc prowadzimy mapowanie ścieżka -> ID (z cache).
    """

    scheme = "gdrive"

    def __init__(self, token: dict):
        super().__init__("gdrive", token)
        self._id_cache: dict[str, str] = {"/": "root"}

    def display_name(self) -> str:
        return "Google Drive"

    def _refresh_token(self) -> None:
        keys = load_app_keys().get("gdrive", {})
        refresh = self._token.get("refresh_token")
        if not refresh:
            raise FileSystemError("Brak refresh tokena Google — zaloguj ponownie.")
        resp = requests.post("https://oauth2.googleapis.com/token", data={
            "refresh_token": refresh, "grant_type": "refresh_token",
            "client_id": keys.get("client_id"), "client_secret": keys.get("client_secret"),
        }, timeout=30)
        if resp.status_code != 200:
            raise FileSystemError("Odświeżenie tokena Google nieudane.")
        self._token.update(resp.json())
        save_token("gdrive", self._token)

    # ----- mapowanie ścieżek -----
    def _resolve(self, path: str) -> str:
        """Ścieżka -> file ID (FileSystemError gdy nie istnieje)."""
        path = path.rstrip("/") or "/"
        if path in self._id_cache:
            return self._id_cache[path]
        parent_path = self.parent(path) or "/"
        name = path.rsplit("/", 1)[-1]
        parent_id = self._resolve(parent_path)
        q = (f"'{parent_id}' in parents and name = '{name.replace(chr(39), chr(92)+chr(39))}' "
             "and trashed = false")
        resp = self._check(
            self._request("GET", f"{API}/files",
                          params={"q": q, "fields": "files(id)"}),
            "Drive resolve")
        files = resp.json().get("files", [])
        if not files:
            raise FileSystemError(f"Ścieżka nie istnieje na Drive: {path}")
        self._id_cache[path] = files[0]["id"]
        return files[0]["id"]

    @staticmethod
    def _entry_info(f: dict) -> FileInfo:
        is_dir = f["mimeType"] == FOLDER_MIME
        modified = None
        if f.get("modifiedTime"):
            modified = datetime.fromisoformat(f["modifiedTime"].replace("Z", "+00:00"))
        return FileInfo(
            name=f["name"],
            path=f["name"],          # ustawiane właściwie w list_dir
            type=FileType.DIRECTORY if is_dir else FileType.FILE,
            size=int(f.get("size", 0) or 0) if not is_dir else 0,
            modified=modified,
            mime="inode/directory" if is_dir else f["mimeType"],
            hidden=f["name"].startswith("."),
        )

    # ----- API -----
    def list_dir(self, path: str) -> Iterator[FileInfo]:
        folder_id = self._resolve(path)
        base = path.rstrip("/")
        page_token = None
        while True:
            resp = self._check(
                self._request("GET", f"{API}/files", params={
                    "q": f"'{folder_id}' in parents and trashed = false",
                    "fields": "nextPageToken, files(id,name,mimeType,size,modifiedTime)",
                    "pageSize": 1000,
                    **({"pageToken": page_token} if page_token else {}),
                }), "Drive list")
            data = resp.json()
            entries = []
            for f in data.get("files", []):
                info = self._entry_info(f)
                info.path = f"{base}/{info.name}" if base != "" else f"/{info.name}"
                self._id_cache[info.path] = f["id"]
                entries.append(info)
            for info in sorted(entries, key=lambda i: (not i.is_dir, i.name.lower())):
                yield info
            page_token = data.get("nextPageToken")
            if not page_token:
                break

    def stat(self, path: str) -> FileInfo:
        file_id = self._resolve(path)
        resp = self._check(
            self._request("GET", f"{API}/files/{file_id}",
                          params={"fields": "id,name,mimeType,size,modifiedTime"}),
            "Drive stat")
        info = self._entry_info(resp.json())
        info.path = path
        return info

    def mkdir(self, path: str) -> None:
        current = ""
        for part in [p for p in path.split("/") if p]:
            current += "/" + part
            if current in self._id_cache:
                continue
            parent_id = self._resolve(self.parent(current) or "/")
            try:
                self._id_cache[current] = self._resolve(current)
                continue
            except FileSystemError:
                pass
            resp = self._check(
                self._request("POST", f"{API}/files", json={
                    "name": part, "mimeType": FOLDER_MIME, "parents": [parent_id],
                }, params={"fields": "id"}), "Drive mkdir")
            self._id_cache[current] = resp.json()["id"]

    def delete(self, path: str, progress: Optional[ProgressCallback] = None) -> None:
        file_id = self._resolve(path)
        self._check(self._request("DELETE", f"{API}/files/{file_id}"),
                    "Drive delete")
        self._id_cache.pop(path.rstrip("/"), None)

    def rename(self, path: str, new_name: str) -> None:
        file_id = self._resolve(path)
        self._check(self._request("PATCH", f"{API}/files/{file_id}",
                                  json={"name": new_name}), "Drive rename")
        old = path.rstrip("/")
        new_path = f"{(self.parent(old) or '/').rstrip('/')}/{new_name}"
        self._id_cache.pop(old, None)
        self._id_cache[new_path] = file_id

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
        file_id = self._resolve(path)
        resp = self._request("GET", f"{API}/files/{file_id}",
                             params={"alt": "media"})
        self._check(resp, "Drive download")
        return _BytesCtx(io.BytesIO(resp.content))

    def open_write(self, path: str):
        return _GDriveUploadCtx(self, path)


class _BytesCtx:
    def __init__(self, buf): self._buf = buf
    def __enter__(self): return self._buf
    def __exit__(self, *a): self._buf.close()


class _GDriveUploadCtx:
    """Bufor + resumable upload przy zamknięciu."""

    def __init__(self, fs: GDriveFileSystem, path: str):
        self._fs, self._path = fs, path
        self._buf = io.BytesIO()

    def __enter__(self): return self._buf

    def __exit__(self, exc_type, *a):
        if exc_type is None:
            self._upload()
        self._buf.close()

    def _upload(self) -> None:
        data = self._buf.getvalue()
        name = self._path.rstrip("/").rsplit("/", 1)[-1]
        parent_id = self._fs._resolve(self._fs.parent(self._path) or "/")
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"

        # Nadpis istniejącego pliku o tej nazwie?
        try:
            existing = self._fs._resolve(self._path)
        except FileSystemError:
            existing = None

        if existing:
            resp = self._fs._request(
                "PATCH", f"{UPLOAD}/files/{existing}",
                params={"uploadType": "media"},
                headers={"Content-Type": mime}, data=data)
        else:
            metadata = {"name": name, "parents": [parent_id]}
            boundary = "fm_boundary_42"
            body = (
                f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
                + __import__("json").dumps(metadata)
                + f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n"
            ).encode() + data + f"\r\n--{boundary}--".encode()
            resp = self._fs._request(
                "POST", f"{UPLOAD}/files",
                params={"uploadType": "multipart"},
                headers={"Content-Type": f'multipart/related; boundary="{boundary}"'},
                data=body)
        self._fs._check(resp, "Drive upload")
