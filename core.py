# -*- coding: utf-8 -*-
"""
Coeur de l'assistant : config, notes, automatisations, voix (Whisper),
fournisseurs d'IA (Anthropic / OpenAI / Gemini / DeepSeek / Ollama),
analyse du PC et gestion des modèles locaux.
"""

import json
import os
import re
import sys
import threading
import time
import traceback
import unicodedata
import uuid

import numpy as np

import storage
import winext

# Version de l'app — source unique. Doit rester égale au MyAppVersion de
# installer/nova.iss (test_v3 le vérifie) ; les releases GitHub sont taguées
# « v » + cette valeur, et updater.py s'en sert pour détecter une mise à jour.
APP_VERSION = "3.1.26"

APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))


def resource_path(rel):
    """Chemin d'une ressource embarquée (icône, HTML d'onboarding…), qu'on
    tourne en script ou en .exe PyInstaller (`sys._MEIPASS`). Source unique —
    app.py et onboarding.py l'utilisaient chacun en copie identique."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)

DEFAULT_CONFIG = {
    # --- v3 (Speechly-lite) / nova-produit ---
    "ptt_key": "f9",          # push-to-talk : touche MAINTENUE = parle, relâchée = colle
    "mode": "auto",           # mode de reformulation courant (registre modes_registry)
    "custom_vars": [],         # Custom Variables : [{"trigger","value"}], 100 % local
    "profile": "normal",      # profil de puissance : normal | eleve | ultra (power_profiles)
    "seq_memory": True,       # décharge le STT avant le LLM (petites configs)
    "instant_normal": False,  # Style Normal collé par règles pures, sans IA
    "onboarding_done": False, # assistant de bienvenue affiché une seule fois
    "auto_update": True,      # mise à jour silencieuse au lancement (updater.py)
    "dock_ui": "web",         # interface : "web" = dock/fenêtres du site (défaut),
                              # "pill" = pilule tkinter (repli sans WebView2)
    "mode_hotkeys": {},       # raccourci clavier par Style : {mode_id: "ctrl+alt+e"}
    "menu_hotkey": "",        # raccourci qui ouvre le menu des Styles ("" = aucun)
    "settings_hotkey": "",    # combinaison qui ouvre la fenêtre Réglages
    "dock_position": "bottom-center",  # ancrage de la bulle : top/bottom × left/center/right
    "dock_scale": 1.0,        # taille de la bulle : 1.0 normale, 0.85 petite
    "dock_opacity": 1.0,      # opacité de la bulle (0.55 → 1.0)
    "dock_ghost": False,      # invisible au repos : la bulle n'apparaît que
                              # pendant la dictée (Nova vit dans le tray)
    "hotkey": "ctrl+alt+space",
    "note_hotkey": "ctrl+alt+n",
    "dictation_hotkey": "ctrl+alt+d",
    "continuous_listening": False,
    "wake_word": "nova",
    "wake_engine": "whisper",        # whisper (sans clé) | porcupine (clé Picovoice)
    "porcupine_keyword": "jarvis",   # keyword intégré ou 'custom'
    "porcupine_ppn": "",             # chemin .ppn personnalisé
    "porcupine_sensitivity": 0.6,
    "show_bubble": True,             # bulle micro compacte pendant l'écoute continue
    "wake_model": "base",            # modèle Whisper dédié à l'éveil/aperçus : tiny | base | small
    "whisper_model": "small",
    "dictation_live": True,          # la dictée tape le texte pendant qu'on parle
    "dictation_punctuation": True,   # « virgule », « point », « à la ligne » deviennent , . \n
    "pill_pos": None,                # position [x, y] si la pilule a été déplacée
    "bubble_pos": None,              # idem pour la bulle micro
    "language": "fr",
    # Local d'abord (GOAL Partie 4) : reformulation via Ollama local par défaut ;
    # le toggle « Cloud » bascule sur « auto » (fournisseurs cloud si clé + en ligne).
    "provider": "ollama",   # ollama (local) | auto (cloud) | anthropic | … | off
    "providers": {
        "anthropic":  {"api_key": "", "model": "claude-haiku-4-5"},
        "openai":     {"api_key": "", "model": "gpt-4o-mini"},
        "gemini":     {"api_key": "", "model": "gemini-2.5-flash"},
        "deepseek":   {"api_key": "", "model": "deepseek-chat"},
        "groq":       {"api_key": "", "model": "llama-3.3-70b-versatile"},
        "mistral":    {"api_key": "", "model": "mistral-small-latest"},
        "xai":        {"api_key": "", "model": "grok-3-mini"},
        "openrouter": {"api_key": "", "model": "openrouter/auto"},
        "ollama":     {"url": "http://localhost:11434", "model": ""},
    },
    "pill_hide_mode": "timer",   # timer | click | never (disparition de la pilule)
    "relisten_on_fail": True,    # incompris → réécoute directe sans redire « Nova »
    "timer_style": "web",        # web = onglet minuteur visible + alerte vocale | nova = vocal seul
    "continuous_conversation": True,  # après chaque réponse : réécoute pour enchaîner
    "screen_vision": True,       # « regarde mon écran » → capture envoyée à l'IA choisie
    "custom_apps": {},           # « ouvre X » personnalisé : nom vocal → commande/exe/URL
    "ha_url": "",                # Home Assistant (domotique JARVIS) : http://IP:8123
    "ha_entities": {},           # nom vocal → {type: light|switch|sensor, id: entity_id}
    "routines": {},              # « mode X » → liste de cibles (app/dossier/url/musique)
    "music": {"spotify_uri": "", "youtube_url": ""},  # musique attitrée
    "double_clap": "off",        # off | listen | light:<nom> (double applaudissement)
    "iptv": {"source": ""},      # playlist IPTV (M3U/XSPF/PLS, chemin ou URL)
    "obsidian_vault": "",        # coffre Obsidian ('' = dossier ObsidianVault local)
    "mobile_enabled": False,     # accès mobile LAN (opt-in)
    "mobile_port": 8080,
    "mobile_token": "",          # jeton d'appairage optionnel (?k=)
    "city": "",                  # ville par défaut (météo, prompt IA)
    "ia_fallback_on_fail": True, # un mode règle échoue → l'IA tente le rattrapage
    "mic_device_index": None,    # micro choisi (None = défaut Windows)
    "session_timeout": 30,       # s : fenêtre de conversation sans redire « Nova »
    "wake_ack_sound": True,      # bip discret après « Nova » seul
    "clap_threshold": 0.037,     # sensibilité du double applaudissement
    "stt": {
        "cloud_enabled": False,      # Groq Whisper, opt-in uniquement
        "cloud_model": "whisper-large-v3-turbo",
        # --- latence (PC sans GPU surtout) ---
        "live": True,               # transcrire PENDANT la dictée (segments)
        "keep_warm": "auto",        # garder le moteur en RAM entre dictées
        "precision_max": False,     # beam 5 sur CPU (lent) au lieu de beam 1
        "quality_max": False,       # grand moteur multilingue local (~1,5 Go)
    },
    "tts": {
        "enabled": False,            # confirmations à voix haute (opt-in)
        "engine": "sapi",            # sapi (offline) | edge (voix neuronale, en ligne)
        "edge_voice": "fr-FR-DeniseNeural",   # Denise (femme) | Henri (homme)
        "rate": 1, "volume": 100, "voice": "",
    },
    "modes": {
        "message":    {"enabled": True, "delivery": "auto"},  # auto | twilio | clipboard
        "navigation": {"enabled": True, "app": "gmaps"},      # gmaps | waze
        "media":      {"enabled": True},
        "call":       {"enabled": True},
        "emergency":  {"enabled": True, "contact_name": "", "contact_phone": "",
                       "trigger": "urgence"},
    },
    "neural": {"translate_to": ""},  # traduction auto des messages ('' = off)
    "twilio": {"from_number": ""},
    "obd": {"mock": True, "port": "", "coolant_alert_c": 105, "poll_ms": 2000},
    "active_profile": "",
    "close_to_tray": True,
    "max_record_seconds": 12,
    "silence_seconds": 1.2,
    "silence_threshold": 0.01,
}

NOTE_TRIGGERS = ("note que", "prends note", "prend note", "nouvelle note", "note ")

# Langues STT proposées (Whisper est multilingue, ~99 langues au total ; cette
# liste couvre les plus demandées). SOURCE UNIQUE : menu tray ET onboarding la
# consomment tous les deux, jamais de liste dupliquée. « auto » = détection.
LANGUAGES = [
    ("auto", "Auto (détection)"), ("fr", "Français"), ("en", "English"),
    ("es", "Español"), ("de", "Deutsch"), ("it", "Italiano"),
    ("pt", "Português"), ("nl", "Nederlands"), ("pl", "Polski"),
    ("ru", "Русский"), ("ar", "العربية"), ("tr", "Türkçe"),
    ("hi", "हिन्दी"), ("zh", "中文"), ("ja", "日本語"), ("ko", "한국어"),
]

_lock = threading.RLock()   # ré-entrant : save_config le tient sur toute la
#                             lecture-modification-écriture de CFG PUIS appelle
#                             _save (qui le reprend) — RMW atomique sans
#                             auto-blocage, et _save reste neutralisable en test.


# ------------------------------------------------------------------ util ----

def _path(name):
    return os.path.join(APP_DIR, name)


def _load(name, default):
    try:
        with open(_path(name), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(name, data):
    with _lock:
        with open(_path(name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def _merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def normalize(text):
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    # réduit les espaces multiples (« mets  la  musique » du STT) et les bords :
    # sinon une commande à double espace ne matcherait aucune règle
    return re.sub(r"\s+", " ", text).strip()


_LOG_MAX_BYTES = 512 * 1024   # rotation simple : nova.log → nova.log.1 (2 fichiers max)


def log_err(context, err):
    """Journal d'erreurs (nova.log à côté de l'exe — installation par
    utilisateur, donc inscriptible) : les pannes silencieuses de la dictée ou
    du chargement des modèles deviennent visibles. Si `err` est une exception,
    sa trace complète est jointe (indispensable pour diagnostiquer à distance
    la machine d'un client)."""
    try:
        p = _path("nova.log")
        try:
            if os.path.getsize(p) > _LOG_MAX_BYTES:
                os.replace(p, _path("nova.log.1"))
        except OSError:
            pass                       # fichier absent : rien à faire pivoter
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {context}: {err}\n"
        if isinstance(err, BaseException) and err.__traceback__ is not None:
            tb = "".join(traceback.format_exception(type(err), err,
                                                    err.__traceback__))
            line += "    " + tb.replace("\n", "\n    ").rstrip() + "\n"
        with open(p, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def install_crash_logging():
    """Boîte noire — en .exe fenêtré il n'y a AUCUNE console, c'est la seule
    trace d'un plantage. Deux étages : faulthandler → nova-crash.log (piles de
    tous les threads, même sur un plantage NATIF WebView2/pythonnet qui ne
    passe par aucun try/except Python) ; excepthooks → nova.log pour les
    exceptions Python non rattrapées (threads compris). Dans core : chaque
    point d'entrée (app, --preload-models, onboarding) en profite."""
    try:
        import faulthandler
        f = open(_path("nova-crash.log"), "a", encoding="utf-8",
                 errors="replace")
        faulthandler.enable(f)
    except Exception:
        pass
    try:
        sys.excepthook = lambda t, v, tb: log_err("crash", v)
        threading.excepthook = lambda a: log_err("crash_thread", a.exc_value)
    except Exception:
        pass


# ------------------------------------------------------------------ config --

CFG = _merge(DEFAULT_CONFIG, _load("config.json", {}))


# Dictionnaires REMPLACÉS tels quels à la sauvegarde (jamais fusionnés) : la
# fusion récursive de _merge rend toute SUPPRESSION de clé impossible — un
# raccourci de Style retiré réapparaissait à la sauvegarde suivante. Les deux
# écrans envoient toujours le dictionnaire complet pour ces clés.
_REPLACE_KEYS = ("mode_hotkeys",)


def save_config(new_cfg):
    # Lecture-modification-écriture ATOMIQUE du global CFG, tenue sous _lock (le
    # même verrou que l'écriture fichier) : deux fils qui sauvegardent en même
    # temps — p.ex. la bascule « Qualité maximale » et le fil de synchro du modèle
    # qu'elle déclenche — ne peuvent plus s'écraser mutuellement. Sans ça, le
    # lost-update laissait un config incohérent (quality_max=True mais
    # whisper_model="small"). Écriture en place plutôt qu'appel à _save : _lock
    # n'est pas ré-entrant.
    global CFG
    with _lock:
        merged = _merge(CFG, new_cfg)
        for k in _REPLACE_KEYS:
            if isinstance((new_cfg or {}).get(k), dict):
                merged[k] = dict(new_cfg[k])
        CFG = merged
        _save("config.json", CFG)    # _lock est ré-entrant → _save le reprend ;
        #                              reste neutralisable par les tests
    return CFG


def _migrate_plaintext_keys():
    """Les clés API du config.json passent dans le stockage chiffré (DPAPI)."""
    changed = False
    for name in ("anthropic", "openai", "gemini", "deepseek",
                 "groq", "mistral", "xai", "openrouter"):
        key = CFG["providers"].get(name, {}).get("api_key", "")
        if key:
            winext.set_secret(name, key)
            CFG["providers"][name]["api_key"] = ""
            changed = True
    # jeton d'appairage mobile éventuellement resté en clair (config d'avant 2.14)
    tok = CFG.get("mobile_token", "")
    if tok:
        winext.set_secret("mobile_token", tok)
        CFG["mobile_token"] = ""
        changed = True
    if changed:
        _save("config.json", CFG)


_migrate_plaintext_keys()

# gemini-2.0-flash n'a plus de quota gratuit (429 permanent) : on migre
if CFG["providers"].get("gemini", {}).get("model") == "gemini-2.0-flash":
    CFG["providers"]["gemini"]["model"] = "gemini-2.5-flash"
    _save("config.json", CFG)

if not CFG.get("active_profile"):
    CFG["active_profile"] = storage.ensure_default_profile()


def get_api_key(provider):
    key = winext.get_secret(provider)
    if not key and provider == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY", "")
    return key


# ------------------------------------------------------------------ notes ---

def get_notes():
    return _load("notes.json", [])


def add_note(text, title=None):
    notes = get_notes()
    note = {
        "id": uuid.uuid4().hex[:8],
        "title": title or (text.strip().split("\n")[0][:60] or "Note"),
        "text": text.strip(),
        "created": time.strftime("%Y-%m-%d %H:%M"),
    }
    notes.insert(0, note)
    _save("notes.json", notes)
    return note


def update_note(note_id, text=None, title=None):
    notes = get_notes()
    for n in notes:
        if n["id"] == note_id:
            if text is not None:
                n["text"] = text
            if title is not None:
                n["title"] = title
    _save("notes.json", notes)
    return True


def delete_note(note_id):
    notes = [n for n in get_notes() if n["id"] != note_id]
    _save("notes.json", notes)
    return True


# ------------------------------------------------------------ automations ---

def _migrate_automation(item):
    """Accepte l'ancien format de commands.json (keywords/action/target à plat)."""
    if "phrases" in item and isinstance(item.get("action"), dict):
        item.setdefault("id", uuid.uuid4().hex[:8])
        item.setdefault("enabled", True)
        return item
    return {
        "id": item.get("id", uuid.uuid4().hex[:8]),
        "name": item.get("name", "Automatisation"),
        "phrases": item.get("keywords", item.get("phrases", [])),
        "action": {
            "type": item.get("action", "open_url"),
            "target": item.get("target", ""),
            "args": item.get("args", ""),
        },
        "reply": item.get("reply", ""),
        "enabled": item.get("enabled", True),
    }


def get_automations():
    autos = [_migrate_automation(a) for a in _load("commands.json", [])]
    return autos


def save_automation(auto):
    autos = get_automations()
    auto = _migrate_automation(auto)
    for i, a in enumerate(autos):
        if a["id"] == auto["id"]:
            autos[i] = auto
            break
    else:
        autos.append(auto)
    _save("commands.json", autos)
    return auto


def delete_automation(auto_id):
    autos = [a for a in get_automations() if a["id"] != auto_id]
    _save("commands.json", autos)
    return True


# ------------------------------------------------------------------ audio ---

_model = None
_model_name = ""          # nom du modèle actuellement chargé (détecte les changements de profil)
_model_lock = threading.Lock()
_model_state = {"status": "non chargé"}
transcribe_lock = threading.Lock()   # le modèle ne gère qu'une transcription à la fois

# Device STT résolu UNE seule fois : GPU (cuda/float16) si disponible, sinon
# CPU (int8). Sur cette machine, le GPU rend « small » quasi instantané (~500×
# vs CPU) → précision maximale sans compromis de latence. Repli automatique et
# définitif si l'init GPU échoue (autre machine, pilote absent, cuDNN manquant,
# VRAM pleine) : Nova démarre toujours.
_DEVICE = {"device": "", "compute": ""}
_cuda_path_done = False


def _setup_cuda_dll_path():
    """Rend les DLLs CUDA (cublas64_12, cudart64_12, cudnn…) trouvables par
    CTranslate2. Elles vivent dans les paquets nvidia-*-cu12 (dev) ou à côté de
    l'exe (build figé). On les met sur le PATH — indispensable pour les
    dépendances transitives (cublas → cudart) qu'os.add_dll_directory seul ne
    couvre pas. Idempotent ; sans GPU/paquets, ne fait rien."""
    global _cuda_path_done
    if _cuda_path_done:
        return
    _cuda_path_done = True
    import glob
    dirs = []
    if getattr(sys, "frozen", False):                 # exe : DLLs copiées à côté
        dirs.append(os.path.dirname(sys.executable))
    try:
        import nvidia                                 # dev : paquets pip nvidia-*-cu12
        for base in list(nvidia.__path__):
            dirs += glob.glob(os.path.join(base, "*", "bin"))
    except Exception:
        pass
    try:
        import ctranslate2                            # cudnn64_9 embarqué
        dirs.append(os.path.dirname(ctranslate2.__file__))
    except Exception:
        pass
    seen = set()
    for d in dirs:
        if d and d not in seen and os.path.isdir(d):
            seen.add(d)
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            try:
                os.add_dll_directory(d)
            except Exception:
                pass


def _gpu_vram_gb():
    """VRAM totale du premier GPU NVIDIA (Go), 0.0 si indéterminable.
    nvidia-smi est livré avec tout pilote NVIDIA — best-effort, jamais
    bloquant (délai court, aucune fenêtre)."""
    try:
        import subprocess
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return float(out.stdout.strip().splitlines()[0]) / 1024.0
    except Exception:
        return 0.0


def _pick_gpu_compute(vram_gb):
    """PURE (testable sans GPU) : type de calcul selon la VRAM. Les vieilles
    cartes à peu de mémoire ne sont plus du tout-ou-rien :
      • inconnue (0) → float16, comportement historique + repli à l'exécution ;
      • < 1,5 Go     → None : CPU d'emblée (le modèle ne tiendra pas — mieux
                       vaut choisir AVANT que planter le chargement) ;
      • 1,5-3,5 Go   → int8_float16 : moitié moins de mémoire, souvent PLUS
                       rapide sur les anciennes générations ;
      • ≥ 3,5 Go     → float16, pleine précision de calcul."""
    if vram_gb <= 0:
        return "float16"
    if vram_gb < 1.5:
        return None
    if vram_gb < 3.5:
        return "int8_float16"
    return "float16"


def _cpu_threads():
    """Fils de calcul du STT sur CPU : cœurs logiques − 2, borné à [2, 8] —
    la valeur par défaut du moteur est prudente et laisse 20-40 % de vitesse
    sur la table sur un 4-8 cœurs, sans affamer le reste du système."""
    try:
        n = os.cpu_count() or 4
    except Exception:
        n = 4
    return max(2, min(8, n - 2))


def _resolve_device():
    """(device, compute_type), mémorisé. Préférence via CFG['stt']['device'] :
    'auto' (défaut) / 'cuda' / 'cpu'. 'auto' prend le GPU s'il est présent ET
    que sa VRAM suffit (choix du format par _pick_gpu_compute)."""
    if _DEVICE["device"]:
        return _DEVICE["device"], _DEVICE["compute"]
    pref = (CFG.get("stt", {}) or {}).get("device", "auto")
    if pref in ("auto", "cuda", "gpu"):
        _setup_cuda_dll_path()
        try:
            import ctranslate2
            if ctranslate2.get_cuda_device_count() > 0:
                comp = _pick_gpu_compute(_gpu_vram_gb())
                if comp is None and pref in ("cuda", "gpu"):
                    # choix EXPLICITE de l'utilisateur : on tente quand même,
                    # en format économe — le repli CPU du chargement
                    # (_load_whisper) reste le filet si la carte ne tient pas
                    comp = "int8_float16"
                if comp:
                    _DEVICE.update(device="cuda", compute=comp)
                    return _DEVICE["device"], _DEVICE["compute"]
                log_err("gpu_detect", "VRAM insuffisante → CPU d'emblée")
        except Exception as e:
            log_err("gpu_detect", e)
    _DEVICE.update(device="cpu", compute="int8")
    return _DEVICE["device"], _DEVICE["compute"]


def gpu_active():
    """Vrai si le STT tourne sur le GPU (résout le device au besoin)."""
    return _resolve_device()[0] == "cuda"


def _load_whisper(name):
    """Charge un WhisperModel sur le device résolu, avec repli CPU DÉFINITIF si
    le GPU refuse (cuDNN absent, VRAM pleine…) — pour que Nova démarre toujours."""
    from faster_whisper import WhisperModel

    def _mk(**kw):
        # local_files_only=True évite la requête réseau (HEAD vers le Hub) que
        # WhisperModel lance à CHAQUE construction (démarrage + chaque changement
        # de modèle : profil, bascule qualité) : ~quelques centaines de ms sur bon
        # réseau, PLUSIEURS secondes sur réseau d'entreprise/instable, et plus
        # d'attente hors ligne. Le modèle est déjà en cache (pré-téléchargé par
        # download_stt_model). Repli SANS le drapeau si le cache manque encore
        # (1er lancement sans pré-téléchargement) → le téléchargement se fait alors,
        # exactement comme avant. Mêmes octets de poids chargés → texte identique :
        # gain de latence sans coût qualité.
        try:
            return WhisperModel(name, local_files_only=True, **kw)
        except Exception:
            return WhisperModel(name, **kw)

    dev, comp = _resolve_device()
    if dev == "cuda":
        try:
            return _mk(device="cuda", compute_type=comp)
        except Exception as e:
            log_err("gpu_load", e)
            _DEVICE.update(device="cpu", compute="int8")   # bascule CPU pour de bon
    return _mk(device="cpu", compute_type="int8", cpu_threads=_cpu_threads())


_RAM_TOTAL = {"gb": None}   # mémoïsé : la RAM totale ne change pas en session
                            # et cette valeur est relue sur des chemins chauds


def _ram_total_gb():
    """RAM totale de la machine (Go), 0 si indéterminable — les décisions
    « auto » (keep_warm, relèvement qualité, keep_alive du LLM) deviennent
    alors prudentes au lieu de supposer une machine confortable."""
    if _RAM_TOTAL["gb"] is None:
        try:
            import psutil
            _RAM_TOTAL["gb"] = psutil.virtual_memory().total / 1e9
        except Exception:
            _RAM_TOTAL["gb"] = 0.0
    return _RAM_TOTAL["gb"]


def _llm_keep_alive():
    """Durée pendant laquelle Ollama garde le modèle de reformulation chargé
    après usage. Son défaut (~5 min) faisait payer plusieurs secondes de
    rechargement à la première dictée après chaque pause — le pendant LLM du
    problème réglé côté transcription par keep_warm. Dès ~8 Go de RAM : 30 min
    (une session de travail) ; en dessous : comportement d'origine."""
    return "30m" if _ram_total_gb() >= 7.5 else "5m"


# RAM minimale pour tenir le grand moteur multilingue (large-v3-turbo, ~1,5 Go)
# EN PLUS du LLM de reformulation. UN SEUL littéral partagé par stt_keep_warm()
# (le garder chaud) et quality_max_supported() (autoriser son relèvement) : les
# deux encodent le MÊME invariant — ne jamais relever le modèle là où il ne
# pourrait pas rester chaud (sinon rechargement de ~1,5 Go à chaque dictée).
_RAM_TURBO_WARM_GB = 12.0


def stt_keep_warm():
    """Garder le moteur STT en mémoire entre les dictées ? Sans ça, chaque
    dictée commençait par RECHARGER le modèle depuis le disque (2-4 s perdues
    à chaque fois sur un PC sans GPU). « auto » : oui si la RAM peut tenir le
    modèle EN PLUS du LLM de reformulation — seuil proportionné au modèle
    (standard ~0,7 Go dès ~8 Go ; grand moteur multilingue ~1,5 Go dès
    ~12 Go). Jamais pour le très grand modèle (Apex), qui reste séquentiel :
    l'invariant « jamais les deux gros modèles en RAM » prime."""
    pref = (CFG.get("stt") or {}).get("keep_warm", "auto")
    if pref is True or pref is False:
        return pref
    model = CFG.get("whisper_model") or ""
    if model == "large-v3":
        return False
    need = _RAM_TURBO_WARM_GB if model == "large-v3-turbo" else 7.5
    return _ram_total_gb() >= need


def _stt_beam():
    """Largeur de recherche : 5 sur GPU (précision max quasi gratuite) ; sur
    CPU, 1 par défaut (3-5× plus rapide, perte négligeable sur une dictée
    propre) — 5 si l'utilisateur coche « précision maximale »."""
    if gpu_active():
        return 5
    return 5 if (CFG.get("stt") or {}).get("precision_max") else 1


def quality_max_supported():
    """La machine peut-elle tenir le grand moteur multilingue (~1,5 Go) EN PLUS
    du LLM de reformulation ? MÊME seuil que keep_warm pour ce modèle
    (_RAM_TURBO_WARM_GB) : sinon « qualité maximale » relèverait le modèle sans
    pouvoir le garder chaud → rechargement de 1,5 Go à chaque dictée (thrash) et
    promesse UI trompeuse. Le garde-fou RAM des profils ne doit pas être
    contournable par une simple case."""
    return _ram_total_gb() >= _RAM_TURBO_WARM_GB


def effective_stt_model(profile_stt):
    """Modèle STT réellement chargé : celui du profil de puissance, RELEVÉ au
    grand moteur multilingue local (large-v3-turbo) si « qualité maximale »
    est coché — sauf si le profil embarque déjà un modèle au moins aussi bon,
    ou si la machine n'a pas la mémoire pour le tenir (quality_max_supported)."""
    if ((CFG.get("stt") or {}).get("quality_max")
            and profile_stt in ("tiny", "base", "small")
            and quality_max_supported()):
        return "large-v3-turbo"
    return profile_stt


_stt_sync_lock = threading.Lock()   # sérialise la lecture-calcul-écriture de
#                                     whisper_model. Verrou FEUILLE : n'acquiert
#                                     _lock/_model_lock qu'ensuite (via
#                                     set_stt_model), jamais l'inverse → pas
#                                     d'inversion d'ordre possible.


def sync_stt_model():
    """Aligne whisper_model sur le profil courant + l'option qualité maximale
    (appelé quand l'option change). Décharge l'ancien modèle au besoin.
    Lecture (effective_stt_model lit quality_max + profil) ET écriture
    (set_stt_model) tenues sous _stt_sync_lock : deux bascules rapides (Qualité
    ON puis OFF, ou double-clic) ne peuvent plus écrire whisper_model dans le
    désordre — plus d'état incohérent « grand moteur chargé alors que
    quality_max=False »."""
    try:
        import power_profiles
        with _stt_sync_lock:
            p = power_profiles.get_profile(CFG.get("profile") or "normal")
            want = effective_stt_model(p["stt"])
            if want != CFG.get("whisper_model"):
                set_stt_model(want)
    except Exception as e:
        log_err("stt_quality", e)


def download_stt_model(name=None):
    """Pré-télécharge le modèle STT dans le cache local SANS tenir _model_lock :
    le téléchargement (~1,5 Go) peut durer des minutes et, sous le verrou, il
    gelait la dictée ET les réglages pendant tout ce temps. get_model() n'a
    ensuite qu'un chargement disque de quelques secondes à faire sous verrou.
    Best-effort : hors ligne, le chargement échouera et son erreur est déjà
    gérée par l'appelant."""
    try:
        from faster_whisper.utils import download_model
        download_model(name or CFG["whisper_model"])
    except Exception as e:
        log_err("stt_download", e)


def get_model():
    global _model, _model_name
    with _model_lock:
        want = CFG["whisper_model"]
        # recharge si le modèle voulu a changé (ex. changement de profil de
        # puissance) : sinon un modèle lourd resterait en RAM après un passage à
        # un profil plus léger, ruinant la garantie « jamais de saturation RAM ».
        if _model is None or _model_name != want:
            _model_state["status"] = "chargement…"
            try:
                # on charge dans une variable temporaire : si le nouveau modèle
                # échoue (fichier absent/corrompu, hors ligne au 1er usage après
                # un changement de profil), l'ancien modèle qui marchait reste en
                # place → la dictée continue au lieu d'être cassée.
                m = _load_whisper(want)
            except Exception as e:
                _model_state["status"] = f"erreur : {e}"
                if _model is not None:
                    log_err("stt_reload", e)   # garde le modèle courant, réessaiera
                    return _model
                raise
            _model = m
            _model_name = want
            _model_state["status"] = "prêt (%s)" % _DEVICE["device"].upper()
            log_err("stt_device", "modèle « %s » chargé sur %s/%s"
                    % (want, _DEVICE["device"], _DEVICE["compute"]))
    return _model


def model_status():
    return _model_state["status"]


def unload_whisper():
    """Libère le modèle Whisper de la RAM (gestion mémoire séquentielle, GOAL
    Partie 5) : sur les petites configs on décharge le STT après transcription,
    avant de solliciter le LLM, pour ne jamais tenir les deux gros modèles en
    mémoire. Rechargé paresseusement au prochain get_model()."""
    global _model
    import gc
    with _model_lock:
        _model = None
        _model_state["status"] = "déchargé"
    gc.collect()


def set_stt_model(name):
    """Change le modèle Whisper actif (mapping profil de puissance → STT) et
    décharge l'ancien pour que le nouveau soit chargé au prochain usage."""
    if name and name != CFG.get("whisper_model"):
        save_config({"whisper_model": name})
        unload_whisper()


_wake_model = None
_wake_model_name = ""
_wake_model_lock = threading.Lock()
quick_lock = threading.Lock()


def get_wake_model():
    """Petit modèle dédié au mot d'éveil et aux aperçus live (base par défaut :
    réagit en une fraction de seconde là où small prend plusieurs secondes).
    Chargé sur le même device que le modèle principal (GPU si dispo)."""
    global _wake_model, _wake_model_name
    name = CFG.get("wake_model", "tiny")
    if name == CFG.get("whisper_model"):
        return get_model()
    with _wake_model_lock:
        if _wake_model is None or _wake_model_name != name:
            _wake_model = _load_whisper(name)
            _wake_model_name = name
    return _wake_model


# --- seuil de voix adaptatif : suit le bruit ambiant du micro au lieu d'un
#     seuil fixe (micro discret → seuil abaissé, pièce bruyante → relevé).
NOISE = {"floor": 0.0}


def update_noise(rms):
    f = NOISE["floor"]
    if f <= 0:
        NOISE["floor"] = rms
    elif rms < f:
        NOISE["floor"] = f * 0.9 + rms * 0.1
    else:
        NOISE["floor"] = min(f * 1.01 + 1e-5, rms)


def _rms(block):
    """Niveau RMS d'un bloc audio — partagé par l'enregistreur et la
    transcription en continu (même définition de « voix »)."""
    return float(np.sqrt(np.mean(block ** 2)))


def effective_threshold():
    f = NOISE["floor"]
    if f <= 0:
        return CFG["silence_threshold"]
    return max(0.003, f * 2.8)


def voiced_rms_min():
    """Rms voisé moyen minimal du filtre pré-ASR : borné par le seuil de
    détection adaptatif au lieu du 0,008 fixe hérité de JARVIS. Sur un micro à
    faible gain (voix détectée entre 0,003 et 0,008), une vraie phrase n'est
    plus jetée systématiquement ; comportement inchangé sur un micro normal."""
    return min(0.008, max(0.004, effective_threshold() * 1.5))


_MIC_CACHE = {"t": 0.0, "list": []}


def list_mics():
    """Micros disponibles [{index, name, default}] — mis en cache 10 s
    (l'UI interroge l'état toutes les ~1,2 s)."""
    now = time.time()
    if now - _MIC_CACHE["t"] < 10:
        return _MIC_CACHE["list"]
    out = []
    try:
        import sounddevice as sd
        try:
            default_in = sd.default.device[0]
        except Exception:
            default_in = -1
        seen = set()
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) <= 0:
                continue
            name = (d.get("name") or "").strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            out.append({"index": i, "name": name[:60], "default": i == default_in})
    except Exception as e:
        log_err("list_mics", e)
    _MIC_CACHE.update(t=now, list=out)
    return out


def _mic_kw():
    """Argument device= pour sd.InputStream selon le micro choisi.
    Index invalide (périphérique débranché) → défaut Windows."""
    idx = CFG.get("mic_device_index")
    if idx is None or idx == "":
        return {}
    try:
        import sounddevice as sd
        d = sd.query_devices(int(idx))
        if d.get("max_input_channels", 0) > 0:
            return {"device": int(idx)}
    except Exception:
        pass
    return {}


# Époque des reprises micro : incrémentée (sous frames_lock) quand
# record_audio JETTE le tampon partagé après une perte du périphérique.
# LiveTranscriber la surveille : sa détection « le tampon a rétréci »
# (len < _done) peut rater la fenêtre si un commit de plusieurs secondes est
# en vol pendant que le tampon se vide PUIS regrossit au-delà de _done.
_MIC_EPOCH = {"n": 0}


def record_audio(on_level=None, frames_out=None, frames_lock=None, cancel=None,
                 end_silence=None, min_voiced=0.0, stop=None):
    """Enregistre jusqu'au silence. on_level(rms) est appelé à chaque bloc (pour
    l'animation) ; frames_out/frames_lock permettent la transcription partielle
    live ; cancel (threading.Event) interrompt et renvoie None (clic ailleurs) ;
    stop (threading.Event) TERMINE et CONSERVE l'audio — base du push-to-talk :
    on relâche la touche, l'enregistrement s'arrête et ce qui a été dit est gardé ;
    end_silence remplace silence_seconds (commandes = plus réactif que dictée) ;
    min_voiced (s) : filtre pré-ASR JARVIS — un enregistrement qui contient
    moins de voix que ça (ou trop faible en moyenne) est jeté au lieu d'être
    transcrit (supprime les hallucinations Whisper sur du bruit)."""
    import sounddevice as sd
    sr = 16000
    frames = frames_out if frames_out is not None else []
    started = False
    silence_start = None
    voiced = 0          # blocs de 0,1 s au-dessus du seuil
    rms_sum = 0.0
    limit = float(end_silence or CFG["silence_seconds"])
    t0 = time.time()

    def _run(dev_kw):
        nonlocal started, silence_start, voiced, rms_sum, t0
        with sd.InputStream(samplerate=sr, channels=1, dtype="float32",
                            **dev_kw) as stream:
            while True:
                if cancel is not None and cancel.is_set():
                    return "cancel"
                if stop is not None and stop.is_set():
                    return "ok"        # touche relâchée : on garde ce qui est dit
                block, _ = stream.read(int(sr * 0.1))
                if frames_lock:
                    with frames_lock:
                        frames.append(block.copy())
                else:
                    frames.append(block.copy())
                rms = _rms(block)
                if on_level:
                    on_level(rms)
                now = time.time()
                if not started:
                    update_noise(rms)
                if rms > effective_threshold():
                    started = True
                    silence_start = None
                    voiced += 1
                    rms_sum += rms
                elif started:
                    if silence_start is None:
                        silence_start = now
                    elif now - silence_start > limit:
                        return "ok"
                if now - t0 > CFG["max_record_seconds"]:
                    return "ok"
                if not started and now - t0 > 5:
                    return "ok"

    try:
        res = _run(_mic_kw())
    except (sd.PortAudioError, OSError) as e:
        # micro perdu/débranché : une seule relance sur le périphérique par
        # défaut, seuil de bruit remis à zéro (recalibrage immédiat)
        log_err("record_audio", e)
        NOISE["floor"] = 0.0
        # vidage SOUS verrou (le fil du live lit ce tampon en parallèle) et
        # époque incrémentée : la transcription en continu sait que son texte
        # committé décrit de l'audio disparu, même si elle rate le passage à vide
        if frames_lock:
            with frames_lock:
                frames.clear()
                _MIC_EPOCH["n"] += 1
        else:
            frames.clear()
            _MIC_EPOCH["n"] += 1
        started, silence_start, voiced, rms_sum = False, None, 0, 0.0
        t0 = time.time()
        try:
            res = _run({})
        except Exception as e2:
            log_err("record_audio_retry", e2)
            return None
    if res == "cancel" or not started:
        return None
    # filtre anti-bruit (valeurs JARVIS converties int16 → float32)
    if min_voiced and (voiced * 0.1 < min_voiced
                       or (rms_sum / max(1, voiced)) < voiced_rms_min()):
        return None
    return np.concatenate(frames).flatten()


def _stt_language():
    """Code langue pour Whisper, ou None si « auto » (détection automatique).
    « auto » n'est pas un code ISO valide : le passer tel quel casse le STT."""
    lang = CFG.get("language", "fr")
    return None if lang in ("auto", "", None) else lang


def transcribe(audio, prompt=None):
    """Transcription locale complète. `prompt` (amorce) : par défaut le lexique
    utilisateur (stt_prompt) ; la transcription en continu passe le texte déjà
    committé — UNE seule invocation du modèle dans tout le dépôt."""
    prompt = prompt or stt_prompt() or None
    # verrou BORNÉ : si une transcription de fond est figée (modèle
    # pathologiquement lent, machine en swap), attendre sans limite gèlerait
    # la dictée entière — le repli de LiveTranscriber.finish() bloquait sur ce
    # même verrou. Au-delà, on lève : chaque appelant a déjà son chemin d'erreur.
    if not transcribe_lock.acquire(timeout=120):
        raise TimeoutError("transcription de fond figée")
    try:
        segments, _info = get_model().transcribe(
            audio, language=_stt_language(), beam_size=_stt_beam(),
            vad_filter=True, initial_prompt=prompt)
        return " ".join(s.text for s in segments).strip()
    finally:
        transcribe_lock.release()


def transcribe_quick(audio, prompt=None, beam=1):
    """Transcription rapide avec le petit modèle d'éveil (« base »).
    prompt amorce le modèle (ex. le mot d'éveil : « Nova. » — testé, ça fait
    passer la détection de ratée à fiable). Si le petit modèle n'est pas
    disponible (téléchargement en cours/échoué), repli sur le principal.

    beam :
      1 (défaut) → mot d'éveil et aperçus live : le plus vif possible.
      3          → commande courte (transcribe_routed fast) : mesuré, fait
                   passer l'intention de 6/12 à 8/12 — la précision du gros
                   modèle — pour seulement +0,2 s (voir bench_stt.py)."""
    try:
        model = get_wake_model()
    except Exception as e:
        log_err("wake_model", e)
        model = get_model()
    lock = transcribe_lock if model is _model else quick_lock
    with lock:
        segments, _info = model.transcribe(
            audio, language=_stt_language(), beam_size=beam, vad_filter=True,
            condition_on_previous_text=False, initial_prompt=prompt)
        return " ".join(s.text for s in segments).strip()


# ------------------------------------------------------------------ IA ------

LLM_ACTIONS = ("open_url", "open_app", "web_search", "keys", "type_text",
               "shell", "media", "note", "timer", "wait", "look_screen",
               "fact", "home", "file_rename", "file_move", "none")

LLM_SYSTEM_TEMPLATE = (
    "Tu es le cerveau de Nova, un assistant vocal Windows. L'utilisateur vient de dicter une "
    "demande (transcription automatique : mots déformés possibles — corrige mentalement, "
    "ex. « meilleur minuteur » = « mets un minuteur »).\n"
    "Tu es un AGENT : l'utilisateur décrit un RÉSULTAT, à toi de trouver la suite d'actions "
    "qui y mène. Décompose TOUTE la demande : si elle contient plusieurs actions ou "
    "informations, traite-les toutes, dans l'ordre dit, sans en oublier une seule. Ajoute "
    "les étapes intermédiaires évidentes même si elles n'ont pas été dites : ouvrir "
    "l'application avant d'y taper, wait 1 à 2 s après une ouverture pour laisser la page "
    "charger, keys enter pour valider une recherche…\n"
    "Privilégie TOUJOURS les vraies applications Windows et les vrais sites de "
    "l'utilisateur (open_app, open_url) plutôt qu'une réponse texte qui simule : "
    "« ouvre Google » = le vrai google.com, « mets du jazz » = la vraie appli/site de "
    "musique. L'action timer ouvre déjà un compte à rebours visible.\n"
    "Réfléchis avant d'agir : la cible est-elle une APPLICATION INSTALLÉE "
    "(→ open_app avec l'exécutable : chrome, firefox, msedge, winword, excel, vlc, "
    "steam, notepad…), un SITE (→ open_url) ou un RÉGLAGE Windows (→ open_app "
    "ms-settings:…) ? « Ouvre Google Chrome » = open_app chrome, JAMAIS google.com. "
    "« Ouvre Word » = open_app winword, pas une recherche.\n"
    "Réponds UNIQUEMENT avec un objet JSON :\n"
    '{"reply": "confirmation très courte en français", '
    '"steps": [{"action": "...", "target": "...", "args": ""}, ...]}\n'
    "Actions disponibles :\n"
    "- open_url : target = URL complète la plus pertinente.\n"
    "- open_app : target = exécutable Windows (notepad, calc…), URI (spotify:, ms-settings:) "
    "ou chemin complet ; args = arguments éventuels. Pour une page précise des Paramètres "
    "Windows, utilise l'URI exacte : ms-settings:display, ms-settings:sound, "
    "ms-settings:bluetooth, ms-settings:network-wifi, ms-settings:windowsupdate, "
    "ms-settings:privacy, ms-settings:appsfeatures…\n"
    "- web_search : target = termes de recherche Google.\n"
    "- keys : target = raccourci clavier (ex. ctrl+s, win+e, f11, ctrl+shift+escape).\n"
    "- type_text : target = texte tapé au clavier à l'endroit du curseur. Sers-t'en pour "
    "RÉDIGER ce qu'on te demande (mail, liste, paragraphe…) : mets le texte complet.\n"
    "- shell : target = commande Windows. Jamais de commande destructrice.\n"
    "- media : target = playPause | next | prev | volUp | volDown | mute.\n"
    "- note : target = contenu à mémoriser dans les notes de Nova.\n"
    "- timer : target = durée (ex. « 10 minutes »), args = libellé du rappel.\n"
    "- wait : target = secondes d'attente (max 8), ex. laisser une app s'ouvrir avant de taper.\n"
    "- look_screen : SEULE étape, target vide. Utilise-la dès que tu dois VOIR l'écran "
    "pour répondre (lire, décrire, résumer, traduire ou expliquer ce qui est affiché, "
    "répondre à un mail visible, « c'est quoi ça »…) et qu'aucune capture n'est jointe : "
    "Nova te renverra la même demande avec la capture d'écran.\n"
    "- fact : target = information durable sur l'utilisateur à mémoriser (il demande "
    "explicitement de retenir, ou donne une info clairement réutilisable plus tard).\n"
    "- home : domotique Home Assistant — target = on | off | color <couleur> | "
    "bright <0-100>, args = le nom de l'appareil ({ha_names}). Uniquement ces appareils.\n"
    "- file_rename : target = nom (partiel) du fichier à retrouver dans "
    "Bureau/Téléchargements/Documents, args = nouveau nom. Jamais d'écrasement.\n"
    "- file_move : target = nom (partiel) du fichier, args = dossier cible "
    "(téléchargements, bureau, documents, images, vidéos, musique).\n"
    "- none : impossible/incompris ; steps = [] et explique brièvement dans reply.\n"
    "Règles : 12 étapes maximum, l'ordre compte. Si on te demande d'écrire quelque chose "
    "SANS préciser où, type_text directement (le curseur est déjà placé) ; si la cible est "
    "NOMMÉE (un mail, le bloc-notes, une recherche…), ouvre-la d'abord, attends, puis agis. "
    "Tu ne vois pas l'écran : quand la suite exigerait de lire (choisir un résultat, lire "
    "un mail reçu), amène l'utilisateur au bon endroit et dis-le dans reply.\n"
    "Exemples :\n"
    "« mets un minuteur de dix minutes et ouvre netflix » → steps : timer « 10 minutes », "
    "puis open_url https://www.netflix.com\n"
    "« écris une liste de courses dans le bloc-notes » → open_app notepad, wait 1.5, "
    "type_text (la liste complète, avec des retours à la ligne)\n"
    "« cherche des vidéos de cuisine sur youtube » → open_url "
    "https://www.youtube.com/results?search_query=vid%C3%A9os+de+cuisine\n"
    "« réponds à mon dernier mail que j'arrive » → open_url https://mail.google.com, "
    "reply : « Gmail est ouvert : ouvre le mail et je te dicterai la réponse »\n"
    "« qu'est-ce que tu vois ? », « c'est quoi ce truc ? », « aide-moi là-dessus » → "
    "steps : look_screen (JAMAIS « demande incomprise » : demande la capture et regarde)\n"
    "Infos personnelles : si l'utilisateur veut insérer son adresse, son numéro de téléphone, "
    "son e-mail ou son prénom, écris LITTÉRALEMENT « mon adresse », « mon numéro de "
    "téléphone », « mon e-mail », « mon prénom » dans type_text : Nova remplace localement "
    "par les vraies valeurs (tu ne les connais pas).\n"
    "Corrections à l'oral : si l'utilisateur se reprend (« euh non », « plutôt », « pardon, "
    "je voulais dire »), n'exécute QUE la version corrigée, jamais les deux.\n"
    "Date et heure actuelles : {now}.\n"
    "Automatisations déjà définies par l'utilisateur (déclenchées ailleurs par phrases "
    "exactes) : {autos}. Si la demande y correspond mais formulée autrement, accomplis "
    "la même chose avec tes propres actions."
)

LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "steps": {
            "type": "array",
            "maxItems": 12,
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": list(LLM_ACTIONS)},
                    "target": {"type": "string"},
                    "args": {"type": "string"},
                },
                "required": ["action", "target"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["reply", "steps"],
    "additionalProperties": False,
}

OPENAI_COMPAT = {
    "openai":     "https://api.openai.com/v1/chat/completions",
    "deepseek":   "https://api.deepseek.com/v1/chat/completions",
    "gemini":     "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    "groq":       "https://api.groq.com/openai/v1/chat/completions",
    "mistral":    "https://api.mistral.ai/v1/chat/completions",
    "xai":        "https://api.x.ai/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}


def _llm_system():
    autos = ", ".join(a["name"] for a in get_automations()) or "aucune"
    ents = CFG.get("ha_entities") or {}
    ha_names = ", ".join(f"{k} ({v.get('type', '?')})" for k, v in ents.items()
                         if isinstance(v, dict)) or "aucun appareil configuré"
    txt = (LLM_SYSTEM_TEMPLATE
           .replace("{autos}", autos)
           .replace("{ha_names}", ha_names)
           .replace("{now}", time.strftime("%A %d/%m/%Y %H:%M")))
    who = personal_info().get("prenom", "").strip()
    if who:
        txt += f"\nL'utilisateur s'appelle {who}."
    city = (CFG.get("city") or "").strip()
    if city:
        txt += f" Il se trouve à {city}."
    try:
        facts = storage.list_facts(25)
    except Exception:
        facts = []
    if facts:
        lst = " ; ".join(
            f"{f['fact']} (noté le "
            f"{time.strftime('%d/%m/%Y', time.localtime((f.get('ts') or 0) / 1000))})"
            for f in facts)[:900]
        txt += ("\nMémoire durable dictée par l'utilisateur (« souviens-toi "
                "que… ») — sers-t'en dès que c'est pertinent : " + lst)
    if CFG.get("tts", {}).get("enabled"):
        txt += ("\nreply est lu À VOIX HAUTE par une synthèse vocale : aucun "
                "Markdown (ni *, ni #, ni puces), pas d'URL brute (dis « le "
                "lien »), nombres arrondis et naturels à l'oreille "
                "(« 20 degrés », jamais « 20.3 »).")
    return txt


def _normalize_llm(result):
    """Uniformise la réponse IA : accepte l'ancien format {action, target}
    (fournisseurs sans schéma strict) et borne les étapes aux actions connues."""
    if not isinstance(result, dict):
        return None
    if "steps" not in result and result.get("action"):
        steps = [] if result["action"] == "none" else [
            {"action": result["action"], "target": result.get("target", ""),
             "args": result.get("args", "")}]
        result = {"reply": result.get("reply", ""), "steps": steps}
    steps = []
    for s in (result.get("steps") or [])[:12]:
        if isinstance(s, dict) and s.get("action") in LLM_ACTIONS and s["action"] != "none":
            steps.append({"action": s["action"], "target": str(s.get("target", "")),
                          "args": str(s.get("args", ""))})
    return {"reply": str(result.get("reply", "")), "steps": steps}


def _extract_json(raw):
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError(f"Réponse IA sans JSON : {raw[:120]}")
    return json.loads(m.group(0))


def ollama_url():
    return CFG["providers"]["ollama"].get("url", "http://localhost:11434").rstrip("/")


def ollama_models():
    """Modèles déjà téléchargés localement. [] si Ollama absent/éteint."""
    try:
        import requests
        r = requests.get(ollama_url() + "/api/tags", timeout=1.5)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return None


_PROV_PRIORITY = ("anthropic", "openai", "gemini", "deepseek",
                  "groq", "mistral", "xai", "openrouter")

# Santé mesurée des fournisseurs (en mémoire) : dernier appel réussi/raté,
# latence, et cooldown pour ne pas marteler un quota épuisé (429).
PROV_HEALTH = {}


def _mark_provider(name, ok, ms=0, detail="", cooldown=0):
    PROV_HEALTH[name] = {"ok": ok, "ms": ms, "detail": detail, "ts": time.time(),
                         "until": time.time() + cooldown if cooldown else 0}


def provider_health():
    """État par fournisseur pour l'UI : mémoire vive prioritaire, sinon le
    dernier test persisté dans config.json (survit au redémarrage)."""
    saved = CFG.get("provider_status", {}) or {}
    out = {}
    for name in _PROV_PRIORITY + ("ollama",):
        h = PROV_HEALTH.get(name) or saved.get(name)
        if h:
            out[name] = {k: h.get(k) for k in ("ok", "ms", "detail", "ts")}
    return out


def _human_err(e):
    """Erreur fournisseur → phrase courte en français (pilule + page IA)."""
    import requests as _rq
    if isinstance(e, _rq.exceptions.Timeout):
        return "Délai dépassé, connexion lente ou service surchargé"
    if isinstance(e, _rq.exceptions.ConnectionError):
        return "Fournisseur injoignable, vérifiez la connexion"
    code = getattr(e, "status_code", None) \
        or getattr(getattr(e, "response", None), "status_code", None)
    if code in (401, 403):
        return "Clé d'accès invalide ou non autorisée"
    if code == 404:
        return "Modèle introuvable, vérifiez son nom"
    if code == 429:
        return "Limite d'utilisation atteinte, réessayez dans quelques minutes"
    if code and code >= 500:
        return f"Service en panne côté fournisseur ({code})"
    return str(e)[:120]


def _cooldown_for(e):
    """Combien de temps éviter ce fournisseur en mode auto après cet échec."""
    code = getattr(e, "status_code", None) \
        or getattr(getattr(e, "response", None), "status_code", None)
    if code == 429:
        try:
            retry = int(float(e.response.headers.get("Retry-After", "")))
        except Exception:
            retry = 0
        return min(max(retry, 60), 300)
    if code in (401, 403, 404):
        return 600  # clé ou modèle cassé : réessayer ne changera rien
    return 20


def provider_order():
    """Fournisseurs utilisables, du plus prometteur au moins prometteur.
    En mode auto : validés d'abord (triés par latence), puis non testés,
    puis en échec — c'est ça « Nova choisit le meilleur fournisseur »."""
    p = CFG.get("provider", "auto")
    if p == "off":
        return []
    if p != "auto":
        return [p]
    names = [n for n in _PROV_PRIORITY if get_api_key(n)]
    if ollama_models():
        names.append("ollama")
    health = provider_health()

    def rank(n):
        h = health.get(n) or {}
        state = 0 if h.get("ok") else (1 if h.get("ok") is None else 2)
        prio = _PROV_PRIORITY.index(n) if n in _PROV_PRIORITY else 9
        return (state, h.get("ms") or 99999, prio)

    return sorted(names, key=rank)


def resolve_provider():
    order = provider_order()
    return order[0] if order else "off"


VISION_PROVIDERS = ("anthropic", "openai", "gemini")

VISION_BOX_SYSTEM = (
    "Tu es l'œil de Nova. On te donne une capture d'écran ({w}x{h} px) et une "
    "cible à localiser. Réponds UNIQUEMENT en JSON : "
    '{"box":[ymin,xmin,ymax,xmax],"found":true,"desc":"court"} — coordonnées '
    "normalisées 0 à 1000 (0 = haut/gauche, 1000 = bas/droite). Si l'élément "
    'est introuvable : {"found":false}.'
)


def ask_vision_box(target, image, w, h):
    """Localise un élément à l'écran via l'IA vision. Retourne (x_px, y_px,
    desc) en pixels absolus, ou None. target = « le bouton Lecture »…"""
    sys_txt = VISION_BOX_SYSTEM.replace("{w}", str(w)).replace("{h}", str(h))
    prov = resolve_provider()
    order = [prov] if prov in VISION_PROVIDERS else []
    order += [p for p in provider_order() if p in VISION_PROVIDERS and p not in order]
    content = [
        {"type": "text", "text": "Cible : " + target},
        {"type": "image_url",
         "image_url": {"url": "data:image/jpeg;base64," + image}},
    ]
    for name in order:
        try:
            raw = _vision_raw(name, sys_txt, content, image, target)
            data = _extract_json(raw)
            if not data.get("found", True) or "box" not in data:
                continue
            ymin, xmin, ymax, xmax = data["box"]
            x = int((xmin + xmax) / 2 / 1000 * w)
            y = int((ymin + ymax) / 2 / 1000 * h)
            return x, y, data.get("desc", target)
        except Exception as e:
            log_err("vision_box_" + name, e)
    return None


def _vision_raw(provider, sys_txt, content, image, target):
    """Appel vision brut renvoyant le texte (pour ask_vision_box)."""
    prov = CFG["providers"]
    if provider == "anthropic":
        from anthropic import Anthropic
        client = Anthropic(api_key=get_api_key("anthropic") or None)
        msg = client.messages.create(
            model=prov["anthropic"]["model"] or "claude-haiku-4-5",
            max_tokens=300, system=sys_txt,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64",
                                             "media_type": "image/jpeg", "data": image}},
                {"type": "text", "text": "Cible : " + target}]}])
        return next(b.text for b in msg.content if b.type == "text")
    import requests
    api_key = get_api_key(provider)
    r = requests.post(OPENAI_COMPAT[provider], timeout=30,
                      headers={"Authorization": f"Bearer {api_key}"},
                      json={"model": prov[provider]["model"],
                            "messages": [{"role": "system", "content": sys_txt},
                                         {"role": "user", "content": content}]})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

