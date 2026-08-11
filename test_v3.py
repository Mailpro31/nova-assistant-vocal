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
    check("label todo", modes_registry.label_of("todo"), "To-do list")
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
        # --- v3.1.2 : titres d'onglets réels (la plainte : Gmail non détecté)
        ("Boîte de réception (2 351) - x@gmail.com - Gmail", "chrome.exe", "email"),
        ("Inbox (12) - me@fastmail.com", "msedge.exe", "email"),
        ("Mes tâches - Trello", "chrome.exe", "todo"),
        ("Sans titre - Bloc-notes", "notepad.exe", "notes"),
        ("réunion clients | Microsoft Teams", "ms-teams.exe", "messages"),
        # mots courants qui ressemblent à des apps : toujours neutres
        ("Spots de windsurf en Bretagne - Blog", "chrome.exe", "voice_to_text"),
        ("CSS cursor property - MDN", "firefox.exe", "voice_to_text"),
    ]
    for title, proc, want in cases:
        check(f"{title or '(vide)'} / {proc or '-'}",
              auto_mode.resolve(title, proc), want)
    # règles utilisateur (config.json → auto_rules) : gagnent sur l'intégré
    check("règle perso : MonCRM → email",
          auto_mode.resolve("MonCRM - Tableau de bord", "chrome.exe",
                            [("email", ["moncrm"])]), "email")
    check("règle perso n'altère pas un titre neutre",
          auto_mode.resolve("Un document - Éditeur", "editor.exe",
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
    # (dormance simulée : ces règles perso sont gatées Pro/Ultra et le dépôt
    # embarque désormais la vraie clé publique → licences actives par défaut)
    import licensing as _lic
    _pub_cm = _lic.PUBLIC_KEY_B64
    _lic.PUBLIC_KEY_B64 = ""
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
    # « Meilleure IA » : meilleur modèle local selon la RAM (fonction pure)
    check("best_local_llm : 16 Go → qwen2.5:7b",
          power_profiles.best_local_llm(16), "qwen2.5:7b")
    check("best_local_llm : 32 Go → qwen2.5:14b",
          power_profiles.best_local_llm(32), "qwen2.5:14b")
    check("best_local_llm : 8 Go → qwen2.5:3b",
          power_profiles.best_local_llm(8), "qwen2.5:3b")
    # _reform_model : sans best_ai → modèle configuré ; avec → premium
    _core.CFG["best_ai"] = False
    _sv = _core.CFG.get("providers", {}).get("anthropic", {}).get("model", "")
    check("_reform_model : best_ai off → modèle configuré",
          _core._reform_model("anthropic"), _sv)
    _core.CFG["best_ai"] = True   # dormant → licensing.has renvoie True
    check("_reform_model : best_ai on → petit modèle cloud rapide (Haiku)",
          _core._reform_model("anthropic"), "claude-haiku-4-5")
    check("_reform_model : best_ai on (Groq) → Llama 70B (quasi gratuit)",
          _core._reform_model("groq"), "llama-3.3-70b-versatile")
    _core.CFG.pop("best_ai", None)
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
    _lic.PUBLIC_KEY_B64 = _pub_cm          # fin de la dormance simulée


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

    # gating par abonnement : sans palier payant, Élevé/Ultra verrouillés même
    # sur une grosse machine, avec le motif « abonnement » (pas « mémoire »)
    free = {e["id"]: e for e in power_profiles.evaluate(forte, has_paid=False)}
    check("Free : Normal débloqué (32 Go)", free["normal"]["locked"], False)
    check("Free : Élevé verrouillé (abonnement)", free["eleve"]["locked"], True)
    check("Free : Ultra verrouillé (abonnement)", free["ultra"]["locked"], True)
    check("Free : motif = abonnement, pas mémoire",
          "Pro" in free["eleve"]["reason"], True)
    check("Free 32 Go : recommandé retombe sur Normal",
          power_profiles.recommended_id(forte, has_paid=False), "normal")
    check("Free : sélection Ultra bornée à Normal",
          power_profiles.safe_selection("ultra", forte, has_paid=False), "normal")
    # payé mais petite machine : la RAM reste un garde-fou (motif « mémoire »)
    paid_low = {e["id"]: e for e in power_profiles.evaluate(faible, has_paid=True)}
    check("Payé 8 Go : Ultra verrouillé par la RAM",
          paid_low["ultra"]["locked"], True)
    check("Payé 8 Go : motif = mémoire",
          "mémoire" in paid_low["ultra"]["reason"], True)


# --------------------------------------------------- onboarding (accueil) ----
def test_onboarding():
    """L'assistant de bienvenue est 100 % NATIF (tkinter) : aucune dépendance
    web, aucun import lourd au chargement du module (tkinter n'est importé que
    dans run()). Sa logique de configuration réutilise celle du tray / des
    Réglages (setters de module). On teste le drapeau 1er lancement + les
    setters, sans ouvrir de fenêtre."""
    print("Onboarding — drapeau 1er lancement + setters natifs (sans WebView)")
    core.CFG["onboarding_done"] = False
    check("pas encore fait → nécessaire", onboarding.needs_onboarding(), True)
    core.CFG["onboarding_done"] = True
    check("déjà fait → plus nécessaire", onboarding.needs_onboarding(), False)

    check("set_ptt_key persiste (normalisé en minuscules)",
          onboarding.set_ptt_key("F8"), "f8")
    check("set_ptt_key ignore une valeur vide (garde l'ancienne)",
          onboarding.set_ptt_key(""), "f8")
    check("set_language persiste", onboarding.set_language("ja"), "ja")
    # Turbo n'est pas proposé à l'installation sans droit Ultra : refus net,
    # provider inchangé. Les deux cas sont SIMULÉS (has patché) pour ne pas
    # dépendre de l'état de licence de la machine qui exécute les tests
    # (dormante en CI, active ailleurs).
    import licensing as _lic
    _has0 = _lic.has
    _prov0 = core.CFG.get("provider")
    try:
        _lic.has = lambda f: False
        check("set_cloud→True SANS droit Ultra → refusé",
              (onboarding.set_cloud(True), core.CFG.get("provider")),
              (False, _prov0))
        _lic.has = lambda f: True
        check("set_cloud→True AVEC droit Ultra → provider auto",
              (onboarding.set_cloud(True), core.CFG.get("provider")),
              (True, "auto"))
    finally:
        _lic.has = _has0
    check("set_cloud→False repasse en local (ollama)",
          (onboarding.set_cloud(False), core.CFG.get("provider")),
          (False, "ollama"))
    # même garde-fou que le tray : une sélection impossible retombe sur un profil sûr
    got = onboarding.set_profile("ultra")
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
    check("pro : reformulations illimitées",
          L.has("unlimited_reformulation", L.PRO), True)
    check("pro : pas de Turbo (Ultra only)", L.has("cloud_stt", L.PRO), False)
    check("pro : pas la perso Ultra", L.has("custom_modes", L.PRO), False)
    check("pro : pas la meilleure IA", L.has("best_models", L.PRO), False)
    check("ultra : Turbo débloqué", L.has("cloud_stt", L.ULTRA), True)
    check("ultra : meilleure IA", L.has("best_models", L.ULTRA), True)
    check("ultra : personnalisation", L.has("orb_customization", L.ULTRA), True)
    check("business = niveau Pro (fonctions)",
          L.has("unlimited_reformulation", L.BUSINESS), True)
    check("business : pas la perso Ultra", L.has("custom_modes", L.BUSINESS),
          False)
    # modes offerts en Free : le quotidien (décision produit) — Normal,
    # E-mail, Messages ; To-do, Prompt IA et Prise de notes restent Pro.
    check("free : mode email autorisé", L.mode_allowed("email", L.FREE), True)
    check("free : mode messages autorisé",
          L.mode_allowed("messages", L.FREE), True)
    check("free : mode todo bloqué", L.mode_allowed("todo", L.FREE), False)
    check("free : mode prompt IA bloqué",
          L.mode_allowed("prompt_engineer", L.FREE), False)
    check("free : mode notes bloqué", L.mode_allowed("notes", L.FREE), False)
    check("pro : tous les modes", L.mode_allowed("todo", L.PRO), True)
    check("free : « auto » (mode par défaut) autorisé",
          L.mode_allowed("auto", L.FREE), True)
    check("free : best_models bloqué", L.has("best_models", L.FREE), False)
    check("ultra : best_models débloqué", L.has("best_models", L.ULTRA), True)
    # mode dormant (clé publique vide, simulée) → accès complet + illimité
    _pub = L.PUBLIC_KEY_B64
    L.PUBLIC_KEY_B64 = ""
    try:
        check("dormant → licences désactivées", L.enabled(), False)
        check("dormant → has True partout", L.has("custom_modes"), True)
        check("dormant → reformulation illimitée",
              L.quota_status()["limit"], None)
        check("dormant → can_reformulate", L.can_reformulate(), True)
        check("transcription illimitée à tous les paliers",
              L.can_transcribe(), True)
        # sync_trial : no-op sûr en dormant (aucun appel réseau, ne lève jamais)
        check("essai inversé : sync_trial no-op en dormant",
              L.sync_trial(), None)
    finally:
        L.PUBLIC_KEY_B64 = _pub
    # clé publique réelle présente → le système est ACTIF dans les builds
    check("licences actives (clé publique en place)",
          L.enabled(), bool(L._HAVE_CRYPTO))
    # quota Free simulé (repli config) — calcul journalier des reformulations ;
    # la dictée, elle, reste illimitée (can_transcribe True partout).
    _saved = core.CFG.get("usage")
    core.CFG["usage"] = {"day": L._day_key(), "count": L.FREE_DAILY_REFORMULATIONS}
    check("quota calc : used=limit → remaining 0 (tier free simulé)",
          max(0, L.FREE_DAILY_REFORMULATIONS - L._usage_used()), 0)
    core.CFG["usage"] = {"day": "2000-01-01", "count": 99}
    check("quota : jour différent → compteur remis à 0", L._usage_used(), 0)
    if _saved is None:
        core.CFG.pop("usage", None)
    else:
        core.CFG["usage"] = _saved
    # essai inversé : arithmétique des jours restants (indépendante de winext)
    _its = L._install_ts
    try:
        L._install_ts = lambda: int(time.time()) - 3 * 86400
        check("essai inversé : 3 j écoulés → 11 j restants",
              L._trial_days_left(), 11)
        L._install_ts = lambda: int(time.time()) - (L.TRIAL_DAYS + 1) * 86400
        check("essai inversé : expiré → 0 j", L._trial_days_left(), 0)
        L._install_ts = lambda: 0
        check("essai inversé : install indispo → 0 j (fail-safe Free)",
              L._trial_days_left(), 0)
    finally:
        L._install_ts = _its
    # v3.1.24 : la persistance du quota passe par winext.set_secret("usage").
    # « usage » DOIT figurer dans SECRET_KEYS du vrai winext.py, sinon
    # set_secret lève ValueError — avalée par _usage_write → compteur figé à
    # 0/2500 et plafond jamais bloquant (bug ≤ v3.1.23, invisible avec un stub
    # no-op). winext étant Windows-only, on lit ses clés par AST et on rejoue
    # l'aller-retour écriture → relecture avec un coffre simulé qui REPRODUIT
    # le contrat réel (clé inconnue → ValueError).
    import ast
    import os
    _src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "winext.py"), encoding="utf-8").read()
    _keys = ()
    for _n in ast.walk(ast.parse(_src)):
        if isinstance(_n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "SECRET_KEYS"
                for t in _n.targets):
            _keys = tuple(ast.literal_eval(_n.value))
    check("winext : « usage » présent dans SECRET_KEYS", "usage" in _keys, True)
    _w, _store = sys.modules["winext"], {}

    def _vault_set(k, v):
        if k not in _keys:
            raise ValueError(f"secret inconnu : {k}")
        _store[k] = v
        return True
    _w.set_secret, _w.get_secret = _vault_set, lambda k: _store.get(k, "")
    try:
        L._usage_write(L._day_key(), 123)
        check("quota : écrit puis relu via le coffre chiffré",
              L._usage_used(), 123)
    finally:
        del _w.set_secret                        # retour au repli __getattr__
        _w.get_secret = lambda *_a, **_k: ""
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

            def _mk(tier, exp=0, seats=1, machine=None):
                p = {"t": tier, "e": "a@b.com", "x": exp, "s": seats}
                if machine is not None:
                    p["m"] = machine
                p = json.dumps(p).encode("utf-8")
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
            # liaison machine : jeton d'une AUTRE machine refusé, la sienne OK
            import winext as _wx
            check("jeton lié à une autre machine → None",
                  L.verify_key(_mk("pro", machine="f" * 32), _pub), None)
            check("jeton lié à CETTE machine → accepté",
                  (L.verify_key(_mk("pro",
                                    machine=_wx.machine_fingerprint()), _pub)
                   or {}).get("tier"), "pro")


