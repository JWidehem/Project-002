# WhisperFlow — Document de maintenance

> Application desktop Windows de dictée vocale locale (sans cloud, sans LLM, sans écoute permanente).
> Usage : perso uniquement — Jimmy.
> Objectif : maintenir l'app stable, pas d'ajout de features sauf demande explicite.
> Dernière mise à jour : 2026-07-22 — **v2.1 — import audio fichier**

---

## Routine de maintenance mensuelle

> **Pour l'agent LLM qui relit ce fichier :** exécute les commandes ci-dessous dans l'ordre,
> analyse les résultats, et signale à Jimmy ce qui nécessite une action.

```powershell
cd "D:\Project-002"

# 1. Audit sécurité — CVE connues dans les packages installés
python -m pip_audit --path .\.venv --desc

# 2. Packages obsolètes — versions disponibles vs installées
.\.venv\Scripts\python.exe -m pip list --outdated

# 3. Tests — vérifier que tout passe toujours
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

**Interprétation attendue :**
- `pip-audit` : si une CVE est trouvée → signaler le package, la CVE et la version corrigée
- `pip list --outdated` : signaler uniquement les packages du `requirements.txt` (ignorer les dépendances transitives)
- `pytest` : si un test échoue → le signaler avec le traceback

**Seuil d'action :** ne revenir sur VS Code que si CVE critique, ou si un package direct du `requirements.txt` a une mise à jour majeure (ex: PyQt6 6.x → 7.x, faster-whisper 1.x → 2.x).

---

## Lancement

```bash
pythonw main.py          # production (sans console)
python main.py           # debug (avec console)
pytest tests/ -v         # tests (87/87)
```

## Environnement

| Elément | Valeur |
|---|---|
| Python | 3.14.3 |
| Venv | .venv\Scripts\pythonw.exe |
| Raccourci bureau | WhisperFlow.lnk -> .venv\Scripts\pythonw.exe "main.py" |
| Lockfile | data\whisperflow.lock (PID) |

---

## Architecture

```
Process unique
+-- Thread Qt main   -> fenetre principale, overlay, tray
+-- Thread hotkey    -> pynput Listener
+-- Thread audio     -> sounddevice 16kHz mono
+-- Thread ASR       -> faster-whisper (lazy-loaded, garde en RAM)
```

Inter-threads : queue.Queue + signaux Qt (pyqtSignal). Zero partage d'etat direct.

## Machine d'états

```
IDLE -> RECORDING -> TRANSCRIBING -> IDLE
           |                |
        (Escape)         (Escape)
           +-----------------> IDLE
```

---

## Logique hotkeys (v2.0)

| Geste | Effet |
|---|---|
| Ctrl+Alt maintenu | Demarre l'enregistrement (hold) |
| Space pendant hold | Verrouille en mains libres (latch) — lacher les touches |
| Space en mode latch | Transcrit |
| Ctrl+Alt relache (sans Space) | Transcrit (push-to-talk classique) |
| Escape | Annule immediatement |

Cles de configuration :
- hotkey_hold = "<ctrl>+<alt>"
- hotkey_toggle = "<ctrl>+<alt>+<space>" -> latch_keys = {space}

Auto-guerison : si _hold_active=True mais etat=IDLE (key-up avale par l'OS), le prochain appui reinitialise tout avant de rereevaluer.

---

## Pipeline dictee

```
1. Hotkey -> RECORDING -> sounddevice accumule PCM
2. Overlay visible : barres RMS or (hold) ou ambre (latch)
3. Arret -> TRANSCRIBING
   -- < 300ms -> discard silencieux
