# -*- coding: utf-8 -*-
"""
Coeur de l'assistant : config, notes, automatisations, voix (Whisper),
fournisseurs d'IA (Anthropic / OpenAI / Gemini / DeepSeek / Ollama),
analyse du PC et gestion des modèles locaux.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.parse
import uuid
import webbrowser

import numpy as np

import storage
import winext

APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))

DEFAULT_CONFIG = {
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
    "provider": "auto",   # auto | anthropic | openai | gemini | deepseek | ollama | off
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

_lock = threading.Lock()


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
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def log_err(context, err):
    """Journal d'erreurs (nova.log à côté de l'exe) : les pannes silencieuses
    de l'écoute continue ou du chargement des modèles deviennent visibles."""
    try:
        with open(_path("nova.log"), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {context}: {err}\n")
    except Exception:
        pass


# ------------------------------------------------------------------ config --

CFG = _merge(DEFAULT_CONFIG, _load("config.json", {}))


def save_config(new_cfg):
    global CFG
    CFG = _merge(CFG, new_cfg)
    _save("config.json", CFG)
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


def _resolve_device():
    """(device, compute_type), mémorisé. Préférence via CFG['stt']['device'] :
    'auto' (défaut) / 'cuda' / 'cpu'. 'auto' prend le GPU s'il est présent."""
    if _DEVICE["device"]:
        return _DEVICE["device"], _DEVICE["compute"]
    pref = (CFG.get("stt", {}) or {}).get("device", "auto")
    if pref in ("auto", "cuda", "gpu"):
        _setup_cuda_dll_path()
        try:
            import ctranslate2
            if ctranslate2.get_cuda_device_count() > 0:
                _DEVICE.update(device="cuda", compute="float16")
                return _DEVICE["device"], _DEVICE["compute"]
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
    dev, comp = _resolve_device()
    if dev == "cuda":
        try:
            return WhisperModel(name, device="cuda", compute_type=comp)
        except Exception as e:
            log_err("gpu_load", e)
            _DEVICE.update(device="cpu", compute="int8")   # bascule CPU pour de bon
    return WhisperModel(name, device="cpu", compute_type="int8")


def get_model():
    global _model
    with _model_lock:
        if _model is None:
            _model_state["status"] = "chargement…"
            try:
                _model = _load_whisper(CFG["whisper_model"])
                _model_state["status"] = "prêt (%s)" % _DEVICE["device"].upper()
            except Exception as e:
                _model_state["status"] = f"erreur : {e}"
                raise
    return _model


def model_status():
    return _model_state["status"]


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


def record_audio(on_level=None, frames_out=None, frames_lock=None, cancel=None,
                 end_silence=None, min_voiced=0.0):
    """Enregistre jusqu'au silence. on_level(rms) est appelé à chaque bloc (pour
    l'animation) ; frames_out/frames_lock permettent la transcription partielle
    live ; cancel (threading.Event) interrompt et renvoie None (clic ailleurs) ;
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
                block, _ = stream.read(int(sr * 0.1))
                if frames_lock:
                    with frames_lock:
                        frames.append(block.copy())
                else:
                    frames.append(block.copy())
                rms = float(np.sqrt(np.mean(block ** 2)))
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
        frames.clear()
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


def transcribe(audio):
    prompt = stt_prompt() or None
    with transcribe_lock:
        segments, _info = get_model().transcribe(
            audio, language=CFG["language"], beam_size=5, vad_filter=True,
            initial_prompt=prompt)
        return " ".join(s.text for s in segments).strip()


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
            audio, language=CFG["language"], beam_size=beam, vad_filter=True,
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
        return "Clé API invalide ou non autorisée"
    if code == 404:
        return "Modèle introuvable, vérifiez son nom"
    if code == 429:
        return "Quota atteint (niveau gratuit ?), réessayez plus tard ou changez de modèle"
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


def _complete_one(provider, system, user, timeout):
    prov = CFG["providers"]
    if provider == "anthropic":
        from anthropic import Anthropic
        client = Anthropic(api_key=get_api_key("anthropic") or None)
        msg = client.messages.create(
            model=prov["anthropic"]["model"] or "claude-haiku-4-5",
            max_tokens=400, system=system,
            messages=[{"role": "user", "content": user}])
        return next((b.text for b in msg.content if b.type == "text"), "").strip() or None
    import requests
    if provider == "ollama":
        model = prov["ollama"]["model"] or ((ollama_models() or [""])[0])
        if not model:
            return None
        r = requests.post(ollama_url() + "/api/chat", timeout=timeout, json={
            "model": model, "stream": False,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]})
        r.raise_for_status()
        return (r.json()["message"]["content"] or "").strip() or None
    if provider in OPENAI_COMPAT:
        api_key = get_api_key(provider)
        if not api_key:
            return None
        r = requests.post(OPENAI_COMPAT[provider], timeout=timeout,
                          headers={"Authorization": f"Bearer {api_key}"},
                          json={"model": prov[provider]["model"],
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


def format_message(text):
    """Reformate un message dicté (ponctuation, majuscules) — IA si dispo."""
    vocab = active_vocabulary()
    out = llm_complete(
        "Tu reformates des messages dictés à la voix. Corrige ponctuation et majuscules, "
        "garde le sens exact, reste bref. "
        + (f"Vocabulaire propre à l'utilisateur : {', '.join(vocab)}. " if vocab else "")
        + "Réponds UNIQUEMENT avec le message reformulé, rien d'autre.",
        text)
    return out or format_rules(text)


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
    ("adresse",   re.compile(r"mon adresse(?: postale)?", re.I)),
    ("telephone", re.compile(r"mon num[ée]ro(?: de t[ée]l[ée]phone)?|mon t[ée]l[ée]phone", re.I)),
    ("prenom",    re.compile(r"mon pr[ée]nom", re.I)),
    ("nom",       re.compile(r"mon nom de famille", re.I)),
]


def personal_info():
    pid = CFG.get("active_profile", "")
    p = storage.get_profile(pid) if pid else None
    return (p or {}).get("personal", {}) or {}


def fill_personal(text):
    if not text:
        return text
    info = personal_info()
    if not info:
        return text
    for key, rx in _PERSONAL_PATTERNS:
        val = (info.get(key) or "").strip()
        if val:
            text = rx.sub(val, text)
    return text


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
    perso = list(active_vocabulary())
    try:
        perso += [a["name"] for a in get_automations()][:12]
        pid = CFG.get("active_profile", "")
        p = storage.get_profile(pid) if pid else None
        perso += [c.get("name", "") for c in (p or {}).get("contacts", [])][:12]
    except Exception:
        pass

    generic = ["Nova", "ouvre", "lance", "mets", "joue", "appelle", "envoie",
               "rappelle", "monte", "baisse", "allume", "éteins", "va à",
               "cherche", "note", "minuteur", "volume", "écran",
               "regarde mon écran"]
    try:                                   # import paresseux : modes.py importe core
        import modes
        generic += list(modes.SITES)[:24]  # youtube, gmail, maps, spotify, netflix…
        generic += list(modes.APPS)[:12]   # bloc-notes, calculatrice, word, excel…
    except Exception:
        generic += ["YouTube", "Spotify", "Deezer", "Netflix", "WhatsApp",
                    "Gmail", "Google Maps", "Chrome"]
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


def transcribe_routed(audio, fast=False):
    """Local par défaut ; Groq cloud si opt-in + en ligne + clé.
    Un échec cloud retombe TOUJOURS sur le local. fast = commandes courtes.
    Retourne (texte, moteur)."""
    import integrations
    if (CFG.get("stt", {}).get("cloud_enabled") and winext.has_secret("groq")
            and integrations.is_online()):
        try:
            text = integrations.groq_transcribe(
                audio, language=CFG["language"],
                model=CFG["stt"].get("cloud_model", "whisper-large-v3-turbo"),
                prompt=stt_prompt())
            return text, "cloud"
        except Exception:
            pass
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
        except Exception:
            pass
    return transcribe(audio), "local"


# --------------------------------------------------------------- exécution --

# commandes shell manifestement destructrices : jamais exécutées, même si l'IA les propose
_SHELL_BLOCK = re.compile(
    r"format\s+[a-z]:|del\s+/[fsq]|erase\s+/[fsq]|rmdir\s+/s|\brd\s+/s|rm\s+-rf"
    r"|diskpart|cipher\s+/w|vssadmin\s+delete|bcdedit|mkfs|dd\s+if="
    r"|reg\s+delete\s+hk(lm|ey_local_machine)|remove-item\s+.*-recurse"
    r"|shutdown\s+/s\s+/t\s+[0-5]\b",   # arrêt immédiat : réservé au mode power confirmé
    re.IGNORECASE)


def shell_blocked(cmd):
    return bool(_SHELL_BLOCK.search(cmd or ""))


def _auto_pause(prev, cur):
    """Pause implicite quand l'IA a oublié le wait entre une ouverture
    (app, page, commande) et une frappe clavier : l'app doit avoir le focus."""
    return 1.5 if prev in ("open_app", "open_url", "shell") \
        and cur in ("type_text", "keys") else 0.0


def _timer_web_path(seconds):
    secs = int(seconds)
    return f"{secs // 60}minutes" if secs >= 60 and secs % 60 == 0 \
        else f"{secs}seconds"


def start_timer(seconds, label=""):
    """Minuteur : moteur interne (alerte vocale prioritaire, annulation,
    liste) + compte à rebours VISIBLE dans un onglet (les vraies applis du
    PC en priorité — réglage timer_style)."""
    import timers as _timers
    tid = _timers.start(seconds, label)
    if CFG.get("timer_style", "web") == "web":
        try:
            webbrowser.open("https://e.ggtimer.com/" + _timer_web_path(seconds))
        except Exception as e:
            log_err("timer web", e)
    return tid


def execute_steps(steps, spoken=""):
    """Exécute la séquence d'actions renvoyée par l'IA.
    Retourne (réussies, total, motif_de_blocage)."""
    import timers as _timers
    done = 0
    prev = None
    for s in steps:
        a = s.get("action")
        target = (s.get("target") or "").strip()
        args = (s.get("args") or "").strip()
        pause = _auto_pause(prev, a)
        if pause:
            time.sleep(pause)
        prev = a
        try:
            if a == "type_text":
                import keyboard
                time.sleep(0.15)
                keyboard.write(fill_personal(target), delay=0.004)
            elif a == "media":
                if not winext.send_media_key(target):
                    continue
            elif a == "timer":
                secs = _timers.parse_duration(target)
                if not secs:
                    continue
                start_timer(secs, args)
            elif a == "wait":
                try:
                    time.sleep(min(8.0, max(0.0, float(str(target).replace(",", ".")))))
                except ValueError:
                    continue
            elif a == "shell":
                if shell_blocked(target):
                    return done, len(steps), "Commande refusée par sécurité"
                subprocess.Popen(target, shell=True)
            elif a == "note":
                add_note(target)
            elif a == "fact":
                if target.strip():
                    storage.add_fact(target.strip())
            elif a == "home":
                import modes as _modes
                if not _modes.home_step(target, args):
                    continue
            elif a in ("file_rename", "file_move"):
                import files_mode as _fm
                src = _fm.find_file(target)
                fn = _fm.safe_rename if a == "file_rename" else _fm.safe_move
                if not src or not fn(src, args):
                    continue
            elif a in ("open_url", "open_app", "web_search", "keys"):
                if not execute({"action": a, "target": target, "args": args, "text": spoken}):
                    continue
            else:
                continue
            done += 1
        except Exception as e:
            log_err(f"step {a}", e)
    return done, len(steps), ""

def execute(action):
    a = action.get("type") or action.get("action")
    target = (action.get("target") or "").strip()
    args = (action.get("args") or "").strip()
    if a == "open_url":
        if not target.lower().startswith(("http://", "https://")):
            target = "https://" + target
        webbrowser.open(target)
    elif a == "open_app":
        if args:
            subprocess.Popen(f'start "" "{target}" {args}', shell=True)
        else:
            try:
                os.startfile(target)
            except OSError:
                subprocess.Popen(f'start "" "{target}"', shell=True)
    elif a == "web_search":
        webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(target))
    elif a == "keys":
        t = target.replace("windows", "win").strip().lower()
        if t.replace(" ", "") == "win+l":
            # Win+L simulé est filtré par Windows (sécurité) : appel natif
            import ctypes
            ctypes.windll.user32.LockWorkStation()
        else:
            import keyboard
            keyboard.send(t)
    elif a == "shell":
        subprocess.Popen(target, shell=True)
    elif a == "webhook":
        import requests
        if not target.lower().startswith(("http://", "https://")):
            return False
        r = requests.post(target, timeout=8, json={
            "source": "nova", "text": action.get("text", ""), "args": args})
        return r.status_code < 400
    elif a == "note":
        add_note(target)
    else:
        return False
    return True


