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

## Kopiowanie między źródłami (np. chmura ⇄ dysk)

Schowek działa **między wszystkimi źródłami** — transfer idzie przez streaming
(Twój komputer pobiera z jednego źródła i wysyła do drugiego):

1. W źródle A (np. ☁ Google Drive): zaznacz pliki → **Ctrl+C** (Kopiuj).
2. Przełącz się w panelu bocznym na źródło B (np. 🖥 Pamięć lokalna)
   i wejdź do katalogu docelowego.
3. **Ctrl+V** (Wklej) — pojawi się pasek postępu.

**Ctrl+X** (Wytnij) + **Ctrl+V** = przeniesienie (po skopiowaniu usuwa ze źródła).
Działa dla każdej pary: lokalne ⇄ FTP ⇄ SSH ⇄ NAS ⇄ chmury.

## Instalacja i uruchomienie

### Ze źródeł (Linux)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python file_manager.py
# lub:
./run.sh
```

### Pakiet .deb (Linux)

```bash
./build_deb.sh                                   # buduje file-manager_0.1.0_amd64.deb
sudo dpkg -i file-manager_0.1.0_amd64.deb        # instalacja
file-manager                                     # uruchomienie (lub z menu aplikacji)
sudo apt remove file-manager                     # usunięcie
```

Pakiet instaluje się do `/opt/file-manager`, dodaje launcher `/usr/bin/file-manager`,
wpis w menu aplikacji i ikonę. Klucze chmur i tokeny trzymane są w
`~/.config/File_Manager/` (katalog programu jest tylko do odczytu).

### Windows (.exe)

Na komputerze z Windows (Python 3.11+ z python.org):
```
build_windows.bat
```
Wynik: `dist\file-manager\file-manager.exe` — cały folder to przenośna aplikacja.

Alternatywnie po wrzuceniu repo na GitHub workflow
`.github/workflows/build.yml` zbuduje automatycznie **Windows .zip** i
**Linux .deb** (zakładka Actions → „Build installers" → Run workflow,
albo przy tagu `v*`).

## Konfiguracja chmur (OAuth2)

Klucze wpisujesz wygodnie w programie: **Plik → Klucze API chmur…**
(lub ręcznie w `~/.config/File_Manager/cloud_keys.json` —
wzorzec w `config/cloud_keys.example.json`).

Poniżej dokładne instrukcje dla każdego dostawcy.

---

### Google Drive — krok po kroku
*(zweryfikowane z aktualnym interfejsem Google Cloud Console, sierpień 2026)*

> ⚠️ Interfejs Google się zmienił: dawny „OAuth consent screen" to teraz
> **Google Auth Platform** (sekcje: Branding / Audience / Data Access / Clients).

**Krok 1 — utwórz projekt**
1. Wejdź na https://console.cloud.google.com i zaloguj się kontem Google.
2. U góry kliknij selektor projektu → **New Project**.
3. Nazwa: np. `file-manager` → **Create**.
4. **Przełącz się na nowy projekt** w selektorze u góry (częsty błąd: konfigurowanie OAuth na złym projekcie).

**Krok 2 — włącz Google Drive API**

Najszybciej — bezpośredni link (od razu proponuje włączenie):
https://console.cloud.google.com/flows/enableapi?apiid=drive.googleapis.com

Albo ręcznie:
1. Menu ☰ → **APIs & Services** → **Library**
   (https://console.cloud.google.com/apis/library).
2. Wyszukaj **Google Drive API** → otwórz
   (https://console.cloud.google.com/apis/library/drive.googleapis.com) → **Enable**.

⚠️ Sprawdź selektor projektu u góry — API musi włączyć się w projekcie `file-manager`.

**Krok 3 — skonfiguruj Google Auth Platform (ekran zgody)**
1. Menu ☰ → **APIs & Services** → **OAuth consent screen**
   (lub bezpośrednio: https://console.cloud.google.com/auth/branding).
2. Jeśli widzisz „Google Auth Platform not configured yet" → kliknij **Get Started**.
3. **App Information**: nazwa aplikacji np. `File Manager` + Twój email → **Next**.
4. **Audience**: wybierz **External** → **Next**.
5. **Contact Information**: Twój email → **Next** → zaznacz zgodę na politykę → **Create**.

**Krok 4 — dodaj zakres Drive (Data Access)**
1. Wejdź w **Data Access** (https://console.cloud.google.com/auth/scopes).
2. **Add or remove scopes** → znajdź i zaznacz:
   `https://www.googleapis.com/auth/drive` → **Update** → **Save**.

