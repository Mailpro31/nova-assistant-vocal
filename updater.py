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
_UA = "Nova-updater"
# Plafonds du téléchargement : au-delà, quelque chose ne va pas (le timeout
# d'urlopen ne borne que CHAQUE lecture socket — un serveur au goutte-à-goutte
# resterait sinon bloquant pour toujours, verrou tenu).
_MAX_BYTES = 500 * 1024 * 1024
_MAX_SECONDS = 15 * 60


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
                                   "User-Agent": _UA})
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

# Résultats possibles de download_and_install (le succès ne « retourne »
# jamais : le process se termine pour laisser place à l'installateur).
FAILED, BUSY, UNSUPPORTED = "failed", "busy", "unsupported"


def _sweep_old():
    """Supprime les installateurs des mises à jour PRÉCÉDENTES (%TEMP% —
    l'installateur d'une mise à jour réussie ne peut pas se nettoyer lui-même :
    le process quitte pour le laisser tourner). Best-effort : un fichier encore
    verrouillé (installation en cours) est simplement laissé en place."""
    try:
        tmp = tempfile.gettempdir()
        for name in os.listdir(tmp):
            if name.startswith("Nova-Setup-") and name.endswith(".exe"):
                try:
                    os.remove(os.path.join(tmp, name))
                except OSError:
                    pass
    except Exception:
        pass


def _download(url, dest, timeout=30):
    """Télécharge `url` vers `dest` par morceaux. Triple garde-fou : délai par
    lecture socket (urlretrieve n'en avait AUCUN), durée totale et taille
    totale plafonnées — le timeout d'urlopen ne borne que chaque lecture, un
    serveur au goutte-à-goutte serait sinon infini. Lève en cas d'erreur ;
    l'appelant décide des reprises."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    t0, total = time.monotonic(), 0
    with urllib.request.urlopen(req, timeout=timeout) as r, \
            open(dest, "wb") as f:
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_BYTES or time.monotonic() - t0 > _MAX_SECONDS:
                raise ValueError(f"téléchargement anormal ({total} octets, "
                                 f"{int(time.monotonic() - t0)} s)")
            f.write(chunk)
    return total


def download_and_install():
    """Télécharge Nova-Setup.exe puis lance l'installation silencieuse et QUITTE
    le process (l'installateur relance Nova à la fin). Ne retourne que sur
    non-succès : BUSY (une tentative tourne déjà — pas un échec), UNSUPPORTED
    (pas un .exe gelé : développement), FAILED (téléchargement ou lancement
    impossibles) — l'app continue alors normalement."""
    if not is_frozen():
        return UNSUPPORTED
    if not _busy.acquire(blocking=False):
        return BUSY
    dest = ""
    try:
        _sweep_old()                     # les installateurs des MàJ passées
        last = None
        for wait in (0, 3, 8):           # 3 essais : les erreurs réseau et les
            if wait:                     # relais GitHub passagers se résorbent
                time.sleep(wait)
            try:
                # fichier NEUF à chaque essai : un reste partiel encore scanné
                # par l'antivirus ne condamne pas les essais suivants
                if dest:
                    try:
                        os.remove(dest)
                    except OSError:
                        pass
                fd, dest = tempfile.mkstemp(prefix="Nova-Setup-",
                                            suffix=".exe")
                os.close(fd)
                size = _download(SETUP_URL, dest)
                if size < 5_000_000:     # page d'erreur ≠ installateur
                    raise ValueError(f"téléchargement incomplet ({size} octets)")
                last = None
                break
            except Exception as e:
                last = e
        if last is not None:
            core.log_err("update_dl", last)
            return FAILED
        # l'antivirus peut tenir le .exe fraîchement écrit 1-2 s : une reprise
        # du seul LANCEMENT suffit, re-télécharger serait inutile
        for wait in (0, 2):
            if wait:
                time.sleep(wait)
            try:
                subprocess.Popen([dest] + SILENT_FLAGS, close_fds=True)
                os._exit(0)
            except Exception as e:
                core.log_err("update_run", e)
        return FAILED
    except Exception as e:
        core.log_err("update_install", e)
        return FAILED
    finally:
        if dest and os.path.isfile(dest):
            try:                         # atteint seulement en échec : succès
                os.remove(dest)          # → os._exit (l'installateur a besoin
            except OSError:              # du fichier)
                pass
        _busy.release()