AUTO_SUGGEST_SYSTEM = (
    "Tu crées des automatisations pour Nova, un assistant vocal Windows. "
    "L'utilisateur décrit ce qu'il veut ; réponds UNIQUEMENT avec un objet JSON :\n"
    '{"name": "...", "phrases": ["déclencheur vocal", ...], '
    '"action": {"type": "open_url|open_app|keys|shell|webhook", "target": "...", "args": ""}, '
    '"reply": "confirmation très courte"}\n'
    "- phrases : 1 à 3 déclencheurs courts en français, naturels à dire à voix haute.\n"
    "- open_url : target = URL complète. open_app : exécutable Windows (notepad, calc), "
    "URI (spotify:, ms-settings:) ou chemin ; arguments éventuels dans args.\n"
    "- keys : raccourci clavier (ex. win+l, ctrl+shift+s). "
    "shell : commande Windows (ex. shutdown /s /t 3600). "
    "webhook : URL appelée en POST (IFTTT, Zapier, Home Assistant).\n"
    "Choisis l'action la plus simple et la plus sûre qui réalise la demande."
)


def suggest_automation(desc):
    """L'IA transforme une description libre en automatisation prête à valider."""
    out = llm_complete(AUTO_SUGGEST_SYSTEM, desc, timeout=18)
    if not out:
        return None
    try:
        data = _extract_json(out)
        act = data.get("action") or {}
        phrases = [p.strip() for p in (data.get("phrases") or [])
                   if isinstance(p, str) and p.strip()]
        if act.get("type") not in ("open_url", "open_app", "keys", "shell", "webhook") \
                or not phrases or not (act.get("target") or "").strip():
            return None
        return {"name": (data.get("name") or phrases[0])[:60], "phrases": phrases[:3],
                "action": {"type": act["type"], "target": act["target"].strip(),
                           "args": (act.get("args") or "").strip()},
                "reply": (data.get("reply") or "").strip()}
    except Exception:
        return None


