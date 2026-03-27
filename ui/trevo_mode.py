"""JARVIS / Ultron-style wireframe sphere UI for Trevo Mode.

A borderless, semi-transparent, always-on-top window that shows an animated
3D wireframe icosphere (Ultron orb aesthetic). Shows the last dictation +
response as a temporary floating overlay that disappears after 5 seconds.

Supports both PyOpenGL and QPainter fallback rendering.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

import re as _re

from PyQt6.QtCore import (
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QGraphicsOpacityEffect,
    QLabel,
    QMenu,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtGui import QGuiApplication as _QGA

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
        GL_LINES,
        GL_MODELVIEW,
        GL_ONE,
        GL_POINT_SMOOTH,
        GL_POINTS,
        GL_PROJECTION,
        GL_QUADS,
        GL_SRC_ALPHA,
        GL_TEXTURE_2D,
        glBegin,
        glBlendFunc,
        glClear,
        glClearColor,
        glColor4f,
        glDisable,
        glEnable,
        glEnd,
        glLineWidth,
        glLoadIdentity,
        glMatrixMode,
        glPointSize,
        glPopMatrix,
        glPushMatrix,
        glRotatef,
        glTranslatef,
        glVertex3f,
    )
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


# Ultron orb color palette
_STATE_COLORS: dict[TrevoState, Tuple[int, int, int]] = {
    TrevoState.IDLE: (30, 144, 255),        # electric blue
    TrevoState.LISTENING: (255, 69, 0),      # red-orange (alert)
    TrevoState.PROCESSING: (255, 140, 0),    # amber (working)
    TrevoState.SPEAKING: (0, 191, 255),      # bright cyan
    TrevoState.ERROR: (255, 0, 0),           # pure red
}

# Core glow colors (inner energy)
_CORE_COLORS: dict[TrevoState, Tuple[int, int, int]] = {
    TrevoState.IDLE: (200, 60, 20),          # dim red-orange
    TrevoState.LISTENING: (255, 120, 0),     # bright orange
    TrevoState.PROCESSING: (255, 80, 0),     # hot orange
    TrevoState.SPEAKING: (0, 140, 255),      # blue core
    TrevoState.ERROR: (255, 0, 0),           # red
}

_STATE_SPEEDS: dict[TrevoState, float] = {
    TrevoState.IDLE: 0.5,
    TrevoState.LISTENING: 2.0,
    TrevoState.PROCESSING: 4.0,
    TrevoState.SPEAKING: 1.5,
    TrevoState.ERROR: 3.0,
}

_STATE_LABELS: dict[TrevoState, str] = {
    TrevoState.IDLE: "Trevo",
    TrevoState.LISTENING: "Listening...",
    TrevoState.PROCESSING: "Thinking...",
    TrevoState.SPEAKING: "Speaking...",
    TrevoState.ERROR: "Error",
}

_SPHERE_RADIUS = 1.0
_TRANSITION_MS = 500
_SPHERE_SIZE = 380
_WINDOW_W = 420
_WINDOW_H = 600  # taller to fit streaming text below orb
_WINDOW_SIZE = _WINDOW_W  # backwards compat for overlay widths
_MESSAGE_DISPLAY_MS = 5000

# Stop words excluded from keyword extraction
_STOP_WORDS: set[str] = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "i", "me", "my", "we", "our", "you", "your", "he", "him", "his",
    "she", "her", "it", "its", "they", "them", "their", "that", "this",
    "what", "which", "who", "whom", "how", "when", "where", "why",
    "and", "but", "or", "nor", "not", "so", "if", "then", "than",
    "too", "very", "just", "about", "above", "after", "before", "from",
    "into", "of", "on", "to", "with", "for", "at", "by", "in", "up",
    "out", "off", "over", "under", "again", "there", "here", "all",
    "each", "every", "both", "few", "more", "most", "other", "some",
    "such", "no", "only", "own", "same", "also", "as", "well", "like",
    "really", "quite", "still", "even", "much", "many", "let", "got",
    "get", "go", "going", "come", "take", "make", "know", "think",
    "good", "great", "right", "okay", "yes", "yeah", "sure", "hey",
    "hi", "hello", "thanks", "thank", "please", "sorry",
}


def _extract_keywords(text: str, max_kw: int = 6) -> list[str]:
    """Pull the most important nouns/topics from a response.

    Simple heuristic: split into words, drop stop words & short words,
    prefer capitalised words and numbers, limit to *max_kw*.
    """
    words = _re.findall(r"[A-Za-z0-9°%$#@]+(?:'[a-z]+)?", text)
    seen: set[str] = set()
    scored: list[tuple[float, str]] = []
    for w in words:
        low = w.lower()
        if low in _STOP_WORDS or len(w) < 3:
            continue
        if low in seen:
            continue
        seen.add(low)
        # Score: capitalised > numbers > length
        score = 0.0
        if w[0].isupper():
            score += 3.0
        if any(c.isdigit() for c in w):
            score += 2.0
        score += min(len(w) / 4.0, 2.0)
        scored.append((score, w))
    scored.sort(key=lambda x: -x[0])
    return [w for _, w in scored[:max_kw]]


# ---------------------------------------------------------------------------
# Icosphere geometry generation
# ---------------------------------------------------------------------------
def _icosphere_geometry(
    subdivisions: int = 2, radius: float = 1.0
) -> Tuple[List[Tuple[float, float, float]], List[Tuple[int, int]]]:
    """Generate a subdivided icosahedron (icosphere).

    Returns (vertices, edges) where vertices are 3-tuples and edges are
    index pairs into the vertex list.
    """
    # Golden ratio
    phi = (1.0 + math.sqrt(5.0)) / 2.0
    norm = math.sqrt(1.0 + phi * phi)

    # 12 icosahedron vertices
    verts: list[list[float]] = [
        [-1, phi, 0], [1, phi, 0], [-1, -phi, 0], [1, -phi, 0],
        [0, -1, phi], [0, 1, phi], [0, -1, -phi], [0, 1, -phi],
        [phi, 0, -1], [phi, 0, 1], [-phi, 0, -1], [-phi, 0, 1],
    ]
    # Normalize to unit sphere
    verts = [[v[0] / norm, v[1] / norm, v[2] / norm] for v in verts]

    # 20 triangular faces
    faces: list[list[int]] = [
        [0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11],
        [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8],
        [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9],
        [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1],
    ]

    # Midpoint cache for subdivision
    midpoint_cache: dict[Tuple[int, int], int] = {}

    def _midpoint(i1: int, i2: int) -> int:
        key = (min(i1, i2), max(i1, i2))
        if key in midpoint_cache:
            return midpoint_cache[key]
        v1, v2 = verts[i1], verts[i2]
        mid = [(v1[0] + v2[0]) / 2, (v1[1] + v2[1]) / 2, (v1[2] + v2[2]) / 2]
        # Project onto unit sphere
        length = math.sqrt(mid[0] ** 2 + mid[1] ** 2 + mid[2] ** 2)
        mid = [mid[0] / length, mid[1] / length, mid[2] / length]
        idx = len(verts)
        verts.append(mid)
        midpoint_cache[key] = idx
        return idx

    # Subdivide
    for _ in range(subdivisions):
        new_faces: list[list[int]] = []
        midpoint_cache.clear()
        for tri in faces:
            a, b, c = tri
            ab = _midpoint(a, b)
            bc = _midpoint(b, c)
            ca = _midpoint(c, a)
            new_faces.extend([
                [a, ab, ca],
                [b, bc, ab],
                [c, ca, bc],
                [ab, bc, ca],
            ])
        faces = new_faces

    # Scale to radius
    scaled_verts = [(v[0] * radius, v[1] * radius, v[2] * radius) for v in verts]

    # Extract unique edges from faces
    edge_set: set[Tuple[int, int]] = set()
    for tri in faces:
        for i in range(3):
            e = (min(tri[i], tri[(i + 1) % 3]), max(tri[i], tri[(i + 1) % 3]))
            edge_set.add(e)

    return scaled_verts, list(edge_set)


def _generate_shard_fragments(
    n: int = 10, radius: float = 1.4
) -> List[Tuple[float, float, float, float, float]]:
    """Generate orbiting geometric shard data.

    Returns list of (orbit_radius, inclination, phase, speed, size).
    """
    shards = []
    for _ in range(n):
        orbit_r = radius + random.uniform(-0.2, 0.3)
        incl = random.uniform(-60, 60) * math.pi / 180
        phase = random.uniform(0, 2 * math.pi)
        speed = random.uniform(0.3, 1.2)
        size = random.uniform(0.02, 0.06)
        shards.append((orbit_r, incl, phase, speed, size))
    return shards


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
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
# OpenGL wireframe sphere widget (Ultron orb)
# ═══════════════════════════════════════════════════════════════════════════
if HAS_OPENGL:

    class _GLSphereWidget(QOpenGLWidget):
        """QOpenGLWidget that renders a wireframe icosphere (Ultron orb)."""

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self._vertices, self._edges = _icosphere_geometry(2, _SPHERE_RADIUS)
            self._shards = _generate_shard_fragments(10)
            self._start_time = time.monotonic()
            self._rotation_y = 0.0
            self._rotation_x = 0.0

            # State / transition
            self._current_color: Tuple[int, int, int] = _STATE_COLORS[TrevoState.IDLE]
            self._target_color: Tuple[int, int, int] = self._current_color
            self._prev_color: Tuple[int, int, int] = self._current_color
            self._core_color: Tuple[int, int, int] = _CORE_COLORS[TrevoState.IDLE]
            self._target_core: Tuple[int, int, int] = self._core_color
            self._prev_core: Tuple[int, int, int] = self._core_color
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
            self._prev_core = self._core_color
            self._target_core = _CORE_COLORS[state]
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
            self._current_color = (int(r * 255), int(g * 255), int(b * 255))
            cr, cg, cb = _lerp_color(self._prev_core, self._target_core, t_frac)
            self._core_color = (int(cr * 255), int(cg * 255), int(cb * 255))
            self._speed += (self._target_speed - self._speed) * min(1.0, t_frac)

            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)  # type: ignore[arg-type]
            glLoadIdentity()
            glTranslatef(0.0, 0.0, -3.5)

            # Rotation — state-dependent
            if self._state == TrevoState.PROCESSING:
                # Fast multi-axis rotation
                self._rotation_y = (elapsed * 60.0) % 360.0
                self._rotation_x = (elapsed * 25.0) % 360.0
            else:
                self._rotation_y = (elapsed * 15.0) % 360.0
                self._rotation_x = math.sin(elapsed * 0.3) * 5.0

            glRotatef(self._rotation_x, 1.0, 0.0, 0.0)
            glRotatef(self._rotation_y, 0.0, 1.0, 0.0)

            # Scale pulsing for SPEAKING state
            scale = 1.0
            if self._state == TrevoState.SPEAKING:
                scale = 1.0 + 0.08 * math.sin(elapsed * 4.0)
            elif self._state == TrevoState.LISTENING:
                scale = 1.15 + 0.05 * math.sin(elapsed * 2.0)

            # --- Inner core glow -------------------------------------------
            pulse = 0.6 + 0.4 * math.sin(elapsed * self._speed * 2.0)
            self._draw_core(cr, cg, cb, pulse)

            # --- Wireframe icosphere ----------------------------------------
            self._draw_wireframe(elapsed, r, g, b, scale)

            # --- Orbiting shard fragments -----------------------------------
            self._draw_shards(elapsed, r, g, b)

        # --- Drawing helpers ------------------------------------------------
        def _draw_core(self, r: float, g: float, b: float, pulse: float) -> None:
            """Draw a glowing core as additive-blended quads."""
            glPushMatrix()
            glRotatef(-self._rotation_y, 0.0, 1.0, 0.0)
            glRotatef(-self._rotation_x, 1.0, 0.0, 0.0)
            glDisable(GL_DEPTH_TEST)

            core_r = 0.35 * pulse
            alpha = pulse * 0.7
            # Draw two perpendicular quads for volumetric feel
            for angle in (0.0, 90.0):
                glPushMatrix()
                glRotatef(angle, 0.0, 1.0, 0.0)
                glBegin(GL_QUADS)
                glColor4f(r, g, b, alpha)
                glVertex3f(-core_r, -core_r, 0.0)
                glColor4f(r * 0.2, g * 0.2, b * 0.2, 0.0)
                glVertex3f(core_r, -core_r, 0.0)
                glColor4f(r, g, b, alpha * 0.5)
                glVertex3f(core_r, core_r, 0.0)
                glColor4f(r * 0.2, g * 0.2, b * 0.2, 0.0)
                glVertex3f(-core_r, core_r, 0.0)
                glEnd()
                glPopMatrix()

            glEnable(GL_DEPTH_TEST)
            glPopMatrix()

        def _draw_wireframe(
            self, elapsed: float, r: float, g: float, b: float, scale: float,
        ) -> None:
            """Render the icosphere wireframe edges."""
            # Error scatter displacement
            scatter = 0.0
            if self._state == TrevoState.ERROR:
                dt = time.monotonic() - self._error_scatter_time
                if 0.0 < dt < 1.0:
                    scatter = math.sin(dt * math.pi) * 0.6

            # Compute displaced vertices
            displaced: list[Tuple[float, float, float]] = []
            for i, (vx, vy, vz) in enumerate(self._vertices):
                dx = dy = dz = 0.0

                # Processing: vertex jitter/distortion
                if self._state == TrevoState.PROCESSING:
                    dx = math.sin(elapsed * 8.0 + i * 0.5) * 0.03
                    dy = math.cos(elapsed * 6.0 + i * 0.7) * 0.03
                    dz = math.sin(elapsed * 7.0 + i * 0.3) * 0.03

                # Speaking: rhythmic radial pulse
                if self._state == TrevoState.SPEAKING:
                    wave = math.sin(elapsed * 4.0 + i * 0.02) * 0.04
                    length = math.sqrt(vx * vx + vy * vy + vz * vz) or 1.0
                    dx += (vx / length) * wave
                    dy += (vy / length) * wave
                    dz += (vz / length) * wave

                # Error: scatter outward
                if scatter > 0.0:
                    dx += math.sin(i * 1.7) * scatter
                    dy += math.cos(i * 2.3) * scatter
                    dz += math.sin(i * 3.1) * scatter

                displaced.append((
                    (vx + dx) * scale,
                    (vy + dy) * scale,
                    (vz + dz) * scale,
                ))

            # Draw edges as lines
            glLineWidth(1.5)
            glBegin(GL_LINES)
            for i1, i2 in self._edges:
                v1 = displaced[i1]
                v2 = displaced[i2]
                # Depth-based alpha for both endpoints
                for vx, vy, vz in (v1, v2):
                    depth = (vz + _SPHERE_RADIUS * scale) / (2.0 * _SPHERE_RADIUS * scale)
                    depth = max(0.0, min(1.0, depth))
                    alpha = 0.15 + 0.85 * depth
                    glColor4f(r, g, b, alpha)
                    glVertex3f(vx, vy, vz)
            glEnd()

            # Draw brighter vertex dots at intersections
            glPointSize(2.5)
            glBegin(GL_POINTS)
            for vx, vy, vz in displaced:
                depth = (vz + _SPHERE_RADIUS * scale) / (2.0 * _SPHERE_RADIUS * scale)
                depth = max(0.0, min(1.0, depth))
                alpha = 0.3 + 0.7 * depth
                glColor4f(r * 1.2, g * 1.2, b * 1.2, alpha)
                glVertex3f(vx, vy, vz)
            glEnd()

        def _draw_shards(
            self, elapsed: float, r: float, g: float, b: float
        ) -> None:
            """Draw small orbiting geometric fragments around the sphere."""
            glLineWidth(1.0)
            for orbit_r, incl, phase, speed, size in self._shards:
                angle = phase + elapsed * speed
                # Position on orbit
                sx = orbit_r * math.cos(angle)
                sy = orbit_r * math.sin(incl) * math.sin(angle)
                sz = orbit_r * math.cos(incl) * math.sin(angle)

                # Draw a small triangle (shard)
                alpha = 0.4 + 0.3 * math.sin(elapsed * 2.0 + phase)
                glColor4f(r, g, b, alpha)
                glBegin(GL_LINES)
                for j in range(3):
                    a1 = j * 2.0 * math.pi / 3
                    a2 = (j + 1) * 2.0 * math.pi / 3
                    glVertex3f(
                        sx + size * math.cos(a1),
                        sy + size * math.sin(a1),
                        sz,
                    )
                    glVertex3f(
                        sx + size * math.cos(a2),
                        sy + size * math.sin(a2),
                        sz,
                    )
                glEnd()


# ═══════════════════════════════════════════════════════════════════════════
# QPainter fallback sphere widget (Ultron orb — 2D projection)
# ═══════════════════════════════════════════════════════════════════════════
class _PainterSphereWidget(QWidget):
    """Pure QPainter 2D fallback that projects the wireframe icosphere."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._vertices, self._edges = _icosphere_geometry(2, _SPHERE_RADIUS)
        self._shards = _generate_shard_fragments(10)
        self._start_time = time.monotonic()

        self._current_color: Tuple[int, int, int] = _STATE_COLORS[TrevoState.IDLE]
        self._target_color: Tuple[int, int, int] = self._current_color
        self._prev_color: Tuple[int, int, int] = self._current_color
        self._core_color: Tuple[int, int, int] = _CORE_COLORS[TrevoState.IDLE]
        self._target_core: Tuple[int, int, int] = self._core_color
        self._prev_core: Tuple[int, int, int] = self._core_color
        self._transition_start = 0.0
        self._speed = _STATE_SPEEDS[TrevoState.IDLE]
        self._target_speed = self._speed
        self._state = TrevoState.IDLE
        self._error_scatter_time: float = 0.0

    def set_state(self, state: TrevoState) -> None:
        self._state = state
        self._prev_color = self._current_color
        self._target_color = _STATE_COLORS[state]
        self._prev_core = self._core_color
        self._target_core = _CORE_COLORS[state]
        self._target_speed = _STATE_SPEEDS[state]
        self._transition_start = time.monotonic()
        if state == TrevoState.ERROR:
            self._error_scatter_time = time.monotonic()

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        now = time.monotonic()
        elapsed = now - self._start_time

        t_frac = min(1.0, (now - self._transition_start) / (_TRANSITION_MS / 1000.0))
        wr, wg, wb = _lerp_color(self._prev_color, self._target_color, t_frac)
        self._current_color = (int(wr * 255), int(wg * 255), int(wb * 255))
        cr, cg, cb = _lerp_color(self._prev_core, self._target_core, t_frac)
        self._core_color = (int(cr * 255), int(cg * 255), int(cb * 255))
        self._speed += (self._target_speed - self._speed) * min(1.0, t_frac)

        w = self.width()
        h = self.height()
        cx_px = w / 2.0
        cy_px = h / 2.0
        proj_scale = min(w, h) * 0.35

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Rotation
        if self._state == TrevoState.PROCESSING:
            rot_y = elapsed * 60.0 * math.pi / 180.0
            rot_x = elapsed * 25.0 * math.pi / 180.0
        else:
            rot_y = elapsed * 15.0 * math.pi / 180.0
            rot_x = math.sin(elapsed * 0.3) * 5.0 * math.pi / 180.0

        # Scale
        scale = 1.0
        if self._state == TrevoState.SPEAKING:
            scale = 1.0 + 0.08 * math.sin(elapsed * 4.0)
        elif self._state == TrevoState.LISTENING:
            scale = 1.15 + 0.05 * math.sin(elapsed * 2.0)

        # --- Core glow
        pulse = 0.6 + 0.4 * math.sin(elapsed * self._speed * 2.0)
        core_radius = proj_scale * 0.35 * pulse
        gradient = QRadialGradient(cx_px, cy_px, core_radius)
        gradient.setColorAt(
            0.0,
            QColor(self._core_color[0], self._core_color[1],
                   self._core_color[2], int(pulse * 180)),
        )
        gradient.setColorAt(0.5, QColor(self._core_color[0], self._core_color[1],
                                        self._core_color[2], int(pulse * 60)))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(
            QRectF(cx_px - core_radius, cy_px - core_radius,
                   core_radius * 2, core_radius * 2)
        )

        # --- Compute displaced + rotated + projected vertices
        scatter = 0.0
        if self._state == TrevoState.ERROR:
            dt = elapsed - (self._error_scatter_time - self._start_time)
            if 0.0 < dt < 1.0:
                scatter = math.sin(dt * math.pi) * 0.6

        projected: list[Tuple[float, float, float]] = []  # (screen_x, screen_y, depth)
        cam_z = 3.5

        cos_ry, sin_ry = math.cos(rot_y), math.sin(rot_y)
        cos_rx, sin_rx = math.cos(rot_x), math.sin(rot_x)

        for i, (vx, vy, vz) in enumerate(self._vertices):
            dx = dy = dz = 0.0

            if self._state == TrevoState.PROCESSING:
                dx = math.sin(elapsed * 8.0 + i * 0.5) * 0.03
                dy = math.cos(elapsed * 6.0 + i * 0.7) * 0.03
                dz = math.sin(elapsed * 7.0 + i * 0.3) * 0.03

            if self._state == TrevoState.SPEAKING:
                length = math.sqrt(vx * vx + vy * vy + vz * vz) or 1.0
                wave = math.sin(elapsed * 4.0 + i * 0.02) * 0.04
                dx += (vx / length) * wave
                dy += (vy / length) * wave
                dz += (vz / length) * wave

            if scatter > 0.0:
                dx += math.sin(i * 1.7) * scatter
                dy += math.cos(i * 2.3) * scatter
                dz += math.sin(i * 3.1) * scatter

            px = (vx + dx) * scale
            py = (vy + dy) * scale
            pz = (vz + dz) * scale

            # Y rotation
            rx = px * cos_ry + pz * sin_ry
            rz1 = -px * sin_ry + pz * cos_ry
            # X rotation
            ry = py * cos_rx - rz1 * sin_rx
            rz = py * sin_rx + rz1 * cos_rx

            denom = cam_z - rz
            if denom <= 0.1:
                projected.append((cx_px, cy_px, -1.0))
                continue
            sx = cx_px + rx * proj_scale * (cam_z / denom)
            sy = cy_px - ry * proj_scale * (cam_z / denom)
            projected.append((sx, sy, rz))

        # --- Draw wireframe edges
        wire_color = self._current_color
        for i1, i2 in self._edges:
            sx1, sy1, z1 = projected[i1]
            sx2, sy2, z2 = projected[i2]
            if z1 < -_SPHERE_RADIUS * 1.5 or z2 < -_SPHERE_RADIUS * 1.5:
                continue
            avg_z = (z1 + z2) / 2.0
            depth = (avg_z + _SPHERE_RADIUS * scale) / (2.0 * _SPHERE_RADIUS * scale)
            depth = max(0.0, min(1.0, depth))
            alpha = int((0.12 + 0.88 * depth) * 255)
            pen = QPen(QColor(wire_color[0], wire_color[1], wire_color[2], alpha), 1.2)
            painter.setPen(pen)
            painter.drawLine(int(sx1), int(sy1), int(sx2), int(sy2))

        # --- Draw vertex dots
        for sx, sy, z in projected:
            if z < -_SPHERE_RADIUS * 1.5:
                continue
            depth = (z + _SPHERE_RADIUS * scale) / (2.0 * _SPHERE_RADIUS * scale)
            depth = max(0.0, min(1.0, depth))
            alpha = int((0.25 + 0.75 * depth) * 255)
            dot_r = 1.0 + 1.5 * depth
            color = QColor(wire_color[0], wire_color[1], wire_color[2], alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(sx - dot_r, sy - dot_r, dot_r * 2, dot_r * 2))

        # --- Draw orbiting shards
        for orbit_r, incl, phase, speed, size in self._shards:
            angle = phase + elapsed * speed
            sx_s = orbit_r * math.cos(angle)
            sy_s = orbit_r * math.sin(incl) * math.sin(angle)
            sz_s = orbit_r * math.cos(incl) * math.sin(angle)

            # Rotate + project
            rx_s = sx_s * cos_ry + sz_s * sin_ry
            rz_s = -sx_s * sin_ry + sz_s * cos_ry

            denom_s = cam_z - rz_s
            if denom_s <= 0.1:
                continue
            screen_x = cx_px + rx_s * proj_scale * (cam_z / denom_s)
            screen_y = cy_px - sy_s * proj_scale * (cam_z / denom_s)

            shard_alpha = int((0.3 + 0.3 * math.sin(elapsed * 2.0 + phase)) * 255)
            shard_size = size * proj_scale * (cam_z / denom_s)
            pen = QPen(QColor(wire_color[0], wire_color[1], wire_color[2], shard_alpha), 1.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            # Draw small triangle
            pts = []
            for j in range(3):
                a = j * 2.0 * math.pi / 3
                pts.append((screen_x + shard_size * math.cos(a),
                            screen_y + shard_size * math.sin(a)))
            for j in range(3):
                x1, y1 = pts[j]
                x2, y2 = pts[(j + 1) % 3]
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        painter.end()


# ═══════════════════════════════════════════════════════════════════════════
# Keyword bubbles — float around the orb
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class _Bubble:
    """A single floating keyword bubble."""
    text: str
    # Orbit parameters (polar around sphere centre)
    angle: float        # current angle in radians
    radius: float       # distance from centre
    speed: float        # radians per second
    y_offset: float     # vertical offset from centre
    opacity: float = 0.0
    target_opacity: float = 1.0
    born: float = 0.0   # time.monotonic() when created

class _KeywordBubbles(QWidget):
    """Draws keyword bubbles that orbit the sphere."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._bubbles: list[_Bubble] = []
        self._font = QFont("Inter", 11, QFont.Weight.Medium)
        self._color = _STATE_COLORS[TrevoState.SPEAKING]

    def set_keywords(self, keywords: list[str]) -> None:
        """Replace current bubbles with new keywords."""
        now = time.monotonic()
        self._bubbles.clear()
        n = len(keywords)
        for i, kw in enumerate(keywords):
            angle = (2 * math.pi * i / max(n, 1)) + random.uniform(-0.3, 0.3)
            radius = random.uniform(0.55, 0.75)  # as fraction of widget half-width
            speed = random.uniform(0.15, 0.4) * (1 if i % 2 == 0 else -1)
            y_off = random.uniform(-0.3, 0.3)
            self._bubbles.append(_Bubble(
                text=kw, angle=angle, radius=radius, speed=speed,
                y_offset=y_off, opacity=0.0, target_opacity=1.0, born=now,
            ))
        self.update()

    def add_keyword(self, kw: str) -> None:
        """Add a single keyword bubble."""
        now = time.monotonic()
        n = len(self._bubbles) + 1
        angle = random.uniform(0, 2 * math.pi)
        radius = random.uniform(0.55, 0.75)
        speed = random.uniform(0.15, 0.4) * random.choice([-1, 1])
        y_off = random.uniform(-0.3, 0.3)
        self._bubbles.append(_Bubble(
            text=kw, angle=angle, radius=radius, speed=speed,
            y_offset=y_off, opacity=0.0, target_opacity=1.0, born=now,
        ))

    def clear_bubbles(self) -> None:
        """Fade out all bubbles."""
        for b in self._bubbles:
            b.target_opacity = 0.0

    def set_color(self, rgb: Tuple[int, int, int]) -> None:
        self._color = rgb

    def tick(self, dt: float) -> None:
        """Advance animation. Call from parent's timer."""
        alive: list[_Bubble] = []
        for b in self._bubbles:
            b.angle += b.speed * dt
            # Fade in/out
            if b.opacity < b.target_opacity:
                b.opacity = min(b.target_opacity, b.opacity + dt * 2.0)
            elif b.opacity > b.target_opacity:
                b.opacity = max(b.target_opacity, b.opacity - dt * 2.0)
            # Remove fully faded out
            if b.opacity > 0.01 or b.target_opacity > 0:
                alive.append(b)
        self._bubbles = alive
        self.update()

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        if not self._bubbles:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self._font)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        half = min(cx, cy)

        r, g, b = self._color

        for bubble in self._bubbles:
            if bubble.opacity < 0.02:
                continue
            # Position on elliptical orbit
            bx = cx + math.cos(bubble.angle) * bubble.radius * half
            by = cy + math.sin(bubble.angle) * bubble.radius * half * 0.5 + bubble.y_offset * half

            alpha = int(bubble.opacity * 200)
            bg_alpha = int(bubble.opacity * 140)

            # Measure text
            fm = QFontMetrics(self._font)
            tw = fm.horizontalAdvance(bubble.text) + 16
            th = fm.height() + 8

            # Draw pill background
            pill = QRectF(bx - tw / 2, by - th / 2, tw, th)
            bg_color = QColor(r, g, b, bg_alpha // 3)
            border_color = QColor(r, g, b, bg_alpha)
            painter.setPen(QPen(border_color, 1.0))
            painter.setBrush(bg_color)
            painter.drawRoundedRect(pill, th / 2, th / 2)

            # Draw text
            painter.setPen(QColor(255, 255, 255, alpha))
            painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, bubble.text)

        painter.end()


