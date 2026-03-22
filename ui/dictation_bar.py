"""Floating glassmorphism dictation bar for trevo.

Hero UI element — the floating bar users see when recording.
Uses PyQt6 + optional qframelesswindow for native Windows acrylic blur.
Falls back to WA_TranslucentBackground with custom painting if unavailable.
"""

from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSequentialAnimationGroup,
    QSize,
    Qt,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Try to use qframelesswindow for native acrylic blur on Windows
# ---------------------------------------------------------------------------
_USE_ACRYLIC = False
_AcrylicBase: type = QWidget

try:
    from qframelesswindow import AcrylicWindow  # type: ignore[import-untyped]

    _AcrylicBase = AcrylicWindow  # type: ignore[assignment,misc]
    _USE_ACRYLIC = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BAR_WIDTH = 460
BAR_RADIUS = 20
BAR_TOP_MARGIN = 32

COLOR_BG = QColor(15, 15, 25, 209)  # rgba(15,15,25,0.82)
COLOR_BORDER = QColor(255, 255, 255, 20)  # rgba(255,255,255,0.08)
COLOR_TEXT_PRIMARY = QColor(255, 255, 255, 217)  # rgba(255,255,255,0.85)
COLOR_TEXT_SECONDARY = QColor(255, 255, 255, 140)  # rgba(255,255,255,0.55)
COLOR_TEXT_MUTED = QColor(255, 255, 255, 102)  # rgba(255,255,255,0.4)
COLOR_GLASS_PILL = QColor(255, 255, 255, 20)  # rgba(255,255,255,0.08)
COLOR_GLASS_PILL_BORDER = QColor(255, 255, 255, 31)  # rgba(255,255,255,0.12)
COLOR_LEVEL_BG = QColor(255, 255, 255, 15)  # rgba(255,255,255,0.06)
COLOR_LEVEL_BLUE = QColor(59, 130, 246)  # #3B82F6
COLOR_LEVEL_RED = QColor(255, 59, 92)  # #FF3B5C
COLOR_IDLE_ORB = QColor(30, 30, 50, 200)
COLOR_RECORDING = QColor(255, 59, 92)  # #FF3B5C
COLOR_CLOSE_HOVER = QColor(255, 255, 255, 38)  # rgba(255,255,255,0.15)

ANIM_FPS = 60
ANIM_INTERVAL = 1000 // ANIM_FPS  # ~16ms


def _mono_font(size: int = 12) -> QFont:
    """Return a monospace font, preferring Cascadia Code."""
    for family in ("Cascadia Code", "Consolas", "Courier New"):
        fid = QFontDatabase.font(family, "", size)
        if fid.family().lower().startswith(family.lower().split()[0].lower()):
            f = QFont(family, size)
            f.setStyleHint(QFont.StyleHint.Monospace)
            return f
    f = QFont("monospace", size)
    f.setStyleHint(QFont.StyleHint.Monospace)
    return f


def _ui_font(size: int = 12, bold: bool = False) -> QFont:
    """Return a clean UI font."""
    for family in ("Segoe UI", "SF Pro Display", "Inter", "Helvetica Neue"):
        f = QFont(family, size)
        if bold:
            f.setBold(True)
        return f
    f = QFont("sans-serif", size)
    if bold:
        f.setBold(True)
    return f


