"""QSS stylesheets and theming for trevo.

Color System (2025-2026 Dark Glassmorphism):
    Background:    #0F0E17  (deep purple-black)
    Surface:       #1A1725  (purple-gray)
    Elevated:      #2D2640  (muted purple)
    Accent:        #7C3AED  (vibrant purple)
    Accent2:       #06B6D4  (cyan — processing)
    Success:       #10B981  (emerald)
    Error:         #EF4444  (red)
    Warning:       #F59E0B  (amber)
    Text:          #F5F3FF  (white-lavender)
    Text Dim:      #B8A8D0  (lavender mist)
    Glass:         rgba(22, 18, 35, 0.75)
    Border:        rgba(255, 255, 255, 0.08)

Typography:
    Primary:   "Inter", "Segoe UI Variable", "SF Pro Display", sans-serif
    Mono:      "JetBrains Mono", "Cascadia Code", "Fira Code", monospace
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Color constants (reused across themes)
# ---------------------------------------------------------------------------
_BG = "#0F0E17"
_SURFACE = "#1A1725"
_ELEVATED = "#2D2640"
_ACCENT = "#7C3AED"
_ACCENT_HOVER = "#6D28D9"
_ACCENT_PRESSED = "#5B21B6"
_ACCENT2 = "#06B6D4"
_SUCCESS = "#10B981"
_ERROR = "#EF4444"
_WARNING = "#F59E0B"
_TEXT = "#F5F3FF"
_TEXT_DIM = "#B8A8D0"
_TEXT_MUTED = "#8B7FA8"
_BORDER = "rgba(255, 255, 255, 0.08)"
_GLASS = "rgba(22, 18, 35, 0.75)"
_GLASS_BORDER = "rgba(255, 255, 255, 0.08)"
_HOVER_BG = "rgba(124, 58, 237, 0.12)"
_ACTIVE_BG = "rgba(124, 58, 237, 0.20)"

_FONT = '"Inter", "Segoe UI Variable", "SF Pro Display", sans-serif'
_MONO = '"JetBrains Mono", "Cascadia Code", "Fira Code", monospace'

DARK_THEME: str = f"""
/* ───────── Global ───────── */
QWidget {{
    background-color: {_BG};
    color: {_TEXT};
    font-family: {_FONT};
    font-size: 14px;
}}

QLabel {{
    color: {_TEXT};
}}

QLabel#secondaryLabel {{
    color: {_TEXT_DIM};
}}

/* ───────── Glass Panel (reusable) ───────── */
QFrame#glassPanel {{
    background-color: {_GLASS};
    border: 1px solid {_GLASS_BORDER};
    border-radius: 12px;
}}

/* ───────── Dictation Bar ───────── */
QWidget#DictationBar {{
    background-color: rgba(15, 14, 23, 0.88);
    border-radius: 20px;
    border: 1px solid rgba(124, 58, 237, 0.25);
}}

QLabel#transcriptPreview {{
    color: {_TEXT};
    font-size: 14px;
    padding: 4px 8px;
}}

QLabel#timerLabel {{
    color: {_TEXT_DIM};
    font-size: 12px;
    font-family: {_MONO};
}}

QLabel#languageBadge {{
    background-color: {_ELEVATED};
    color: {_TEXT};
    border-radius: 8px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: bold;
}}

QProgressBar#audioLevel {{
    background-color: {_BG};
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
}}
QProgressBar#audioLevel::chunk {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {_ACCENT}, stop:0.7 {_ACCENT2}, stop:1.0 {_ACCENT2}
    );
    border-radius: 3px;
}}

QPushButton#closeButton {{
    background-color: transparent;
    color: {_TEXT_DIM};
    border: none;
    font-size: 16px;
    font-weight: bold;
    padding: 2px 6px;
    border-radius: 10px;
}}
QPushButton#closeButton:hover {{
    background-color: {_ERROR};
    color: {_TEXT};
}}

/* ───────── Tray Menu ───────── */
QMenu {{
    background-color: {_SURFACE};
    border: 1px solid {_ELEVATED};
    border-radius: 8px;
    padding: 6px 0;
}}
QMenu::item {{
    padding: 8px 32px 8px 16px;
    color: {_TEXT};
}}
QMenu::item:selected {{
    background-color: {_HOVER_BG};
}}
QMenu::item:disabled {{
    color: {_TEXT_MUTED};
}}
QMenu::separator {{
    height: 1px;
    background-color: {_ELEVATED};
    margin: 4px 12px;
}}

