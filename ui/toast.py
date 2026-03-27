"""Toast notification system for Trevo.

Provides non-intrusive, auto-dismissing toast notifications that stack
in the top-right corner of the primary screen. Supports success, error,
info, and warning toast types with glass-morphism styling.

Usage:
    from ui.toast import ToastManager, ToastType
    ToastManager.show("Title", "Message body", ToastType.SUCCESS)
"""

from __future__ import annotations

import math
from enum import Enum, auto
from typing import ClassVar, Optional

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
    pyqtProperty,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QLabel, QVBoxLayout, QWidget


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TOAST_WIDTH: int = 320
_BORDER_RADIUS: int = 12
_MAX_VISIBLE: int = 5
_GAP: int = 8
_MARGIN: int = 16
_ICON_SIZE: int = 22
_PADDING: int = 14
_FONT_FAMILIES: str = '"Inter", "Segoe UI Variable", sans-serif'
_COLOR_TEXT: str = "#F5F3FF"
_COLOR_SECONDARY: str = "#B8A8D0"
_COLOR_GLASS: tuple[int, int, int, int] = (15, 14, 23, 234)  # rgba 0-255, ~0.92 alpha


# ---------------------------------------------------------------------------
# ToastType
# ---------------------------------------------------------------------------

class ToastType(Enum):
    """Supported toast notification types."""

    SUCCESS = auto()
    ERROR = auto()
    INFO = auto()
    WARNING = auto()


# Per-type colour definitions: (bg_rgba, border_rgba, icon_hex)
_TYPE_COLORS: dict[ToastType, tuple[tuple[int, int, int, int], tuple[int, int, int, int], str]] = {
    ToastType.SUCCESS: ((16, 185, 129, 38), (16, 185, 129, 77), "#10B981"),
    ToastType.ERROR:   ((239, 68, 68, 38),  (239, 68, 68, 77),  "#EF4444"),
    ToastType.INFO:    ((6, 182, 212, 38),   (6, 182, 212, 77),  "#06B6D4"),
    ToastType.WARNING: ((245, 158, 11, 38),  (245, 158, 11, 77), "#F59E0B"),
}


# ---------------------------------------------------------------------------
# Icon drawing helpers
# ---------------------------------------------------------------------------

