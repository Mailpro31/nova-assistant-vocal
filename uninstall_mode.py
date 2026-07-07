# -*- coding: utf-8 -*-
"""
Désinstallation de programmes à la voix (porté de JARVIS, TechEnClair) :
lister les programmes installés, retrouver celui demandé, lancer son
désinstallateur officiel. Aucune suppression directe de fichiers ni de
clés de registre : on ne fait que démarrer le désinstallateur du programme.
La confirmation est toujours faite par l'interface AVANT d'appeler
uninstall(), jamais à la voix.
"""

import re
import subprocess
import winreg

# les 3 emplacements du registre où Windows référence les programmes
_REG_PATHS = (
    ("hklm", winreg.HKEY_LOCAL_MACHINE,
     r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("hklm32", winreg.HKEY_LOCAL_MACHINE,
     r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("hkcu", winreg.HKEY_CURRENT_USER,
     r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
)


def _log_err(contexte, e):
    """Trace l'erreur via core si disponible, sinon reste silencieux."""
    try:
        import core
        core.log_err(contexte, e)
    except Exception:
        pass


def _normalize(text):
    """Minuscules, sans accents ni ponctuation, espaces réduits."""
    import unicodedata
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _format_size(kb):
    """Taille du registre (EstimatedSize, en Ko) → texte lisible ('' si inconnue)."""
    try:
        kb = int(kb)
    except (TypeError, ValueError):
        return ""
    if kb <= 0:
        return ""
    if kb < 1024:
        return f"{kb} Ko"
    mo = kb / 1024
    if mo < 1024:
        return f"{mo:.1f} Mo".replace(".", ",")
    return f"{mo / 1024:.2f} Go".replace(".", ",")


def _read_value(key, name):
    """Lit une valeur d'une clé de registre, '' si absente ou illisible."""
    try:
        value, _ = winreg.QueryValueEx(key, name)
        return value
    except OSError:
        return ""


def list_programs():
    """Énumère les programmes installés depuis le registre Windows.

    Parcourt les trois emplacements (HKLM, HKLM 32 bits, HKCU), écarte
    les composants système (SystemComponent=1, entrées sans DisplayName
    ou sans désinstallateur), déduplique par nom et trie par nom.
    Retourne une liste de dicts :
    {id, nom, editeur, taille, version, uninstall_string}
    """
    programs = []
    seen = set()
    for tag, hive, path in _REG_PATHS:
        try:
            key = winreg.OpenKey(hive, path, 0, winreg.KEY_READ)
        except OSError:
            continue  # vue absente sur cette machine (ex : WOW6432Node)
        try:
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    sub_name = winreg.EnumKey(key, i)
                    sub = winreg.OpenKey(key, sub_name, 0, winreg.KEY_READ)
                except OSError:
                    continue
                try:
                    nom = str(_read_value(sub, "DisplayName")).strip()
                    if not nom:
                        continue  # entrée interne, rien à montrer
                    if str(_read_value(sub, "SystemComponent")).strip() == "1":
                        continue  # composant système, jamais listé
                    uninstall_string = str(
                        _read_value(sub, "UninstallString")).strip()
                    if not uninstall_string:
                        continue  # aucun désinstallateur à lancer
                    cle = _normalize(nom)
                    if not cle or cle in seen:
                        continue  # doublon (présent dans plusieurs vues)
                    seen.add(cle)
                    programs.append({
                        "id": f"{tag}:{sub_name}",
                        "nom": nom,
                        "editeur": str(_read_value(sub, "Publisher")).strip(),
                        "taille": _format_size(_read_value(sub, "EstimatedSize")),
                        "version": str(_read_value(sub, "DisplayVersion")).strip(),
                        "uninstall_string": uninstall_string,
                    })
                finally:
                    winreg.CloseKey(sub)
        except OSError as e:
            _log_err("uninstall_mode.list_programs", e)
        finally:
            winreg.CloseKey(key)
    programs.sort(key=lambda p: p["nom"].lower())
    return programs


def find_program(query):
    """Retrouve un programme installé à partir d'un nom approximatif.

    Essaie dans l'ordre : nom exact (normalisé), sous-chaîne
    (« zoom » trouve « Zoom Workplace »), puis rapprochement difflib
    pour tolérer fautes de frappe et transcription vocale.
    Retourne le dict du programme, ou None.
    """
    q = _normalize(query)
    if not q:
        return None
    programs = list_programs()
    if not programs:
        return None
    noms = [_normalize(p["nom"]) for p in programs]

    # correspondance exacte
    for p, n in zip(programs, noms):
        if n == q:
            return p

    # sous-chaîne, dans les deux sens : le nom le plus court gagne
    candidats = [(p, n) for p, n in zip(programs, noms)
                 if n and (q in n or n in q)]
    if candidats:
        return min(candidats, key=lambda c: len(c[1]))[0]

    # rapprochement tolérant en dernier recours
    import difflib
    proches = difflib.get_close_matches(q, noms, n=1, cutoff=0.6)
    if proches:
        return programs[noms.index(proches[0])]
    return None


def uninstall(prog_id):
    """Lance le désinstallateur officiel du programme, sans attendre.

    La confirmation a déjà été donnée par l'interface : ici on ne fait
    que démarrer le désinstallateur, qui gère lui-même la suite (fenêtre,
    élévation, suppression). Aucune suppression de fichiers ni de clés
    de registre n'est faite par Nova. Accepte l'id retourné par
    list_programs()/find_program() (ou directement le dict programme).
    Retourne True si le lancement a réussi.
    """
    if isinstance(prog_id, dict):
        prog = prog_id
    else:
        prog = None
        for p in list_programs():
            if p["id"] == prog_id:
                prog = p
                break
    if not prog or not prog.get("uninstall_string"):
        return False

    cmd = prog["uninstall_string"]
    try:
        guid = re.search(
            r"\{[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}\}", cmd)
        if "msiexec" in cmd.lower() and guid:
            # installateur Windows (MSI) : mode désinstallation explicite,
            # car certaines entrées enregistrent « /I » (réparation)
            subprocess.Popen(["MsiExec.exe", "/x", guid.group(0)])
        else:
            # désinstallateur classique : la chaîne contient déjà
            # l'exécutable et ses arguments (pas de shell)
            subprocess.Popen(cmd)
        return True
    except Exception as e:
        _log_err("uninstall_mode.uninstall", e)
        return False