def test_version_sync():
    """core.APP_VERSION et installer/nova.iss doivent porter la même version :
    l'updater compare APP_VERSION au tag de release, l'installateur affiche la
    sienne — une dérive casserait la détection de mise à jour."""
    print("Version — core.APP_VERSION ↔ installer/nova.iss")
    import os
    import re as _re
    iss = open(os.path.join(os.path.dirname(__file__),
                            "installer", "nova.iss"), encoding="utf-8").read()
    m = _re.search(r'#define\s+MyAppVersion\s+"([^"]+)"', iss)
    check("nova.iss définit MyAppVersion", bool(m), True)
    check("versions identiques (core ↔ installeur)",
          m.group(1) if m else "", core.APP_VERSION)
    import updater as _upd
    # version-agnostique (ne se périme plus à chaque bump) : un tag franchement
    # supérieur DOIT être vu comme plus récent que la version courante.
    check("updater : un tag plus récent est détecté comme plus récent",
          _upd._vtuple("v999.0.0") > _upd._vtuple(core.APP_VERSION), True)
    check("updater : version identique → pas plus récente",
          _upd._vtuple(f"v{core.APP_VERSION}") > _upd._vtuple(core.APP_VERSION),
          False)
    # Robustesse « Mise à jour impossible » : les trois issues non-succès sont
    # des statuts EXPLICITES — l'app distingue « échec » (plan B navigateur),
    # « déjà en cours » (pas une erreur) et « développement » (no-op).
    check("updater : non gelé → UNSUPPORTED (no-op, pas d'erreur)",
          _upd.download_and_install(), _upd.UNSUPPORTED)
    real_frozen = _upd.is_frozen
    _upd.is_frozen = lambda: True
    _upd._busy.acquire()
    try:
        check("updater : tentative déjà en cours → BUSY (pas d'erreur)",
              _upd.download_and_install(), _upd.BUSY)
    finally:
        _upd._busy.release()
        _upd.is_frozen = real_frozen


