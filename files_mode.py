# -*- coding: utf-8 -*-
"""
Gestion de fichiers à la voix (portée de JARVIS, TechEnClair) :
trier, ranger, chercher, lister. Tout est local et non destructif
(déplacements dans des sous-dossiers, jamais de suppression).
"""

import os
import shutil

# dossiers connus : « ouvre / trie mes téléchargements »
FOLDERS = {
    "telechargements": "Downloads", "telechargement": "Downloads",
    "downloads": "Downloads", "bureau": "Desktop", "desktop": "Desktop",
    "documents": "Documents", "images": "Pictures", "photos": "Pictures",
    "videos": "Videos", "musique": "Music", "music": "Music",
}

# catégories de tri (extension → sous-dossier)
CATEGORIES = {
    "Images": (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".heic"),
    "Documents": (".pdf", ".doc", ".docx", ".txt", ".odt", ".rtf", ".xls",
                  ".xlsx", ".ppt", ".pptx", ".csv", ".md"),
    "Videos": (".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"),
    "Musique": (".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"),
    "Archives": (".zip", ".rar", ".7z", ".tar", ".gz"),
    "Programmes": (".exe", ".msi", ".bat", ".apk"),
}


# variantes françaises réelles des dossiers + base OneDrive : sur un profil
# redirigé (« OneDrive - IPSA »), Bureau/Documents/Images vivent DANS OneDrive
_FR_NAMES = {
    "Downloads": ("Downloads", "Téléchargements", "Telechargements"),
    "Desktop": ("Desktop", "Bureau"),
    "Documents": ("Documents",),
    "Pictures": ("Pictures", "Images"),
    "Videos": ("Videos", "Vidéos"),
    "Music": ("Music", "Musique"),
}


def resolve_folder(name):
    """Nom vocal → chemin absolu du dossier (ou None). Teste %OneDrive%
    puis le profil utilisateur, avec les noms anglais ET français."""
    home = os.path.expanduser("~")
    key = (name or "").strip().lower()
    sub = FOLDERS.get(key)
    if not sub:
        return None
    bases = [b for b in (os.environ.get("OneDrive", ""), home) if b]
    for base in bases:
        for cand in _FR_NAMES.get(sub, (sub,)):
            p = os.path.join(base, cand)
            if os.path.isdir(p):
                return p
    return home


def _category(ext):
    ext = ext.lower()
    for cat, exts in CATEGORIES.items():
        if ext in exts:
            return cat
    return "Autres"


def sort_folder(path):
    """Range les fichiers du dossier dans des sous-dossiers par catégorie."""
    if not path or not os.path.isdir(path):
        return False, "Dossier introuvable"
    moved, errors = 0, 0
    for entry in list(os.scandir(path)):
        if entry.is_dir():
            continue
        try:
            cat = _category(os.path.splitext(entry.name)[1])
            dest = os.path.join(path, cat)
            os.makedirs(dest, exist_ok=True)
            target = os.path.join(dest, entry.name)
            if os.path.abspath(target) == os.path.abspath(entry.path):
                continue
            # jamais écraser : suffixe (2), (3)… en cas de collision
            base, ext = os.path.splitext(entry.name)
            i = 2
            while os.path.exists(target):
                target = os.path.join(dest, f"{base} ({i}){ext}")
                i += 1
            shutil.move(entry.path, target)
            moved += 1
        except Exception:
            errors += 1
    if moved == 0 and errors == 0:
        return True, "Ce dossier est déjà rangé"
    msg = f"{moved} fichier{'s' if moved > 1 else ''} rangé{'s' if moved > 1 else ''} par catégorie"
    if errors:
        msg += f" ({errors} ignoré{'s' if errors > 1 else ''})"
    return True, msg


def find_file(query, path=None):
    """Cherche un fichier par nom (récursif, ~2 niveaux). Retourne un chemin."""
    roots = [path] if path else [resolve_folder(d) for d in
                                 ("bureau", "telechargements", "documents")]
    q = (query or "").strip().lower()
    if not q:
        return None
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for dirpath, dirs, files in os.walk(root):
            depth = dirpath[len(root):].count(os.sep)
            if depth >= 2:
                dirs[:] = []
                continue
            for f in files:
                if q in f.lower():
                    return os.path.join(dirpath, f)
    return None