def _draw_icon(painter: QPainter, toast_type: ToastType, rect: QRect, color: QColor) -> None:
    """Draw the toast-type icon centred inside *rect* using *painter*."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(color, 2.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    cx = rect.center().x()
    cy = rect.center().y()
    r = min(rect.width(), rect.height()) / 2.0 - 1.0

    if toast_type == ToastType.SUCCESS:
        _draw_checkmark_circle(painter, cx, cy, r)
    elif toast_type == ToastType.ERROR:
        _draw_x_circle(painter, cx, cy, r)
    elif toast_type == ToastType.INFO:
        _draw_info_circle(painter, cx, cy, r)
    elif toast_type == ToastType.WARNING:
        _draw_warning_triangle(painter, cx, cy, r)


def _draw_checkmark_circle(p: QPainter, cx: float, cy: float, r: float) -> None:
    p.drawEllipse(QRect(int(cx - r), int(cy - r), int(2 * r), int(2 * r)))
    # Checkmark
    ir = r * 0.5
    p.drawLine(
        QPoint(int(cx - ir * 0.55), int(cy + ir * 0.1)),
        QPoint(int(cx - ir * 0.05), int(cy + ir * 0.55)),
    )
    p.drawLine(
        QPoint(int(cx - ir * 0.05), int(cy + ir * 0.55)),
        QPoint(int(cx + ir * 0.6), int(cy - ir * 0.4)),
    )


def _draw_x_circle(p: QPainter, cx: float, cy: float, r: float) -> None:
    p.drawEllipse(QRect(int(cx - r), int(cy - r), int(2 * r), int(2 * r)))
    d = r * 0.38
    p.drawLine(QPoint(int(cx - d), int(cy - d)), QPoint(int(cx + d), int(cy + d)))
    p.drawLine(QPoint(int(cx + d), int(cy - d)), QPoint(int(cx - d), int(cy + d)))


def _draw_info_circle(p: QPainter, cx: float, cy: float, r: float) -> None:
    p.drawEllipse(QRect(int(cx - r), int(cy - r), int(2 * r), int(2 * r)))
    # Dot
    dot_r = r * 0.1
    p.setBrush(p.pen().color())
    p.drawEllipse(QRect(int(cx - dot_r), int(cy - r * 0.5 - dot_r), int(2 * dot_r), int(2 * dot_r)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Vertical line
    p.drawLine(QPoint(int(cx), int(cy - r * 0.15)), QPoint(int(cx), int(cy + r * 0.55)))


def _draw_warning_triangle(p: QPainter, cx: float, cy: float, r: float) -> None:
    # Equilateral triangle
    top = QPoint(int(cx), int(cy - r))
    bl = QPoint(int(cx - r * 0.9), int(cy + r * 0.7))
    br = QPoint(int(cx + r * 0.9), int(cy + r * 0.7))

    path = QPainterPath()
    path.moveTo(top.x(), top.y())
    path.lineTo(bl.x(), bl.y())
    path.lineTo(br.x(), br.y())
    path.closeSubpath()
    p.drawPath(path)

    # Exclamation mark
    p.drawLine(QPoint(int(cx), int(cy - r * 0.35)), QPoint(int(cx), int(cy + r * 0.2)))
    dot_r = r * 0.08
    p.setBrush(p.pen().color())
    p.drawEllipse(QRect(int(cx - dot_r), int(cy + r * 0.38 - dot_r), int(2 * dot_r), int(2 * dot_r)))
    p.setBrush(Qt.BrushStyle.NoBrush)


# ---------------------------------------------------------------------------
# ToastWidget
# ---------------------------------------------------------------------------

class ToastWidget(QWidget):
    """A single toast notification widget.

    Renders as a glass-morphism card with an icon, title, and message.
    Slides in from the right, auto-dismisses after *duration_ms*, and
    fades out on close.

    Parameters
    ----------
    title:
        Bold heading text.
    message:
        Body / description text.
    toast_type:
        Determines colours and icon.
    duration_ms:
        Milliseconds before auto-dismiss. Use ``0`` to disable.
    parent:
        Optional parent widget.
    """

    def __init__(
        self,
        title: str,
        message: str,
        toast_type: ToastType = ToastType.INFO,
        duration_ms: int = 3000,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self._title = title
        self._message = message
        self._toast_type = toast_type
        self._duration_ms = duration_ms
        self._closing = False

        # --- Window flags ---------------------------------------------------
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedWidth(_TOAST_WIDTH)

        # --- Opacity effect for fade-out ------------------------------------
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        # --- Build inner layout for size calculation ------------------------
        self._build_layout()

        # --- Auto-dismiss timer ---------------------------------------------
        if self._duration_ms > 0:
            self._dismiss_timer = QTimer(self)
            self._dismiss_timer.setSingleShot(True)
            self._dismiss_timer.setInterval(self._duration_ms)
            self._dismiss_timer.timeout.connect(self.close_animated)
        else:
            self._dismiss_timer = None

    # -- Layout -------------------------------------------------------------

    def _build_layout(self) -> None:
        """Create title and message labels used for height calculation."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            _PADDING + _ICON_SIZE + _PADDING,  # left: icon space
            _PADDING,
            _PADDING,
            _PADDING,
        )
        layout.setSpacing(4)

        # Title
        self._title_label = QLabel(self._title, self)
        self._title_label.setWordWrap(True)
        self._title_label.setStyleSheet(
            f"color: {_COLOR_TEXT}; background: transparent;"
        )
        title_font = QFont()
        title_font.setFamilies(["Inter", "Segoe UI Variable"])
        title_font.setPixelSize(14)
        title_font.setWeight(QFont.Weight.DemiBold)
        self._title_label.setFont(title_font)
        layout.addWidget(self._title_label)

        # Message
        if self._message:
            self._message_label = QLabel(self._message, self)
            self._message_label.setWordWrap(True)
            self._message_label.setStyleSheet(
                f"color: {_COLOR_SECONDARY}; background: transparent;"
            )
            msg_font = QFont()
            msg_font.setFamilies(["Inter", "Segoe UI Variable"])
            msg_font.setPixelSize(12)
            msg_font.setWeight(QFont.Weight.Normal)
            self._message_label.setFont(msg_font)
            layout.addWidget(self._message_label)
        else:
            self._message_label = None

        self.setLayout(layout)
        self.adjustSize()

    # -- Painting -----------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: ANN001
        """Paint the glass background, accent tint, and icon."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        bg_rgba, border_rgba, icon_hex = _TYPE_COLORS[self._toast_type]
        rect = self.rect().adjusted(1, 1, -1, -1)

        # --- Glass background -----------------------------------------------
        path = QPainterPath()
        path.addRoundedRect(float(rect.x()), float(rect.y()),
                            float(rect.width()), float(rect.height()),
                            _BORDER_RADIUS, _BORDER_RADIUS)
        painter.setClipPath(path)

        # Base glass fill
        painter.fillPath(path, QColor(*_COLOR_GLASS))

        # Accent tint overlay
        painter.fillPath(path, QColor(*bg_rgba))

        # --- Border ---------------------------------------------------------
        painter.setClipping(False)
        pen = QPen(QColor(*border_rgba), 1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            rect.x() + 0.5, rect.y() + 0.5,
            rect.width() - 1, rect.height() - 1,
            _BORDER_RADIUS, _BORDER_RADIUS,
        )

        # --- Icon -----------------------------------------------------------
        icon_rect = QRect(_PADDING, _PADDING, _ICON_SIZE, _ICON_SIZE)
        _draw_icon(painter, self._toast_type, icon_rect, QColor(icon_hex))

        painter.end()

    # -- Animations ---------------------------------------------------------

    def show_animated(self, target_pos: QPoint) -> None:
        """Slide in from the right edge of the screen to *target_pos*."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.move(target_pos)
            self.show()
            return

        screen_right = screen.availableGeometry().right()
        start_pos = QPoint(screen_right + 10, target_pos.y())
        self.move(start_pos)
        self.show()

        self._slide_anim = QPropertyAnimation(self, b"pos", self)
        self._slide_anim.setDuration(250)
        self._slide_anim.setStartValue(start_pos)
        self._slide_anim.setEndValue(target_pos)
        self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide_anim.start()

        if self._dismiss_timer is not None:
            self._dismiss_timer.start()

    def close_animated(self) -> None:
        """Fade out and then destroy the widget."""
        if self._closing:
            return
        self._closing = True

        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_anim.setDuration(200)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InQuad)
        self._fade_anim.finished.connect(self._on_fade_finished)
        self._fade_anim.start()

    def _on_fade_finished(self) -> None:
        """Remove the toast from the manager and destroy it."""
        manager = ToastManager.instance()
        if manager is not None:
            manager._remove_toast(self)
        self.close()
        self.deleteLater()

    # -- Input --------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        """Dismiss the toast on click."""
        self.close_animated()


