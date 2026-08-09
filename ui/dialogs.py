"""Dialogi konfiguracji połączeń: FTP, SMB/NAS, serwer FTP."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit,
    QMessageBox, QSpinBox, QVBoxLayout,
)


class FtpConnectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Połącz z serwerem FTP")
        form = QFormLayout()

        self.host = QLineEdit(placeholderText="np. 192.168.1.10")
        self.port = QSpinBox(minimum=1, maximum=65535, value=21)
        self.user = QLineEdit("anonymous")
        self.password = QLineEdit(echoMode=QLineEdit.EchoMode.Password)
        self.anonymous = QCheckBox("Logowanie anonimowe", checked=True)
        self.anonymous.toggled.connect(
            lambda checked: (self.user.setEnabled(not checked),
                             self.password.setEnabled(not checked)))
        self.user.setEnabled(False)
        self.password.setEnabled(False)

        form.addRow("Adres serwera:", self.host)
        form.addRow("Port:", self.port)
        form.addRow(self.anonymous)
        form.addRow("Użytkownik:", self.user)
        form.addRow("Hasło:", self.password)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _validate(self) -> None:
        if not self.host.text().strip():
            QMessageBox.warning(self, "FTP", "Podaj adres serwera.")
            return
        self.accept()

    def params(self) -> dict:
        anon = self.anonymous.isChecked()
        return {
            "host": self.host.text().strip(),
            "port": self.port.value(),
            "user": "anonymous" if anon else self.user.text().strip(),
            "password": "" if anon else self.password.text(),
        }


class SmbConnectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Połącz z NAS (SMB)")
        form = QFormLayout()

        self.host = QLineEdit(placeholderText="np. 192.168.1.20 lub nas.local")
        self.user = QLineEdit(placeholderText="puste = gość")
        self.password = QLineEdit(echoMode=QLineEdit.EchoMode.Password)

        form.addRow("Adres NAS:", self.host)
        form.addRow("Użytkownik:", self.user)
        form.addRow("Hasło:", self.password)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _validate(self) -> None:
        if not self.host.text().strip():
            QMessageBox.warning(self, "NAS", "Podaj adres serwera NAS.")
            return
        self.accept()

    def params(self) -> dict:
        return {
            "host": self.host.text().strip(),
            "user": self.user.text().strip(),
            "password": self.password.text(),
        }


class FtpServerDialog(QDialog):
    """Konfiguracja serwera FTP ("dostęp z PC")."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Udostępnij przez FTP (dostęp z PC)")
        form = QFormLayout()

        self.directory = QLineEdit("/home")
        self.port = QSpinBox(minimum=1024, maximum=65535, value=2121)
        self.user = QLineEdit("user")
        self.password = QLineEdit("12345")

        form.addRow("Katalog do udostępnienia:", self.directory)
        form.addRow("Port:", self.port)
        form.addRow("Użytkownik:", self.user)
        form.addRow("Hasło:", self.password)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def params(self) -> dict:
        return {
            "directory": self.directory.text().strip() or "/",
            "port": self.port.value(),
            "user": self.user.text().strip() or "user",
            "password": self.password.text() or "12345",
        }
