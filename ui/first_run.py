"""First-run setup wizard for trevo.

Shows on first launch to configure:
1. Welcome + overview
2. API Keys (Groq, Gemini, Google Cloud, etc.)
3. Memory Vault location
4. Voice enrollment (optional)
5. Summary + done
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from ui.styles import DARK_THEME


# ---------------------------------------------------------------------------
# Shared styling constants (match the project dark theme)
# ---------------------------------------------------------------------------
_ACCENT = "#7C3AED"
_BG_PRIMARY = "#0F0E17"
_BG_SECONDARY = "#1A1725"
_BG_TERTIARY = "#2D2640"
_TEXT_PRIMARY = "#F5F3FF"
_TEXT_SECONDARY = "#B8A8D0"

_WIZARD_QSS = DARK_THEME + """
/* ───────── Wizard-specific overrides ───────── */
QWizard {
    background-color: %(bg_primary)s;
}
QWizard > QWidget {
    background-color: %(bg_primary)s;
}

QLabel#wizardTitle {
    font-size: 28px;
    font-weight: bold;
    color: %(accent)s;
}
QLabel#wizardSubtitle {
    font-size: 14px;
    color: %(text_secondary)s;
    padding-bottom: 8px;
}
QLabel#featureItem {
    font-size: 13px;
    color: %(text_primary)s;
    padding: 4px 0;
}
QLabel#freeBadge {
    background-color: #22c55e;
    color: #000000;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: bold;
}
QLabel#optionalBadge {
    background-color: %(bg_tertiary)s;
    color: %(text_secondary)s;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
}
QLabel#summaryKey {
    color: %(text_secondary)s;
    font-size: 13px;
}
QLabel#summaryValue {
    color: %(text_primary)s;
    font-size: 13px;
    font-weight: bold;
}

