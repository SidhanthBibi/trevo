"""System tray icon for trevo voice-to-text application."""

from __future__ import annotations

from enum import Enum, auto
from math import cos, sin, pi

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon, QWidget


class TrayState(Enum):
    """Visual states for the tray icon."""

    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()
    OFFLINE = auto()
    ERROR = auto()


# ---------------------------------------------------------------------------
# Icon colours
# ---------------------------------------------------------------------------
_STATE_COLORS: dict[TrayState, str] = {
    TrayState.IDLE: "#7C3AED",       # vibrant purple
    TrayState.RECORDING: "#EF4444",   # red
    TrayState.PROCESSING: "#06B6D4",  # cyan
    TrayState.OFFLINE: "#6B7280",     # gray
    TrayState.ERROR: "#EF4444",       # red
}

APP_TITLE: str = "trevo v1.0.0"
_ICON_SIZE: int = 64

# ---------------------------------------------------------------------------
# Menu stylesheet — translucent glass look
# ---------------------------------------------------------------------------
_MENU_STYLE = """
QMenu {
    background-color: rgba(15, 14, 23, 240);
    border: 1px solid rgba(124, 58, 237, 0.2);
    border-radius: 10px;
    padding: 6px 0px;
    color: #F5F3FF;
    font-family: "Inter", "Segoe UI Variable", "SF Pro Display", sans-serif;
    font-size: 14px;
}
QMenu::item {
    padding: 8px 24px 8px 16px;
    border-radius: 6px;
    margin: 1px 6px;
}
QMenu::item:selected {
    background-color: rgba(124, 58, 237, 0.25);
    color: #FFFFFF;
}
QMenu::item:disabled {
    color: rgba(184, 168, 208, 0.6);
}
QMenu::separator {
    height: 1px;
    background-color: rgba(124, 58, 237, 0.12);
    margin: 4px 12px;
}
"""


# ---------------------------------------------------------------------------
# Icon rendering helpers
# ---------------------------------------------------------------------------

def _draw_circle_background(
    painter: QPainter, size: int, hex_color: str, glow: bool = False
) -> None:
    """Draw a filled circle with a subtle radial gradient highlight."""
    base = QColor(hex_color)
    margin = 2
    diameter = size - 2 * margin

    # Radial gradient — lighter top-left highlight
    gradient = QRadialGradient(
        size * 0.38, size * 0.32, diameter * 0.7
    )
    lighter = QColor(base)
    lighter.setAlpha(255)
    # Brighten the highlight colour
    h, s, l, _ = lighter.getHslF()
    lighter.setHslF(h, max(0.0, s - 0.08), min(1.0, l + 0.18), 1.0)
    gradient.setColorAt(0.0, lighter)
    gradient.setColorAt(1.0, base)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(gradient))
    painter.drawEllipse(margin, margin, diameter, diameter)

    if glow:
        # Soft outer glow ring
        glow_color = QColor(base)
        glow_color.setAlpha(50)
        pen = QPen(glow_color, 2.5)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(0, 0, size, size)
        painter.setPen(Qt.PenStyle.NoPen)


def _draw_mic(painter: QPainter, size: int) -> None:
    """Draw a stylised microphone icon in white, centred on *size*."""
    white = QColor("#FFFFFF")
    cx = size / 2.0
    cy = size / 2.0

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(white)

    # Mic body — rounded rect
    body_w = size * 0.22
    body_h = size * 0.32
    body_x = cx - body_w / 2
    body_y = cy - body_h / 2 - size * 0.06
    painter.drawRoundedRect(
        int(body_x), int(body_y), int(body_w), int(body_h),
        body_w / 2, body_w / 2,
    )

    # Arc (the cradle around the mic head)
    pen = QPen(white, size * 0.045)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    arc_w = size * 0.36
    arc_h = size * 0.30
    arc_x = cx - arc_w / 2
    arc_y = cy - arc_h / 2 - size * 0.02

    from PyQt6.QtCore import QRectF

    painter.drawArc(
        QRectF(arc_x, arc_y, arc_w, arc_h),
        -30 * 16,   # startAngle (in 1/16 degrees)
        -120 * 16,  # spanAngle
    )

    # Stem below the arc
    stem_top_y = cy + arc_h / 2 - size * 0.04
    stem_bot_y = stem_top_y + size * 0.10
    painter.drawLine(
        int(cx), int(stem_top_y),
        int(cx), int(stem_bot_y),
    )

    # Small base
    base_half = size * 0.08
    painter.drawLine(
        int(cx - base_half), int(stem_bot_y),
        int(cx + base_half), int(stem_bot_y),
    )


