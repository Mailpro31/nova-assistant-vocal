# -*- coding: utf-8 -*-
"""Amorçage pour exercer modes.classify() hors Windows.

classify() est de la logique texte quasi pure ; sa seule dépendance native
est winext.find_window(). On stube winext (et l'audio) de façon DÉTERMINISTE
pour pouvoir importer modes et lancer classify() sur Linux/CI. Comme le golden
master compare classify() à elle-même (avant/après refactor) sous des stubs
identiques, la valeur exacte des stubs n'importe pas — seul compte qu'elle soit
stable entre les deux exécutions.
"""

import sys
import types


def _install_stubs():
    # winext : un seul point d'entrée touché par classify() → find_window.
    # On renvoie None (aucune fenêtre trouvée), valeur stable et déterministe.
    if "winext" not in sys.modules:
        winext = types.ModuleType("winext")

        def _find_window(_title):
            return None

        winext.find_window = _find_window

        # Filet : toute autre fonction winext éventuellement touchée renvoie
        # un no-op déterministe (jamais appelée par classify aujourd'hui, mais
        # protège le harnais d'un changement futur).
        def _noop(*_a, **_k):
            return None

        winext.__getattr__ = lambda _name: _noop
        sys.modules["winext"] = winext

    # sounddevice n'est importé qu'à l'usage micro (jamais par classify), mais
    # on le neutralise au cas où un import remonterait.
    sys.modules.setdefault("sounddevice", types.ModuleType("sounddevice"))


def load_modes():
    """Installe les stubs puis renvoie le module modes réel."""
    _install_stubs()
    import modes
    return modes
