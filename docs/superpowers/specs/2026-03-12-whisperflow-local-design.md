# WhisperFlow Local Clone — Design Spec
**Date:** 2026-03-12
**Status:** Approved (rev 2 — reviewer issues resolved)

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

## Chemins de données (`DATA_DIR`)

Toutes les données persistantes (settings, historique, logs, lockfile) utilisent un chemin absolu résolu à l'exécution :

```python
# app/engine/paths.py
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # packagé avec PyInstaller
    DATA_DIR = Path(sys.executable).parent / "data"
else:
    # développement
    DATA_DIR = Path(__file__).parent.parent.parent / "data"

DATA_DIR.mkdir(parents=True, exist_ok=True)
```

Tous les modules importent `DATA_DIR` depuis `app.engine.paths`. Aucun chemin relatif dans le code.

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
│       ├── paths.py         # DATA_DIR
│       ├── state.py         # machine d'états + signaux Qt
│       ├── hotkeys.py
│       ├── audio.py
│       ├── transcription.py
│       ├── cleanup.py
│       ├── injector.py
│       └── storage.py
├── data/                    # créé au premier lancement
│   ├── settings.json
│   ├── history.db
│   ├── whisperflow.log
│   └── whisperflow.lock
├── assets/
│   └── icon.png
└── docs/
```

---

## Machine d'états

```
                          ┌──(Escape / toggle)──┐
                          │                     ▼
IDLE ──(hotkey)──► RECORDING ──(stop)──► TRANSCRIBING ──(done)──► IDLE
                       │                     │   │
                    (error)              (error) (Escape / toggle)
                       │                     │   │
                       └─────────────────────►───┘
                                           IDLE
```

**Transitions valides :**

| De | Vers | Déclencheur |
|----|------|-------------|
| IDLE | RECORDING | hotkey |
| RECORDING | TRANSCRIBING | stop (release hold / toggle) |
| RECORDING | IDLE | Escape, error, durée < 300ms |
| TRANSCRIBING | IDLE | transcription terminée, Escape, toggle hotkey, error |

Toute transition non listée lève `ValueError` dans `AppState.transition()`.

### Interface `AppState` (`engine/state.py`)

```python
class AppState(QObject):
    state_changed = pyqtSignal(str)   # émet le nouveau nom d'état

    IDLE          = "IDLE"
    RECORDING     = "RECORDING"
    TRANSCRIBING  = "TRANSCRIBING"

    _VALID_TRANSITIONS = {
        IDLE:         {RECORDING},
        RECORDING:    {TRANSCRIBING, IDLE},
        TRANSCRIBING: {IDLE},
    }

    def transition(self, new_state: str) -> None:
        """Valide la transition et émet state_changed."""

    def current(self) -> str:
        """Retourne l'état courant."""
```

`AppState` est instancié une fois dans `main.py` et passé par injection de dépendance à tous les composants qui en ont besoin. Pas de singleton global.

---

## Pipeline fonctionnel

```
1.  Hotkey détectée
2.  state.transition(RECORDING)
3.  sounddevice stream démarre → chunks PCM accumulés en mémoire
4.  Overlay visible → visualiseur RMS ~30fps
5a. Hotkey relâchée (hold) ou pressée à nouveau (toggle)
    └── si durée < 300ms → state.transition(IDLE), discard silencieux
5b. Escape pressé → state.transition(IDLE), audio discardé, overlay masqué
6.  state.transition(TRANSCRIBING)
7.  Overlay → indicateur "…"
8.  np.concatenate(chunks) → faster-whisper.transcribe()
    └── si Escape/toggle pendant transcription → annulation, IDLE, pas d'injection
