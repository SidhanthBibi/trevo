"""QSS stylesheets and theming for trevo."""

from __future__ import annotations

DARK_THEME: str = """
/* ───────── Global ───────── */
QWidget {
    background-color: #1a1a2e;
    color: #eaeaea;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}

QLabel {
    color: #eaeaea;
}

QLabel#secondaryLabel {
    color: #a0a0b0;
}

/* ───────── Dictation Bar ───────── */
QWidget#DictationBar {
    background-color: rgba(22, 33, 62, 230);
    border-radius: 16px;
    border: 1px solid rgba(233, 69, 96, 0.3);
}

QLabel#transcriptPreview {
    color: #eaeaea;
    font-size: 14px;
    padding: 4px 8px;
}

QLabel#timerLabel {
    color: #a0a0b0;
    font-size: 12px;
    font-family: "Consolas", "Segoe UI", monospace;
}

QLabel#languageBadge {
    background-color: #0f3460;
    color: #eaeaea;
    border-radius: 8px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: bold;
}

QProgressBar#audioLevel {
    background-color: #1a1a2e;
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
}
QProgressBar#audioLevel::chunk {
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #4ade80, stop:0.7 #e94560, stop:1.0 #e94560
    );
    border-radius: 3px;
}

QPushButton#closeButton {
    background-color: transparent;
    color: #a0a0b0;
    border: none;
    font-size: 16px;
    font-weight: bold;
    padding: 2px 6px;
    border-radius: 10px;
}
QPushButton#closeButton:hover {
    background-color: #e94560;
    color: #eaeaea;
}

/* ───────── Tray Menu ───────── */
QMenu {
    background-color: #16213e;
    border: 1px solid #0f3460;
    border-radius: 8px;
    padding: 6px 0;
}
QMenu::item {
    padding: 8px 32px 8px 16px;
    color: #eaeaea;
}
QMenu::item:selected {
    background-color: #0f3460;
}
QMenu::item:disabled {
    color: #a0a0b0;
}
QMenu::separator {
    height: 1px;
    background-color: #0f3460;
    margin: 4px 12px;
}

/* ───────── Settings Dialog ───────── */
QDialog#SettingsDialog {
    background-color: #1a1a2e;
    min-width: 700px;
    min-height: 550px;
}

/* Sidebar navigation */
QListWidget#settingsSidebar {
    background-color: rgba(15, 52, 96, 0.45);
    border: none;
    border-right: 1px solid rgba(15, 52, 96, 0.6);
    padding: 8px 0;
    outline: none;
    font-size: 13px;
}
QListWidget#settingsSidebar::item {
    color: #a0a0b0;
    padding: 10px 18px;
    border-left: 3px solid transparent;
    border-radius: 0;
}
QListWidget#settingsSidebar::item:selected {
    color: #eaeaea;
    background-color: rgba(233, 69, 96, 0.12);
    border-left: 3px solid #e94560;
}
QListWidget#settingsSidebar::item:hover:!selected {
    color: #eaeaea;
    background-color: rgba(233, 69, 96, 0.06);
}

/* Content area */
QStackedWidget#settingsContent {
    background-color: #16213e;
}

/* Section header label */
QLabel#sectionHeader {
    font-size: 18px;
    font-weight: bold;
    color: #eaeaea;
    padding-bottom: 2px;
}

/* Ghost / Cancel button */
QPushButton#ghostButton {
    background-color: rgba(15, 52, 96, 0.4);
    color: #a0a0b0;
    border: 1px solid rgba(15, 52, 96, 0.6);
}
QPushButton#ghostButton:hover {
    background-color: rgba(15, 52, 96, 0.7);
    color: #eaeaea;
    border-color: #0f3460;
}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #1a1a2e;
    color: #eaeaea;
    border: 1px solid #0f3460;
    border-radius: 6px;
    padding: 6px 10px;
    min-height: 28px;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #e94560;
}

QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #16213e;
    color: #eaeaea;
    selection-background-color: #0f3460;
    border: 1px solid #0f3460;
    border-radius: 4px;
}

QCheckBox {
    color: #eaeaea;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #0f3460;
    background-color: #1a1a2e;
}
QCheckBox::indicator:checked {
    background-color: #e94560;
    border-color: #e94560;
}

QSlider::groove:horizontal {
    background-color: #1a1a2e;
    height: 6px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background-color: #e94560;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}
QSlider::sub-page:horizontal {
    background-color: #e94560;
    border-radius: 3px;
}

QPushButton {
    background-color: #0f3460;
    color: #eaeaea;
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #e94560;
}
QPushButton:pressed {
    background-color: #c73750;
}
QPushButton#primaryButton {
    background-color: #e94560;
}
QPushButton#primaryButton:hover {
    background-color: #c73750;
}

QGroupBox {
    border: 1px solid #0f3460;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 16px;
    color: #eaeaea;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

/* ───────── Transcript Viewer ───────── */
QDialog#TranscriptViewer {
    background-color: #1a1a2e;
    min-width: 800px;
    min-height: 560px;
}

QTableWidget {
    background-color: #16213e;
    color: #eaeaea;
    border: 1px solid #0f3460;
    border-radius: 6px;
    gridline-color: #0f3460;
    selection-background-color: rgba(233, 69, 96, 0.3);
    alternate-background-color: #1a1a2e;
}
QTableWidget::item {
    padding: 6px;
}
QHeaderView::section {
    background-color: #1a1a2e;
    color: #a0a0b0;
    border: none;
    border-bottom: 2px solid #0f3460;
    padding: 8px;
    font-weight: bold;
}

QTextEdit#detailPanel {
    background-color: #1a1a2e;
    color: #eaeaea;
    border: 1px solid #0f3460;
    border-radius: 6px;
    padding: 10px;
    font-size: 13px;
}

QLineEdit#searchBar {
    background-color: #16213e;
    color: #eaeaea;
    border: 1px solid #0f3460;
    border-radius: 10px;
    padding: 8px 16px;
    font-size: 13px;
}
QLineEdit#searchBar:focus {
    border-color: #e94560;
}

QDateEdit {
    background-color: #1a1a2e;
    color: #eaeaea;
    border: 1px solid #0f3460;
    border-radius: 6px;
    padding: 6px 10px;
}

QScrollBar:vertical {
    background-color: #1a1a2e;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background-color: #0f3460;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #e94560;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""

LIGHT_THEME: str = """
/* ───────── Global ───────── */
QWidget {
    background-color: #f5f5f7;
    color: #1c1c1e;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}

QLabel {
    color: #1c1c1e;
}

QLabel#secondaryLabel {
    color: #6e6e73;
}

