"""Installation intégrée de la reformulation locale (« Intelligence privée »).

Le moteur de reformulation local est un service tiers (exécutable + modèle,
~2,5 Go) que l'installateur de Nova n'embarque pas. Sur une machine neuve il
est ABSENT : chaque Style retombait alors en silence sur le collage brut
(« style_fallback: IA indisponible ») et le journal se remplissait de
tracebacks de connexion refusée à chaque démarrage. Ce module fournit une
installation en un clic, pilotée depuis les Réglages (dock ET tkinter) :

  téléchargement de l'installateur officiel → installation silencieuse →
  attente du service → téléchargement du modèle adapté au profil de puissance.

Tout est défensif (« jamais de plantage ») : échec → état `error` avec un
message sobre, l'app continue de fonctionner comme avant (collage brut).
Aucun nom de modèle n'est jamais montré à l'utilisateur (lexique produit :
« Intelligence privée »).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

import requests

import core

SETUP_URL = "https://ollama.com/download/OllamaSetup.exe"
_MIN_FREE_GB = 6                  # installateur ~700 Mo + modèle ~2 Go + marge
_CREATE_NO_WINDOW = 0x08000000    # jamais de console visible

_lock = threading.Lock()
# phases : idle | download | install | service | model | done | error
_state = {"phase": "idle", "progress": 0.0, "error": ""}


def service_up(timeout=1.5):
    """Le service local répond-il ? (peu importe les modèles présents)"""
    try:
        return bool(requests.get(core.ollama_url() + "/api/tags",
                                 timeout=timeout).ok)
    except Exception:
        return False


def ready():
    """Reformulation locale UTILISABLE : service en marche ET ≥1 modèle."""
    return service_up() and bool(core.ollama_models())


def status():
    """État consommé par les Réglages (dock via js_api, tkinter via after).
    `ready` n'est sondé qu'au repos — pendant une installation, la phase
    fait foi (pas d'aller-retour HTTP par seconde de poll)."""
    st = dict(_state)
    st["ready"] = ready() if st["phase"] in ("idle", "done", "error") else False
    return st


def start():
    """Lance l'installation en arrière-plan. Idempotent : no-op si déjà en
    cours. Retourne l'état courant immédiatement (l'UI poll ensuite)."""
    with _lock:
        if _state["phase"] in ("download", "install", "service", "model"):
            return status()
        _state.update({"phase": "download", "progress": 0.0, "error": ""})
    threading.Thread(target=_run, daemon=True, name="engine-setup").start()
    return status()


def _fail(msg):
    _state.update({"phase": "error", "error": msg})


def snapshot():
    """Copie de l'état SANS aucun aller-retour HTTP — utilisable depuis le fil
    UI tkinter pendant une installation (le poll ne doit pas bloquer)."""
    return dict(_state)


def _run():
    try:
        if ready():                              # déjà en place (autre install)
            _state.update({"phase": "done", "progress": 1.0})
            return
        svc = service_up()
        # espace disque vérifié dans les DEUX cas : installateur+modèle (~6 Go)
        # ou modèle seul (~3 Go, service déjà là mais aucun modèle)
        need = _MIN_FREE_GB if not svc else 3
        if shutil.disk_usage(tempfile.gettempdir()).free / 1e9 < need:
            return _fail(f"Espace disque insuffisant ({need} Go nécessaires)")
        if not svc:
            dest = os.path.join(tempfile.gettempdir(), "NovaEngineSetup.exe")
            _download_setup(dest)                            # 0 → 45 %
            _state.update({"phase": "install", "progress": .45})
            # installateur officiel (Inno Setup) : silencieux, sans redémarrage.
            # 30 min de plafond : un disque lent/antivirus peut être TRÈS long,
            # et tuer l'installateur en plein vol laisserait une installation
            # corrompue — le dépassement a donc son propre message honnête.
            kw = {"creationflags": _CREATE_NO_WINDOW} if sys.platform == "win32" else {}
            try:
                subprocess.run([dest, "/VERYSILENT", "/SUPPRESSMSGBOXES",
                                "/NORESTART"], check=True, timeout=1800, **kw)
            except subprocess.TimeoutExpired:
                raise RuntimeError("Installation du composant trop longue — "
                                   "redémarrez le PC puis réessayez")
            _state.update({"phase": "service", "progress": .55})
            _wait_service()
        _state.update({"phase": "model", "progress": .6})
        _pull_model()                                        # 60 → 100 %
        _state.update({"phase": "done", "progress": 1.0})
        try:
            core.warmup_engines()      # 1re dictée reformulée sans attente
        except Exception:
            pass
    except Exception as e:
        core.log_err("engine_setup", e)
        # message précis quand on en a un (RuntimeError posé par nous),
        # générique sinon
        msg = str(e) if isinstance(e, RuntimeError) and str(e) else \
            "L'installation a échoué — vérifiez la connexion internet puis réessayez"
        _fail(msg)


def _download_setup(dest):
    with requests.get(SETUP_URL, stream=True, timeout=30) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or 0)
        got = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1024 * 256):
                f.write(chunk)
                got += len(chunk)
                if total:
                    _state["progress"] = .45 * got / total


def _wait_service():
    """L'installateur démarre normalement le service ; sinon on lance
    nous-mêmes l'app installée (silencieuse, dans le tray)."""
    exe = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                       "Programs", "Ollama", "ollama app.exe")
    for i in range(60):                          # jusqu'à ~2 min
        if service_up():
            return
        if i == 10 and os.path.isfile(exe):
            try:
                subprocess.Popen([exe], creationflags=_CREATE_NO_WINDOW)
            except Exception:
                pass
        time.sleep(2)
    raise RuntimeError("service local injoignable après installation")


def _model_name():
    """Modèle du profil de puissance courant (posé par apply_profile dans
    providers.ollama.model) ; repli = le modèle du profil le plus léger."""
    try:
        m = (core.CFG.get("providers") or {}).get("ollama", {}).get("model")
        if m:
            return m
    except Exception:
        pass
    return "qwen2.5:3b"


def _pull_model():
    """Téléchargement du modèle via l'API locale (NDJSON streamé → progrès).
    Pas de dépendance au PATH : tout passe par le service HTTP."""
    with requests.post(core.ollama_url() + "/api/pull",
                       json={"name": _model_name()},
                       stream=True, timeout=3600) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("error"):
                raise RuntimeError(d["error"])
            total = int(d.get("total") or 0)
            done = int(d.get("completed") or 0)
            if total:
                _state["progress"] = .6 + .4 * min(1.0, done / total)
    # vérification tolérante : juste après un pull de ~2 Go le service peut
    # être occupé à vérifier le blob et rater le timeout court de /api/tags —
    # quelques tentatives espacées avant de déclarer l'échec
    for _ in range(10):
        if core.ollama_models():
            return
        time.sleep(2)
    raise RuntimeError("Le modèle n'est pas visible après téléchargement — "
                       "réessayez")
