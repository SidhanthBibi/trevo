"""Settings data model for trevo — mirrors config.toml structure."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

from utils.logger import logger

try:
    import tomli
except ModuleNotFoundError:  # Python 3.11+ ships tomllib
    import tomllib as tomli  # type: ignore[no-redef]

try:
    import tomli_w
except ModuleNotFoundError:
    tomli_w = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_config_path() -> Path:
    """Return the path to config.toml in the application directory."""
    app_dir = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "trevo"
    return app_dir / "config.toml"


def _get_project_config_path() -> Path:
    """Return the path to the bundled default config.toml next to the package."""
    return Path(__file__).resolve().parent.parent / "config.toml"


# ---------------------------------------------------------------------------
# Nested settings dataclasses
# ---------------------------------------------------------------------------

@dataclass
class GeneralSettings:
    hotkey: str = "ctrl+shift+space"
    command_hotkey: str = "ctrl+shift+c"
    mode: str = "toggle"
    auto_start: bool = False
    start_minimized: bool = True
    theme: str = "dark"


@dataclass
class DeepgramSettings:
    model: str = "nova-3"
    smart_format: bool = True
    interim_results: bool = True
    filler_words: bool = False


@dataclass
class WhisperSettings:
    model_size: str = "small"
    device: str = "auto"
    compute_type: str = "int8"


@dataclass
class STTSettings:
    engine: str = "deepgram"
    language: str = "auto"
    deepgram_api_key: str = ""
    openai_api_key: str = ""
    groq_api_key: str = ""
    gemini_api_key: str = ""
    google_cloud_api_key: str = ""
    deepgram: DeepgramSettings = field(default_factory=DeepgramSettings)
    whisper: WhisperSettings = field(default_factory=WhisperSettings)


@dataclass
class PolishingSettings:
    enabled: bool = True
    provider: str = "groq"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    groq_api_key: str = ""
    gemini_api_key: str = ""
    ollama_model: str = "llama3.2"
    ollama_url: str = "http://localhost:11434"
    context_aware: bool = True


@dataclass
class AudioSettings:
    input_device: str = "default"
    sample_rate: int = 16000
    noise_gate_threshold: float = 0.01
    vad_sensitivity: float = 0.5
    save_audio: bool = False


@dataclass
class UISettings:
    bar_position: str = "top_center"
    bar_opacity: float = 0.95
    show_interim_results: bool = True
    font_size: int = 14
    notification_sounds: bool = True


@dataclass
class HistorySettings:
    enabled: bool = True
    max_entries: int = 10000
    auto_cleanup_days: int = 90


# ---------------------------------------------------------------------------
# Top-level Settings
# ---------------------------------------------------------------------------

@dataclass
class Settings:
    """Top-level settings object that mirrors the full config.toml structure."""

    general: GeneralSettings = field(default_factory=GeneralSettings)
    stt: STTSettings = field(default_factory=STTSettings)
    polishing: PolishingSettings = field(default_factory=PolishingSettings)
    audio: AudioSettings = field(default_factory=AudioSettings)
    ui: UISettings = field(default_factory=UISettings)
    history: HistorySettings = field(default_factory=HistorySettings)
    snippets: Dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        """Load settings from a TOML file.

        Resolution order:
        1. Explicit *path* argument
        2. User config at ``get_config_path()``
        3. Bundled project default ``config.toml``
        4. Pure dataclass defaults (no file)
        """
        candidates: list[Path] = []
        if path is not None:
            candidates.append(path)
        candidates.append(get_config_path())
        candidates.append(_get_project_config_path())

        for candidate in candidates:
            if candidate.exists():
                logger.debug("Loading settings from {}", candidate)
                try:
                    with open(candidate, "rb") as f:
                        data = tomli.load(f)
                    return cls._from_dict(data)
                except Exception:
                    logger.exception("Failed to load settings from {}", candidate)

        logger.info("No config file found — using defaults")
        return cls()

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> Settings:
        general_data = data.get("general", {})
        stt_data = data.get("stt", {})
        polishing_data = data.get("polishing", {})
        audio_data = data.get("audio", {})
        ui_data = data.get("ui", {})
        history_data = data.get("history", {})
        snippets_data = data.get("snippets", {})

        # STT has nested sub-tables
        deepgram_data = stt_data.pop("deepgram", {})
        whisper_data = stt_data.pop("whisper", {})

        return cls(
            general=GeneralSettings(**{k: v for k, v in general_data.items() if k in GeneralSettings.__dataclass_fields__}),
            stt=STTSettings(
                **{k: v for k, v in stt_data.items() if k in STTSettings.__dataclass_fields__ and k not in ("deepgram", "whisper")},
                deepgram=DeepgramSettings(**{k: v for k, v in deepgram_data.items() if k in DeepgramSettings.__dataclass_fields__}),
                whisper=WhisperSettings(**{k: v for k, v in whisper_data.items() if k in WhisperSettings.__dataclass_fields__}),
            ),
            polishing=PolishingSettings(**{k: v for k, v in polishing_data.items() if k in PolishingSettings.__dataclass_fields__}),
            audio=AudioSettings(**{k: v for k, v in audio_data.items() if k in AudioSettings.__dataclass_fields__}),
            ui=UISettings(**{k: v for k, v in ui_data.items() if k in UISettings.__dataclass_fields__}),
            history=HistorySettings(**{k: v for k, v in history_data.items() if k in HistorySettings.__dataclass_fields__}),
            snippets=dict(snippets_data),
        )

    # ------------------------------------------------------------------
    # Saving
    # ------------------------------------------------------------------

    def save(self, path: Path | None = None) -> None:
        """Save settings to a TOML file."""
        target = path or get_config_path()
        target.parent.mkdir(parents=True, exist_ok=True)

        data = self._to_dict()

        if tomli_w is not None:
            with open(target, "wb") as f:
                tomli_w.dump(data, f)
        else:
            with open(target, "w", encoding="utf-8") as f:
                f.write(self._dict_to_toml(data))

        logger.info("Settings saved to {}", target)

    def _to_dict(self) -> dict[str, Any]:
        """Convert settings tree to a plain dict suitable for TOML serialisation."""
        from dataclasses import asdict

        stt_dict = {
            "engine": self.stt.engine,
            "language": self.stt.language,
            "deepgram_api_key": self.stt.deepgram_api_key,
            "openai_api_key": self.stt.openai_api_key,
            "groq_api_key": self.stt.groq_api_key,
            "gemini_api_key": self.stt.gemini_api_key,
            "google_cloud_api_key": self.stt.google_cloud_api_key,
            "deepgram": asdict(self.stt.deepgram),
            "whisper": asdict(self.stt.whisper),
        }

        return {
            "general": asdict(self.general),
            "stt": stt_dict,
            "polishing": asdict(self.polishing),
            "audio": asdict(self.audio),
            "ui": asdict(self.ui),
            "history": asdict(self.history),
            "snippets": dict(self.snippets),
        }

    # ------------------------------------------------------------------
    # Manual TOML writer (fallback when tomli_w is not installed)
    # ------------------------------------------------------------------

    @staticmethod
    def _dict_to_toml(data: dict[str, Any], prefix: str = "") -> str:
        """Minimalist dict -> TOML string builder."""
        lines: list[str] = []

        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key

            if isinstance(value, dict):
                lines.append(f"\n[{full_key}]")
                for k, v in value.items():
                    if isinstance(v, dict):
                        # nested table
                        lines.append(Settings._dict_to_toml({k: v}, prefix=full_key).rstrip())
                    else:
                        lines.append(f"{k} = {Settings._format_toml_value(v)}")
            else:
                lines.append(f"{key} = {Settings._format_toml_value(value)}")

        return "\n".join(lines) + "\n"

    @staticmethod
    def _format_toml_value(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            return str(value)
        if isinstance(value, str):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return repr(value)