def test_free_offer_sync():
    """Le nombre de Styles annoncé (site + README) doit suivre
    licensing.FREE_MODES (moins « auto », qui est un sélecteur, pas un Style) :
    cette dérive est déjà arrivée — même principe que test_version_sync."""
    print("Offre Gratuit — nombre de Styles annoncé ↔ FREE_MODES")
    import os
    import re as _re
    nb = len([m for m in licensing.FREE_MODES if m != "auto"])
    base = os.path.dirname(__file__)
    html = open(os.path.join(base, "landing", "index.html"),
                encoding="utf-8").read()
    counts = _re.findall(r"(\d+)\s+(?:\w+\s+)?Styles\b", html)
    check("landing : au moins une mention du compte de Styles",
          bool(counts), True)
    # Le plan Gratuit doit annoncer exactement len(FREE_MODES) - auto Styles ;
    # les paliers payants peuvent afficher le total « 7 Styles » (hors périmètre
    # de FREE_MODES), donc on garde le compte Free présent sans interdire le reste.
    check("landing : le plan Gratuit annonce len(FREE_MODES) - auto Styles",
          str(nb) in counts, True)
    readme = open(os.path.join(base, "README.md"), encoding="utf-8").read()
    m = _re.search(r"\|\s*Styles\s*\|\s*(\d+)\s*\|", readme)   # lexique produit
    check("README : la colonne Free du tableau des paliers est à jour",
          m.group(1) if m else "", str(nb))


