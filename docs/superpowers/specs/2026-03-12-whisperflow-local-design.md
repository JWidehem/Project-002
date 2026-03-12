# WhisperFlow Local Clone — Design Spec
**Date:** 2026-03-12
**Status:** Approved

---

## Vision

Application desktop Windows locale permettant la dictée vocale dans n'importe quel champ texte via raccourcis clavier globaux. Usage strictement personnel, sans cloud, sans LLM, sans écoute permanente.

---

## Stack

- **Language :** Python 100%
- **UI :** PyQt6
- **ASR :** faster-whisper (modèle `small` par défaut)
- **Audio :** sounddevice
- **Hotkeys :** pynput
- **Injection :** pyperclip + keyboard
- **Stockage :** SQLite (historique) + JSON (settings)

---

## Architecture

### Approche retenue : Single process + threads

Un seul processus Python. Communication inter-threads via `queue.Queue` et signaux Qt (`pyqtSignal`). Pas de partage d'état direct entre threads.

```
Process unique
├── Thread principal  → PyQt6 event loop (overlay, tray, settings, history)
├── Thread hotkey     → pynput GlobalHotKeys listener
├── Thread audio      → sounddevice InputStream → buffer PCM
└── Thread ASR        → faster-whisper (lazy-loaded, garde en mémoire)
```

### Structure du projet

```
whisperflow/
├── main.py
├── app/
│   ├── ui/
│   │   ├── overlay.py
│   │   ├── tray.py
│   │   ├── settings.py
│   │   └── history.py
│   └── engine/
│       ├── state.py
│       ├── hotkeys.py
│       ├── audio.py
│       ├── transcription.py
│       ├── cleanup.py
│       ├── injector.py
│       └── storage.py
├── data/
│   ├── settings.json
│   └── history.db
├── assets/
│   └── icon.png
└── docs/
```

---

## Machine d'états

```
IDLE ──(hotkey)──► RECORDING ──(stop)──► TRANSCRIBING ──(done)──► IDLE
                       │                        │
                    (error)                  (error)
                       └──────────────────────►┘
                                             IDLE
```

---

## Pipeline fonctionnel

```
1. Hotkey détectée
2. state → RECORDING
3. sounddevice stream démarre → chunks PCM accumulés en mémoire
4. Overlay visible → visualiseur RMS ~30fps
5. Hotkey relâchée (hold) ou pressée à nouveau (toggle)
6. state → TRANSCRIBING
7. Overlay → indicateur "…"
8. np.concatenate(chunks) → faster-whisper.transcribe()
9. cleanup(texte)
10. Sauvegarde clipboard → pyperclip.copy(texte) → Ctrl+V → restauration clipboard
11. storage.save(entrée)
12. state → IDLE
13. Overlay masqué
```

---

## Composants UI

### Overlay

- Fenêtre frameless, `Qt.WindowStaysOnTopHint`, non focusable, non cliquable
- Position : bas à droite de l'écran, ~380×48px, coins arrondis, opacité ~85%
- Trois états visuels :

```
IDLE         → invisible

RECORDING    → [⏺  ▁▃▇▅▂▆▄▁▃▇▅▂  00:04]
               barres RMS animées + durée

TRANSCRIBING → [◌  Transcription…]
               spinner, pas de barres
```

- Icône tray : grise (idle), rouge (recording), orange (transcribing)

### Tray

Menu contextuel :
```
⚪ WhisperFlow — Idle
─────────────────────
📋 Historique
⚙️  Réglages
─────────────────────
🚪 Quitter
```

### Fenêtre Réglages

5 sections :
- **Général** : lancer au démarrage, langue
- **Hotkeys** : hold (défaut `Ctrl+Shift+Space`), toggle (défaut `Ctrl+Shift+D`)
- **Modèle** : choix modèle Whisper, option préchargement au démarrage
- **Nettoyage** : niveau (Aucun / Léger / Moyen), liste mots parasites
- **Glossaire** : zone texte multiline, un mot par ligne

### Fenêtre Historique