/* ───────── Dictation Bar ───────── */
QWidget#DictationBar {
    background-color: rgba(255, 255, 255, 235);
    border-radius: 16px;
    border: 1px solid rgba(0, 0, 0, 0.08);
}

QLabel#transcriptPreview {
    color: #1c1c1e;
    font-size: 14px;
    padding: 4px 8px;
}

QLabel#timerLabel {
    color: #6e6e73;
    font-size: 12px;
    font-family: "Consolas", "Segoe UI", monospace;
}

QLabel#languageBadge {
    background-color: #e8edf4;
    color: #0f3460;
    border-radius: 8px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: bold;
}

QProgressBar#audioLevel {
    background-color: #e0e0e4;
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
}
QProgressBar#audioLevel::chunk {
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #34c759, stop:0.7 #ff3b30, stop:1.0 #ff3b30
    );
    border-radius: 3px;
}

QPushButton#closeButton {
    background-color: transparent;
    color: #6e6e73;
    border: none;
    font-size: 16px;
    font-weight: bold;
    padding: 2px 6px;
    border-radius: 10px;
}
QPushButton#closeButton:hover {
    background-color: #ff3b30;
    color: #ffffff;
}

/* ───────── Tray Menu ───────── */
QMenu {
    background-color: #ffffff;
    border: 1px solid #d1d1d6;
    border-radius: 8px;
    padding: 6px 0;
}
QMenu::item {
    padding: 8px 32px 8px 16px;
    color: #1c1c1e;
}
QMenu::item:selected {
    background-color: #e8edf4;
}
QMenu::item:disabled {
    color: #6e6e73;
}
QMenu::separator {
    height: 1px;
    background-color: #d1d1d6;
    margin: 4px 12px;
}

