# WhisperFlow — Suivi de projet

> Document de passation destiné à un agent LLM prenant le relais.  
> Dernière mise à jour : 2026-03-15 — **v1.9 — Fix hotkey stuck (auto-guérison + reset()) + 78/78 tests**

---

## Vision

Application desktop Windows de dictée vocale locale. L'utilisateur parle, le texte est transcrit et injecté dans le champ actif — sans cloud, sans LLM, sans écoute permanente.

**Lancement :** `pythonw main.py` (sans console) ou `python main.py` (debug)

---

## État global

| Composant                                         | État                                                                          |
| ------------------------------------------------- | ----------------------------------------------------------------------------- |
| Engine (audio, transcription, injection, hotkeys) | ✅ stable                                                                     |
| Tests unitaires                                   | ✅ 100 % passants                                                             |
| Onglet **Accueil** (bento glassmorphism)          | ✅ **terminé et validé**                                                      |
| Onglet **Historique** (liste complète)            | ✅ **terminé et validé** — glassmorphism, recherche, icône QPainter, compteur |
| Onglet **Réglages**                               | ✅ **terminé et validé** — glassmorphism 5 sections, toggles, icônes QPainter |
| Onglet **Performances**                           | ✅ **terminé et validé** — stats live CPU/RAM/GPU/VRAM                        |
| Assets (`logo00.png`, `icone00.ico`)              | ✅ intégrés partout                                                           |
| Raccourci bureau                                  | ✅ `WhisperFlow.lnk` avec `icone00.ico`                                       |

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
- **Stats** : 3 tuiles dorées (mots / WPM / jours), **live depuis `history.db`** via `_compute_stats()`
- **Mini-historique** : jusqu'à 15 entrées depuis `storage.list()`, `QListWidget` stretch=1, titre "Historique" (QPushButton cliquable) et lien "Voir tout →" naviguent tous deux vers l'onglet Historique (index 1)

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
│       ├── settings.py         # SettingsWidget — glassmorphism 5 sections, GlassCard, ToggleSwitch, icônes QPainter
│       ├── history.py          # HistoryWidget — glassmorphism, GlassCard, recherche filtrée, icône QPainter
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

## Onglet Réglages — VALIDÉ ✅

### Layout (1 GlassCard scrollable + footer fixe)

```
┌─────────────────────────────────────────────────────┐
│  🎙 DICTÉE                                          │
│     Microphone : [combo]       Langue : [combo]     │
├─────────────────────────────────────────────────────┤
│  🔑 RACCOURCIS CLAVIER                              │
│     Hold    : [HotkeyCapture]                       │
│     Toggle  : [HotkeyCapture]                       │
│     (label conflit)                                 │
├─────────────────────────────────────────────────────┤
│  🧠 MODÈLE ASR                                      │
│     Modèle : [combo]   Accélération : [combo]       │
│     Précharger au démarrage : [ToggleSwitch]         │
├─────────────────────────────────────────────────────┤
│  🖌 NETTOYAGE TEXTE                                 │
│     Niveau : [combo]   Mots parasites : [edit]      │
│     Glossaire : [TextEdit]                          │
├─────────────────────────────────────────────────────┤
│  ⚙  GÉNÉRAL                                         │
│     Démarrage auto Windows : [ToggleSwitch]         │
├─────────────────────────────────────────────────────┤
│  [Réinitialiser]                     [Enregistrer]  │  ← footer fixe
└─────────────────────────────────────────────────────┘
```

### Éléments clés

| Classe / Objet               | Rôle                                                                                   |
| ---------------------------- | -------------------------------------------------------------------------------------- | ----------------------------------------- |
| `_GlassCard`                 | Carte glassmorphism, blur régional, tint warm, bordure or                              |
| `_ToggleSwitch`              | Pill toggle doré (remplace QCheckBox) — `.isChecked` est une **propriété** (sans `()`) |
| `_IconBase` + 6 sous-classes | Icônes QPainter 28×28 : Mic, Key, Brain, Brush, Globe, Cog                             |
| `HotkeyCapture`              | QPushButton capturant les combinaisons clavier en live                                 |
| `SettingsWidget`             | Widget principal — scroll interne + footer fixe Réinitialiser/Enregistrer              |
| `SettingsWindow`             | QDialog wrapper, `__getattr__` délègue vers `SettingsWidget` (tests)                   |
| `_settings_bg_cache`         | Module-level `QPixmap                                                                  | None`, injecté par `\_rebuild_bg_cache()` |

---

## Onglet Historique — VALIDÉ ✅

### Layout (1 GlassCard pleine page)

