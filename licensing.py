# -*- coding: utf-8 -*-
"""Licences & paliers de Nova : Free / Pro / Ultra / Business.

Modèle « offline-first » : une clé de licence est un jeton signé **Ed25519**,
vérifié LOCALEMENT avec la clé publique ci-dessous — aucun serveur, marche
100 % hors ligne, et impossible à forger sans la clé privée (que seul l'éditeur
détient, cf. `tools/mint_license.py`).

Paliers :
  • FREE     — dictée locale ILLIMITÉE + ~10 reformulations IA / jour + 3 Styles.
  • PRO      — reformulations illimitées + les 7 Styles + profils de puissance
               + variables personnalisées (tout le local, sans limite).
  • ULTRA    — Pro + Turbo (moteur en ligne) + transcription en ligne + meilleure
               IA + personnalisation (couleurs, noms…) + avant-première.
  • BUSINESS — mêmes fonctions que Pro, licence multi-postes (`seats`), tarif
               par siège plus bas (abonnement équipe).

Essai inversé : les TRIAL_DAYS premiers jours après l'installation, l'app passe
en PRO sans clé (reformulations illimitées, 7 Styles) puis retombe en FREE — la
reformulation redevient ~10/jour ; la dictée reste illimitée dans tous les cas.

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

# Clé publique Ed25519 de l'éditeur (base64, 32 octets bruts). VIDE =
# licences désactivées (accès complet). La clé privée correspondante vit
# UNIQUEMENT dans le coffre du serveur d'activation (Supabase, projet
# nova-licences) — jamais dans ce dépôt.
PUBLIC_KEY_B64 = "Q+U/LqaeFgLSDkvqiAXRcHQ8DSwqU9NcrHiPt8A6EJE="

# Serveur d'activation : transforme une clé d'achat « NOVA-XXXXX-XXXXX-XXXXX »
# (reçue après paiement) en jeton signé lié à CETTE machine. L'app reste
# 100 % hors ligne ensuite (vérification locale, 7 j de grâce inclus côté
# serveur dans l'expiration du jeton).
ACTIVATION_URL = ("https://cvpucqsxgjczkdskohte.supabase.co"
                  "/functions/v1/license/activate")

FREE, PRO, ULTRA, BUSINESS = "free", "pro", "ultra", "business"
# Niveau de fonctionnalités : Business = niveau Pro (mêmes fonctions), mais
# licence multi-postes moins chère par siège.
_LEVEL = {FREE: 0, BUSINESS: 1, PRO: 1, ULTRA: 2}

# Plafond quotidien de reformulations IA en Free (payant = illimité). La dictée
# (transcription) reste ILLIMITÉE à TOUS les paliers — on ne bride jamais la voix.
FREE_DAILY_REFORMULATIONS = 10

# Essai inversé : jours de Pro offerts après l'installation, puis bascule Free.
TRIAL_DAYS = 14

# Fonctionnalité → palier minimum requis. (Ajuster ici = changer l'offre.)
FEATURES = {
    # toutes les langues sont offertes en Gratuit (choix produit) — non gaté
    "cloud_stt":         ULTRA,   # Turbo (transcription cloud Groq) — Ultra only
    "all_modes":         PRO,     # les 7 modes (Free : cf. FREE_MODES)
    "custom_variables":  PRO,     # Custom Variables
    "power_profiles":    PRO,     # profils Élevé / Ultra (Free : Normal)
    "web_dock":          FREE,    # dock web « bille de verre » = l'interface
                                  # principale de Nova (la pilule tkinter n'est
                                  # qu'un repli si WebView2 manque)
    "unlimited_reformulation": PRO,  # reformulations IA sans plafond quotidien
    "best_models":       ULTRA,   # meilleure IA / meilleure qualité
    "custom_modes":      ULTRA,   # créer ses propres modes / prompts
    "custom_auto_rules": ULTRA,   # règles auto_rules personnelles
    "orb_customization": ULTRA,   # couleurs / thème de l'orbe
    "custom_naming":     ULTRA,   # renommer l'app / les modes
    "priority_updates":  ULTRA,   # nouveautés en avant-première
}

# Modes de reformulation offerts en Free (décision produit : le quotidien —
# Normal, E-mail, Messages — est gratuit ; To-do, Prompt IA et Prise de notes
# restent côté Pro). « auto » est inclus : c'est le mode PAR DÉFAUT — il se
# résout ensuite vers un mode concret, downgradé sur voice_to_text si l'app
# détectée est réservée à un palier payant.
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
        if data.get("m") and data["m"] != _machine_fingerprint():
            return None                 # jeton lié à une AUTRE machine
        return {"tier": data["t"], "email": data.get("e", ""),
                "expiry": exp, "seats": int(data.get("s", 1) or 1)}
    except Exception:
        return None


def _machine_fingerprint():
    """Empreinte de CE poste (via winext). Défensif : '' si indisponible —
    un jeton lié à une machine sera alors refusé, jamais accepté à tort."""
    try:
        import winext
        return winext.machine_fingerprint()
    except Exception:
        return ""


def _license_from_config():
    try:
        import core
        return core.CFG.get("license_key") or ""
    except Exception:
        return ""


def _status(tier, active, trial_days_left=0):
    return {"tier": tier, "email": "", "expiry": 0, "seats": 1,
            "active": active, "trial_days_left": int(trial_days_left)}


def _install_ts():
    """Horodatage de première utilisation (essai inversé), stocké CHIFFRÉ pour
    survivre à un effacement de config. Posé paresseusement au 1er appel.
    → epoch (int), ou 0 si indisponible (→ pas d'essai, on retombe en Free :
    fail-safe, jamais Pro à tort)."""
    try:
        import winext
        raw = winext.get_secret("install")
        if raw:
            ts = int(json.loads(raw).get("ts", 0) or 0)
            if ts:
                return ts
        now = int(time.time())
        winext.set_secret("install", json.dumps({"ts": now}))
        return now
    except Exception:
        return 0


def _trial_days_left():
    """Jours d'essai Pro restants (1..TRIAL_DAYS ; 0 si fini ou indisponible)."""
    ts = _install_ts()
    if not ts:
        return 0
    left = TRIAL_DAYS - (time.time() - ts) / 86400.0
    return int(left) + 1 if left > 0 else 0


