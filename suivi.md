# WhisperFlow — Suivi de projet

> Document de passation destiné à un agent LLM prenant le relais.  
> Dernière mise à jour : 2026-03-14 — **v1.2 — Onglet Performances complet avec stats live GPU/CPU/RAM**

---

## Vision

Application desktop Windows de dictée vocale locale. L'utilisateur parle, le texte est transcrit et injecté dans le champ actif — sans cloud, sans LLM, sans écoute permanente.

**Lancement :** `pythonw main.py` (sans console) ou `python main.py` (debug)

---

## État global

| Composant                                         | État                                                      |
| ------------------------------------------------- | --------------------------------------------------------- |
| Engine (audio, transcription, injection, hotkeys) | ✅ stable                                                 |
| Tests unitaires                                   | ✅ 100 % passants                                         |
| Onglet **Accueil** (bento glassmorphism)          | ✅ **terminé et validé**                                  |
| Onglet **Historique** (liste complète)            | ✅ fonctionnel (UI basique, pas encore redesignée)        |
| Onglet **Réglages**                               | ⏳ fonctionnel mais UI non redesignée — wireframe à venir |
| Onglet **Performances**                           | ✅ **terminé et validé** — stats live CPU/RAM/GPU/VRAM    |
| Assets (`logo00.png`, `icone00.ico`)              | ✅ intégrés partout                                       |
| Raccourci bureau                                  | ✅ `WhisperFlow.lnk` avec `icone00.ico`                   |

---

## Écran d'accueil — VALIDÉ ✅

L'écran d'accueil est **exactement conforme** à la vision finale. Aucune modification requise.

### Layout bento 3 colonnes

```
┌──────────────────────────────────────────────────────────┐
│  [–] [×]           🔱 (logo centré)                      │  ← TitleBar 62px
├──────────────────────────────────────────────────────────┤
│             ┌─────────────────────────────┐              │
│             │  SAMEDI 14 MARS 2026        │              │
│             │  19:05                      │  (horloge    │
│             │  Welcome back.              │   live 1s)   │
│             │  Jimmy                      │              │
│ ┌─────────┐ │  ┌──────┐ ┌──────┐ ┌─────┐│ ┌──────────┐ │
│ │ ⚙ Gear  │ │  │ 5.2K │ │ 150  │ │  3  ││ │ Gauge    │ │
│ │         │ │  │ MOTS │ │ WPM  │ │JOURS││ │          │ │
│ │Réglages │ └─────────────────────────────┘ │Perf.     │ │
│ │         │ ┌─────────────────────────────┐ │          │ │
│ │Modèles, │ │ Historique                  │ │CPU·RAM·  │ │
│ │raccour- │ │  18:03  Et bah écoute…      │ │Threads   │ │
│ │cis, opt.│ │  18:00  Ok, très beau…      │ │          │ │
│ │         │ │  17:55  Et bah écoute…      │ │          │ │
│ │         │ │  …                          │ │          │ │
│ │         │ │  Voir tout →                │ │          │ │
└─┴─────────┴─┴─────────────────────────────┴─┴──────────┴─┘
```

### Détails techniques de l'accueil

- **Fenêtre** : frameless, `WA_TranslucentBackground=True`, `paintEvent` clip arrondi 16px, bordure or `QColor(201,168,76,200)` 1.8px
- **Fond** : `background00.png` cover-fit + vignette `rgba(6,5,3,80)` + blur scale-down/up (PyQt6 6.7.1 — `stackBlur` absent des bindings Python)
- **GlassCard** : blur régional partagé via `_bg_pixmap_cache`, tint warm, même bordure or
- **TitleBar** : hauteur 62px, logo centré par compensation `addSpacing(60)` côté gauche, boutons `–`/`×` or `#C9A84C` 28px à droite
- **Icônes nav** : `_GearIcon(52)` (engrenage QPainter 8 dents) et `_GaugeIcon(52)` (compteur QPainter arc+aiguille) — même palette or, même taille
- **Horloge** : `QTimer` 1 s, date en français via `QLocale`
- **Stats** : 3 tuiles dorées (mots / WPM / jours), hardcodées pour l'instant
- **Mini-historique** : jusqu'à 15 entrées depuis `storage.list()`, `QListWidget` stretch=1, lien "Voir tout →"

---

## Assets

