# WhisperFlow — Suivi de projet

> Document de passation destiné à un agent LLM prenant le relais.  
> Dernière mise à jour : 2026-03-13 — **v1 livrée, stable**

---

## Vision

Application desktop Windows de dictée vocale locale. L'utilisateur parle, le texte est transcrit et injecté dans le champ actif — sans cloud, sans LLM, sans écoute permanente.

**Lancement :** `pythonw main.py` (sans console) ou `python main.py` (debug)

---

## État : v1 stable ✅

- [x] Tous les composants engine + UI implémentés
- [x] Tests unitaires, 100% passants (`pytest tests/ -v`)
- [x] Smoke test manuel validé — dictée, injection, historique, réglages OK
- [x] Icônes `assets/logo.png` + `assets/logo.ico` présentes
- [x] Raccourci bureau configuré (`WhisperFlow.lnk` → `pythonw main.py`, icône logo, WindowStyle=7)
- [x] Démarrage automatique Windows optionnel (registre HKCU)

---

## Architecture

```
Process unique
├── Thread Qt main   → main_window, overlay, tray, history, settings
├── Thread hotkey    → pynput Listener (hold + toggle avec timer différé)
├── Thread audio     → sounddevice InputStream 16kHz mono → buffer PCM
└── Thread ASR       → faster-whisper (lazy-loaded, gardé en mémoire)
```

Communication inter-threads : `queue.Queue` + signaux Qt (`pyqtSignal`). Aucun partage d'état direct.

---

## Structure des fichiers

```
D:\Project-002\
├── main.py                     # Entry point : DI, lockfile, orchestration
├── requirements.txt
├── pytest.ini
├── suivi.md                    # ce fichier
├── app/
│   ├── engine/
│   │   ├── paths.py            # DATA_DIR (dev vs packaged)
│   │   ├── state.py            # AppState : IDLE / RECORDING / TRANSCRIBING
│   │   ├── storage.py          # settings.json + history.db (SQLite)
│   │   ├── cleanup.py          # post-traitement texte (none / light / medium)
│   │   ├── injector.py         # clipboard + Ctrl+V, fallback keyboard.type
│   │   ├── audio.py            # sounddevice, RMS queue
│   │   ├── transcription.py    # faster-whisper, cancel event, glossaire
│   │   ├── hotkeys.py          # hold + toggle avec timer différé (350 ms)
│   │   └── autostart.py        # registre Windows
│   └── ui/
│       ├── theme.py            # QSS + constantes couleurs gold
│       ├── main_window.py      # fenêtre principale frameless (bento home, onglets)
│       ├── overlay.py          # indicateur d'enregistrement (bottom-center, or)
│       ├── tray.py             # icône tray + menu contextuel
│       ├── settings.py         # réglages (général, hotkeys, modèle, nettoyage, glossaire)
│       └── history.py          # historique anti-chrono, copier/supprimer
├── tests/                      # tests unitaires (pytest)
├── assets/
│   ├── logo.png                # 256×256 PNG
│   └── logo.ico                # ICO multi-résolution (16/32/48/256)
└── data/                       # créé au 1er lancement (gitignored)
    ├── settings.json
    ├── history.db
    ├── whisperflow.log
    └── whisperflow.lock
```

---

## Machine d'états

```
IDLE ──(hotkey)──► RECORDING ──(stop)──► TRANSCRIBING ──(done)──► IDLE
                       │                       │
                   (Escape/cancel)         (Escape/cancel)
                       └───────────────────────► IDLE
```

Toute transition non listée lève `ValueError`. Implémenté dans `app/engine/state.py`.

---

## Hotkeys — logique clé

Deux raccourcis configurables indépendamment dans les réglages.

| Mode                      | Raccourci défaut     | Comportement                                         |
| ------------------------- | -------------------- | ---------------------------------------------------- |
| **Hold** (push-to-talk)   | `Ctrl + Alt`         | Maintenir pour enregistrer, relâcher pour transcrire |
| **Toggle** (mains libres) | `Ctrl + Alt + Space` | Appuyer pour démarrer, réappuyer pour transcrire     |

**Cas superset** (toggle ⊃ hold, ex. Ctrl+Alt vs Ctrl+Alt+Space) :  
Un timer différé de 350 ms est lancé dès que les touches hold sont pressées. Si Space arrive dans ce délai → mode toggle. Sinon → mode hold. Une fois un mode actif, l'autre est ignoré (`_hold_active` / `_toggle_active` mutuellement exclusifs).