# ═══════════════════════════════════════════════════════════════════════════
# MicOrb — custom-painted recording indicator
# ═══════════════════════════════════════════════════════════════════════════
class _MicOrb(QWidget):
    """32x32 circular mic indicator with three visual states.

    States: idle, recording (pulsing red glow), processing (spinning arc).
    All rendering via QPainter at ~60fps.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(32, 32)

        self._state: str = "idle"  # idle | recording | processing

        # Animation state
        self._pulse_phase: float = 0.0  # 0..1 for recording pulse cycle
        self._spin_angle: float = 0.0  # degrees for processing spinner
        self._ring_opacity: float = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(ANIM_INTERVAL)
        self._timer.timeout.connect(self._tick)

    def set_state(self, state: str) -> None:
        self._state = state
        if state in ("recording", "processing"):
            self._pulse_phase = 0.0
            self._spin_angle = 0.0
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def _tick(self) -> None:
        dt = ANIM_INTERVAL / 1000.0
        if self._state == "recording":
            # Pulse cycle: 1200ms loop
            self._pulse_phase = (self._pulse_phase + dt / 1.2) % 1.0
        elif self._state == "processing":
            # Spinner: 1000ms per revolution
            self._spin_angle = (self._spin_angle + 360.0 * dt) % 360.0
        self.update()

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2.0, self.height() / 2.0

        if self._state == "recording":
            self._paint_recording(p, cx, cy)
        elif self._state == "processing":
            self._paint_processing(p, cx, cy)
        else:
            self._paint_idle(p, cx, cy)

        # Mic icon (always drawn on top)
        self._paint_mic_icon(p, cx, cy)
        p.end()

    def _paint_idle(self, p: QPainter, cx: float, cy: float) -> None:
        """Dark glass circle."""
        p.setPen(QPen(QColor(255, 255, 255, 15), 1.0))
        p.setBrush(COLOR_IDLE_ORB)
        p.drawEllipse(QPointF(cx, cy), 14, 14)

    def _paint_recording(self, p: QPainter, cx: float, cy: float) -> None:
        """Pulsing red/coral glow with animated rings."""
        # Outer pulse ring: radius 16→24, opacity 0.6→0
        ring_r = 16.0 + 8.0 * self._pulse_phase
        ring_alpha = int(153 * (1.0 - self._pulse_phase))  # 0.6*255=153
        ring_color = QColor(COLOR_RECORDING)
        ring_color.setAlpha(ring_alpha)
        p.setPen(QPen(ring_color, 2.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), ring_r, ring_r)

        # Second ring (offset phase)
        phase2 = (self._pulse_phase + 0.5) % 1.0
        ring_r2 = 16.0 + 8.0 * phase2
        ring_alpha2 = int(100 * (1.0 - phase2))
        ring_color2 = QColor(COLOR_RECORDING)
        ring_color2.setAlpha(ring_alpha2)
        p.setPen(QPen(ring_color2, 1.5))
        p.drawEllipse(QPointF(cx, cy), ring_r2, ring_r2)

        # Core glow
        glow = QRadialGradient(QPointF(cx, cy), 16)
        glow.setColorAt(0.0, QColor(255, 59, 92, 200))
        glow.setColorAt(0.6, QColor(255, 59, 92, 120))
        glow.setColorAt(1.0, QColor(255, 59, 92, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QPointF(cx, cy), 16, 16)

        # Solid inner circle
        p.setBrush(COLOR_RECORDING)
        p.drawEllipse(QPointF(cx, cy), 10, 10)

    def _paint_processing(self, p: QPainter, cx: float, cy: float) -> None:
        """Spinning gradient arc."""
        # Background circle
        p.setPen(QPen(QColor(255, 255, 255, 15), 1.0))
        p.setBrush(COLOR_IDLE_ORB)
        p.drawEllipse(QPointF(cx, cy), 14, 14)

        # Spinning arc
        arc_rect = QRectF(cx - 13, cy - 13, 26, 26)
        grad = QConicalGradient(QPointF(cx, cy), -self._spin_angle)
        grad.setColorAt(0.0, QColor(59, 130, 246, 220))
        grad.setColorAt(0.35, QColor(139, 92, 246, 180))
        grad.setColorAt(0.7, QColor(255, 59, 92, 60))
        grad.setColorAt(1.0, QColor(59, 130, 246, 0))

        pen = QPen(QBrush(grad), 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        # Draw an arc spanning 270 degrees
        start = int(self._spin_angle * 16)
        span = 270 * 16
        p.drawArc(arc_rect, start, span)

    def _paint_mic_icon(self, p: QPainter, cx: float, cy: float) -> None:
        """Draw a minimal mic icon with QPainter."""
        icon_color = QColor(255, 255, 255, 230) if self._state != "idle" else QColor(255, 255, 255, 160)
        pen = QPen(icon_color, 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        # Mic body (rounded rect approximation)
        mic_w, mic_h = 4.0, 6.0
        mic_rect = QRectF(cx - mic_w / 2, cy - mic_h / 2 - 1, mic_w, mic_h)
        p.drawRoundedRect(mic_rect, 2.0, 2.0)

        # Mic cup (arc below)
        cup_rect = QRectF(cx - 5, cy - 4, 10, 10)
        p.drawArc(cup_rect, -10 * 16, -160 * 16)

        # Stem
        p.drawLine(QPointF(cx, cy + 5), QPointF(cx, cy + 7))
        # Base
        p.drawLine(QPointF(cx - 3, cy + 7), QPointF(cx + 3, cy + 7))


# ═══════════════════════════════════════════════════════════════════════════
# AudioLevelBar — custom painted pill-shaped level meter
# ═══════════════════════════════════════════════════════════════════════════
class _AudioLevelBar(QWidget):
    """Custom-painted audio level bar with gradient fill and smooth animation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(4)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._level: float = 0.0
        self._display_level: float = 0.0

        self._anim = QPropertyAnimation(self, b"displayLevel")
        self._anim.setDuration(80)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def get_display_level(self) -> float:
        return self._display_level

    def set_display_level(self, v: float) -> None:
        self._display_level = v
        self.update()

    displayLevel = pyqtProperty(float, get_display_level, set_display_level)

    def set_level(self, level: float) -> None:
        """Set target level 0.0..1.0 with smooth animation."""
        self._level = max(0.0, min(1.0, level))
        self._anim.stop()
        self._anim.setStartValue(self._display_level)
        self._anim.setEndValue(self._level)
        self._anim.start()

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        radius = h / 2.0

        # Background track
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(COLOR_LEVEL_BG)
        p.drawRoundedRect(QRectF(0, 0, w, h), radius, radius)

        # Filled portion
        fill_w = max(h, w * self._display_level)  # minimum pill width
        if self._display_level > 0.005:
            grad = QLinearGradient(0, 0, fill_w, 0)
            grad.setColorAt(0.0, COLOR_LEVEL_BLUE)
            # Blend toward red as level increases
            if self._display_level > 0.6:
                red_t = (self._display_level - 0.6) / 0.4
                grad.setColorAt(1.0, _lerp_color(COLOR_LEVEL_BLUE, COLOR_LEVEL_RED, red_t))
            else:
                grad.setColorAt(1.0, COLOR_LEVEL_BLUE)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(QRectF(0, 0, fill_w, h), radius, radius)

        p.end()


