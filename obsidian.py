# -*- coding: utf-8 -*-
"""
Intégration Obsidian (portée de JARVIS) : notes markdown dans un coffre
local. Créer, lire, supprimer, lister, chercher — 100 % local, aucune
requête réseau. Les titres sont assainis (anti path-traversal, caractères
interdits Windows) et le matching tolère la casse et les accents.
"""

import os
import sys
import unicodedata

# caractères interdits dans un nom de fichier Windows
_INTERDITS = '<>:"/\\|?*'

# noms réservés par Windows (CON.md ou con.md posent problème)
_RESERVES = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} \
            | {f"LPT{i}" for i in range(1, 10)}


# ------------------------------------------------------------------ util ----

def _log_err(context, err):
    """Erreurs vers nova.log via core quand il est importable, sinon rien."""
    try:
        import core
        core.log_err(context, err)
    except Exception:
        pass


def _app_dir():
    """Dossier de l'exécutable (winext.APP_DIR, avec repli autonome)."""
    try:
        import winext
        return winext.APP_DIR
    except Exception:
        return os.path.dirname(os.path.abspath(sys.argv[0]))


_fold_cache = {}


def _fold(text):
    """Minuscules sans accents, longueur conservée caractère par caractère :
    les index trouvés dans le texte replié restent valables dans l'original."""
    out = []
    for ch in text:
        v = _fold_cache.get(ch)
        if v is None:
            d = unicodedata.normalize("NFD", ch)
            base = "".join(c for c in d if unicodedata.category(c) != "Mn")
            v = (base or ch)[:1].lower()[:1]
            _fold_cache[ch] = v
        out.append(v)
    return "".join(out)


def _safe_filename(titre):
    """Titre → nom de fichier .md sûr, ou None si rien d'utilisable.
    basename seul + retrait des caractères interdits Windows (anti
    path-traversal), extension .md forcée."""
    name = os.path.basename(str(titre or "").strip())
    name = "".join(c for c in name if c not in _INTERDITS and ord(c) >= 32)
    name = name.strip().rstrip(". ")
    if name.lower().endswith(".md"):
        name = name[:-3].rstrip(". ")
    if not name:
        return None
    if name.upper() in _RESERVES:
        name += "_"
    return name + ".md"


def _chemin_note(titre):
    """Titre → chemin d'une note existante du coffre (matching tolérant :
    casse et accents ignorés), ou None si elle n'existe pas."""
    fname = _safe_filename(titre)
    if not fname:
        return None
    vault = vault_path()
    exact = os.path.join(vault, fname)
    if os.path.isfile(exact):
        return exact
    cible = _fold(fname[:-3])
    try:
        for entry in os.scandir(vault):
            if entry.is_file() and entry.name.lower().endswith(".md") \
                    and _fold(entry.name[:-3]) == cible:
                return entry.path
    except OSError as e:
        _log_err("obsidian._chemin_note", e)
    return None


# ----------------------------------------------------------------- coffre ---

def vault_path():
    """Chemin du coffre : config 'obsidian_vault' si définie, sinon dossier
    ObsidianVault à côté de l'exécutable. Créé s'il n'existe pas."""
    perso = ""
    try:
        import core
        perso = str(core.CFG.get("obsidian_vault") or "").strip()
    except Exception:
        pass
    if perso:
        path = os.path.expanduser(perso)
        try:
            os.makedirs(path, exist_ok=True)
            return path
        except OSError as e:
            _log_err("obsidian.vault_path", e)  # config invalide → repli
    path = os.path.join(_app_dir(), "ObsidianVault")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        _log_err("obsidian.vault_path", e)
    return path


# ------------------------------------------------------------------ notes ---

def creer_note(titre, contenu):
    """Crée une note markdown dans le coffre (ou remplace la note du même
    titre, matching tolérant). Retourne (ok, message)."""
    fname = _safe_filename(titre)
    if not fname:
        return False, "Titre de note invalide"
    filepath = _chemin_note(titre) or os.path.join(vault_path(), fname)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(str(contenu or ""))
        nom = os.path.basename(filepath)[:-3]
        return True, f"Note « {nom} » enregistrée dans le coffre Obsidian"
    except OSError as e:
        _log_err("obsidian.creer_note", e)
        return False, "Impossible d'écrire la note dans le coffre"


def lire_note(titre):
    """Lit une note du coffre (titre tolérant à la casse et aux accents).
    Retourne (True, contenu) ou (False, message)."""
    filepath = _chemin_note(titre)
    if not filepath:
        return False, f"Aucune note « {titre} » dans le coffre"
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return True, f.read()
    except OSError as e:
        _log_err("obsidian.lire_note", e)
        return False, "Impossible de lire la note"


def supprimer_note(titre):
    """Supprime une note du coffre (titre tolérant). Retourne (ok, message)."""
    filepath = _chemin_note(titre)
    if not filepath:
        return False, f"Aucune note « {titre} » dans le coffre"
    try:
        nom = os.path.basename(filepath)[:-3]
        os.remove(filepath)
        return True, f"Note « {nom} » supprimée du coffre"
    except OSError as e:
        _log_err("obsidian.supprimer_note", e)
        return False, "Impossible de supprimer la note"


def lister_notes(limit=15):
    """Notes du coffre, plus récentes d'abord :
    [{titre, taille, mtime}], au plus `limit` entrées."""
    notes = []
    try:
        for entry in os.scandir(vault_path()):
            if entry.is_file() and entry.name.lower().endswith(".md"):
                st = entry.stat()
                notes.append({"titre": entry.name[:-3],
                              "taille": st.st_size,
                              "mtime": st.st_mtime})
    except OSError as e:
        _log_err("obsidian.lister_notes", e)
    notes.sort(key=lambda n: n["mtime"], reverse=True)
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 15
    return notes[:limit] if limit > 0 else notes


def chercher(terme):
    """Recherche tolérante (casse, accents) dans les titres et le contenu.
    Retourne [(titre, extrait)] ; extrait vide si seul le titre correspond,
    sinon fenêtre -40/+80 autour de la première occurrence."""
    q = _fold(str(terme or "").strip())
    if not q:
        return []
    resultats = []
    try:
        entries = [e for e in os.scandir(vault_path())
                   if e.is_file() and e.name.lower().endswith(".md")]
    except OSError as e:
        _log_err("obsidian.chercher", e)
        return []
    for entry in entries:
        titre = entry.name[:-3]
        trouve = q in _fold(titre)
        extrait = ""
        try:
            with open(entry.path, "r", encoding="utf-8", errors="replace") as f:
                contenu = f.read()
            idx = _fold(contenu).find(q)
            if idx >= 0:
                trouve = True
                debut = max(0, idx - 40)
                fin = min(len(contenu), idx + 80)
                extrait = "..." + contenu[debut:fin].replace("\n", " ").strip() + "..."
        except OSError:
            pass  # note illisible → on garde l'éventuel match sur le titre
        if trouve:
            resultats.append((titre, extrait))
    return resultats
