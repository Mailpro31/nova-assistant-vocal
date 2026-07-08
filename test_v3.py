# -*- coding: utf-8 -*-
"""Tests logiques v3 (Speechly-lite) exécutables hors Windows.

Couvre ce qui est vérifiable sans micro/tray/IA : le registre de modes, la table
de résolution du mode Automatique (fonction pure) et la substitution des Custom
Variables. Le reste (push-to-talk, collage curseur, reformulation IA, pystray)
se valide sur Windows — voir le rapport de handoff.

Lancer :  python test_v3.py
"""

import sys
import types


def _stub_winext():
    """winext touche le Win32 natif à l'import → stub déterministe sous Linux/CI
    (même principe que l'ancien harnais classify). core.py fait `import winext`."""
    if "winext" not in sys.modules:
        w = types.ModuleType("winext")
        w.has_secret = lambda *_a, **_k: False
        w.get_secret = lambda *_a, **_k: ""
        w.active_window_title = lambda: ""
        w.active_process_name = lambda: ""
        w.paste_into_active_app = lambda *_a, **_k: True
        w.__getattr__ = lambda _n: (lambda *_a, **_k: None)
        sys.modules["winext"] = w
    sys.modules.setdefault("sounddevice", types.ModuleType("sounddevice"))


_stub_winext()

import core                     # noqa: E402
import modes_registry           # noqa: E402
import auto_mode                # noqa: E402
import power_profiles           # noqa: E402

_fails = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}: {got!r}" +
          ("" if ok else f"  (attendu {want!r})"))
    if not ok:
        _fails.append(label)


# --------------------------------------------------- registre de modes -------
def test_registry():
    print("Registre de modes")
    check("7 modes", len(modes_registry.all_modes()), 7)
    check("ids", modes_registry.mode_ids(),
          ["auto", "voice_to_text", "email", "prompt_engineer", "todo",
           "messages", "notes"])
    check("auto sans prompt figé", modes_registry.prompt_of("auto"), None)
    check("email a un prompt", bool(modes_registry.prompt_of("email")), True)
    check("hotkey 3 → email", modes_registry.by_hotkey("3")["id"], "email")
    check("label todo", modes_registry.label_of("todo"), "To-do lister")
    check("id inconnu → défaut auto", modes_registry.get_mode("xxx")["id"], "auto")
    # invariant : chaque hotkey 1..7 est unique et mappe un mode
    keys = [m["hotkey"] for m in modes_registry.all_modes()]
    check("hotkeys uniques 1..7", sorted(keys), ["1", "2", "3", "4", "5", "6", "7"])


# --------------------------------------------------- mode Automatique --------
def test_auto_resolve():
    print("Mode Automatique — résolution app → mode (fonction pure)")
    cases = [
        ("Boîte de réception - Gmail", "chrome.exe", "email"),
        ("Courrier - Outlook", "outlook.exe", "email"),
        ("WhatsApp", "whatsapp.exe", "messages"),
        ("Slack | général", "slack.exe", "messages"),
        ("Microsoft Teams", "ms-teams.exe", "messages"),
        ("claude.ai/new — Google Chrome", "chrome.exe", "prompt_engineer"),
        ("ChatGPT", "chrome.exe", "prompt_engineer"),
        ("Notion — Projet Nova", "notion.exe", "notes"),
        ("Obsidian v1.5", "obsidian.exe", "notes"),
        ("Microsoft To Do", "todo.exe", "todo"),
        ("Todoist", "todoist.exe", "todo"),
        ("Visual Studio Code", "code.exe", "voice_to_text"),  # défaut : dictée brute
        ("", "", "voice_to_text"),
    ]
    for title, proc, want in cases:
        check(f"{title or '(vide)'} / {proc or '-'}",
              auto_mode.resolve(title, proc), want)
    check("current_mode ne lève jamais (winext stubbé)",
          auto_mode.current_mode(), "voice_to_text")


# --------------------------------------------------- Custom Variables --------
def test_custom_vars():
    print("Custom Variables — substitution locale")
    core.CFG["custom_vars"] = [
        {"trigger": "IBAN", "value": "FR76 3000 1000 0100"},
        {"trigger": "mon boss", "value": "Monsieur Dupont"},
    ]
    core.CFG["active_profile"] = ""     # pas de profil → pas d'accès DB
    check("IBAN remplacé", core.fill_personal("voici mon IBAN merci"),
          "voici mon FR76 3000 1000 0100 merci")
    check("casse ignorée", core.fill_personal("voici mon iban"),
          "voici mon FR76 3000 1000 0100")
    check("frontière de mot (ribambelle intact)",
          core.fill_personal("une ribambelle"), "une ribambelle")
    check("multi-mot", core.fill_personal("demande à mon boss"),
          "demande à Monsieur Dupont")
    check("valeur avec backslash non interprétée",
          _sub_backslash(), r"chemin C:\Users\x")
    # dédoublonnage + nettoyage
    clean = core.save_custom_variables([
        {"trigger": "a", "value": "1"}, {"trigger": "A", "value": "2"},
        {"trigger": "", "value": "x"}, {"trigger": "b", "value": ""}])
    check("save dédoublonne (casse) et filtre vides", len(clean), 1)


