import io
import wave

import numpy as np


def pcm_to_bytes(audio: np.ndarray, dtype=np.int16) -> bytes:
    """Convert numpy float32 audio to PCM bytes."""
    if audio.dtype != dtype:
        if dtype == np.int16:
            audio = (audio * 32767).clip(-32768, 32767).astype(np.int16)
        else:
            audio = audio.astype(dtype)
    return audio.tobytes()


def bytes_to_pcm(data: bytes, dtype=np.int16) -> np.ndarray:
    return np.frombuffer(data, dtype=dtype)


def calculate_rms(audio: np.ndarray) -> float:
    """Return RMS level (0.0–1.0) for audio level meter."""
    if audio.dtype == np.int16:
        audio = audio.astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(audio ** 2)))
    return min(1.0, rms * 10)  # scale for display


def int16_to_float32(audio: np.ndarray) -> np.ndarray:
    """Convert int16 PCM to float32 in [-1.0, 1.0]."""
    if audio.dtype == np.int16:
        return audio.astype(np.float32) / 32768.0
    return audio


def pcm_to_wav(pcm_data: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    """Wrap raw int16 PCM bytes in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return buf.getvalue()


def normalize_audio(audio: np.ndarray, target_rms: float = 0.1) -> np.ndarray:
    """Normalize audio to a target RMS level."""
    if audio.dtype == np.int16:
        audio = audio.astype(np.float32) / 32768.0
    current_rms = float(np.sqrt(np.mean(audio ** 2)))
    if current_rms < 1e-6:
        return audio
    gain = target_rms / current_rms
    gain = min(gain, 10.0)  # cap gain to avoid clipping
    return (audio * gain).clip(-1.0, 1.0)
