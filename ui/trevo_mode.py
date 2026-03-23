"""JARVIS-style particle sphere UI for Trevo Mode.

A borderless, semi-transparent, always-on-top window that shows an animated
3D particle sphere. Supports both PyOpenGL and QPainter fallback rendering.
"""

from __future__ import annotations

import math
import time
from enum import Enum
from typing import List, Optional, Tuple

from PyQt6.QtCore import (
    QPoint,
    QRectF,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import QMenu, QVBoxLayout, QWidget

# ---------------------------------------------------------------------------
# Try importing OpenGL; fall back gracefully
# ---------------------------------------------------------------------------
try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    from OpenGL.GL import (  # type: ignore[import-untyped]
        GL_BLEND,
        GL_COLOR_BUFFER_BIT,
        GL_DEPTH_BUFFER_BIT,
        GL_DEPTH_TEST,
        GL_MODELVIEW,
        GL_ONE,
        GL_POINT_SMOOTH,
        GL_PROJECTION,
        GL_SRC_ALPHA,
        glBegin,
        glBlendFunc,
        glClear,
        glClearColor,
        glColor4f,
        glEnable,
        glEnd,
        glLoadIdentity,
        glMatrixMode,
        glPointSize,
        glPopMatrix,
        glPushMatrix,
        glRotatef,
        glTranslatef,
        glVertex3f,
    )
    from OpenGL.GL import GL_POINTS  # type: ignore[import-untyped]
    from OpenGL.GL import GL_QUADS  # type: ignore[import-untyped]
    from OpenGL.GL import GL_TEXTURE_2D, glDisable  # type: ignore[import-untyped]
    from OpenGL.GLU import gluPerspective  # type: ignore[import-untyped]

    HAS_OPENGL = True
except ImportError:
    HAS_OPENGL = False


# ---------------------------------------------------------------------------
# State definitions
# ---------------------------------------------------------------------------
class TrevoState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    ERROR = "error"


_STATE_COLORS: dict[TrevoState, Tuple[int, int, int]] = {
    TrevoState.IDLE: (0x4A, 0x9E, 0xFF),
    TrevoState.LISTENING: (0x00, 0xFF, 0x88),
    TrevoState.PROCESSING: (0xFF, 0x88, 0x44),
    TrevoState.SPEAKING: (0xAA, 0x66, 0xFF),
    TrevoState.ERROR: (0xFF, 0x44, 0x44),
}

_STATE_SPEEDS: dict[TrevoState, float] = {
    TrevoState.IDLE: 0.5,
    TrevoState.LISTENING: 2.0,
    TrevoState.PROCESSING: 3.0,
    TrevoState.SPEAKING: 1.5,
    TrevoState.ERROR: 2.5,
}

_STATE_LABELS: dict[TrevoState, str] = {
    TrevoState.IDLE: "Trevo",
    TrevoState.LISTENING: "Listening...",
    TrevoState.PROCESSING: "Thinking...",
    TrevoState.SPEAKING: "Speaking...",
    TrevoState.ERROR: "Error",
}

_PARTICLE_COUNT = 300
_SPHERE_RADIUS = 1.0
_TRANSITION_MS = 500
_WINDOW_SIZE = 600


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _golden_spiral_points(n: int, radius: float) -> List[Tuple[float, float, float]]:
    """Generate *n* points on a sphere using the golden spiral method."""
    points: list[Tuple[float, float, float]] = []
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(n):
        y = 1.0 - (i / (n - 1)) * 2.0  # y goes from 1 to -1
        r = math.sqrt(1.0 - y * y)
        theta = golden_angle * i
        x = math.cos(theta) * r
        z = math.sin(theta) * r
        points.append((x * radius, y * radius, z * radius))
    return points


def _lerp_color(
    c1: Tuple[int, int, int], c2: Tuple[int, int, int], t: float
) -> Tuple[float, float, float]:
    """Linearly interpolate two RGB tuples, returning floats in [0, 1]."""
    t = max(0.0, min(1.0, t))
    return (
        (c1[0] + (c2[0] - c1[0]) * t) / 255.0,
        (c1[1] + (c2[1] - c1[1]) * t) / 255.0,
        (c1[2] + (c2[2] - c1[2]) * t) / 255.0,
    )


# ═══════════════════════════════════════════════════════════════════════════
# OpenGL sphere widget
# ═══════════════════════════════════════════════════════════════════════════
if HAS_OPENGL:

    class _GLSphereWidget(QOpenGLWidget):
        """QOpenGLWidget that renders the 3D particle sphere."""

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self._base_points = _golden_spiral_points(_PARTICLE_COUNT, _SPHERE_RADIUS)
            self._start_time = time.monotonic()
            self._rotation_angle = 0.0

            # State / transition
            self._current_color: Tuple[int, int, int] = _STATE_COLORS[TrevoState.IDLE]
            self._target_color: Tuple[int, int, int] = self._current_color
            self._prev_color: Tuple[int, int, int] = self._current_color
            self._transition_start = 0.0
            self._speed = _STATE_SPEEDS[TrevoState.IDLE]
            self._target_speed = self._speed
            self._state = TrevoState.IDLE

            # Error scatter
            self._error_scatter_time: float = 0.0

        # --- State ----------------------------------------------------------
        def set_state(self, state: TrevoState) -> None:
            self._state = state
            self._prev_color = self._current_color
            self._target_color = _STATE_COLORS[state]
            self._target_speed = _STATE_SPEEDS[state]
            self._transition_start = time.monotonic()
            if state == TrevoState.ERROR:
                self._error_scatter_time = time.monotonic()

        # --- OpenGL callbacks -----------------------------------------------
        def initializeGL(self) -> None:  # noqa: N802
            glClearColor(0.0, 0.0, 0.0, 0.0)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE)
            glEnable(GL_POINT_SMOOTH)
            glEnable(GL_DEPTH_TEST)

        def resizeGL(self, w: int, h: int) -> None:  # noqa: N802
            from OpenGL.GL import glViewport  # type: ignore[import-untyped]

            glViewport(0, 0, w, h)
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            aspect = w / max(h, 1)
            gluPerspective(45.0, aspect, 0.1, 100.0)
            glMatrixMode(GL_MODELVIEW)

        def paintGL(self) -> None:  # noqa: N802
            now = time.monotonic()
            elapsed = now - self._start_time

            # --- Smooth transitions -----------------------------------------
            t_frac = min(1.0, (now - self._transition_start) / (_TRANSITION_MS / 1000.0))
            r, g, b = _lerp_color(self._prev_color, self._target_color, t_frac)
            self._current_color = (
                int(r * 255),
                int(g * 255),
                int(b * 255),
            )
            self._speed += (self._target_speed - self._speed) * min(1.0, t_frac)

            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)  # type: ignore[arg-type]
            glLoadIdentity()
            glTranslatef(0.0, 0.0, -3.5)

            # Slow auto-rotation
            self._rotation_angle = (elapsed * 15.0) % 360.0
            glRotatef(self._rotation_angle, 0.0, 1.0, 0.0)

            # --- Inner core glow -------------------------------------------
            pulse = 0.7 + 0.3 * math.sin(elapsed * self._speed * 2.0)
            self._draw_core(r, g, b, pulse)

            # --- Particles --------------------------------------------------
            self._draw_particles(elapsed, r, g, b)

        # --- Drawing helpers ------------------------------------------------
        def _draw_core(self, r: float, g: float, b: float, pulse: float) -> None:
            """Draw a glowing core as an additive-blended quad."""
            glPushMatrix()
            # Counter-rotate so the quad always faces the camera
            glRotatef(-self._rotation_angle, 0.0, 1.0, 0.0)
            glDisable(GL_DEPTH_TEST)

            core_r = 0.3
            alpha = pulse * 0.6
            glBegin(GL_QUADS)
            # center bright
            glColor4f(r, g, b, alpha)
            glVertex3f(0.0, 0.0, 0.0)
            # edges fade
            glColor4f(r * 0.3, g * 0.3, b * 0.3, 0.0)
            glVertex3f(-core_r, -core_r, 0.0)
            glColor4f(r * 0.3, g * 0.3, b * 0.3, 0.0)
            glVertex3f(core_r, -core_r, 0.0)
            glColor4f(r, g, b, alpha)
            glVertex3f(0.0, 0.0, 0.0)

            # second triangle pair to form a diamond shape
            glColor4f(r, g, b, alpha)
            glVertex3f(0.0, 0.0, 0.0)
            glColor4f(r * 0.3, g * 0.3, b * 0.3, 0.0)
            glVertex3f(core_r, -core_r, 0.0)
            glColor4f(r * 0.3, g * 0.3, b * 0.3, 0.0)
            glVertex3f(core_r, core_r, 0.0)
            glColor4f(r, g, b, alpha)
            glVertex3f(0.0, 0.0, 0.0)

            glColor4f(r, g, b, alpha)
            glVertex3f(0.0, 0.0, 0.0)
            glColor4f(r * 0.3, g * 0.3, b * 0.3, 0.0)
            glVertex3f(core_r, core_r, 0.0)
            glColor4f(r * 0.3, g * 0.3, b * 0.3, 0.0)
            glVertex3f(-core_r, core_r, 0.0)
            glColor4f(r, g, b, alpha)
            glVertex3f(0.0, 0.0, 0.0)

            glColor4f(r, g, b, alpha)
            glVertex3f(0.0, 0.0, 0.0)
            glColor4f(r * 0.3, g * 0.3, b * 0.3, 0.0)
            glVertex3f(-core_r, core_r, 0.0)
            glColor4f(r * 0.3, g * 0.3, b * 0.3, 0.0)
            glVertex3f(-core_r, -core_r, 0.0)
            glColor4f(r, g, b, alpha)
            glVertex3f(0.0, 0.0, 0.0)
            glEnd()

            glEnable(GL_DEPTH_TEST)
            glPopMatrix()

        def _draw_particles(
            self, elapsed: float, r: float, g: float, b: float
        ) -> None:
            """Render all particles with displacement noise."""
            scatter = 0.0
            if self._state == TrevoState.ERROR:
                dt = elapsed - (self._error_scatter_time - self._start_time)
                if 0.0 < dt < 1.0:
                    scatter = math.sin(dt * math.pi) * 0.5

            # Expansion factor for LISTENING state
            expansion = 1.1 if self._state == TrevoState.LISTENING else 1.0

            for i, (bx, by, bz) in enumerate(self._base_points):
                # Organic displacement
                offset_x = math.sin(elapsed * self._speed + i * 0.1) * 0.05
                offset_y = math.cos(elapsed * self._speed * 0.7 + i * 0.15) * 0.05
                offset_z = math.sin(elapsed * self._speed * 0.5 + i * 0.2) * 0.05

                # Speaking wave pattern
                if self._state == TrevoState.SPEAKING:
                    wave = math.sin(elapsed * 4.0 + i * 0.05) * 0.08
                    offset_y += wave

                # Error scatter
                if scatter > 0.0:
                    offset_x += math.sin(i * 1.7) * scatter
                    offset_y += math.cos(i * 2.3) * scatter
                    offset_z += math.sin(i * 3.1) * scatter

                px = bx * expansion + offset_x
                py = by * expansion + offset_y
                pz = bz * expansion + offset_z

                # Depth-based alpha and size
                depth = pz + _SPHERE_RADIUS  # 0 .. 2*radius
                depth_norm = depth / (2.0 * _SPHERE_RADIUS)
                alpha = 0.3 + 0.7 * depth_norm

                # Point size must be set OUTSIDE glBegin/glEnd (OpenGL spec)
                size = 2.0 + 4.0 * depth_norm
                glPointSize(size)
                glColor4f(r, g, b, alpha)
                glBegin(GL_POINTS)
                glVertex3f(px, py, pz)
                glEnd()