def _draw_x_mark(painter: QPainter, size: int) -> None:
    """Draw a bold X in the centre of the icon."""
    pen = QPen(QColor("#FFFFFF"), size * 0.07)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)

    off = size * 0.28
    painter.drawLine(int(off), int(off), int(size - off), int(size - off))
    painter.drawLine(int(size - off), int(off), int(off), int(size - off))


def _draw_spinner(painter: QPainter, size: int, phase: int) -> None:
    """Draw a simple spinning indicator made of small dots."""
    cx = size / 2.0
    cy = size / 2.0
    radius = size * 0.28
    dot_count = 8
    dot_r = size * 0.04

    for i in range(dot_count):
        angle = 2 * pi * i / dot_count - pi / 2 + (phase * pi / 4)
        x = cx + radius * cos(angle)
        y = cy + radius * sin(angle)

        alpha = int(255 * ((i + 1) / dot_count))
        c = QColor(255, 255, 255, alpha)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(c)
        painter.drawEllipse(int(x - dot_r), int(y - dot_r), int(dot_r * 2), int(dot_r * 2))


# ---------------------------------------------------------------------------
# High-level icon builders
# ---------------------------------------------------------------------------

def _make_idle_icon() -> QIcon:
    pm = QPixmap(QSize(_ICON_SIZE, _ICON_SIZE))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    _draw_circle_background(p, _ICON_SIZE, _STATE_COLORS[TrayState.IDLE])
    _draw_mic(p, _ICON_SIZE)
    p.end()
    return QIcon(pm)


def _make_recording_icons() -> tuple[QIcon, QIcon]:
    """Return two slightly different icons used for the pulse animation."""
    icons: list[QIcon] = []
    for scale in (1.0, 0.92):
        pm = QPixmap(QSize(_ICON_SIZE, _ICON_SIZE))
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        offset = _ICON_SIZE * (1.0 - scale) / 2
        p.translate(offset, offset)
        p.scale(scale, scale)
        _draw_circle_background(p, _ICON_SIZE, _STATE_COLORS[TrayState.RECORDING], glow=(scale == 1.0))
        _draw_mic(p, _ICON_SIZE)
        p.end()
        icons.append(QIcon(pm))
    return icons[0], icons[1]


def _make_processing_icon(phase: int) -> QIcon:
    pm = QPixmap(QSize(_ICON_SIZE, _ICON_SIZE))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    _draw_circle_background(p, _ICON_SIZE, _STATE_COLORS[TrayState.PROCESSING])
    _draw_spinner(p, _ICON_SIZE, phase)
    p.end()
    return QIcon(pm)


def _make_offline_icon() -> QIcon:
    pm = QPixmap(QSize(_ICON_SIZE, _ICON_SIZE))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    _draw_circle_background(p, _ICON_SIZE, _STATE_COLORS[TrayState.OFFLINE])
    _draw_mic(p, _ICON_SIZE)
    p.end()
    return QIcon(pm)


def _make_error_icon() -> QIcon:
    pm = QPixmap(QSize(_ICON_SIZE, _ICON_SIZE))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    _draw_circle_background(p, _ICON_SIZE, _STATE_COLORS[TrayState.ERROR])
    _draw_x_mark(p, _ICON_SIZE)
    p.end()
    return QIcon(pm)


# ---------------------------------------------------------------------------
# TrayIcon
# ---------------------------------------------------------------------------

