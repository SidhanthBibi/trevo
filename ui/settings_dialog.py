"""Glassmorphism + shadcn-inspired settings dialog for trevo."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


# ── Sidebar section definitions ──────────────────────────────────────
_SECTIONS: list[tuple[str, str]] = [
    ("\u2699  General", "general"),
    ("\U0001f399  Speech Engine", "speech"),
    ("\u2728  AI Polishing", "polish"),
    ("\U0001f3a7  Audio", "audio"),
    ("\U0001f3a8  Appearance", "appearance"),
    ("\U0001f4dc  History", "history"),
    ("\U0001f4d6  Knowledge", "knowledge"),
]


class SettingsDialog(QDialog):
    """Modern sidebar-navigation settings dialog for trevo."""

    def __init__(
        self,
        settings: dict[str, Any] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsDialog")
        self.setWindowTitle("trevo - Settings")
        self.setMinimumSize(700, 550)

        self._settings: dict[str, Any] = settings or {}

        self._build_ui()
        self._load_settings(self._settings)

    # ──────────────────────────────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Main body: sidebar + content ──
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Sidebar
        self._sidebar = QListWidget()
        self._sidebar.setObjectName("settingsSidebar")
        self._sidebar.setFixedWidth(200)
        self._sidebar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._sidebar.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        for display, _key in _SECTIONS:
            item = QListWidgetItem(display)
            item.setSizeHint(QSize(200, 44))
            self._sidebar.addItem(item)
        self._sidebar.setCurrentRow(0)
        body.addWidget(self._sidebar)

        # Content stack
        self._stack = QStackedWidget()
        self._stack.setObjectName("settingsContent")

        self._stack.addWidget(self._build_general_page())
        self._stack.addWidget(self._build_speech_page())
        self._stack.addWidget(self._build_polish_page())
        self._stack.addWidget(self._build_audio_page())
        self._stack.addWidget(self._build_appearance_page())
        self._stack.addWidget(self._build_history_page())
        self._stack.addWidget(self._build_knowledge_page())

        body.addWidget(self._stack, 1)

        self._sidebar.currentRowChanged.connect(self._stack.setCurrentIndex)

        root.addLayout(body, 1)

        # ── Bottom bar ──
        bottom = QHBoxLayout()
        bottom.setContentsMargins(16, 10, 16, 14)
        bottom.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("ghostButton")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(self._cancel_btn)

        self._save_btn = QPushButton("Save")
        self._save_btn.setObjectName("primaryButton")
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.clicked.connect(self._on_save)
        bottom.addWidget(self._save_btn)

        root.addLayout(bottom)

    # ──────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _scrollable(inner: QWidget) -> QScrollArea:
        """Wrap *inner* in a scroll area for pages that may overflow."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(inner)
        return scroll

    @staticmethod
    def _slider_row(
        slider: QSlider, label: QLabel, suffix: str = ""
    ) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(slider, 1)
        row.addWidget(label)
        slider.valueChanged.connect(
            lambda v, lbl=label, s=suffix: lbl.setText(f"{v}{s}")
        )
        return row

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionHeader")
        return lbl

    # ──────────────────────────────────────────────────────────────────
    # Page builders
    # ──────────────────────────────────────────────────────────────────
    def _build_general_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(24, 20, 24, 12)
        outer.setSpacing(16)

        outer.addWidget(self._section_label("General"))

        group = QGroupBox("Preferences")
        form = QFormLayout(group)
        form.setSpacing(12)
        form.setContentsMargins(16, 20, 16, 16)

        self._hotkey_edit = QLineEdit()
        self._hotkey_edit.setPlaceholderText("e.g. Ctrl+Shift+Space")
        form.addRow("Hotkey:", self._hotkey_edit)

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Toggle", "Push-to-Talk"])
        form.addRow("Dictation mode:", self._mode_combo)

        self._auto_start_cb = QCheckBox("Launch trevo on system startup")
        form.addRow(self._auto_start_cb)

        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["Dark", "Light"])
        form.addRow("Theme:", self._theme_combo)

        outer.addWidget(group)
        outer.addStretch()
        return self._scrollable(page)

    # ──────────────────────────────────────────────────────────────────
    def _build_speech_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(24, 20, 24, 12)
        outer.setSpacing(16)

        outer.addWidget(self._section_label("Speech Engine"))

        # Engine selection
        engine_group = QGroupBox("Engine")
        eg = QFormLayout(engine_group)
        eg.setSpacing(12)
        eg.setContentsMargins(16, 20, 16, 16)

        self._engine_combo = QComboBox()
        self._engine_combo.addItem("Groq Whisper (Free)", "groq")
        self._engine_combo.addItem("Deepgram Nova-3", "deepgram")
        self._engine_combo.addItem("Whisper (Local)", "whisper_local")
        self._engine_combo.addItem("OpenAI Whisper", "openai")
        self._engine_combo.addItem("Gemini (Free)", "gemini")
        self._engine_combo.addItem("Google Cloud STT", "google_cloud")
        self._engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        eg.addRow("STT engine:", self._engine_combo)

        outer.addWidget(engine_group)

        # API keys
        keys_group = QGroupBox("API Keys")
        kg = QFormLayout(keys_group)
        kg.setSpacing(12)
        kg.setContentsMargins(16, 20, 16, 16)

        self._groq_stt_key = QLineEdit()
        self._groq_stt_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._groq_stt_key.setPlaceholderText("Free: console.groq.com")
        kg.addRow("Groq:", self._groq_stt_key)

        self._deepgram_key = QLineEdit()
        self._deepgram_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._deepgram_key.setPlaceholderText("Deepgram API key")
        kg.addRow("Deepgram:", self._deepgram_key)

        self._openai_stt_key = QLineEdit()
        self._openai_stt_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._openai_stt_key.setPlaceholderText("OpenAI API key")
        kg.addRow("OpenAI:", self._openai_stt_key)

        self._gemini_stt_key = QLineEdit()
        self._gemini_stt_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._gemini_stt_key.setPlaceholderText("Free: aistudio.google.com/apikey")
        kg.addRow("Gemini:", self._gemini_stt_key)

        self._google_cloud_stt_key = QLineEdit()
        self._google_cloud_stt_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._google_cloud_stt_key.setPlaceholderText("Google Cloud API key")
        kg.addRow("Google Cloud:", self._google_cloud_stt_key)

        outer.addWidget(keys_group)

        # Model settings
        model_group = QGroupBox("Model")
        mg = QFormLayout(model_group)
        mg.setSpacing(12)
        mg.setContentsMargins(16, 20, 16, 16)

        self._stt_model_combo = QComboBox()
        self._stt_model_combo.addItems([
            "nova-3",
            "nova-2",
            "nova-2-general",
            "whisper-large-v3",
            "whisper-1",
        ])
        mg.addRow("Model:", self._stt_model_combo)

        self._stt_language = QComboBox()
        self._stt_language.addItems([
            "en", "es", "fr", "de", "ja", "zh", "ko", "pt", "auto",
        ])
        mg.addRow("Language:", self._stt_language)

        outer.addWidget(model_group)
        outer.addStretch()
        return self._scrollable(page)

    # ──────────────────────────────────────────────────────────────────
    def _build_polish_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(24, 20, 24, 12)
        outer.setSpacing(16)

        outer.addWidget(self._section_label("AI Polishing"))

        self._polishing_enabled_cb = QCheckBox("Enable AI polishing")
        outer.addWidget(self._polishing_enabled_cb)

        provider_group = QGroupBox("Provider")
        pg = QFormLayout(provider_group)
        pg.setSpacing(12)
        pg.setContentsMargins(16, 20, 16, 16)

        self._polish_provider = QComboBox()
        self._polish_provider.addItem("Groq (Free)", "groq")
        self._polish_provider.addItem("Gemini (Free)", "gemini")
        self._polish_provider.addItem("Ollama (Local)", "ollama")
        self._polish_provider.addItem("OpenAI", "openai")
        self._polish_provider.addItem("Anthropic", "anthropic")
        self._polish_provider.addItem("None", "none")
        self._polish_provider.currentIndexChanged.connect(self._on_provider_changed)
        pg.addRow("Provider:", self._polish_provider)

        self._polish_api_key = QLineEdit()
        self._polish_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._polish_api_key.setPlaceholderText("API key for selected provider")
        pg.addRow("API key:", self._polish_api_key)

        self._polish_model = QComboBox()
        self._polish_model.addItems([
            "llama-3.3-70b-versatile", "gemini-2.0-flash",
            "llama3.2", "gpt-4o-mini", "gpt-4o",
            "claude-sonnet-4-20250514",
        ])
        pg.addRow("Model:", self._polish_model)

        outer.addWidget(provider_group)

        self._context_aware_cb = QCheckBox(
            "Context-aware polishing (use active app info)"
        )
        outer.addWidget(self._context_aware_cb)

        outer.addStretch()
        return self._scrollable(page)

    # ──────────────────────────────────────────────────────────────────
    def _build_audio_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(24, 20, 24, 12)
        outer.setSpacing(16)

        outer.addWidget(self._section_label("Audio"))

        device_group = QGroupBox("Input")
        dg = QFormLayout(device_group)
        dg.setSpacing(12)
        dg.setContentsMargins(16, 20, 16, 16)

        self._input_device_combo = QComboBox()
        self._populate_audio_devices()
        dg.addRow("Input device:", self._input_device_combo)

        self._sample_rate_combo = QComboBox()
        self._sample_rate_combo.addItems(["16000", "22050", "44100", "48000"])
        dg.addRow("Sample rate (Hz):", self._sample_rate_combo)

        outer.addWidget(device_group)

        processing_group = QGroupBox("Processing")
        proc = QFormLayout(processing_group)
        proc.setSpacing(12)
        proc.setContentsMargins(16, 20, 16, 16)

        # Noise gate slider
        self._noise_gate_slider = QSlider(Qt.Orientation.Horizontal)
        self._noise_gate_slider.setRange(0, 100)
        self._noise_gate_slider.setValue(20)
        self._noise_gate_label = QLabel("20")
        self._noise_gate_label.setMinimumWidth(28)
        self._noise_gate_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        proc.addRow(
            "Noise gate:",
            self._slider_row(self._noise_gate_slider, self._noise_gate_label),
        )

        # VAD sensitivity slider
        self._vad_slider = QSlider(Qt.Orientation.Horizontal)
        self._vad_slider.setRange(0, 100)
        self._vad_slider.setValue(50)
        self._vad_label = QLabel("50")
        self._vad_label.setMinimumWidth(28)
        self._vad_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        proc.addRow(
            "VAD sensitivity:",
            self._slider_row(self._vad_slider, self._vad_label),
        )

        outer.addWidget(processing_group)
        outer.addStretch()
        return self._scrollable(page)

    # ──────────────────────────────────────────────────────────────────
    def _build_appearance_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(24, 20, 24, 12)
        outer.setSpacing(16)

        outer.addWidget(self._section_label("Appearance"))

        group = QGroupBox("Dictation Bar")
        form = QFormLayout(group)
        form.setSpacing(12)
        form.setContentsMargins(16, 20, 16, 16)

        self._bar_position_combo = QComboBox()
        self._bar_position_combo.addItems([
            "Top Center", "Top Left", "Top Right", "Bottom Center",
        ])
        form.addRow("Bar position:", self._bar_position_combo)

        # Opacity slider
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(40, 100)
        self._opacity_slider.setValue(90)
        self._opacity_label = QLabel("90%")
        self._opacity_label.setMinimumWidth(36)
        self._opacity_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        form.addRow(
            "Opacity:",
            self._slider_row(self._opacity_slider, self._opacity_label, "%"),
        )

        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(10, 24)
        self._font_size_spin.setValue(13)
        self._font_size_spin.setSuffix(" px")
        form.addRow("Font size:", self._font_size_spin)

        self._show_interim_cb = QCheckBox("Show interim (partial) results")
        self._show_interim_cb.setChecked(True)
        form.addRow(self._show_interim_cb)

        outer.addWidget(group)
        outer.addStretch()
        return self._scrollable(page)

    # ──────────────────────────────────────────────────────────────────
    def _build_history_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(24, 20, 24, 12)
        outer.setSpacing(16)

        outer.addWidget(self._section_label("History"))

        group = QGroupBox("Transcript History")
        form = QFormLayout(group)
        form.setSpacing(12)
        form.setContentsMargins(16, 20, 16, 16)

        self._history_enabled_cb = QCheckBox("Enable transcript history")
        self._history_enabled_cb.setChecked(True)
        form.addRow(self._history_enabled_cb)

        self._max_entries_spin = QSpinBox()
        self._max_entries_spin.setRange(100, 100_000)
        self._max_entries_spin.setValue(5000)
        self._max_entries_spin.setSingleStep(500)
        form.addRow("Max entries:", self._max_entries_spin)

        self._auto_cleanup_spin = QSpinBox()
        self._auto_cleanup_spin.setRange(0, 365)
        self._auto_cleanup_spin.setValue(30)
        self._auto_cleanup_spin.setSuffix(" days")
        self._auto_cleanup_spin.setSpecialValueText("Never")
        form.addRow("Auto-cleanup after:", self._auto_cleanup_spin)

        outer.addWidget(group)
        outer.addStretch()
        return self._scrollable(page)

    # ──────────────────────────────────────────────────────────────────
    def _build_knowledge_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(24, 20, 24, 12)
        outer.setSpacing(16)

        outer.addWidget(self._section_label("Knowledge"))

        group = QGroupBox("Obsidian / Vault Integration")
        form = QFormLayout(group)
        form.setSpacing(12)
        form.setContentsMargins(16, 20, 16, 16)

        self._vault_path_edit = QLineEdit()
        self._vault_path_edit.setPlaceholderText("Path to Obsidian vault folder")
        form.addRow("Vault path:", self._vault_path_edit)

        self._auto_link_cb = QCheckBox("Auto-link transcripts to vault notes")
        form.addRow(self._auto_link_cb)

        self._daily_notes_cb = QCheckBox("Append to daily notes")
        form.addRow(self._daily_notes_cb)

        outer.addWidget(group)
        outer.addStretch()
        return self._scrollable(page)

    # ──────────────────────────────────────────────────────────────────
    # Audio device enumeration
    # ──────────────────────────────────────────────────────────────────
    def _populate_audio_devices(self) -> None:
        self._input_device_combo.clear()
        self._input_device_combo.addItem("System Default")
        try:
            import sounddevice as sd  # type: ignore[import-untyped]

            devices = sd.query_devices()
            for i, dev in enumerate(devices):  # type: ignore[arg-type]
                if dev.get("max_input_channels", 0) > 0:  # type: ignore[union-attr]
                    self._input_device_combo.addItem(dev["name"], userData=i)  # type: ignore[index]
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────
    # Load / Save
    # ──────────────────────────────────────────────────────────────────
    def _load_settings(self, s: dict[str, Any]) -> None:
        """Populate every widget from *s*."""
        if not s:
            return

        # General
        self._hotkey_edit.setText(s.get("hotkey", "Ctrl+Shift+Space"))
        idx = self._mode_combo.findText(
            s.get("mode", "Toggle"), Qt.MatchFlag.MatchFixedString
        )
        if idx >= 0:
            self._mode_combo.setCurrentIndex(idx)
        self._auto_start_cb.setChecked(s.get("auto_start", False))
        theme_idx = self._theme_combo.findText(
            s.get("theme", "Dark"), Qt.MatchFlag.MatchFixedString
        )
        if theme_idx >= 0:
            self._theme_combo.setCurrentIndex(theme_idx)

        # Speech Engine
        engine_val = s.get("stt_engine", "groq")
        for i in range(self._engine_combo.count()):
            if self._engine_combo.itemData(i) == engine_val:
                self._engine_combo.setCurrentIndex(i)
                break
        # Manually trigger engine change handler in case index didn't change
        self._on_engine_changed(self._engine_combo.currentIndex())
        self._groq_stt_key.setText(s.get("groq_stt_api_key", ""))
        self._deepgram_key.setText(s.get("deepgram_api_key", ""))
        self._openai_stt_key.setText(s.get("openai_api_key", ""))
        self._gemini_stt_key.setText(s.get("gemini_stt_api_key", ""))
        self._google_cloud_stt_key.setText(s.get("google_cloud_stt_api_key", ""))
        model_idx = self._stt_model_combo.findText(
            s.get("stt_model", "nova-3"), Qt.MatchFlag.MatchFixedString
        )
        if model_idx >= 0:
            self._stt_model_combo.setCurrentIndex(model_idx)
        lang_idx = self._stt_language.findText(
            s.get("stt_language", "en"), Qt.MatchFlag.MatchFixedString
        )
        if lang_idx >= 0:
            self._stt_language.setCurrentIndex(lang_idx)

        # AI Polishing
        self._polishing_enabled_cb.setChecked(s.get("polishing_enabled", True))
        provider_val = s.get("polish_provider", "groq")
        for i in range(self._polish_provider.count()):
            if self._polish_provider.itemData(i) == provider_val:
                self._polish_provider.setCurrentIndex(i)
                break
        self._polish_api_key.setText(s.get("polish_api_key", ""))
        pm_idx = self._polish_model.findText(
            s.get("polish_model", "gpt-4o-mini"), Qt.MatchFlag.MatchFixedString
        )
        if pm_idx >= 0:
            self._polish_model.setCurrentIndex(pm_idx)
        self._context_aware_cb.setChecked(s.get("context_aware", False))

        # Audio
        sr_idx = self._sample_rate_combo.findText(
            str(s.get("sample_rate", 16000)), Qt.MatchFlag.MatchFixedString
        )
        if sr_idx >= 0:
            self._sample_rate_combo.setCurrentIndex(sr_idx)
        self._noise_gate_slider.setValue(s.get("noise_gate", 20))
        self._vad_slider.setValue(s.get("vad_sensitivity", 50))

        # Appearance
        bp_idx = self._bar_position_combo.findText(
            s.get("bar_position", "Top Center"), Qt.MatchFlag.MatchFixedString
        )
        if bp_idx >= 0:
            self._bar_position_combo.setCurrentIndex(bp_idx)
        self._opacity_slider.setValue(s.get("opacity", 90))
        self._font_size_spin.setValue(s.get("font_size", 13))
        self._show_interim_cb.setChecked(s.get("show_interim", True))

        # History
        self._history_enabled_cb.setChecked(s.get("history_enabled", True))
        self._max_entries_spin.setValue(s.get("max_entries", 5000))
        self._auto_cleanup_spin.setValue(s.get("auto_cleanup_days", 30))

        # Knowledge
        self._vault_path_edit.setText(s.get("vault_path", ""))
        self._auto_link_cb.setChecked(s.get("auto_link", False))
        self._daily_notes_cb.setChecked(s.get("daily_notes", False))

    def get_settings(self) -> dict[str, Any]:
        """Collect all widget values into a flat settings dict."""
        return {
            # General
            "hotkey": self._hotkey_edit.text(),
            "mode": self._mode_combo.currentText(),
            "auto_start": self._auto_start_cb.isChecked(),
            "theme": self._theme_combo.currentText(),
            # Speech Engine
            "stt_engine": self._engine_combo.currentData() or self._engine_combo.currentText(),
            "groq_stt_api_key": self._groq_stt_key.text(),
            "deepgram_api_key": self._deepgram_key.text(),
            "openai_api_key": self._openai_stt_key.text(),
            "gemini_stt_api_key": self._gemini_stt_key.text(),
            "google_cloud_stt_api_key": self._google_cloud_stt_key.text(),
            "stt_model": self._stt_model_combo.currentText(),
            "stt_language": self._stt_language.currentText(),
            # AI Polishing
            "polishing_enabled": self._polishing_enabled_cb.isChecked(),
            "polish_provider": self._polish_provider.currentData() or self._polish_provider.currentText(),
            "polish_api_key": self._polish_api_key.text(),
            "polish_model": self._polish_model.currentText(),
            "context_aware": self._context_aware_cb.isChecked(),
            # Audio
            "input_device": self._input_device_combo.currentText(),
            "input_device_index": self._input_device_combo.currentData(),
            "sample_rate": int(self._sample_rate_combo.currentText()),
            "noise_gate": self._noise_gate_slider.value(),
            "vad_sensitivity": self._vad_slider.value(),
            # Appearance
            "bar_position": self._bar_position_combo.currentText(),
            "opacity": self._opacity_slider.value(),
            "font_size": self._font_size_spin.value(),
            "show_interim": self._show_interim_cb.isChecked(),
            # History
            "history_enabled": self._history_enabled_cb.isChecked(),
            "max_entries": self._max_entries_spin.value(),
            "auto_cleanup_days": self._auto_cleanup_spin.value(),
            # Knowledge
            "vault_path": self._vault_path_edit.text(),
            "auto_link": self._auto_link_cb.isChecked(),
            "daily_notes": self._daily_notes_cb.isChecked(),
        }

    # ──────────────────────────────────────────────────────────────────
    def _on_save(self) -> None:
        self._settings = self.get_settings()
        self.accept()

    def _on_engine_changed(self, _index: int) -> None:
        """React to engine selection changes."""
        engine = self._engine_combo.currentData()
        # Show/hide relevant key fields based on engine
        self._groq_stt_key.setEnabled(engine == "groq")
        self._deepgram_key.setEnabled(engine == "deepgram")
        self._openai_stt_key.setEnabled(engine == "openai")
        self._gemini_stt_key.setEnabled(engine == "gemini")
        self._google_cloud_stt_key.setEnabled(engine == "google_cloud")

    def _on_provider_changed(self, _index: int) -> None:
        """Update model suggestions based on provider selection."""
        provider = self._polish_provider.currentData()
        self._polish_model.clear()
        _models = {
            "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
            "gemini": ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
            "ollama": ["llama3.2", "llama3.1", "mistral", "phi3"],
            "openai": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"],
            "anthropic": ["claude-sonnet-4-20250514", "claude-3-5-haiku-20241022"],
            "none": [],
        }
        self._polish_model.addItems(_models.get(provider, []))
        self._polish_api_key.setEnabled(provider not in ("ollama", "none"))