# ═══════════════════════════════════════════════════════════════════════════
# QPainter fallback sphere widget
# ═══════════════════════════════════════════════════════════════════════════
class _PainterSphereWidget(QWidget):
    """Pure QPainter 2D fallback that projects the same 3D sphere."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._base_points = _golden_spiral_points(_PARTICLE_COUNT, _SPHERE_RADIUS)
        self._start_time = time.monotonic()

        self._current_color: Tuple[int, int, int] = _STATE_COLORS[TrevoState.IDLE]
        self._target_color: Tuple[int, int, int] = self._current_color
        self._prev_color: Tuple[int, int, int] = self._current_color
        self._transition_start = 0.0
        self._speed = _STATE_SPEEDS[TrevoState.IDLE]
        self._target_speed = self._speed
        self._state = TrevoState.IDLE
        self._error_scatter_time: float = 0.0

    def set_state(self, state: TrevoState) -> None:
        self._state = state
        self._prev_color = self._current_color
        self._target_color = _STATE_COLORS[state]
        self._target_speed = _STATE_SPEEDS[state]
        self._transition_start = time.monotonic()
        if state == TrevoState.ERROR:
            self._error_scatter_time = time.monotonic()

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        now = time.monotonic()
        elapsed = now - self._start_time

        # Transition interpolation
        t_frac = min(1.0, (now - self._transition_start) / (_TRANSITION_MS / 1000.0))
        cr, cg, cb = _lerp_color(self._prev_color, self._target_color, t_frac)
        self._current_color = (int(cr * 255), int(cg * 255), int(cb * 255))
        self._speed += (self._target_speed - self._speed) * min(1.0, t_frac)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        scale = min(w, h) * 0.35

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Rotation angle
        rot = elapsed * 15.0 * math.pi / 180.0

        # --- Core glow -----------------------------------------------------
        pulse = 0.7 + 0.3 * math.sin(elapsed * self._speed * 2.0)
        core_radius = scale * 0.3
        gradient = QRadialGradient(cx, cy, core_radius)
        gradient.setColorAt(
            0.0,
            QColor(
                self._current_color[0],
                self._current_color[1],
                self._current_color[2],
                int(pulse * 150),
            ),
        )
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(QRectF(cx - core_radius, cy - core_radius, core_radius * 2, core_radius * 2))

        # --- Particles -----------------------------------------------------
        expansion = 1.1 if self._state == TrevoState.LISTENING else 1.0
        scatter = 0.0
        if self._state == TrevoState.ERROR:
            dt = elapsed - (self._error_scatter_time - self._start_time)
            if 0.0 < dt < 1.0:
                scatter = math.sin(dt * math.pi) * 0.5

        for i, (bx, by, bz) in enumerate(self._base_points):
            # Displacement
            ox = math.sin(elapsed * self._speed + i * 0.1) * 0.05
            oy = math.cos(elapsed * self._speed * 0.7 + i * 0.15) * 0.05
            oz = math.sin(elapsed * self._speed * 0.5 + i * 0.2) * 0.05

            if self._state == TrevoState.SPEAKING:
                oy += math.sin(elapsed * 4.0 + i * 0.05) * 0.08
            if scatter > 0.0:
                ox += math.sin(i * 1.7) * scatter
                oy += math.cos(i * 2.3) * scatter
                oz += math.sin(i * 3.1) * scatter

            px = bx * expansion + ox
            py = by * expansion + oy
            pz = bz * expansion + oz

            # Y-axis rotation
            rx = px * math.cos(rot) + pz * math.sin(rot)
            ry = py
            rz = -px * math.sin(rot) + pz * math.cos(rot)

            # Simple perspective projection
            cam_z = 3.5
            denom = cam_z - rz
            if denom <= 0.1:
                continue
            proj_x = cx + rx * scale * (cam_z / denom)
            proj_y = cy - ry * scale * (cam_z / denom)

            depth_norm = (rz + _SPHERE_RADIUS) / (2.0 * _SPHERE_RADIUS)
            depth_norm = max(0.0, min(1.0, depth_norm))
            alpha = int((0.3 + 0.7 * depth_norm) * 255)
            radius = 1.5 + 3.0 * depth_norm

            color = QColor(
                self._current_color[0],
                self._current_color[1],
                self._current_color[2],
                alpha,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(proj_x - radius, proj_y - radius, radius * 2, radius * 2))

        painter.end()


# ═══════════════════════════════════════════════════════════════════════════
# Main window
# ═══════════════════════════════════════════════════════════════════════════
class TrevoModeWindow(QWidget):
    """Frameless, always-on-top Trevo Mode overlay with animated particle sphere."""

    # Signals
    wake_phrase_detected = pyqtSignal()
    speech_text = pyqtSignal(str)
    close_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # ── Window flags ───────────────────────────────────────────────────
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(_WINDOW_SIZE, _WINDOW_SIZE)

        # ── State ──────────────────────────────────────────────────────────
        self._state = TrevoState.IDLE
        self._drag_pos: Optional[QPoint] = None

        # ── Layout ─────────────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Choose renderer
        if HAS_OPENGL:
            self._sphere: QWidget = _GLSphereWidget(self)
        else:
            self._sphere = _PainterSphereWidget(self)

        self._sphere.setMinimumSize(400, 400)
        layout.addWidget(self._sphere, stretch=1)

        # ── Animation timer ────────────────────────────────────────────────
        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60 fps
        self._timer.timeout.connect(self._sphere.update)
        self._timer.start()

    # ── Public API ─────────────────────────────────────────────────────────
    def set_state(self, state: TrevoState) -> None:
        """Transition to a new visual state."""
        self._state = state
        self._sphere.set_state(state)  # type: ignore[attr-defined]

    def show_sphere(self) -> None:
        """Center on screen and show."""
        screen = self.screen()
        if screen is not None:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 2
            self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def hide_sphere(self) -> None:
        """Hide the overlay."""
        self.hide()

    # ── Painting (background + status text) ────────────────────────────────
    def paintEvent(self, _event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Dark rounded-rect background
        bg = QColor(10, 10, 26, 230)  # #0a0a1a @ ~90%
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 24.0, 24.0)
        painter.drawPath(path)

        # Status text
        label = _STATE_LABELS.get(self._state, "")
        font = QFont()
        font.setPointSize(14)
        painter.setFont(font)
        color = QColor(255, 255, 255, 160 if self._state == TrevoState.IDLE else 220)
        painter.setPen(QPen(color))
        text_rect = QRectF(0, self.height() - 60, self.width(), 40)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label)

        painter.end()

    # ── Keyboard / mouse events ────────────────────────────────────────────
    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        from PyQt6.QtGui import QKeyEvent

        if isinstance(event, QKeyEvent) and event.key() == Qt.Key.Key_Escape:
            self.close_requested.emit()
            self.hide_sphere()
        else:
            super().keyPressEvent(event)  # type: ignore[arg-type]

    def mousePressEvent(self, event: Optional[QMouseEvent]) -> None:  # noqa: N802
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)  # type: ignore[arg-type]

    def mouseMoveEvent(self, event: Optional[QMouseEvent]) -> None:  # noqa: N802
        if (
            event is not None
            and self._drag_pos is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)  # type: ignore[arg-type]

    def mouseReleaseEvent(self, event: Optional[QMouseEvent]) -> None:  # noqa: N802
        self._drag_pos = None
        if event is not None:
            super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event: object) -> None:  # noqa: N802
        from PyQt6.QtGui import QContextMenuEvent

        if not isinstance(event, QContextMenuEvent):
            return
        menu = QMenu(self)
        close_action = QAction("Close", self)
        close_action.triggered.connect(lambda: (self.close_requested.emit(), self.hide_sphere()))
        menu.addAction(close_action)
        menu.exec(event.globalPos())

    # ── Cleanup ────────────────────────────────────────────────────────────
    def closeEvent(self, event: object) -> None:  # noqa: N802
        self._timer.stop()
        super().closeEvent(event)  # type: ignore[arg-type]
