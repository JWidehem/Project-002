from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QCheckBox, QLineEdit, QTextEdit, QPushButton, QGroupBox, QFormLayout,
)
from PyQt6.QtCore import Qt
import sounddevice as sd
from app.ui import theme

LANGUAGES = [("fr", "Français"), ("en", "English"), ("es", "Español")]
MODELS = ["tiny", "base", "small", "medium", "large-v3"]
CLEANUP_LEVELS = [("none", "Aucun"), ("light", "Léger"), ("medium", "Moyen")]


def _fmt_hotkey(h: str) -> str:
    """Convert pynput hotkey string to human-readable display."""
    _MAP = {
        "<ctrl>": "Ctrl", "<shift>": "Shift", "<alt>": "Alt", "<cmd>": "⊞",
        "<space>": "Space", "<enter>": "Enter", "<backspace>": "⌫",
        "<delete>": "Del", "<esc>": "Échap", "<tab>": "Tab",
        **{f"<f{i}>": f"F{i}" for i in range(1, 13)},
    }
    if not h:
        return "(non configuré)"
    return " + ".join(
        _MAP.get(p.strip().lower(), p.strip().upper()) for p in h.split("+")
    )


class HotkeyCapture(QPushButton):
    """
    Button that captures a keyboard shortcut when clicked.
    Stores the hotkey in pynput format (e.g. '<ctrl>+<shift>+<space>').
    Displays it in a human-readable form (e.g. 'Ctrl + Shift + Space').
    """

    def __init__(self, hotkey: str = "", parent=None) -> None:
        super().__init__(parent)
        self._hotkey = hotkey
        self._capturing = False
        self._update_display()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.clicked.connect(self._start_capture)

    # ── Public API ────────────────────────────────────────────────────────

    @property
    def hotkey(self) -> str:
        return self._hotkey

    def set_hotkey(self, h: str) -> None:
        self._hotkey = h
        if not self._capturing:
            self._update_display()

    # ── Internal ──────────────────────────────────────────────────────────

    def _update_display(self) -> None:
        if self._capturing:
            self.setText("Appuyez sur votre combinaison…")
            self.setStyleSheet(
                "QPushButton { background: rgba(201,168,76,0.12);"
                " border: 1px solid #C9A84C; color: #E8C96A;"
                " border-radius: 7px; padding: 7px 14px;"
                " font-size: 12px; text-align: left; }"
            )
        else:
            self.setText(_fmt_hotkey(self._hotkey))
            self.setStyleSheet(
                "QPushButton { background: rgba(14,12,8,0.82);"
                " border: 1px solid rgba(255,255,255,0.07);"
                " border-bottom: 1px solid rgba(201,168,76,0.32);"
                " color: #F0EDE0; border-radius: 7px;"
                " padding: 7px 14px; font-size: 12px; text-align: left; }"
                " QPushButton:hover { border-color: rgba(201,168,76,0.5); color: #C9A84C; }"
            )

    def _start_capture(self) -> None:
        self._capturing = True
        self._update_display()
        self.setFocus()

    def _stop_capture(self, new_hotkey: str | None) -> None:
        self._capturing = False
        if new_hotkey is not None:
            self._hotkey = new_hotkey
        self._update_display()
        self.clearFocus()

    # ── Qt overrides ──────────────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:
        if not self._capturing:
            super().keyPressEvent(event)
            return
        key = event.key()
        # Bare Escape cancels capture
        if key == Qt.Key.Key_Escape:
            self._stop_capture(None)
            event.accept()
            return
        # Ignore lone modifier presses
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt,
                   Qt.Key.Key_Meta, Qt.Key.Key_AltGr):
            event.accept()
            return
        # Build pynput combo string
        parts: list[str] = []
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("<ctrl>")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("<shift>")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("<alt>")
        _SPECIAL: dict = {
            Qt.Key.Key_Space:     "<space>",
            Qt.Key.Key_Return:    "<enter>",
            Qt.Key.Key_Enter:     "<enter>",
            Qt.Key.Key_Backspace: "<backspace>",
            Qt.Key.Key_Delete:    "<delete>",
            Qt.Key.Key_Tab:       "<tab>",
            **{getattr(Qt.Key, f"Key_F{i}"): f"<f{i}>" for i in range(1, 13)},
        }
        if key in _SPECIAL:
            parts.append(_SPECIAL[key])
        else:
            ch = event.text().lower()
            if ch and ch.isprintable() and not ch.isspace():
                parts.append(ch)
            else:
                event.accept()
                return
        if parts:
            self._stop_capture("+".join(parts))
        event.accept()

    def focusOutEvent(self, event) -> None:
        if self._capturing:
            self._stop_capture(None)
        super().focusOutEvent(event)