/* ───────── Settings Dialog ───────── */
QDialog#SettingsDialog {{
    background-color: {_BG};
    min-width: 700px;
    min-height: 550px;
}}

/* Sidebar navigation */
QListWidget#settingsSidebar {{
    background-color: rgba(26, 23, 37, 0.6);
    border: none;
    border-right: 1px solid {_ELEVATED};
    padding: 8px 0;
    outline: none;
    font-size: 14px;
}}
QListWidget#settingsSidebar::item {{
    color: {_TEXT_DIM};
    padding: 10px 18px;
    border-left: 3px solid transparent;
    border-radius: 0;
}}
QListWidget#settingsSidebar::item:selected {{
    color: {_TEXT};
    background-color: {_ACTIVE_BG};
    border-left: 3px solid {_ACCENT};
}}
QListWidget#settingsSidebar::item:hover:!selected {{
    color: {_TEXT};
    background-color: {_HOVER_BG};
}}

/* Content area */
QStackedWidget#settingsContent {{
    background-color: {_SURFACE};
}}

/* Section header label */
QLabel#sectionHeader {{
    font-size: 18px;
    font-weight: 600;
    color: {_TEXT};
    padding-bottom: 2px;
}}

/* Ghost / Cancel button */
QPushButton#ghostButton {{
    background-color: rgba(45, 38, 64, 0.5);
    color: {_TEXT_DIM};
    border: 1px solid {_ELEVATED};
}}
QPushButton#ghostButton:hover {{
    background-color: {_ELEVATED};
    color: {_TEXT};
    border-color: {_ACCENT};
}}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {_BG};
    color: {_TEXT};
    border: 1px solid {_ELEVATED};
    border-radius: 8px;
    padding: 6px 12px;
    min-height: 30px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {_ACCENT};
}}

QComboBox::drop-down {{
    border: none;
    padding-right: 10px;
}}
QComboBox QAbstractItemView {{
    background-color: {_SURFACE};
    color: {_TEXT};
    selection-background-color: {_HOVER_BG};
    border: 1px solid {_ELEVATED};
    border-radius: 6px;
}}

QCheckBox {{
    color: {_TEXT};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1px solid {_ELEVATED};
    background-color: {_BG};
}}
QCheckBox::indicator:checked {{
    background-color: {_ACCENT};
    border-color: {_ACCENT};
}}

QSlider::groove:horizontal {{
    background-color: {_BG};
    height: 6px;
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background-color: {_ACCENT};
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}
QSlider::sub-page:horizontal {{
    background-color: {_ACCENT};
    border-radius: 3px;
}}

QPushButton {{
    background-color: {_ELEVATED};
    color: {_TEXT};
    border: none;
    border-radius: 8px;
    padding: 8px 20px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {_ACCENT};
}}
QPushButton:pressed {{
    background-color: {_ACCENT_PRESSED};
}}
QPushButton#primaryButton {{
    background-color: {_ACCENT};
}}
QPushButton#primaryButton:hover {{
    background-color: {_ACCENT_HOVER};
}}

QGroupBox {{
    border: 1px solid {_ELEVATED};
    border-radius: 10px;
    margin-top: 12px;
    padding-top: 16px;
    color: {_TEXT};
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}}

/* ───────── Transcript Viewer ───────── */
QDialog#TranscriptViewer {{
    background-color: {_BG};
    min-width: 800px;
    min-height: 560px;
}}

QTableWidget {{
    background-color: {_SURFACE};
    color: {_TEXT};
    border: 1px solid {_ELEVATED};
    border-radius: 8px;
    gridline-color: {_ELEVATED};
    selection-background-color: {_ACTIVE_BG};
    alternate-background-color: rgba(15, 14, 23, 0.5);
}}
QTableWidget::item {{
    padding: 6px 10px;
}}
QHeaderView::section {{
    background-color: {_BG};
    color: {_TEXT_DIM};
    border: none;
    border-bottom: 2px solid {_ELEVATED};
    padding: 8px;
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

QTextEdit#detailPanel {{
    background-color: {_BG};
    color: {_TEXT};
    border: 1px solid {_ELEVATED};
    border-radius: 8px;
    padding: 12px;
    font-size: 14px;
}}

QLineEdit#searchBar {{
    background-color: {_SURFACE};
    color: {_TEXT};
    border: 1px solid {_ELEVATED};
    border-radius: 12px;
    padding: 8px 16px;
    font-size: 14px;
}}
QLineEdit#searchBar:focus {{
    border-color: {_ACCENT};
}}

QDateEdit {{
    background-color: {_BG};
    color: {_TEXT};
    border: 1px solid {_ELEVATED};
    border-radius: 8px;
    padding: 6px 10px;
}}

