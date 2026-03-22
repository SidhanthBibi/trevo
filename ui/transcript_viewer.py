"""Glassmorphism + shadcn-inspired transcript history viewer for trevo."""

from __future__ import annotations

import csv
import html
import io
from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence

from PyQt6.QtCore import Qt, QDate, QMargins
from PyQt6.QtGui import QFont, QColor, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TranscriptEntry:
    """Single transcript record used by the viewer."""

    id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    raw_text: str = ""
    polished_text: str = ""
    language: str = "en"
    app_context: str = ""
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _escape_html(text: str) -> str:
    """HTML-escape for safe display in QTextEdit."""
    return html.escape(text, quote=False).replace("\n", "<br>")


_GLASS_STYLESHEET = """
/* ---- Glass foundation ---- */
QDialog#TranscriptViewer {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(15, 15, 20, 235),
        stop:1 rgba(24, 24, 32, 240)
    );
}

/* ---- Card panels ---- */
QFrame#glassCard {
    background: rgba(255, 255, 255, 6);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
}

/* ---- Search bar ---- */
QLineEdit#searchBar {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 8px;
    padding: 8px 14px;
    color: #e4e4e7;
    font-size: 13px;
    selection-background-color: rgba(139, 92, 246, 0.4);
}
QLineEdit#searchBar:focus {
    border: 1px solid rgba(139, 92, 246, 0.55);
}
QLineEdit#searchBar::placeholder {
    color: rgba(161, 161, 170, 0.6);
}

/* ---- Filter controls ---- */
QDateEdit, QComboBox {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 6px;
    padding: 5px 10px;
    color: #d4d4d8;
    font-size: 12px;
    min-height: 28px;
}
QDateEdit:focus, QComboBox:focus {
    border: 1px solid rgba(139, 92, 246, 0.50);
}
QDateEdit::drop-down, QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: right center;
    width: 20px;
    border: none;
}
QComboBox QAbstractItemView {
    background: rgba(30, 30, 40, 245);
    border: 1px solid rgba(255, 255, 255, 0.10);
    color: #d4d4d8;
    selection-background-color: rgba(139, 92, 246, 0.35);
}

/* ---- Filter labels ---- */
QLabel.filterLabel {
    color: rgba(161, 161, 170, 0.75);
    font-size: 11px;
    font-weight: 500;
}

/* ---- Table ---- */
QTableWidget {
    background: transparent;
    alternate-background-color: rgba(255, 255, 255, 0.02);
    gridline-color: rgba(255, 255, 255, 0.04);
    border: none;
    color: #d4d4d8;
    font-size: 12px;
    selection-background-color: rgba(139, 92, 246, 0.22);
    selection-color: #f4f4f5;
    outline: 0;
}
QTableWidget::item {
    padding: 6px 10px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}
QTableWidget::item:selected {
    background: rgba(139, 92, 246, 0.18);
}
QHeaderView::section {
    background: rgba(255, 255, 255, 0.04);
    color: rgba(161, 161, 170, 0.85);
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    border-right: 1px solid rgba(255, 255, 255, 0.04);
}
QHeaderView::section:last {
    border-right: none;
}

/* ---- Detail panel ---- */
QTextEdit#detailPanel {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 10px;
    color: #d4d4d8;
    font-size: 13px;
    padding: 14px;
    selection-background-color: rgba(139, 92, 246, 0.35);
}

/* ---- Pagination ---- */
QLabel#pageLabel {
    color: rgba(161, 161, 170, 0.8);
    font-size: 12px;
}

/* ---- Buttons ---- */
QPushButton {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 8px;
    padding: 7px 18px;
    color: #d4d4d8;
    font-size: 12px;
    font-weight: 500;
    min-height: 30px;
}
QPushButton:hover {
    background: rgba(255, 255, 255, 0.10);
    border-color: rgba(139, 92, 246, 0.40);
    color: #f4f4f5;
}
QPushButton:pressed {
    background: rgba(139, 92, 246, 0.20);
}
QPushButton:disabled {
    background: rgba(255, 255, 255, 0.02);
    color: rgba(161, 161, 170, 0.35);
    border-color: rgba(255, 255, 255, 0.04);
}
QPushButton#btnDanger {
    border-color: rgba(239, 68, 68, 0.35);
    color: #fca5a5;
}
QPushButton#btnDanger:hover {
    background: rgba(239, 68, 68, 0.15);
    border-color: rgba(239, 68, 68, 0.55);
    color: #fecaca;
}
QPushButton#btnPrimary {
    background: rgba(139, 92, 246, 0.20);
    border-color: rgba(139, 92, 246, 0.40);
    color: #c4b5fd;
}
QPushButton#btnPrimary:hover {
    background: rgba(139, 92, 246, 0.30);
    color: #ddd6fe;
}

/* ---- Splitter handle ---- */
QSplitter::handle {
    background: rgba(255, 255, 255, 0.06);
    height: 2px;
    margin: 4px 40px;
    border-radius: 1px;
}

/* ---- Scrollbars ---- */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 0.10);
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(255, 255, 255, 0.18);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
    height: 0;
}
QScrollBar:horizontal {
    background: transparent;
    height: 8px;
}
QScrollBar::handle:horizontal {
    background: rgba(255, 255, 255, 0.10);
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover {
    background: rgba(255, 255, 255, 0.18);
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
    width: 0;
}
"""

