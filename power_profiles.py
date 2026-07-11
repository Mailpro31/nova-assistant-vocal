# -*- coding: utf-8 -*-
"""Profils de puissance — le cœur du produit vendable (GOAL Partie 3).

L'utilisateur ne voit JAMAIS un nom de modèle ni de jargon : il choisit **Normal /
Élevé / Ultra**. Le mapping profil → modèles (Whisper + LLM local) est caché ici.

Garantie « sans bug, sans saturation RAM » : au lancement on mesure la machine
(RAM + GPU via psutil) et on VERROUILLE les profils qu'elle ne peut pas encaisser.
Un profil sélectionnable est donc toujours sûr. `evaluate()` est une fonction
PURE (matériel en entrée) → testable hors Windows, sur des configs simulées.
"""

# Mapping INTERNE profil → modèles. Ne JAMAIS exposer ces valeurs dans l'UI.
#   stt         : nom du modèle faster-whisper
#   llm         : modèle Ollama local (reformulation) ; "" = règles seules
#   min_ram_gb  : RAM totale minimale pour tenir le profil sans risque
#   seq_memory  : décharger le STT avant d'appeler le LLM (petites configs)
#   prefers_gpu : profil pensé pour une machine à GPU (avertissement sinon)
PROFILES = [
    {"id": "normal", "label": "Normal", "stt": "small",
     "llm": "qwen2.5:3b", "min_ram_gb": 4, "seq_memory": True,
     "prefers_gpu": False},
    {"id": "eleve", "label": "Élevé", "stt": "large-v3-turbo",
     "llm": "qwen2.5:7b", "min_ram_gb": 16, "seq_memory": True,
     "prefers_gpu": False},
    {"id": "ultra", "label": "Ultra", "stt": "large-v3",
     "llm": "qwen2.5:14b", "min_ram_gb": 24, "seq_memory": False,
     "prefers_gpu": True},
]

_BY_ID = {p["id"]: p for p in PROFILES}
DEFAULT_ID = "normal"          # le plus léger : sûr sur toute machine ciblée


def best_local_llm(ram_gb=None):
    """« Meilleure IA » locale (palier Ultra) : le meilleur modèle Ollama que la
    RAM peut tenir sans faire ramer la machine. 16 Go → qwen2.5:7b (idéal,
    ~5 Go) ; 24 Go+ → qwen2.5:14b ; en dessous → qwen2.5:3b. Réutilise la
    logique de déverrouillage des profils (source unique du mapping)."""
    hw = detect_hardware() if ram_gb is None else {"ram_total_gb": ram_gb}
    return get_profile(recommended_id(hw))["llm"]

# tolérance : on débloque un profil dès que la RAM totale atteint son minimum
# à cette marge près en DESSOUS (16 Go débloque Élevé/16 ; évite le rejet d'une
# machine « pile à la limite » où psutil rapporte 15,9 « Go »)
_RAM_MARGIN_GB = 0.5

_LOCK_MSG = "Nécessite plus de mémoire"
_LOCK_MSG_SUB = "Nécessite Nova Pro ou Ultra"
_HEAVY_MSG = "Plus performant, mais plus demandeur en mémoire et processeur."
_GPU_MSG = ("Optimal avec une carte graphique récente ; "
            "fonctionnera plus lentement sans.")


# ------------------------------------------------- détection matérielle ------
_HW_CACHE = None  # le matériel ne change pas en cours de session → mesuré 1 fois


def detect_hardware():
    """{ram_total_gb, ram_avail_gb, has_gpu, gpu_name, vram_gb}. Ne lève jamais :
    en cas de doute, renvoie une machine modeste (→ seul Normal débloqué).
    Mémoïsé : la sonde GPU (CTranslate2/CUDA) est coûteuse et le résultat est
    stable pour toute la session."""
    global _HW_CACHE
    if _HW_CACHE is not None:
        return dict(_HW_CACHE)
    ram_total = ram_avail = 8.0
    try:
        import psutil
        vm = psutil.virtual_memory()
        ram_total = vm.total / 1e9
        ram_avail = vm.available / 1e9
    except Exception:
        pass
    gpu_name, vram = _detect_gpu()
    _HW_CACHE = {
        "ram_total_gb": round(ram_total, 1),
        "ram_avail_gb": round(ram_avail, 1),
        "has_gpu": bool(gpu_name),
        "gpu_name": gpu_name,
        "vram_gb": vram,
    }
    return dict(_HW_CACHE)