_VISION_NOTE = (
    "\nUne capture de l'écran de l'utilisateur est jointe : réponds d'après ce "
    "qui est VISIBLE (lis, résume, explique, traduis, agis dessus). Si on te "
    "demande de rédiger une réponse (mail, message…), donne le texte dans reply "
    "ou tape-le via type_text si le curseur est déjà au bon endroit."
)


def _ask_one(provider, text, context=None, image=None):
    """Un appel IA vers UN fournisseur donné (lève une exception en cas d'échec).
    image = capture d'écran JPEG base64 (fournisseurs vision uniquement)."""
    prov = CFG["providers"]
    if image and provider not in VISION_PROVIDERS:
        raise RuntimeError(f"{provider} ne lit pas les images")
    sys_txt = _llm_system() + (_VISION_NOTE if image else "")
    content = text if not image else [
        {"type": "text", "text": text},
        {"type": "image_url",
         "image_url": {"url": "data:image/jpeg;base64," + image}},
    ]
    user_msgs = list(context or []) + [{"role": "user", "content": content}]
    if provider == "anthropic":
        from anthropic import Anthropic
        if image:
            user_msgs[-1] = {"role": "user", "content": [
                {"type": "image", "source": {"type": "base64",
                                             "media_type": "image/jpeg",
                                             "data": image}},
                {"type": "text", "text": text},
            ]}
        client = Anthropic(api_key=get_api_key("anthropic") or None)
        msg = client.messages.create(
            model=prov["anthropic"]["model"] or "claude-haiku-4-5",
            max_tokens=700 if image else 300,
            system=sys_txt,
            output_config={"format": {"type": "json_schema", "schema": LLM_SCHEMA}},
            messages=user_msgs,
        )
        return _normalize_llm(_extract_json(next(b.text for b in msg.content if b.type == "text")))

    import requests
    if provider == "ollama":
        model = prov["ollama"]["model"] or ((ollama_models() or [""])[0])
        if not model:
            raise RuntimeError("Aucun modèle Ollama installé")
        r = requests.post(ollama_url() + "/api/chat", timeout=90, json={
            "model": model, "stream": False, "format": "json",
            "keep_alive": _llm_keep_alive(),
            "messages": [{"role": "system", "content": sys_txt}] + user_msgs,
        })
        r.raise_for_status()
        return _normalize_llm(_extract_json(r.json()["message"]["content"]))

    if provider in OPENAI_COMPAT:
        api_key = get_api_key(provider)
        if not api_key:
            raise RuntimeError(f"Clé API {provider} manquante")
        body = {
            "model": prov[provider]["model"],
            "messages": [{"role": "system", "content": sys_txt}] + user_msgs,
        }
        if provider != "openrouter":   # openrouter/auto : certains modèles le refusent
            body["response_format"] = {"type": "json_object"}
        r = requests.post(OPENAI_COMPAT[provider], timeout=60,
                          headers={"Authorization": f"Bearer {api_key}"},
                          json=body)
        r.raise_for_status()
        return _normalize_llm(_extract_json(r.json()["choices"][0]["message"]["content"]))

    raise RuntimeError(f"Fournisseur inconnu : {provider}")


