# -*- coding: utf-8 -*-
"""Golden master de modes.classify().

But : garantir qu'un refactor de classify() ne change RIEN à la classification.
On fige la sortie de classify() sur un large corpus (test_classify_corpus.json)
dans test_classify_golden.json, puis on compare à chaque exécution.

  Régénérer la référence :  python test_classify_golden.py --generate
  Vérifier (défaut / CI)  :  python test_classify_golden.py

classify() étant de la logique texte quasi pure, on l'exécute hors Windows via
_classify_harness (stub winext déterministe) + une config et une base SQLite
temporaire fixes, pour un résultat 100 % reproductible.
"""

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "test_classify_corpus.json")
GOLDEN = os.path.join(HERE, "test_classify_golden.json")

# Config FIXE : exerce un maximum de branches (domotique, routines, apps custom,
# urgence). Les valeurs exactes importent peu — seule leur stabilité compte, car
# on compare classify() à elle-même avant/après refactor.
CONFIG = {
    "modes": {"emergency": {"trigger": "urgence"}},
    "custom_apps": {
        "mon site": "https://exemple.fr",
        "boulot": "C:\\\\Travail",
    },
    "routines": {
        "bonne nuit": {"steps": []},
        "mode cinema": {"steps": []},
    },
    "ha_entities": {
        "salon": {"type": "light", "id": "light.salon"},
        "chambre": {"type": "light", "id": "light.chambre"},
        "cuisine": {"type": "switch", "id": "switch.cuisine"},
        "prise chambre": {"type": "switch", "id": "switch.prise_chambre"},
        "chauffage salon": {"type": "climate", "id": "climate.salon"},
        "cinema": {"type": "scene", "id": "scene.cinema"},
        "entree": {"type": "lock", "id": "lock.entree"},
        "maison": {"type": "alarm", "id": "alarm_control_panel.maison"},
        "robot": {"type": "vacuum", "id": "vacuum.robot"},
        "temperature chambre": {"type": "sensor", "id": "sensor.temp_chambre"},
        "telephone": {"type": "battery", "id": "sensor.batt_phone"},
    },
}


# dossier personnel FIGÉ : files_mode.resolve_folder() renvoie os.path.expanduser
# ("~") pour « ouvre mes téléchargements » ; sans ce gel, la sortie dépendrait
# du compte (/root en local, /home/runner en CI). Valeur arbitraire mais stable.
_FIXED_HOME = "/nova-golden-home"


def _setup():
    """Environnement déterministe (dossier perso figé, stubs, base SQLite
    temporaire, config fixe) puis renvoie le module modes."""
    os.environ["HOME"] = _FIXED_HOME
    os.environ["USERPROFILE"] = _FIXED_HOME
    os.environ.pop("OneDrive", None)
    import _classify_harness
    modes = _classify_harness.load_modes()
    import core
    import storage
    # base temporaire (évite de polluer le dépôt, garantit un état vide stable)
    storage._DB = os.path.join(tempfile.gettempdir(), "nova_golden_test.db")
    if os.path.exists(storage._DB):
        os.remove(storage._DB)
    storage._conn = None
    core.CFG.update(CONFIG)
    return modes


def _run(modes):
    corpus = json.load(open(CORPUS, encoding="utf-8"))
    out = {}
    for phrase in corpus:
        res = modes.classify(phrase)
        # tuples -> listes pour un JSON stable ; None reste None
        out[phrase] = list(res) if isinstance(res, tuple) else res
    return out


def generate():
    modes = _setup()
    out = _run(modes)
    json.dump(out, open(GOLDEN, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, sort_keys=True)
    print(f"Référence écrite : {len(out)} phrases -> {os.path.basename(GOLDEN)}")


def verify():
    modes = _setup()
    got = _run(modes)
    golden = json.load(open(GOLDEN, encoding="utf-8"))
    diffs = []
    for phrase, expected in golden.items():
        actual = got.get(phrase, "<absente>")
        if actual != expected:
            diffs.append((phrase, expected, actual))
    # phrases nouvelles non couvertes par la référence
    extra = [p for p in got if p not in golden]
    if diffs:
        print(f"ÉCHEC : {len(diffs)} divergence(s) classify() vs référence :\n")
        for phrase, exp, act in diffs[:50]:
            print(f"  {phrase!r}\n    référence : {exp}\n    obtenu    : {act}")
        if len(diffs) > 50:
            print(f"  … et {len(diffs) - 50} autres")
        return 1
    if extra:
        print(f"ATTENTION : {len(extra)} phrase(s) du corpus absente(s) de la "
              f"référence — régénérez avec --generate.")
        return 1
    print(f"OK : {len(golden)} phrases classées à l'identique de la référence.")
    return 0


if __name__ == "__main__":
    if "--generate" in sys.argv:
        generate()
    else:
        sys.exit(verify())