def test_stt_latency():
    """Piliers de latence STT (PC 8 Go sans GPU) : découpe de la transcription
    en continu (logique pure, transcripteur injecté), moteur gardé en mémoire,
    beam adaptatif et relèvement « qualité maximale » du modèle."""
    print("Latence STT — transcription en continu, keep_warm, beam, qualité")
    import numpy as _np
    import threading as _th
    import core

    # --- LiveTranscriber : logique de découpe, sans thread ni vrai modèle ---
    calls = []

    def fake_tx(audio, prompt):
        calls.append((len(audio), prompt))
        return f"seg{len(calls)}"

    frames, lock = [], _th.Lock()
    lt = core.LiveTranscriber(frames, lock)   # .start() jamais appelé : pas de
    lt._transcribe = fake_tx                  # thread, logique de découpe pure
    core.NOISE["floor"] = 0.01                 # seuil de voix réaliste
    quiet = _np.zeros(1600, dtype=_np.float32)             # bloc silencieux
    loud = _np.ones(1600, dtype=_np.float32) * 0.5         # bloc de voix
    # voix en cours, pas de pause → aucun commit
    frames.extend([loud] * 30)
    lt._commit(final=False)
    check("live : pas de commit tant que la voix continue", calls, [])
    # une pause de ~0,5 s → commit de la tranche
    frames.extend([quiet] * 6)
    lt._commit(final=False)
    check("live : commit à la pause", len(calls), 1)
    # la traîne est transcrite par finish (avec l'amorce du texte committé)
    frames.extend([loud] * 8)
    out = lt.finish()
    check("live : texte final = tranches + traîne", out, "seg1 seg2")
    # l'amorce se termine par le texte committé (le lexique utilisateur, s'il
    # existe, la PRÉCÈDE — il ne doit jamais disparaître après la 1re tranche)
    check("live : la traîne reçoit l'amorce du committé",
          (calls[1][1] or "").endswith("seg1"), True)
    # fil cassé → None (l'appelant repart sur la transcription intégrale)
    lt2 = core.LiveTranscriber([], _th.Lock())
    lt2._transcribe = fake_tx
    lt2.broken = True
    check("live : cassé → None (repli intégral)", lt2.finish(), None)
    # tampon RÉTRÉCI (record_audio l'a vidé sur reprise micro) : le texte
    # committé décrit de l'audio disparu → cassé, repli intégral
    f3 = [loud] * 34 + [quiet] * 6
    lt3 = core.LiveTranscriber(f3, _th.Lock())
    lt3._transcribe = fake_tx
    lt3._commit(final=False)                  # committe le tampon initial
    del f3[:]                                 # reprise micro : tampon vidé
    check("live : tampon vidé → cassé, repli intégral", lt3.finish(), None)
    # reprise micro signalée par l'ÉPOQUE : même si le tampon a regrossi
    # au-delà du curseur avant le poll suivant (commit lent en vol), le texte
    # committé décrit toujours de l'audio jeté → cassé, repli intégral
    f5 = [loud] * 34 + [quiet] * 6
    lt5 = core.LiveTranscriber(f5, _th.Lock())
    lt5._transcribe = fake_tx
    lt5._commit(final=False)
    core._MIC_EPOCH["n"] += 1                 # record_audio a vidé + rerempli
    f5.extend([loud] * 20)                    # regrossi au-delà du curseur
    try:
        check("live : reprise micro (époque) → cassé, repli intégral",
              lt5.finish(), None)
    finally:
        core._MIC_EPOCH["n"] -= 1             # état module restauré
    # tranche de silence pur (touche tenue en réfléchissant) : AUCUNE
    # inférence — le curseur avance sans amorcer d'écho-hallucination
    calls4 = []
    f4 = [quiet] * 40
    lt4 = core.LiveTranscriber(f4, _th.Lock())
    lt4._transcribe = lambda a, p: calls4.append(p) or "écho"
    lt4._commit(final=False)
    check("live : tranche silencieuse → zéro inférence", calls4, [])
    check("live : le curseur avance quand même", lt4._done, 40)
    # …mais le commit FINAL transcrit TOUJOURS la traîne, même murmurée (sous
    # le seuil) : sinon finish() rendrait un texte non vide sans elle et
    # l'appelant ne repasserait pas par le repli intégral → mots de fin perdus
    calls4b = []
    lt4b = core.LiveTranscriber([quiet] * 40, _th.Lock())
    lt4b._transcribe = lambda a, p: calls4b.append(1) or "traîne"
    lt4b._commit(final=True)
    check("live : commit final transcrit même une traîne murmurée",
          len(calls4b), 1)

    # --- keep_warm : explicite > auto ---
    old_stt = dict(core.CFG.get("stt") or {})
    try:
        core.CFG["stt"] = dict(old_stt, keep_warm=True)
        check("keep_warm : explicite oui", core.stt_keep_warm(), True)
        core.CFG["stt"] = dict(old_stt, keep_warm=False)
        check("keep_warm : explicite non", core.stt_keep_warm(), False)
        core.CFG["stt"] = dict(old_stt, keep_warm="auto")
        check("keep_warm : auto → booléen",
              core.stt_keep_warm() in (True, False), True)
        # auto proportionné au modèle : le grand moteur multilingue (~1,5 Go)
        # n'est gardé chaud qu'avec une vraie marge RAM ; Apex jamais —
        # l'invariant seq_memory « jamais les deux gros modèles » prime
        _rr = core._ram_total_gb
        _wm = core.CFG.get("whisper_model")
        try:
            core._ram_total_gb = lambda: 8.0
            core.CFG["whisper_model"] = "small"
            check("keep_warm auto : standard dès 8 Go",
                  core.stt_keep_warm(), True)
            core.CFG["whisper_model"] = "large-v3-turbo"
            check("keep_warm auto : grand moteur à 8 Go → séquentiel",
                  core.stt_keep_warm(), False)
            core._ram_total_gb = lambda: 16.0
            check("keep_warm auto : grand moteur dès 12 Go",
                  core.stt_keep_warm(), True)
            core.CFG["whisper_model"] = "large-v3"
            check("keep_warm auto : Apex jamais gardé chaud",
                  core.stt_keep_warm(), False)
        finally:
            core._ram_total_gb = _rr
            core.CFG["whisper_model"] = _wm

        # --- beam adaptatif (CPU en CI) ---
        core.CFG["stt"] = dict(old_stt, precision_max=False)
        check("beam : CPU rapide par défaut", core._stt_beam(), 1)
        core.CFG["stt"] = dict(old_stt, precision_max=True)
        check("beam : précision maximale → 5", core._stt_beam(), 5)

        # --- qualité maximale : relève small (si la RAM suit), respecte
        # large-v3, et ne contourne JAMAIS le garde-fou RAM des profils ---
        _rr2 = core._ram_total_gb
        core.CFG["stt"] = dict(old_stt, quality_max=True)
        try:
            core._ram_total_gb = lambda: 16.0
            check("qualité max : small → grand moteur multilingue",
                  core.effective_stt_model("small"), "large-v3-turbo")
            check("qualité max : large-v3 (Apex) inchangé",
                  core.effective_stt_model("large-v3"), "large-v3")
            check("qualité max : supportée dès 12 Go",
                  core.quality_max_supported(), True)
            core._ram_total_gb = lambda: 10.0
            # 8–11,9 Go : le grand moteur ne pourrait pas rester chaud (keep_warm
            # exige 12) → il thrasherait à chaque dictée. On aligne les deux
            # seuils : quality_max ne s'engage que là où keep_warm le tient.
            check("qualité max : 10 Go → refusée (aligné sur keep_warm)",
                  core.effective_stt_model("small"), "small")
            check("qualité max : 10 Go → non supportée",
                  core.quality_max_supported(), False)
            core._ram_total_gb = lambda: 4.0
            check("qualité max : 4 Go → garde-fou RAM, pas de relèvement",
                  core.effective_stt_model("small"), "small")
        finally:
            core._ram_total_gb = _rr2
        core.CFG["stt"] = dict(old_stt, quality_max=False)
        check("qualité off : le profil décide",
              core.effective_stt_model("small"), "small")

        # --- v3.1.10 : choix GPU selon la VRAM (fonction pure) ---
        check("gpu : VRAM inconnue → float16 (comportement historique)",
              core._pick_gpu_compute(0.0), "float16")
        check("gpu : 1 Go → CPU d'emblée (None)",
              core._pick_gpu_compute(1.0), None)
        check("gpu : 2 Go → int8_float16 (vieille carte utilisable)",
              core._pick_gpu_compute(2.0), "int8_float16")
        check("gpu : 8 Go → float16", core._pick_gpu_compute(8.0), "float16")
        # threads CPU bornés [2, 8]
        check("threads STT : borne basse/haute respectée",
              2 <= core._cpu_threads() <= 8, True)
        # keep_alive LLM adaptatif à la RAM
        real_ram = core._ram_total_gb
        try:
            core._ram_total_gb = lambda: 16.0
            check("LLM gardé chaud dès 8 Go", core._llm_keep_alive(), "30m")
            core._ram_total_gb = lambda: 4.0
            check("LLM : petite RAM → défaut Ollama",
                  core._llm_keep_alive(), "5m")
        finally:
            core._ram_total_gb = real_ram
        # collage éclair : off par défaut (choix explicite de l'utilisateur)
        check("collage éclair désactivé par défaut",
              core.DEFAULT_CONFIG.get("instant_normal"), False)
    finally:
        core.CFG["stt"] = old_stt
        core.NOISE["floor"] = 0.0