def ask_llm(text, provider=None, context=None, image=None):
    """Demande libre → plan d'actions. Fournisseur imposé, ou mode auto :
    essaie chaque fournisseur configuré et bascule sur le suivant en cas
    d'échec (quota, panne…), en mémorisant la santé de chacun.
    image : capture d'écran b64 → seuls les fournisseurs vision sont essayés."""
    if provider:
        t0 = time.time()
        try:
            res = _ask_one(provider, text, context, image)
            _mark_provider(provider, True, int((time.time() - t0) * 1000))
            return res
        except Exception as e:
            _mark_provider(provider, False, detail=_human_err(e),
                           cooldown=_cooldown_for(e))
            raise
    order = provider_order()
    if not order:
        return None
    now = time.time()
    usable = [n for n in order
              if PROV_HEALTH.get(n, {}).get("until", 0) <= now] or order
    if image:
        usable = [n for n in usable if n in VISION_PROVIDERS]
        if not usable:
            raise RuntimeError("Aucune IA compatible vision — configure OpenAI, "
                               "Gemini ou Anthropic (page Intelligence)")
    last = None
    for name in usable:
        t0 = time.time()
        try:
            res = _ask_one(name, text, context, image)
            _mark_provider(name, True, int((time.time() - t0) * 1000))
            return res
        except Exception as e:
            log_err("llm_" + name, e)
            _mark_provider(name, False, detail=_human_err(e),
                           cooldown=_cooldown_for(e))
            last = e
    if len(usable) == 1:
        raise RuntimeError(_human_err(last))
    raise RuntimeError("Aucune IA n'a répondu — " + " ; ".join(
        f"{n} : {(PROV_HEALTH.get(n) or {}).get('detail', '?')}" for n in usable))