QProgressBar#enrollLevel {
    background-color: %(bg_primary)s;
    border: none;
    border-radius: 3px;
    height: 8px;
}
QProgressBar#enrollLevel::chunk {
    background-color: %(accent)s;
    border-radius: 3px;
}
""" % {
    "accent": _ACCENT,
    "bg_primary": _BG_PRIMARY,
    "bg_secondary": _BG_SECONDARY,
    "bg_tertiary": _BG_TERTIARY,
    "text_primary": _TEXT_PRIMARY,
    "text_secondary": _TEXT_SECONDARY,
}


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  FirstRunWizard                                                          ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

class FirstRunWizard(QWizard):
    """Multi-page setup wizard shown on first launch."""

    finished_with_config = pyqtSignal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome to trevo")
        self.setMinimumSize(640, 480)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setStyleSheet(_WIZARD_QSS)

        # Pages
        self.addPage(WelcomePage())
        self.addPage(APIKeysPage())
        self.addPage(MemoryVaultPage())
        self.addPage(VoiceEnrollPage())
        self._summary_page = SummaryPage()
        self.addPage(self._summary_page)

        # Wire up the Finish button
        self.accepted.connect(self._on_finish)

    # ------------------------------------------------------------------
    # Collecting configuration
    # ------------------------------------------------------------------

    def get_config(self) -> dict[str, Any]:
        """Collect all wizard values into a config dict."""
        config: dict[str, Any] = {
            "general": {
                "hotkey": "ctrl+shift+space",
                "mode": "toggle",
                "auto_start": False,
                "start_minimized": True,
                "theme": "dark",
            },
            "stt": {
                "engine": "groq",
                "language": "auto",
                "groq_api_key": self.field("groq_key") or "",
                "gemini_api_key": self.field("gemini_key") or "",
                "google_cloud_api_key": self.field("google_cloud_key") or "",
                "openai_api_key": self.field("openai_key") or "",
            },
            "polishing": {
                "enabled": True,
                "provider": "groq",
                "groq_api_key": self.field("groq_key") or "",
                "gemini_api_key": self.field("gemini_key") or "",
                "anthropic_api_key": self.field("anthropic_key") or "",
                "openai_api_key": self.field("openai_key") or "",
            },
            "audio": {
                "input_device": "default",
                "sample_rate": 16000,
                "noise_gate_threshold": 0.01,
                "vad_sensitivity": 0.5,
                "save_audio": False,
            },
            "ui": {
                "bar_position": "top_center",
                "bar_opacity": 0.95,
                "show_interim_results": True,
                "font_size": 14,
                "notification_sounds": True,
            },
            "history": {
                "enabled": True,
                "max_entries": 10000,
                "auto_cleanup_days": 90,
            },
        }

        # Pick the best available engine based on which keys were provided
        if config["stt"]["groq_api_key"]:
            config["stt"]["engine"] = "groq"
            config["polishing"]["provider"] = "groq"
        elif config["stt"]["gemini_api_key"]:
            config["stt"]["engine"] = "gemini"
            config["polishing"]["provider"] = "gemini"
        elif config["stt"]["google_cloud_api_key"]:
            config["stt"]["engine"] = "google_cloud"

        return config

    def _on_finish(self) -> None:
        """Save configuration and emit signal."""
        config = self.get_config()
        vault_path = self.field("vault_path") or str(Path.home() / "trevo-vault")

        # Save config.toml
        try:
            from models.settings import Settings, get_config_path
            settings = Settings._from_dict(config)
            settings.save()
        except Exception:
            # Fallback: write config manually
            self._write_config_fallback(config)

        # Create vault directory
        Path(vault_path).mkdir(parents=True, exist_ok=True)

        self.finished_with_config.emit(config)

    @staticmethod
    def _write_config_fallback(config: dict[str, Any]) -> None:
        """Write config as TOML without requiring tomli_w."""
        app_dir = Path(
            os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
        ) / "trevo"
        app_dir.mkdir(parents=True, exist_ok=True)
        target = app_dir / "config.toml"

        try:
            from models.settings import Settings
            toml_str = Settings._dict_to_toml(config)
            target.write_text(toml_str, encoding="utf-8")
        except Exception:
            pass  # Best-effort; settings will use defaults


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Page 1: Welcome                                                         ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

class WelcomePage(QWizardPage):
    """Welcome page with app overview."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle("")
        self.setSubTitle("")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 16)
        layout.setSpacing(12)

        # Title
        title = QLabel("trevo")
        title.setObjectName("wizardTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Your AI-powered voice assistant for everything")
        subtitle.setObjectName("wizardSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(16)

        # Features list
        features = [
            "Voice-to-text dictation with best-in-class accuracy",
            "AI polishing — auto-corrects grammar and formatting",
            "Trevo Mode — conversational AI assistant",
            "Knowledge vault — linked notes from your voice",
            "Node-based workflows for automation",
            "Works everywhere — types into any application",
        ]
        for text in features:
            item = QLabel(f"  {text}")
            item.setObjectName("featureItem")
            layout.addWidget(item)

        layout.addStretch()

        hint = QLabel("This wizard will help you set up trevo in under a minute.")
        hint.setObjectName("wizardSubtitle")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Page 2: API Keys                                                        ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

class APIKeysPage(QWizardPage):
    """API key entry page."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle("API Keys")
        self.setSubTitle(
            "Enter at least one API key. Groq and Gemini are free!"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 12)
        layout.setSpacing(12)

        # --- Free tier keys (recommended) ---
        free_group = QGroupBox("Free APIs (recommended)")
        free_form = QFormLayout(free_group)
        free_form.setSpacing(10)
        free_form.setContentsMargins(16, 20, 16, 16)

        self._groq_key = self._api_key_row(
            free_form, "Groq:", "groq_key",
            "Free: console.groq.com/keys",
            badge="FREE",
        )

        self._gemini_key = self._api_key_row(
            free_form, "Gemini:", "gemini_key",
            "Free: aistudio.google.com/apikey",
            badge="FREE",
        )

        self._google_cloud_key = self._api_key_row(
            free_form, "Google Cloud:", "google_cloud_key",
            "Free tier: console.cloud.google.com",
            badge="FREE",
        )

        layout.addWidget(free_group)

        # --- Optional keys ---
        optional_group = QGroupBox("Optional APIs")
        opt_form = QFormLayout(optional_group)
        opt_form.setSpacing(10)
        opt_form.setContentsMargins(16, 20, 16, 16)

        self._openai_key = self._api_key_row(
            opt_form, "OpenAI:", "openai_key",
            "platform.openai.com/api-keys",
            badge="optional",
        )

        self._anthropic_key = self._api_key_row(
            opt_form, "Anthropic:", "anthropic_key",
            "console.anthropic.com/settings/keys",
            badge="optional",
        )

        layout.addWidget(optional_group)
        layout.addStretch()

    def _api_key_row(
        self,
        form: QFormLayout,
        label_text: str,
        field_name: str,
        placeholder: str,
        badge: str = "",
    ) -> QLineEdit:
        """Create a password-mode QLineEdit with an optional badge, register as a wizard field."""
        row = QHBoxLayout()
        edit = QLineEdit()
        edit.setEchoMode(QLineEdit.EchoMode.Password)
        edit.setPlaceholderText(placeholder)
        row.addWidget(edit, 1)

        if badge:
            badge_label = QLabel(badge.upper())
            if badge.lower() == "free":
                badge_label.setObjectName("freeBadge")
            else:
                badge_label.setObjectName("optionalBadge")
            row.addWidget(badge_label)

        form.addRow(label_text, row)
        self.registerField(field_name, edit)
        return edit


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Page 3: Memory Vault Location                                           ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

class MemoryVaultPage(QWizardPage):
    """Choose Memory Vault location."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle("Memory Vault")
        self.setSubTitle(
            "Choose where trevo saves your voice notes as .md files."
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 12)
        layout.setSpacing(16)

        desc = QLabel(
            "Your voice notes and transcripts are saved as Markdown (.md) files "
            "in a vault folder. You can open this folder in Obsidian, VS Code, "
            "or any text editor."
        )
        desc.setWordWrap(True)
        desc.setObjectName("wizardSubtitle")
        layout.addWidget(desc)

        # Path picker
        group = QGroupBox("Vault Location")
        gform = QFormLayout(group)
        gform.setSpacing(12)
        gform.setContentsMargins(16, 20, 16, 16)

        path_row = QHBoxLayout()
        default_vault = str(Path.home() / "trevo-vault")
        self._vault_edit = QLineEdit()
        self._vault_edit.setText(default_vault)
        self._vault_edit.setPlaceholderText(default_vault)
        path_row.addWidget(self._vault_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(browse_btn)

        gform.addRow("Folder:", path_row)
        layout.addWidget(group)

        self.registerField("vault_path", self._vault_edit)

        layout.addStretch()

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Vault Folder",
            self._vault_edit.text() or str(Path.home()),
        )
        if folder:
            self._vault_edit.setText(folder)


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Page 4: Voice Enrollment (optional)                                     ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

class VoiceEnrollPage(QWizardPage):
    """Optional voice enrollment."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle("Voice Enrollment (Optional)")
        self.setSubTitle(
            "Record a short sample so trevo can recognise your voice. You can skip this."
        )

        self._is_recording = False
        self._timer: QTimer | None = None
        self._elapsed = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 12)
        layout.setSpacing(16)

        prompt = QLabel('Press "Record" and say your name clearly.')
        prompt.setObjectName("featureItem")
        prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(prompt)

        layout.addSpacing(8)

        # Audio level bar
        self._level_bar = QProgressBar()
        self._level_bar.setObjectName("enrollLevel")
        self._level_bar.setRange(0, 100)
        self._level_bar.setValue(0)
        self._level_bar.setTextVisible(False)
        self._level_bar.setFixedHeight(10)
        layout.addWidget(self._level_bar)

        # Timer label
        self._timer_label = QLabel("0.0s / 5.0s")
        self._timer_label.setObjectName("wizardSubtitle")
        self._timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._timer_label)

        layout.addSpacing(8)

        # Record button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._record_btn = QPushButton("Record")
        self._record_btn.setObjectName("primaryButton")
        self._record_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._record_btn.setFixedWidth(140)
        self._record_btn.clicked.connect(self._toggle_recording)
        btn_row.addWidget(self._record_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Status
        self._status_label = QLabel("")
        self._status_label.setObjectName("wizardSubtitle")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)

        layout.addStretch()

        skip_hint = QLabel("This step is optional. You can enroll later from Settings.")
        skip_hint.setObjectName("wizardSubtitle")
        skip_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(skip_hint)

    def _toggle_recording(self) -> None:
        if self._is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        self._is_recording = True
        self._elapsed = 0
        self._record_btn.setText("Stop")
        self._status_label.setText("Recording...")
        self._level_bar.setValue(0)

        # Start a timer to simulate recording progress
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

        # Try to actually start recording
        try:
            from core.speaker_recognition import SpeakerRecognition
            self._speaker = SpeakerRecognition()
            self._speaker.start_enrollment()
        except Exception:
            pass  # Recording visualization still works

    def _on_tick(self) -> None:
        self._elapsed += 0.1
        self._timer_label.setText(f"{self._elapsed:.1f}s / 5.0s")

        # Simple fake level animation when real audio is not available
        import random
        self._level_bar.setValue(random.randint(20, 80))

        if self._elapsed >= 5.0:
            self._stop_recording()

    def _stop_recording(self) -> None:
        self._is_recording = False
        if self._timer:
            self._timer.stop()
            self._timer = None

        self._record_btn.setText("Record Again")
        self._level_bar.setValue(0)

        try:
            from core.speaker_recognition import SpeakerRecognition
            if hasattr(self, "_speaker"):
                self._speaker.stop_enrollment()
                self._status_label.setText("Voice sample saved!")
                return
        except Exception:
            pass

        self._status_label.setText(
            "Voice enrollment not available (speaker_recognition module not loaded)."
        )

    def isComplete(self) -> bool:
        """This page is always complete — enrollment is optional."""
        return True


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Page 5: Summary                                                         ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

class SummaryPage(QWizardPage):
    """Summary of configuration."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle("You're All Set!")
        self.setSubTitle("")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(24, 16, 24, 12)
        self._layout.setSpacing(12)

        self._summary_label = QLabel()
        self._summary_label.setWordWrap(True)
        self._summary_label.setObjectName("featureItem")
        self._layout.addWidget(self._summary_label)

        self._layout.addStretch()

        done_label = QLabel(
            "Click Finish to save your settings and start using trevo.\n"
            "You can change any of these later in Settings."
        )
        done_label.setObjectName("wizardSubtitle")
        done_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        done_label.setWordWrap(True)
        self._layout.addWidget(done_label)

    def initializePage(self) -> None:
        """Build the summary text from wizard fields when the page is shown."""
        groq = self.field("groq_key") or ""
        gemini = self.field("gemini_key") or ""
        google_cloud = self.field("google_cloud_key") or ""
        openai = self.field("openai_key") or ""
        anthropic = self.field("anthropic_key") or ""
        vault = self.field("vault_path") or str(Path.home() / "trevo-vault")

        # Determine engine
        if groq:
            engine = "Groq Whisper (free)"
        elif gemini:
            engine = "Gemini (free)"
        elif google_cloud:
            engine = "Google Cloud STT"
        elif openai:
            engine = "OpenAI Whisper"
        else:
            engine = "None configured yet"

        keys_configured = sum(bool(k) for k in [groq, gemini, google_cloud, openai, anthropic])

        lines = [
            f"<b>Speech Engine:</b> {engine}",
            f"<b>API Keys Configured:</b> {keys_configured}",
            f"<b>Memory Vault:</b> {vault}",
            f"<b>Polishing:</b> Enabled (using {'Groq' if groq else 'Gemini' if gemini else 'default'})",
            f"<b>Theme:</b> Dark",
            f"<b>Hotkey:</b> Ctrl+Shift+Space",
        ]
        self._summary_label.setText("<br><br>".join(lines))