`Escape` annule immédiatement l'enregistrement ou la transcription en cours, sans injection.

---

## Pipeline complet (happy path)

```
1. Hotkey → state.transition(RECORDING)
2. sounddevice stream → chunks PCM accumulés en RAM
3. Overlay visible (barres RMS animées, palette or)
4. Hotkey relâchée (hold) ou re-pressée (toggle) → state.transition(TRANSCRIBING)
   └── si durée < 300 ms → discard silencieux → IDLE
5. np.concatenate(chunks) → faster-whisper.transcribe()
   └── si Escape pendant transcription → cancel event → IDLE, pas d'injection
6. cleanup(texte) selon niveau configuré
7. inject(texte) → clipboard + Ctrl+V, restauration clipboard, fallback keyboard.type
8. storage.save(entrée) → history.db
9. state.transition(IDLE) → overlay masqué
```

---

## Paramètres configurables (settings.json)

| Clé              | Défaut                   | Description                                |
| ---------------- | ------------------------ | ------------------------------------------ |
| `language`       | `"fr"`                   | Langue Whisper                             |
| `model`          | `"small"`                | Modèle faster-whisper                      |
| `compute_device` | `"cpu"`                  | `"cpu"` ou `"cuda"`                        |
| `preload_model`  | `false`                  | Charger le modèle au démarrage             |
| `hotkey_hold`    | `"<ctrl>+<alt>"`         | Raccourci mode hold                        |
| `hotkey_toggle`  | `"<ctrl>+<alt>+<space>"` | Raccourci mode toggle                      |
| `cleanup_level`  | `"light"`                | `"none"` / `"light"` / `"medium"`          |
| `filler_words`   | `["euh", "hum", ...]`    | Mots parasites supprimés                   |
| `glossary`       | `[]`                     | Mots passés en `initial_prompt` à Whisper  |
| `autostart`      | `false`                  | Démarrage automatique Windows              |
| `audio_device`   | `null`                   | Périphérique audio (null = défaut système) |

---

## Points techniques notables

### Fenêtre principale (`main_window.py`)

Fenêtre frameless (`Qt.FramelessWindowHint`), fond opaque sombre (`_USE_ACRYLIC = False` — la transparence DWM causait du lag au drag). Déplacement via `nativeEvent` → `WM_NCHITTEST` → `HTCAPTION` sur la barre de titre. Interface en 4 onglets : **Accueil** (bento : bienvenue + activité + tuiles navigation), **Historique**, **Réglages**, Performances (placeholder).

### Overlay (`overlay.py`)

Fenêtre `Tool | FramelessWindowHint | WindowStaysOnTopHint`, positionnée en bas-centre. Palette entièrement or (`#E8C96A` / `#C9A84C`). Trois états visuels : point clignotant (IDLE caché), barres RMS (RECORDING), arc spinner (TRANSCRIBING).

### Injection texte (`injector.py`)

Clipboard → Ctrl+V → restauration clipboard après 100 ms. Fallback `keyboard.type()` si pyperclip échoue.

### Modèle Whisper

Chargé lazily au premier usage, gardé en RAM pour toute la session. Premier lancement : téléchargement ~460 MB (modèle `small`), dialog de progression affiché.

### Lockfile

PID ASCII dans `data/whisperflow.lock`. Vérifié via `psutil.pid_exists()` au démarrage. Supprimé à l'arrêt via `atexit`.

---

## Prochaines étapes possibles (post-v1)

- Packaging PyInstaller (`.exe` standalone, sans Python requis)
- Onglet Performances avec graphiques de sessions
- Recherche dans l'historique
- Support GPU (CUDA) pour transcription plus rapide
- Tests d'intégration end-to-end

---

## Commandes utiles

```bash
# Lancer l'app (avec console pour debug)
python main.py

# Lancer sans console (mode production)
pythonw main.py

# Tests
pytest tests/ -v --tb=short

# Tuer + relancer proprement (PowerShell)
Stop-Process -Name python,pythonw -Force -EA SilentlyContinue
Start-Sleep 1
Remove-Item data\whisperflow.lock, data\whisperflow.show -EA SilentlyContinue
pythonw main.py
```