def test_provider(provider):
    """Aller-retour rapide pour valider une clé / un modèle. Le résultat est
    persisté (provider_status) pour afficher « validé » après redémarrage."""
    try:
        t0 = time.time()
        result = ask_llm("Ouvre google", provider=provider)
        ms = int((time.time() - t0) * 1000)
        ok = isinstance(result, dict) and "steps" in result
        detail = "" if ok else "réponse invalide"
    except Exception as e:
        ok, ms, detail = False, 0, _human_err(e)
    save_config({"provider_status": {provider: {
        "ok": ok, "ms": ms, "detail": detail, "ts": int(time.time()),
        "model": CFG["providers"].get(provider, {}).get("model", "")}}})
    return {"ok": ok, "ms": ms, "detail": detail}


# « Meilleure IA » (palier Ultra) : modèle cloud PETIT, RAPIDE et PEU COÛTEUX
# couvrant la plupart des langues — l'API cloud du palier Ultra étant illimitée,
# le coût unitaire doit rester négligeable (décision produit : pas de modèle
# phare type Opus ici). Pour le local, cf. power_profiles.best_local_llm.
# Les fournisseurs non listés gardent le modèle choisi par l'utilisateur.
BEST_CLOUD_LLM = {
    "groq":      "llama-3.3-70b-versatile",   # quasi gratuit, le plus rapide,
    #                                           même clé que le STT Groq
    "anthropic": "claude-haiku-4-5",          # petit, rapide, 100+ langues
}