```
┌─────────────────────────────────────────────────────┐
│  🕐 HISTORIQUE DES DICTÉES              [N entrées] │
│  ─────────────────────────────────────────────────── │
│  [🔍 Rechercher dans l'historique…               ]  │
│  ─────────────────────────────────────────────────── │
│  2026-03-14 15:42  3s                               │
│  Et bah écoute, j'ai juste à dire que c'était…     │  ← item 2 lignes
│  2026-03-14 15:38  2s                               │
│  Ok, très beau travail...                           │
│  …                                                  │
│  ─────────────────────────────────────────────────── │
│                            [Copier]  [Supprimer]    │
└─────────────────────────────────────────────────────┘
```

### Éléments clés

| Classe / Objet      | Rôle                                                                   |
| ------------------- | ---------------------------------------------------------------------- | ----------------------------------------- |
| `_GlassCard`        | Carte glassmorphism, `_history_bg_cache` pour le blur                  |
| `_HistIcon`         | Icône horloge QPainter 28×28 (aiguilles heure/minute, or + blanc)      |
| `_search_edit`      | QLineEdit glassmorphism, filtre en temps réel sur texte + date         |
| `list_widget`       | QListWidget, items 2 lignes (date+durée / aperçu), scrollbar dorée 6px |
| `copy_btn`          | Copie le texte sélectionné dans le clipboard                           |
| `delete_btn`        | Supprime l'entrée via `on_delete(id)` + rafraîchissement               |
| `HistoryWindow`     | QDialog wrapper, `__getattr__` délègue vers `HistoryWidget` (tests)    |
| `_history_bg_cache` | Module-level `QPixmap                                                  | None`, injecté par `\_rebuild_bg_cache()` |

- Double-clic sur un item = copie immédiate
- Compteur entrées mis à jour en temps réel selon filtre de recherche

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

## Changelog v1.9 (2026-03-15)

### Fix hotkey stuck — auto-guérison