4. faster-whisper.transcribe() — VAD + initial_prompt glossaire
5. clean() : filler words + deduplication + ponctuation
6. inject() : clipboard + Ctrl+V -> restauration clipboard -> fallback keyboard.type
7. history.db -> SQLite (max 500 entrees)
8. IDLE
```

---

## Parametres (data/settings.json)

| Cle | Defaut | Description |
|---|---|---|
| language | "fr" | Langue Whisper |
| model | "small" | Modele faster-whisper |
| compute_device | "cpu" | "cpu" ou "cuda" |
| preload_model | false | Charger le modele au demarrage |
| hotkey_hold | "<ctrl>+<alt>" | Raccourci hold |
| hotkey_toggle | "<ctrl>+<alt>+<space>" | Raccourci latch |
| cleanup_level | "light" | "none" / "light" / "medium" |
| filler_words | ["euh","hum",...] | Mots parasites supprimes |
| glossary | [] | Termes techniques (initial_prompt Whisper) |
| autostart | false | Demarrage auto Windows |
| audio_device | null | Micro (null = defaut systeme) |

---

## UI — Style et organisation

**Style global : glassmorphism**
- Fenetre frameless, WA_TranslucentBackground=True
- Fond : background00.png cover-fit + vignette rgba(6,5,3,80) + blur regional
- GlassCard : blur regional partage via _bg_pixmap_cache, tint warm, bordure or
- Couleur or principale : QColor(201,168,76) — bordure 1.8px, icones QPainter, textes
- TitleBar : 62px, logo centre, boutons -/x or a droite
- Deplacement fenetre : nativeEvent -> WM_NCHITTEST -> HTCAPTION (zone <= 63px du haut)
- _rebuild_bg_cache() propage le pixmap vers settings et history (debounce 100ms resize)

**4 onglets**

| Onglet | Contenu |
|---|---|
| Accueil | Bento 3 colonnes : horloge live, stats mots/WPM/jours, mini-historique (haut) + carte Import Audio (bas) |
| Historique | Liste searchable 2 lignes/entree, copie/suppression/export CSV, compteur live |
| Reglages | 5 sections scrollables + footer fixe : Dictee, Raccourcis, Modele ASR, Nettoyage, General |
| Performances | Stats live CPU/RAM/GPU/VRAM (psutil + pynvml), profil materiel, recommandation modele |

**Classes UI cles a connaitre**

| Classe | Fichier | Detail |
|---|---|---|
| GlassCard | glass_card.py | Carte glassmorphism reutilisable — blur regional |
| _ToggleSwitch | settings.py | Pill toggle dore — .isChecked est une PROPRIETE (sans ()) |
| HotkeyCapture | settings.py | QPushButton capturant les combos clavier en live |
| _HoverTip | main_window.py | Popup glassmorphism singleton (hover tuiles perf) |
| Overlay | overlay.py | or en hold, ambre en latch, spinner en transcription |
| _ImportAudioCard | home_tab.py | Carte bento import fichier audio — browse, transcrire, annuler |
| _TranscriptResultDialog | home_tab.py | Dialog glassmorphism draggable — texte scrollable, copier, enregistrer |

**Icones** : toutes dessinées en QPainter — aucun fichier image externe sauf assets/logo00.png et assets/background00.png.

---

## Stack

| Package | Version | Role |
|---|---|---|
| faster-whisper | 1.1.1 | Transcription locale (CTranslate2) |
| PyQt6 | 6.7.1 | UI glassmorphism |
| sounddevice | 0.5.1 | Capture audio |
| pynput | 1.7.7 | Hotkeys bas niveau |
| pyperclip + keyboard | — | Injection texte |
| psutil + nvidia-ml-py | — | Stats perf UI |
| numpy | >=2.0.0 | Audio DSP (wheel Python 3.14) |

---

## Structure des fichiers

```
main.py                  # Entry point, DI, lockfile, orchestration
app/engine/
  paths.py               # DATA_DIR
  state.py               # AppState IDLE/RECORDING/TRANSCRIBING
  storage.py             # Settings (JSON) + History (SQLite)
  audio.py               # AudioCapture, normalisation RMS
  transcription.py       # Transcriber (faster-whisper, lazy-load, cancel, transcribe_file)
  cleanup.py             # Nettoyage texte 3 niveaux
  injector.py            # clipboard + Ctrl+V
  hotkeys.py             # HotkeyManager — hold + latch
  autostart.py           # Registre Windows demarrage auto
app/ui/
  main_window.py         # Fenetre principale — 4 onglets, _rebuild_bg_cache
  glass_card.py          # GlassCard reutilisable
  home_tab.py            # Onglet Accueil (bento) + _ImportAudioCard + _TranscriptResultDialog
  perf_tab.py            # Onglet Performances (stats live)
  overlay.py             # Indicateur enregistrement (or/ambre/spinner)
  settings.py            # Onglet Reglages
  history.py             # Onglet Historique
  tray.py                # Icone tray + menu
  theme.py               # QSS global
assets/
  background00.png       # Fond glassmorphism
  logo00.png             # Logo barre de titre
  icone00.ico            # Icone bureau multi-resolution
data/                    # Cree au 1er lancement (gitignored)
  settings.json
  history.db
  whisperflow.log
  whisperflow.lock
```

---

## Points techniques a retenir

- **CUDA** : cublas64_12.dll prechargee via ctypes.CDLL avant Qt (ordre critique MKL/Qt)
- **Overlay** : or QColor(201,168,76) en hold, ambre QColor(210,140,60) en latch, spinner en transcription
- **Fond blur** : _bg_pixmap_cache partage entre onglets via _rebuild_bg_cache() (debounce 100ms)
- **Instance unique** : lockfile PID, detection psutil.pid_exists(), signal file pour re-ouvrir
- **Timeout transcription** : watchdog 90s -> annulation automatique
- **Git SID** : apres reset PC -> git config --global --add safe.directory D:/Project-002

---

## Changelog

| Version | Date | Resume |
|---|---|---|
| v2.1 | 2026-07-22 | Import fichier audio (mp3/m4a/aac/wav…) : transcribe_file(), progression live %, _ImportAudioCard, _TranscriptResultDialog, 87/87 tests |
| v2.0 | 2026-04-10 | Logique latch (Space pendant hold = mains libres), indicateur overlay ambre, Python 3.14, numpy>=2.0 |
| v1.9 | 2026-03-15 | Fix hotkey stuck (auto-guerison + reset()), 78/78 tests |
| v1.8 | 2026-03-15 | Export CSV, gestion micro deconnecte, timeout 90s, decoupage main_window.py |