def _best_ai_on():
    """La « Meilleure IA » est-elle activée ET débloquée (palier Ultra) ?"""
    if not CFG.get("best_ai"):
        return False
    try:
        import licensing
        return licensing.has("best_models")
    except Exception:
        return False


def _reform_model(provider):
    """Modèle de reformulation pour ce fournisseur. « Meilleure IA » active →
    modèle premium (meilleur local selon la RAM, meilleur cloud selon le
    fournisseur) ; sinon le modèle configuré par l'utilisateur."""
    cfg_model = CFG["providers"].get(provider, {}).get("model", "")
    if not _best_ai_on():
        return cfg_model
    if provider == "ollama":
        try:
            import power_profiles
            return power_profiles.best_local_llm()
        except Exception:
            return cfg_model
    return BEST_CLOUD_LLM.get(provider, cfg_model)


def _ollama_warm_model():
    """Le modèle Ollama que la prochaine reformulation chargera RÉELLEMENT —
    résolution unique, partagée par _complete_one et warmup_engines. Sans
    elle, le préchauffage lisait le modèle configuré brut et pouvait charger
    un modèle différent de celui de la dictée : deux résidents pendant
    30 minutes."""
    return _reform_model("ollama") or ((ollama_models() or [""])[0])


def _llm_num_ctx():
    """Fenêtre de contexte du LLM de reformulation. Assez GRANDE pour que le
    PRÉFIXE système (COMMON_RULES = garde-fous absolus « reformule / ne réponds
    JAMAIS », « zéro invention ») ne soit JAMAIS tronqué : Ollama coupe
    silencieusement l'entrée > num_ctx EN PARTANT DU DÉBUT (défaut ~2048) — il
    supprimerait donc justement ces règles sur une dictée longue, laissant le
    modèle RÉPONDRE à une question dictée ou inventer. Le prefill ne coûte que
    les tokens RÉELS (pas la taille allouée) → latence inchangée ; seul le
    KV-cache grandit, d'où le bornage par la RAM. Valeur PARTAGÉE
    _complete_one/warmup (via le builder) : un num_ctx différent ferait charger
    un runner distinct côté Ollama et perdrait le KV-cache préchauffé."""
    gb = _ram_total_gb()
    if gb >= 16:
        return 8192
    if gb >= 7.5:
        return 4096
    return 3072            # plancher ~4 Go : large pour garde-fous + dictée
    #                        longue, KV modéré (~0,18 Go pour un 3B)