9.  cleanup(texte)
10. injection(texte)
11. storage.save(entrée)
12. state.transition(IDLE)
13. Overlay masqué
```

**Annulation pendant TRANSCRIBING :** si Escape ou toggle hotkey est pressé pendant la transcription, un `threading.Event` de cancel est activé. Le thread ASR vérifie cet event après `transcribe()` — si activé, il abandonne le résultat et retourne IDLE sans injection ni sauvegarde.

---

## Composants UI

### Overlay

- Fenêtre frameless, `Qt.WindowStaysOnTopHint`, non focusable, non cliquable
- **Position multi-écrans :** bas à droite du monitor contenant le curseur souris au moment du déclenchement hotkey (`QApplication.screenAt(QCursor.pos())`)
- Dimensions : ~380×48px, coins arrondis, opacité ~85%
- Trois états visuels :

```
IDLE         → invisible

RECORDING    → [⏺  ▁▃▇▅▂▆▄▁▃▇▅▂  00:04]
               barres RMS animées + durée
               → à 4:30 : barre orange "Limite 5min approche"

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
- **Hotkeys** : hold (défaut `Ctrl+Shift+Space`), toggle (défaut `Ctrl+Shift+D`). Si la combinaison est déjà prise par un autre processus (détecté au démarrage du listener), label rouge "⚠ Conflit détecté" affiché sous le champ. Pas de suggestion automatique dans le MVP.
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
- **Toggle** : `on_press` → START si IDLE, STOP si RECORDING, CANCEL si TRANSCRIBING

**Détection de conflit :** au démarrage du listener, si pynput lève une exception à l'enregistrement de la hotkey, le conflit est reporté via signal Qt → badge d'avertissement dans les réglages. Pas de détection live.

Listener recréé à chaque changement de réglages.

### Audio (`engine/audio.py`)

`sounddevice.InputStream` — 16kHz mono float32. Chunks accumulés dans liste mémoire pendant l'enregistrement. Niveau RMS poussé dans `rms_queue` pour le visualiseur (~30fps).

**Durée minimale :** si l'enregistrement s'arrête après moins de 300ms, les chunks sont discardés et l'état revient à IDLE sans déclencher de transcription.

**Durée maximale :** 5 minutes (300 secondes). À 4:30, l'overlay affiche un indicateur d'approche de limite. À 5:00, l'enregistrement s'arrête automatiquement et la transcription démarre. Mémoire max ~19MB (300s × 16000 × 4 bytes).

À l'arrêt : `np.concatenate(chunks)` transmis au thread ASR.

### Transcription (`engine/transcription.py`)

**Modèle et cache :** faster-whisper télécharge le modèle depuis Hugging Face au premier usage et le met en cache dans `~/.cache/huggingface/` (comportement par défaut de la bibliothèque). Ce téléchargement unique requiert une connexion internet ; le modèle tourne ensuite 100% offline. En cas d'interruption, la bibliothèque reprend ou re-télécharge au prochain lancement.

**Dialog premier lancement :** si le modèle n'est pas présent en cache, une boîte de dialogue bloquante s'affiche avant toute tentative de transcription. Elle présente une barre de progression alimentée par un callback de téléchargement. L'utilisateur peut annuler ; dans ce cas l'app reste fonctionnelle mais la transcription est désactivée jusqu'au prochain téléchargement réussi.

```python
model = WhisperModel("small", device="auto", compute_type="auto")
# auto → GPU (CUDA) si disponible, sinon CPU
# compute_type auto → float16 GPU / int8 CPU

segments, _ = model.transcribe(
    audio_np,
    language="fr",          # configurable
    vad_filter=True,        # supprime silences début/fin
    word_timestamps=False,
    initial_prompt=glossary_prompt,  # voir Glossaire ci-dessous
)
text = " ".join(s.text for s in segments).strip()
```

Chargement lazy au premier usage, modèle gardé en mémoire pour la session.

**Glossaire :** les mots du glossaire sont passés via le paramètre `initial_prompt` de `transcribe()`. Format : `"Glossaire: mot1, mot2, mot3"`. Ce prompt biaise le modèle à reconnaître ces termes. Si le glossaire est vide, `initial_prompt` n'est pas passé.

### Cleanup (`engine/cleanup.py`)

Trois passes, appliquées selon le niveau configuré :

| Niveau | Passes |
|--------|--------|
| Aucun | — |
| Léger | 1 + 2 |
| Moyen | 1 + 2 + 3 |

