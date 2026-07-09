# -*- coding: utf-8 -*-
"""Mode « Automatique » : choisit le mode de reformulation selon l'app active.

Le mode `auto` du registre n'a pas de `system_prompt` figé — il est résolu ici
à l'instant du collage, d'après le titre de la fenêtre au premier plan (qui
contient le nom de l'onglet pour un navigateur) et le nom du process.

Précision (pour ne pas se tromper de mode) :
  • correspondance « MOT ENTIER » (bordures), pas en sous-chaîne : « Le chat »
    (l'animal), « Release notes », « Signal processing » ne déclenchent plus un
    mode à tort ;
  • deux familles de repères séparées — les NOMS D'APPS distinctifs sont
    cherchés dans le TITRE/onglet (« Gmail », « ChatGPT », « Notion »…), les
    mots plus génériques mais fiables sont cherchés dans le seul PROCESS
    (« signal.exe », « discord.exe »…), jamais dans le texte libre du titre ;
  • les repères sont les noms VISIBLES des apps (stables entre langues et
    présents dans le titre d'onglet) — le titre d'une fenêtre de navigateur ne
    contient PAS l'URL, seulement le titre de la page ;
  • règles personnalisables via `config.json` → clé `auto_rules`
    ({ "mode_id": ["repère", ...] }) : elles gagnent sur les règles intégrées.

`resolve()` reste une fonction PURE (titre/process/regles → id de mode),
testable hors Windows ; `current_mode()` est le seul point qui touche winext.
"""

import re

DEFAULT_ID = "voice_to_text"   # défaut : dictée brute nettoyée (brief Phase 3)


def _rx(token):
    """Compile un repère en motif « mot entier » (insensible à la casse via un
    foin déjà en minuscules). Les espaces du repère acceptent plusieurs espaces
    réels ; les bornes rejettent lettres/chiffres/underscore adjacents pour ne
    pas matcher « gmail » dans « gmailx » ni « to do » dans « photodo »."""
    esc = re.escape(token.strip().lower()).replace(r"\ ", r"\s+")
    return re.compile(r"(?<![0-9a-z_])" + esc + r"(?![0-9a-z_])")


# Ordre = priorité (première règle qui matche gagne). Chaque règle =
# (mode_id, repères de TITRE, repères de PROCESS).
_RULES_RAW = [
    ("email",
     ("gmail", "outlook", "thunderbird", "proton mail", "protonmail",
      "yahoo mail", "icloud mail", "fastmail", "superhuman", "courrier",
      "hey.com"),
     ("outlook", "thunderbird", "spark", "mailspring", "protonmail")),

    ("messages",
     ("whatsapp", "slack", "microsoft teams", "teams", "messenger",
      "telegram", "discord", "google chat", "wechat", "instagram"),
     ("whatsapp", "slack", "teams", "ms-teams", "discord", "telegram",
      "signal", "messenger", "wechat", "line", "skype")),

    ("prompt_engineer",
     ("chatgpt", "chat gpt", "claude", "gemini", "perplexity", "copilot",
      "mistral", "deepseek", "grok", "hugging face"),
     ("chatgpt", "claude", "msty", "lm studio")),

    ("todo",
     ("todoist", "ticktick", "microsoft to do", "google tasks", "omnifocus",
      "any.do", "to-do", "to do"),
     ("todoist", "ticktick", "omnifocus")),

    ("notes",
     ("notion", "obsidian", "onenote", "evernote", "logseq", "joplin",
      "google keep", "roam research", "craft docs", "anytype"),
     ("notion", "obsidian", "onenote", "evernote", "logseq", "joplin",
      "anytype")),
]

_RULES = [
    (mode_id, [_rx(t) for t in title_toks], [_rx(t) for t in proc_toks])
    for mode_id, title_toks, proc_toks in _RULES_RAW
]


def _match_user(extra_rules, hay):
    """Règles utilisateur : repères cherchés (mot entier) dans « titre +
    process ». Tolérant aux formats mal formés (ignore silencieusement)."""
    for mode_id, tokens in extra_rules:
        try:
            if mode_id and any(_rx(t).search(hay) for t in tokens):
                return mode_id
        except Exception:
            continue
    return None


def resolve(title, proc="", extra_rules=None):
    """(titre fenêtre, nom process[, règles utilisateur]) → id de mode concret
    (jamais « auto »). Fonction pure : aucun appel système, testable partout.

    `extra_rules` : liste de (mode_id, [repères]) prioritaire sur les règles
    intégrées — permet à l'utilisateur d'épingler ses propres apps."""
    title_l = (title or "").lower()
    proc_l = (proc or "").lower()

    if extra_rules:
        got = _match_user(extra_rules, f"{title_l} {proc_l}")
        if got:
            return got

    for mode_id, title_pats, proc_pats in _RULES:
        if any(p.search(title_l) for p in title_pats) or \
           any(p.search(proc_l) for p in proc_pats):
            return mode_id
    return DEFAULT_ID


def _user_rules():
    """Règles depuis config.json (`auto_rules`), ou None. Forme attendue :
    { "email": ["moncrm", "facturation"], "notes": ["mon wiki"] }."""
    try:
        import core
        raw = core.CFG.get("auto_rules") or {}
        rules = []
        for mode_id, toks in raw.items():
            if isinstance(toks, str):
                toks = [toks]
            toks = [str(t) for t in (toks or []) if str(t).strip()]
            if mode_id and toks:
                rules.append((mode_id, toks))
        return rules or None
    except Exception:
        return None


def current_mode():
    """Résout le mode d'après la fenêtre RÉELLE au premier plan (Windows).
    Repli sur le défaut si winext est indisponible."""
    try:
        import winext
        title = winext.active_window_title()
        proc = winext.active_process_name()
    except Exception:
        return DEFAULT_ID
    return resolve(title, proc, _user_rules())
