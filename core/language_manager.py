"""Language management for trevo speech-to-text engines."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from utils.logger import logger


# ---------------------------------------------------------------------------
# Language data
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LanguageConfig:
    """Configuration for a single supported language."""
    code: str            # BCP-47 code, e.g. "en-US"
    name: str            # Human-readable name, e.g. "English (US)"
    whisper_code: str    # Whisper language token, e.g. "en"
    azure_locale: str    # Azure Speech locale, e.g. "en-US"
    vosk_model: str      # Vosk model name hint, e.g. "vosk-model-en-us-0.22"


_SUPPORTED_LANGUAGES: dict[str, LanguageConfig] = {
    "en-US": LanguageConfig("en-US", "English (US)", "en", "en-US", "vosk-model-en-us-0.22"),
    "en-GB": LanguageConfig("en-GB", "English (UK)", "en", "en-GB", "vosk-model-en-us-0.22"),
    "es-ES": LanguageConfig("es-ES", "Spanish (Spain)", "es", "es-ES", "vosk-model-es-0.42"),
    "es-MX": LanguageConfig("es-MX", "Spanish (Mexico)", "es", "es-MX", "vosk-model-es-0.42"),
    "fr-FR": LanguageConfig("fr-FR", "French", "fr", "fr-FR", "vosk-model-fr-0.22"),
    "de-DE": LanguageConfig("de-DE", "German", "de", "de-DE", "vosk-model-de-0.21"),
    "it-IT": LanguageConfig("it-IT", "Italian", "it", "it-IT", "vosk-model-it-0.22"),
    "pt-BR": LanguageConfig("pt-BR", "Portuguese (Brazil)", "pt", "pt-BR", "vosk-model-pt-fb-v0.1.1-20220516_2113"),
    "pt-PT": LanguageConfig("pt-PT", "Portuguese (Portugal)", "pt", "pt-PT", "vosk-model-pt-fb-v0.1.1-20220516_2113"),
    "zh-CN": LanguageConfig("zh-CN", "Chinese (Simplified)", "zh", "zh-CN", "vosk-model-cn-0.22"),
    "ja-JP": LanguageConfig("ja-JP", "Japanese", "ja", "ja-JP", "vosk-model-ja-0.22"),
    "ko-KR": LanguageConfig("ko-KR", "Korean", "ko", "ko-KR", "vosk-model-ko-0.22"),
    "ru-RU": LanguageConfig("ru-RU", "Russian", "ru", "ru-RU", "vosk-model-ru-0.42"),
    "ar-SA": LanguageConfig("ar-SA", "Arabic", "ar", "ar-SA", "vosk-model-ar-mgb2-0.4"),
    "hi-IN": LanguageConfig("hi-IN", "Hindi", "hi", "hi-IN", "vosk-model-hi-0.22"),
    "nl-NL": LanguageConfig("nl-NL", "Dutch", "nl", "nl-NL", "vosk-model-nl-spraakherkenning-0.6"),
    "pl-PL": LanguageConfig("pl-PL", "Polish", "pl", "pl-PL", "vosk-model-pl-0.22"),
    "tr-TR": LanguageConfig("tr-TR", "Turkish", "tr", "tr-TR", "vosk-model-tr-0.3"),
    "sv-SE": LanguageConfig("sv-SE", "Swedish", "sv", "sv-SE", "vosk-model-sv-grammars-0.22"),
    "uk-UA": LanguageConfig("uk-UA", "Ukrainian", "uk", "uk-UA", "vosk-model-uk-v3"),
}


# ---------------------------------------------------------------------------
# LanguageManager
# ---------------------------------------------------------------------------

class LanguageManager:
    """Manages language selection for trevo STT engines.

    Supports auto-detect mode (``language=None``) and explicit overrides.
    """

    def __init__(self, language: Optional[str] = None) -> None:
        self._language: Optional[str] = None
        self._auto_detect: bool = True
        if language is not None:
            self.set_language(language)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def supported_languages() -> list[LanguageConfig]:
        """Return all supported language configs, sorted by name."""
        return sorted(_SUPPORTED_LANGUAGES.values(), key=lambda lc: lc.name)

    @staticmethod
    def supported_codes() -> list[str]:
        """Return all supported BCP-47 codes."""
        return sorted(_SUPPORTED_LANGUAGES.keys())

    @property
    def auto_detect(self) -> bool:
        return self._auto_detect

    @property
    def current_language(self) -> Optional[str]:
        """Return the currently configured language code, or ``None`` if auto-detect."""
        return self._language

    def set_language(self, code: str) -> None:
        """Manually set the language by BCP-47 code (e.g. ``"en-US"``)."""
        if code not in _SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Unsupported language code '{code}'. "
                f"Supported: {', '.join(sorted(_SUPPORTED_LANGUAGES))}"
            )
        self._language = code
        self._auto_detect = False
        logger.info("Language set to {} ({})", code, _SUPPORTED_LANGUAGES[code].name)

    def set_auto_detect(self) -> None:
        """Switch back to auto-detect mode."""
        self._language = None
        self._auto_detect = True
        logger.info("Language mode set to auto-detect")

    def get_config(self, code: Optional[str] = None) -> LanguageConfig:
        """Return the :class:`LanguageConfig` for the given or current language.

        Falls back to ``en-US`` when auto-detect is active and no code is
        provided (individual STT engines handle auto-detection internally).
        """
        effective = code or self._language or "en-US"
        cfg = _SUPPORTED_LANGUAGES.get(effective)
        if cfg is None:
            logger.warning("Language '{}' not found — falling back to en-US", effective)
            cfg = _SUPPORTED_LANGUAGES["en-US"]
        return cfg

    def get_whisper_code(self, code: Optional[str] = None) -> Optional[str]:
        """Return the Whisper language token, or ``None`` for auto-detect."""
        if self._auto_detect and code is None:
            return None  # let Whisper auto-detect
        return self.get_config(code).whisper_code

    def get_azure_locale(self, code: Optional[str] = None) -> str:
        """Return the Azure Speech locale string."""
        return self.get_config(code).azure_locale

    def get_vosk_model(self, code: Optional[str] = None) -> str:
        """Return the recommended Vosk model name."""
        return self.get_config(code).vosk_model
