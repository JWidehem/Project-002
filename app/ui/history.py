from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel,
)
from PyQt6.QtCore import Qt
import pyperclip
from app.ui import theme


class HistoryWidget(QWidget):
    def __init__(self, entries: list[dict], on_delete) -> None:
        super().__init__()
        self._on_delete = on_delete
        self._entries: list[dict] = []
        self._build_ui()
        self.refresh(entries)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Historique des dictées"))
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        self.copy_btn = QPushButton("📋 Copier")
        self.copy_btn.clicked.connect(self._copy_selected)
        self.delete_btn = QPushButton("🗑 Supprimer")
        self.delete_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(self.copy_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def refresh(self, entries: list[dict]) -> None:
        self._entries = entries
        self.list_widget.clear()
        for e in entries:
            dt = e.get("created_at", "")[:16]
            text = e.get("clean_text", "")
            preview = text[:60] + ("…" if len(text) > 60 else "")
            self.list_widget.addItem(f"{dt}  {preview}")

    def _on_row_changed(self, row: int) -> None:
        enabled = 0 <= row < len(self._entries)
        self.copy_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled)

    def _copy_selected(self) -> None:
        row = self.list_widget.currentRow()
        if 0 <= row < len(self._entries):
            pyperclip.copy(self._entries[row].get("clean_text", ""))

    def _delete_selected(self) -> None:
        row = self.list_widget.currentRow()
        if 0 <= row < len(self._entries):
            entry_id = self._entries[row].get("id")
            if entry_id is None:
                return
            self._on_delete(entry_id)
            self._entries = [e for e in self._entries if e.get("id") != entry_id]
            self.refresh(self._entries)


class HistoryWindow(QDialog):
    """Thin dialog wrapper around HistoryWidget."""

    def __init__(self, entries: list[dict], on_delete) -> None:
        super().__init__()
        self.setWindowTitle("Historique — WhisperFlow")
        self.setMinimumSize(500, 400)
        self.setStyleSheet(theme.STYLESHEET)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._widget = HistoryWidget(entries, on_delete)
        layout.addWidget(self._widget)

    def refresh(self, entries: list[dict]) -> None:
        self._widget.refresh(entries)