class TrayIcon(QSystemTrayIcon):
    """Polished system-tray icon for the trevo voice-to-text application."""

    # Signals
    dictation_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    history_requested = pyqtSignal()
    knowledge_requested = pyqtSignal()
    trevo_mode_requested = pyqtSignal()
    workflow_editor_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._state: TrayState = TrayState.IDLE
        self._anim_phase: int = 0

        # Pre-build static icons
        self._idle_icon: QIcon = _make_idle_icon()
        self._recording_icons: tuple[QIcon, QIcon] = _make_recording_icons()
        self._offline_icon: QIcon = _make_offline_icon()
        self._error_icon: QIcon = _make_error_icon()

        # Animation timer (shared by recording pulse + processing spinner)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(400)
        self._anim_timer.timeout.connect(self._on_anim_tick)

        self.setToolTip(APP_TITLE)
        self._apply_icon()

        self._build_menu()

        # Double-click emits dictation_requested
        self.activated.connect(self._on_activated)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------
    def _build_menu(self) -> None:
        menu = QMenu()
        menu.setStyleSheet(_MENU_STYLE)

        # Title
        title_action = QAction(APP_TITLE, self)
        title_action.setEnabled(False)
        title_font = QFont("Inter", 10)
        title_font.setBold(True)
        title_action.setFont(title_font)
        menu.addAction(title_action)

        menu.addSeparator()

        # Dictation toggle
        self._dictation_action = QAction("Start Dictation\tRCtrl ×2", self)
        self._dictation_action.triggered.connect(self.dictation_requested.emit)
        menu.addAction(self._dictation_action)

        act_trevo_mode = QAction("Trevo Mode\tRCtrl ×4", self)
        act_trevo_mode.triggered.connect(self.trevo_mode_requested.emit)
        menu.addAction(act_trevo_mode)

        act_workflow = QAction("Workflow Editor", self)
        act_workflow.triggered.connect(self.workflow_editor_requested.emit)
        menu.addAction(act_workflow)

        menu.addSeparator()

        # Navigation actions
        act_history = QAction("Transcript History", self)
        act_history.triggered.connect(self.history_requested.emit)
        menu.addAction(act_history)

        act_settings = QAction("Settings", self)
        act_settings.triggered.connect(self.settings_requested.emit)
        menu.addAction(act_settings)

        act_knowledge = QAction("Knowledge Vault", self)
        act_knowledge.triggered.connect(self.knowledge_requested.emit)
        menu.addAction(act_knowledge)

        menu.addSeparator()

        # Status indicators (disabled / informational)
        self._engine_action = QAction("Engine: —", self)
        self._engine_action.setEnabled(False)
        menu.addAction(self._engine_action)

        self._language_action = QAction("Language: Auto-detect", self)
        self._language_action.setEnabled(False)
        menu.addAction(self._language_action)

        menu.addSeparator()

        act_quit = QAction("Quit", self)
        act_quit.triggered.connect(self.quit_requested.emit)
        menu.addAction(act_quit)

        self.setContextMenu(menu)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_state(self, state: TrayState) -> None:
        """Set the tray icon visual state."""
        if state == self._state:
            return
        self._state = state
        self._anim_phase = 0

        # Start or stop animation timer as needed
        needs_anim = state in (TrayState.RECORDING, TrayState.PROCESSING)
        if needs_anim and not self._anim_timer.isActive():
            self._anim_timer.start()
        elif not needs_anim and self._anim_timer.isActive():
            self._anim_timer.stop()

        self._apply_icon()
        self._update_tooltip()

    def set_engine_status(self, text: str) -> None:
        """Update the engine info line in the context menu."""
        self._engine_action.setText(f"Engine: {text}")

    def set_language_status(self, text: str) -> None:
        """Update the language info line in the context menu."""
        self._language_action.setText(f"Language: {text}")

    def set_dictating(self, active: bool) -> None:
        """Convenience method: switch between RECORDING and IDLE states."""
        self._dictation_action.setText(
            "Stop Dictation\tRCtrl ×2" if active
            else "Start Dictation\tRCtrl ×2"
        )
        self.set_state(TrayState.RECORDING if active else TrayState.IDLE)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _apply_icon(self) -> None:
        """Set the actual QIcon based on current state and animation phase."""
        state = self._state
        if state is TrayState.IDLE:
            self.setIcon(self._idle_icon)
        elif state is TrayState.RECORDING:
            self.setIcon(self._recording_icons[self._anim_phase % 2])
        elif state is TrayState.PROCESSING:
            self.setIcon(_make_processing_icon(self._anim_phase))
        elif state is TrayState.OFFLINE:
            self.setIcon(self._offline_icon)
        elif state is TrayState.ERROR:
            self.setIcon(self._error_icon)

    def _update_tooltip(self) -> None:
        labels = {
            TrayState.IDLE: "trevo — Ready",
            TrayState.RECORDING: "trevo — Recording",
            TrayState.PROCESSING: "trevo — Processing",
            TrayState.OFFLINE: "trevo — Offline",
            TrayState.ERROR: "trevo — Error",
        }
        self.setToolTip(labels.get(self._state, APP_TITLE))

    def _on_anim_tick(self) -> None:
        self._anim_phase += 1
        self._apply_icon()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.dictation_requested.emit()