QScrollBar:vertical {{
    background-color: transparent;
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background-color: {_ELEVATED};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {_ACCENT};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background-color: transparent;
    height: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background-color: {_ELEVATED};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {_ACCENT};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ───────── Workflow Editor ───────── */
QDialog#WorkflowEditor {{
    background-color: {_BG};
}}

/* ───────── Command Palette ───────── */
QWidget#CommandPalette {{
    background-color: rgba(15, 14, 23, 0.92);
    border: 1px solid rgba(124, 58, 237, 0.3);
    border-radius: 16px;
}}

QLineEdit#paletteSearch {{
    background-color: rgba(26, 23, 37, 0.8);
    color: {_TEXT};
    border: none;
    border-bottom: 1px solid {_ELEVATED};
    border-radius: 0;
    padding: 14px 16px;
    font-size: 16px;
}}
QLineEdit#paletteSearch:focus {{
    border-bottom: 1px solid {_ACCENT};
}}

QListWidget#paletteResults {{
    background-color: transparent;
    border: none;
    outline: none;
    padding: 4px 0;
}}
QListWidget#paletteResults::item {{
    color: {_TEXT};
    padding: 10px 16px;
    border-radius: 8px;
    margin: 1px 6px;
}}
QListWidget#paletteResults::item:selected {{
    background-color: {_ACTIVE_BG};
}}
QListWidget#paletteResults::item:hover:!selected {{
    background-color: {_HOVER_BG};
}}

/* ───────── Toast Notifications ───────── */
QWidget#ToastWidget {{
    border-radius: 12px;
    border: 1px solid {_GLASS_BORDER};
    padding: 12px 16px;
}}
QWidget#ToastSuccess {{
    background-color: rgba(16, 185, 129, 0.15);
    border: 1px solid rgba(16, 185, 129, 0.3);
}}
QWidget#ToastError {{
    background-color: rgba(239, 68, 68, 0.15);
    border: 1px solid rgba(239, 68, 68, 0.3);
}}
QWidget#ToastInfo {{
    background-color: rgba(6, 182, 212, 0.15);
    border: 1px solid rgba(6, 182, 212, 0.3);
}}
QWidget#ToastWarning {{
    background-color: rgba(245, 158, 11, 0.15);
    border: 1px solid rgba(245, 158, 11, 0.3);
}}

/* ───────── Ambient Widget ───────── */
QWidget#AmbientWidget {{
    background-color: rgba(15, 14, 23, 0.85);
    border: 1px solid rgba(124, 58, 237, 0.25);
    border-radius: 18px;
}}

/* ───────── Chat Bubbles (Trevo Mode) ───────── */
QLabel#chatBubbleUser {{
    background-color: rgba(124, 58, 237, 0.2);
    border: 1px solid rgba(124, 58, 237, 0.3);
    border-radius: 14px;
    padding: 10px 14px;
    color: {_TEXT};
    font-size: 13px;
}}
QLabel#chatBubbleTrevo {{
    background-color: rgba(26, 23, 37, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 14px;
    padding: 10px 14px;
    color: {_TEXT};
    font-size: 13px;
}}

/* ───────── Badge Styles ───────── */
QLabel#accentBadge {{
    background-color: {_ACCENT};
    color: {_TEXT};
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#successBadge {{
    background-color: {_SUCCESS};
    color: {_TEXT};
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}
"""

# ---------------------------------------------------------------------------
# Light Theme
# ---------------------------------------------------------------------------
_L_BG = "#FAFAF9"
_L_SURFACE = "#FFFFFF"
_L_ELEVATED = "#F0ECF5"
_L_BORDER = "#E5E0ED"
_L_TEXT = "#1A1625"
_L_TEXT_DIM = "#6B5F80"
_L_TEXT_MUTED = "#9B8FB0"
_L_ACCENT = "#7C3AED"
_L_ACCENT_HOVER = "#6D28D9"

LIGHT_THEME: str = f"""
/* ───────── Global ───────── */
QWidget {{
    background-color: {_L_BG};
    color: {_L_TEXT};
    font-family: {_FONT};
    font-size: 14px;
}}

QLabel {{
    color: {_L_TEXT};
}}

QLabel#secondaryLabel {{
    color: {_L_TEXT_DIM};
}}

/* ───────── Dictation Bar ───────── */
QWidget#DictationBar {{
    background-color: rgba(255, 255, 255, 0.92);
    border-radius: 20px;
    border: 1px solid rgba(124, 58, 237, 0.15);
}}