- **Symptôme** : après Ctrl+Alt pendant une transcription, ou après Alt+Tab / Win+D pendant qu'on tenait les touches, l'OS avalait le key-up → `_hold_active` restait `True` → hotkey sourd jusqu'au redémarrage
- **Fix `_on_press`** : si `_hold_active=True` mais state=IDLE → auto-guérison complète (`_pressed` vidé, `_hold_active` remis à False) avant de ré-évaluer la touche
- **Fix nettoyage touches fantômes** : en mode IDLE pur, les touches non-combo qui traînent dans `_pressed` (séquelles d'OS-swallowed key-ups) sont supprimées
- **Nouvelle méthode `HotkeyManager.reset()`** : réinitialise `_hold_active`, `_toggle_active`, `_hold_pending`, `_pressed` — appelée depuis `_cancel()` (timeout 90s, erreur micro, Escape)
- **Tests** : 2 nouveaux tests (`test_self_heal_when_hold_active_stuck_and_state_idle`, `test_reset_clears_hotkey_state`) → **78/78** ✅

---

## Changelog v1.8 (2026-03-15)

### Fonctionnalités ajoutées

- **Export CSV** : bouton "Exporter" dans l'onglet Historique ET dans le tray — exporte l'historique complet en CSV horodaté
- **Icône QPainter export** : emoji "📤" remplacé par une icône dessinée (flèche montante + plateau, palette or `QColor(201,168,76,210)`)
- **Fix `on_export` MainWindow** : `HistoryWidget` dans `_make_history_tab()` ne recevait pas `on_export` → corrigé (param ajouté à `MainWindow.__init__`)
- **Gestion micro déconnecté** : `AudioCapture` accepte `on_error` callback ; si le callback audio reçoit un `status` d'erreur (ou si `PortAudioError` est levé dans `stop()`), `main.py` annule l'enregistrement et notifie l'utilisateur via la bulle système
- **Timeout transcription 90s** : `_run_transcription` lance un watchdog `_timeout_check()` ; si `done.wait(90.0)` expire, appel `transcriber.cancel()` + reset état + notification

### Améliorations qualité

- **Glossaire étendu** (8 nouveaux termes analysés depuis CSV exporté) : `l'IA`, `overlay`, `keybind`, `keybinds`, `drag and drop`, `MVP`, `preload`, `glassmorphism`, `bento`, `dark mode`, `light mode`
- **`initial_prompt`** amélioré : `"Développeur français utilisant l'IA quotidiennement, dictée vocale professionnelle. Termes techniques: {terms}."`

### Nettoyage

- **`.gitignore`** : ajout de `suivi.md` et `*.spec`
- **Assets supprimés** : `logo.ico` et `logo.png` (non référencés dans le code, remplacés par `icone00.ico` / `logo00.png`)
- **Tests** : 76/76 ✅ (dont `test_audio.py` compatible avec le nouveau param `on_error`)

---

## Points techniques notables

### Fenêtre principale (`main_window.py`)

- Frameless + `WA_TranslucentBackground=True`
- `_USE_ACRYLIC = False` (DWM causait lag au drag) — transparence gérée par `paintEvent`
- Déplacement via `nativeEvent` → `WM_NCHITTEST` → `HTCAPTION` (zone <= 63px du haut)
- Fond : `background00.png` cover-fit + vignette + blur régional (`_bg_pixmap_cache` partagé entre les 3 onglets glassmorphism via `_rebuild_bg_cache()`)
- `_rebuild_bg_cache()` propage le pixmap vers `settings._settings_bg_cache` et `history._history_bg_cache`
- 4 onglets complets : **Accueil** (bento glassmorphism), **Historique** (recherche + liste), **Réglages** (5 sections), **Performances** (stats live)
- Icônes nav : `_GearIcon(52)` + `_GaugeIcon(52)` — QPainter, palette or

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

## Prochains chantiers — v2.0

### 0. Packaging — fichier .exe ← prochain

Whisper ne se « fine-tune » pas sans infrastructure d'entraînement. Ce qu'on peut faire :

| Levier                     | Mécanisme                                                | Impact |
| -------------------------- | -------------------------------------------------------- | ------ |
| **Glossaire**              | Mots en `initial_prompt` → Whisper amorce le vocabulaire | ⭐⭐⭐ |
| **Session de calibration** | Lire 15 phrases imposées, analyser les erreurs système   | ⭐⭐⭐ |
| **Mots parasites**         | Affiner la liste selon usage réel                        | ⭐⭐   |
| **`beam_size`**            | Augmenter (5→10) pour plus de précision (plus lent)      | ⭐⭐   |
| **Modèle `medium`**        | Plus précis, +2× RAM, +2× temps CPU                      | ⭐⭐⭐ |
| **`temperature=0`**        | Désactiver aléatoire → moins d'hallucinations            | ⭐     |

**Workflow de calibration convenu :** l'agent fournit 15 phrases à lire, l'utilisateur les dicte, on compare les transcriptions et on ajuste le glossaire + filler words.

### 1. Packaging — fichier .exe

Outil : **PyInstaller**. Complexité élevée avec faster-whisper (CTranslate2, librairies C++, DLLs).

```bash
pip install pyinstaller
pyinstaller --onedir --windowed --icon=assets/icone00.ico --name=WhisperFlow main.py
```

Points d'attention :

- **Taille** : ~350 MB sans CUDA, ~1.8 GB avec CUDA (torch + CUDA DLLs)
- **Modèle Whisper** : stocké dans `%APPDATA%/HuggingFace/hub/` — NON inclus dans le .exe, téléchargé au premier lancement comme aujourd'hui
- **Assets** : `--add-data "assets;assets"` pour inclure le fond + icônes
- **pynput / sounddevice** : nécessitent `--collect-all pynput` et `--collect-all sounddevice`
- **DLLs CUDA** : `nvidia-cublas-cu12` installé dans le venv. `main.py` précharge `cublas64_12.dll` via `ctypes.CDLL` avant ctranslate2. Pour le packaging .exe, il faudra inclure ces DLLs avec `--add-binary` et adapter le chemin (le `.venv/` n'existera plus)
- Un fichier `.spec` dédié (`whisperflow.spec`) sera nécessaire pour fiabiliser la build
- Distribution recommandée : dossier `dist/WhisperFlow/` (mode `--onedir`) + installateur NSIS ou archive ZIP

### 3. Améliorations identifiées

| Priorité    | Sujet                        | État | Détail                                                                                                                   |
| ----------- | ---------------------------- | ---- | ------------------------------------------------------------------------------------------------------------------------ |
| ~~Haute~~   | Stats accueil réelles        | ✅   | Déjà branchées sur `history.db` via `_compute_stats()` — aucun changement requis                                         |
| ~~Haute~~   | Tests tray (3 échecs)        | ✅   | Fixture corrigée (`on_open=MagicMock()`) — 3/3 passants                                                                  |
| ~~Haute~~   | `preload_model` toggle       | ✅   | `main.py` : `_ensure_loaded()` conditionnel sur le setting                                                               |
| ~~Haute~~   | CUDA ne fonctionne pas       | ✅   | `cublas64_12.dll` absente — `nvidia-cublas-cu12` installé + préchargé via `ctypes.CDLL` dans `main.py` avant ctranslate2 |
| ~~Moyenne~~ | Découpage `main_window.py`   | ✅   | 1 663 → 492 lignes — extrait dans `glass_card.py`, `home_tab.py`, `perf_tab.py`                                          |
| ~~Moyenne~~ | Export historique CSV        | ✅   | Bouton dans onglet Historique + tray + icône QPainter or                                                                 |
| ~~Faible~~  | `_rebuild_bg_cache` débounce | ✅   | `QTimer` singleShot 100 ms dans `resizeEvent`                                                                            |
| ~~Faible~~  | Gestion déconnexion micro    | ✅   | `AudioCapture.on_error` → `_on_audio_error` → notification + cancel automatique                                          |
| ~~Faible~~  | Hotkey intermittent          | ✅   | Auto-guérison dans `_on_press` + `reset()` appelé depuis `_cancel()` — testé en session réelle                           |
