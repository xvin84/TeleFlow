import json
from pathlib import Path
from typing import Dict, Any
from teleflow.utils.logger import logger

class Translator:
    """Handles parsing and returning translated strings."""

    def __init__(self, locale: str = "ru") -> None:
        self.locale = locale
        self._strings: Dict[str, Any] = {}
        self._load_locale()

    def set_locale(self, locale: str) -> None:
        """Change the application language."""
        if self.locale != locale:
            self.locale = locale
            self._load_locale()

    def _load_locale(self) -> None:
        """Load localized strings from the JSON file."""
        locale_path = Path(__file__).parent / "locales" / f"{self.locale}.json"
        
        if not locale_path.exists():
            logger.error(f"Locale file not found: {locale_path}. Falling back to 'ru'.")
            if self.locale != "ru":
                self.locale = "ru"
                self._load_locale()
            return
            
        try:
            with open(locale_path, "r", encoding="utf-8") as f:
                self._strings = json.load(f)
                logger.debug(f"Loaded locale: {self.locale}")
        except Exception as e:
            logger.error(f"Failed to load locale '{self.locale}': {e}")
            self._strings = {}

    def get(self, key: str, **kwargs: Any) -> str:
        """
        Get a translated string by dot-separated key.
        E.g. t('login.title')
        """
        keys = key.split('.')
        current = self._strings
        
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                logger.warning(f"Missing translation key: '{key}' for locale '{self.locale}'")
                return key
                
        if not isinstance(current, str):
            logger.warning(f"Translation key '{key}' does not point to a string.")
            return key
            
        try:
            return current.format(**kwargs) if kwargs else current
        except KeyError as e:
            logger.warning(f"Missing format argument '{e.args[0]}' for translation key '{key}'")
            return current

# Global default translator instance
_translator = Translator("ru")

def t(key: str, **kwargs: Any) -> str:
    """Convenience function for accessing translations globally."""
    return _translator.get(key, **kwargs)

def set_locale(locale: str) -> None:
    """Change the global locale."""
    _translator.set_locale(locale)