def test_hotkey_removal():
    """Supprimer un raccourci de Style doit VRAIMENT le supprimer :
    save_config REMPLACE les dictionnaires de _REPLACE_KEYS au lieu de les
    fusionner — la fusion récursive de _merge ne sait pas retirer une clé
    (le raccourci « supprimé » réapparaissait à la sauvegarde suivante)."""
    print("Config — suppression d'un raccourci de Style")
    real_cfg = core.CFG
    try:
        core.save_config({"mode_hotkeys": {"email": "ctrl+alt+e",
                                           "todo": "ctrl+alt+t"}})
        core.save_config({"mode_hotkeys": {"email": "ctrl+alt+e"}})
        check("raccourci retiré → absent après sauvegarde",
              "todo" in (core.CFG.get("mode_hotkeys") or {}), False)
        check("raccourci conservé → toujours là",
              (core.CFG.get("mode_hotkeys") or {}).get("email"), "ctrl+alt+e")
        core.save_config({"stt": {"live": False}})
        check("les autres dictionnaires fusionnent toujours (pas de perte)",
              isinstance(core.CFG.get("providers"), dict), True)
    finally:
        core.CFG = real_cfg          # _save est neutralisé en tête de fichier


def test_save_config_atomic():
    """save_config fait une lecture-modification-écriture du global CFG. Sans
    verrou tenu sur TOUTE l'opération (et pas seulement l'écriture disque), deux
    sauvegardes simultanées s'écrasent — lost update : la bascule « Qualité
    maximale » et le fil de synchro du modèle qu'elle lance pouvaient laisser
    quality_max=True avec whisper_model=\"small\". _lock est ré-entrant et tenu
    sur la RMW entière. On martèle save_config depuis N fils au départ simultané
    et on vérifie qu'AUCUNE écriture n'est perdue."""
    import threading as _th
    print("Config — save_config atomique sous fils concurrents")
    real_cfg = core.CFG
    try:
        core.CFG = dict(real_cfg)
        n = 40
        gate = _th.Barrier(n)

        def writer(i):
            gate.wait()                  # départ simultané → maximise la course
            core.save_config({f"_atomic_{i}": i})

        ths = [_th.Thread(target=writer, args=(i,)) for i in range(n)]
        for t in ths:
            t.start()
        for t in ths:
            t.join()
        survived = sum(1 for i in range(n) if core.CFG.get(f"_atomic_{i}") == i)
        check("40 écritures concurrentes survivent (0 lost update)", survived, n)
    finally:
        core.CFG = real_cfg          # _save est neutralisé en tête de fichier


