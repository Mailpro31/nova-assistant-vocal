# -*- coding: utf-8 -*-
"""Mode « Automatique » : choisit le mode de reformulation selon l'app active.

Le mode `auto` du registre n'a pas de `system_prompt` figé — il est résolu ici
à l'instant du collage, d'après le titre de la fenêtre au premier plan (et, en
secours, le nom du process). La table `_RULES` est une simple liste ordonnée
(motifs → id de mode) : ajouter une app = ajouter une règle, aucune logique à
réécrire. `resolve()` est une fonction PURE (titre/process en entrée) → testable
hors Windows ; `current_mode()` est le seul point qui touche winext.
"""

DEFAULT_ID = "voice_to_text"   # défaut : dictée brute nettoyée (brief Phase 3)

# Ordre = priorité (première règle qui matche gagne). Chaque motif est cherché
# en sous-chaîne dans « titre + nom du process », tout en minuscules.
_RULES = [
    ("email", (
        "gmail", "outlook", "courrier", "mail.google", "proton mail",
        "protonmail", "yahoo mail", "thunderbird", "outlook.exe",
    )),
    ("messages", (
        "whatsapp", "slack", "teams", "microsoft teams", "messenger",
        "telegram", "discord", "signal", "whatsapp.exe", "slack.exe",
        "teams.exe", "discord.exe", "telegram.exe",
    )),
    ("prompt_engineer", (
        "claude.ai", "chatgpt", "chat.openai", "openai", "gemini",
        "perplexity", "mistral", "le chat", "claude.exe",
    )),
    ("todo", (
        "to do", "to-do", "todoist", "ticktick", "things", "microsoft to do",
        "wunderlist", "any.do", "todoist.exe", "ticktick.exe",
    )),
    ("notes", (
        "notion", "obsidian", "onenote", "evernote", "bear", "apple notes",
        "notes", "logseq", "roam", "notion.exe", "obsidian.exe",
        "onenote.exe",
    )),
]


def resolve(title, proc=""):
    """(titre fenêtre, nom process) → id de mode concret (jamais « auto »).
    Fonction pure : aucun appel système, donc testable partout."""
    hay = f"{title or ''} {proc or ''}".lower()
    for mode_id, needles in _RULES:
        if any(n in hay for n in needles):
            return mode_id
    return DEFAULT_ID


def current_mode():
    """Résout le mode d'après la fenêtre RÉELLE au premier plan (Windows).
    Repli sur le défaut si winext est indisponible."""
    try:
        import winext
        return resolve(winext.active_window_title(), winext.active_process_name())
    except Exception:
        return DEFAULT_ID