def _detect_gpu():
    """(nom_gpu, vram_gb) via CTranslate2 (déjà embarqué pour Whisper), sinon
    ('', 0.0). Best-effort, jamais bloquant."""
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            # libellé affiché tel quel dans les Réglages (dock + tkinter) :
            # lexique produit, pas de jargon GPU/CUDA
            return "accélération graphique NVIDIA", 0.0
    except Exception:
        pass
    return "", 0.0


# --------------------------------------------------- évaluation (PURE) -------
def evaluate(hw, has_paid=True):
    """matériel → [{id, label, locked, reason, warning}] pour construire l'UI.
    Fonction pure : aucun effet de bord, testable sur des configs simulées.

    `has_paid` = l'utilisateur a un abonnement payant (Pro/Ultra). Élevé et Ultra
    sont des profils payants ; sans abonnement ils sont verrouillés avec le motif
    « abonnement ». La RAM reste un garde-fou : même abonné, un profil que la
    machine ne peut pas tenir reste verrouillé (motif « mémoire ») — jamais de
    saturation. Défaut True → no-op quand `licensing` est dormant (has() partout
    True), conformément à la règle des gates dormants."""
    ram = hw.get("ram_total_gb", 0.0)
    has_gpu = hw.get("has_gpu", False)
    out = []
    for p in PROFILES:
        # le profil plancher (le plus léger) n'est JAMAIS verrouillé : c'est la
        # base sûre garantie, il n'existe rien de plus léger vers quoi replier.
        # Invariant : safe_selection() renvoie toujours un profil débloqué.
        premium = p["id"] != DEFAULT_ID
        sub_locked = premium and not has_paid
        ram_locked = premium and ram + _RAM_MARGIN_GB < p["min_ram_gb"]
        locked = sub_locked or ram_locked
        # l'abonnement d'abord (c'est l'argument de vente), la RAM en garde-fou
        reason = _LOCK_MSG_SUB if sub_locked else (_LOCK_MSG if ram_locked else "")
        warning = ""
        if not locked:
            if p["prefers_gpu"] and not has_gpu:
                warning = _GPU_MSG
            elif p["min_ram_gb"] >= 16:
                warning = _HEAVY_MSG
        out.append({"id": p["id"], "label": p["label"], "locked": locked,
                    "reason": reason, "warning": warning})
    return out


def recommended_id(hw, has_paid=True):
    """Meilleur profil que la machine encaisse sans risque (le plus lourd
    débloqué), pour présélectionner un défaut pertinent à la 1re ouverture."""
    best = DEFAULT_ID
    for ev in evaluate(hw, has_paid):
        if not ev["locked"]:
            best = ev["id"]
    return best


def is_available(profile_id, hw, has_paid=True):
    for ev in evaluate(hw, has_paid):
        if ev["id"] == profile_id:
            return not ev["locked"]
    return False


# ------------------------------------------------- sélection / application ---
def get_profile(profile_id):
    return _BY_ID.get(profile_id) or _BY_ID[DEFAULT_ID]


def safe_selection(profile_id, hw, has_paid=True):
    """Profil demandé s'il est disponible (abonnement + RAM), sinon repli sur le
    plus lourd débloqué. Empêche toute sélection qui planterait (règle absolue)
    et toute sélection au-dessus du palier."""
    if is_available(profile_id, hw, has_paid):
        return profile_id
    return recommended_id(hw, has_paid)


def apply_profile(profile_id, cfg_save):
    """Applique le profil : câble le modèle STT et le modèle LLM local (Ollama)
    dans la config, SANS exposer leurs noms ailleurs. `cfg_save` = core.save_config.
    Retourne l'id réellement appliqué."""
    p = get_profile(profile_id)
    providers = {"ollama": {"model": p["llm"]}}
    cfg_save({
        "profile": p["id"],
        "whisper_model": p["stt"],
        "seq_memory": p["seq_memory"],
        "providers": providers,
    })
    return p["id"]


def select_and_apply(profile_id, cfg_save, has_paid=True):
    """Détecte le matériel, borne la sélection à ce qu'il supporte sans risque
    ET au palier d'abonnement, puis l'applique — la SEULE séquence à appeler
    pour changer de profil (tray, onboarding, démarrage). Retourne l'id
    réellement appliqué."""
    hw = detect_hardware()
    safe = safe_selection(profile_id, hw, has_paid)
    return apply_profile(safe, cfg_save)
