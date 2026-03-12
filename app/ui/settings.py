from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QCheckBox, QLineEdit, QTextEdit, QPushButton, QGroupBox, QFormLayout,
)
from PyQt6.QtCore import Qt

LANGUAGES = [("fr", "Français"), ("en", "English"), ("es", "Español")]
MODELS = ["tiny", "base", "small", "medium", "large-v3"]
CLEANUP_LEVELS = [("none", "Aucun"), ("light", "Léger"), ("medium", "Moyen")]


class SettingsWindow(QDialog):
    def __init__(self, settings: dict, on_save) -> None:
        super().__init__()
        self._on_save = on_save
        self.setWindowTitle("Réglages — WhisperFlow")
        self.setMinimumWidth(440)
        self._build_ui(settings)

    def _build_ui(self, s: dict) -> None:
        layout = QVBoxLayout(self)

        # General
        gen = QGroupBox("Général")
        gen_form = QFormLayout(gen)
        self.autostart_cb = QCheckBox()
        self.autostart_cb.setChecked(s.get("autostart", False))
        self.language_combo = QComboBox()
        for code, label in LANGUAGES:
            self.language_combo.addItem(label, code)
        idx = next((i for i, (c, _) in enumerate(LANGUAGES) if c == s.get("language", "fr")), 0)
        self.language_combo.setCurrentIndex(idx)
        gen_form.addRow("Lancer au démarrage", self.autostart_cb)
        gen_form.addRow("Langue", self.language_combo)
        layout.addWidget(gen)

        # Hotkeys
        hk = QGroupBox("Hotkeys")
        hk_form = QFormLayout(hk)
        self.hold_edit = QLineEdit(s.get("hotkey_hold", ""))
        self.toggle_edit = QLineEdit(s.get("hotkey_toggle", ""))
        self.conflict_label = QLabel("")
        self.conflict_label.setStyleSheet("color: red")
        hk_form.addRow("Mode maintien", self.hold_edit)
        hk_form.addRow("Mode toggle", self.toggle_edit)
        hk_form.addRow("", self.conflict_label)
        layout.addWidget(hk)

        # Model
        mdl = QGroupBox("Modèle")
        mdl_form = QFormLayout(mdl)
        self.model_combo = QComboBox()
        for m in MODELS:
            self.model_combo.addItem(m, m)
        midx = MODELS.index(s.get("model", "small")) if s.get("model", "small") in MODELS else 2
        self.model_combo.setCurrentIndex(midx)
        self.preload_cb = QCheckBox()
        self.preload_cb.setChecked(s.get("preload_model", False))
        mdl_form.addRow("Modèle Whisper", self.model_combo)
        mdl_form.addRow("Charger au démarrage", self.preload_cb)
        layout.addWidget(mdl)

        # Cleanup
        cl = QGroupBox("Nettoyage")
        cl_form = QFormLayout(cl)
        self.cleanup_combo = QComboBox()
        for code, label in CLEANUP_LEVELS:
            self.cleanup_combo.addItem(label, code)
        cidx = next((i for i, (c, _) in enumerate(CLEANUP_LEVELS) if c == s.get("cleanup_level", "light")), 1)
        self.cleanup_combo.setCurrentIndex(cidx)
        self.fillers_edit = QLineEdit(", ".join(s.get("filler_words", [])))
        cl_form.addRow("Niveau", self.cleanup_combo)
        cl_form.addRow("Mots à ignorer", self.fillers_edit)
        layout.addWidget(cl)

        # Glossary
        gl = QGroupBox("Glossaire")
        gl_layout = QVBoxLayout(gl)
        self.glossary_edit = QTextEdit()
        self.glossary_edit.setPlainText("\n".join(s.get("glossary", [])))
        self.glossary_edit.setFixedHeight(80)
        gl_layout.addWidget(self.glossary_edit)
        layout.addWidget(gl)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.save_btn = QPushButton("Enregistrer")
        self.save_btn.clicked.connect(self._save)
        btn_row.addWidget(self.save_btn)
        layout.addLayout(btn_row)

    def _save(self) -> None:
        data = {
            "autostart": self.autostart_cb.isChecked(),
            "language": self.language_combo.currentData(),
            "hotkey_hold": self.hold_edit.text().strip(),
            "hotkey_toggle": self.toggle_edit.text().strip(),
            "model": self.model_combo.currentData(),
            "preload_model": self.preload_cb.isChecked(),
            "cleanup_level": self.cleanup_combo.currentData(),
            "filler_words": [w.strip() for w in self.fillers_edit.text().split(",") if w.strip()],
            "glossary": [w.strip() for w in self.glossary_edit.toPlainText().splitlines() if w.strip()],
        }
        self._on_save(data)

    def show_conflict(self, message: str) -> None:
        self.conflict_label.setText(message)