class SettingsWidget(QWidget):
    def __init__(self, settings: dict, on_save) -> None:
        super().__init__()
        self._on_save = on_save
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
        self.hold_capture = HotkeyCapture(s.get("hotkey_hold", ""))
        self.toggle_capture = HotkeyCapture(s.get("hotkey_toggle", ""))
        self.conflict_label = QLabel("")
        self.conflict_label.setStyleSheet("color: #C05A00;")
        hint_lbl = QLabel("Cliquez sur le bouton puis appuyez sur votre combinaison")
        hint_lbl.setStyleSheet("color:#383028; font-size:10px;")
        hk_form.addRow("Mode maintien", self.hold_capture)
        hk_form.addRow("Mode toggle", self.toggle_capture)
        hk_form.addRow("", hint_lbl)
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

        # Audio
        aud = QGroupBox("Audio")
        aud_form = QFormLayout(aud)
        self.device_combo = QComboBox()
        self.device_combo.addItem("Défaut système", None)
        current_device = s.get("audio_device")
        selected_idx = 0
        for i, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] > 0:
                label = f"{dev['name']} ({dev['hostapi']})"
                self.device_combo.addItem(label, i)
                if i == current_device:
                    selected_idx = self.device_combo.count() - 1
        self.device_combo.setCurrentIndex(selected_idx)
        aud_form.addRow("Microphone", self.device_combo)
        layout.addWidget(aud)

        # Compute
        cmp = QGroupBox("Accélération")
        cmp_form = QFormLayout(cmp)
        self.compute_combo = QComboBox()
        _COMPUTE_OPTIONS = [
            ("cpu",  "CPU uniquement (stable, recommandé)"),
            ("cuda", "GPU NVIDIA CUDA (rapide, nécessite CUDA)"),
            ("auto", "Auto (CPU ou GPU selon disponibilité)"),
        ]
        for code, label in _COMPUTE_OPTIONS:
            self.compute_combo.addItem(label, code)
        cur_dev = s.get("compute_device", "cpu")
        cidx2 = next((i for i, (c, _) in enumerate(_COMPUTE_OPTIONS) if c == cur_dev), 0)
        self.compute_combo.setCurrentIndex(cidx2)
        cuda_note = QLabel("⚠ CUDA : redémarrez l'app après changement")
        cuda_note.setStyleSheet("color:#504840; font-size:10px;")
        cmp_form.addRow("Processeur", self.compute_combo)
        cmp_form.addRow("", cuda_note)
        layout.addWidget(cmp)

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
            "hotkey_hold": self.hold_capture.hotkey,
            "hotkey_toggle": self.toggle_capture.hotkey,
            "model": self.model_combo.currentData(),
            "preload_model": self.preload_cb.isChecked(),
            "cleanup_level": self.cleanup_combo.currentData(),
            "filler_words": [w.strip() for w in self.fillers_edit.text().split(",") if w.strip()],
            "glossary": [w.strip() for w in self.glossary_edit.toPlainText().splitlines() if w.strip()],
            "audio_device": self.device_combo.currentData(),
            "compute_device": self.compute_combo.currentData(),
        }
        self._on_save(data)

    def show_conflict(self, message: str) -> None:
        self.conflict_label.setText(message)

    def sync_from(self, s: dict) -> None:
        """Update all form widgets to reflect a new settings dict (called externally)."""
        self.autostart_cb.setChecked(s.get("autostart", False))
        lang_idx = next((i for i, (c, _) in enumerate(LANGUAGES) if c == s.get("language", "fr")), 0)
        self.language_combo.setCurrentIndex(lang_idx)
        self.hold_capture.set_hotkey(s.get("hotkey_hold", ""))
        self.toggle_capture.set_hotkey(s.get("hotkey_toggle", ""))
        model = s.get("model", "small")
        midx = MODELS.index(model) if model in MODELS else 2
        self.model_combo.setCurrentIndex(midx)
        self.preload_cb.setChecked(s.get("preload_model", False))
        cl_idx = next((i for i, (c, _) in enumerate(CLEANUP_LEVELS) if c == s.get("cleanup_level", "light")), 1)
        self.cleanup_combo.setCurrentIndex(cl_idx)
        self.fillers_edit.setText(", ".join(s.get("filler_words", [])))
        self.glossary_edit.setPlainText("\n".join(s.get("glossary", [])))
        current_device = s.get("audio_device")
        for i in range(self.device_combo.count()):
            if self.device_combo.itemData(i) == current_device:
                self.device_combo.setCurrentIndex(i)
                break
        _COMPUTE_CODES = ["cpu", "cuda", "auto"]
        cd = s.get("compute_device", "cpu")
        cd_idx = _COMPUTE_CODES.index(cd) if cd in _COMPUTE_CODES else 0
        self.compute_combo.setCurrentIndex(cd_idx)


class SettingsWindow(QDialog):
    """Thin dialog wrapper around SettingsWidget."""

    def __init__(self, settings: dict, on_save) -> None:
        super().__init__()
        self.setWindowTitle("Réglages — WhisperFlow")
        self.setMinimumWidth(440)
        self.setStyleSheet(theme.STYLESHEET)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        def _save_and_close(data: dict) -> None:
            on_save(data)
            self.accept()

        self._widget = SettingsWidget(settings, _save_and_close)
        layout.addWidget(self._widget)

    def show_conflict(self, message: str) -> None:
        self._widget.show_conflict(message)