LANGUAGES = ["All", "en", "es", "fr", "de", "ja", "zh", "ko", "pt", "hi"]


# ---------------------------------------------------------------------------
# Main viewer
# ---------------------------------------------------------------------------

class TranscriptViewer(QDialog):
    """Searchable, filterable, paginated transcript history viewer.

    Glassmorphism + shadcn/ui-inspired data-table aesthetic for the trevo
    voice-to-text desktop application.
    """

    PAGE_SIZE: int = 100

    # ---------------------------------------------------------------
    # Construction
    # ---------------------------------------------------------------

    def __init__(
        self,
        entries: Sequence[TranscriptEntry] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("TranscriptViewer")
        self.setWindowTitle("trevo \u2014 Transcript History")
        self.setMinimumSize(900, 620)

        self._all_entries: list[TranscriptEntry] = list(entries or [])
        self._filtered: list[TranscriptEntry] = list(self._all_entries)
        self._page: int = 0

        # Apply the built-in glass stylesheet
        self.setStyleSheet(_GLASS_STYLESHEET)

        self._build_ui()
        self._refresh_table()

    # ---------------------------------------------------------------
    # UI construction
    # ---------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(12)

        # ---- Title row ----
        title = QLabel("Transcript History")
        title.setStyleSheet(
            "color: #f4f4f5; font-size: 18px; font-weight: 700; "
            "letter-spacing: 0.3px; padding-bottom: 2px;"
        )
        subtitle = QLabel("Browse, search, and manage your voice transcriptions")
        subtitle.setStyleSheet(
            "color: rgba(161,161,170,0.70); font-size: 12px; padding-bottom: 4px;"
        )
        header_col = QVBoxLayout()
        header_col.setSpacing(2)
        header_col.addWidget(title)
        header_col.addWidget(subtitle)
        root.addLayout(header_col)

        # ---- Search bar row ----
        search_row = QHBoxLayout()
        search_row.setSpacing(10)

        self._search_edit = QLineEdit()
        self._search_edit.setObjectName("searchBar")
        self._search_edit.setPlaceholderText("Search transcripts...")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._apply_filters)
        search_row.addWidget(self._search_edit, stretch=3)

        root.addLayout(search_row)

        # ---- Filters row ----
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        lbl_from = QLabel("From")
        lbl_from.setProperty("class", "filterLabel")
        lbl_from.setStyleSheet("color: rgba(161,161,170,0.75); font-size: 11px;")
        filter_row.addWidget(lbl_from)

        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDate(QDate.currentDate().addMonths(-1))
        self._date_from.setDisplayFormat("yyyy-MM-dd")
        self._date_from.dateChanged.connect(self._apply_filters)
        filter_row.addWidget(self._date_from)

        lbl_to = QLabel("To")
        lbl_to.setStyleSheet("color: rgba(161,161,170,0.75); font-size: 11px;")
        filter_row.addWidget(lbl_to)

        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDate(QDate.currentDate())
        self._date_to.setDisplayFormat("yyyy-MM-dd")
        self._date_to.dateChanged.connect(self._apply_filters)
        filter_row.addWidget(self._date_to)

        lbl_lang = QLabel("Language")
        lbl_lang.setStyleSheet("color: rgba(161,161,170,0.75); font-size: 11px;")
        filter_row.addWidget(lbl_lang)

        self._lang_filter = QComboBox()
        self._lang_filter.addItems(LANGUAGES)
        self._lang_filter.setMinimumWidth(72)
        self._lang_filter.currentTextChanged.connect(self._apply_filters)
        filter_row.addWidget(self._lang_filter)

        filter_row.addStretch()
        root.addLayout(filter_row)

        # ---- Separator ----
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(255,255,255,0.06);")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # ---- Main splitter: table + detail ----
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(6)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["Timestamp", "Preview", "Language", "Context", "Duration"],
        )
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setWordWrap(False)

        header = self._table.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self._table.currentCellChanged.connect(self._on_row_selected)
        splitter.addWidget(self._table)

        # Detail panel
        self._detail = QTextEdit()
        self._detail.setObjectName("detailPanel")
        self._detail.setReadOnly(True)
        self._detail.setPlaceholderText("Select a transcript row to view details...")
        splitter.addWidget(self._detail)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)

        # ---- Pagination row ----
        page_row = QHBoxLayout()
        page_row.setSpacing(12)

        self._prev_btn = QPushButton("\u2039  Previous")
        self._prev_btn.setFixedWidth(110)
        self._prev_btn.clicked.connect(self._prev_page)
        page_row.addWidget(self._prev_btn)

        page_row.addStretch()

        self._page_label = QLabel("Page 1 of 1  (0 entries)")
        self._page_label.setObjectName("pageLabel")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page_row.addWidget(self._page_label)

        page_row.addStretch()

        self._next_btn = QPushButton("Next  \u203a")
        self._next_btn.setFixedWidth(110)
        self._next_btn.clicked.connect(self._next_page)
        page_row.addWidget(self._next_btn)

        root.addLayout(page_row)

        # ---- Action bar ----
        action_sep = QFrame()
        action_sep.setFrameShape(QFrame.Shape.HLine)
        action_sep.setStyleSheet("color: rgba(255,255,255,0.06);")
        action_sep.setFixedHeight(1)
        root.addWidget(action_sep)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._copy_btn = QPushButton("Copy to Clipboard")
        self._copy_btn.setObjectName("btnPrimary")
        self._copy_btn.clicked.connect(self._copy_selected)
        btn_row.addWidget(self._copy_btn)

        self._export_btn = QPushButton("Export CSV")
        self._export_btn.clicked.connect(self._export_csv)
        btn_row.addWidget(self._export_btn)

        self._delete_btn = QPushButton("Delete Selected")
        self._delete_btn.setObjectName("btnDanger")
        self._delete_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(self._delete_btn)

        btn_row.addStretch()
        root.addLayout(btn_row)

    # ---------------------------------------------------------------
    # Filtering
    # ---------------------------------------------------------------

    def _apply_filters(self) -> None:
        query = self._search_edit.text().strip().lower()
        lang = self._lang_filter.currentText()
        date_from = self._date_from.date().toPyDate()
        date_to = self._date_to.date().toPyDate()

        filtered: list[TranscriptEntry] = []
        for e in self._all_entries:
            # Date range
            entry_date = e.timestamp.date()
            if entry_date < date_from or entry_date > date_to:
                continue
            # Language
            if lang != "All" and e.language != lang:
                continue
            # Text search (raw + polished + context)
            if query:
                haystack = (
                    e.raw_text.lower()
                    + " " + e.polished_text.lower()
                    + " " + e.app_context.lower()
                )
                if query not in haystack:
                    continue
            filtered.append(e)

        self._filtered = filtered
        self._page = 0
        self._refresh_table()

    # ---------------------------------------------------------------
    # Table rendering
    # ---------------------------------------------------------------

    def _refresh_table(self) -> None:
        start = self._page * self.PAGE_SIZE
        end = start + self.PAGE_SIZE
        page_entries = self._filtered[start:end]

        self._table.setRowCount(len(page_entries))
        for row, entry in enumerate(page_entries):
            # Timestamp
            ts_item = QTableWidgetItem(entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"))
            ts_item.setForeground(QColor(161, 161, 170))
            self._table.setItem(row, 0, ts_item)

            # Preview (prefer polished, fall back to raw)
            preview_text = (entry.polished_text or entry.raw_text)[:140]
            self._table.setItem(row, 1, QTableWidgetItem(preview_text))

            # Language
            lang_item = QTableWidgetItem(entry.language.upper())
            lang_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            )
            lang_item.setForeground(QColor(139, 92, 246))
            self._table.setItem(row, 2, lang_item)

            # Context
            ctx_item = QTableWidgetItem(entry.app_context or "\u2014")
            ctx_item.setForeground(QColor(113, 113, 122))
            self._table.setItem(row, 3, ctx_item)

            # Duration
            mins, secs = divmod(int(entry.duration_seconds), 60)
            dur_item = QTableWidgetItem(f"{mins}:{secs:02d}")
            dur_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            dur_item.setForeground(QColor(161, 161, 170))
            self._table.setItem(row, 4, dur_item)

        # Pagination label
        total_pages = max(1, -(-len(self._filtered) // self.PAGE_SIZE))
        self._page_label.setText(
            f"Page {self._page + 1} of {total_pages}  ({len(self._filtered)} entries)"
        )
        self._prev_btn.setEnabled(self._page > 0)
        self._next_btn.setEnabled(end < len(self._filtered))

        self._detail.clear()

    # ---------------------------------------------------------------
    # Pagination
    # ---------------------------------------------------------------

    def _prev_page(self) -> None:
        if self._page > 0:
            self._page -= 1
            self._refresh_table()

    def _next_page(self) -> None:
        if (self._page + 1) * self.PAGE_SIZE < len(self._filtered):
            self._page += 1
            self._refresh_table()

    # ---------------------------------------------------------------
    # Detail panel
    # ---------------------------------------------------------------

    def _on_row_selected(
        self, row: int, _col: int, _prev_row: int, _prev_col: int
    ) -> None:
        idx = self._page * self.PAGE_SIZE + row
        if not (0 <= idx < len(self._filtered)):
            return
        entry = self._filtered[idx]
        mins, secs = divmod(int(entry.duration_seconds), 60)
        self._detail.setHtml(
            '<div style="font-family: system-ui, sans-serif; line-height: 1.6;">'
            '<table style="color: #a1a1aa; font-size: 12px; margin-bottom: 12px;">'
            f'<tr><td style="padding-right:14px;"><b style="color:#8b5cf6;">Timestamp</b></td>'
            f'<td>{_escape_html(entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"))}</td></tr>'
            f'<tr><td><b style="color:#8b5cf6;">Language</b></td>'
            f'<td>{_escape_html(entry.language.upper())}</td></tr>'
            f'<tr><td><b style="color:#8b5cf6;">Context</b></td>'
            f'<td>{_escape_html(entry.app_context or "N/A")}</td></tr>'
            f'<tr><td><b style="color:#8b5cf6;">Duration</b></td>'
            f'<td>{mins}:{secs:02d} ({entry.duration_seconds:.1f}s)</td></tr>'
            "</table>"
            '<hr style="border: none; border-top: 1px solid rgba(255,255,255,0.06); margin: 8px 0 12px 0;">'
            '<p style="color: #71717a; font-size: 11px; margin-bottom: 4px;">RAW TEXT</p>'
            f'<p style="color: #d4d4d8; font-size: 13px;">{_escape_html(entry.raw_text)}</p>'
            '<hr style="border: none; border-top: 1px solid rgba(255,255,255,0.04); margin: 10px 0;">'
            '<p style="color: #71717a; font-size: 11px; margin-bottom: 4px;">POLISHED TEXT</p>'
            f'<p style="color: #f4f4f5; font-size: 13px;">{_escape_html(entry.polished_text)}</p>'
            "</div>"
        )

    # ---------------------------------------------------------------
    # Actions
    # ---------------------------------------------------------------

    def _copy_selected(self) -> None:
        rows = sorted({idx.row() for idx in self._table.selectedIndexes()})
        if not rows:
            return
        texts: list[str] = []
        for r in rows:
            idx = self._page * self.PAGE_SIZE + r
            if 0 <= idx < len(self._filtered):
                e = self._filtered[idx]
                texts.append(e.polished_text or e.raw_text)
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText("\n\n".join(texts))

    def _delete_selected(self) -> None:
        rows = sorted(
            {idx.row() for idx in self._table.selectedIndexes()}, reverse=True
        )
        if not rows:
            return

        count = len(rows)
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete {count} selected transcript{'s' if count != 1 else ''}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        ids_to_remove: set[str] = set()
        for r in rows:
            idx = self._page * self.PAGE_SIZE + r
            if 0 <= idx < len(self._filtered):
                ids_to_remove.add(self._filtered[idx].id)

        self._all_entries = [
            e for e in self._all_entries if e.id not in ids_to_remove
        ]
        self._apply_filters()

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Transcripts", "transcripts.csv", "CSV Files (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "ID",
                    "Timestamp",
                    "Raw Text",
                    "Polished Text",
                    "Language",
                    "App Context",
                    "Duration (s)",
                ])
                for entry in self._filtered:
                    writer.writerow([
                        entry.id,
                        entry.timestamp.isoformat(),
                        entry.raw_text,
                        entry.polished_text,
                        entry.language,
                        entry.app_context,
                        f"{entry.duration_seconds:.1f}",
                    ])
            QMessageBox.information(
                self,
                "Export Complete",
                f"Exported {len(self._filtered)} entries to:\n{path}",
            )
        except OSError as exc:
            QMessageBox.warning(self, "Export Error", str(exc))

    # ---------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------

    def set_entries(self, entries: Sequence[TranscriptEntry]) -> None:
        """Replace the full transcript list and refresh the view."""
        self._all_entries = list(entries)
        self._apply_filters()
