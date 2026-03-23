"""Visual node-based workflow editor for trevo.

A DaVinci Resolve-inspired node graph editor built with PyQt6
QGraphicsScene / QGraphicsView.  Nodes are draggable boxes with typed
input/output ports connected by bezier-curve wires.

Usage::

    from trevo.ui.workflow_editor import WorkflowEditorDialog
    dlg = WorkflowEditorDialog(parent=None)
    dlg.exec()
"""

from __future__ import annotations

import logging
import math
from functools import partial
from pathlib import Path
from typing import Any

from PyQt6.QtCore import (
    QPointF,
    QRectF,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QTransform,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QToolBar,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.workflow_engine import (
    Port,
    Workflow,
    WorkflowConnection,
    WorkflowEngine,
    WorkflowNode,
    all_node_types,
    create_node,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Theme colours
# ---------------------------------------------------------------------------

_BG = QColor("#1a1a2e")
_NODE_BG = QColor("#16213e")
_NODE_BG_SELECTED = QColor("#1c2a4a")
_NODE_BORDER = QColor("#0f3460")
_NODE_BORDER_SELECTED = QColor("#e94560")
_TITLE_BG = QColor("#0f3460")
_TEXT = QColor("#eaeaea")
_TEXT_DIM = QColor("#a0a0b0")
_ACCENT = QColor("#e94560")
_GRID_LINE = QColor("#222244")
_GRID_LINE_MAJOR = QColor("#2a2a50")

PORT_COLORS: dict[str, QColor] = {
    "text": QColor("#4ade80"),
    "audio": QColor("#60a5fa"),
    "any": QColor("#e0e0e0"),
    "bool": QColor("#fb923c"),
    "number": QColor("#a78bfa"),
    "results": QColor("#facc15"),
}

_NODE_WIDTH = 180
_NODE_TITLE_H = 28
_PORT_RADIUS = 6
_PORT_SPACING = 24
_PORT_MARGIN_TOP = 10

# Category icons (unicode fallback -- no image assets required)
_CAT_ICONS: dict[str, str] = {
    "Input": "\u25b6",
    "Output": "\u25c0",
    "AI": "\u2726",
    "Processing": "\u2699",
    "Logic": "\u2442",
    "Utility": "\u2022",
}

# Category -> ordered list of node_type keys
NODE_CATEGORIES: dict[str, list[str]] = {}


def _build_categories() -> None:
    """Populate NODE_CATEGORIES from the executor registry."""
    NODE_CATEGORIES.clear()
    for ntype, cls in all_node_types().items():
        cat = cls.category
        NODE_CATEGORIES.setdefault(cat, []).append(ntype)


# ---------------------------------------------------------------------------
# Port graphics item
# ---------------------------------------------------------------------------

class PortItem(QGraphicsEllipseItem):
    """A small coloured circle representing an input or output port."""

    def __init__(
        self,
        port: Port,
        parent_node: NodeItem,
    ) -> None:
        r = _PORT_RADIUS
        super().__init__(-r, -r, r * 2, r * 2, parent_node)
        self.port = port
        self.parent_node = parent_node
        colour = PORT_COLORS.get(port.port_type, PORT_COLORS["any"])
        self.setBrush(QBrush(colour))
        self.setPen(QPen(colour.darker(130), 1.5))
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setZValue(3)

        # Tooltip
        direction = "Input" if port.direction == "input" else "Output"
        self.setToolTip(f"{direction}: {port.name} ({port.port_type})")

    # --- label next to port ------------------------------------------------

    def add_label(self) -> None:
        """Create a small text label next to the port circle."""
        label = QGraphicsSimpleTextItem(self.port.name, self.parent_node)
        label.setFont(QFont("Segoe UI", 8))
        label.setBrush(QBrush(_TEXT_DIM))
        pos = self.pos()
        if self.port.direction == "input":
            label.setPos(pos.x() + _PORT_RADIUS + 4, pos.y() - 7)
        else:
            tw = label.boundingRect().width()
            label.setPos(pos.x() - _PORT_RADIUS - 4 - tw, pos.y() - 7)


# ---------------------------------------------------------------------------
# Node graphics item
# ---------------------------------------------------------------------------

class NodeItem(QGraphicsRectItem):
    """Visual representation of a WorkflowNode on the canvas."""

    def __init__(self, node: WorkflowNode, scene: WorkflowScene) -> None:
        self.node = node
        self._scene = scene
        self.port_items: dict[str, PortItem] = {}

        # Calculate height based on port count.
        max_ports = max(len(node.inputs), len(node.outputs), 1)
        body_h = _PORT_MARGIN_TOP + max_ports * _PORT_SPACING + 8
        total_h = _NODE_TITLE_H + body_h

        super().__init__(0, 0, _NODE_WIDTH, total_h)
        self.setPos(node.position[0], node.position[1])
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setZValue(1)

        self._draw_body(total_h)
        self._create_ports(body_h)

    # ---- drawing ----------------------------------------------------------

    def _draw_body(self, total_h: float) -> None:
        """Set up gradients and title bar."""
        self.setBrush(QBrush(_NODE_BG))
        self.setPen(QPen(_NODE_BORDER, 1.5))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, False)

        # Title bar background
        title_rect = QGraphicsRectItem(0, 0, _NODE_WIDTH, _NODE_TITLE_H, self)
        gradient = QLinearGradient(0, 0, _NODE_WIDTH, 0)
        gradient.setColorAt(0, _TITLE_BG)
        gradient.setColorAt(1, _TITLE_BG.darker(120))
        title_rect.setBrush(QBrush(gradient))
        title_rect.setPen(QPen(Qt.PenStyle.NoPen))
        title_rect.setZValue(0)

        # Title text
        title = QGraphicsSimpleTextItem(self.node.label, self)
        title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        title.setBrush(QBrush(_TEXT))
        tw = title.boundingRect().width()
        title.setPos((_NODE_WIDTH - tw) / 2, 5)
        title.setZValue(2)

    def _create_ports(self, body_h: float) -> None:
        """Create port circles on left (inputs) and right (outputs)."""
        y_start = _NODE_TITLE_H + _PORT_MARGIN_TOP

        for i, port in enumerate(self.node.inputs):
            pi = PortItem(port, self)
            py = y_start + i * _PORT_SPACING
            pi.setPos(0, py)
            pi.add_label()
            self.port_items[f"in:{port.name}"] = pi

        for i, port in enumerate(self.node.outputs):
            pi = PortItem(port, self)
            py = y_start + i * _PORT_SPACING
            pi.setPos(_NODE_WIDTH, py)
            pi.add_label()
            self.port_items[f"out:{port.name}"] = pi

    # ---- selection visual -------------------------------------------------

    def paint(
        self,
        painter: QPainter,
        option: Any,
        widget: QWidget | None = None,
    ) -> None:
        """Override to change border colour when selected."""
        if self.isSelected():
            self.setPen(QPen(_NODE_BORDER_SELECTED, 2.0))
            self.setBrush(QBrush(_NODE_BG_SELECTED))
        else:
            self.setPen(QPen(_NODE_BORDER, 1.5))
            self.setBrush(QBrush(_NODE_BG))
        super().paint(painter, option, widget)

    # ---- keep model in sync -----------------------------------------------

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            pos = self.pos()
            self.node.position = (pos.x(), pos.y())
            self._scene.update_connections_for(self.node.id)
        return super().itemChange(change, value)

    # ---- context menu -----------------------------------------------------

    def contextMenuEvent(self, event: Any) -> None:  # noqa: N802
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu { background: #16213e; color: #eaeaea; border: 1px solid #0f3460; }"
            "QMenu::item:selected { background: #0f3460; }"
        )
        act_cfg = menu.addAction("Configure...")
        act_dup = menu.addAction("Duplicate")
        menu.addSeparator()
        act_del = menu.addAction("Delete")

        chosen = menu.exec(event.screenPos())
        if chosen == act_del:
            self._scene.delete_node(self.node.id)
        elif chosen == act_dup:
            self._scene.duplicate_node(self.node.id)
        elif chosen == act_cfg:
            self._scene.open_node_config(self.node.id)

    def mouseDoubleClickEvent(self, event: Any) -> None:  # noqa: N802
        self._scene.open_node_config(self.node.id)


# ---------------------------------------------------------------------------
# Connection (wire) graphics item
# ---------------------------------------------------------------------------

class ConnectionWire(QGraphicsPathItem):
    """A bezier curve connecting two ports."""

    def __init__(
        self,
        connection: WorkflowConnection,
        source: PortItem,
        target: PortItem,
    ) -> None:
        super().__init__()
        self.connection = connection
        self.source = source
        self.target = target

        colour = PORT_COLORS.get(source.port.port_type, PORT_COLORS["any"])
        self.setPen(QPen(colour, 2.5, Qt.PenStyle.SolidLine))
        self.setZValue(0)
        self.setAcceptHoverEvents(True)
        self.update_path()

    def update_path(self) -> None:
        """Recalculate the bezier curve between the two port items."""
        p1 = self.source.scenePos()
        p2 = self.target.scenePos()
        path = QPainterPath(p1)
        dx = abs(p2.x() - p1.x()) * 0.5
        dx = max(dx, 50.0)
        path.cubicTo(
            p1.x() + dx, p1.y(),
            p2.x() - dx, p2.y(),
            p2.x(), p2.y(),
        )
        self.setPath(path)

    def contextMenuEvent(self, event: Any) -> None:  # noqa: N802
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu { background: #16213e; color: #eaeaea; border: 1px solid #0f3460; }"
            "QMenu::item:selected { background: #0f3460; }"
        )
        act_del = menu.addAction("Delete Connection")
        chosen = menu.exec(event.screenPos())
        if chosen == act_del:
            scene = self.scene()
            if isinstance(scene, WorkflowScene):
                scene.delete_connection(self.connection.id)

    def hoverEnterEvent(self, event: Any) -> None:  # noqa: N802
        pen = self.pen()
        pen.setWidthF(4.0)
        self.setPen(pen)

    def hoverLeaveEvent(self, event: Any) -> None:  # noqa: N802
        pen = self.pen()
        pen.setWidthF(2.5)
        self.setPen(pen)


# ---------------------------------------------------------------------------
# Temporary wire (while dragging)
# ---------------------------------------------------------------------------

class TempWire(QGraphicsPathItem):
    """Rubber-band wire shown while the user drags from a port."""

    def __init__(self, start: QPointF, color: QColor) -> None:
        super().__init__()
        self._start = start
        pen = QPen(color, 2.0, Qt.PenStyle.DashLine)
        self.setPen(pen)
        self.setZValue(5)

    def update_end(self, end: QPointF) -> None:
        p1 = self._start
        dx = abs(end.x() - p1.x()) * 0.5
        dx = max(dx, 40.0)
        path = QPainterPath(p1)
        path.cubicTo(
            p1.x() + dx, p1.y(),
            end.x() - dx, end.y(),
            end.x(), end.y(),
        )
        self.setPath(path)


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------

class WorkflowScene(QGraphicsScene):
    """QGraphicsScene that owns all node/connection items and the workflow model."""

    node_selected = pyqtSignal(str)  # node_id
    node_deselected = pyqtSignal()
    workflow_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSceneRect(-4000, -4000, 8000, 8000)

        self.workflow: Workflow | None = None
        self._node_items: dict[str, NodeItem] = {}
        self._wire_items: dict[str, ConnectionWire] = {}
        self._temp_wire: TempWire | None = None
        self._drag_source_port: PortItem | None = None

    # ---- load a workflow --------------------------------------------------

    def load_workflow(self, workflow: Workflow) -> None:
        """Clear the scene and display the given workflow."""
        self.clear()
        self._node_items.clear()
        self._wire_items.clear()
        self.workflow = workflow

        for node in workflow.nodes.values():
            self._add_node_item(node)
        for conn in workflow.connections:
            self._add_wire_item(conn)

    def _add_node_item(self, node: WorkflowNode) -> NodeItem:
        item = NodeItem(node, self)
        self.addItem(item)
        self._node_items[node.id] = item
        return item

    def _add_wire_item(self, conn: WorkflowConnection) -> ConnectionWire | None:
        src_item = self._node_items.get(conn.from_node)
        dst_item = self._node_items.get(conn.to_node)
        if not src_item or not dst_item:
            return None
        src_port = src_item.port_items.get(f"out:{conn.from_port}")
        dst_port = dst_item.port_items.get(f"in:{conn.to_port}")
        if not src_port or not dst_port:
            return None
        wire = ConnectionWire(conn, src_port, dst_port)
        self.addItem(wire)
        self._wire_items[conn.id] = wire
        return wire

    # ---- mutations --------------------------------------------------------

    def add_node_at(self, node_type: str, pos: QPointF) -> WorkflowNode | None:
        """Create a new node and place it at *pos*."""
        if not self.workflow:
            return None
        try:
            node = create_node(node_type, position=(pos.x(), pos.y()))
        except KeyError:
            log.error("Unknown node type: %s", node_type)
            return None
        self.workflow.add_node(node)
        self._add_node_item(node)
        self.workflow_changed.emit()
        return node

    def delete_node(self, node_id: str) -> None:
        """Remove a node and its connections from the scene and model."""
        if not self.workflow:
            return
        # Remove wires first.
        conns_to_remove = [
            c for c in self.workflow.connections
            if c.from_node == node_id or c.to_node == node_id
        ]
        for c in conns_to_remove:
            self.delete_connection(c.id)
        # Remove item.
        item = self._node_items.pop(node_id, None)
        if item:
            self.removeItem(item)
        self.workflow.nodes.pop(node_id, None)
        self.workflow_changed.emit()

    def duplicate_node(self, node_id: str) -> None:
        """Duplicate a node (without connections)."""
        if not self.workflow:
            return
        orig = self.workflow.nodes.get(node_id)
        if not orig:
            return
        new = create_node(
            orig.node_type,
            label=orig.label + " (copy)",
            config=dict(orig.config),
            position=(orig.position[0] + 40, orig.position[1] + 40),
        )
        self.workflow.add_node(new)
        self._add_node_item(new)
        self.workflow_changed.emit()

    def delete_connection(self, conn_id: str) -> None:
        """Remove a connection wire."""
        if not self.workflow:
            return
        wire = self._wire_items.pop(conn_id, None)
        if wire:
            self.removeItem(wire)
        self.workflow.disconnect(conn_id)
        self.workflow_changed.emit()

    def create_connection(self, src_port: PortItem, dst_port: PortItem) -> None:
        """Create a connection between two port items."""
        if not self.workflow:
            return
        from_node = src_port.parent_node.node.id
        from_port = src_port.port.name
        to_node = dst_port.parent_node.node.id
        to_port = dst_port.port.name

        # Validate directions.
        if src_port.port.direction != "output" or dst_port.port.direction != "input":
            return
        # No self-connections.
        if from_node == to_node:
            return
        # Check type compatibility.
        if (
            src_port.port.port_type != dst_port.port.port_type
            and src_port.port.port_type != "any"
            and dst_port.port.port_type != "any"
        ):
            return

        conn = self.workflow.connect(from_node, from_port, to_node, to_port)
        self._add_wire_item(conn)
        self.workflow_changed.emit()

    def update_connections_for(self, node_id: str) -> None:
        """Refresh bezier paths for all wires touching *node_id*."""
        if not self.workflow:
            return
        for conn in self.workflow.connections:
            if conn.from_node == node_id or conn.to_node == node_id:
                wire = self._wire_items.get(conn.id)
                if wire:
                    wire.update_path()

    def open_node_config(self, node_id: str) -> None:
        """Emit a signal to open the config panel (handled by parent)."""
        self.node_selected.emit(node_id)

    # ---- port dragging (connection creation) ------------------------------

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        item = self.itemAt(event.scenePos(), QTransform())
        if isinstance(item, PortItem) and event.button() == Qt.MouseButton.LeftButton:
            self._drag_source_port = item
            colour = PORT_COLORS.get(item.port.port_type, PORT_COLORS["any"])
            self._temp_wire = TempWire(item.scenePos(), colour)
            self.addItem(self._temp_wire)
            return
        super().mousePressEvent(event)
        # Notify property panel of selection.
        sel = self.selectedItems()
        if sel and isinstance(sel[0], NodeItem):
            self.node_selected.emit(sel[0].node.id)
        else:
            self.node_deselected.emit()

    def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802
        if self._temp_wire:
            self._temp_wire.update_end(event.scenePos())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:  # noqa: N802
        if self._temp_wire and self._drag_source_port:
            item = self.itemAt(event.scenePos(), QTransform())
            if isinstance(item, PortItem) and item is not self._drag_source_port:
                src = self._drag_source_port
                dst = item
                # Allow dragging from either direction.
                if src.port.direction == "input" and dst.port.direction == "output":
                    src, dst = dst, src
                self.create_connection(src, dst)
            self.removeItem(self._temp_wire)
            self._temp_wire = None
            self._drag_source_port = None
            return
        super().mouseReleaseEvent(event)

    # ---- auto-arrange -----------------------------------------------------

    def auto_arrange(self) -> None:
        """Lay out nodes left-to-right based on topological order."""
        if not self.workflow:
            return
        from core.workflow_engine import WorkflowEngine
        try:
            order = WorkflowEngine._topological_sort(self.workflow)
        except ValueError:
            return

        x = 0.0
        for nid in order:
            item = self._node_items.get(nid)
            if item:
                item.setPos(x, 0)
                item.node.position = (x, 0.0)
                x += _NODE_WIDTH + 60
        for conn in self.workflow.connections:
            wire = self._wire_items.get(conn.id)
            if wire:
                wire.update_path()


# ---------------------------------------------------------------------------
# Canvas (QGraphicsView)
# ---------------------------------------------------------------------------

class WorkflowCanvas(QGraphicsView):
    """Pannable, zoomable viewport for the workflow scene."""

    def __init__(self, scene: WorkflowScene, parent: QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("border: none;")
        self.setBackgroundBrush(QBrush(_BG))

        self._panning = False
        self._pan_start = QPointF()
        self._zoom = 1.0

    # ---- grid background --------------------------------------------------

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        super().drawBackground(painter, rect)
        grid_size = 25
        left = int(rect.left()) - (int(rect.left()) % grid_size)
        top = int(rect.top()) - (int(rect.top()) % grid_size)

        # Minor grid
        painter.setPen(QPen(_GRID_LINE, 0.5))
        x = left
        while x < rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += grid_size
        y = top
        while y < rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += grid_size

        # Major grid (every 4)
        major = grid_size * 4
        left_m = int(rect.left()) - (int(rect.left()) % major)
        top_m = int(rect.top()) - (int(rect.top()) % major)
        painter.setPen(QPen(_GRID_LINE_MAJOR, 1.0))
        x = left_m
        while x < rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += major
        y = top_m
        while y < rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += major

    # ---- pan & zoom -------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        new_zoom = self._zoom * factor
        if 0.15 < new_zoom < 5.0:
            self._zoom = new_zoom
            self.scale(factor, factor)

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                int(self.horizontalScrollBar().value() - delta.x())
            )
            self.verticalScrollBar().setValue(
                int(self.verticalScrollBar().value() - delta.y())
            )
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: Any) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Delete:
            scene = self.scene()
            if isinstance(scene, WorkflowScene):
                for item in scene.selectedItems():
                    if isinstance(item, NodeItem):
                        scene.delete_node(item.node.id)
            return
        super().keyPressEvent(event)

    # ---- drop from palette ------------------------------------------------

    def dragEnterEvent(self, event: Any) -> None:  # noqa: N802
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event: Any) -> None:  # noqa: N802
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event: Any) -> None:  # noqa: N802
        node_type = event.mimeData().text()
        pos = self.mapToScene(event.position().toPoint())
        scene = self.scene()
        if isinstance(scene, WorkflowScene):
            scene.add_node_at(node_type, pos)
        event.acceptProposedAction()