# ------------------------------------------------------------ interprète ----

def interpret(text):
    """Retourne (résultat, source) où source ∈ règle/note/recherche/ia/aucune."""
    n = normalize(text).strip(" .!?")

    for trig in NOTE_TRIGGERS:
        if n.startswith(normalize(trig)):
            content = text.strip()[len(trig):].strip(" ,.:") or text
            return {"action": "note", "target": content, "reply": "Note enregistrée"}, "note"

    for auto in get_automations():
        if auto.get("enabled", True) is False:
            continue
        for phrase in auto.get("phrases", []):
            if matches_phrase(normalize(phrase), n):
                act = dict(auto["action"])
                act["reply"] = auto.get("reply") or auto["name"]
                return {"action": act.get("type"), "target": act.get("target"),
                        "args": act.get("args", ""), "reply": act["reply"]}, "règle"

    m = re.search(r"\b(?:recherche|cherche|google)\s+(.{2,})", n)
    if m:
        return {"action": "web_search", "target": m.group(1),
                "reply": f"Je cherche « {m.group(1)} »"}, "recherche"

    result = ask_llm(text)
    if result:
        return result, "ia"
    return None, "aucune"


# ------------------------------------------------------------- analyse PC ---

MODEL_CATALOG = [
    {"name": "llama3.2:1b",   "size_gb": 1.3, "min_ram": 4,  "desc": "Ultra léger, très rapide"},
    {"name": "qwen2.5:1.5b",  "size_gb": 1.0, "min_ram": 4,  "desc": "Léger, bon en français"},
    {"name": "llama3.2:3b",   "size_gb": 2.0, "min_ram": 8,  "desc": "Bon équilibre vitesse/qualité"},
    {"name": "qwen2.5:3b",    "size_gb": 1.9, "min_ram": 8,  "desc": "Recommandé pour les commandes vocales"},
    {"name": "mistral:7b",    "size_gb": 4.4, "min_ram": 16, "desc": "Modèle français réputé"},
    {"name": "qwen2.5:7b",    "size_gb": 4.7, "min_ram": 16, "desc": "Très bonne compréhension"},
    {"name": "llama3.1:8b",   "size_gb": 4.9, "min_ram": 16, "desc": "Polyvalent, très populaire"},
    {"name": "qwen2.5:14b",   "size_gb": 9.0, "min_ram": 32, "desc": "Haute qualité (PC puissant)"},
]