1. **Suppression mots parasites** — liste configurable (euh, hum, ben, voilà, enfin…)
2. **Déduplication immédiate** — regex avec flags `re.IGNORECASE | re.UNICODE` :
   `re.sub(r'\b(\w+)(\s+\1)+\b', r'\1', text, flags=re.IGNORECASE | re.UNICODE)`
3. **Normalisation ponctuation** — espaces avant `,.!?`, majuscule après `.!?`

### Injection (`engine/injector.py`)

Stratégie primaire : clipboard + paste avec restauration.

```python
def inject(text: str) -> None:
    try:
        previous = pyperclip.paste()
        pyperclip.copy(text)
        keyboard.send("ctrl+v")
        time.sleep(0.1)          # heuristique — voir note ci-dessous
        pyperclip.copy(previous)
    except Exception:
        # pyperclip indisponible (ex: pas de gestionnaire clipboard X11)
        keyboard.type(text)      # fallback : frappe caractère par caractère
```

**Note sur le délai de 100ms :** il s'agit d'une heuristique pragmatique suffisante pour la quasi-totalité des applications Windows. Sur des applications très lentes (Electron lourd, navigateur sous charge), un paste occasionnel peut échouer. C'est une limitation connue et acceptée du MVP. La restauration du clipboard se fait inconditionnellement après 100ms.

**Fallback** : déclenché uniquement si les opérations pyperclip lèvent une exception. Pas de détection du succès du Ctrl+V.

---

## Stockage

### `DATA_DIR/settings.json`

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

Fichier recréé avec defaults si absent ou corrompu.

### `DATA_DIR/history.db`

```sql
CREATE TABLE history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    raw_text   TEXT,
    clean_text TEXT,
    duration_s REAL
);
```

Rotation : 500 entrées max (suppression des plus anciennes).

### Autostart Windows

Clé registre `HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run`, écrite uniquement sur action utilisateur dans les réglages.

### Lockfile (`DATA_DIR/whisperflow.lock`)

Format : PID du processus en cours (entier ASCII).

Au démarrage :
1. Si le fichier n'existe pas → écrire PID courant, continuer.
2. Si le fichier existe → lire le PID.
   - Si le PID est en cours d'exécution (via `psutil.pid_exists`) → afficher une notification ballon tray Windows "WhisperFlow est déjà en cours d'exécution", quitter.
   - Si le PID n'est plus actif (processus mort) → lockfile périmé, écraser avec PID courant, continuer.

Suppression du lockfile à l'arrêt propre de l'application (`atexit`).

---

## Error Handling

| Situation | Comportement |
|-----------|-------------|
| Micro absent / permission refusée | Notification tray + log, retour IDLE |
| Modèle absent du cache | Dialog bloquant avec barre de progression téléchargement |
| Téléchargement interrompu | Re-téléchargement au prochain lancement |
| Transcription échoue | Notification tray, retour IDLE |
| Hotkey en conflit | Label rouge dans réglages "⚠ Conflit détecté", pas de suggestion MVP |
| Clipboard inaccessible (exception) | Fallback `keyboard.type()` automatique |
| App déjà lancée (PID actif) | Notification ballon tray, exit immédiat |
| Lockfile périmé (PID mort) | Écrasement silencieux, démarrage normal |
| Enregistrement < 300ms | Discard silencieux, retour IDLE |
| Enregistrement ≥ 5min | Auto-stop, transcription démarre normalement |
| Escape / toggle pendant TRANSCRIBING | Annulation, retour IDLE, pas d'injection |

**Logging :** `DATA_DIR/whisperflow.log`, rotation 2MB, niveau INFO. Format : `[ISO8601] [LEVEL] module: message`.

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
psutil
```

---

## Définition du succès MVP

- L'utilisateur peut dicter dans n'importe quel champ texte Windows
- L'expérience est rapide et discrète (overlay non intrusif)
- Le texte est propre sans LLM
- L'app reste légère au repos (pas d'écoute permanente)
- Remplace WhisperFlow pour un usage personnel principal
