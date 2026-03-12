# WhisperFlow — Suivi de projet

> Document de passation destiné à un agent LLM prenant le relais.
> Dernière mise à jour : 2026-03-12

---

## Vision

Application desktop Windows de dictée vocale locale. L'utilisateur parle, le texte est transcrit et injecté dans le champ actif — sans cloud, sans LLM, sans écoute permanente.

**Lancement :** `python main.py`

---

## État actuel : MVP fonctionnel, en attente de smoke test manuel

- [x] Tous les composants implementés (engine + UI)
- [x] 72 tests, 100% passants (`pytest tests/ -v`)
- [x] Branche `feat/implementation` mergée sur `main`
- [ ] **Smoke test manuel** — à faire (voir section ci-dessous)
- [ ] Packaging PyInstaller — non prévu dans le MVP, à décider ensuite

---

## Architecture

```
Process unique
├── Thread Qt main   → overlay, tray, settings, history
├── Thread hotkey    → pynput GlobalHotKeys listener
├── Thread audio     → sounddevice InputStream → buffer PCM
└── Thread ASR       → faster-whisper (lazy-loaded, gardé en mémoire)
```

Communication inter-threads : `queue.Queue` + signaux Qt (`pyqtSignal`). Pas de partage d'état direct.

---

## Structure des fichiers

```
D:\Project-002\
├── main.py                        # Entry point : DI, lockfile, pipeline
├── requirements.txt
├── pytest.ini
├── app/
│   ├── engine/
│   │   ├── paths.py               # DATA_DIR (dev vs packaged)
│   │   ├── state.py               # AppState + machine d'états Qt
│   │   ├── storage.py             # settings.json + history.db (SQLite)
│   │   ├── cleanup.py             # post-traitement texte (3 niveaux)
│   │   ├── injector.py            # clipboard + Ctrl+V, fallback keyboard.type
│   │   ├── audio.py               # sounddevice 16kHz mono, RMS queue
│   │   ├── transcription.py       # faster-whisper wrapper, cancel, glossaire
│   │   ├── hotkeys.py             # GlobalHotKeys hold/toggle, détection conflit
│   │   └── autostart.py           # registre Windows HKCU\...\Run
│   └── ui/
│       ├── overlay.py             # fenêtre frameless RMS + transcribing
│       ├── tray.py                # icône tray + menu contextuel
│       ├── settings.py            # 5 sections : général, hotkeys, modèle, nettoyage, glossaire
│       └── history.py             # liste anti-chrono, copier/supprimer
├── tests/                         # 72 tests unitaires
├── data/                          # créé au 1er lancement (gitignored)
│   ├── settings.json
│   ├── history.db
│   ├── whisperflow.log
│   └── whisperflow.lock
├── assets/
│   └── icon.png                   # ⚠ À créer — l'app démarre sans, mais le tray est vide
└── docs/
    └── superpowers/
        ├── specs/2026-03-12-whisperflow-local-design.md   # spec complète
        └── plans/2026-03-12-whisperflow-local.md          # plan d'implémentation
```

---

## Machine d'états

```
IDLE ──(hotkey)──► RECORDING ──(stop)──► TRANSCRIBING ──(done)──► IDLE
                       │                      │
                    (Escape/error)         (Escape/toggle/error)
                       └──────────────────────► IDLE
```

Toute transition non listée lève `ValueError`. Implémenté dans `app/engine/state.py`.

---

## Pipeline complet (happy path)

```
1. Hotkey → state.transition(RECORDING)
2. sounddevice stream → chunks PCM accumulés en RAM
3. Overlay visible + visualiseur RMS ~30fps
4. Hotkey relâchée (hold) ou re-pressée (toggle) → state.transition(TRANSCRIBING)
   └── si durée < 300ms → discard silencieux → IDLE
5. np.concatenate(chunks) → faster-whisper.transcribe()
   └── si Escape pendant transcription → cancel event → IDLE, pas d'injection
6. cleanup(texte) selon niveau configuré
7. inject(texte) → clipboard + Ctrl+V, restauration clipboard, fallback keyboard.type
8. storage.save(entrée) → history.db
9. state.transition(IDLE) → overlay masqué
```

---

## Paramètres configurables (settings.json)