def _ollama_chat_request(system, user, options, timeout):
    """Requête de reformulation Ollama /api/chat — builder UNIQUE partagé par la
    reformulation réelle (_complete_one) ET le préchauffage (warmup_engines) :
    même endpoint, même modèle (_ollama_warm_model), même keep_alive, même
    num_ctx, même structure de messages. Le KV-cache amorcé au warmup correspond
    ainsi PAR CONSTRUCTION au préfixe que la dictée enverra — plus de dérive
    silencieuse possible si l'endpoint ou la structure évolue. Seul `options`
    varie : reformulation {temperature, top_p} ; warmup {num_predict:1}. Retourne
    l'objet réponse requests brut (ou None si aucun modèle disponible)."""
    import requests
    model = _ollama_warm_model()
    if not model:
        return None
    opts = {"num_ctx": _llm_num_ctx()}
    opts.update(options)
    return requests.post(ollama_url() + "/api/chat", timeout=timeout, json={
        "model": model, "stream": False,
        "keep_alive": _llm_keep_alive(),
        "options": opts,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}]})


def _complete_one(provider, system, user, timeout):
    if provider == "anthropic":
        from anthropic import Anthropic
        client = Anthropic(api_key=get_api_key("anthropic") or None)
        msg = client.messages.create(
            model=_reform_model("anthropic") or "claude-haiku-4-5",
            max_tokens=400, system=system,
            messages=[{"role": "user", "content": user}])
        return next((b.text for b in msg.content if b.type == "text"), "").strip() or None
    import requests
    if provider == "ollama":
        # Reformuler n'est pas créer : température basse = sortie FIDÈLE au texte
        # dicté (moins de dérive, meilleure « qualité métier ») ET décodage plus
        # court/déterministe (convergence rapide vers la fin sur CPU sans GPU).
        # Gain temps ET qualité, aucun compromis. Requête via le builder PARTAGÉ
        # (mêmes octets que le préchauffage → KV-cache du préfixe système réutilisé).
        r = _ollama_chat_request(system, user,
                                 {"temperature": 0.3, "top_p": 0.9}, timeout)
        if r is None:
            return None
        r.raise_for_status()
        return (r.json()["message"]["content"] or "").strip() or None
    if provider in OPENAI_COMPAT:
        api_key = get_api_key(provider)
        if not api_key:
            return None
        r = requests.post(OPENAI_COMPAT[provider], timeout=timeout,
                          headers={"Authorization": f"Bearer {api_key}"},
                          json={"model": _reform_model(provider),
                                "messages": [{"role": "system", "content": system},
                                             {"role": "user", "content": user}]})
        r.raise_for_status()
        return (r.json()["choices"][0]["message"]["content"] or "").strip() or None
    return None


def llm_complete(system, user, timeout=9):
    """Complétion texte simple (None si aucun fournisseur/échec). Comme
    ask_llm : bascule sur le fournisseur suivant si le premier échoue.
    Sert à la couche 'neurale' : reformulation des messages, traduction."""
    now = time.time()
    order = provider_order()
    usable = [n for n in order
              if PROV_HEALTH.get(n, {}).get("until", 0) <= now] or order
    for provider in usable[:3]:
        try:
            out = _complete_one(provider, system, user, timeout)
            if out:
                return out
        except Exception as e:
            _mark_provider(provider, False, detail=_human_err(e),
                           cooldown=_cooldown_for(e))
    return None


# ponctuation vocale : « virgule », « point », « à la ligne »… (dictée)
_PUNCT_RULES = [
    (re.compile(r"\bnouveau paragraphe\b", re.I), "\n\n"),
    (re.compile(r"\bretour (?:a|à) la ligne\b", re.I), "\n"),
    (re.compile(r"\b(?:a|à) la ligne\b", re.I), "\n"),
    (re.compile(r"\bnouvelle ligne\b", re.I), "\n"),
    (re.compile(r"\bpoint d[' ]interrogation\b", re.I), "?"),
    (re.compile(r"\bpoint d[' ]exclamation\b", re.I), "!"),
    (re.compile(r"\bpoints? de suspension\b", re.I), "…"),
    (re.compile(r"\bpoint[- ]virgule\b", re.I), ";"),
    (re.compile(r"\bdeux[- ]points\b", re.I), ":"),
    (re.compile(r"\bouvre (?:la )?parenth[eè]se\b", re.I), "("),
    (re.compile(r"\bferme (?:la )?parenth[eè]se\b", re.I), ")"),
    (re.compile(r"\bvirgule\b", re.I), ","),
    (re.compile(r"\bpoint\b", re.I), "."),
]


def voice_punctuation(text):
    """« bonjour virgule ça va point à la ligne » → « bonjour, ça va.\\n »"""
    t = text
    for rx, rep in _PUNCT_RULES:
        t = rx.sub(rep, t)
    t = re.sub(r"\s+([,.;:!?…)])", r"\1", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"([(\n])[ \t]+", r"\1", t)
    t = re.sub(r"([.!?…]\s+|\n)([a-zà-ÿ])", lambda m: m.group(1) + m.group(2).upper(), t)
    return t


def format_rules(text):
    """Nettoyage par règles : toujours disponible, offline, sans IA."""
    t = re.sub(r"\s+", " ", text.strip())
    if not t:
        return t
    t = t[0].upper() + t[1:]
    if not re.search(r"[.!?…]$", t):
        t += "."
    return t


# Règles absolues de TOUTE reformulation, quel que soit le Style (intégré ou
# sur mesure) et le moteur (Intelligence privée locale ou Turbo). Préfixées à
# chaque appel par format_message — un Style n'a donc à décrire QUE sa forme.
COMMON_RULES = (
    "Tu transformes une dictée vocale brute en texte final prêt à coller. "
    "Règles absolues, par ordre de priorité : "
    "1) Tu reformules, tu ne réponds JAMAIS : une question dictée reste une "
    "question, un ordre dicté reste un ordre — sans réponse ni exécution. "
    "2) Zéro invention : aucun nom, chiffre, date ou détail absent de la "
    "dictée ; ne complète pas ce qui manque. "
    "3) Zéro perte : garde toutes les informations significatives (noms, "
    "montants, dates, conditions, liens). "
    "4) Auto-correction dictée (« à 14 h… non plutôt 15 h ») : ne garde que "
    "la version finale. "
    "5) Supprime hésitations (« euh », « bah », « hein »), tics vides "
    "(« genre », « du coup », « voilà » isolés), répétitions et faux départs. "
    "6) Écris nombres, heures, dates et montants proprement (14 h, 3 000 €, "
    "12 mars). "
    "7) Réponds dans la langue de la dictée, quelle qu'elle soit. "
    "8) Dictée déjà propre → corrige seulement ponctuation et majuscules ; "
    "dictée incompréhensible → renvoie-la simplement nettoyée, sans "
    "commentaire. "
    "Consigne du Style à appliquer : ")

_DEFAULT_REFORMULATE = (
    "Style Normal — rends la dictée claire, fluide et bien ponctuée, en "
    "respectant son ton et son niveau de langue, sans structure imposée.")


def _reform_system(system_prompt=None):
    """Prompt système de reformulation : COMMON_RULES (garde-fous) + consigne du
    Style + vocabulaire utilisateur + « réponds uniquement… ». Extrait pour être
    partagé par format_message_ex ET le préchauffage : le KV-cache amorcé au
    warmup correspond alors EXACTEMENT au préfixe que la reformulation enverra."""
    vocab = active_vocabulary()
    system = COMMON_RULES + (system_prompt or _DEFAULT_REFORMULATE) + " " + (
        f"Vocabulaire propre à l'utilisateur : {', '.join(vocab)}. " if vocab else "")
    return system + "Réponds UNIQUEMENT avec le texte reformulé, rien d'autre."


def format_message(text, system_prompt=None):
    """Moteur de reformulation générique, partagé par tous les modes du registre.

    `system_prompt` = consigne propre au mode choisi (Voice to text, E-mail,
    Prompt Engineer…). None → reformulation générique par défaut. COMMON_RULES
    (garde-fous : ne jamais répondre au contenu, zéro invention…) est préfixé
    dans tous les cas — y compris pour les Styles sur mesure. Le vocabulaire
    personnel de l'utilisateur est toujours injecté pour préserver les noms
    propres. Repli SANS IA (`format_rules`) si l'IA échoue ou est hors ligne :
    le curseur ne reçoit jamais du vide (garde-fou Phase 5b)."""
    return format_message_ex(text, system_prompt)[0]


def format_message_ex(text, system_prompt=None):
    """Comme `format_message`, mais dit AUSSI si le Style a réellement été
    appliqué : → (texte, ia_ok). Quand l'IA échoue (modèle absent, hors ligne,
    panne), l'appelant peut l'annoncer honnêtement au lieu d'afficher le Style
    comme si tout allait bien — le texte collé, lui, n'est jamais vide."""
    out = llm_complete(_reform_system(system_prompt), text)
    if out:
        return out, True
    log_err("style_fallback", "IA indisponible → collage format_rules (le "
            "Style demandé n'a pas été appliqué)")
    return format_rules(text), False


def translate_if_needed(text):
    lang = CFG.get("neural", {}).get("translate_to", "").strip()
    if not lang:
        return text
    out = llm_complete(
        f"Traduis le message suivant vers {lang}. Réponds UNIQUEMENT avec la traduction.",
        text)
    return out or text


# ------------------------------------------------- infos personnelles -------
# « mon adresse », « mon numéro de téléphone »… → valeurs préremplies du profil
# (Réglages > Profils). Substitution 100 % locale, jamais envoyée à une IA.

_PERSONAL_PATTERNS = [
    ("email",     re.compile(r"mon (?:adresse )?(?:e[- ]?mail|mail|courriel)", re.I)),
    # « mon adresse » mais PAS « mon adresse e-mail » (traité par le motif e-mail)
    ("adresse",   re.compile(r"mon adresse(?: postale)?(?!\s+(?:e[- ]?mail|mail|courriel))", re.I)),
    # « mon téléphone » / « mon numéro de téléphone » / « mon numéro » nu — mais
    # jamais « mon numéro de dossier/client/compte… » (numéro suivi d'un autre « de »)
    ("telephone", re.compile(r"mon t[ée]l[ée]phone|mon num[ée]ro de t[ée]l[ée]phone|mon num[ée]ro(?!\s+de\s+\w)", re.I)),
    ("prenom",    re.compile(r"mon pr[ée]nom", re.I)),
    ("nom",       re.compile(r"mon nom de famille", re.I)),
]


def personal_info():
    pid = CFG.get("active_profile", "")
    p = storage.get_profile(pid) if pid else None
    return (p or {}).get("personal", {}) or {}


def save_personal(info):
    """Enregistre les infos perso (« Mes infos » : prénom, nom, e-mail, tél,
    adresse) dans le profil actif. Utilisé par fill_personal (« mon adresse »
    → …), 100 % local. Le profil actif est garanti par le bootstrap au chargement."""
    pid = CFG.get("active_profile") or storage.ensure_default_profile()
    prof = storage.get_profile(pid) or {"id": pid, "name": "Profil 1"}
    prof["personal"] = {**(prof.get("personal") or {}), **(info or {})}
    storage.save_profile(prof)
    return prof["personal"]


