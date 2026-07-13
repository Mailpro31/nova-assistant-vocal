"""Installation intégrée de la reformulation locale (« Intelligence privée »).

Le moteur de reformulation local est un service tiers (exécutable + modèle,
~2,5 Go) que l'installateur de Nova n'embarque pas. Sur une machine neuve il
est ABSENT : chaque Style retombait alors en silence sur le collage brut
(« style_fallback: IA indisponible ») et le journal se remplissait de
tracebacks de connexion refusée à chaque démarrage. Ce module fournit une
installation en un clic, pilotée depuis les Réglages (dock ET tkinter) :

  téléchargement de l'installateur officiel → installation silencieuse →
  attente du service → téléchargement du modèle adapté au profil de puissance.

Point CLÉ : le modèle téléchargé est EXACTEMENT celui que la reformulation
chargera ensuite (même résolution que core — profil de puissance + « Meilleure
IA »). Sans cela l'installation pouvait réussir en téléchargeant un modèle,
pendant que les Styles en demandaient un autre → collage brut malgré un
« installé » affiché.

Tout est défensif (« jamais de plantage ») : échec → état `error` avec un
message sobre EN FRANÇAIS (jamais un message technique brut ni un nom de
modèle), l'app continue de fonctionner comme avant (collage brut). Aucun nom de
modèle n'est jamais montré à l'utilisateur (lexique produit :
« Intelligence privée »).
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

import requests

import core

SETUP_URL = "https://ollama.com/download/OllamaSetup.exe"
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


def _installed():
    """Modèles présents localement ([] si service absent/éteint)."""
    return core.ollama_models() or []


def _target():
    """Le modèle que la reformulation chargera RÉELLEMENT — MÊME résolution que
    core (`_reform_model` : profil de puissance + « Meilleure IA »). On installe
    donc précisément ce que les Styles demanderont, jamais un autre."""
    try:
        m = core._reform_model("ollama")
        if m:
            return m
    except Exception:
        pass
    return "qwen2.5:3b"


def _have_target():
    """Le modèle CIBLE (pas n'importe lequel) est-il déjà présent ? Un autre
    modèle installé ne suffit PAS : la reformulation chargerait la cible absente
    et retomberait sur le collage brut."""
    return _target() in _installed()


def ready():
    """Reformulation locale UTILISABLE : service en marche ET le modèle CIBLE
    présent (celui que les Styles vont vraiment charger)."""
    return service_up() and _have_target()


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


def _model_gb(name):
    """Estimation PRUDENTE de l'espace disque du modèle (Go) d'après le nombre
    de paramètres du tag (3b≈2 Go, 7b≈4,7 Go, 14b≈9 Go réels) — marge incluse
    pour ne pas tomber en panne de disque en plein téléchargement."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*b", name.lower())
    p = float(m.group(1)) if m else 3.0
    return max(2.5, p * 0.75 + 1.5)      # 3b→3,75 ; 7b→6,75 ; 14b→12


def _models_dir():
    """Là où le service stocke les modèles (%OLLAMA_MODELS% sinon
    %USERPROFILE%\\.ollama\\models) — PAS le dossier temp : c'est ce volume qui
    doit avoir la place, il peut différer de celui de TEMP."""
    d = os.environ.get("OLLAMA_MODELS")
    if d:
        return d
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return os.path.join(home, ".ollama", "models")


def _existing_ancestor(path):
    """Premier dossier existant en remontant `path` (le dossier .ollama n'existe
    pas encore sur une machine neuve — shutil.disk_usage exige un chemin réel)."""
    p = os.path.abspath(path)
    while p and not os.path.isdir(p):
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return p or tempfile.gettempdir()


def _free_gb(path):
    try:
        return shutil.disk_usage(_existing_ancestor(path)).free / 1e9
    except Exception:
        return 1e9               # illisible : on ne bloque pas l'utilisateur