| Clé | Défaut | Description |
|-----|--------|-------------|
| `language` | `"fr"` | Langue Whisper |
| `model` | `"small"` | Modèle faster-whisper |
| `preload_model` | `false` | Charger le modèle au démarrage |
| `hotkey_hold` | `"<ctrl>+<shift>+<space>"` | Hotkey mode hold |
| `hotkey_toggle` | `"<ctrl>+<shift>+d"` | Hotkey mode toggle |
| `cleanup_level` | `"light"` | `"none"` / `"light"` / `"medium"` |
| `filler_words` | `["euh", "hum", ...]` | Mots parasites supprimés |
| `glossary` | `[]` | Mots passés en `initial_prompt` à Whisper |
| `autostart` | `false` | Clé registre Windows au démarrage |

---

## Smoke test à faire

Le smoke test n'a pas encore été réalisé. Voici la procédure :

```bash
# 1. Depuis D:\Project-002 avec l'environnement Python activé
python main.py
```

**Vérifications à effectuer :**

1. **Démarrage** — L'icône WhisperFlow apparaît dans le tray (grise)
2. **Hotkey hold** — `Ctrl+Shift+Space` → overlay apparaît, icône rouge, barres RMS animées
3. **Relâche** — Overlay passe en "Transcription…", icône orange, puis disparaît
4. **Injection** — Le texte dicté s'insère dans le champ actif (tester dans Notepad ou un navigateur)
5. **Escape** — Presser Escape pendant l'enregistrement ou la transcription → retour IDLE sans injection
6. **Réglages** — Clic droit tray → Réglages → modifier une option → sauvegarder
7. **Historique** — Clic droit tray → Historique → vérifier les entrées, copier, supprimer
8. **Durée courte** — Appuyer et relâcher immédiatement la hotkey → pas de transcription (< 300ms)
9. **Instance double** — Lancer `python main.py` une 2e fois → notification ballon "déjà en cours", exit

**Points de vigilance connus :**

- `assets/icon.png` n'existe pas encore — à créer (16×16 ou 32×32 PNG) pour éviter un tray vide
- Le modèle Whisper `small` se télécharge (~460 MB) au premier appel → un dialog de progression s'affiche
- L'injection via clipboard peut rater dans des applis très lentes (Electron lourd) — comportement attendu et documenté

---

## Points techniques notables

### Injection texte (`injector.py`)
Stratégie : copie dans clipboard → Ctrl+V → restauration clipboard après 100ms. Si pyperclip échoue (exception), fallback `keyboard.type()` caractère par caractère.

### Annulation pendant TRANSCRIBING
Un `threading.Event` est passé au thread ASR. Si Escape ou le toggle hotkey est pressé pendant `transcribe()`, l'event est activé. Le thread ASR vérifie après `transcribe()` et abandonne le résultat.

### Modèle Whisper
Chargé lazily au premier usage, gardé en RAM pour toute la session. Si le modèle n'est pas en cache (`~/.cache/huggingface/`), un dialog bloquant avec barre de progression s'affiche.

### Hotkey listener
Recréé à chaque changement de réglages. La détection de conflit est réalisée au démarrage du listener (si pynput lève une exception) → badge `⚠ Conflit détecté` dans les réglages.

### Lockfile
Format : PID ASCII dans `data/whisperflow.lock`. Vérifié via `psutil.pid_exists()` au démarrage. Supprimé à l'arrêt via `atexit`.

---

## Prochaines étapes possibles (hors MVP)

- Packaging PyInstaller (`.exe` standalone)
- Icône tray animée pendant la transcription
- Recherche dans l'historique
- Support multi-langues dans l'UI (actuellement tout en français)
- Tests d'intégration end-to-end (avec sounddevice mocké et Whisper mocké)

---

## Commandes utiles

```bash
# Lancer l'app
python main.py

# Tests
pytest tests/ -v --tb=short

# Tests d'un module spécifique
pytest tests/test_state.py -v

# Voir les données
ls data/
```

---

## Références

- Spec complète : `docs/superpowers/specs/2026-03-12-whisperflow-local-design.md`
- Plan d'implémentation : `docs/superpowers/plans/2026-03-12-whisperflow-local.md`
- Stack : Python 3.11+, PyQt6, faster-whisper, sounddevice, pynput, pyperclip, keyboard, psutil