Liste anti-chronologique, actions par entrée : copier / supprimer. Pas de recherche MVP.

---

## Composants Engine

### Hotkeys (`engine/hotkeys.py`)

`pynput.keyboard.GlobalHotKeys` dans thread daemon. Deux modes :
- **Hold** : `on_press` → START_RECORDING, `on_release` → STOP_RECORDING
- **Toggle** : `on_press` → START si IDLE, STOP si RECORDING

Listener recréé à chaque changement de réglages.

### Audio (`engine/audio.py`)

`sounddevice.InputStream` — 16kHz mono float32. Chunks accumulés dans liste mémoire pendant l'enregistrement. Niveau RMS poussé dans `rms_queue` pour le visualiseur. À l'arrêt : `np.concatenate(chunks)` transmis au thread ASR.

### Transcription (`engine/transcription.py`)

```python
model = WhisperModel("small", device="auto", compute_type="auto")
# auto → GPU (CUDA) si disponible, sinon CPU
# compute_type auto → float16 GPU / int8 CPU

segments, _ = model.transcribe(
    audio_np,
    language="fr",       # configurable
    vad_filter=True,     # supprime silences début/fin
    word_timestamps=False,
)
text = " ".join(s.text for s in segments).strip()
```

Chargement lazy au premier usage, modèle gardé en mémoire pour la session.

### Cleanup (`engine/cleanup.py`)

Trois passes, appliquées selon le niveau configuré :

| Niveau | Passes |
|--------|--------|
| Aucun | — |
| Léger | 1 + 2 |
| Moyen | 1 + 2 + 3 |

1. **Suppression mots parasites** — liste configurable (euh, hum, ben, voilà, enfin…)
2. **Déduplication immédiate** — `r'\b(\w+)(\s+\1)+\b'` → `r'\1'`
3. **Normalisation ponctuation** — espaces avant `,.!?`, majuscule après `.!?`

### Injection (`engine/injector.py`)

```python
def inject(text):
    previous = pyperclip.paste()
    pyperclip.copy(text)
    keyboard.send("ctrl+v")
    time.sleep(0.1)
    pyperclip.copy(previous)   # restauration
```

Fallback automatique si Ctrl+V échoue : `keyboard.type(text)`.

---

## Stockage

### `data/settings.json`

```json
{
  "language": "fr",
  "model": "small",
  "preload_model": false,
  "hotkey_hold": "<ctrl>+<shift>+<space>",
  "hotkey_toggle": "<ctrl>+<shift>+d",
  "cleanup_level": "light",
  "filler_words": ["euh", "hum", "ben", "voilà", "enfin"],
  "glossary": [],
  "autostart": false
}
```

Fichier recréé avec defaults si corrompu.

### `data/history.db`

```sql
CREATE TABLE history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    raw_text   TEXT,
    clean_text TEXT,
    duration_s REAL
);
```

Rotation : 500 entrées max.

### Autostart Windows

Clé registre `HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run`, écrite uniquement sur action utilisateur dans les réglages.

---

## Error Handling

| Situation | Comportement |
|-----------|-------------|
| Micro absent / permission refusée | Notification tray + log, retour IDLE |
| Modèle non téléchargé | Dialog au premier lancement avec barre de progression |
| Transcription échoue | Notification tray, retour IDLE |
| Hotkey déjà prise | Warning dans réglages, suggestion alternative |
| Clipboard inaccessible | Fallback `keyboard.type()` automatique |
| App déjà lancée | Lockfile détecté → focus tray existant, exit |

Logging : `whisperflow.log` rotatif 2MB, niveau INFO.

---

## Dépendances

```
faster-whisper
sounddevice
numpy
PyQt6
pynput
pyperclip
keyboard
```

---

## Définition du succès MVP

- L'utilisateur peut dicter dans n'importe quel champ texte Windows
- L'expérience est rapide et discrète (overlay non intrusif)
- Le texte est propre sans LLM
- L'app reste légère au repos (pas d'écoute permanente)
- Remplace WhisperFlow pour un usage personnel principal
