"""Tiny always-on-top ambient indicator widget for trevo.

Shows the current recording state (idle / listening / processing) as a
compact pill-shaped overlay anchored to the top-right corner of the screen.
Designed to be unobtrusive while still providing at-a-glance feedback.

All rendering is performed via QPainter in ``paintEvent`` — no child widgets,
no stylesheets, no pixmaps.
"""

from __future__ import annotations

import math
import time
from typing import Optional

from PyQt6.QtCore import (
    QPoint,
    QPointF,
    QRectF,
    QSettings,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QGuiApplication,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import QMenu, QWidget


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PILL_WIDTH: int = 120
PILL_HEIGHT: int = 36
PILL_RADIUS: int = 18  # full pill end-caps

SCREEN_MARGIN: int = 20  # px from screen edges

ANIM_FPS: int = 60
ANIM_INTERVAL_MS: int = 1000 // ANIM_FPS  # ~16 ms

# Colours
COLOR_BG = QColor(15, 14, 23, 217)            # rgba(15,14,23,0.85)
COLOR_BORDER = QColor(124, 58, 237, 64)        # rgba(124,58,237,0.25)
COLOR_TEXT = QColor(245, 243, 255)              # #F5F3FF
COLOR_IDLE_DOT = QColor(124, 58, 237)          # #7C3AED
COLOR_LISTENING = QColor(16, 185, 129)         # #10B981
COLOR_PROCESSING_START = QColor(124, 58, 237)  # #7C3AED
COLOR_PROCESSING_END = QColor(6, 182, 212)     # #06B6D4

# State labels
_STATE_LABELS: dict[str, str] = {
    "idle": "Ready",
    "listening": "Listening\u2026",
    "processing": "Processing\u2026",
}

# Settings persistence key
_SETTINGS_GROUP: str = "AmbientWidget"


class AmbientWidget(QWidget):
    """Compact always-on-top ambient recording indicator.

    Signals
    -------
    expand_requested
        Emitted when the user left-clicks the widget (open dictation bar).
    settings_requested
        Emitted from the right-click context menu.
    trevo_mode_requested
        Emitted from the right-click context menu.
    quit_requested
        Emitted from the right-click context menu.
    """

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------
    expand_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    trevo_mode_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # State ---------------------------------------------------------
        self._state: str = "idle"
        self._audio_level: float = 0.0

        # Animation clock (seconds since widget creation)
        self._t0: float = time.monotonic()
        self._phase: float = 0.0  # updated every tick

        # Drag support --------------------------------------------------
        self._drag_origin: Optional[QPoint] = None

        # Window flags --------------------------------------------------
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # hide from taskbar
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(PILL_WIDTH, PILL_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

        # Position ------------------------------------------------------
        self._restore_position()

        # Animation timer -----------------------------------------------
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._timer.start(ANIM_INTERVAL_MS)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_state(self, state: str) -> None:
        """Set the visual state of the widget.

        Parameters
        ----------
        state : str
            One of ``"idle"``, ``"listening"``, or ``"processing"``.
        """
        if state not in _STATE_LABELS:
            return
        self._state = state
        self.update()

    def update_audio_level(self, level: float) -> None:
        """Feed an audio-level sample (0.0 – 1.0) for the waveform bars.

        Only affects the ``"listening"`` state.

        Parameters
        ----------
        level : float
            Normalised audio level in [0.0, 1.0].
        """
        self._audio_level = max(0.0, min(1.0, level))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _tick(self) -> None:
        """Advance animation phase and repaint."""
        self._phase = time.monotonic() - self._t0
        self.update()

    def _restore_position(self) -> None:
        """Move widget to last saved position, or default top-right."""
        settings = QSettings("trevo", "trevo")
        settings.beginGroup(_SETTINGS_GROUP)
        saved = settings.value("pos")
        settings.endGroup()

        if saved is not None and isinstance(saved, QPoint):
            self.move(saved)
        else:
            self._move_to_default()

    def _move_to_default(self) -> None:
        """Anchor to top-right of the primary screen with margin."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.move(100, 100)
            return
        geo = screen.availableGeometry()
        x = geo.right() - PILL_WIDTH - SCREEN_MARGIN
        y = geo.top() + SCREEN_MARGIN
        self.move(x, y)

    def _save_position(self) -> None:
        """Persist the current position so it survives restarts."""
        settings = QSettings("trevo", "trevo")
        settings.beginGroup(_SETTINGS_GROUP)
        settings.setValue("pos", self.pos())
        settings.endGroup()

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------
    def _show_context_menu(self, global_pos: QPoint) -> None:
        """Build and display the right-click context menu."""
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu {"
            "  background: rgba(15, 14, 23, 0.92);"
            "  color: #F5F3FF;"
            "  border: 1px solid rgba(124, 58, 237, 0.25);"
            "  border-radius: 8px;"
            "  padding: 4px 0px;"
            "}"
            "QMenu::item {"
            "  padding: 6px 24px;"
            "}"
            "QMenu::item:selected {"
            "  background: rgba(124, 58, 237, 0.30);"
            "}"
        )

        act_settings = QAction("Settings", self)
        act_settings.triggered.connect(self.settings_requested.emit)

        act_trevo = QAction("Trevo Mode", self)
        act_trevo.triggered.connect(self.trevo_mode_requested.emit)

        act_quit = QAction("Quit", self)
        act_quit.triggered.connect(self.quit_requested.emit)

        menu.addAction(act_settings)
        menu.addAction(act_trevo)
        menu.addSeparator()
        menu.addAction(act_quit)

        menu.exec(global_pos)

    # ------------------------------------------------------------------
    # Qt event overrides
    # ------------------------------------------------------------------
    def paintEvent(self, _event: object) -> None:  # noqa: N802
        """Render the entire widget via QPainter."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = self.width()
        h = self.height()

        # --- background pill -------------------------------------------
        bg_rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)
        bg_path = QPainterPath()
        bg_path.addRoundedRect(bg_rect, PILL_RADIUS, PILL_RADIUS)

        p.setPen(QPen(COLOR_BORDER, 1.0))
        p.setBrush(QBrush(COLOR_BG))
        p.drawPath(bg_path)

        # --- state-specific indicator (left side) ----------------------
        indicator_cx = 20.0
        indicator_cy = h / 2.0

        if self._state == "idle":
            self._paint_idle_dot(p, indicator_cx, indicator_cy)
        elif self._state == "listening":
            self._paint_waveform(p, indicator_cx, indicator_cy)
        elif self._state == "processing":
            self._paint_spinner(p, indicator_cx, indicator_cy)

        # --- text label ------------------------------------------------
        font = QFont("Inter", 9)
        font.setPixelSize(11)
        p.setFont(font)
        p.setPen(QPen(COLOR_TEXT))

        label = _STATE_LABELS.get(self._state, "")
        text_rect = QRectF(36.0, 0.0, w - 40.0, float(h))
        p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, label)

        p.end()

    # --- idle: breathing dot -------------------------------------------
    def _paint_idle_dot(
        self, p: QPainter, cx: float, cy: float
    ) -> None:
        """Draw a purple dot with a subtle breathing glow (0.5 Hz)."""
        # Breathing factor: sinusoidal 0.5 Hz → period = 2s
        breath = 0.5 + 0.5 * math.sin(2.0 * math.pi * 0.5 * self._phase)

        # Outer glow
        glow_radius = 8.0 + 2.0 * breath
        glow_color = QColor(COLOR_IDLE_DOT)
        glow_color.setAlphaF(0.15 + 0.15 * breath)

        glow = QRadialGradient(QPointF(cx, cy), glow_radius)
        glow.setColorAt(0.0, glow_color)
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QPointF(cx, cy), glow_radius, glow_radius)

        # Solid dot
        dot_radius = 4.0 + 0.5 * breath
        p.setBrush(QBrush(COLOR_IDLE_DOT))
        p.drawEllipse(QPointF(cx, cy), dot_radius, dot_radius)

    # --- listening: waveform bars --------------------------------------
    def _paint_waveform(
        self, p: QPainter, cx: float, cy: float
    ) -> None:
        """Draw 3 animated mini bars whose height responds to audio level."""
        bar_w = 3.0
        gap = 2.5
        max_h = 14.0
        min_h = 3.0
        num_bars = 3
        total_w = num_bars * bar_w + (num_bars - 1) * gap
        start_x = cx - total_w / 2.0

        level = self._audio_level

        for i in range(num_bars):
            # Each bar has a slightly different phase offset for liveliness
            offset = i * 0.35
            wave = 0.5 + 0.5 * math.sin(
                2.0 * math.pi * 3.0 * self._phase + offset
            )
            # Blend between idle wobble and level-driven height
            factor = 0.3 * wave + 0.7 * level
            bar_h = min_h + (max_h - min_h) * factor

            x = start_x + i * (bar_w + gap)
            y = cy - bar_h / 2.0

            bar_path = QPainterPath()
            bar_path.addRoundedRect(
                QRectF(x, y, bar_w, bar_h), bar_w / 2.0, bar_w / 2.0
            )
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(COLOR_LISTENING))
            p.drawPath(bar_path)

    # --- processing: spinning gradient ring ----------------------------
    def _paint_spinner(
        self, p: QPainter, cx: float, cy: float
    ) -> None:
        """Draw a spinning ring with a purple-to-cyan conical gradient."""
        radius = 7.0
        ring_width = 2.5

        # Conical gradient rotating 360 deg/s
        angle_deg = (self._phase * 360.0) % 360.0
        gradient = QConicalGradient(QPointF(cx, cy), angle_deg)
        gradient.setColorAt(0.0, COLOR_PROCESSING_START)
        gradient.setColorAt(0.5, COLOR_PROCESSING_END)
        gradient.setColorAt(1.0, COLOR_PROCESSING_START)

        pen = QPen(QBrush(gradient), ring_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), radius, radius)

    # --- mouse events --------------------------------------------------
    def mousePressEvent(self, event: Optional[QMouseEvent]) -> None:  # noqa: N802
        """Start drag on left-button press."""
        if event is None:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint() - self.pos()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event: Optional[QMouseEvent]) -> None:  # noqa: N802
        """Move widget while dragging."""
        if (
            event is not None
            and self._drag_origin is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            self.move(event.globalPosition().toPoint() - self._drag_origin)
            event.accept()

    def mouseReleaseEvent(self, event: Optional[QMouseEvent]) -> None:  # noqa: N802
        """Finish drag and handle click."""
        if event is None:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            # If the mouse barely moved, treat it as a click
            if self._drag_origin is not None:
                delta = (
                    event.globalPosition().toPoint() - self.pos()
                ) - self._drag_origin
                if delta.manhattanLength() < 4:
                    self.expand_requested.emit()
            self._drag_origin = None
            self._save_position()
            event.accept()

    # --- lifecycle -----------------------------------------------------
    def showEvent(self, _event: object) -> None:  # noqa: N802
        """Ensure timer is running when the widget becomes visible."""
        if not self._timer.isActive():
            self._timer.start(ANIM_INTERVAL_MS)

    def hideEvent(self, _event: object) -> None:  # noqa: N802
        """Pause animation timer when hidden to save CPU."""
        self._timer.stop()

    def closeEvent(self, _event: object) -> None:  # noqa: N802
        """Persist position on close."""
        self._save_position()
        self._timer.stop()