def list_folder(path, limit=12):
    """Résumé du contenu : n fichiers, n dossiers, quelques noms."""
    if not path or not os.path.isdir(path):
        return None
    files, dirs = [], []
    for e in os.scandir(path):
        (dirs if e.is_dir() else files).append(e.name)
    return {"files": files, "dirs": dirs,
            "sample": (dirs + files)[:limit]}


_MOIS_FR = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet",
            "août", "septembre", "octobre", "novembre", "décembre")


def _move_safe(entry_path, dest, name):
    """Déplace sans JAMAIS écraser : suffixe (2), (3)… en cas d'homonyme."""
    os.makedirs(dest, exist_ok=True)
    target = os.path.join(dest, name)
    if os.path.abspath(target) == os.path.abspath(entry_path):
        return False
    base, ext = os.path.splitext(name)
    i = 2
    while os.path.exists(target):
        target = os.path.join(dest, f"{base} ({i}){ext}")
        i += 1
    shutil.move(entry_path, target)
    return True


def sort_folder_by_date(path, with_type=False):
    """Range par « année/mois » en français (JARVIS : jamais strftime %B,
    dépendant de la locale). with_type : catégorie PUIS année."""
    if not path or not os.path.isdir(path):
        return False, "Dossier introuvable"
    import time as _t
    moved, errors = 0, 0
    for entry in list(os.scandir(path)):
        if entry.is_dir():
            continue
        try:
            t = _t.localtime(entry.stat().st_mtime)
            if with_type:
                cat = _category(os.path.splitext(entry.name)[1])
                dest = os.path.join(path, cat, str(t.tm_year))
            else:
                dest = os.path.join(path, str(t.tm_year), _MOIS_FR[t.tm_mon - 1])
            if _move_safe(entry.path, dest, entry.name):
                moved += 1
        except Exception:
            errors += 1
    if moved == 0 and errors == 0:
        return True, "Ce dossier est déjà rangé"
    msg = (f"{moved} fichier{'s' if moved > 1 else ''} "
           f"rangé{'s' if moved > 1 else ''} par date")
    if errors:
        msg += f" ({errors} ignoré{'s' if errors > 1 else ''})"
    return True, msg


def folder_summary(path):
    """« Qu'y a-t-il dans mes téléchargements ? » → répartition par catégorie."""
    if not path or not os.path.isdir(path):
        return None
    counts = {}
    dirs = 0
    for e in os.scandir(path):
        if e.is_dir():
            dirs += 1
            continue
        cat = _category(os.path.splitext(e.name)[1])
        counts[cat] = counts.get(cat, 0) + 1
    return {"dirs": dirs, "counts": counts, "total": sum(counts.values())}


def make_folder(name, base="documents"):
    """Crée un dossier (défaut : Documents), jamais d'écrasement.
    Retourne le chemin créé, ou None."""
    root = resolve_folder(base) or resolve_folder("documents")
    if not root:
        return None
    clean = "".join(c for c in os.path.basename(name.strip())
                    if c not in '<>:"/\\|?*').strip() or "Nouveau dossier"
    target = os.path.join(root, clean)
    i = 2
    while os.path.exists(target):
        target = os.path.join(root, f"{clean} ({i})")
        i += 1
    os.makedirs(target)
    return target


def _within_home(p):
    """Garde-fou (actions IA) : uniquement le profil utilisateur / OneDrive."""
    p = os.path.abspath(p)
    for base in (os.path.expanduser("~"), os.environ.get("OneDrive", "")):
        if not base:
            continue
        base = os.path.abspath(base)
        try:
            if os.path.commonpath([p, base]) == base:
                return True
        except ValueError:
            continue
    return False


def safe_rename(src, new_name):
    """Renomme un fichier — jamais d'écrasement, borné au profil (action IA)."""
    if not src or not _within_home(src) or not os.path.exists(src):
        return False
    clean = "".join(c for c in os.path.basename(new_name.strip())
                    if c not in '<>:"/\\|?*').strip()
    if not clean:
        return False
    if "." not in clean and "." in os.path.basename(src):
        clean += os.path.splitext(src)[1]
    dest = os.path.join(os.path.dirname(src), clean)
    if os.path.exists(dest):
        return False
    os.rename(src, dest)
    return True


def safe_move(src, dest_folder_name):
    """Déplace un fichier vers un dossier connu — collision-safe, borné (IA)."""
    dest_dir = resolve_folder(dest_folder_name)
    if not src or not dest_dir or not _within_home(src) \
            or not os.path.exists(src):
        return False
    return _move_safe(src, dest_dir, os.path.basename(src))