# ---------------------------------------------------------------------------
# Node palette (sidebar)
# ---------------------------------------------------------------------------

class NodePalette(QWidget):
    """Sidebar listing available node types by category, drag-to-add."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        _build_categories()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        title = QLabel("Node Palette")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title.setStyleSheet("color: #eaeaea; padding: 6px;")
        layout.addWidget(title)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setStyleSheet(
            "QTreeWidget { background: #16213e; color: #eaeaea; border: none; }"
            "QTreeWidget::item { padding: 4px 8px; }"
            "QTreeWidget::item:hover { background: #0f3460; }"
            "QTreeWidget::item:selected { background: rgba(233,69,96,0.25); }"
        )
        self._tree.setDragEnabled(True)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

        ntypes = all_node_types()
        for cat, type_keys in NODE_CATEGORIES.items():
            icon = _CAT_ICONS.get(cat, "")
            cat_item = QTreeWidgetItem([f"{icon}  {cat}"])
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            for tk in type_keys:
                cls = ntypes[tk]
                child = QTreeWidgetItem([cls.display_name])
                child.setData(0, Qt.ItemDataRole.UserRole, tk)
                child.setToolTip(0, cls.description)
                cat_item.addChild(child)
            self._tree.addTopLevelItem(cat_item)
            cat_item.setExpanded(True)

        self._tree.itemPressed.connect(self._start_drag)
        layout.addWidget(self._tree)

        self.setMinimumWidth(180)
        self.setMaximumWidth(240)

    def _start_drag(self, item: QTreeWidgetItem, column: int) -> None:
        node_type = item.data(0, Qt.ItemDataRole.UserRole)
        if not node_type:
            return
        from PyQt6.QtCore import QMimeData
        from PyQt6.QtGui import QDrag

        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(node_type)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


# ---------------------------------------------------------------------------
# Properties panel (right sidebar)
# ---------------------------------------------------------------------------

class PropertiesPanel(QWidget):
    """Dynamic form showing configuration for the selected node."""

    config_changed = pyqtSignal(str, dict)  # node_id, new_config

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._current_node_id: str | None = None

        self._title = QLabel("Properties")
        self._title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._title.setStyleSheet("color: #eaeaea; padding: 6px 0;")
        self._layout.addWidget(self._title)

        self._form_container = QWidget()
        self._form_layout = QFormLayout(self._form_container)
        self._form_layout.setContentsMargins(0, 0, 0, 0)
        self._form_layout.setSpacing(8)
        self._layout.addWidget(self._form_container)

        self._layout.addStretch()

        self.setMinimumWidth(220)
        self.setMaximumWidth(320)

        self._editors: dict[str, QWidget] = {}

    def show_node(self, node: WorkflowNode | None) -> None:
        """Display configuration fields for *node*."""
        # Clear previous
        while self._form_layout.rowCount() > 0:
            self._form_layout.removeRow(0)
        self._editors.clear()

        if node is None:
            self._title.setText("Properties")
            self._current_node_id = None
            return

        self._current_node_id = node.id
        self._title.setText(f"{node.label}")

        # Node type (read-only)
        type_label = QLabel(node.node_type)
        type_label.setStyleSheet("color: #a0a0b0;")
        self._form_layout.addRow("Type:", type_label)

        # Label editor
        label_edit = QLineEdit(node.label)
        label_edit.setStyleSheet(
            "background: #1a1a2e; color: #eaeaea; border: 1px solid #0f3460; "
            "border-radius: 4px; padding: 4px;"
        )
        label_edit.textChanged.connect(lambda t, n=node: self._update_label(n, t))
        self._form_layout.addRow("Label:", label_edit)

        # Config fields
        ntypes = all_node_types()
        executor_cls = ntypes.get(node.node_type)
        defaults = executor_cls.default_config if executor_cls else {}

        for key, default_val in defaults.items():
            current = node.config.get(key, default_val)
            widget = self._create_editor(key, current, default_val, node)
            if widget:
                self._form_layout.addRow(f"{key.replace('_', ' ').title()}:", widget)
                self._editors[key] = widget

    def _create_editor(
        self, key: str, value: Any, default: Any, node: WorkflowNode
    ) -> QWidget | None:
        """Create an appropriate editor widget for a config value."""
        style = (
            "background: #1a1a2e; color: #eaeaea; border: 1px solid #0f3460; "
            "border-radius: 4px; padding: 4px;"
        )

        if isinstance(default, bool):
            combo = QComboBox()
            combo.addItems(["True", "False"])
            combo.setCurrentText(str(value))
            combo.setStyleSheet(style)
            combo.currentTextChanged.connect(
                lambda v, k=key, n=node: self._update_config(n, k, v == "True")
            )
            return combo

        if isinstance(default, (int, float)) and not isinstance(default, bool):
            if isinstance(default, int):
                spin = QSpinBox()
                spin.setRange(0, 999999)
                spin.setValue(int(value))
                spin.setStyleSheet(style)
                spin.valueChanged.connect(
                    lambda v, k=key, n=node: self._update_config(n, k, v)
                )
                return spin
            else:
                spin = QDoubleSpinBox()
                spin.setRange(0.0, 100.0)
                spin.setSingleStep(0.1)
                spin.setDecimals(2)
                spin.setValue(float(value))
                spin.setStyleSheet(style)
                spin.valueChanged.connect(
                    lambda v, k=key, n=node: self._update_config(n, k, v)
                )
                return spin

        # Known enum-like fields.
        known_choices: dict[str, list[str]] = {
            "engine": ["gemini", "google", "deepgram", "whisper", "openai"],
            "provider": ["groq", "gemini", "ollama", "openai", "anthropic", "claude_cli"],
            "style": ["formal", "casual", "bullet", "email", "clean", "technical"],
            "method": ["clipboard", "keyboard"],
            "condition_type": ["contains", "regex", "length", "language"],
            "target_language": ["en", "es", "fr", "de", "ja", "ko", "zh", "pt", "it", "ru", "ar", "hi"],
        }
        if key in known_choices:
            combo = QComboBox()
            choices = known_choices[key]
            combo.addItems(choices)
            if str(value) in choices:
                combo.setCurrentText(str(value))
            else:
                combo.addItem(str(value))
                combo.setCurrentText(str(value))
            combo.setStyleSheet(style)
            combo.currentTextChanged.connect(
                lambda v, k=key, n=node: self._update_config(n, k, v)
            )
            return combo

        # Long text (code, system_prompt, template).
        if key in ("code", "system_prompt", "template"):
            editor = QPlainTextEdit()
            editor.setPlainText(str(value))
            editor.setMaximumHeight(120)
            editor.setStyleSheet(
                "background: #1a1a2e; color: #eaeaea; border: 1px solid #0f3460; "
                "border-radius: 4px; font-family: Consolas; font-size: 11px;"
            )
            editor.textChanged.connect(
                lambda k=key, n=node, e=editor: self._update_config(n, k, e.toPlainText())
            )
            return editor

        # Default: string
        edit = QLineEdit(str(value))
        edit.setStyleSheet(style)
        edit.textChanged.connect(
            lambda v, k=key, n=node: self._update_config(n, k, v)
        )
        return edit

    @staticmethod
    def _update_config(node: WorkflowNode, key: str, value: Any) -> None:
        node.config[key] = value

    @staticmethod
    def _update_label(node: WorkflowNode, text: str) -> None:
        node.label = text


# ---------------------------------------------------------------------------
# Main editor dialog
# ---------------------------------------------------------------------------

class WorkflowEditorDialog(QDialog):
    """Full-window workflow editor with toolbar, palette, canvas, and properties."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WorkflowEditor")
        self.setWindowTitle("trevo - Workflow Editor")
        self.resize(1280, 800)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(self._stylesheet())

        self._engine = WorkflowEngine()
        self._scene = WorkflowScene(self)
        self._canvas = WorkflowCanvas(self._scene, self)
        self._canvas.setAcceptDrops(True)

        self._palette = NodePalette(self)
        self._properties = PropertiesPanel(self)

        # Signals
        self._scene.node_selected.connect(self._on_node_selected)
        self._scene.node_deselected.connect(self._on_node_deselected)

        self._build_ui()

        # Load a default workflow.
        presets = self._engine.get_builtin_workflows()
        if presets:
            self._load_workflow(presets[0])

    # ---- UI construction --------------------------------------------------

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Toolbar
        toolbar = self._build_toolbar()
        main_layout.addWidget(toolbar)

        # Splitter: palette | canvas | properties
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._palette)
        splitter.addWidget(self._canvas)
        splitter.addWidget(self._properties)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([200, 700, 260])
        main_layout.addWidget(splitter)

        # Status bar
        self._status = QStatusBar()
        self._status.setStyleSheet(
            "QStatusBar { background: #0f3460; color: #a0a0b0; font-size: 11px; padding: 2px 8px; }"
        )
        self._status.showMessage("Ready")
        main_layout.addWidget(self._status)

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(42)
        bar.setStyleSheet("background: #0f3460;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # Add Node dropdown
        add_btn = QToolButton()
        add_btn.setText("+ Add Node")
        add_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        add_btn.setStyleSheet(self._toolbar_btn_style())
        add_menu = QMenu(add_btn)
        add_menu.setStyleSheet(
            "QMenu { background: #16213e; color: #eaeaea; border: 1px solid #0f3460; }"
            "QMenu::item { padding: 6px 24px; }"
            "QMenu::item:selected { background: #0f3460; }"
        )
        _build_categories()
        ntypes = all_node_types()
        for cat, type_keys in NODE_CATEGORIES.items():
            sub = add_menu.addMenu(f"{_CAT_ICONS.get(cat, '')}  {cat}")
            sub.setStyleSheet(add_menu.styleSheet())
            for tk in type_keys:
                cls = ntypes[tk]
                act = sub.addAction(cls.display_name)
                act.triggered.connect(partial(self._add_node_center, tk))
        add_btn.setMenu(add_menu)
        layout.addWidget(add_btn)

        # Presets dropdown
        preset_btn = QToolButton()
        preset_btn.setText("Presets")
        preset_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        preset_btn.setStyleSheet(self._toolbar_btn_style())
        preset_menu = QMenu(preset_btn)
        preset_menu.setStyleSheet(add_menu.styleSheet())
        for wf in self._engine.get_builtin_workflows():
            act = preset_menu.addAction(wf.name)
            act.triggered.connect(partial(self._load_workflow, wf))
        preset_btn.setMenu(preset_menu)
        layout.addWidget(preset_btn)

        layout.addSpacing(12)

        # Run
        run_btn = QPushButton("\u25b6  Run")
        run_btn.setStyleSheet(
            "QPushButton { background: #22c55e; color: white; border-radius: 4px; "
            "padding: 4px 16px; font-weight: bold; }"
            "QPushButton:hover { background: #16a34a; }"
        )
        run_btn.clicked.connect(self._run_workflow)
        layout.addWidget(run_btn)

        layout.addStretch()

        # Auto arrange
        arrange_btn = QPushButton("Auto Arrange")
        arrange_btn.setStyleSheet(self._toolbar_btn_style())
        arrange_btn.clicked.connect(self._auto_arrange)
        layout.addWidget(arrange_btn)

        # Save / Load
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(self._toolbar_btn_style())
        save_btn.clicked.connect(self._save_workflow)
        layout.addWidget(save_btn)

        load_btn = QPushButton("Load")
        load_btn.setStyleSheet(self._toolbar_btn_style())
        load_btn.clicked.connect(self._load_workflow_from_file)
        layout.addWidget(load_btn)

        return bar

    # ---- actions ----------------------------------------------------------

    def _add_node_center(self, node_type: str) -> None:
        center = self._canvas.mapToScene(self._canvas.viewport().rect().center())
        self._scene.add_node_at(node_type, center)

    def _load_workflow(self, workflow: Workflow) -> None:
        self._scene.load_workflow(workflow)
        self.setWindowTitle(f"trevo - Workflow Editor - {workflow.name}")
        self._status.showMessage(f"Loaded: {workflow.name}")

    def _save_workflow(self) -> None:
        if not self._scene.workflow:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Workflow", "", "JSON Files (*.json)"
        )
        if path:
            self._engine.save_workflow(self._scene.workflow, Path(path))
            self._status.showMessage(f"Saved to {path}")

    def _load_workflow_from_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Workflow", "", "JSON Files (*.json)"
        )
        if path:
            try:
                wf = self._engine.load_workflow(Path(path))
                self._load_workflow(wf)
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"Failed to load workflow:\n{exc}")

    def _run_workflow(self) -> None:
        if not self._scene.workflow:
            return
        import asyncio as _asyncio

        self._status.showMessage("Running workflow...")

        def progress(node_id: str, status: str, current: int, total: int) -> None:
            self._status.showMessage(f"Running: {node_id} ({current}/{total})")

        async def _run() -> None:
            try:
                results = await self._engine.execute(
                    self._scene.workflow,
                    progress_callback=progress,
                )
                self._status.showMessage(
                    f"Workflow complete -- {len(results)} nodes executed"
                )
            except Exception as exc:
                self._status.showMessage(f"Error: {exc}")
                log.error("Workflow execution failed: %s", exc)

        # Run workflow in a background thread to avoid blocking the Qt event loop
        import threading

        def _run_in_thread():
            try:
                import asyncio as _aio
                _aio.run(_run())
            except Exception as exc:
                log.error("Workflow execution failed in thread: %s", exc)

        t = threading.Thread(target=_run_in_thread, daemon=True)
        t.start()

    def _auto_arrange(self) -> None:
        self._scene.auto_arrange()
        self._status.showMessage("Auto-arranged nodes")

    # ---- property panel signals -------------------------------------------

    def _on_node_selected(self, node_id: str) -> None:
        if self._scene.workflow and node_id in self._scene.workflow.nodes:
            self._properties.show_node(self._scene.workflow.nodes[node_id])

    def _on_node_deselected(self) -> None:
        self._properties.show_node(None)

    # ---- styling ----------------------------------------------------------

    @staticmethod
    def _toolbar_btn_style() -> str:
        return (
            "QPushButton, QToolButton { background: rgba(26,26,46,0.6); color: #eaeaea; "
            "border: 1px solid rgba(233,69,96,0.3); border-radius: 4px; "
            "padding: 4px 12px; font-size: 12px; }"
            "QPushButton:hover, QToolButton:hover { background: #e94560; border-color: #e94560; }"
        )

    @staticmethod
    def _stylesheet() -> str:
        return (
            "QDialog#WorkflowEditor { background: #1a1a2e; }"
            "QSplitter::handle { background: #0f3460; width: 2px; }"
            "QLabel { color: #eaeaea; }"
        )


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Launch the workflow editor as a standalone window."""
    import sys

    app = QApplication.instance() or QApplication(sys.argv)
    dlg = WorkflowEditorDialog()
    dlg.show()
    if not QApplication.instance() or not hasattr(app, "_exec_started"):
        app._exec_started = True  # type: ignore[union-attr]
        app.exec()


if __name__ == "__main__":
    main()
