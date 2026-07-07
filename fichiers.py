# -*- coding: utf-8 -*-
"""
Gestion de fichiers à la voix (portée de JARVIS v8) : ouvrir, lister,
trier par type ou par date, chercher. Ne touche qu'aux fichiers de
premier niveau du dossier visé, jamais aux sous-dossiers.
"""

import os
import shutil
import subprocess
import time

DOSSIERS = {
    "telechargements": "Downloads", "telechargement": "Downloads",
    "downloads": "Downloads",
    "documents": "Documents", "document": "Documents",
    "bureau": "Desktop", "desktop": "Desktop",
    "images": "Pictures", "photos": "Pictures",
    "videos": "Videos", "video": "Videos",
    "musique": "Music", "musiques": "Music",
}

CATEGORIES = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp",
               ".heic", ".ico", ".tiff"},
    "Documents": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                  ".txt", ".odt", ".ods", ".csv", ".rtf", ".md", ".epub"},
    "Vidéos": {".mp4", ".