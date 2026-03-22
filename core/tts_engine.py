"""Text-to-Speech engine abstraction and implementations for trevo.

Provides a TTSManager with automatic fallback chain:
Google Cloud TTS (WaveNet) → gTTS (free) → pyttsx3 (offline).
"""

from __future__ import annotations

import io
import tempfile
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from utils.logger import logger


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def _pcm_to_wav(pcm: bytes, sample_rate: int = 24000, channels: int = 1,
                sample_width: int = 2) -> bytes:
    """Wrap raw PCM bytes in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class TTSEngine(ABC):
    """Abstract TTS engine."""

    @abstractmethod
    async def speak(self, text: str) -> bytes:
        """Convert text to audio bytes (WAV format, 16-bit PCM, 24 kHz)."""
        ...

    @abstractmethod
    async def speak_to_file(self, text: str, path: Path) -> Path:
        """Convert text to an audio file and return *path*."""
        ...


# ---------------------------------------------------------------------------
# Google Cloud TTS (WaveNet) — free 1M chars / month
# ---------------------------------------------------------------------------

@dataclass
class GoogleCloudTTSConfig:
    """Configuration for Google Cloud TTS."""

    voice: str = "en-US-Wavenet-D"
    language: str = "en-US"
    speaking_rate: float = 1.0
    pitch: float = 0.0
    sample_rate_hz: int = 24000


class GoogleCloudTTS(TTSEngine):
    """Google Cloud TTS with WaveNet voices.

    Requires the ``google-cloud-texttospeech`` package and valid credentials
    (either via *GOOGLE_APPLICATION_CREDENTIALS* env-var or an API key).
    """

    def __init__(self, config: Optional[GoogleCloudTTSConfig] = None) -> None:
        self._config = config or GoogleCloudTTSConfig()
        self._client: object | None = None
        self._texttospeech: object | None = None
        self._available: bool = False
        self._init_client()

    # -- internal ----------------------------------------------------------

    def _init_client(self) -> None:
        try:
            from google.cloud import texttospeech  # type: ignore[import-untyped]
            self._texttospeech = texttospeech
            self._client = texttospeech.TextToSpeechClient()
            self._available = True
            logger.info("GoogleCloudTTS backend initialised (voice=%s)", self._config.voice)
        except Exception as exc:  # noqa: BLE001
            logger.debug("GoogleCloudTTS unavailable: %s", exc)
            self._available = False

    def _synthesise(self, text: str) -> bytes:
        """Synchronous synthesis; called from *speak*."""
        tts = self._texttospeech
        synthesis_input = tts.SynthesisInput(text=text)
        voice_params = tts.VoiceSelectionParams(
            language_code=self._config.language,
            name=self._config.voice,
        )
        audio_config = tts.AudioConfig(
            audio_encoding=tts.AudioEncoding.LINEAR16,
            sample_rate_hertz=self._config.sample_rate_hz,
            speaking_rate=self._config.speaking_rate,
            pitch=self._config.pitch,
        )
        response = self._client.synthesize_speech(
            input=synthesis_input, voice=voice_params, audio_config=audio_config,
        )
        return response.audio_content

    # -- public API --------------------------------------------------------

    async def speak(self, text: str) -> bytes:
        if not self._available:
            raise RuntimeError("GoogleCloudTTS is not available")

        import asyncio
        loop = asyncio.get_running_loop()
        audio_bytes: bytes = await loop.run_in_executor(None, self._synthesise, text)
        logger.debug("GoogleCloudTTS synthesised %d bytes for %d chars", len(audio_bytes), len(text))
        return audio_bytes

    async def speak_to_file(self, text: str, path: Path) -> Path:
        audio = await self.speak(text)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio)
        logger.info("GoogleCloudTTS wrote audio to %s", path)
        return path


# ---------------------------------------------------------------------------
# gTTS — free, no API key, needs internet
# ---------------------------------------------------------------------------

class FreeTTS(TTSEngine):
    """Free TTS using gTTS (Google Translate TTS).

    Good quality for many languages.  Requires an internet connection.
    """

    def __init__(self, language: str = "en", slow: bool = False) -> None:
        self._language = language
        self._slow = slow
        self._available: bool = False
        try:
            import gtts  # noqa: F401  # type: ignore[import-untyped]
            self._available = True
            logger.info("FreeTTS (gTTS) backend initialised (lang=%s)", self._language)
        except ImportError:
            logger.debug("FreeTTS unavailable: gTTS not installed")

    # -- internal ----------------------------------------------------------

    def _synthesise(self, text: str) -> bytes:
        from gtts import gTTS  # type: ignore[import-untyped]

        tts = gTTS(text=text, lang=self._language, slow=self._slow)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            tts.save(str(tmp_path))
            # gTTS produces MP3; convert to WAV via pydub if available,
            # otherwise return the raw MP3 bytes.
            return self._mp3_to_wav(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    @staticmethod
    def _mp3_to_wav(mp3_path: Path) -> bytes:
        """Best-effort MP3 → WAV (16-bit PCM 24 kHz) conversion."""
        try:
            from pydub import AudioSegment  # type: ignore[import-untyped]
            seg = AudioSegment.from_mp3(str(mp3_path))
            seg = seg.set_frame_rate(24000).set_channels(1).set_sample_width(2)
            buf = io.BytesIO()
            seg.export(buf, format="wav")
            return buf.getvalue()
        except Exception:  # noqa: BLE001
            # Fallback: return raw MP3 bytes (still playable by many consumers).
            logger.debug("pydub unavailable; returning raw MP3 from gTTS")
            return mp3_path.read_bytes()

    # -- public API --------------------------------------------------------

    async def speak(self, text: str) -> bytes:
        if not self._available:
            raise RuntimeError("FreeTTS (gTTS) is not available")

        import asyncio
        loop = asyncio.get_running_loop()
        audio_bytes: bytes = await loop.run_in_executor(None, self._synthesise, text)
        logger.debug("FreeTTS synthesised %d bytes for %d chars", len(audio_bytes), len(text))
        return audio_bytes

    async def speak_to_file(self, text: str, path: Path) -> Path:
        audio = await self.speak(text)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio)
        logger.info("FreeTTS wrote audio to %s", path)
        return path


# ---------------------------------------------------------------------------
# pyttsx3 — fully offline (Windows SAPI / espeak / nsss)
# ---------------------------------------------------------------------------

class OfflineTTS(TTSEngine):
    """Offline TTS using pyttsx3 (Windows SAPI voices).

    Fully offline, robotic but functional.
    """

    def __init__(self, rate: int = 180, volume: float = 1.0,
                 voice_id: Optional[str] = None) -> None:
        self._rate = rate
        self._volume = volume
        self._voice_id = voice_id
        self._available: bool = False
        try:
            import pyttsx3  # type: ignore[import-untyped]
            self._pyttsx3 = pyttsx3
            self._available = True
            logger.info("OfflineTTS (pyttsx3) backend initialised")
        except ImportError:
            logger.debug("OfflineTTS unavailable: pyttsx3 not installed")

    def _get_engine(self) -> object:
        """Create a fresh pyttsx3 engine (not thread-safe, create per call)."""
        engine = self._pyttsx3.init()
        engine.setProperty("rate", self._rate)
        engine.setProperty("volume", self._volume)
        if self._voice_id:
            engine.setProperty("voice", self._voice_id)
        return engine

    def _synthesise_to_file(self, text: str, path: Path) -> None:
        engine = self._get_engine()
        engine.save_to_file(text, str(path))
        engine.runAndWait()

    # -- public API --------------------------------------------------------

    async def speak(self, text: str) -> bytes:
        if not self._available:
            raise RuntimeError("OfflineTTS (pyttsx3) is not available")

        import asyncio

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._synthesise_to_file, text, tmp_path)
            audio_bytes = tmp_path.read_bytes()
        finally:
            tmp_path.unlink(missing_ok=True)

        logger.debug("OfflineTTS synthesised %d bytes for %d chars", len(audio_bytes), len(text))
        return audio_bytes

    async def speak_to_file(self, text: str, path: Path) -> Path:
        if not self._available:
            raise RuntimeError("OfflineTTS (pyttsx3) is not available")

        import asyncio

        path.parent.mkdir(parents=True, exist_ok=True)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._synthesise_to_file, text, path)
        logger.info("OfflineTTS wrote audio to %s", path)
        return path


# ---------------------------------------------------------------------------
# TTSManager — fallback chain
# ---------------------------------------------------------------------------

class TTSManager:
    """Manages TTS with automatic fallback chain.

    The chain order is: configured primary provider → gTTS → pyttsx3.
    Each engine is tried in turn; the first to succeed wins.
    """

    _PROVIDER_MAP = {
        "google_cloud": "_build_google_cloud",
        "gtts": "_build_gtts",
        "free": "_build_gtts",
        "offline": "_build_offline",
        "pyttsx3": "_build_offline",
    }

    def __init__(self, config: Optional[dict] = None) -> None:
        self._config: dict = config or {}
        self._engines: list[TTSEngine] = []
        self._build_chain()

    # -- chain construction ------------------------------------------------

    def _build_chain(self) -> None:
        provider = self._config.get("provider", "gtts")
        language = self._config.get("language", "en-US")

        # Primary engine
        builder = self._PROVIDER_MAP.get(provider)
        if builder:
            engine = getattr(self, builder)(language)
            if engine is not None:
                self._engines.append(engine)

        # Fallback: gTTS (skip if already primary)
        if provider not in ("gtts", "free"):
            gtts_engine = self._build_gtts(language)
            if gtts_engine is not None:
                self._engines.append(gtts_engine)

        # Fallback: pyttsx3 (skip if already primary)
        if provider not in ("offline", "pyttsx3"):
            offline_engine = self._build_offline(language)
            if offline_engine is not None:
                self._engines.append(offline_engine)

        if not self._engines:
            logger.warning("TTSManager: no TTS engines available — speech output disabled")
        else:
            names = [type(e).__name__ for e in self._engines]
            logger.info("TTSManager fallback chain: %s", " → ".join(names))

    def _build_google_cloud(self, language: str) -> Optional[GoogleCloudTTS]:
        cfg = GoogleCloudTTSConfig(
            voice=self._config.get("voice", "en-US-Wavenet-D"),
            language=language,
            speaking_rate=self._config.get("speaking_rate", 1.0),
            pitch=self._config.get("pitch", 0.0),
        )
        engine = GoogleCloudTTS(config=cfg)
        return engine if engine._available else None

    def _build_gtts(self, language: str) -> Optional[FreeTTS]:
        # gTTS uses short language codes like "en", "es", "fr"
        short_lang = language.split("-")[0] if "-" in language else language
        engine = FreeTTS(language=short_lang)
        return engine if engine._available else None

    def _build_offline(self, _language: str) -> Optional[OfflineTTS]:
        voice_id = self._config.get("voice_id")
        engine = OfflineTTS(voice_id=voice_id)
        return engine if engine._available else None

    # -- public API --------------------------------------------------------

    async def speak(self, text: str) -> bytes:
        """Try each engine in the fallback chain until one succeeds.

        Raises ``RuntimeError`` if every engine fails.
        """
        if not text or not text.strip():
            return _pcm_to_wav(b"", sample_rate=24000)

        last_error: Optional[Exception] = None
        for engine in self._engines:
            try:
                return await engine.speak(text)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "TTSManager: %s failed (%s), trying next engine",
                    type(engine).__name__, exc,
                )
                last_error = exc

        raise RuntimeError(
            f"All TTS engines failed. Last error: {last_error}"
        ) from last_error

    async def speak_to_file(self, text: str, path: Path) -> Path:
        """Speak to file using the fallback chain."""
        audio = await self.speak(text)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio)
        return path

    async def play(self, text: str) -> None:
        """Speak *text* and play through speakers using sounddevice.

        Attempts to decode the WAV payload and stream it via
        ``sounddevice.play``.  Falls back to writing a temp file and
        using the platform default player if sounddevice is unavailable.
        """
        audio_bytes = await self.speak(text)

        try:
            import sounddevice as sd  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("sounddevice not installed — cannot play audio directly")
            return

        # Decode WAV → numpy
        try:
            buf = io.BytesIO(audio_bytes)
            with wave.open(buf, "rb") as wf:
                n_channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                framerate = wf.getframerate()
                raw_frames = wf.readframes(wf.getnframes())

            if sample_width == 2:
                dtype = np.int16
            elif sample_width == 4:
                dtype = np.int32
            else:
                dtype = np.int16

            audio_array = np.frombuffer(raw_frames, dtype=dtype)
            if n_channels > 1:
                audio_array = audio_array.reshape(-1, n_channels)

            # Convert to float32 for sounddevice
            audio_float = audio_array.astype(np.float32) / (2 ** (8 * sample_width - 1))

            import asyncio
            loop = asyncio.get_running_loop()

            def _play_blocking() -> None:
                sd.play(audio_float, samplerate=framerate)
                sd.wait()

            await loop.run_in_executor(None, _play_blocking)
            logger.debug("TTSManager.play finished (%d samples @ %d Hz)", len(audio_float), framerate)

        except wave.Error:
            # Audio might be MP3 from gTTS fallback — try pydub + sounddevice
            logger.debug("WAV decode failed; attempting pydub MP3 decode for playback")
            try:
                from pydub import AudioSegment  # type: ignore[import-untyped]
                seg = AudioSegment.from_file(io.BytesIO(audio_bytes))
                seg = seg.set_frame_rate(24000).set_channels(1).set_sample_width(2)
                raw = np.frombuffer(seg.raw_data, dtype=np.int16)
                audio_float = raw.astype(np.float32) / 32768.0

                import asyncio
                loop = asyncio.get_running_loop()

                def _play_blocking() -> None:
                    sd.play(audio_float, samplerate=24000)
                    sd.wait()

                await loop.run_in_executor(None, _play_blocking)
            except Exception as exc:  # noqa: BLE001
                logger.error("TTSManager.play: cannot decode audio for playback: %s", exc)