def pc_info():
    import psutil
    ram_gb = round(psutil.virtual_memory().total / (1024 ** 3))
    gpu = None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW)
        if out.returncode == 0 and out.stdout.strip():
            gpu = out.stdout.strip().split("\n")[0]
    except Exception:
        pass
    installed = ollama_models()
    return {
        "ram_gb": ram_gb,
        "cpu_cores": os.cpu_count(),
        "gpu": gpu,
        "ollama_installed": shutil.which("ollama") is not None,
        "ollama_running": installed is not None,
        "installed_models": installed or [],
    }


def suggest_models():
    info = pc_info()
    ram = info["ram_gb"]
    out = []
    for m in MODEL_CATALOG:
        fits = ram >= m["min_ram"]
        out.append({**m, "fits": fits,
                    "installed": any(x.startswith(m["name"]) for x in info["installed_models"]),
                    "recommended": fits and m["min_ram"] >= max(
                        (c["min_ram"] for c in MODEL_CATALOG if ram >= c["min_ram"]), default=4)})
    return {"pc": info, "models": out}


_pulls = {}


def ollama_pull(model):
    """Lance `ollama pull` en arrière-plan ; suivre via pull_status()."""
    if model in _pulls and _pulls[model]["status"] == "en cours":
        return True
    _pulls[model] = {"status": "en cours", "progress": ""}

    def run():
        try:
            proc = subprocess.Popen(
                ["ollama", "pull", model],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW)
            for line in proc.stdout:
                line = line.strip()
                if line:
                    _pulls[model]["progress"] = line[-80:]
            proc.wait()
            _pulls[model]["status"] = "terminé" if proc.returncode == 0 else "erreur"
        except FileNotFoundError:
            _pulls[model]["status"] = "erreur"
            _pulls[model]["progress"] = "Ollama n'est pas installé (ollama.com)"
        except Exception as e:
            _pulls[model]["status"] = "erreur"
            _pulls[model]["progress"] = str(e)

    threading.Thread(target=run, daemon=True).start()
    return True


def pull_status():
    return _pulls