# ═══════════════════════════════════════════════════════════════════════════
# Streaming text display — word-by-word below the orb
# ═══════════════════════════════════════════════════════════════════════════

class _StreamingText(QWidget):
    """Shows response text word by word as Trevo speaks."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._full_text: str = ""
        self._visible_chars: int = 0
        self._opacity: float = 0.0
        self._target_opacity: float = 0.0

        # Word-by-word reveal timer
        self._reveal_timer = QTimer(self)
        self._reveal_timer.setInterval(50)  # ~20 chars/sec
        self._reveal_timer.timeout.connect(self._reveal_next)

        self._font = QFont("Inter", 13, QFont.Weight.Normal)

    def stream_text(self, text: str) -> None:
        """Start streaming a full response word by word."""
        self._full_text = text
        self._visible_chars = 0
        self._target_opacity = 1.0
        self._reveal_timer.start()
        self.show()
        self.update()

    def append_text(self, text: str) -> None:
        """Append more text to the current stream (for real-time chunks)."""
        self._full_text += text
        if not self._reveal_timer.isActive():
            self._reveal_timer.start()
        self._target_opacity = 1.0
        self.show()

    def clear_text(self) -> None:
        """Clear and fade out."""
        self._reveal_timer.stop()
        self._full_text = ""
        self._visible_chars = 0
        self._target_opacity = 0.0
        self.update()

    def get_full_text(self) -> str:
        return self._full_text

    def tick(self, dt: float) -> None:
        """Advance fade animation."""
        if self._opacity < self._target_opacity:
            self._opacity = min(self._target_opacity, self._opacity + dt * 3.0)
        elif self._opacity > self._target_opacity:
            self._opacity = max(self._target_opacity, self._opacity - dt * 2.0)
            if self._opacity < 0.02:
                self.hide()
        self.update()

    def _reveal_next(self) -> None:
        """Show the next chunk of characters."""
        if self._visible_chars >= len(self._full_text):
            self._reveal_timer.stop()
            return
        # Reveal in word-sized chunks for natural feel
        next_space = self._full_text.find(" ", self._visible_chars + 1)
        if next_space == -1:
            self._visible_chars = len(self._full_text)
        else:
            self._visible_chars = next_space + 1
        self.update()

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        if not self._full_text or self._opacity < 0.02:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Glassmorphic background
        bg = QColor(15, 14, 23, int(self._opacity * 180))
        border = QColor(30, 144, 255, int(self._opacity * 40))
        rect = QRectF(8, 0, self.width() - 16, self.height())
        path = QPainterPath()
        path.addRoundedRect(rect, 12.0, 12.0)
        painter.setPen(QPen(border, 1.0))
        painter.setBrush(bg)
        painter.drawPath(path)

        # Draw visible portion of text
        visible = self._full_text[:self._visible_chars]
        if not visible:
            painter.end()
            return

        text_rect = rect.adjusted(14, 8, -14, -8)
        painter.setFont(self._font)
        painter.setPen(QColor(245, 243, 255, int(self._opacity * 240)))
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            visible,
        )

        # Blinking cursor at the end if still revealing
        if self._visible_chars < len(self._full_text):
            fm = QFontMetrics(self._font)
            # Simple cursor — just a pipe after text
            cursor_text = visible + "▌"
            painter.setPen(QColor(30, 144, 255, int(self._opacity * 180)))
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                cursor_text,
            )

        painter.end()


# ═══════════════════════════════════════════════════════════════════════════
# Temporary message overlay — legacy compat (kept slim)
# ═══════════════════════════════════════════════════════════════════════════
class _MessageOverlay(QWidget):
    """Floating message overlay — now delegates to streaming text + bubbles."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.hide()  # not used directly anymore

    def show_message(self, user_text: str, response_text: str) -> None:
        pass  # handled by _StreamingText + _KeywordBubbles now


