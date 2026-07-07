# -*- coding: utf-8 -*-
"""Registre de modes de reformulation — le cœur de l'architecture v3.

Chaque mode est une simple config (dict) : un `id`, un `label` affiché, une
`hotkey` (chiffre du menu) et un `system_prompt` consommé tel quel par
`core.format_message(text, system_prompt)`. Aucun code n'est câblé par mode :
ajouter un 8e mode (ex. « contrôle PC ») = ajouter une entrée ici, rien d'autre
à toucher. Un mode qui doit AGIR plutôt que reformuler peut porter un `handler`
optionnel (callable) — le reste de l'app teste sa présence, pas son identité.

Principe : `system_prompt = None` ⇒ résolu dynamiquement (mode Automatique, qui
choisit un autre mode selon l'app active — voir auto_mode.py).
"""

MODES = [
    {
        "id": "auto",
        "label": "Automatique",
        "hotkey": "1",
        "system_prompt": None,  # résolu dynamiquement selon l'app active
    },
    {
        "id": "voice_to_text",
        "label": "Voice to text",
        "hotkey": "2",
        "system_prompt": "Transcris fidèlement, corrige ponctuation et "
                         "majuscules, supprime les hésitations (euh, genre). "
                         "Garde le sens exact, aucune reformulation de fond.",
    },
    {
        "id": "email",
        "label": "E-mail",
        "hotkey": "3",
        "system_prompt": "Reformate en e-mail professionnel : formule "
                         "d'ouverture, corps clair, formule de clôture. "
                         "Garde le sens du message dicté.",
    },
    {
        "id": "prompt_engineer",
        "label": "Prompt Engineer",
        "hotkey": "4",
        "system_prompt": "Transforme la demande dictée en prompt structuré "
                         "pour une IA : rôle, tâche, contexte, contraintes.",
    },
    {
        "id": "todo",
        "label": "To-do lister",
        "hotkey": "5",
        "system_prompt": "Transforme la liste dictée en to-do list "
                         "structurée, une tâche par ligne, verbes d'action.",
    },
    {
        "id": "messages",
        "label": "Messages",
        "hotkey": "6",
        "system_prompt": "Reformate en message court et clair pour "
                         "messagerie (WhatsApp/Slack) : phrases courtes, "
                         "ton naturel, pas de formalisme excessif.",
    },
    {
        "id": "notes",
        "label": "Note taker",
        "hotkey": "7",
        "system_prompt": "Structure les notes dictées : points clés en "
                         "évidence, chiffres et critères mis en valeur, "
                         "format concis et scannable.",
    },
]

# id → config (accès O(1) ; construit une seule fois à l'import)
_BY_ID = {m["id"]: m for m in MODES}

DEFAULT_MODE_ID = "auto"


def all_modes():
    """Liste ordonnée des modes (pour construire le menu tray)."""
    return MODES


def get_mode(mode_id):
    """Config d'un mode par id, ou le mode par défaut si inconnu."""
    return _BY_ID.get(mode_id) or _BY_ID[DEFAULT_MODE_ID]


def mode_ids():
    return [m["id"] for m in MODES]


def label_of(mode_id):
    return get_mode(mode_id)["label"]


def prompt_of(mode_id):
    """`system_prompt` du mode (None pour « auto », résolu ailleurs)."""
    return get_mode(mode_id)["system_prompt"]


def by_hotkey(digit):
    """Mode associé à une touche du menu ('1'..'7'), ou None."""
    for m in MODES:
        if m.get("hotkey") == str(digit):
            return m
    return None
