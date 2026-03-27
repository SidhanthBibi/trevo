"""Raycast / VS Code-style command palette overlay for trevo."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QParallelAnimationGroup,
    QRect,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QKeyEvent,
    QPainter,
    QPainterPath,
    QPen,
    QScreen,
)
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PaletteAction:
    """A single command-palette entry."""

    id: str
    label: str
    icon: str
    shortcut: str = ""
    description: str = ""


# ---------------------------------------------------------------------------
# Default actions
# ---------------------------------------------------------------------------

DEFAULT_ACTIONS: list[PaletteAction] = [
    PaletteAction(id="start_dictation",      label="Start Dictation",       icon="\U0001f399",  shortcut="Right Ctrl"),
    PaletteAction(id="toggle_trevo_mode",    label="Toggle Trevo Mode",     icon="\U0001f52e",  shortcut="Ctrl+Shift+T"),
    PaletteAction(id="open_settings",        label="Open Settings",         icon="\u2699\ufe0f"),
    PaletteAction(id="view_history",         label="View History",          icon="\U0001f4cb"),
    PaletteAction(id="open_workflow_editor", label="Open Workflow Editor",  icon="\U0001f517"),
    PaletteAction(id="toggle_theme",         label="Toggle Theme",          icon="\U0001f319"),
    PaletteAction(id="quit_trevo",           label="Quit Trevo",           icon="\u274c"),
]


# ---------------------------------------------------------------------------
# Style constants
# ---------------------------------------------------------------------------

_PALETTE_WIDTH = 500
_BORDER_RADIUS = 16
_BG_COLOR = QColor(15, 14, 23, 234)          # rgba(15,14,23,0.92)
_BORDER_COLOR = QColor(124, 58, 237, 77)     # rgba(124,58,237,0.3)
_TEXT_PRIMARY = "#F5F3FF"
_TEXT_SECONDARY = "#B8A8D0"
_ACCENT = "rgba(124, 58, 237, {alpha})"
_FONT_FAMILY = '"Inter", "Segoe UI Variable", sans-serif'

_SEARCH_STYLE = f"""
QLineEdit#paletteSearch {{
    background: transparent;
    border: none;
    border-bottom: 1px solid rgba(124, 58, 237, 0.3);
    color: {_TEXT_PRIMARY};
    font-size: 16px;
    font-family: {_FONT_FAMILY};
    padding: 14px 16px;
    selection-background-color: rgba(124, 58, 237, 0.35);
}}
QLineEdit#paletteSearch::placeholder {{
    color: {_TEXT_SECONDARY};
}}
"""

_LIST_STYLE = f"""
QListWidget#paletteResults {{
    background: transparent;
    border: none;
    outline: none;
    font-family: {_FONT_FAMILY};
    color: {_TEXT_PRIMARY};
}}
QListWidget#paletteResults::item {{
    padding: 10px 16px;
    border-radius: 8px;
    margin: 2px 6px;
}}
QListWidget#paletteResults::item:hover {{
    background: rgba(124, 58, 237, 0.12);
}}
QListWidget#paletteResults::item:selected {{
    background: rgba(124, 58, 237, 0.20);
}}
"""


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------

def _fuzzy_score(query: str, text: str) -> int | None:
    """Return a match score for *query* against *text*, or ``None`` if no match.

    Lower scores are better.  The algorithm walks through *text* looking
    for each character of *query* in order, penalising gaps between
    consecutive matches so that tighter clusters rank higher.
    """
    query_lower = query.lower()
    text_lower = text.lower()
    qi = 0
    score = 0
    last_match = -1

    for ti, ch in enumerate(text_lower):
        if qi < len(query_lower) and ch == query_lower[qi]:
            gap = ti - last_match - 1 if last_match >= 0 else 0
            score += gap
            last_match = ti
            qi += 1

    if qi < len(query_lower):
        return None  # not all characters matched
    return score


# ---------------------------------------------------------------------------
# Custom item widget for rich rows
# ---------------------------------------------------------------------------

class _ActionItemWidget(QWidget):
    """Renders a single palette row: icon, label, shortcut badge."""

    def __init__(self, action: PaletteAction, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        # Icon
        icon_label = QLabel(action.icon)
        icon_label.setFixedWidth(28)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet(f"font-size: 16px; color: {_TEXT_PRIMARY};")
        layout.addWidget(icon_label)

        # Label
        name_label = QLabel(action.label)
        name_label.setStyleSheet(
            f"font-size: 14px; font-family: {_FONT_FAMILY}; color: {_TEXT_PRIMARY};"
        )
        layout.addWidget(name_label, stretch=1)

        # Shortcut badge
        if action.shortcut:
            badge = QLabel(action.shortcut)
            badge.setStyleSheet(
                f"font-size: 11px; font-family: {_FONT_FAMILY}; "
                f"color: {_TEXT_SECONDARY}; "
                "background: rgba(124, 58, 237, 0.15); "
                "border-radius: 4px; padding: 2px 8px;"
            )
            layout.addWidget(badge)


# ---------------------------------------------------------------------------
# CommandPalette widget
# ---------------------------------------------------------------------------

class CommandPalette(QWidget):
    """Translucent, always-on-top command palette overlay.

    Emits :pyqtSignal:`action_triggered` with the action *id* string
    when the user selects an entry.

    Usage::

        palette = CommandPalette(parent=main_window)
        palette.action_triggered.connect(handle_action)
        palette.toggle()
    """

    action_triggered = pyqtSignal(str)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        actions: Sequence[PaletteAction] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._actions: list[PaletteAction] = list(actions or DEFAULT_ACTIONS)
        self._visible_actions: list[PaletteAction] = list(self._actions)

        # ── Window flags ──────────────────────────────────────────────
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("CommandPalette")
        self.setFixedWidth(_PALETTE_WIDTH)

        # ── Opacity effect for fade animation ─────────────────────────
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        # ── Layout ────────────────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Search input
        self._search = QLineEdit()
        self._search.setObjectName("paletteSearch")
        self._search.setPlaceholderText("Type a command\u2026")
        self._search.setStyleSheet(_SEARCH_STYLE)
        self._search.textChanged.connect(self._on_filter)
        root.addWidget(self._search)

        # Results list
        self._results = QListWidget()
        self._results.setObjectName("paletteResults")
        self._results.setStyleSheet(_LIST_STYLE)
        self._results.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._results.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._results.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._results.itemClicked.connect(self._on_item_clicked)
        root.addWidget(self._results)

        # ── Animations ────────────────────────────────────────────────
        self._anim_group: QParallelAnimationGroup | None = None

        # Populate initial list
        self._populate(self._actions)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_actions(self, actions: Sequence[PaletteAction]) -> None:
        """Replace the available actions list."""
        self._actions = list(actions)
        self._search.clear()
        self._populate(self._actions)

    def add_action(self, action: PaletteAction) -> None:
        """Append a single action to the palette."""
        self._actions.append(action)
        self._on_filter(self._search.text())

    def show_palette(self) -> None:
        """Center on screen, show with fade-in animation, and focus search."""
        self._search.clear()
        self._populate(self._actions)

        # Center on the active screen
        screen = self._current_screen()
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - _PALETTE_WIDTH) // 2
        y = geo.y() + int(geo.height() * 0.28)
        self.move(x, y)
        self.adjustSize()

        self.show()
        self.raise_()
        self._search.setFocus()

        self._animate_show()

    def hide_palette(self) -> None:
        """Hide with fade-out animation."""
        self._animate_hide()

    def toggle(self) -> None:
        """Show if hidden, hide if visible."""
        if self.isVisible():
            self.hide_palette()
        else:
            self.show_palette()

    # ------------------------------------------------------------------
    # Painting — glass background
    # ------------------------------------------------------------------

    def paintEvent(self, event: object) -> None:  # noqa: N802
        """Draw the rounded-rect glass background with a subtle border."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(float(rect.x()), float(rect.y()),
                            float(rect.width()), float(rect.height()),
                            _BORDER_RADIUS, _BORDER_RADIUS)

        # Background fill
        painter.fillPath(path, QBrush(_BG_COLOR))

        # Border stroke
        pen = QPen(QColor(_BORDER_COLOR), 1.0)
        painter.setPen(pen)
        painter.drawPath(path)

        painter.end()

    # ------------------------------------------------------------------
    # Key handling
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent | None) -> None:  # noqa: N802
        """Handle Escape, Enter/Return, and arrow-key navigation."""
        if event is None:
            return

        key = event.key()

        if key == Qt.Key.Key_Escape:
            self.hide_palette()
            return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._execute_selected()
            return

        if key == Qt.Key.Key_Down:
            row = self._results.currentRow()
            if row < self._results.count() - 1:
                self._results.setCurrentRow(row + 1)
            return

        if key == Qt.Key.Key_Up:
            row = self._results.currentRow()
            if row > 0:
                self._results.setCurrentRow(row - 1)
            return

        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Focus policy — hide when focus leaves the palette
    # ------------------------------------------------------------------

    def focusOutEvent(self, event: object) -> None:  # noqa: N802
        """Hide palette when it loses focus entirely."""
        # Small delay so that clicking an item doesn't immediately close
        QTimer.singleShot(150, self._maybe_hide_on_focus_loss)

    def _maybe_hide_on_focus_loss(self) -> None:
        """Hide only if neither the search nor the list currently has focus."""
        focused = QApplication.focusWidget()
        if focused is not None and (focused is self._search or self.isAncestorOf(focused)):
            return
        if self.isVisible():
            self.hide_palette()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _current_screen(self) -> QScreen:
        """Return the screen the palette should appear on."""
        screen = None
        if self.parent() and isinstance(self.parent(), QWidget):
            screen = self.parent().screen()  # type: ignore[union-attr]
        if screen is None:
            screen = QApplication.primaryScreen()
        assert screen is not None
        return screen

    def _populate(self, actions: Sequence[PaletteAction]) -> None:
        """Fill the results list with the given actions."""
        self._results.clear()
        self._visible_actions = list(actions)

        for action in actions:
            item = QListWidgetItem()
            widget = _ActionItemWidget(action)
            item.setSizeHint(QSize(_PALETTE_WIDTH - 12, 42))
            item.setData(Qt.ItemDataRole.UserRole, action.id)
            self._results.addItem(item)
            self._results.setItemWidget(item, widget)

        if self._results.count() > 0:
            self._results.setCurrentRow(0)

        # Cap height so the palette doesn't grow unbounded
        row_count = min(self._results.count(), 8)
        list_height = row_count * 46 + 8
        self._results.setFixedHeight(max(list_height, 46))

    def _on_filter(self, text: str) -> None:
        """Re-populate the results list based on fuzzy match of *text*."""
        query = text.strip()
        if not query:
            self._populate(self._actions)
            return

        scored: list[tuple[int, PaletteAction]] = []
        for action in self._actions:
            score = _fuzzy_score(query, action.label)
            if score is not None:
                scored.append((score, action))

        scored.sort(key=lambda t: t[0])
        self._populate([a for _, a in scored])

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Execute the action behind a clicked item."""
        action_id = item.data(Qt.ItemDataRole.UserRole)
        if action_id:
            self.hide_palette()
            self.action_triggered.emit(str(action_id))

    def _execute_selected(self) -> None:
        """Execute the currently highlighted action."""
        item = self._results.currentItem()
        if item is None:
            return
        action_id = item.data(Qt.ItemDataRole.UserRole)
        if action_id:
            self.hide_palette()
            self.action_triggered.emit(str(action_id))

    # ------------------------------------------------------------------
    # Animations
    # ------------------------------------------------------------------

    def _stop_running_animations(self) -> None:
        """Stop any in-progress animation group."""
        if self._anim_group is not None:
            self._anim_group.stop()
            self._anim_group = None

    def _animate_show(self) -> None:
        """Fade-in: opacity 0 -> 1 and scale 0.95 -> 1.0 over 200 ms."""
        self._stop_running_animations()

        group = QParallelAnimationGroup(self)

        # Opacity animation
        opacity_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        opacity_anim.setDuration(200)
        opacity_anim.setStartValue(0.0)
        opacity_anim.setEndValue(1.0)
        opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        group.addAnimation(opacity_anim)

        # Scale simulation via geometry animation
        target_geo = self.geometry()
        dx = int(target_geo.width() * 0.025)
        dy = int(target_geo.height() * 0.025)
        start_geo = target_geo.adjusted(dx, dy, -dx, -dy)

        geo_anim = QPropertyAnimation(self, b"geometry", self)
        geo_anim.setDuration(200)
        geo_anim.setStartValue(start_geo)
        geo_anim.setEndValue(target_geo)
        geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        group.addAnimation(geo_anim)

        self._anim_group = group
        group.start()

    def _animate_hide(self) -> None:
        """Fade-out: opacity 1 -> 0 over 150 ms, then actually hide."""
        self._stop_running_animations()

        group = QParallelAnimationGroup(self)

        opacity_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        opacity_anim.setDuration(150)
        opacity_anim.setStartValue(1.0)
        opacity_anim.setEndValue(0.0)
        opacity_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        group.addAnimation(opacity_anim)

        # Slight scale-down
        current_geo = self.geometry()
        dx = int(current_geo.width() * 0.015)
        dy = int(current_geo.height() * 0.015)
        end_geo = current_geo.adjusted(dx, dy, -dx, -dy)

        geo_anim = QPropertyAnimation(self, b"geometry", self)
        geo_anim.setDuration(150)
        geo_anim.setStartValue(current_geo)
        geo_anim.setEndValue(end_geo)
        geo_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        group.addAnimation(geo_anim)

        group.finished.connect(self._on_hide_finished)
        self._anim_group = group
        group.start()

    def _on_hide_finished(self) -> None:
        """Actually hide the widget once the fade-out completes."""
        self.hide()
        # Reset opacity for next show
        self._opacity_effect.setOpacity(1.0)
