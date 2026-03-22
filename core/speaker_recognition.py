"""Speaker recognition (enrollment and identification) for trevo.

Uses `resemblyzer <https://github.com/resemble-ai/Resemblyzer>`_ to extract
256-dimensional voice embeddings.  Profiles are stored as ``.npy`` files under
the configured profiles directory (default ``~/trevo-vault/voices/``).

If resemblyzer is not installed the module degrades gracefully: enrollment
raises, and identification always returns ``None``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

from utils.logger import logger

# ---------------------------------------------------------------------------
# Optional dependency
# ---------------------------------------------------------------------------

_RESEMBLYZER_AVAILABLE: bool = False

try:
    from resemblyzer import VoiceEncoder, preprocess_wav  # type: ignore[import-untyped]
    _RESEMBLYZER_AVAILABLE = True
except ImportError:
    logger.warning(
        "resemblyzer is not installed — speaker recognition will be unavailable. "
        "Install with: pip install resemblyzer"
    )

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

_DEFAULT_PROFILES_DIR = Path.home() / "trevo-vault" / "voices"

# Minimum audio length in seconds required for a reliable embedding.
_MIN_AUDIO_SECONDS: float = 3.0
_SAMPLE_RATE: int = 16_000
_IDENTIFICATION_THRESHOLD: float = 0.75


@dataclass
class SpeakerProfile:
    """A saved voice profile."""

    name: str
    embedding: np.ndarray  # 256-dim vector
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    preferences: dict = field(default_factory=dict)

    # -- serialisation helpers ---------------------------------------------

    def save(self, directory: Path) -> None:
        """Persist the profile to *directory*/<name>.npy + .json."""
        directory.mkdir(parents=True, exist_ok=True)
        safe_name = self._safe_filename(self.name)

        np.save(directory / f"{safe_name}.npy", self.embedding)

        meta = {
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "preferences": self.preferences,
        }
        (directory / f"{safe_name}.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8",
        )

    @classmethod
    def load(cls, npy_path: Path) -> SpeakerProfile:
        """Load a profile from an ``.npy`` file (expects a sibling ``.json``)."""
        embedding = np.load(npy_path)
        json_path = npy_path.with_suffix(".json")

        if json_path.exists():
            meta = json.loads(json_path.read_text(encoding="utf-8"))
            name = meta.get("name", npy_path.stem)
            created_at_str = meta.get("created_at")
            created_at = (
                datetime.fromisoformat(created_at_str)
                if created_at_str
                else datetime.now(timezone.utc)
            )
            preferences = meta.get("preferences", {})
        else:
            name = npy_path.stem
            created_at = datetime.now(timezone.utc)
            preferences = {}

        return cls(
            name=name,
            embedding=embedding,
            created_at=created_at,
            preferences=preferences,
        )

    @staticmethod
    def _safe_filename(name: str) -> str:
        """Sanitise *name* for use as a filename."""
        return "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip()


# ---------------------------------------------------------------------------
# SpeakerRecognition
# ---------------------------------------------------------------------------

class SpeakerRecognition:
    """Voice enrollment and identification using resemblyzer.

    Parameters
    ----------
    profiles_dir:
        Directory to store / load ``.npy`` voice profiles.
        Defaults to ``~/trevo-vault/voices/``.
    threshold:
        Cosine-similarity threshold for positive identification.
    """

    def __init__(
        self,
        profiles_dir: Optional[Path] = None,
        threshold: float = _IDENTIFICATION_THRESHOLD,
    ) -> None:
        self._profiles_dir: Path = profiles_dir or _DEFAULT_PROFILES_DIR
        self._threshold: float = threshold
        self._profiles: dict[str, SpeakerProfile] = {}
        self._encoder: object | None = None

        self._init_encoder()
        self._load_profiles()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_encoder(self) -> None:
        if not _RESEMBLYZER_AVAILABLE:
            return
        try:
            self._encoder = VoiceEncoder()
            logger.info("Speaker recognition encoder loaded")
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load VoiceEncoder: %s", exc)
            self._encoder = None

    def _load_profiles(self) -> None:
        """Load all ``.npy`` profiles from the profiles directory."""
        if not self._profiles_dir.exists():
            logger.debug("Profiles directory does not exist yet: %s", self._profiles_dir)
            return

        npy_files = list(self._profiles_dir.glob("*.npy"))
        for npy_path in npy_files:
            try:
                profile = SpeakerProfile.load(npy_path)
                self._profiles[profile.name] = profile
                logger.debug("Loaded speaker profile: %s", profile.name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load profile %s: %s", npy_path.name, exc)

        if self._profiles:
            logger.info("Loaded %d speaker profile(s)", len(self._profiles))

    # ------------------------------------------------------------------
    # Audio helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _bytes_to_float32(audio: bytes) -> np.ndarray:
        """Convert 16-bit PCM bytes to float32 in [-1.0, 1.0]."""
        pcm = np.frombuffer(audio, dtype=np.int16)
        return pcm.astype(np.float32) / 32768.0

    def _embed(self, audio: bytes) -> np.ndarray:
        """Extract a 256-dim embedding from raw 16-bit 16 kHz PCM audio."""
        if self._encoder is None:
            raise RuntimeError(
                "VoiceEncoder not available — install resemblyzer: pip install resemblyzer"
            )

        wav = self._bytes_to_float32(audio)
        duration_s = len(wav) / _SAMPLE_RATE
        if duration_s < _MIN_AUDIO_SECONDS:
            raise ValueError(
                f"Audio too short ({duration_s:.1f} s). "
                f"At least {_MIN_AUDIO_SECONDS:.0f} seconds of speech required."
            )

        # resemblyzer expects float32 in [-1, 1]
        preprocessed = preprocess_wav(wav, source_sr=_SAMPLE_RATE)
        embedding = self._encoder.embed_utterance(preprocessed)
        return embedding

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enroll(self, name: str, audio: bytes) -> SpeakerProfile:
        """Enroll a new speaker from a raw PCM audio sample.

        Parameters
        ----------
        name:
            Display name for the speaker.
        audio:
            Raw 16-bit 16 kHz mono PCM bytes (at least 3 seconds).

        Returns
        -------
        SpeakerProfile
            The newly created profile.

        Raises
        ------
        RuntimeError
            If resemblyzer is unavailable.
        ValueError
            If the audio sample is too short.
        """
        embedding = self._embed(audio)
        profile = SpeakerProfile(name=name, embedding=embedding)
        profile.save(self._profiles_dir)
        self._profiles[name] = profile
        logger.info("Enrolled speaker '%s' (embedding dim=%d)", name, len(embedding))
        return profile

    def identify(self, audio: bytes) -> Optional[tuple[str, float]]:
        """Identify a speaker from a raw PCM audio sample.

        Returns
        -------
        tuple[str, float] | None
            ``(name, confidence)`` if confidence exceeds the threshold,
            otherwise ``None``.
        """
        if not _RESEMBLYZER_AVAILABLE or self._encoder is None:
            logger.debug("Speaker identification unavailable (no encoder)")
            return None

        if not self._profiles:
            logger.debug("No speaker profiles enrolled")
            return None

        try:
            embedding = self._embed(audio)
        except (RuntimeError, ValueError) as exc:
            logger.debug("Cannot identify speaker: %s", exc)
            return None

        best_name: Optional[str] = None
        best_score: float = -1.0

        for name, profile in self._profiles.items():
            score = self._cosine_similarity(embedding, profile.embedding)
            if score > best_score:
                best_score = score
                best_name = name

        if best_name is not None and best_score >= self._threshold:
            logger.info("Identified speaker '%s' (confidence=%.3f)", best_name, best_score)
            return (best_name, best_score)

        logger.debug(
            "No confident match (best='%s', score=%.3f, threshold=%.2f)",
            best_name, best_score, self._threshold,
        )
        return None

    def get_profiles(self) -> list[SpeakerProfile]:
        """List all enrolled speaker profiles."""
        return list(self._profiles.values())

    def delete_profile(self, name: str) -> bool:
        """Remove a speaker profile by name.

        Returns ``True`` if a profile was deleted, ``False`` if not found.
        """
        profile = self._profiles.pop(name, None)
        if profile is None:
            logger.debug("delete_profile: '%s' not found", name)
            return False

        safe_name = SpeakerProfile._safe_filename(name)
        npy_path = self._profiles_dir / f"{safe_name}.npy"
        json_path = self._profiles_dir / f"{safe_name}.json"

        for p in (npy_path, json_path):
            try:
                p.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Could not delete %s: %s", p, exc)

        logger.info("Deleted speaker profile '%s'", name)
        return True

    def update_preferences(self, name: str, preferences: dict) -> bool:
        """Update stored preferences for an enrolled speaker.

        Returns ``True`` if the profile exists and was updated.
        """
        profile = self._profiles.get(name)
        if profile is None:
            return False

        profile.preferences.update(preferences)
        profile.save(self._profiles_dir)
        logger.debug("Updated preferences for '%s'", name)
        return True

    # ------------------------------------------------------------------
    # Math helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two vectors, clamped to [0, 1]."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        similarity = float(np.dot(a, b) / (norm_a * norm_b))
        return max(0.0, min(1.0, similarity))