def custom_variables():
    """« Custom Variables » façon Speechly : quand l'utilisateur dit `trigger`,
    on colle `value` (ex. « IBAN » → un RIB complet). Définies dans les Réglages,
    stockées dans la config (100 % local, JAMAIS envoyées à une IA).
    Retourne [(trigger, value)] nettoyé."""
    out = []
    raw = CFG.get("custom_vars", []) or []
    if not isinstance(raw, list):            # config éditée à la main → ignorée
        return out
    for v in raw:
        if not isinstance(v, dict):          # entrée malformée : sautée, pas fatale
            continue
        trig = str(v.get("trigger") or "").strip()   # str() : tolère nombres/None
        val = str(v.get("value") or "").strip()
        if trig and val:
            out.append((trig, val))
    return out


def save_custom_variables(items):
    """Enregistre la liste des Custom Variables (dédoublonnée sur le trigger,
    insensible à la casse). Retourne la liste propre effectivement stockée."""
    clean, seen = [], set()
    for it in items or []:
        trig = (it.get("trigger") or "").strip()
        val = (it.get("value") or "").strip()
        key = trig.lower()
        if trig and val and key not in seen:
            seen.add(key)
            clean.append({"trigger": trig, "value": val})
    save_config({"custom_vars": clean})
    return clean


def clean_tokens(toks):
    """Repères utilisateur → liste de chaînes non vides, chacune rognée. Accepte
    une chaîne nue (→ [chaîne]) ; toute autre valeur non itérable-de-tokens
    (int, dict…) → []. Source UNIQUE du nettoyage des mots-clés (mode
    Automatique + modes sur mesure). Défensif : ne lève jamais sur une config
    éditée à la main."""
    if isinstance(toks, str):
        toks = [toks]
    if not isinstance(toks, (list, tuple, set)):
        return []
    return [s for t in toks if (s := str(t).strip())]


def save_custom_modes(items):
    """Modes sur mesure (palier Ultra) : [{id?, name, match, prompt}]. Nettoie,
    dédoublonne sur l'id et persiste — source UNIQUE de la validation du schéma
    (tray + dock). Retourne la liste propre effectivement stockée."""
    clean, seen = [], set()
    for cm in items or []:
        try:
            name = str(cm.get("name") or "").strip()[:40]
            match = clean_tokens(cm.get("match"))
            prompt = str(cm.get("prompt") or "").strip()
        except Exception:
            continue
        if not (name and match and prompt):
            continue
        cid = str(cm.get("id") or "").strip() or uuid.uuid4().hex[:8]
        while cid in seen:                       # collision d'id → nouvel id
            cid = uuid.uuid4().hex[:8]
        seen.add(cid)
        clean.append({"id": cid, "name": name, "match": match, "prompt": prompt})
    save_config({"custom_modes": clean})
    return clean


def _cloud_licensed():
    """Le palier autorise-t-il le STT cloud ? Défensif : si licensing est
    indisponible (dormant/erreur), on n'ajoute aucune restriction."""
    try:
        import licensing
        return licensing.has("cloud_stt")
    except Exception:
        return True


def fill_personal(text, custom_vars=True):
    """Substitution locale : champs de profil (« mon adresse » → …) PUIS Custom
    Variables utilisateur. Tout se fait AVANT tout envoi IA, jamais transmis.

    `custom_vars=False` n'applique QUE les champs de profil (fonction de base,
    non facturée) — les Custom Variables sont un palier Pro, gaté par l'appelant.
    """
    if not text:
        return text
    info = personal_info()
    for key, rx in _PERSONAL_PATTERNS:
        val = (info.get(key) or "").strip()
        if val:
            text = rx.sub(lambda _m, v=val: v, text)
    # informations personnalisées (« Mes infos » extensibles) : même statut que
    # les champs fixes (fonction de base, non gatée) — mêmes frontières
    # conditionnelles que les Custom Variables ci-dessous.
    for e in (info.get("extra") or []):
        if not isinstance(e, dict):
            continue
        trig = str(e.get("label") or "").strip()
        val = str(e.get("value") or "").strip()
        if not trig or not val:
            continue
        left = r"(?<!\w)" if _is_word_char(trig[:1]) else ""
        right = r"(?!\w)" if _is_word_char(trig[-1:]) else ""
        text = re.sub(left + re.escape(trig) + right,
                      lambda _m, v=val: v, text, flags=re.IGNORECASE)
    if not custom_vars:
        return text
    for trig, val in custom_variables():
        # Frontières conditionnelles : on n'exige un bord « mot » que si le
        # trigger COMMENCE / FINIT par un caractère de mot. Sinon un trigger à
        # ponctuation (« c.a. », « @perso », « n° ») ne matcherait jamais avec un
        # simple \b\b. Pour un mot normal (« IBAN »), cela reste équivalent à
        # \bIBAN\b (« ribambelle » exclu). Casse ignorée ; lambda pour ne pas
        # interpréter \1, \\ dans la valeur collée.
        left = r"(?<!\w)" if _is_word_char(trig[:1]) else ""
        right = r"(?!\w)" if _is_word_char(trig[-1:]) else ""
        text = re.sub(left + re.escape(trig) + right,
                      lambda _m, v=val: v, text, flags=re.IGNORECASE)
    return text


def _is_word_char(ch):
    return bool(ch) and (ch.isalnum() or ch == "_")


# ------------------------------------------- plusieurs demandes d'un coup ---

_MULTI_SPLIT = re.compile(
    r"\s+(?:et puis|et ensuite|et apr[eè]s(?: [cç]a)?|puis|ensuite)\s+|\s+et\s+",
    re.IGNORECASE)
_ACTION_VERBS = {
    "ouvre", "ouvres", "lance", "mets", "met", "joue", "ferme", "cherche",
    "recherche", "envoie", "appelle", "note", "rappelle", "monte", "baisse",
    "coupe", "verrouille", "eteins", "allume", "ecris", "tape", "fais",
    "demarre", "affiche", "va", "emmene", "ajoute", "annule", "prends",
    "dis", "cree", "augmente", "diminue", "passe", "remets", "reprends",
    "arrete", "descends", "montre", "donne", "regle", "programme",
    "previens", "verifie", "traduis", "calcule", "active", "desactive",
    "relance", "redemarre", "capture", "colle", "copie", "enregistre",
    "change", "bascule", "souviens", "reduis", "agrandis",
}


# hésitations à l'oral : retirées avant analyse (« euh ouvre euh youtube »)
_FILLER_SPEECH = re.compile(r"\b(?:euh+|heu+|hum+|hmm+|bah|hein)\b[, ]*", re.IGNORECASE)


def clean_speech(text):
    t = _FILLER_SPEECH.sub(" ", text or "")
    t = re.sub(r"\s{2,}", " ", t).strip(" ,")
    return t or text


# une automatisation ne se déclenche que si sa phrase couvre TOUTE la demande
_FILLER_WORDS = {"nova", "stp", "svp", "s'il", "te", "vous", "plait", "merci",
                 "maintenant", "vite", "donc", "alors"}

# préfixes de politesse retirés avant les règles rapides : « est-ce que tu
# peux ouvrir youtube » reste instantané au lieu de partir vers l'IA
_POLITE_PREFIXES = tuple(sorted((
    "nova ", "nova, ", "ok nova ", "dis nova ",
    "s'il te plait ", "s'il vous plait ", "stp ", "svp ",
    "est-ce que ", "est ce que ", "merci de ", "merci d'",
    "peux-tu ", "peux tu ", "pourrais-tu ", "pourrais tu ",
    "veux-tu ", "veux tu ", "veux-tu bien ",
    "tu peux ", "tu pourrais ", "tu veux bien ", "tu veux ",
    "j'aimerais que tu ", "je veux que tu ", "je voudrais que tu ",
    "il faut que tu ", "il faudrait que tu ",
    "j'aimerais ", "je voudrais ", "je veux ",
), key=len, reverse=True))


def strip_politeness(n):
    """« est-ce que tu peux ouvrir youtube » → « ouvrir youtube ».
    Répète tant qu'un préfixe matche (les formules s'empilent à l'oral)."""
    changed = True
    while changed:
        changed = False
        for p in _POLITE_PREFIXES:
            if n.startswith(p) and len(n) > len(p) + 2:
                n = n[len(p):].lstrip(" ,")
                changed = True
    return n


def matches_phrase(phrase_n, n):
    """True si la demande n correspond à la phrase (politesse tolérée).
    « ouvre les paramètres de l'écran » ne déclenche PAS « ouvre les
    paramètres » : la demande plus précise doit suivre son vrai chemin."""
    if not phrase_n:
        return False
    if phrase_n == n:
        return True
    if phrase_n in n:
        rest = n.replace(phrase_n, " ", 1).split()
        if all(w in _FILLER_WORDS for w in rest):
            return True
    np = strip_politeness(n)
    return np != n and matches_phrase(phrase_n, np)


def split_multi(text):
    """« ouvre youtube et mets un minuteur » → ["ouvre youtube", "mets un minuteur"].
    On ne coupe que si CHAQUE morceau commence par un verbe d'action connu,
    pour ne pas casser « dis à paul que j'arrive et que je serai en retard »."""
    parts = [p.strip(" ,.!?") for p in _MULTI_SPLIT.split(text)
             if p and p.strip(" ,.!?")]
    if len(parts) < 2:
        return None
    for p in parts:
        first = normalize(p).split(" ", 1)[0]
        # « montre-moi », « donne-nous » : le pronom collé ne change pas le verbe
        first = re.sub(r"-(?:moi|nous|toi|le|la|les|y|en)$", "", first)
        if first not in _ACTION_VERBS:
            return None
    return parts


# ------------------------------------------------------------- STT router ---

def active_vocabulary():
    pid = CFG.get("active_profile", "")
    p = storage.get_profile(pid) if pid else None
    return (p or {}).get("vocabulary", [])


def stt_prompt():
    """Amorce Whisper avec les mots que Nova doit reconnaître à coup sûr.

    Ordre = du plus PERSONNEL au plus générique, pour que rien d'irremplaçable
    ne soit tronqué par le plafond : contacts, automatisations et vocabulaire du
    profil d'abord ; puis verbes de commande (orientent la reconnaissance ET
    l'intention) ; puis noms propres d'applis/sites tirés des tables de modes.py
    (que Whisper déforme souvent) ; puis quelques villes pour la navigation.
    Mesuré (bench_stt.py) : +1 à +2 intentions et WER en nette baisse sur le
    chemin commande, pour une latence quasi inchangée."""
    perso = []
    try:
        # tout l'accès stockage sous garde : stt_prompt est appelé par le
        # dernier recours local (transcribe) — une panne DB ne doit jamais
        # tuer la dictée, juste renvoyer une amorce sans vocabulaire perso
        perso = list(active_vocabulary())
        perso += [a["name"] for a in get_automations()][:12]
        pid = CFG.get("active_profile", "")
        p = storage.get_profile(pid) if pid else None
        perso += [c.get("name", "") for c in (p or {}).get("contacts", [])][:12]
    except Exception as e:
        log_err("stt_prompt_perso", e)

    generic = ["Nova", "ouvre", "lance", "mets", "joue", "appelle", "envoie",
               "rappelle", "monte", "baisse", "allume", "éteins", "va à",
               "cherche", "note", "minuteur", "volume", "écran",
               "regarde mon écran"]
    generic += ["YouTube", "Spotify", "Deezer", "Netflix", "WhatsApp", "Gmail",
                "Google Maps", "Chrome", "Word", "Excel", "Notion", "Slack"]
    generic += ["Paris", "Lyon", "Marseille", "Bordeaux", "gare de Lyon"]

    seen, out = set(), []
    for w in perso + generic:
        w = (w or "").strip()
        if w and w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    s = ", ".join(out)
    if len(s) > 520:                       # coupe sur une frontière d'item, pas en plein mot
        s = s[:520].rsplit(", ", 1)[0]
    return s