def _run():
    try:
        if ready():                              # cible déjà en place
            _state.update({"phase": "done", "progress": 1.0})
            return
        svc = service_up()
        target = _target()
        # espace pour le MODÈLE là où le service le stocke (pas TEMP), + ~1 Go
        # pour l'installateur quand le service est absent
        if _free_gb(_models_dir()) < _model_gb(target):
            return _fail(f"Espace disque insuffisant "
                         f"({round(_model_gb(target))} Go nécessaires)")
        if not svc and _free_gb(tempfile.gettempdir()) < 1.2:
            return _fail("Espace disque insuffisant pour l'installateur")
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
            except subprocess.CalledProcessError:
                # échec LOCAL de l'installateur (antivirus, exécutable corrompu) :
                # ne PAS accuser la connexion internet
                raise RuntimeError("L'installation du composant a échoué — "
                                   "réessayez (antivirus ? redémarrage ?)")
            _state.update({"phase": "service", "progress": .55})
            _wait_service()
        _state.update({"phase": "model", "progress": .6})
        _pull_model(target)                                  # 60 → 100 %
        _state.update({"phase": "done", "progress": 1.0})
        try:
            core.warmup_engines()      # 1re dictée reformulée sans attente
        except Exception:
            pass
    except Exception as e:
        core.log_err("engine_setup", e)
        # message précis quand on en a un (RuntimeError sobre posé par nous),
        # générique sinon
        msg = str(e) if isinstance(e, RuntimeError) and str(e) else \
            "L'installation a échoué — vérifiez la connexion internet puis réessayez"
        _fail(msg)


def _download_setup(dest):
    with requests.get(SETUP_URL, stream=True, timeout=30) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or 0)
        got = 0
        t0 = time.monotonic()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1024 * 256):
                f.write(chunk)
                got += len(chunk)
                # borne TOTALE : un serveur qui livre au goutte-à-goutte
                # (« half-open ») ne doit pas laisser l'install coincée pour
                # toujours à phase=download — l'exception retombe dans _run → error
                if got > 1_500_000_000 or time.monotonic() - t0 > 15 * 60:
                    raise RuntimeError("Téléchargement du composant anormalement "
                                       "long — vérifiez la connexion puis réessayez")
                if total:
                    _state["progress"] = .45 * got / total
                else:
                    # taille inconnue (transfert « chunked ») : courbe
                    # asymptotique vers .45 pour que la barre AVANCE toujours
                    # (~700 Mo attendus) au lieu de rester figée à 0
                    _state["progress"] = .45 * (1 - 7e8 / (7e8 + got))


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
    raise RuntimeError("Service local injoignable après installation — "
                       "redémarrez le PC puis réessayez")


def _pull_model(target):
    """Téléchargement du modèle CIBLE via l'API locale (NDJSON streamé).
    Pas de dépendance au PATH : tout passe par le service HTTP.

    Progrès : Ollama émet des lignes PAR COUCHE (chacune avec son propre
    total/completed) ; suivre une seule couche ferait reculer la barre quand la
    couche suivante démarre. On agrège donc les OCTETS CUMULÉS de toutes les
    couches (monotone) et on projette une courbe asymptotique .6 → .98 —
    toujours en avant, jamais bloquée à 100 % avant la fin."""
    scale = max(1e9, _model_gb(target) * 0.6e9)   # échelle ≈ taille réelle
    got = 0
    seen = {}                                     # digest -> dernier `completed`
    # timeout=(connexion, LECTURE) : une lecture bloquée lève ReadTimeout au bout
    # de 3 min (au lieu de pendre jusqu'à 1 h) → retombe dans _run → error retriable
    t0 = time.monotonic()
    last_advance = t0
    with requests.post(core.ollama_url() + "/api/pull",
                       json={"name": target},
                       stream=True, timeout=(10, 180)) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            # garde de NON-PROGRESSION : si aucun octet n'a avancé depuis 5 min
            # (service coincé, débit nul), on abandonne au lieu de pendre
            if time.monotonic() - last_advance > 5 * 60:
                raise RuntimeError("Le téléchargement de l'intelligence est "
                                   "bloqué — réessayez")
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("error"):
                # jamais de message technique brut ni de nom de modèle à
                # l'utilisateur : le détail va au journal, l'UI voit du français
                core.log_err("engine_setup_pull", str(d["error"]))
                raise RuntimeError("Le téléchargement de l'intelligence a "
                                   "échoué — réessayez")
            dig = d.get("digest")
            done = int(d.get("completed") or 0)
            if dig:
                delta = max(0, done - seen.get(dig, 0))
                if delta:
                    last_advance = time.monotonic()      # progrès réel : on ré-arme la garde
                got += delta                             # somme des deltas ≥ 0
                seen[dig] = done
                _state["progress"] = .6 + .38 * (1 - scale / (scale + got))
    # vérification tolérante : le modèle qu'on VIENT de télécharger doit
    # apparaître (juste après un gros pull le service peut tarder à le lister) —
    # un AUTRE modèle ne compte pas, la reformulation chargerait la cible absente
    for _ in range(10):
        if target in _installed():
            return
        time.sleep(2)
    raise RuntimeError("L'intelligence n'est pas disponible après "
                       "téléchargement — réessayez")