| Fichier                   | Rôle                                                          |
| ------------------------- | ------------------------------------------------------------- |
| `assets/background00.png` | Fond fenêtre principale                                       |
| `assets/logo00.png`       | Logo barre de titre + tray + icône Qt                         |
| `assets/icone00.png`      | Source PNG de l'icône app                                     |
| `assets/icone00.ico`      | ICO multi-résolution (16/32/48/64/128/256) — raccourci bureau |

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
│       ├── theme.py            # QSS global + constantes couleurs
│       ├── main_window.py      # fenêtre principale — glassmorphism, bento, 4 onglets
│       ├── overlay.py          # indicateur d'enregistrement (bottom-center, or)
│       ├── tray.py             # icône tray + menu contextuel
│       ├── settings.py         # SettingsWidget (UI basique, à redesigner)
│       └── history.py          # HistoryWidget (UI basique, à redesigner)
├── tests/                      # tests unitaires (pytest)
├── assets/
│   ├── background00.png        # fond glassmorphism
│   ├── logo00.png              # logo app
│   ├── icone00.png             # source icône
│   └── icone00.ico             # icône bureau multi-résolution
└── data/                       # créé au 1er lancement (gitignored)
    ├── settings.json
    ├── history.db
    ├── whisperflow.log
    └── whisperflow.lock
```

---

## Onglet Performances — VALIDÉ ✅

### Layout (4 GlassCards empilées verticalement)

```
┌─────────────────────────────────────────────────────┐
│  PROFIL MATÉRIEL           [Ré-analyser]            │
│  [CPU : Intel Core i7-...]  [16 GB RAM]  [RTX 5070] │
│  ┌─ Recommandation modèle ────────────────────────┐ │
│  │  🏅 medium                                      │ │
│  │  ⚡ GPU (cuda)                                  │ │
│  │  Raison...                 [▶ Appliquer]        │ │
│  └─────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────┤
│  CPU & RAM                                          │
│  [CPU APP] [CPU SYS] [RAM APP] [RAM SYS]            │
├─────────────────────────────────────────────────────┤
│  GPU & VRAM  (masquée si pas de GPU CUDA)           │
│  [GPU APP] [GPU SYS] [VRAM APP] [VRAM SYS]         │
├─────────────────────────────────────────────────────┤
│  Modèle : small · PID : 12345 · RAM totale : 245 MB │
└─────────────────────────────────────────────────────┘
```

### Classes clés dans `main_window.py`

| Classe / Fonction              | Rôle                                                                         |
| ------------------------------ | ---------------------------------------------------------------------------- |
| `_get_nvml_handle()`           | Init lazy `pynvml`, retourne handle GPU-0 ou `None`                          |
| `_hw_detect()`                 | Détecte CPU (winreg), RAM (psutil), GPU (wmic + pynvml)                      |
| `_hw_recommend()`              | Retourne `rec_model`, `rec_device`, `reason` selon profil                    |
| `_HoverTip`                    | Singleton popup glassmorphism, opaque `rgb(22,17,12)`                        |
| `_HintIcon`                    | Wrapper autour d'une icône tuile — `enterEvent` → popup, `leaveEvent` → hide |
| `_StatTile`                    | Tuile métrique : icône QPainter + valeur dorée + label + hint optionnel      |
| `_TileIcon` (+ 8 sous-classes) | Icônes QPainter 28×28, palette or/blanc — une par tuile                      |
| `_refresh_perf()`              | QTimer 2 s — met à jour les 8 tuiles via psutil + pynvml                     |
| `_refresh_hw_card()`           | Affiche/masque `_perf_gpu_card` selon `profile["cuda_count"]`                |
| `_apply_hw_recommendation()`   | Écrit `model` + `compute_device` dans settings et appelle `sync_from`        |

### Tuiles et icônes

| Tuile    | Icône                                 | Source donnée                            |
| -------- | ------------------------------------- | ---------------------------------------- |
| CPU APP  | `_CpuAppIcon` — chip + flèche bas     | `psutil.Process.cpu_percent()`           |
| CPU SYS  | `_CpuSysIcon` — chip + vague activité | `psutil.cpu_percent()`                   |
| RAM APP  | `_RamAppIcon` — barrette + barre fill | `psutil.Process.memory_info().rss`       |
| RAM SYS  | `_RamSysIcon` — 2 barrettes empilées  | `psutil.virtual_memory().used`           |
| GPU APP  | `_GpuAppIcon` — GPU + flèche bas      | `nvmlDeviceGetProcessUtilization()`      |
| GPU SYS  | `_GpuSysIcon` — GPU + barres          | `nvmlDeviceGetUtilizationRates()`        |
| VRAM APP | `_VramAppIcon` — éclair dans cadre    | `nvmlDeviceGetComputeRunningProcesses()` |
| VRAM SYS | `_VramSysIcon` — éclair + rayons      | `nvmlDeviceGetMemoryInfo()`              |

### Dépendances ajoutées

- `nvidia-ml-py` ajouté à `requirements.txt` et installé (interface Python pour pynvml)
- GPU testé et validé : NVIDIA GeForce RTX 5070

### Tooltip popup (hover sur icône)

- `_HintIcon` wrapping l'icône QPainter de chaque tuile
- `enterEvent` → `_HoverTip.instance().show_for(widget, texte)`
- `leaveEvent` → `_HoverTip.instance().hide()`
- Popup : fenêtre `Tool|Frameless|StaysOnTop`, fond opaque `rgb(22,17,12)`, bordure or, 220px largeur

---

## Prochaines étapes — Redesign des onglets intérieurs

L'utilisateur va fournir des **wireframes dessinés** pour les onglets suivants. Ces onglets sont actuellement fonctionnels mais avec une UI basique qui sera remplacée par le même style glassmorphism que l'accueil.

### Onglets à redesigner (dans l'ordre à définir)

| Onglet               | Contenu actuel                                                                                 | À venir                                                    |
| -------------------- | ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| ~~**Performances**~~ | ✅ Redesign terminé                                                                            | —                                                          |
| **Réglages**         | SettingsWidget scroll : langue, modèle, périphérique, hotkeys, nettoyage, glossaire, autostart | Wireframe utilisateur → redesign glassmorphism             |
| **Historique**       | HistoryWidget : liste anti-chrono, copier/supprimer, recherche                                 | Wireframe utilisateur → redesign glassmorphism si souhaité |

### Workflow convenu

1. Utilisateur envoie wireframe/ébauche dessiné pour un onglet
2. L'agent implémente le layout dans `main_window.py` et/ou les widgets dédiés
3. Validation screenshot → ajustements

---

## Machine d'états

```
IDLE ──(hotkey)──► RECORDING ──(stop)──► TRANSCRIBING ──(done)──► IDLE
                       │                       │
                   (Escape/cancel)         (Escape/cancel)
                       └───────────────────────► IDLE
