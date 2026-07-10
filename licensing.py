# -*- coding: utf-8 -*-
"""Licences & paliers de Nova : Free / Pro / Ultra / Business.

Modèle « offline-first » : une clé de licence est un jeton signé **Ed25519**,
vérifié LOCALEMENT avec la clé publique ci-dessous — aucun serveur, marche
100 % hors ligne, et impossible à forger sans la clé privée (que seul l'éditeur
détient, cf. `tools/mint_license.py`).

Paliers :
  • FREE     — dictée locale, quota ~2500 caractères transcrits / semaine.
  • PRO      — tout l'usage quotidien débloqué, transcription illimitée.
  • ULTRA    — Pro + meilleure IA/qualité + personnalisation (couleurs, noms…)
               + nouveautés en avant-première.
  • BUSINESS — mêmes fonctions que Pro, licence multi-postes (`seats`), tarif
               par siège plus bas (abonnement équipe).

État DORMANT : tant que `PUBLIC_KEY_B64` est vide (dépôt de dev) ou que le
paquet `cryptography` est absent, tout est débloqué et illimité — l'app tourne
sans restriction. Dès que l'éditeur colle sa clé publique et recompile, les
paliers s'appliquent : sans licence = Free ; sinon le palier de la licence.

Toutes les fonctions sont défensives (jamais d'exception propagée) pour tenir
la garantie « jamais de plantage ».
"""

import base64
import json
import time

# Clé publique Ed25519 de l'éditeur (base64url, 32 octets bruts). VIDE =
# licences désactivées (accès complet). Générer via :
#     python tools/mint_license.py genkey
PUBLIC_KEY_B64 = ""

FREE, PRO, ULTRA, BUSINESS = "free", "pro", "ultra", "business"
# Niveau de fonctionnalités : Business = niveau Pro (mêmes fonctions), mais
# licence multi-postes moins chère par siège.
_LEVEL = {FREE: 0, BUSINESS: 1, PRO: 1, ULTRA: 2}

# Quota hebdomadaire de caractères transcrits en Free (payant = illimité).
FREE_WEEKLY_CHARS = 2500

# Fonctionnalité → palier minimum requis. (Ajuster ici = changer l'offre.)
FEATURES = {
    "cloud_stt":         PRO,     # transcription cloud (Groq)
    "all_modes":         PRO,     # les 7 modes (Free en a 3)
    "all_languages":     PRO,     # toutes les langues (Free : la langue système)
    "custom_variables":  PRO,     # Custom Variables
    "power_profiles":    PRO,     # profils Élevé / Ultra (Free : Normal)
    "web_dock":          PRO,     # dock web « bille de verre »
    "unlimited_stt":     PRO,     # transcription sans quota hebdo
    "best_models":       ULTRA,   # meilleure IA / meilleure qualité
    "custom_modes":      ULTRA,   # créer ses propres modes / prompts
    "custom_auto_rules": ULTRA,   # règles auto_rules personnelles
    "orb_customization": ULTRA,   # couleurs / thème de l'orbe
    "custom_naming":     ULTRA,   # renommer l'app / les modes
    "priority_updates":  ULTRA,   # nouveautés en avant-première
}

# Modes de reformulation offerts en Free. « auto » est inclus : c'est le mode
# PAR DÉFAUT — il se résout ensuite vers un mode concret, downgradé sur
# voice_to_text si l'app détectée est réservée à un palier payant.
FREE_MODES = ("auto", "voice_to_text", "email", "messages")

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    _HAVE_CRYPTO = True
except BaseException:                   # paquet absent OU backend cassé (le
    # binding Rust peut lever une PanicException, non-`Exception`) → dormant,
    # jamais de plantage à l'import.
    _HAVE_CRYPTO = False


