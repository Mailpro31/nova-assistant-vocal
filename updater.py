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


def download_and_install():
    """Télécharge Nova-Setup.exe puis lance l'installation silencieuse et QUITTE
    le process (l'installateur relance Nova à la fin). Retourne False si la
    mise à jour n'a pas pu partir — l'app continue alors normalement."""
    if not is_frozen():
        return False
    try:
        dest = os.path.join(tempfile.gettempdir(), "Nova-Setup.exe")
        urllib.request.urlretrieve(SETUP_URL, dest)
        if os.path.getsize(dest) < 5_000_000:   # page d'erreur ≠ installateur
            raise ValueError("téléchargement incomplet")
        subprocess.Popen([dest] + SILENT_FLAGS, close_fds=True)
        os._exit(0)
    except Exception as e:
        core.log_err("update_install", e)
        return False