/* ───────── Settings Dialog ───────── */
QDialog#SettingsDialog {
    background-color: #f5f5f7;
    min-width: 640px;
    min-height: 480px;
}

QTabWidget::pane {
    background-color: #ffffff;
    border: 1px solid #d1d1d6;
    border-radius: 8px;
    padding: 12px;
}
QTabBar::tab {
    background-color: #f5f5f7;
    color: #6e6e73;
    padding: 10px 20px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #ffffff;
    color: #1c1c1e;
    border-bottom: 2px solid #e94560;
}
QTabBar::tab:hover:!selected {
    color: #1c1c1e;
}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #ffffff;
    color: #1c1c1e;
    border: 1px solid #d1d1d6;
    border-radius: 6px;
    padding: 6px 10px;
    min-height: 28px;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #e94560;
}

QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #1c1c1e;
    selection-background-color: #e8edf4;
    border: 1px solid #d1d1d6;
    border-radius: 4px;
}

QCheckBox {
    color: #1c1c1e;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #d1d1d6;
    background-color: #ffffff;
}
QCheckBox::indicator:checked {
    background-color: #e94560;
    border-color: #e94560;
}

QSlider::groove:horizontal {
    background-color: #e0e0e4;
    height: 6px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background-color: #e94560;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}
QSlider::sub-page:horizontal {
    background-color: #e94560;
    border-radius: 3px;
}

QPushButton {
    background-color: #e8edf4;
    color: #1c1c1e;
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #e94560;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: #c73750;
    color: #ffffff;
}
QPushButton#primaryButton {
    background-color: #e94560;
    color: #ffffff;
}
QPushButton#primaryButton:hover {
    background-color: #c73750;
}

QGroupBox {
    border: 1px solid #d1d1d6;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 16px;
    color: #1c1c1e;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

/* ───────── Transcript Viewer ───────── */
QDialog#TranscriptViewer {
    background-color: #f5f5f7;
    min-width: 800px;
    min-height: 560px;
}

QTableWidget {
    background-color: #ffffff;
    color: #1c1c1e;
    border: 1px solid #d1d1d6;
    border-radius: 6px;
    gridline-color: #e0e0e4;
    selection-background-color: rgba(233, 69, 96, 0.15);
    alternate-background-color: #f9f9fb;
}
QTableWidget::item {
    padding: 6px;
}
QHeaderView::section {
    background-color: #f5f5f7;
    color: #6e6e73;
    border: none;
    border-bottom: 2px solid #d1d1d6;
    padding: 8px;
    font-weight: bold;
}

QTextEdit#detailPanel {
    background-color: #ffffff;
    color: #1c1c1e;
    border: 1px solid #d1d1d6;
    border-radius: 6px;
    padding: 10px;
    font-size: 13px;
}

QLineEdit#searchBar {
    background-color: #ffffff;
    color: #1c1c1e;
    border: 1px solid #d1d1d6;
    border-radius: 10px;
    padding: 8px 16px;
    font-size: 13px;
}
QLineEdit#searchBar:focus {
    border-color: #e94560;
}

QDateEdit {
    background-color: #ffffff;
    color: #1c1c1e;
    border: 1px solid #d1d1d6;
    border-radius: 6px;
    padding: 6px 10px;
}

QScrollBar:vertical {
    background-color: #f5f5f7;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background-color: #d1d1d6;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #e94560;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
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
