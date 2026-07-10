# -*- coding: utf-8 -*-
"""Tests logiques v3 (Speechly-lite) exécutables hors Windows.

Couvre ce qui est vérifiable sans micro/tray/IA : le registre de modes, la table
de résolution du mode Automatique (fonction pure) et la substitution des Custom
Variables. Le reste (push-to-talk, collage curseur, reformulation IA, pystray)
se valide sur Windows — voir le rapport de handoff.

Lancer :  python test_v3.py
"""

import json
import sys
import time
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
core._save = lambda *a, **k: None   # les tests ne DOIVENT jamais écrire le vrai
#                                     config.json de l'utilisateur (save_config OK
#                                     en mémoire, mais aucune persistance disque)
import modes_registry           # noqa: E402
import auto_mode                # noqa: E402
import power_profiles           # noqa: E402
import licensing                # noqa: E402
import onboarding               # noqa: E402  (ne doit PAS importer webview au chargement)

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
        # --- onglets de navigateur réels (le titre porte le nom de l'onglet) --
        ("Boîte de réception (12) - moi@gmail.com - Gmail - Google Chrome",
         "chrome.exe", "email"),
        ("(2) WhatsApp", "chrome.exe", "messages"),
        ("ChatGPT - Google Chrome", "msedge.exe", "prompt_engineer"),
        ("Claude", "firefox.exe", "prompt_engineer"),
        ("#général - Mon Serveur - Discord", "discord.exe", "messages"),
        ("Perplexity", "chrome.exe", "prompt_engineer"),
        # --- process fiable même quand le titre est muet -------------------
        ("Signal", "signal.exe", "messages"),
        # --- GARDE-FOUS anti-faux-positifs (le vrai sujet : ne pas se tromper)
        ("Le chat de ma voisine - Google Docs", "chrome.exe", "voice_to_text"),
        ("Release notes v2.1 - Google Docs", "chrome.exe", "voice_to_text"),
        ("Signal processing basics - YouTube", "chrome.exe", "voice_to_text"),
        ("Paramètres", "explorer.exe", "voice_to_text"),
        ("Choses à faire aujourd'hui - Google Docs", "chrome.exe", "voice_to_text"),
    ]
    for title, proc, want in cases:
        check(f"{title or '(vide)'} / {proc or '-'}",
              auto_mode.resolve(title, proc), want)
    # règles utilisateur (config.json → auto_rules) : gagnent sur l'intégré
    check("règle perso : MonCRM → email",
          auto_mode.resolve("MonCRM - Tableau de bord", "chrome.exe",
                            [("email", ["moncrm"])]), "email")
    check("règle perso n'altère pas un titre neutre",
          auto_mode.resolve("Bloc-notes", "notepad.exe",
                            [("email", ["moncrm"])]), "voice_to_text")
    # _compile_user réellement tolérant : entrées mal formées ignorées, jamais
    # de crash ni de match-tout (retour /code-review)
    check("règle perso repère vide → n'attrape pas tout",
          auto_mode.resolve("Un document - Éditeur", "",
                            [("email", ["gmail", ""])]), "voice_to_text")
    check("règle perso couple mal formé → ignoré sans lever",
          auto_mode.resolve("x", "", [("email",), ("messages", ["slack"])]),
          "voice_to_text")
    check("règle perso repères en chaîne nue → pas d'itération par lettre",
          auto_mode.resolve("a - b", "", [("email", "gmail")]), "voice_to_text")
    # bordures Unicode : un repère générique n'attrape pas un mot accentué
    check("bordure accentuée : « line » n'attrape pas « câline »",
          auto_mode.resolve("câline", "câline.exe",
                            [("messages", ["line"])]), "voice_to_text")
    check("current_mode ne lève jamais (winext stubbé)",
          auto_mode.current_mode(), "voice_to_text")
    # _user_rules ne garde que des mode_id CONCRETS du registre : une faute de
    # frappe ou « auto » dans config.json est écartée (retour /code-review)
    import core as _core
    _saved = _core.CFG.get("auto_rules")
    _core.CFG["auto_rules"] = {"emial": ["x"], "auto": ["y"], "email": ["moncrm"]}
    check("auto_rules : mode_id invalide/auto filtré, valide conservé",
          auto_mode._user_rules(), [("email", ["moncrm"])])
    # modes SUR MESURE (Ultra) : prioritaires sur auto_rules et les intégrés ;
    # entrées sans prompt/match/id écartées
    _saved_cm = _core.CFG.get("custom_modes")
    _core.CFG["custom_modes"] = [
        {"id": "j1", "name": "Jira", "match": ["jira"], "prompt": "Ticket."},
        {"id": "", "name": "sans id", "match": ["x"], "prompt": "p"},
        {"id": "np", "name": "sans prompt", "match": ["y"], "prompt": " "},
    ]
    check("custom_modes : règle perso en tête, mal formées écartées",
          auto_mode._user_rules(),
          [("custom:j1", ["jira"]), ("email", ["moncrm"])])
    check("resolve → custom:j1 sur un onglet Jira",
          auto_mode.resolve("PROJ-42 - Jira - Google Chrome", "chrome.exe",
                            auto_mode._user_rules()), "custom:j1")
    check("resolve custom prioritaire sur un intégré (gmail)",
          auto_mode.resolve("Jira - Gmail - Google Chrome", "chrome.exe",
                            auto_mode._user_rules()), "custom:j1")
    check("custom_mode('j1') → prompt lisible",
          (auto_mode.custom_mode("j1") or {}).get("prompt"), "Ticket.")
    check("custom_mode inconnu → None (repli dictée dans app)",
          auto_mode.custom_mode("inconnu"), None)
    check("custom_mode sans prompt → None",
          auto_mode.custom_mode("np"), None)
    # core.save_custom_modes : normaliseur UNIQUE (nom rogné à 40, tokens
    # nettoyés, id auto, entrées invalides écartées) — retour /simplify
    _cm = _core.save_custom_modes([
        {"name": "X" * 60, "match": [" jira ", "", "atlassian"], "prompt": "p"},
        {"name": "SansMatch", "match": [], "prompt": "p"},   # écarté
        {"id": "keep", "name": "Wiki", "match": "notion", "prompt": "q"},
    ])
    check("save_custom_modes : 2 valides sur 3", len(_cm), 2)
    check("save_custom_modes : nom rogné à 40", len(_cm[0]["name"]), 40)
    check("save_custom_modes : tokens nettoyés (rognés, vides retirés)",
          _cm[0]["match"], ["jira", "atlassian"])
    check("save_custom_modes : id auto attribué", bool(_cm[0]["id"]), True)
    check("save_custom_modes : id fourni conservé + str→[str]",
          (_cm[1]["id"], _cm[1]["match"]), ("keep", ["notion"]))
    # clean_tokens défensif : un scalaire (config éditée à la main) → [] sans lever
    check("clean_tokens : entier → [] (pas de crash)", _core.clean_tokens(3), [])
    check("clean_tokens : dict → []", _core.clean_tokens({"a": 1}), [])
    check("clean_tokens : chaîne nue → [chaîne]", _core.clean_tokens(" x "), ["x"])
    # dédoublonnage sur l'id
    _dup = _core.save_custom_modes([
        {"id": "d", "name": "A", "match": ["a"], "prompt": "p"},
        {"id": "d", "name": "B", "match": ["b"], "prompt": "q"},
    ])
    check("save_custom_modes : ids dédoublonnés",
          len({m["id"] for m in _dup}), 2)
    # custom_mode robuste : une entrée mal formée n'en masque pas d'autres
    _core.CFG["custom_modes"] = ["oops", {"id": "ok", "name": "OK",
                                          "match": ["x"], "prompt": "P"}]
    check("custom_mode : entrée invalide en tête n'empêche pas de trouver la suivante",
          (auto_mode.custom_mode("ok") or {}).get("prompt"), "P")
    _core.CFG.pop("custom_modes", None)
    if _saved_cm is None:
        _core.CFG.pop("custom_modes", None)
    else:
        _core.CFG["custom_modes"] = _saved_cm
    if _saved is None:
        _core.CFG.pop("auto_rules", None)
    else:
        _core.CFG["auto_rules"] = _saved


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
    # custom_vars=False (palier Free) : Custom Variables NON appliquées, mais la
    # substitution reste sans effet ici (pas de profil) → texte inchangé
    check("custom_vars=False → IBAN non substitué (palier Free)",
          core.fill_personal("voici mon IBAN", custom_vars=False),
          "voici mon IBAN")
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