def test_partial_stt_merge():
    """Les écrans de réglages n'envoient plus qu'un patch MINIMAL du sous-dict
    stt (seule la clé changée). save_config/_merge doit fusionner cette clé SANS
    écraser ses voisines — sinon un basculement Turbo (cloud_enabled) et un
    réglage de latence écrits en parallèle s'écrasent (lost update inter-appels)."""
    print("Config — fusion partielle du sous-dict stt (anti lost-update)")
    real_cfg = core.CFG
    try:
        core.CFG = core._merge(real_cfg,
                               {"stt": {"cloud_enabled": False, "live": True}})
        core.save_config({"stt": {"cloud_enabled": True}})    # un seul champ
        stt = core.CFG.get("stt") or {}
        check("cloud_enabled mis à jour", stt.get("cloud_enabled"), True)
        check("live (voisin) préservé", stt.get("live"), True)
        core.save_config({"stt": {"live": False}})            # un autre champ
        stt = core.CFG.get("stt") or {}
        check("live mis à jour", stt.get("live"), False)
        check("cloud_enabled (voisin) préservé", stt.get("cloud_enabled"), True)
    finally:
        core.CFG = real_cfg          # _save est neutralisé en tête de fichier


def test_warmup_llm_gate():
    """Préchauffage LLM : JAMAIS en mémoire séquentielle sur petite RAM
    (seq_memory + STT non gardé chaud). Sinon la 1re dictée chargerait le STT
    alors que le LLM (~2 Go) est encore résident → STT+LLM coexistants → swap/OOM
    sur 4 Go, l'inverse du but du préchauffage. Le garde-fou court-circuite avant
    toute résolution de fournisseur (déterministe, sans réseau)."""
    print("Préchauffage — LLM non épinglé en mémoire séquentielle (petite RAM)")
    real_ram = core._RAM_TOTAL["gb"]
    real_cfg = core.CFG
    try:
        core._RAM_TOTAL["gb"] = 4.0
        core.CFG = core._merge(real_cfg, {"seq_memory": True,
                                          "whisper_model": "small",
                                          "stt": {"keep_warm": "auto"}})
        check("seq_memory + 4 Go → STT non gardé chaud", core.stt_keep_warm(), False)
        check("seq_memory + 4 Go → LLM NON préchauffé (anti coexistence STT+LLM)",
              core._should_warm_llm(), False)
    finally:
        core._RAM_TOTAL["gb"] = real_ram
        core.CFG = real_cfg


