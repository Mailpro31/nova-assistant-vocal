# -*- coding: utf-8 -*-
"""Mise à jour automatique — GitHub Releases + installateur Inno silencieux.

Principe : on compare core.APP_VERSION au tag de la dernière release GitHub ;
si plus récente, on télécharge Nova-Setup.exe dans %TEMP% puis on le lance en
silencieux (/VERYSILENT) et on quitte — l'installateur remplace les fichiers
et relance Nova tout seul (entrée [Run] `Check: WizardSilent` de nova.iss).

Garde-fous « jamais de plantage » : chaque étape est best-effort et journalisée ;
hors .exe gelé (développement), tout est no-op — l'app continue normalement si
la mise à jour échoue, elle ne casse jamais un lancement.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

import core

RELEASES_API = ("https://api.github.com/repos/"
                "Mailpro31/nova-assistant-vocal/releases/latest")
SETUP_URL = ("https://github.com/Mailpro31/nova-assistant-vocal/"
             "releases/latest/download/Nova-Setup.exe")
# /MERGETASKS=!preload : pas de re-téléchargement du modèle pendant une MàJ
SILENT_FLAGS = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                "/MERGETASKS=!preload"]


def is_frozen():
    """Vrai en .exe PyInstaller — en développement, l'updater est un no-op."""
    return bool(getattr(sys, "frozen", False))


def _vtuple(v):
    """'v3.1.0' → (3, 1, 0) : comparaison numérique, robuste aux préfixes."""
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:3]) or (0,)


def check_latest(timeout=10):
    """Interroge la dernière release. → {'version': '3.2.0', 'newer': bool}
    ou None (hors ligne, API indisponible…) — jamais d'exception."""
    try:
        req = urllib.request.Request(
            RELEASES_API, headers={"Accept": "application/vnd.github+json",
                                   "User-Agent": "Nova-updater"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            tag = str(json.load(r).get("tag_name") or "")
        if not tag:
            return None
        return {"version": tag.lstrip("vV"),
                "newer": _vtuple(tag) > _vtuple(core.APP_VERSION)}
    except Exception as e:
        core.log_err("update_check", e)
        return None


# Une seule mise à jour à la fois : la vérification auto du lancement et le
# bouton « Rechercher maintenant » peuvent se chevaucher — sans ce verrou, les
# deux écrivaient le même fichier temporaire et le second échouait (accès
# refusé Windows), d'où un faux « Mise à jour impossible ».
_busy = threading.Lock()


def _download(url, dest, timeout=30):
    """Télécharge `url` vers `dest` par morceaux, avec délai limite par lecture
    (urlretrieve n'a AUCUN timeout : une connexion figée bloquait pour
    toujours). Lève en cas d'erreur ; l'appelant décide des reprises."""
    req = urllib.request.Request(url, headers={"User-Agent": "Nova-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as r, \
            open(dest, "wb") as f:
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)


def download_and_install():
    """Télécharge Nova-Setup.exe puis lance l'installation silencieuse et QUITTE
    le process (l'installateur relance Nova à la fin). Retourne False si la
    mise à jour n'a pas pu partir, True si une tentative est déjà en cours —
    l'app continue alors normalement, elle n'affiche pas d'erreur."""
    if not is_frozen():
        return False
    if not _busy.acquire(blocking=False):
        return True                      # déjà en cours — pas un échec
    dest = ""
    try:
        # nom unique à chaque tentative : jamais de collision avec un
        # téléchargement précédent (fichier verrouillé, antivirus en cours…)
        fd, dest = tempfile.mkstemp(prefix="Nova-Setup-", suffix=".exe")
        os.close(fd)
        last = None
        for wait in (0, 3, 8):           # 3 essais : les erreurs réseau et les
            if wait:                     # relais GitHub passagers se résorbent
                time.sleep(wait)
            try:
                _download(SETUP_URL, dest)
                if os.path.getsize(dest) < 5_000_000:   # page d'erreur ≠ setup
                    raise ValueError("téléchargement incomplet "
                                     f"({os.path.getsize(dest)} octets)")
                last = None
                break
            except Exception as e:
                last = e
        if last is not None:
            core.log_err("update_dl", last)
            return False
        try:
            subprocess.Popen([dest] + SILENT_FLAGS, close_fds=True)
        except Exception as e:           # lancement bloqué (antivirus…) : on ne
            core.log_err("update_run", e)   # re-télécharge pas, c'est inutile
            return False
        os._exit(0)
    except Exception as e:
        core.log_err("update_install", e)
        return False
    finally:
        if dest and os.path.isfile(dest):
            try:                         # atteint seulement en échec : succès
                os.remove(dest)          # → os._exit (l'installateur a besoin
            except OSError:              # du fichier)
                pass
        _busy.release()
