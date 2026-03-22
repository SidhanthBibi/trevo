"""Tests for trevo AudioCapture module."""
from __future__ import annotations

import math
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest

# We mock sounddevice before importing AudioCapture so the module loads
# without real audio hardware.
sd_mock = MagicMock()
with patch.dict("sys.modules", {"sounddevice": sd_mock}):
    from core.audio_capture import AudioCapture, SAMPLE_RATE, CHANNELS, CHUNK_SIZE


# ---------------------------------------------------------------------------
# Device enumeration
# ---------------------------------------------------------------------------

class TestDeviceEnumeration:
    """Test AudioCapture.list_devices and default_device."""

    def test_list_devices_returns_input_devices_only(self):
        fake_devices = [
            {"name": "Mic 1", "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 44100.0},
            {"name": "Speakers", "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 48000.0},
            {"name": "Mic 2", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 16000.0},
        ]
        sd_mock.query_devices.return_value = fake_devices

        devices = AudioCapture.list_devices()

        assert len(devices) == 2
        assert devices[0]["name"] == "Mic 1"
        assert devices[0]["channels"] == 2
        assert devices[1]["name"] == "Mic 2"

    def test_list_devices_empty_when_no_inputs(self):
        sd_mock.query_devices.return_value = [
            {"name": "Speakers", "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 48000.0},
        ]
        assert AudioCapture.list_devices() == []

    def test_default_device_returns_index(self):
        sd_mock.query_devices.return_value = {"index": 3, "name": "Default Mic"}
        sd_mock.query_devices.side_effect = None
        sd_mock.query_devices.return_value = {"index": 3, "name": "Default Mic"}

        result = AudioCapture.default_device()
        assert result == 3

    def test_default_device_returns_none_on_error(self):
        sd_mock.query_devices.side_effect = RuntimeError("no device")
        assert AudioCapture.default_device() is None
        sd_mock.query_devices.side_effect = None


# ---------------------------------------------------------------------------
# Start / Stop lifecycle
# ---------------------------------------------------------------------------

class TestStartStop:
    """Test the start and stop lifecycle of AudioCapture."""

    @patch("core.audio_capture.sd")
    def test_start_opens_stream(self, mock_sd):
        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream

        cap = AudioCapture.__new__(AudioCapture)
        # Manually init required attributes (avoid QObject.__init__ which needs Qt)
        cap._device = None
        cap._noise_gate_threshold = 0.01
        cap._stream = None
        cap._ring_buffer = MagicMock()
        cap._lock = MagicMock()
        cap._running = False
        cap.audio_chunk = MagicMock()
        cap.audio_level = MagicMock()

        cap.start()

        mock_sd.InputStream.assert_called_once()
        mock_stream.start.assert_called_once()
        assert cap._running is True

    @patch("core.audio_capture.sd")
    def test_start_twice_is_noop(self, mock_sd):
        cap = AudioCapture.__new__(AudioCapture)
        cap._device = None
        cap._noise_gate_threshold = 0.01
        cap._stream = MagicMock()
        cap._ring_buffer = MagicMock()
        cap._lock = MagicMock()
        cap._running = True
        cap.audio_chunk = MagicMock()
        cap.audio_level = MagicMock()

        cap.start()
        # Should not create a new stream because already running
        mock_sd.InputStream.assert_not_called()

    @patch("core.audio_capture.sd")
    def test_stop_closes_stream(self, mock_sd):
        mock_stream = MagicMock()

        cap = AudioCapture.__new__(AudioCapture)
        cap._device = None
        cap._noise_gate_threshold = 0.01
        cap._stream = mock_stream
        cap._ring_buffer = MagicMock()
        cap._lock = MagicMock()
        cap._running = True
        cap.audio_chunk = MagicMock()
        cap.audio_level = MagicMock()

        cap.stop()

        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()
        assert cap._running is False
        assert cap._stream is None

    @patch("core.audio_capture.sd")
    def test_stop_when_not_running_is_noop(self, mock_sd):
        cap = AudioCapture.__new__(AudioCapture)
        cap._running = False
        cap._stream = None

        cap.stop()  # should not raise


# ---------------------------------------------------------------------------
# Audio level (RMS) calculation
# ---------------------------------------------------------------------------

class TestAudioLevel:
    """Test the _compute_rms static method."""

    def test_silence_returns_zero(self):
        silence = np.zeros(512, dtype=np.int16)
        assert AudioCapture._compute_rms(silence) == 0.0

    def test_max_amplitude_returns_one(self):
        loud = np.full(512, 32767, dtype=np.int16)
        rms = AudioCapture._compute_rms(loud)
        assert rms == pytest.approx(1.0, abs=0.01)

    def test_known_rms_value(self):
        # A constant signal at half amplitude
        half = np.full(512, 16384, dtype=np.int16)
        rms = AudioCapture._compute_rms(half)
        expected = 16384.0 / 32768.0  # ~0.5
        assert rms == pytest.approx(expected, abs=0.01)

    def test_rms_clamped_to_one(self):
        # Even though int16 max is 32767, ensure we never exceed 1.0
        loud = np.full(512, 32767, dtype=np.int16)
        rms = AudioCapture._compute_rms(loud)
        assert rms <= 1.0


# ---------------------------------------------------------------------------
# Noise gate
# ---------------------------------------------------------------------------

class TestNoiseGate:
    """Test noise gate threshold property."""

    def test_noise_gate_threshold_setter_clamps_negative(self):
        cap = AudioCapture.__new__(AudioCapture)
        cap._noise_gate_threshold = 0.01

        cap.noise_gate_threshold = -0.5
        assert cap.noise_gate_threshold == 0.0

    def test_noise_gate_threshold_accepts_positive(self):
        cap = AudioCapture.__new__(AudioCapture)
        cap._noise_gate_threshold = 0.01

        cap.noise_gate_threshold = 0.05
        assert cap.noise_gate_threshold == 0.05