def test_llm_num_ctx():
    """Fenêtre de contexte du LLM de reformulation : assez grande pour que le
    préfixe système (COMMON_RULES = garde-fous « ne réponds jamais / zéro
    invention ») ne soit JAMAIS tronqué (Ollama coupe l'entrée > num_ctx en
    partant du DÉBUT = les règles). Bornée par la RAM (le KV-cache grandit avec
    num_ctx) — plancher sûr sur 4 Go, plus large si la RAM le permet. Latence
    inchangée (le prefill ne coûte que les tokens réels)."""
    print("Reformulation — fenêtre de contexte LLM bornée par la RAM")
    _rr = core._ram_total_gb
    try:
        core._ram_total_gb = lambda: 4.0
        check("4 Go → num_ctx plancher 3072 (garde-fous tiennent, KV modéré)",
              core._llm_num_ctx(), 3072)
        core._ram_total_gb = lambda: 8.0
        check("8 Go → num_ctx 4096", core._llm_num_ctx(), 4096)
        core._ram_total_gb = lambda: 16.0
        check("16 Go → num_ctx 8192", core._llm_num_ctx(), 8192)
        core._ram_total_gb = lambda: 3.0
        check("num_ctx toujours ≥ 2048 (jamais sous le défaut Ollama, "
              "garde-fous jamais tronqués)", core._llm_num_ctx() >= 2048, True)
    finally:
        core._ram_total_gb = _rr


