"""Dialog ustawień kluczy API chmur — wpisywanie client_id/secret z poziomu GUI."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QLabel, QLineEdit,
    QMessageBox, QVBoxLayout,
)

from core.cloud.base import KEYS_FILE, load_app_keys, save_app_keys

PROVIDERS = [
    ("gdrive", "Google Drive",
     "console.cloud.google.com → APIs & Services → Credentials → OAuth client ID (Web application)"),
    ("dropbox", "Dropbox",
     "dropbox.com/developers/apps → Create app → Scoped access → Full Dropbox"),
    ("onedrive", "OneDrive",
     "portal.azure.com → App registrations → New registration → Web"),
]

HELP_TEXT = (
    "Każda chmura wymaga <b>darmowej rejestracji aplikacji</b> u dostawcy. "
    "W konsoli dostawcy ustaw redirect URI:<br>"
    "<code>http://127.0.0.1:8765/callback</code><br><br>"
    "Szczegółowa instrukcja krok po kroku: README.md, sekcja „Konfiguracja chmur”."
)


class CloudKeysDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Klucze API chmur")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)

        help_label = QLabel(HELP_TEXT, wordWrap=True)
        help_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(help_label)

        self._fields: dict[str, tuple[QLineEdit, QLineEdit]] = {}
        current = load_app_keys()

        for key, title, hint in PROVIDERS:
            box = QGroupBox(title)
            form = QFormLayout(box)

            client_id = QLineEdit(current.get(key, {}).get("client_id", ""))
            client_secret = QLineEdit(current.get(key, {}).get("client_secret", ""))
            client_secret.setEchoMode(QLineEdit.EchoMode.Password)

            form.addRow("Client ID:", client_id)
            form.addRow("Client Secret:", client_secret)
            hint_label = QLabel(f"<small>{hint}</small>", wordWrap=True)
            hint_label.setTextFormat(Qt.TextFormat.RichText)
            form.addRow(hint_label)

            self._fields[key] = (client_id, client_secret)
            layout.addWidget(box)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        keys = load_app_keys()
        for key, (cid, secret) in self._fields.items():
            keys[key] = {
                "client_id": cid.text().strip(),
                "client_secret": secret.text().strip(),
            }
        try:
            save_app_keys(keys)
        except OSError as exc:
            QMessageBox.critical(self, "Błąd zapisu", f"Nie można zapisać:\n{exc}")
            return
        QMessageBox.information(
            self, "Zapisano",
            f"Klucze zapisane w:\n{KEYS_FILE}\n\n"
            "Teraz kliknij wybraną chmurę w panelu bocznym, aby się zalogować.")
        self.accept()