**Krok 5 — dodaj siebie jako użytkownika testowego**
1. Wejdź w **Audience** (https://console.cloud.google.com/auth/audience).
2. W sekcji **Test users** → **Add users** → wpisz **swój adres Gmail** → **Save**.
   (Bez tego logowanie zakończy się błędem „access_denied" —
   aplikacja niezweryfikowana działa tylko dla użytkowników testowych.)

**Krok 6 — utwórz klucze OAuth**
1. Wejdź w **Clients** (https://console.cloud.google.com/auth/clients) → **Create Client**.
2. **Application type**: **Web application**.
3. Nazwa: dowolna (np. `file-manager-desktop`).
4. **Authorized redirect URIs** → **Add URI** → wpisz dokładnie:
   ```
   http://127.0.0.1:8765/callback
   ```
5. **Create**.
6. ⚠️ **Skopiuj Client ID i Client Secret od razu** — od 2025 r. Google
   pokazuje client secret **tylko raz** (potem trzeba tworzyć nowy klient).

**Krok 7 — wpisz klucze w File Managerze**
1. Uruchom `./run.sh` → menu **Plik → Klucze API chmur…**.
2. W sekcji **Google Drive** wklej Client ID i Client Secret → **Zapisz**.

**Krok 8 — zaloguj się**
1. Panel boczny → **☁ Google Drive…** (otworzy się przeglądarka).
2. Wybierz konto → pojawi się ostrzeżenie **„Google hasn't verified this app"**
   → kliknij **Advanced** → **Go to File Manager (unsafe)**
   (to bezpieczne — to Twoja własna, zarejestrowana przez Ciebie aplikacja).
3. Zaznacz zgodę na dostęp do plików Drive → karta wyświetli
   „Logowanie zakończone" → wróć do programu.

Token zapisuje się w `~/.config/File_Manager/cloud_tokens.json` i odświeża się
automatycznie — logujesz się tylko raz.

**Najczęstsze błędy:**
| Objaw | Przyczyna i rozwiązanie |
|---|---|
| `Error 400: redirect_uri_mismatch` | Redirect URI w kroku 6 musi być dokładnie `http://127.0.0.1:8765/callback` (bez spacji, bez https) |
| `access_denied` / `Error 403` | Nie dodałeś swojego Gmaila w Audience → Test users (krok 5) |
| `invalid_scope` | Brak zakresu `.../auth/drive` w Data Access (krok 4) |
| „client_secret nie działa" | Secret był pokazany tylko raz — utwórz nowy klient (krok 6) |
| Zmieniłeś coś, a dalej błąd | Usuń `~/.config/File_Manager/cloud_tokens.json` i zaloguj ponownie |

---

### Dropbox — krok po kroku

1. Wejdź na https://www.dropbox.com/developers/apps → **Create app**.
2. Wybierz: **Scoped access** → **Full Dropbox** → nazwa np. `file-manager` → **Create app**.
3. Na karcie **Settings** aplikacji:
   - w polu **Redirect URIs** wpisz `http://127.0.0.1:8765/callback` → **Add**,
   - skopiuj **App key** i **App secret**.
4. Na karcie **Permissions** zaznacz: `files.content.read`, `files.content.write`,
   `files.metadata.read`, `files.metadata.write` → **Submit**.
5. W File Managerze: **Plik → Klucze API chmur…** → sekcja **Dropbox**
   (App key → Client ID, App secret → Client Secret) → Zapisz.
6. Panel boczny → **☁ Dropbox…** → zaloguj się w przeglądarce.

---

### OneDrive — krok po kroku

1. Wejdź na https://portal.azure.com → wyszukaj **App registrations** → **New registration**.
2. Nazwa: np. `File Manager`; typ kont: **Accounts in any organizational directory
   and personal Microsoft accounts** → **Register**.
3. Skopiuj **Application (client) ID** ze strony przeglądu.
4. **Authentication** → **Add a platform** → **Web** → redirect URI:
   `http://127.0.0.1:8765/callback` → **Configure**.
5. **Certificates & secrets** → **New client secret** → opis dowolny → **Add** →
   skopiuj **Value** (pokazywany tylko raz!).
6. W File Managerze: **Plik → Klucze API chmur…** → sekcja **OneDrive** → Zapisz.
7. Panel boczny → **☁ OneDrive…** → zaloguj się kontem Microsoft.

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