def _b64url_decode(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def enabled():
    """True si le système de licences est ACTIF (clé publique configurée +
    crypto disponible). Sinon dormant → accès complet."""
    return bool(PUBLIC_KEY_B64) and _HAVE_CRYPTO


def verify_key(key, pub_b64=None):
    """Vérifie un jeton « NOVA1.<payload>.<sig> » signé Ed25519.
    → dict {tier, email, expiry, seats} si signature valide et non expirée,
    sinon None. Ne lève jamais."""
    pub_b64 = PUBLIC_KEY_B64 if pub_b64 is None else pub_b64
    if not key or not pub_b64 or not _HAVE_CRYPTO:
        return None
    try:
        parts = key.strip().split(".")
        if len(parts) != 3 or parts[0] != "NOVA1":
            return None
        payload = _b64url_decode(parts[1])
        sig = _b64url_decode(parts[2])
        Ed25519PublicKey.from_public_bytes(_b64url_decode(pub_b64)).verify(
            sig, payload)               # lève si signature invalide
        data = json.loads(payload.decode("utf-8"))
        if data.get("t") not in _LEVEL:
            return None
        exp = int(data.get("x", 0) or 0)
        if exp and time.time() > exp:
            return None                 # expirée
        return {"tier": data["t"], "email": data.get("e", ""),
                "expiry": exp, "seats": int(data.get("s", 1) or 1)}
    except Exception:
        return None


def _license_from_config():
    try:
        import core
        return core.CFG.get("license_key") or ""
    except Exception:
        return ""


def _status(tier, active):
    return {"tier": tier, "email": "", "expiry": 0, "seats": 1, "active": active}


def status():
    """État courant : {tier, email, expiry, seats, active}. Défensif."""
    if not enabled():
        return _status(ULTRA, False)         # dormant → accès complet
    info = verify_key(_license_from_config())
    if info:
        info["active"] = True
        return info
    return _status(FREE, True)               # actif, sans licence valide


def current_tier():
    return status()["tier"]


def has(feature, tier=None):
    """La fonctionnalité est-elle débloquée ? Système dormant → True (accès
    complet). Passer `tier` explicitement permet de tester la logique sans
    crypto ni config."""
    if tier is None:
        if not enabled():
            return True
        tier = current_tier()
    return _LEVEL.get(tier, 0) >= _LEVEL[FEATURES.get(feature, ULTRA)]


def mode_allowed(mode_id, tier=None):
    """Un mode de reformulation est-il autorisé au palier courant ?"""
    return has("all_modes", tier) or mode_id in FREE_MODES


# ---------------------------------------------------- quota hebdo (Free) -----

def _week_key():
    """Clé de semaine ISO, ex. « 2026-W28 » (réinitialise le quota chaque lundi)."""
    return time.strftime("%G-W%V")


def _usage_used():
    try:
        import core
        u = core.CFG.get("usage") or {}
        return int(u.get("chars", 0)) if u.get("week") == _week_key() else 0
    except Exception:
        return 0


def quota_status():
    """Quota de transcription de la semaine. Paliers payants → illimité.
    → {limit, used, remaining, week}. `limit`/`remaining` valent None si illimité."""
    week = _week_key()
    if has("unlimited_stt"):
        return {"limit": None, "used": 0, "remaining": None, "week": week}
    used = _usage_used()
    return {"limit": FREE_WEEKLY_CHARS, "used": used,
            "remaining": max(0, FREE_WEEKLY_CHARS - used), "week": week}


def can_transcribe():
    """Reste-t-il du quota cette semaine ? (True si illimité.)"""
    st = quota_status()
    return st["remaining"] is None or st["remaining"] > 0


def record_transcription(text):
    """Comptabilise les caractères transcrits (Free uniquement). Défensif :
    n'écrit rien et ne lève jamais pour un palier illimité."""
    try:
        if has("unlimited_stt"):
            return
        import core
        week = _week_key()
        used = _usage_used()
        core.save_config({"usage": {"week": week,
                                    "chars": used + len(text or "")}})
    except Exception:
        pass


def activate(key):
    """Vérifie puis PERSISTE la clé en config (`license_key`). → status()
    enrichi de `ok`. N'écrit rien si la clé est invalide."""
    info = verify_key(key)
    if not info:
        return {"ok": False, "error": "Clé invalide ou expirée."}
    try:
        import core
        core.save_config({"license_key": key.strip()})
    except Exception:
        return {"ok": False, "error": "Impossible d'enregistrer la licence."}
    st = status()
    st["ok"] = True
    return st
