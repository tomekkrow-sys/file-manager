"""
Wbudowany odtwarzacz audio/wideo (QMediaPlayer).
Pliki z backendów sieciowych są buforowane do pliku tymczasowego.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout,
)

from core.fs_base import FileSystemProvider
from core.local_fs import LocalFileSystem


class MediaPlayerDialog(QDialog):
    def __init__(self, provider: FileSystemProvider, path: str,
                 is_video: bool, parent=None):
        super().__init__(parent)
        name = path.rsplit("/", 1)[-1]
        self.setWindowTitle(name)
        self.resize(900, 600 if is_video else 220)

        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)

        self._video: QVideoWidget | None = None
        if is_video:
            self._video = QVideoWidget()
            self._player.setVideoOutput(self._video)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.sliderMoved.connect(self._player.setPosition)
        self._player.positionChanged.connect(self._slider.setValue)
        self._player.durationChanged.connect(self._slider.setMaximum)

        self._lbl_time = QLabel("0:00 / 0:00")
        self._player.positionChanged.connect(lambda _: self._update_time())

        btn_play = QPushButton("▶ / ⏸")
        btn_play.clicked.connect(self._toggle)
        btn_stop = QPushButton("⏹")
        btn_stop.clicked.connect(self._player.stop)

        bar = QHBoxLayout()
        bar.addWidget(btn_play)
        bar.addWidget(btn_stop)
        bar.addWidget(self._slider, 1)
        bar.addWidget(self._lbl_time)

        layout = QVBoxLayout(self)
        if self._video:
            layout.addWidget(self._video, 1)
        else:
            layout.addWidget(QLabel(f"🎵 {name}", alignment=Qt.AlignmentFlag.AlignCenter), 1)
        layout.addLayout(bar)

        # Lokalne: odtwarzaj bezpośrednio; sieciowe: buforuj do /tmp
        if isinstance(provider, LocalFileSystem):
            url = QUrl.fromLocalFile(path)
            self._tmp: Path | None = None
        else:
            with provider.open_read(path) as f:
                data = f.read()
            suffix = Path(name).suffix
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(data)
            tmp.close()
            self._tmp = Path(tmp.name)
            url = QUrl.fromLocalFile(str(self._tmp))

        self._player.setSource(url)
        self._player.play()

    def _toggle(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _update_time(self) -> None:
        def fmt(ms: int) -> str:
            s = ms // 1000
            return f"{s // 60}:{s % 60:02d}"
        self._lbl_time.setText(
            f"{fmt(self._player.position())} / {fmt(self._player.duration())}")

    def closeEvent(self, event) -> None:
        self._player.stop()
        if self._tmp:
            self._tmp.unlink(missing_ok=True)
        super().closeEvent(event)
