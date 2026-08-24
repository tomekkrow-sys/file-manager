"""Multi-language / i18n — lokalizacja interfejsu."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional


class LocaleManager:
    """Menadżer lokalizacji — obsługa wielu języków."""

    def __init__(self, locales_dir: Optional[Path] = None):
        self._locales_dir = locales_dir or Path(__file__).parent / "locales"
        self._locales_dir.mkdir(parents=True, exist_ok=True)
        self._current_locale = "en"
        self._translations: Dict[str, Dict[str, str]] = {}
        self._load_available_locales()

    def _load_available_locales(self) -> None:
        """Załaduj dostępneLocale."""
        translations_dir = self.locales_dir / "translations"
        if translations_dir.exists():
            for file in translations_dir.glob("*.json"):
                locale_code = file.stem
                with open(file, encoding="utf-8") as f:
                    self._translations[locale_code] = json.load(f)

    @property
    def locales_dir(self) -> Path:
        return self._locales_dir

    @locales_dir.setter
    def locales_dir(self, value: Path) -> None:
        self._locales_dir = value

    @property
    def available_locales(self) -> list[str]:
        return list(self._translations.keys())

    @property
    def current_locale(self) -> str:
        return self._current_locale

    @property
    def current_locale(self) -> str:
        return self._current_locale

    @current_locale.setter
    def current_locale(self, locale: str) -> None:
        if locale in self._translations:
            self._current_locale = locale

    @current_locale.setter
    def current_locale(self, locale: str) -> None:
        if locale in self._translations:
            self._current_locale = locale

    def get(self, key: str, default: Optional[str] = None) -> str:
        """Pobierz przekład klucza."""
        lang = self._translations.get(self._current_locale, {})
        return lang.get(key, default or key)

    def translate(self, text: str, context: Optional[str] = None) -> str:
        """Przetłumacz tekst."""
        lookup_key = f"{context}.{text}" if context else text
        return self.get(lookup_key, text)

    def gettext(self, text: str) -> str:
        """ gettext alias."""
        return self.translate(text)

    def ngettext(self, singular: str, plural: str, count: int) -> str:
        """ ngettext alias."""
        lookup_key = f"plural_{singular}"
        lang = self._translations.get(self._current_locale, {})
        if plural in lang:
            return lang[plural]
        return plural if count > 1 else singular

    def add_locale(self, locale: str, translations: dict[str, str]) -> None:
        """Dodaj nową lokalizację."""
        self._translations[locale] = translations

    def remove_locale(self, locale: str) -> None:
        """Usuń lokalizację."""
        self._translations.pop(locale, None)

    def save_locale(self, locale: str) -> None:
        """Zapisz lokalizację."""
        translations_dir = self.locales_dir / "translations"
        translations_dir.mkdir(parents=True, exist_ok=True)
        file = translations_dir / f"{locale}.json"
        with open(file, "w", encoding="utf-8") as f:
            json.dump(self._translations[locale], f, ensure_ascii=False, indent=2)


# Globalny instancja
_i18n: Optional[LocaleManager] = None


def get_i18n() -> LocaleManager:
    """Pobierz globalny moduł i18n."""
    global _i18n
    if _i18n is None:
        _i18n = LocaleManager()
    return _i18n


def tr(text: str, context: Optional[str] = None) -> str:
    """Funkcja tłumaczenia."""
    return get_i18n().translate(text, context)


def N_(text: str) -> str:
    """Zaznaczenie tekstu do przetłumaczenia."""
    return text