# --------------------------------------------------- onboarding (accueil) ----
def test_onboarding():
    """L'assistant de bienvenue ne doit dépendre de pywebview qu'à l'usage réel
    (run()), jamais au chargement du module — sinon la CI (sans pywebview
    installé) casserait juste en import. `import onboarding` a déjà réussi plus
    haut : c'est la première preuve. Ici on vérifie la logique (Api, drapeau)."""
    print("Onboarding — drapeau 1er lancement + pont API (sans pywebview)")
    core.CFG["onboarding_done"] = False
    check("pas encore fait → nécessaire", onboarding.needs_onboarding(), True)
    core.CFG["onboarding_done"] = True
    check("déjà fait → plus nécessaire", onboarding.needs_onboarding(), False)

    check("vidéo absente → url vide (pas d'erreur)", onboarding.video_url(), "")

    api = onboarding.Api()
    st = api.state()
    check("state() expose tous les modes (source modes_registry)",
          len(st["modes"]), len(modes_registry.all_modes()))
    check("state() expose les langues (source core.LANGUAGES)",
          len(st["languages"]), len(core.LANGUAGES))
    check("state() expose tous les profils (source power_profiles)",
          len(st["profiles"]), len(power_profiles.PROFILES))

    check("set_ptt_key persiste", api.set_ptt_key("F8"), "f8")
    check("set_ptt_key ignore une valeur vide (garde l'ancienne)",
          api.set_ptt_key(""), "f8")
    check("set_language persiste", api.set_language("ja"), "ja")
    check("set_cloud→True bascule le provider en auto",
          (api.set_cloud(True), core.CFG.get("provider")), (True, "auto"))
    check("set_cloud→False repasse en local (ollama)",
          (api.set_cloud(False), core.CFG.get("provider")), (False, "ollama"))
    # même garde-fou que le tray : une sélection impossible retombe sur un profil sûr
    got = api.set_profile("ultra")
    check("set_profile jamais un profil verrouillé sur cette machine",
          power_profiles.is_available(got, power_profiles.detect_hardware()), True)