def status():
    """État courant : {tier, email, expiry, seats, active, trial_days_left}.
    Défensif. Sans licence, les TRIAL_DAYS premiers jours après l'installation
    passent en PRO (essai inversé), puis bascule en FREE."""
    if not enabled():
        return _status(ULTRA, False)         # dormant → accès complet
    info = verify_key(_license_from_config())
    if info:
        info["active"] = True
        info.setdefault("trial_days_left", 0)
        return info
    left = _trial_days_left()
    if left > 0:
        return _status(PRO, True, left)      # essai inversé : Pro offert
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


# ------------------------------------------ quota reformulations (Free) ------
# Modèle : la dictée (transcription) est ILLIMITÉE partout ; en Free, c'est la
# reformulation IA (le « waouh ») qui est plafonnée à FREE_DAILY_REFORMULATIONS
# par jour. Usage stocké CHIFFRÉ (DPAPI via winext) pour qu'éditer/effacer
# config.json ne réinitialise pas le compteur ; l'horodatage sert de garde
# anti-recul d'horloge. Toutes les fonctions sont défensives.

def _day_key():
    """Clé de jour ISO, ex. « 2026-07-15 » (réinitialise le quota chaque jour)."""
    return time.strftime("%Y-%m-%d")


def _usage_read():
    """Usage du jour, stocké CHIFFRÉ (DPAPI via winext). Repli sur l'ancien
    emplacement config (migration douce) puis {}. Ne lève jamais."""
    try:
        import winext
        raw = winext.get_secret("usage")
        if raw:
            u = json.loads(raw)
            if isinstance(u, dict):
                return u
    except Exception:
        pass
    try:
        import core
        return dict(core.CFG.get("usage") or {})
    except Exception:
        return {}


def _usage_write(day, count):
    """Persiste l'usage dans le coffre chiffré, avec l'horodatage qui sert de
    garde anti-recul d'horloge. Défensif : silencieux si le coffre échoue."""
    try:
        import winext
        winext.set_secret("usage", json.dumps(
            {"day": day, "count": int(count), "ts": int(time.time())}))
    except Exception:
        pass