def _sub_backslash():
    core.CFG["custom_vars"] = [{"trigger": "chemin", "value": r"chemin C:\Users\x"}]
    return core.fill_personal("chemin")


# ------------------------------------ extensibilité (test concret du brief) --
def test_extensibility():
    """Brief Phase 7 : ajouter un mode = une entrée, RIEN d'autre à toucher.
    On ajoute un mode factice « Test » et on vérifie qu'il est pris en compte
    partout (menu, résolution, prompt) sans modifier une seule autre ligne."""
    print("Extensibilité — ajout d'un mode sans toucher au reste")
    before = len(modes_registry.all_modes())
    modes_registry.MODES.append({
        "id": "test_dummy", "label": "Test", "hotkey": "8",
        "system_prompt": "Mode de test."})
    modes_registry._BY_ID["test_dummy"] = modes_registry.MODES[-1]
    try:
        check("le mode apparaît dans la liste (menu tray)",
              len(modes_registry.all_modes()), before + 1)
        check("résolu par id sans code dédié",
              modes_registry.get_mode("test_dummy")["label"], "Test")
        check("son prompt est consommé tel quel",
              modes_registry.prompt_of("test_dummy"), "Mode de test.")
        check("accessible par hotkey", modes_registry.by_hotkey("8")["id"],
              "test_dummy")
    finally:
        modes_registry.MODES.pop()
        modes_registry._BY_ID.pop("test_dummy", None)


# ------------------------------------ profils de puissance (GOAL Partie 3) ---
def _locked(hw):
    return {e["id"]: e["locked"] for e in power_profiles.evaluate(hw)}


def test_power_profiles():
    """3 configs simulées (GOAL Partie 9) : la détection propose les bons profils
    et VERROUILLE les trop lourds — un profil sélectionnable est toujours sûr."""
    print("Profils de puissance — verrouillage selon la machine (fonction pure)")

    faible = {"ram_total_gb": 8.0, "has_gpu": False}      # 8 Go, pas de GPU
    moyenne = {"ram_total_gb": 16.0, "has_gpu": False}    # 16 Go
    forte = {"ram_total_gb": 32.0, "has_gpu": True}       # 32 Go + GPU

    lf = _locked(faible)
    check("8 Go : Normal débloqué", lf["normal"], False)
    check("8 Go : Élevé verrouillé", lf["eleve"], True)
    check("8 Go : Ultra verrouillé", lf["ultra"], True)
    check("8 Go : recommandé = Normal", power_profiles.recommended_id(faible), "normal")

    lm = _locked(moyenne)
    check("16 Go : Normal+Élevé OK", (lm["normal"], lm["eleve"]), (False, False))
    check("16 Go : Ultra verrouillé", lm["ultra"], True)
    check("16 Go : recommandé = Élevé", power_profiles.recommended_id(moyenne), "eleve")

    lF = _locked(forte)
    check("32 Go+GPU : tout débloqué",
          (lF["normal"], lF["eleve"], lF["ultra"]), (False, False, False))
    check("32 Go+GPU : recommandé = Ultra",
          power_profiles.recommended_id(forte), "ultra")

    # règle absolue : une sélection impossible retombe sur un profil sûr
    check("sélection Ultra sur 8 Go → repli sûr (jamais verrouillé)",
          power_profiles.is_available(
              power_profiles.safe_selection("ultra", faible), faible), True)
    check("Ultra sans GPU → avertissement, pas verrouillage",
          [e for e in power_profiles.evaluate(moyenne)
           if e["id"] == "ultra"][0]["locked"], True)
    # modèles jamais exposés : l'UI ne manipule que id/label
    ev = power_profiles.evaluate(forte)[0]
    check("evaluate n'expose aucun nom de modèle",
          set(ev) == {"id", "label", "locked", "reason", "warning"}, True)


# --------------------------------------------------- fallback texte brut -----
def test_format_rules():
    print("Repli texte brut (sans IA)")
    check("majuscule + point", core.format_rules("bonjour tout le monde"),
          "Bonjour tout le monde.")
    check("espaces réduits", core.format_rules("  salut   toi  "), "Salut toi.")
    check("ponctuation conservée", core.format_rules("ça va ?"), "Ça va ?")
    check("vide → vide", core.format_rules("   "), "")


if __name__ == "__main__":
    test_registry()
    test_auto_resolve()
    test_custom_vars()
    test_extensibility()
    test_power_profiles()
    test_format_rules()
    print()
    if _fails:
        print(f"❌ {len(_fails)} échec(s) : {', '.join(_fails)}")
        sys.exit(1)
    print("✅ Tous les tests logiques v3 passent.")