# ═══════════════════════════════════════════════════════════════════════════
# Main window — Wireframe sphere with temporary message overlay
# ═══════════════════════════════════════════════════════════════════════════
class TrevoModeWindow(QWidget):
    """Frameless, always-on-top Trevo Mode overlay — Ultron orb.

    Features:
    - Keyword bubbles float around the orb (extracted key topics)
    - Streaming word-by-word text below the orb as Trevo speaks
    - Interruption clears text + bubbles and restarts listening
    """

    # Signals
    wake_phrase_detected = pyqtSignal()
    speech_text = pyqtSignal(str)
    close_requested = pyqtSignal()
    text_input_submitted = pyqtSignal(str)  # kept for compatibility

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # ── Window flags
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(_WINDOW_W, _WINDOW_H)

        # ── State
        self._state = TrevoState.IDLE
        self._drag_pos: Optional[QPoint] = None
        self._last_tick = time.monotonic()

        # ── Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 4)
        layout.setSpacing(0)

        # -- Sphere widget (orb area)
        if HAS_OPENGL:
            self._sphere: QWidget = _GLSphereWidget(self)
        else:
            self._sphere = _PainterSphereWidget(self)

        self._sphere.setMinimumSize(_SPHERE_SIZE, _SPHERE_SIZE)
        self._sphere.setMaximumHeight(_SPHERE_SIZE)
        layout.addWidget(self._sphere, stretch=0)

        # Status label below sphere
        self._status_label = QLabel(_STATE_LABELS[TrevoState.IDLE])
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet(
            "color: rgba(245,243,255,0.65); font-size: 13px; font-weight: 500; "
            "background: transparent; font-family: 'Inter', 'Segoe UI Variable', sans-serif;"
        )
        layout.addWidget(self._status_label)

        # -- Streaming text area below status
        self._streaming_text = _StreamingText(self)
        self._streaming_text.setFixedHeight(150)
        layout.addWidget(self._streaming_text, stretch=0)

        # -- Keyword bubbles (overlaid on top of sphere area)
        self._keyword_bubbles = _KeywordBubbles(self)
        self._keyword_bubbles.setGeometry(0, 0, _WINDOW_W, _SPHERE_SIZE + 30)
        self._keyword_bubbles.raise_()

        # -- Legacy message overlay (compatibility shim)
        self._message_overlay = _MessageOverlay(self)

        # ── Animation timer — drives sphere, bubbles, and streaming text
        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60 fps
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

        # Auto-fade timer for text after speaking finishes
        self._text_fade_timer = QTimer(self)
        self._text_fade_timer.setSingleShot(True)
        self._text_fade_timer.timeout.connect(self._fade_response)

    def _on_tick(self) -> None:
        """Master tick — advances all animations."""
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now
        self._sphere.update()
        self._keyword_bubbles.tick(dt)
        self._streaming_text.tick(dt)

    # ── Public API
    def set_state(self, state: TrevoState) -> None:
        """Transition to a new visual state."""
        prev_state = self._state
        self._state = state
        self._sphere.set_state(state)  # type: ignore[attr-defined]
        self._status_label.setText(_STATE_LABELS.get(state, ""))
        alpha = "0.65" if state == TrevoState.IDLE else "0.9"
        self._status_label.setStyleSheet(
            f"color: rgba(245,243,255,{alpha}); font-size: 13px; font-weight: 500; "
            f"background: transparent; font-family: 'Inter', 'Segoe UI Variable', sans-serif;"
        )

        # On interruption: user starts speaking → clear response + bubbles
        if state == TrevoState.LISTENING and prev_state == TrevoState.SPEAKING:
            self.clear_response()

        # Update bubble color to match state
        self._keyword_bubbles.set_color(
            _STATE_COLORS.get(state, _STATE_COLORS[TrevoState.IDLE])
        )

    def show_response(self, text: str) -> None:
        """Stream a response word-by-word + extract keyword bubbles."""
        self._text_fade_timer.stop()
        # Extract keywords and show as floating bubbles
        keywords = _extract_keywords(text)
        self._keyword_bubbles.set_keywords(keywords)
        # Stream the full text word by word
        self._streaming_text.stream_text(text)

    def append_response(self, text: str) -> None:
        """Append text to the current streaming response (for real-time chunks)."""
        self._streaming_text.append_text(text)
        # Extract new keywords from appended text
        new_kw = _extract_keywords(text, max_kw=2)
        for kw in new_kw:
            self._keyword_bubbles.add_keyword(kw)

    def clear_response(self) -> None:
        """Clear streaming text and fade out bubbles (on interruption)."""
        self._text_fade_timer.stop()
        self._streaming_text.clear_text()
        self._keyword_bubbles.clear_bubbles()

    def finish_speaking(self) -> None:
        """Called when Trevo finishes speaking — schedule fade after delay."""
        self._text_fade_timer.start(_MESSAGE_DISPLAY_MS)

    def _fade_response(self) -> None:
        """Auto-fade response text after display duration."""
        self._streaming_text.clear_text()
        self._keyword_bubbles.clear_bubbles()

    def show_message(self, user_text: str = "", response_text: str = "") -> None:
        """Show a response — routes to streaming text + keyword bubbles."""
        if response_text:
            self.show_response(response_text)

    def add_message(self, text: str, sender: str = "user") -> None:
        """Compatibility shim — routes to streaming text.

        When sender is 'user', stores text for pairing with response.
        When sender is 'trevo', shows both together.
        """
        if sender == "user":
            self._last_user_text = text
        else:
            self.show_response(text)
            self._last_user_text = ""

    def clear_chat(self) -> None:
        """Clear all response text and bubbles."""
        self.clear_response()

    def show_sphere(self) -> None:
        """Center on screen and show."""
        screen = self.screen()
        if screen is None:
            screen = _QGA.primaryScreen()
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

    # ── Painting (window background)
    def paintEvent(self, _event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Near-transparent dark background — lets the sphere be the focus
        bg = QColor(10, 8, 18, 200)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 20.0, 20.0)
        painter.drawPath(path)

        # Subtle electric blue border
        border_color = QColor(30, 144, 255, 35)
        painter.setPen(QPen(border_color, 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 20.0, 20.0
        )

        # Subtle divider line between sphere area and text area
        div_y = _SPHERE_SIZE + 44  # below status label
        painter.setPen(QPen(QColor(30, 144, 255, 20), 1.0))
        painter.drawLine(20, div_y, self.width() - 20, div_y)

        painter.end()

    # ── Keyboard / mouse events
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
        menu.setStyleSheet(
            "QMenu { background: rgba(10,8,18,0.95); color: #F5F3FF; "
            "border: 1px solid rgba(30,144,255,0.2); border-radius: 8px; padding: 4px 0; "
            "font-family: 'Inter', 'Segoe UI Variable', sans-serif; font-size: 13px; }"
            "QMenu::item { padding: 6px 20px; }"
            "QMenu::item:selected { background: rgba(30,144,255,0.25); }"
        )
        close_action = QAction("Close Trevo Mode", self)
        close_action.triggered.connect(lambda: (self.close_requested.emit(), self.hide_sphere()))
        menu.addAction(close_action)
        menu.exec(event.globalPos())

    # ── Cleanup
    def closeEvent(self, event: object) -> None:  # noqa: N802
        self._timer.stop()
        super().closeEvent(event)  # type: ignore[arg-type]