# ---------------------------------------------------------------------------
# ToastManager (singleton)
# ---------------------------------------------------------------------------

class ToastManager:
    """Manages positioning and lifecycle of active :class:`ToastWidget` instances.

    Uses a singleton pattern so that toasts from anywhere in the application
    share a single stack in the top-right corner of the primary screen.
    """

    _instance: ClassVar[Optional["ToastManager"]] = None
    _toasts: list[ToastWidget]

    def __init__(self) -> None:
        self._toasts = []

    @classmethod
    def instance(cls) -> "ToastManager":
        """Return the singleton manager, creating it on first access."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- Public API ---------------------------------------------------------

    @classmethod
    def show(
        cls,
        title: str,
        message: str = "",
        toast_type: ToastType = ToastType.INFO,
        duration_ms: int = 3000,
    ) -> ToastWidget:
        """Create and display a toast notification.

        Parameters
        ----------
        title:
            Bold heading text.
        message:
            Optional body text shown below the title.
        toast_type:
            Determines the colour scheme and icon.
        duration_ms:
            Auto-dismiss delay in milliseconds. Pass ``0`` to keep the
            toast visible until the user clicks it.

        Returns
        -------
        ToastWidget
            The widget instance (useful for testing or manual control).
        """
        mgr = cls.instance()

        # Evict oldest if at capacity
        while len(mgr._toasts) >= _MAX_VISIBLE:
            oldest = mgr._toasts[0]
            oldest.close_animated()

        toast = ToastWidget(title, message, toast_type, duration_ms)
        mgr._toasts.append(toast)

        target = mgr._next_position(toast)
        toast.show_animated(target)
        return toast

    # -- Internal -----------------------------------------------------------

    def _next_position(self, toast: ToastWidget) -> QPoint:
        """Calculate the screen position for *toast* at the bottom of the stack."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return QPoint(100, 100)

        geo = screen.availableGeometry()
        x = geo.right() - _TOAST_WIDTH - _MARGIN

        y = geo.top() + _MARGIN
        for existing in self._toasts:
            if existing is toast:
                continue
            if not existing._closing:
                y += existing.height() + _GAP

        return QPoint(x, y)

    def _remove_toast(self, toast: ToastWidget) -> None:
        """Remove *toast* from the managed list and re-position remaining toasts."""
        if toast in self._toasts:
            self._toasts.remove(toast)
        self._reposition()

    def _reposition(self) -> None:
        """Slide remaining toasts into their correct positions."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return

        geo = screen.availableGeometry()
        x = geo.right() - _TOAST_WIDTH - _MARGIN
        y = geo.top() + _MARGIN

        for toast in self._toasts:
            if toast._closing:
                continue
            target = QPoint(x, y)
            if toast.pos() != target:
                anim = QPropertyAnimation(toast, b"pos", toast)
                anim.setDuration(200)
                anim.setEndValue(target)
                anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                anim.start()
            y += toast.height() + _GAP