def _lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    """Linearly interpolate between two colours."""
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


# ═══════════════════════════════════════════════════════════════════════════
# CloseButton — glass circle with hover highlight
# ═══════════════════════════════════════════════════════════════════════════
class _CloseButton(QWidget):
    """Custom 24x24 glass close button."""

    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(24, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hovered = False

    def enterEvent(self, _event: object) -> None:  # noqa: N802
        self._hovered = True
        self.update()

    def leaveEvent(self, _event: object) -> None:  # noqa: N802
        self._hovered = False
        self.update()

    def mousePressEvent(self, _event: object) -> None:  # noqa: N802
        self.clicked.emit()

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2.0, self.height() / 2.0

        # Background circle
        bg = COLOR_CLOSE_HOVER if self._hovered else COLOR_GLASS_PILL
        p.setPen(QPen(COLOR_GLASS_PILL_BORDER, 1.0))
        p.setBrush(bg)
        p.drawEllipse(QPointF(cx, cy), 11, 11)

        # X mark
        p.setPen(QPen(QColor(255, 255, 255, 180 if self._hovered else 120), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        d = 4.0
        p.drawLine(QPointF(cx - d, cy - d), QPointF(cx + d, cy + d))
        p.drawLine(QPointF(cx + d, cy - d), QPointF(cx - d, cy + d))
        p.end()


# ═══════════════════════════════════════════════════════════════════════════
# LanguageBadge — small glass pill
# ═══════════════════════════════════════════════════════════════════════════
class _LanguageBadge(QWidget):
    """Tiny glass pill showing current language code."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = "EN"
        self._font = _ui_font(10)
        self._font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
        self._font.setCapitalization(QFont.Capitalization.AllUppercase)
        self.setFixedSize(36, 20)

    def set_text(self, text: str) -> None:
        self._text = text.upper()[:5]
        self.update()

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        r = h / 2.0

        # Pill background
        p.setPen(QPen(COLOR_GLASS_PILL_BORDER, 1.0))
        p.setBrush(COLOR_GLASS_PILL)
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), r, r)

        # Text
        p.setPen(COLOR_TEXT_SECONDARY)
        p.setFont(self._font)
        p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, self._text)
        p.end()


# ═══════════════════════════════════════════════════════════════════════════
# StatusLabel — "Listening...", "Processing...", "Ready" with animated dots
# ═══════════════════════════════════════════════════════════════════════════
class _StatusLabel(QWidget):
    """Status text with animated ellipsis."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base_text = "Ready"
        self._dot_count = 0
        self._animate_dots = False
        self._font = _ui_font(12)
        self.setFixedHeight(18)
        self.setMinimumWidth(90)

        self._dot_timer = QTimer(self)
        self._dot_timer.setInterval(400)
        self._dot_timer.timeout.connect(self._cycle_dots)

    def set_status(self, text: str, animate: bool = False) -> None:
        self._base_text = text
        self._animate_dots = animate
        self._dot_count = 0
        if animate:
            if not self._dot_timer.isActive():
                self._dot_timer.start()
        else:
            self._dot_timer.stop()
        self.update()

    def _cycle_dots(self) -> None:
        self._dot_count = (self._dot_count + 1) % 4
        self.update()

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setPen(COLOR_TEXT_SECONDARY)
        p.setFont(self._font)

        text = self._base_text
        if self._animate_dots:
            text = self._base_text + "." * self._dot_count

        p.drawText(QRectF(0, 0, self.width(), self.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        p.end()


# ═══════════════════════════════════════════════════════════════════════════
# DictationBar — main floating glassmorphism bar
# ═══════════════════════════════════════════════════════════════════════════
class DictationBar(_AcrylicBase):  # type: ignore[misc]
    """Floating glassmorphism dictation bar for trevo.

    Provides a polished, always-on-top overlay with recording state,
    audio levels, live transcript, and smooth animations.
    """

    close_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Window flags (set even if AcrylicWindow handles some of them)
        base_flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setWindowFlags(base_flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(BAR_WIDTH)

        # State
        self._state: str = "idle"
        self._drag_pos: QPoint | None = None
        self._hide_after_fade = False

        # Build everything
        self._build_ui()
        self._setup_animations()
        self._position_default()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)  # space for shadow
        root_layout.setSpacing(0)

        # Glass container
        self._glass = QWidget(self)
        self._glass.setObjectName("glassContainer")
        root_layout.addWidget(self._glass)

        # Drop shadow on the glass container
        shadow = QGraphicsDropShadowEffect(self._glass)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 80))
        self._glass.setGraphicsEffect(shadow)

        main_layout = QVBoxLayout(self._glass)
        main_layout.setContentsMargins(16, 12, 14, 12)
        main_layout.setSpacing(8)

        # --- Top row ---
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        self._mic_orb = _MicOrb()
        top_row.addWidget(self._mic_orb)

        self._audio_level = _AudioLevelBar()
        top_row.addWidget(self._audio_level, stretch=1)

        self._status_label = _StatusLabel()
        top_row.addWidget(self._status_label)

        self._language_badge = _LanguageBadge()
        top_row.addWidget(self._language_badge)

        self._timer_label = QLabel("00:00")
        self._timer_label.setFont(_mono_font(12))
        self._timer_label.setStyleSheet(f"color: rgba(255,255,255,0.4); background: transparent;")
        self._timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._timer_label.setFixedWidth(46)
        top_row.addWidget(self._timer_label)

        self._close_btn = _CloseButton()
        self._close_btn.clicked.connect(self._on_close)
        top_row.addWidget(self._close_btn)

        main_layout.addLayout(top_row)

        # --- Transcript preview ---
        self._transcript_label = QLabel("")
        self._transcript_label.setFont(_ui_font(13))
        self._transcript_label.setStyleSheet(
            "color: rgba(255,255,255,0.85); background: transparent; padding: 0 2px;"
        )
        self._transcript_label.setWordWrap(True)
        self._transcript_label.setMaximumHeight(42)  # ~2 lines
        self._transcript_label.setMinimumHeight(0)
        self._transcript_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._transcript_label.setTextFormat(Qt.TextFormat.PlainText)
        main_layout.addWidget(self._transcript_label)

        # Initial state
        self._transcript_label.hide()
        self.set_state("idle")

    # ------------------------------------------------------------------
    # Custom painting — glass background
    # ------------------------------------------------------------------
    def paintEvent(self, _event: object) -> None:  # noqa: N802
        if _USE_ACRYLIC:
            # AcrylicWindow handles the blur; we still paint our rounded rect
            super().paintEvent(_event)  # type: ignore[arg-type]

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # The glass area is inside the root layout margins
        m = 12  # matches root_layout margins
        rect = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)

        # Background fill
        path = QPainterPath()
        path.addRoundedRect(rect, BAR_RADIUS, BAR_RADIUS)

        if not _USE_ACRYLIC:
            # Semi-transparent dark fill
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(COLOR_BG)
            p.drawPath(path)

        # Subtle top highlight (glass refraction simulation)
        highlight = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + 30))
        highlight.setColorAt(0.0, QColor(255, 255, 255, 12))
        highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(highlight))
        p.drawPath(path)

        # Border
        p.setPen(QPen(COLOR_BORDER, 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), BAR_RADIUS, BAR_RADIUS)

        p.end()

    # ------------------------------------------------------------------
    # Animations (show/hide)
    # ------------------------------------------------------------------
    def _setup_animations(self) -> None:
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        # Fade animation
        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_anim.setDuration(200)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Slide animation (Y position offset)
        self._slide_anim = QPropertyAnimation(self, b"pos")
        self._slide_anim.setDuration(200)
        self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Group for parallel execution
        self._show_group = QParallelAnimationGroup(self)
        self._show_group.addAnimation(self._fade_anim)
        self._show_group.addAnimation(self._slide_anim)

        self._show_group.finished.connect(self._on_anim_finished)

    def _on_anim_finished(self) -> None:
        if self._hide_after_fade:
            self._hide_after_fade = False
            self.hide()

    # ------------------------------------------------------------------
    # Positioning
    # ------------------------------------------------------------------
    def _position_default(self) -> None:
        """Place bar at top-center of primary screen, 32px from top."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geom = screen.availableGeometry()
        x = geom.x() + (geom.width() - self.width()) // 2
        y = geom.y() + BAR_TOP_MARGIN
        self.move(x, y)
        self._default_pos = QPoint(x, y)

    def set_position(self, x: int, y: int) -> None:
        """Move bar to an explicit screen position."""
        self.move(x, y)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def show_bar(self) -> None:
        """Show the bar with fade-in + slide-down animation."""
        self._hide_after_fade = False
        self._show_group.stop()

        target_pos = self.pos()
        start_pos = QPoint(target_pos.x(), target_pos.y() - 10)

        self._opacity_effect.setOpacity(0.0)
        self.move(start_pos)
        self.show()

        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setDuration(200)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._slide_anim.setStartValue(start_pos)
        self._slide_anim.setEndValue(target_pos)
        self._slide_anim.setDuration(200)
        self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._show_group.start()

    def hide_bar(self) -> None:
        """Hide the bar with fade-out + slide-up animation."""
        self._hide_after_fade = True
        self._show_group.stop()

        current_pos = self.pos()
        end_pos = QPoint(current_pos.x(), current_pos.y() - 10)

        self._fade_anim.setStartValue(self._opacity_effect.opacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setDuration(150)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InCubic)

        self._slide_anim.setStartValue(current_pos)
        self._slide_anim.setEndValue(end_pos)
        self._slide_anim.setDuration(150)
        self._slide_anim.setEasingCurve(QEasingCurve.Type.InCubic)

        self._show_group.start()

    def update_transcript(self, text: str) -> None:
        """Set the live transcript preview text."""
        if not text:
            self._transcript_label.hide()
        else:
            # Truncate to ~2 lines worth (roughly 120 chars for 460px width)
            if len(text) > 120:
                display = text[:117] + "..."
            else:
                display = text
            self._transcript_label.setText(display)
            self._transcript_label.show()
        self.adjustSize()

    def update_audio_level(self, level: float) -> None:
        """Update the audio level bar. *level* should be 0.0 .. 1.0."""
        self._audio_level.set_level(level)

    def update_timer(self, seconds: int) -> None:
        """Display elapsed recording time."""
        mins, secs = divmod(max(0, seconds), 60)
        self._timer_label.setText(f"{mins:02d}:{secs:02d}")

    def set_language(self, lang: str) -> None:
        """Update the language badge (e.g. 'EN', 'ES')."""
        self._language_badge.set_text(lang)

    def set_state(self, state: str) -> None:
        """Set the bar state: 'idle', 'recording', or 'processing'.

        Updates the mic orb animation and status label accordingly.
        """
        self._state = state
        self._mic_orb.set_state(state)

        if state == "recording":
            self._status_label.set_status("Listening", animate=True)
        elif state == "processing":
            self._status_label.set_status("Processing", animate=True)
        else:
            self._status_label.set_status("Ready", animate=False)

    # Backward compat
    def set_recording(self, recording: bool) -> None:
        """Legacy toggle — maps to set_state."""
        self.set_state("recording" if recording else "idle")

    # ------------------------------------------------------------------
    # Dragging support
    # ------------------------------------------------------------------
    def mousePressEvent(self, event: object) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:  # type: ignore[union-attr]
            self._drag_pos = event.globalPosition().toPoint() - self.pos()  # type: ignore[union-attr]
            event.accept()  # type: ignore[union-attr]

    def mouseMoveEvent(self, event: object) -> None:  # noqa: N802
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:  # type: ignore[union-attr]
            self.move(event.globalPosition().toPoint() - self._drag_pos)  # type: ignore[union-attr]
            event.accept()  # type: ignore[union-attr]

    def mouseReleaseEvent(self, event: object) -> None:  # noqa: N802
        self._drag_pos = None
        event.accept()  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    def _on_close(self) -> None:
        self.close_requested.emit()
        self.hide_bar()