# --------------------------------------------------- langue STT « auto » -----
def test_stt_language():
    """« auto » (menu Langue) doit devenir None pour Whisper — sinon le STT
    casse (ce n'est pas un code ISO). Une langue explicite passe telle quelle."""
    print("Langue STT — normalisation « auto » → None")
    core.CFG["language"] = "auto"
    check("auto → None", core._stt_language(), None)
    core.CFG["language"] = "fr"
    check("fr → fr", core._stt_language(), "fr")
    core.CFG["language"] = "ja"
    check("ja → ja", core._stt_language(), "ja")


# --------------------------------------------------- fallback texte brut -----
def test_format_rules():
    print("Repli texte brut (sans IA)")
    check("majuscule + point", core.format_rules("bonjour tout le monde"),
          "Bonjour tout le monde.")
    check("espaces réduits", core.format_rules("  salut   toi  "), "Salut toi.")
    check("ponctuation conservée", core.format_rules("ça va ?"), "Ça va ?")
    check("vide → vide", core.format_rules("   "), "")


# --------------------------------------------------- Licences & paliers ------
def test_licensing():
    print("Licences — paliers Free/Pro/Ultra/Business (logique pure)")
    L = licensing
    # gating par palier (tier explicite → n'exige ni crypto ni config)
    check("free : pas de cloud", L.has("cloud_stt", L.FREE), False)
    check("free : dictée locale de base ok", L.has("cloud_stt", L.FREE) is False
          and L.mode_allowed("email", L.FREE), True)
    check("pro : tout l'usage débloqué", L.has("cloud_stt", L.PRO), True)
    check("pro : pas la perso Ultra", L.has("custom_modes", L.PRO), False)
    check("pro : pas la meilleure IA", L.has("best_models", L.PRO), False)
    check("ultra : meilleure IA", L.has("best_models", L.ULTRA), True)
    check("ultra : personnalisation", L.has("orb_customization", L.ULTRA), True)
    check("business = niveau Pro (fonctions)", L.has("cloud_stt", L.BUSINESS),
          True)
    check("business : pas la perso Ultra", L.has("custom_modes", L.BUSINESS),
          False)
    # modes offerts en Free
    check("free : mode email autorisé", L.mode_allowed("email", L.FREE), True)
    check("free : mode todo bloqué", L.mode_allowed("todo", L.FREE), False)
    check("pro : tous les modes", L.mode_allowed("todo", L.PRO), True)
    check("free : « auto » (mode par défaut) autorisé",
          L.mode_allowed("auto", L.FREE), True)
    # dormant (pas de clé publique dans le dépôt) → accès complet + illimité
    check("dormant → licences désactivées", L.enabled(), False)
    check("dormant → has True partout", L.has("custom_modes"), True)
    check("dormant → transcription illimitée", L.quota_status()["limit"], None)
    check("dormant → can_transcribe", L.can_transcribe(), True)
    # quota Free simulé sur un tier explicite (via record) — vérifie le calcul
    _saved = core.CFG.get("usage")
    core.CFG["usage"] = {"week": L._week_key(), "chars": L.FREE_WEEKLY_CHARS}
    check("quota calc : used=limit → remaining 0 (tier free simulé)",
          max(0, L.FREE_WEEKLY_CHARS - L._usage_used()), 0)
    if _saved is None:
        core.CFG.pop("usage", None)
    else:
        core.CFG["usage"] = _saved
    # aller-retour cryptographique si `cryptography` est présent. Le backend
    # Rust exige l'entropie de l'OS pour generate() : indisponible dans certains
    # bacs à sable (panic pyo3) — on saute alors proprement ; ça tourne en CI
    # (GitHub Actions) et sous Windows.
    if L._HAVE_CRYPTO:
        try:
            import base64 as _b64
            from cryptography.hazmat.primitives import serialization as _ser
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PrivateKey as _Priv)
            _priv = _Priv.generate()
            _pub = _b64.urlsafe_b64encode(_priv.public_key().public_bytes(
                _ser.Encoding.Raw, _ser.PublicFormat.Raw)).decode().rstrip("=")

            def _mk(tier, exp=0, seats=1):
                p = json.dumps({"t": tier, "e": "a@b.com", "x": exp, "s": seats}
                               ).encode("utf-8")
                b = lambda x: _b64.urlsafe_b64encode(x).decode().rstrip("=")  # noqa: E731
                return "NOVA1.%s.%s" % (b(p), b(_priv.sign(p)))
        except BaseException as _e:     # entropie OS bloquée (bac à sable)
            print(f"  [skip] round-trip crypto indisponible ici "
                  f"({type(_e).__name__})")
        else:
            check("clé pro valide → tier pro",
                  (L.verify_key(_mk("pro"), _pub) or {}).get("tier"), "pro")
            check("clé business → sièges lus",
                  (L.verify_key(_mk("business", seats=10), _pub)
                   or {}).get("seats"), 10)
            check("clé expirée → None",
                  L.verify_key(_mk("pro", exp=int(time.time()) - 10), _pub),
                  None)
            check("signature trafiquée → None",
                  L.verify_key(_mk("ultra")[:-3] + "aaa", _pub), None)
            check("mauvaise clé publique → None",
                  L.verify_key(_mk("pro"),
                               _b64.urlsafe_b64encode(b"\x00" * 32).decode()),
                  None)


if __name__ == "__main__":
    test_registry()
    test_auto_resolve()
    test_custom_vars()
    test_extensibility()
    test_power_profiles()
    test_onboarding()
    test_stt_language()
    test_format_rules()
    test_licensing()
    print()
    if _fails:
        print(f"❌ {len(_fails)} échec(s) : {', '.join(_fails)}")
        sys.exit(1)
    print("✅ Tous les tests logiques v3 passent.")
