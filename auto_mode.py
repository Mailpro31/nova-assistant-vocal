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
    réels ; les bornes `\\w` (Unicode) rejettent toute lettre/chiffre adjacente —
    y compris accentuée — pour ne pas matcher « gmail » dans « gmailx », « to do »
    dans « photodo », ni « line » dans « câline »."""
    esc = re.escape(token.strip().lower()).replace(r"\ ", r"\s+")
    if not esc:
        return re.compile(r"(?!x)x")   # repère vide → ne matche jamais
    return re.compile(r"(?<!\w)" + esc + r"(?!\w)")


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


def _compile_user(extra_rules):
    """Compile les règles utilisateur (mode_id, [repères]) au même format que
    `_RULES` — repères testés à la fois sur le titre et le process. Réellement
    tolérant : une entrée mal formée (pas un couple, repères en chaîne nue,
    repères vides) est ignorée sans lever ni matcher tout."""
    out = []
    for entry in extra_rules or ():
        try:
            mode_id, tokens = entry
            if isinstance(tokens, str):
                tokens = [tokens]
            pats = [_rx(t) for t in tokens if str(t).strip()]
        except Exception:
            continue
        if mode_id and pats:
            out.append((mode_id, pats, pats))
    return out


def resolve(title, proc="", extra_rules=None):
    """(titre fenêtre, nom process[, règles utilisateur]) → id de mode concret
    (jamais « auto »). Fonction pure : aucun appel système, testable partout.

    `extra_rules` : liste de (mode_id, [repères]) prioritaire sur les règles
    intégrées — permet à l'utilisateur d'épingler ses propres apps. Ses repères
    sont testés sur le titre ET le process (comme les règles intégrées)."""
    title_l = (title or "").lower()
    proc_l = (proc or "").lower()

    rules = _compile_user(extra_rules) + _RULES if extra_rules else _RULES
    for mode_id, title_pats, proc_pats in rules:
        if any(p.search(title_l) for p in title_pats) or \
           any(p.search(proc_l) for p in proc_pats):
            return mode_id
    return DEFAULT_ID


def _user_rules():
    """Règles depuis config.json, ou None. Deux sources, par priorité :

    1. `custom_modes` (palier Ultra) — modes SUR MESURE créés par l'utilisateur
       ({id, name, match: [repères], prompt}) : quand un repère matche l'app ou
       l'onglet actif, resolve() renvoie « custom:<id> » et le prompt du mode
       est appliqué à la reformulation (résolu dans app._resolve_prompt).
    2. `auto_rules` (palier Ultra) — routage perso vers les modes INTÉGRÉS
       ({ "email": ["moncrm"] }). Les mode_id inconnus ou « auto » sont ignorés.
    """
    try:
        import core
        import modes_registry
        import licensing
        rules = []
        if licensing.has("custom_modes"):
            for cm in core.CFG.get("custom_modes") or []:
                try:
                    toks = core.clean_tokens(cm.get("match"))
                    if toks and str(cm.get("prompt") or "").strip() \
                            and str(cm.get("id") or "").strip():
                        rules.append((f"custom:{cm['id']}", toks))
                except Exception:
                    continue            # entrée mal formée → ignorée
        if licensing.has("custom_auto_rules"):
            valid = set(modes_registry.mode_ids()) - {"auto"}
            for mode_id, toks in (core.CFG.get("auto_rules") or {}).items():
                if mode_id in valid:
                    toks = core.clean_tokens(toks)
                    if toks:
                        rules.append((mode_id, toks))
        return rules or None
    except Exception:
        return None


def custom_mode(cid):
    """Mode sur mesure par id (config `custom_modes`), ou None si absent ou
    sans prompt. Défensif — utilisé par app._resolve_prompt au collage."""
    try:
        import core
        modes = core.CFG.get("custom_modes") or []
    except Exception:
        return None
    for cm in modes:
        try:                            # une entrée mal formée n'en masque pas d'autres
            if str(cm.get("id")) == str(cid) \
                    and str(cm.get("prompt") or "").strip():
                return cm
        except Exception:
            continue
    return None


def current_mode():
    """Résout le mode d'après la fenêtre RÉELLE au premier plan (Windows).
    Repli sur le défaut si winext est indisponible OU si la résolution lève
    (garantie « jamais de plantage » : resolve reste dans le try)."""
    try:
        import winext
        return resolve(winext.active_window_title(),
                       winext.active_process_name(), _user_rules())
    except Exception:
        return DEFAULT_ID