def test_ui_default_native():
    """Décision produit (demandée par l'utilisateur) : l'UI par défaut est la
    pilule tkinter NATIVE — 100 % Python, AUCUN WebView (fini les « 404 Not
    Found » et les plantages du moteur web), aucun conflit de DLL Qt → elle
    démarre PARTOUT. Le dock web n'est plus auto-sélectionné ; le dock natif Qt
    reste un opt-in explicite (dock_ui="qt"). Une régression qui remettrait le
    WebView dans le chemin par défaut renverrait les plantages."""
    print("UI — pilule native par défaut (sans WebView)")
    check("config : dock_ui vaut « pill » par défaut",
          core.DEFAULT_CONFIG.get("dock_ui"), "pill")
    import licensing as _lic
    check("licensing : web_dock défini (dormant si le web est réactivé)",
          _lic.FEATURES.get("web_dock"), _lic.FREE)
    # app.py n'est pas importable ici (Win32) → comparaison SOURCE.
    import os
    _here = os.path.dirname(os.path.abspath(__file__))
    _app = open(os.path.join(_here, "app.py"), encoding="utf-8").read()
    _dock = open(os.path.join(_here, "ui", "dock.html"), encoding="utf-8").read()
    # défaut RÉEL : _make_ui retombe sur la pilule native (return Pill) et n'a
    # plus aucune branche de sélection AUTOMATIQUE de WebDock
    check("UI : défaut = pilule native (return Pill + log 'pill')",
          "return Pill()" in _app and 'dock_ui_chosen", "pill"' in _app, True)
    check("UI : WebDock() plus jamais instancié automatiquement",
          "return WebDock()" not in _app, True)
    # dock Qt disponible UNIQUEMENT en opt-in explicite
    check("UI : dock Qt en opt-in explicite (dock_ui == \"qt\")",
          'core.CFG.get("dock_ui") == "qt"' in _app, True)
    # dock QML (Qt Quick) : opt-in explicite (dock_ui == "qml"), défaut inchangé
    check("UI : dock QML en opt-in explicite (dock_ui == \"qml\")",
          'core.CFG.get("dock_ui") == "qml"' in _app and "_new_qml_dock" in _app, True)
    # le dock QML fabrique QApplication AVANT les moteurs (correctif du crash).
    # Lu en SOURCE (comme app.py) : pas d'import Qt dans l'env de test.
    _qmls = open(os.path.join(_here, "qmldock.py"), encoding="utf-8").read()
    check("QML : QApplication construit tôt (_ensure_qapp dans __init__)",
          "self._app = _ensure_qapp()" in _qmls and "def _ensure_qapp" in _qmls, True)
    check("QML : API compatible (show/hide/level/serve/open_settings/open_modes)",
          all(("def %s(" % m) in _qmls for m in
              ("show", "hide", "level", "serve", "open_settings", "open_modes")), True)
    # les fichiers QML embarqués existent (bundlés par --add-data "qml;qml")
    check("QML : qml/Main.qml et qml/Orb.qml présents",
          os.path.isfile(os.path.join(_here, "qml", "Main.qml"))
          and os.path.isfile(os.path.join(_here, "qml", "Orb.qml")), True)
    # Réglages QML en process : la fenêtre existe et réutilise les fonctions de
    # app.py (aucune logique de config dupliquée → rien de cassé).
    _qsets = open(os.path.join(_here, "qmlsettings.py"), encoding="utf-8").read()
    check("QML : fenêtre Réglages présente (qml/Settings.qml + open_settings)",
          os.path.isfile(os.path.join(_here, "qml", "Settings.qml"))
          and "def open_settings" in _qsets, True)
    check("QML Réglages : réutilise les setters de app.py (pas de dup config)",
          "_toggle_cloud" in _qsets and "_set_profile" in _qsets
          and "_apply_stt_opts" in _qsets, True)
    # Onboarding QML : fenêtre présente, réutilise les setters onboarding.py, et
    # onboarding.run() l'emploie en mode QML avec repli tkinter.
    _qonb = open(os.path.join(_here, "qmlonboarding.py"), encoding="utf-8").read()
    _onb = open(os.path.join(_here, "onboarding.py"), encoding="utf-8").read()
    check("QML : onboarding présent (qml/Onboarding.qml + run_qml)",
          os.path.isfile(os.path.join(_here, "qml", "Onboarding.qml"))
          and "def run_qml" in _qonb, True)
    check("QML onboarding : réutilise onboarding.set_* (pas de dup config)",
          "onboarding.set_ptt_key" in _qonb and "onboarding.set_profile" in _qonb
          and "onboarding.set_language" in _qonb and "onboarding.set_cloud" in _qonb, True)
    check("onboarding.run : QML si dock_ui==qml, repli tkinter sinon",
          'core.CFG.get("dock_ui") == "qml"' in _onb
          and "qmlonboarding" in _onb and "_run_wizard()" in _onb, True)
    # dock.html reste autonome (injecté en mémoire, sans serveur → jamais de 404)
    check("dock : dock.html injecté en mémoire (html=_dock_html())",
          "html=_dock_html()" in _app, True)
    check("dock.html : html,body en background:transparent (si web réactivé)",
          "html,body{" in _dock and "background:transparent" in _dock, True)


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
    test_version_sync()
    test_free_offer_sync()
    test_stt_latency()
    test_hotkey_removal()
    test_save_config_atomic()
    test_partial_stt_merge()
    test_warmup_llm_gate()
    test_llm_num_ctx()
    test_ui_default_native()
    print()
    if _fails:
        print(f"❌ {len(_fails)} échec(s) : {', '.join(_fails)}")
        sys.exit(1)
    print("✅ Tous les tests logiques v3 passent.")
