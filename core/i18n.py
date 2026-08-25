"""Prosty system tłumaczeń (Polski ↔ English) dla File Managera.

Kluczami słownika są polskie stringi (domyślny język). Dla angielskiego
podajemy ich tłumaczenia. Jeśli tłumaczenie brakuje, zwracany jest oryginał
(polski), więc apka zawsze działa.

Użycie:
    from core.i18n import _
    label = _("Pamięć lokalna")          # statyczny tekst
    msg = _("Połączono z {host}").format(host=host)  # z zmiennymi
"""

from __future__ import annotations

_LANG = "pl"

# Słownik tłumaczeń PL -> EN. Klucze MUSZĄ dokładnie odpowiadać polskiemu
# tekstowi używanemu w kodzie (łącznie z interpunkcją, emoji i cudzysłowami).
_EN: dict[str, str] = {
    # ---- sidebar places ----
    "🖥  Pamięć lokalna": "🖥  Local storage",
    "📁  Katalog domowy": "📁  Home directory",
    "📊  Analiza pamięci": "📊  Storage analysis",
    "🎵  Zbiory mediów": "🎵  Media collections",
    "── Sieć ──": "── Network ──",
    "➕  Połącz FTP…": "➕  Connect FTP…",
    "➕  Połącz SSH (SFTP)…": "➕  Connect SSH (SFTP)…",
    "➕  Połącz NAS (SMB)…": "➕  Connect NAS (SMB)…",
    "📡  Udostępnij przez FTP…": "📡  Share via FTP…",
    "── Zapisane połączenia ──": "── Saved connections ──",
    "{icon}  {name}": "{icon}  {name}",
    "── Chmury ──": "── Clouds ──",
    "☁  Google Drive…": "☁  Google Drive…",
    "☁  Dropbox…": "☁  Dropbox…",
    "☁  OneDrive…": "☁  OneDrive…",
    "⚙  Klucze API chmur…": "⚙  Cloud API keys…",
    # ---- sidebar context menu ----
    "🔌  Nawiąż połączenie": "🔌  Connect",
    "🗑  Usuń z pamięci": "🗑  Remove from memory",
    # ---- connections / dialogs ----
    "Zapisane połączenia": "Saved connections",
    "Usunąć połączenie „{name}” z pamięci?": "Delete connection \"{name}\" from memory?",
    "FTP": "FTP",
    "SSH": "SSH",
    "NAS": "NAS",
    "Połączenie": "Connection",
    "Połączenie „{name}” zapisane — wybierzesz je z listy.": "Connection \"{name}\" saved — you can pick it from the list.",
    "Chmura": "Cloud",
    "Najpierw musisz wpisać klucze API tej chmury.\nOtworzyć ustawienia kluczy?": "You must first enter this cloud's API keys.\nOpen the key settings?",
    "Otworzono przeglądarkę — zaloguj się do chmury.\nPo zalogowaniu wróć tutaj (okno zamknie się samo).": "Opened browser — log in to the cloud.\nReturn here after logging in (the window will close automatically).",
    "Anuluj": "Cancel",
    "Logowanie do chmury": "Logging in to cloud",
    "Serwer FTP": "FTP Server",
    "Serwer działa (ftp://{ip}:{port}). Zatrzymać?": "Server is running (ftp://{ip}:{port}). Stop it?",
    "Serwer FTP zatrzymany.": "FTP server stopped.",
    "Nie można uruchomić: {exc}": "Could not start: {exc}",
    "Serwer działa!\n\nZ innego urządzenia połącz się z:\n  ftp://{ip}:{port}\n\nUżytkownik i hasło jak w konfiguracji (lub anonimowo, tylko odczyt).": "Server is running!\n\nFrom another device connect to:\n  ftp://{ip}:{port}\n\nUser and password as in configuration (or anonymously, read-only).",
    # ---- navigation / status ----
    "{name}  ▸  {path}": "{name}  ▸  {path}",
    "Ładowanie…": "Loading…",
    "{files} plików, {dirs} katalogów — {size}": "{files} files, {dirs} directories — {size}",
    "Błąd": "Error",
    "Brak wbudowanego podglądu dla typu: {mime}": "No built-in preview for type: {mime}",
    "Archiwum": "Archive",
    "Podgląd archiwów dostępny dla plików lokalnych.\nSkopiuj archiwum na dysk i spróbuj ponownie.": "Archive preview available for local files.\nCopy the archive to disk and try again.",
    "Zawartość: {name}": "Contents: {name}",
    "Archiwum puste.": "Archive empty.",
    "{count} pozycji.\n\n{preview}": "{count} items.\n\n{preview}",
    # ---- file operations ----
    "Nowy katalog": "New folder",
    "Nazwa:": "Name:",
    "Zmień nazwę": "Rename",
    "Nowa nazwa:": "New name:",
    "wytnij": "cut",
    "kopiuj": "copy",
    "Schowek: {count} pozycji ({action}) — przejdź do celu i wciśnij Wklej.": "Clipboard: {count} items ({action}) — go to the destination and press Paste.",
    "Usuń": "Delete",
    "Usunąć trwale {count} pozycji?\n\n{names}": "Permanently delete {count} items?\n\n{names}",
    "Operacja na plikach…": "File operation…",
    "Zakończono: {ok} OK, {err} błędów.": "Finished: {ok} OK, {err} errors.",
    "Błąd: {path} — {msg}": "Error: {path} — {msg}",
    "Kompresja": "Compression",
    "Kompresja ZIP działa dla plików lokalnych.": "ZIP compression works for local files.",
    "Kompresja ZIP": "ZIP Compression",
    "Plik wynikowy:": "Output file:",
    "Wypakuj": "Extract",
    "Zaznacz jedno archiwum (plik lokalny).": "Select a single archive (local file).",
    # ---- toolbar ----
    "Nawigacja": "Navigation",
    "◀ Wstecz": "◀ Back",
    "▶ Dalej": "▶ Forward",
    "⬆ W górę": "⬆ Up",
    "⌂ Start": "⌂ Home",
    "⟳ Odśwież": "⟳ Refresh",
    "📋  Kopiuj": "📋  Copy",
    "✂  Wytnij": "✂  Cut",
    "📥  Wklej": "📥  Paste",
    "🗑  Usuń": "🗑  Delete",
    # ---- menus ----
    "&Plik": "&File",
    "Kopiuj": "Copy",
    "Wytnij": "Cut",
    "Wklej": "Paste",
    "Kompresuj do ZIP…": "Compress to ZIP…",
    "Wypakuj archiwum…": "Extract archive…",
    "Analiza pamięci…": "Storage analysis…",
    "Zbiory mediów…": "Media collections…",
    "Klucze API chmur…": "Cloud API keys…",
    "Zakończ": "Quit",
    "Sprawdź aktualizacje…": "Check for updates…",
    "Język": "Language",
    "Polski": "Polish",
    "English": "English",
    "Zmieniono język — uruchom ponownie aplikację.": "Language changed — restart the application.",
    "Otwórz": "Open",
    "Wypakuj…": "Extract…",
    "Odśwież": "Refresh",
    # ---- updates ----
    "Sprawdzanie aktualizacji…": "Checking for updates…",
    "Aktualizacja": "Update",
    "Masz najnowszą wersję ({version}).": "You have the latest version ({version}).",
    "Nie udało się sprawdzić aktualizacji:\n{error}": "Failed to check for updates:\n{error}",
    "Dostępna nowsza wersja: {version}.\nPobrać i zainstalować teraz?": "A newer version is available: {version}.\nDownload and install now?",
    "Pobieranie {name}…": "Downloading {name}…",
    "Błąd pobierania: {exc}": "Download error: {exc}",
    "Zainstalowano nową wersję. Uruchom aplikację ponownie.": "Installed new version. Restart the application.",
    "Nie udało się zainstalować automatycznie.\nPobrany plik: {dest}\nZainstaluj go ręcznie.": "Failed to install automatically.\nDownloaded file: {dest}\nInstall it manually.",
    # ---- window ----
    "File Manager": "File Manager",
    # ---- fragments ----
    "\n… i {n} więcej": "\n… and {n} more",
    "Nieoczekiwany błąd: {exc}": "Unexpected error: {exc}",
}


def set_language(lang: str) -> None:
    global _LANG
    _LANG = lang if lang in ("pl", "en") else "pl"


def get_language() -> str:
    return _LANG


def _(text: str) -> str:
    """Przetłumacz tekst (jeśli język = en i jest tłumaczenie)."""
    if _LANG == "en":
        return _EN.get(text, text)
    return text