QLabel#transcriptPreview {{
    color: {_L_TEXT};
    font-size: 14px;
    padding: 4px 8px;
}}

QLabel#timerLabel {{
    color: {_L_TEXT_DIM};
    font-size: 12px;
    font-family: {_MONO};
}}

QLabel#languageBadge {{
    background-color: {_L_ELEVATED};
    color: {_L_TEXT};
    border-radius: 8px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: bold;
}}

QProgressBar#audioLevel {{
    background-color: {_L_ELEVATED};
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
}}
QProgressBar#audioLevel::chunk {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {_L_ACCENT}, stop:0.7 #06B6D4, stop:1.0 #06B6D4
    );
    border-radius: 3px;
}}

QPushButton#closeButton {{
    background-color: transparent;
    color: {_L_TEXT_DIM};
    border: none;
    font-size: 16px;
    font-weight: bold;
    padding: 2px 6px;
    border-radius: 10px;
}}
QPushButton#closeButton:hover {{
    background-color: #EF4444;
    color: #ffffff;
}}

/* ───────── Tray Menu ───────── */
QMenu {{
    background-color: {_L_SURFACE};
    border: 1px solid {_L_BORDER};
    border-radius: 8px;
    padding: 6px 0;
}}
QMenu::item {{
    padding: 8px 32px 8px 16px;
    color: {_L_TEXT};
}}
QMenu::item:selected {{
    background-color: rgba(124, 58, 237, 0.08);
}}
QMenu::item:disabled {{
    color: {_L_TEXT_MUTED};
}}
QMenu::separator {{
    height: 1px;
    background-color: {_L_BORDER};
    margin: 4px 12px;
}}

/* ───────── Settings Dialog ───────── */
QDialog#SettingsDialog {{
    background-color: {_L_BG};
    min-width: 700px;
    min-height: 550px;
}}

QListWidget#settingsSidebar {{
    background-color: {_L_SURFACE};
    border: none;
    border-right: 1px solid {_L_BORDER};
    padding: 8px 0;
    outline: none;
    font-size: 14px;
}}
QListWidget#settingsSidebar::item {{
    color: {_L_TEXT_DIM};
    padding: 10px 18px;
    border-left: 3px solid transparent;
    border-radius: 0;
}}
QListWidget#settingsSidebar::item:selected {{
    color: {_L_TEXT};
    background-color: rgba(124, 58, 237, 0.08);
    border-left: 3px solid {_L_ACCENT};
}}
QListWidget#settingsSidebar::item:hover:!selected {{
    color: {_L_TEXT};
    background-color: rgba(124, 58, 237, 0.04);
}}

QStackedWidget#settingsContent {{
    background-color: {_L_BG};
}}

QLabel#sectionHeader {{
    font-size: 18px;
    font-weight: 600;
    color: {_L_TEXT};
    padding-bottom: 2px;
}}

QPushButton#ghostButton {{
    background-color: {_L_ELEVATED};
    color: {_L_TEXT_DIM};
    border: 1px solid {_L_BORDER};
}}
QPushButton#ghostButton:hover {{
    background-color: {_L_BORDER};
    color: {_L_TEXT};
    border-color: {_L_ACCENT};
}}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {_L_SURFACE};
    color: {_L_TEXT};
    border: 1px solid {_L_BORDER};
    border-radius: 8px;
    padding: 6px 12px;
    min-height: 30px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {_L_ACCENT};
}}

QComboBox::drop-down {{
    border: none;
    padding-right: 10px;
}}
QComboBox QAbstractItemView {{
    background-color: {_L_SURFACE};
    color: {_L_TEXT};
    selection-background-color: rgba(124, 58, 237, 0.08);
    border: 1px solid {_L_BORDER};
    border-radius: 6px;
}}

QCheckBox {{
    color: {_L_TEXT};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1px solid {_L_BORDER};
    background-color: {_L_SURFACE};
}}
QCheckBox::indicator:checked {{
    background-color: {_L_ACCENT};
    border-color: {_L_ACCENT};
}}

QSlider::groove:horizontal {{
    background-color: {_L_ELEVATED};
    height: 6px;
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background-color: {_L_ACCENT};
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}
QSlider::sub-page:horizontal {{
    background-color: {_L_ACCENT};
    border-radius: 3px;
}}

QPushButton {{
    background-color: {_L_ELEVATED};
    color: {_L_TEXT};
    border: none;
    border-radius: 8px;
    padding: 8px 20px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {_L_ACCENT};
    color: #ffffff;
}}
QPushButton:pressed {{
    background-color: {_L_ACCENT_HOVER};
    color: #ffffff;
}}
QPushButton#primaryButton {{
    background-color: {_L_ACCENT};
    color: #ffffff;
}}
QPushButton#primaryButton:hover {{
    background-color: {_L_ACCENT_HOVER};
}}