def _effective_day(u):
    """Jour à comptabiliser. Si l'horloge système a RECULÉ de plus de 6 h par
    rapport au dernier enregistrement (triche pour réinitialiser le quota), on
    continue de compter dans le jour déjà enregistré."""
    if int(u.get("ts", 0) or 0) - time.time() > 6 * 3600 and u.get("day"):
        return u["day"]
    return _day_key()


def _usage_used():
    try:
        u = _usage_read()
        return int(u.get("count", 0)) if u.get("day") == _effective_day(u) else 0
    except Exception:
        return 0


def quota_status():
    """Quota de reformulations IA du jour. Paliers payants (et essai) → illimité.
    → {limit, used, remaining, day}. `limit`/`remaining` valent None si illimité."""
    day = _day_key()
    if has("unlimited_reformulation"):
        return {"limit": None, "used": 0, "remaining": None, "day": day}
    used = _usage_used()
    return {"limit": FREE_DAILY_REFORMULATIONS, "used": used,
            "remaining": max(0, FREE_DAILY_REFORMULATIONS - used), "day": day}


def can_reformulate():
    """Reste-t-il des reformulations IA aujourd'hui ? (True si illimité.)"""
    st = quota_status()
    return st["remaining"] is None or st["remaining"] > 0


def record_reformulation():
    """Comptabilise UNE reformulation IA réussie (Free uniquement) dans le coffre
    chiffré. Défensif : no-op pour un palier illimité, ne lève jamais."""
    try:
        if has("unlimited_reformulation"):
            return
        u = _usage_read()
        day = _effective_day(u)
        used = int(u.get("count", 0)) if u.get("day") == day else 0
        _usage_write(day, used + 1)
    except Exception:
        pass


def can_transcribe():
    """Compat : la transcription est désormais ILLIMITÉE à tous les paliers.
    Conservée pour d'anciens appelants — renvoie toujours True."""
    return True


def activate(key):
    """Active une licence puis la PERSISTE en config. Deux formes acceptées :
    clé d'achat « NOVA-XXXXX-XXXXX-XXXXX » (reçue après paiement → échange
    contre un jeton lié à cette machine auprès du serveur) ou jeton « NOVA1.… »
    direct (usage interne / hors ligne). → status() enrichi de `ok`."""
    key = (key or "").strip()
    if key.upper().startswith("NOVA-"):
        return _activate_online(key.upper())
    info = verify_key(key)
    if not info:
        return {"ok": False, "error": "Clé invalide ou expirée."}
    return _persist(key)


def _persist(token, purchase_key=None):
    try:
        import core
        cfg = {"license_key": token}
        if purchase_key:
            cfg["license_purchase_key"] = purchase_key
        core.save_config(cfg)
    except Exception:
        return {"ok": False, "error": "Impossible d'enregistrer la licence."}
    st = status()
    st["ok"] = True
    return st


def _activate_online(purchase_key):
    """Échange la clé d'achat contre un jeton signé lié à CETTE machine
    (2 postes max par licence, un poste inactif 30 j libère sa place)."""
    try:
        import requests
        r = requests.post(ACTIVATION_URL, timeout=10, json={
            "key": purchase_key,
            "machine": _machine_fingerprint(),
        })
        data = r.json()
    except Exception:
        return {"ok": False, "error": "Serveur d'activation injoignable — "
                                      "vérifiez votre connexion internet."}
    if not data.get("ok"):
        return {"ok": False,
                "error": data.get("error", "Activation refusée.")}
    token = data.get("token", "")
    if not verify_key(token):
        return {"ok": False, "error": "Réponse du serveur invalide."}
    return _persist(token, purchase_key)


def refresh_if_needed():
    """Renouvelle silencieusement le jeton d'abonnement quand il approche de
    l'expiration (< 10 j) — appelé au démarrage, best-effort : hors ligne, le
    jeton courant garde sa période de grâce. Ne lève jamais."""
    try:
        if not enabled():
            return
        import core
        purchase_key = core.CFG.get("license_purchase_key") or ""
        if not purchase_key:
            return                      # licence hors ligne : rien à renouveler
        info = verify_key(core.CFG.get("license_key") or "")
        if info and info["expiry"] and info["expiry"] - time.time() > 10 * 86400:
            return                      # encore loin de l'expiration
        _activate_online(purchase_key)
    except Exception:
        pass
