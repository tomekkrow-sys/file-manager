# File Manager

Menedżer plików na Linuxa inspirowany **File Manager Plus** (Android).
Napisany od zera w Pythonie + PySide6, z wykorzystaniem pomysłów z projektów
OSS: abstrakcja providerów wzorowana na **libfm** (jeden interfejs dla
wszystkich źródeł), obsługa archiwów na bibliotece standardowej (jak
**archivetools**).

> Żaden kod nie pochodzi z dekompilacji oryginalnej aplikacji — funkcje
> zostały odtworzone na podstawie publicznego opisu ze sklepu Google Play.

## Funkcje

| Funkcja | Status | Implementacja |
|---|---|---|
| Pliki lokalne (przeglądanie, kopiuj/przenieś/usuń/zmień nazwę, nowy katalog) | ✅ | `core/local_fs.py` |
| Historia nawigacji (wstecz/dalej/w górę) | ✅ | `ui/main_window.py` |
| Archiwa: kompresja **ZIP**, dekompresja **ZIP/TAR/GZ/XZ/BZ2** | ✅ | `core/archives.py` (ochrona zip-slip) |
| Podgląd zawartości archiwum | ✅ | `archives.list_archive()` |
| FTP — klient | ✅ | `core/ftp_fs.py` (`ftplib`) |
| SSH — SFTP (port 22, hasło lub klucz z `~/.ssh`) | ✅ | `core/sftp_fs.py` (`paramiko`) |
| FTP — serwer („dostęp z PC") | ✅ | `core/ftp_server.py` (`pyftpdlib`) |
| NAS — SMB2/3 | ✅ | `core/smb_fs.py` (`smbprotocol`) |
| Chmury: Google Drive / Dropbox / OneDrive | ✅ | `core/cloud/` (OAuth2, REST API) |
| Wbudowana przeglądarka obrazów (zoom, obrót) | ✅ | `ui/viewers/image_viewer.py` |
| Wbudowany edytor tekstu | ✅ | `ui/viewers/text_editor.py` |
| Wbudowany odtwarzacz audio/wideo | ✅ | `ui/viewers/media_player.py` |
| Analiza pamięci (wykres kategorii + największe pliki) | ✅ | `core/storage_analysis.py`, `ui/storage_view.py` |
| Miniaturki obrazów w liście plików | ✅ | `ui/file_list.py` |
| Transfery między dowolnymi źródłami (np. chmura → FTP) | ✅ | streaming przez `copy_stream` |

## Instalacja i uruchomienie

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python file_manager.py
# lub:
./run.sh
```

## Konfiguracja chmur (OAuth2)

1. Skopiuj `config/cloud_keys.example.json` → `config/cloud_keys.json`.
2. Zarejestruj darmową aplikację u dostawcy i wpisz `client_id` / `client_secret`:
   - **Dropbox**: https://www.dropbox.com/developers/apps (Scoped access → Full Dropbox)
   - **Google Drive**: https://console.cloud.google.com (Credentials → OAuth client ID, typ Web)
   - **OneDrive**: https://portal.azure.com (App registrations → Web redirect URI)
3. W każdej konsoli ustaw redirect URI: `http://127.0.0.1:8765/callback`
4. Kliknij chmurę w panelu bocznym — otworzy się przeglądarka z logowaniem.
   Token zapisuje się w `~/.config/File_Manager/cloud_tokens.json`.

## Serwer FTP (dostęp z PC)

Panel boczny → **„Udostępnij przez FTP…"** → wybierz katalog i port (domyślnie
2121). Na innym urządzeniu połącz się z `ftp://<ip-komputera>:2121`.

## Architektura

```
file_manager.py          # punkt wejścia
core/
  fs_base.py             # abstrakcja FileSystemProvider + FileInfo (jak FmFileInfo z libfm)
  local_fs.py            # provider lokalny
  ftp_fs.py              # provider FTP (klient)
  sftp_fs.py             # provider SFTP (SSH, port 22)
  ftp_server.py          # serwer FTP (dostęp z PC)
  smb_fs.py              # provider NAS/SMB
  operations.py          # operacje wsadowe w wątkach (QThread + sygnały)
  archives.py            # ZIP/TAR/GZ/XZ (stdlib)
  storage_analysis.py    # skaner zajętości dysku
  cloud/
    base.py              # OAuth2 (localhost redirect) + cache tokenów
    gdrive.py            # Google Drive API v3
    dropbox.py           # Dropbox API v2
    onedrive.py          # Microsoft Graph
ui/
  main_window.py         # okno główne (jednopanelowe, jak FM+)
  file_list.py           # model/widok listy plików (miniaturki, sortowanie)
  dialogs.py             # dialogi połączeń FTP/SMB/serwer
  storage_view.py        # okno analizy pamięci (wykres kołowy)
  viewers/               # przeglądarka obrazów, edytor tekstu, odtwarzacz
tests/
  test_core.py           # 15 testów jednostkowych core
```

Kluczowa idea: UI operuje wyłącznie na interfejsie `FileSystemProvider`,
więc kopiowanie *z Dropboxa na FTP* to ten sam kod co *z dysku na dysk*.

## Testy

```bash
.venv/bin/python -m pytest tests/ -v
```

## Możliwe rozszerzenia

- Panel dwupanelowy (architektura providerów już na to pozwala)
- SFTP, WebDAV
- Wyszukiwarka plików (globalna, jak w FM+)
- Katalogi zakładek