```

---

## Hotkeys — logique clé

| Mode                      | Raccourci défaut     | Comportement                                         |
| ------------------------- | -------------------- | ---------------------------------------------------- |
| **Hold** (push-to-talk)   | `Ctrl + Alt`         | Maintenir pour enregistrer, relâcher pour transcrire |
| **Toggle** (mains libres) | `Ctrl + Alt + Space` | Appuyer pour démarrer, réappuyer pour transcrire     |

**Cas superset** (toggle ⊃ hold) : timer différé 350 ms. Si Space arrive dans ce délai → toggle. Sinon → hold. `Escape` annule immédiatement.

---

## Pipeline complet (happy path)

```
1. Hotkey → state.transition(RECORDING)
2. sounddevice stream → chunks PCM accumulés en RAM
3. Overlay visible (barres RMS animées, palette or)
4. Hotkey relâchée/re-pressée → state.transition(TRANSCRIBING)
   └── durée < 300 ms → discard silencieux → IDLE
5. np.concatenate(chunks) → faster-whisper.transcribe()
   └── Escape → cancel event → IDLE, pas d'injection
6. cleanup(texte) selon niveau configuré
7. inject(texte) → clipboard + Ctrl+V → restauration clipboard → fallback keyboard.type
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
| `filler_words`   | `["euh", "hum", …]`      | Mots parasites supprimés                   |
| `glossary`       | `[]`                     | Mots passés en `initial_prompt` à Whisper  |
| `autostart`      | `false`                  | Démarrage automatique Windows              |
| `audio_device`   | `null`                   | Périphérique audio (null = défaut système) |

---

## Points techniques notables

### Fenêtre principale (`main_window.py`)

- Frameless + `WA_TranslucentBackground=True`
- `_USE_ACRYLIC = False` (DWM causait lag au drag) — transparence gérée uniquement par `paintEvent`
- Déplacement via `nativeEvent` → `WM_NCHITTEST` → `HTCAPTION` (zone <= 63px du haut)
- Fond : `background00.png` cover-fit + vignette + blur régional partagé (`_bg_pixmap_cache`)
- Icônes peintes : `_GaugeIcon` (speedometer) + `_GearIcon` (engrenage) — QPainter, palette or

### Overlay (`overlay.py`)

Fenêtre `Tool | FramelessWindowHint | WindowStaysOnTopHint`, bas-centre. Palette or. 3 états : point clignotant (IDLE caché) / barres RMS (RECORDING) / arc spinner (TRANSCRIBING).

### Injection texte (`injector.py`)

Clipboard → Ctrl+V → restauration clipboard 100 ms. Fallback `keyboard.type()`.

### Modèle Whisper

Lazy-loaded au premier usage, gardé en RAM. Premier lancement : ~460 MB téléchargés (modèle `small`), dialog de progression.

### Lockfile

PID ASCII dans `data/whisperflow.lock`. `psutil.pid_exists()` au démarrage. Supprimé via `atexit`.

---

## Commandes utiles

```bash
# Lancer (debug)
python main.py

# Lancer (production, sans console)
pythonw main.py

# Tests
pytest tests/ -v --tb=short

# Tuer + relancer proprement (PowerShell)
Stop-Process -Name python,pythonw -Force -EA SilentlyContinue
Start-Sleep 1
Remove-Item data\whisperflow.lock, data\whisperflow.show -EA SilentlyContinue
pythonw main.py
```

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