QGroupBox {{
    border: 1px solid {_L_BORDER};
    border-radius: 10px;
    margin-top: 12px;
    padding-top: 16px;
    color: {_L_TEXT};
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}}

/* ───────── Transcript Viewer ───────── */
QDialog#TranscriptViewer {{
    background-color: {_L_BG};
    min-width: 800px;
    min-height: 560px;
}}

QTableWidget {{
    background-color: {_L_SURFACE};
    color: {_L_TEXT};
    border: 1px solid {_L_BORDER};
    border-radius: 8px;
    gridline-color: {_L_ELEVATED};
    selection-background-color: rgba(124, 58, 237, 0.1);
    alternate-background-color: {_L_BG};
}}
QTableWidget::item {{
    padding: 6px 10px;
}}
QHeaderView::section {{
    background-color: {_L_BG};
    color: {_L_TEXT_DIM};
    border: none;
    border-bottom: 2px solid {_L_BORDER};
    padding: 8px;
    font-weight: 600;
    font-size: 12px;
}}

QTextEdit#detailPanel {{
    background-color: {_L_SURFACE};
    color: {_L_TEXT};
    border: 1px solid {_L_BORDER};
    border-radius: 8px;
    padding: 12px;
    font-size: 14px;
}}

QLineEdit#searchBar {{
    background-color: {_L_SURFACE};
    color: {_L_TEXT};
    border: 1px solid {_L_BORDER};
    border-radius: 12px;
    padding: 8px 16px;
    font-size: 14px;
}}
QLineEdit#searchBar:focus {{
    border-color: {_L_ACCENT};
}}

QDateEdit {{
    background-color: {_L_SURFACE};
    color: {_L_TEXT};
    border: 1px solid {_L_BORDER};
    border-radius: 8px;
    padding: 6px 10px;
}}

QScrollBar:vertical {{
    background-color: transparent;
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background-color: {_L_BORDER};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {_L_ACCENT};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background-color: transparent;
    height: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background-color: {_L_BORDER};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {_L_ACCENT};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ───────── Command Palette ───────── */
QWidget#CommandPalette {{
    background-color: rgba(255, 255, 255, 0.95);
    border: 1px solid {_L_BORDER};
    border-radius: 16px;
}}

QLineEdit#paletteSearch {{
    background-color: transparent;
    color: {_L_TEXT};
    border: none;
    border-bottom: 1px solid {_L_BORDER};
    border-radius: 0;
    padding: 14px 16px;
    font-size: 16px;
}}
QLineEdit#paletteSearch:focus {{
    border-bottom: 1px solid {_L_ACCENT};
}}

QListWidget#paletteResults {{
    background-color: transparent;
    border: none;
    outline: none;
    padding: 4px 0;
}}
QListWidget#paletteResults::item {{
    color: {_L_TEXT};
    padding: 10px 16px;
    border-radius: 8px;
    margin: 1px 6px;
}}
QListWidget#paletteResults::item:selected {{
    background-color: rgba(124, 58, 237, 0.1);
}}
QListWidget#paletteResults::item:hover:!selected {{
    background-color: rgba(124, 58, 237, 0.05);
}}

/* ───────── Chat Bubbles ───────── */
QLabel#chatBubbleUser {{
    background-color: rgba(124, 58, 237, 0.1);
    border: 1px solid rgba(124, 58, 237, 0.2);
    border-radius: 14px;
    padding: 10px 14px;
    color: {_L_TEXT};
    font-size: 13px;
}}
QLabel#chatBubbleTrevo {{
    background-color: {_L_ELEVATED};
    border: 1px solid {_L_BORDER};
    border-radius: 14px;
    padding: 10px 14px;
    color: {_L_TEXT};
    font-size: 13px;
}}
"""

_THEMES: dict[str, str] = {
    "dark": DARK_THEME,
    "light": LIGHT_THEME,
}


def get_theme(name: str) -> str:
    """Return the QSS stylesheet for the given theme name.

    Args:
        name: Theme identifier, either ``"dark"`` or ``"light"``.

    Returns:
        The full QSS string for the requested theme.

    Raises:
        KeyError: If *name* is not a recognised theme.
    """
    key = name.strip().lower()
    if key not in _THEMES:
        raise KeyError(
            f"Unknown theme {name!r}. Available themes: {', '.join(_THEMES)}"
        )
    return _THEMES[key]