class LiveTranscriber:
    """Transcription AU FIL de la parole — le gros levier de latence sur un PC
    sans GPU. Pendant que la touche est tenue, chaque tranche terminée (pause
    de voix d'environ une demi-seconde) est transcrite en arrière-plan et
    « committée » ; à la relâche, seule la traîne reste à transcrire : la
    latence ressentie ne dépend plus de la longueur de la dictée.

    Défensif de bout en bout (« jamais de plantage ») : au moindre pépin le
    fil se marque cassé et finish() rend None — l'appelant repasse alors par
    la transcription intégrale classique, sur le MÊME audio complet, avec le
    MÊME résultat qu'avant. Les tests injectent `_transcribe` et appellent
    `_commit` directement (start=False) : la logique de découpe est pure."""

    MIN_COMMIT_S = 2.4       # tranche mini avant commit (évite les miettes)
    PAUSE_BLOCKS = 5         # ~0,5 s sous le seuil de voix = fin de tranche

    def __init__(self, frames, lock, on_partial=None):
        self._frames, self._lock = frames, lock
        self._on_partial = on_partial
        self._transcribe = transcribe     # les tests shadowent cet attribut
        self._done = 0                    # nb de blocs déjà committés
        self._epoch = _MIC_EPOCH["n"]     # détecte une reprise micro (tampon jeté)
        # lexique figé UNE fois pour la session (noms propres, contacts,
        # automations), invariant pendant la dictée. Calculé PARESSEUSEMENT au
        # 1er commit (fil de fond), JAMAIS dans __init__ : ce constructeur tourne
        # sur le fil d'appui de la touche, AVANT l'ouverture du micro — y lire le
        # profil + commands.json + la base contacts retarderait les tout premiers
        # phonèmes (même discipline que stt_live_enabled, non bloquant à l'appui).
        self._lex = None
        self._parts = []
        self.broken = False
        self._stop = threading.Event()
        self._th = None

    def start(self):
        """Démarre la boucle de fond (séparé du constructeur : les tests
        exercent la logique de découpe sans thread)."""
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    # --- boucle de fond -----------------------------------------------------
    def _loop(self):
        try:
            while not self._stop.wait(0.3):
                self._commit(final=False)
        except Exception as e:
            log_err("stt_live", e)
            self.broken = True

    def _pending(self):
        with self._lock:
            total = len(self._frames)
            if total < self._done or self._epoch != _MIC_EPOCH["n"]:
                # le tampon a été VIDÉ par record_audio (reprise micro) —
                # l'époque le dit même quand un commit lent a raté la fenêtre
                # où le tampon était encore plus court que _done. Le texte
                # committé décrit de l'audio disparu → on se marque cassé,
                # l'appelant repassera par la transcription intégrale du
                # nouvel enregistrement.
                self.broken = True
                return [], total
            return self._frames[self._done:], total

    def _commit(self, final):
        pending, total = self._pending()
        if not pending:
            return
        # Le commit FINAL transcrit TOUJOURS la traîne : aucun minimum, aucune
        # garde de silence. Une fin de phrase murmurée (sous le seuil) ne doit
        # pas être jetée sans repli, car finish() rendrait alors un texte non
        # vide et l'appelant ne repasserait pas par la transcription intégrale.
        # Les gardes ci-dessous ne concernent donc QUE les commits intermédiaires
        # (calcul de seuil et de RMS au court-circuit, jamais sur le final).
        if not final:
            # trop court : on rend la main sans même calculer les RMS
            if 0.1 * len(pending) < self.MIN_COMMIT_S + 0.1 * self.PAUSE_BLOCKS:
                return
            thr = effective_threshold()
            # la voix doit s'être tue sur les derniers blocs (sinon on
            # couperait un mot) — court-circuit dès le premier bloc encore voisé
            if any(_rms(b) > thr for b in pending[-self.PAUSE_BLOCKS:]):
                return
            # tranche SANS aucune voix (touche tenue en réfléchissant) : on
            # avance le curseur sans payer d'inférence toutes les ~3 s ni
            # risquer l'écho-hallucination (le moteur, amorcé par le texte
            # committé, le répète volontiers sur du souffle → re-committé en
            # boule de neige)
            if not any(_rms(b) > thr for b in pending):
                self._done = total
                return
        audio = np.concatenate(pending).flatten()
        # amorce : le lexique utilisateur d'abord (figé en session, il ne doit
        # JAMAIS disparaître après la 1re tranche), puis le texte déjà committé
        # (ponctuation et contexte). Whisper conserve la QUEUE de l'amorce : le
        # lexique en tête + le contexte récent en fin tiennent dans les 224 tk.
        if self._lex is None:              # lu UNE fois, ici (fil de fond)
            self._lex = (stt_prompt() or "").strip()[:128]
        ctx = " ".join(self._parts)[-320:]
        prompt = (self._lex + " " + ctx).strip() or None
        txt = self._transcribe(audio, prompt)
        self._done = total
        if txt:
            self._parts.append(txt)
            # jamais d'aperçu APRÈS la fin (stop/finish posés) : la bulle est
            # déjà passée à « Un instant… » ou à l'erreur — un aperçu tardif
            # la renverrait à « écoute » alors que le micro est fermé
            if self._on_partial and not final and not self._stop.is_set():
                try:
                    self._on_partial(" ".join(self._parts))
                except Exception:
                    pass

    # --- fin de dictée ------------------------------------------------------
    def stop(self):
        """Arrêt SANS transcription finale (rien entendu, annulation) : la
        traîne serait jetée, inutile de payer une inférence pour elle."""
        self._stop.set()

    def finish(self):
        """→ texte complet (tranches committées + traîne), ou None si le fil a
        cassé — l'appelant retombe alors sur la transcription classique.
        Ne lève JAMAIS : c'est son contrat, l'appelant n'a qu'un seul chemin
        d'erreur (le repli intégral)."""
        try:
            self._stop.set()
            if self._th is not None:
                self._th.join(timeout=30)
                if self._th.is_alive():    # transcription de fond figée
                    return None
            if self.broken:
                return None
            self._commit(final=True)
            if self.broken:                # rétrécissement vu par le commit
                return None
            return " ".join(self._parts).strip()
        except Exception as e:
            log_err("stt_live", e)
            return None


def stt_live_enabled():
    """La transcription en continu est-elle pertinente ? Opt-out via réglages ;
    inutile sur GPU (déjà quasi instantané) et contre-productive avec Turbo
    (un aller-retour réseau par tranche) — mais seulement si Turbo est
    JOIGNABLE : hors ligne, transcribe_routed retombera en local, autant
    garder le live. Appelée à l'APPUI de la touche, elle ne doit JAMAIS
    bloquer : ni sonde réseau (drapeau mémorisé), ni résolution GPU (imports
    + nvidia-smi peuvent prendre des secondes alors que le micro n'est pas
    encore ouvert — les premiers mots seraient perdus)."""
    stt = CFG.get("stt") or {}
    if stt.get("live", True) is False:
        return False
    if stt.get("cloud_enabled") and _cloud_licensed():
        try:
            import integrations
            if integrations.is_online():
                return False
        except Exception:
            # sonde de connectivité indisponible : on NE désactive PAS le live
            # (la docstring l'exige — hors ligne, le local sert de toute façon).
            # On retombe sur la décision par device juste en dessous.
            pass
    try:
        if not _DEVICE["device"]:
            # device pas encore résolu (tout début de session) : on suppose
            # CPU → live actif. La résolution se fera dans le FIL du live,
            # jamais sur le chemin de l'appui.
            return True
        return _DEVICE["device"] != "cuda"
    except Exception:
        return True


def _seq_exclusive():
    """Mémoire séquentielle sur petite RAM : le STT et le LLM de reformulation ne
    doivent JAMAIS coexister en mémoire. Vrai quand seq_memory est demandé ET que
    le STT n'est pas gardé chaud (RAM contrainte, ~4-7 Go). Source UNIQUE de cet
    invariant : la dictée décharge le STT avant le LLM (_ptt_session) ET le
    préchauffage n'épingle pas le LLM (_should_warm_llm) sur exactement ce prédicat."""
    return bool(CFG.get("seq_memory")) and not stt_keep_warm()


def _should_warm_llm():
    """Faut-il préchauffer le LLM de reformulation au démarrage ? OUI seulement là
    où il peut rester résident sans danger. En mémoire séquentielle sur petite RAM,
    y épingler le LLM romprait l'invariant : la 1re transcription chargerait le STT
    alors que le LLM (~2 Go) est encore résident (keep_alive) → swap/OOM, l'exact
    inverse du but du préchauffage."""
    if _seq_exclusive():
        return False
    return resolve_provider() == "ollama"


def warmup_engines():
    """Préchauffe ce que la PREMIÈRE dictée de la session utilisera : le choix
    GPU/CPU (memoïsé — il ne doit jamais rester à faire à l'appui de touche),
    le moteur de transcription (si « gardé en mémoire ») et le modèle de
    reformulation local — le MÊME que la reformulation chargera réellement
    (_ollama_warm_model), et seulement si le fournisseur résolu est bien le
    moteur local : sinon on chargerait des giga-octets pour rien (fournisseur
    cloud ou désactivé). Appelé en arrière-plan au démarrage : la première
    dictée devient aussi rapide que les suivantes. Best-effort, jamais
    bloquant."""
    try:
        _resolve_device()
    except Exception as e:
        log_err("warmup_device", e)
    try:
        if stt_keep_warm():
            get_model()
            # Réchauffe aussi le CHEMIN de 1re inférence, pas seulement les poids :
            # le modèle VAD Silero se charge PARESSEUSEMENT au 1er transcribe() et
            # CTranslate2 fait son init runtime au 1er appel. Une transcription muette
            # jetée paie ce coût au démarrage (~100-400 ms) au lieu de la 1re dictée.
            # Buffer de zéros, résultat ignoré → texte STRICTEMENT identique (aucun
            # paramètre de décodage réel changé). Uniquement quand le modèle est
            # gardé chaud (RAM confortable) → sans coût mémoire.
            transcribe(np.zeros(16000, dtype=np.float32))
    except Exception as e:
        log_err("warmup_stt", e)
    try:
        if _should_warm_llm():
            # Préchauffe via le builder PARTAGÉ (mêmes endpoint/modèle/keep_alive/
            # num_ctx/préfixe système que la reformulation réelle) : charge le
            # modèle ET amorce le KV-cache du préfixe système constant (~250
            # tokens). Ollama réutilise ce préfixe (plus-long-préfixe-commun, tant
            # que keep_alive tient), donc la 1re dictée saute son pré-remplissage
            # (~0,5-1 s gagnées sur CPU). num_predict=1 : réponse jetée, le vrai
            # appel de reformulation reste inchangé → texte STRICTEMENT identique.
            _ollama_chat_request(_reform_system(), "ok", {"num_predict": 1}, 180)
    except Exception as e:
        # service local ABSENT (pas installé / pas lancé) : condition ATTENDUE
        # sur une machine neuve — une ligne sobre au lieu d'un traceback
        # complet à chaque démarrage. L'installation guidée vit dans les
        # Réglages (engine_setup) ; en attendant, les Styles retombent sur le
        # collage brut (format_rules) comme toujours. (requests est importé
        # paresseusement dans ce module → détection par le nom de la classe.)
        if "ConnectionError" in type(e).__name__:
            log_err("warmup_llm", "reformulation locale indisponible (service "
                                  "absent) — installation via les Réglages")
        else:
            log_err("warmup_llm", e)


def transcribe_routed(audio, fast=False):
    """Local par défaut ; Groq cloud si opt-in + en ligne + clé.
    Un échec cloud retombe TOUJOURS sur le local. fast = commandes courtes.
    Retourne (texte, moteur)."""
    import integrations
    stt_cfg = CFG.get("stt") or {}            # tolère "stt": null (config éditée)
    if (stt_cfg.get("cloud_enabled") and _cloud_licensed()
            and integrations.is_online()):
        try:
            # clé personnelle présente (dev/avancé) → Groq en direct ;
            # sinon relais Nova : jeton de licence + fair-use côté serveur
            _cloud_fn = (integrations.groq_transcribe
                         if winext.has_secret("groq")
                         else integrations.turbo_transcribe)
            text = _cloud_fn(
                audio, language=_stt_language(),
                model=stt_cfg.get("cloud_model", "whisper-large-v3-turbo"),
                prompt=stt_prompt())
            if text and text.strip():
                return text, "cloud"
            # réponse vide OU blanche (coupure réseau silencieuse, quota, audio
            # non reconnu → Groq renvoie parfois " "/"\n") : on retombe sur le
            # local plutôt que de coller un résultat vide.
        except Exception as e:
            log_err("stt_cloud", e)
    if fast and len(audio) < 16000 * 8:
        try:
            if gpu_active():
                # GPU : le gros modèle « small » beam 5 est quasi instantané →
                # précision maximale (11-12/12) même pour une commande rapide
                return transcribe(audio), "local-gpu"
            # CPU : le modèle d'éveil en beam 3 atteint la précision du gros
            # modèle pour ~2,6 s au lieu de ~9,5 s (le précis reste pour la dictée)
            t = transcribe_quick(audio, prompt=stt_prompt(), beam=3)
            if t:
                return t, "local-rapide"
        except Exception as e:
            log_err("stt_wake", e)
    # chemin local principal sous garde : transcribe() peut lever (TimeoutError
    # si un worker de fond tient le verrou > 120 s, modèle corrompu…). Sans ce
    # try, l'exception remontait à _ptt_session → « Erreur — réessaie » et tout
    # l'audio était jeté. On rend un texte vide → l'appelant affiche « Je n'ai
    # pas compris » (dégradé propre), sans perdre le contrôle.
    try:
        return transcribe(audio), "local"
    except Exception as e:
        log_err("stt_local", e)
        return "", "local"

