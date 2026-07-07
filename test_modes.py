# -*- coding: utf-8 -*-
"""Tests rapides Nova v2 : classifieur de modes, stockage SQLite, secrets DPAPI,
formatage. Lancer : .venv\\Scripts\\python.exe test_modes.py"""

import sys
import time

# console Windows cp1252 : ne jamais planter sur un caractère de test
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import core
import modes
import storage
import integrations
import timers
import winext

FAIL = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"  ({extra})" if extra and not cond else ""))
    if not cond:
        FAIL.append(name)


def _calc_rejects(expr):
    """True si l'évaluateur arithmétique refuse `expr` (lève une exception),
    c.-à-d. n'exécute aucun code arbitraire."""
    try:
        fun_mode._safe_eval(expr)
        return False
    except Exception:
        return True


# --- classifieur ---
cases = [
    ("envoie un message à paul que j'arrive dans dix minutes", "message", "paul"),
    ("dis à marie que je serai en retard", "message", "marie"),
    ("va à la gare de lyon", "navigation", "la gare de lyon"),
    ("emmène-moi au centre commercial", "navigation", None),
    ("mets la musique", "media", "playPause"),
    ("chanson suivante", "media", "next"),
    ("monte le son", "media", "volUp"),
    ("appelle maman", "call", "maman"),
    ("urgence urgence", "emergency", None),
    ("change de profil", "system", None),
]
for phrase, mode, target in cases:
    r = modes.classify(phrase)
    ok = r is not None and r[0] == mode and (target is None or target in r[1])
    check(f'classify "{phrase}" -> {mode}', ok, str(r))

cases2 = [
    ("mets un minuteur de 10 minutes", "timer", "10 minutes"),
    ("rappelle-moi de sortir le gateau dans 25 minutes", "timer", "25 minutes"),
    ("rappelle-moi dans une heure de rappeler paul", "timer", "une heure"),
    ("annule le minuteur", "timer_cancel", None),
    ("quelle heure il est", "time", None),
    ("quelle est la meteo a paris", "weather", "paris"),
    ("quel temps fait-il", "weather", None),
    ("mets daft punk sur spotify", "music", "daft punk"),
    ("joue jul sur youtube", "music", "jul"),
    ("ajoute un rendez-vous dentiste demain a 15 h", "calendar", "dentiste"),
    ("envoie un whatsapp a paul que j'arrive", "message", "paul"),
]
for phrase, mode, target in cases2:
    r = modes.classify(phrase)
    ok = r is not None and r[0] == mode and (target is None or target in r[1])
    check(f'classify "{phrase}" -> {mode}', ok, str(r))

check('classify "il fait beau" -> None', modes.classify("il fait beau aujourd'hui") is None)
check('classify "mets la musique" -> media (pas music)', modes.classify("mets la musique")[0] == "media")

# --- ouverture instantanée (sites/applis) + raccourcis vocaux ---
r = modes.classify("ouvre google")
check('classify "ouvre google" -> open', r is not None and r[0] == "open" and "google" in r[1])
r = modes.classify("ouvre notion")
check('classify "ouvre notion" -> open', r is not None and r[0] == "open" and "notion" in r[1])
r = modes.classify("va sur youtube")
check('classify "va sur youtube" -> open', r is not None and r[0] == "open")
r = modes.classify("lance word")
check('classify "lance word" -> open app', r is not None and r[0] == "open" and r[1] == "winword")
check('classify "ouvre la porte du garage" -> None',
      modes.classify("ouvre la porte du garage") is None)
r = modes.classify("colle")
check('classify "colle" -> shortcut ctrl+v', r == ("shortcut", "ctrl+v", "Collé"))
r = modes.classify("plein écran")
check('classify "plein écran" -> shortcut f11', r is not None and r[1] == "f11")
r = modes.classify("verrouille")
check('classify "verrouille" -> shortcut win+l', r is not None and r[1] == "win+l")
r = modes.classify("capture d'écran")
check('classify "capture d\'écran" -> shortcut', r is not None and r[0] == "shortcut")

# --- demandes précises : la version la plus spécifique gagne ---
r = modes.classify("ouvre les paramètres de l'écran")
check('classify "paramètres de l\'écran" -> page affichage',
      r is not None and r[0] == "open" and r[1] == "ms-settings:display", str(r))
r = modes.classify("ouvre les réglages du son")
check('classify "réglages du son" -> page son',
      r is not None and r[1] == "ms-settings:sound", str(r))
r = modes.classify("ouvre les paramètres wifi")
check('classify "paramètres wifi" -> page wifi',
      r is not None and r[1] == "ms-settings:network-wifi", str(r))
r = modes.classify("ouvre les paramètres")
check('classify "ouvre les paramètres" -> app paramètres',
      r is not None and r[0] == "open" and r[1] == "ms-settings:", str(r))
check('classify "va sur le site de la fnac" -> pas navigation',
      modes.classify("va sur le site de la fnac") is None)
check("matches_phrase exact", core.matches_phrase("ouvre youtube", "ouvre youtube"))
check("matches_phrase politesse",
      core.matches_phrase("ouvre youtube", "ouvre youtube s'il te plait"))
check("matches_phrase demande plus précise -> False",
      not core.matches_phrase("ouvre les parametres", "ouvre les parametres de l'ecran"))
check("matches_phrase sans rapport -> False",
      not core.matches_phrase("ouvre youtube", "ouvre la fenetre"))

# --- nettoyage des hésitations ---
check("clean_speech euh", core.clean_speech("euh ouvre euh youtube") == "ouvre youtube")
check("clean_speech hum virgule",
      core.clean_speech("hum, mets un minuteur") == "mets un minuteur")
check("clean_speech intact", core.clean_speech("ouvre la meteo") == "ouvre la meteo")
check("clean_speech ne vide pas", core.clean_speech("euh") == "euh")

# --- durées ---
check("parse_duration 10 minutes", timers.parse_duration("10 minutes") == 600)
check("parse_duration une heure et demie", timers.parse_duration("une heure et demie") == 5400)
check("parse_duration 1 h 30", timers.parse_duration("1 h 30") == 5400)
check("parse_duration 45 secondes", timers.parse_duration("45 secondes") == 45)
check("parse_duration un quart d'heure", timers.parse_duration("un quart d'heure") == 900)
check("parse_duration nombre seul = minutes", timers.parse_duration("10") == 600)

# --- agenda : extraction date/heure ---
dt, title = modes._parse_when_fr("dentiste demain a 15 h 30")
check("parse_when demain 15h30", dt is not None and dt.hour == 15 and dt.minute == 30
      and "dentiste" in title, f"{dt} / {title}")

# --- minuteur bout en bout ---
fired = []
timers.notify = fired.append
tid = timers.start(0.05, "test")
time.sleep(0.3)
check("timer fires", fired == ["test"])
tid2 = timers.start(60, "annulable")
check("timer listed", any(t["id"] == tid2 for t in timers.list_active()))
check("timer cancel", timers.cancel(tid2) is True and not timers.list_active())

# --- formatage règles ---
check("format_rules", core.format_rules("j'arrive dans dix minutes") == "J'arrive dans dix minutes.")

# --- IA multi-étapes : normalisation ---
r = core._normalize_llm({"action": "open_url", "target": "https://x.com", "reply": "ok"})
check("normalize ancien format -> steps", r["steps"] == [
    {"action": "open_url", "target": "https://x.com", "args": ""}])
r = core._normalize_llm({"reply": "ok", "steps": [
    {"action": "open_app", "target": "notepad"},
    {"action": "wait", "target": "1"},
    {"action": "type_text", "target": "bonjour"},
    {"action": "inconnu", "target": "x"},
]})
check("normalize steps filtre les actions inconnues", len(r["steps"]) == 3)
r = core._normalize_llm({"action": "none", "target": "", "reply": "impossible"})
check("normalize none -> steps vides", r["steps"] == [] and r["reply"] == "impossible")

# --- IA multi-fournisseurs : erreurs humanisées + ordre du mode auto ---
import requests as _rq


def _http_err(code, headers=None):
    resp = _rq.models.Response()
    resp.status_code = code
    resp.headers.update(headers or {})
    return _rq.exceptions.HTTPError(response=resp)


check("human_err 429 -> quota", "Quota" in core._human_err(_http_err(429)))
check("human_err 401 -> clé", "Clé" in core._human_err(_http_err(401)))
check("human_err 404 -> modèle", "Modèle" in core._human_err(_http_err(404)))
check("human_err timeout", "Délai" in core._human_err(_rq.exceptions.Timeout()))
check("cooldown 429 >= 60 s", core._cooldown_for(_http_err(429)) >= 60)
check("cooldown 429 Retry-After",
      core._cooldown_for(_http_err(429, {"Retry-After": "120"})) == 120)

_old_key, _old_ollama = core.get_api_key, core.ollama_models
_old_prov = core.CFG.get("provider")
_old_status = core.CFG.get("provider_status")
_old_health = dict(core.PROV_HEALTH)
try:
    core.get_api_key = lambda n: "x" if n in ("openai", "gemini") else ""
    core.ollama_models = lambda: None
    core.CFG["provider"] = "auto"
    core.CFG["provider_status"] = {}
    core.PROV_HEALTH.clear()
    check("provider_order sans santé", core.provider_order() == ["openai", "gemini"])
    core._mark_provider("openai", False, detail="quota", cooldown=60)
    core._mark_provider("gemini", True, ms=500)
    check("provider_order validé d'abord", core.provider_order() == ["gemini", "openai"])
    check("resolve_provider = meilleur", core.resolve_provider() == "gemini")
    core.CFG["provider"] = "openai"
    check("provider_order fixe", core.provider_order() == ["openai"])
finally:
    core.get_api_key, core.ollama_models = _old_key, _old_ollama
    core.CFG["provider"] = _old_prov
    core.CFG["provider_status"] = _old_status
    core.PROV_HEALTH.clear()
    core.PROV_HEALTH.update(_old_health)

check("stt_prompt contient Nova", "Nova" in core.stt_prompt())
check("gemini défaut 2.5-flash",
      core.DEFAULT_CONFIG["providers"]["gemini"]["model"] == "gemini-2.5-flash")

# --- plusieurs commandes dans une phrase ---
check("split_multi et",
      core.split_multi("ouvre youtube et mets un minuteur de 10 minutes")
      == ["ouvre youtube", "mets un minuteur de 10 minutes"])
check("split_multi puis",
      core.split_multi("ouvre le bloc-notes puis écris bonjour")
      == ["ouvre le bloc-notes", "écris bonjour"])
check("split_multi message intact",
      core.split_multi("dis à paul que j'arrive et que je serai en retard") is None)
check("split_multi recherche intacte",
      core.split_multi("cherche fromage et vin") is None)
check("split_multi phrase simple", core.split_multi("ouvre youtube") is None)

# --- garde-fou shell ---
check("shell_blocked format c:", core.shell_blocked("format c: /q"))
check("shell_blocked del /s", core.shell_blocked("del /s /q C:\\Users"))
check("shell_blocked rm -rf", core.shell_blocked("rm -rf /"))
check("shell autorisé shutdown", not core.shell_blocked("shutdown /s /t 3600"))
check("shell autorisé ipconfig", not core.shell_blocked("ipconfig /flushdns"))

# --- ponctuation vocale ---
p = core.voice_punctuation("bonjour virgule ça va point à la ligne super")
check("voice_punctuation", p == "bonjour, ça va.\nSuper", repr(p))
p2 = core.voice_punctuation("tu viens point d'interrogation")
check("voice_punctuation interrogation", p2 == "tu viens?", repr(p2))

# --- stockage ---
storage.add_history("test", "phrase de test fumée", "final", "ok", "local", True)
h = storage.list_history("fumée", 5)
check("storage history insert+search", len(h) >= 1 and h[0]["text"] == "phrase de test fumée")
pid = storage.ensure_default_profile()
check("storage default profile", bool(pid))
p = storage.get_profile(pid)
p["contacts"] = [{"name": "Paul Test", "phone": "+33600000000", "email": ""}]
storage.save_profile(p)
core.CFG["active_profile"] = pid
c = modes.find_contact("paul")
check("find_contact fuzzy", c is not None and c["phone"] == "+33600000000")

# --- infos personnelles (« mon adresse » → valeur préremplie) ---
p = storage.get_profile(pid)
p["personal"] = {"adresse": "12 rue des Lilas, 75011 Paris",
                 "telephone": "+33612345678",
                 "email": "sasha@exemple.fr", "prenom": "Sasha"}
storage.save_profile(p)
t = core.fill_personal("voici mon adresse et mon numéro de téléphone")
check("fill_personal adresse+tel",
      t == "voici 12 rue des Lilas, 75011 Paris et +33612345678", repr(t))
t2 = core.fill_personal("mon adresse mail est sur la carte")
check("fill_personal email avant adresse",
      t2 == "sasha@exemple.fr est sur la carte", repr(t2))
t3 = core.fill_personal("je m'appelle mon prénom")
check("fill_personal prénom", t3 == "je m'appelle Sasha", repr(t3))

# --- secrets DPAPI ---
winext.set_secret("groq", "test-secret-123")
check("secret roundtrip", winext.get_secret("groq") == "test-secret-123")
check("secret presence", winext.secrets_presence()["groq"] is True)
winext.set_secret("groq", "")
check("secret delete", not winext.has_secret("groq"))

# --- media vk table ---
check("media vk", winext.MEDIA_VK["playPause"] == 0xB3 and winext.MEDIA_VK["next"] == 0xB0)

# --- Nova 2.7 : minuteur tolérant aux erreurs de transcription ---
r = modes.classify("meilleur minuteur de dix minutes")
check('classify "meilleur minuteur de dix minutes" -> timer',
      r is not None and r[0] == "timer" and timers.parse_duration(r[1]) == 600, str(r))
r = modes.classify("mets-moi un minuteur de 5 minutes")
check('classify "mets-moi un minuteur de 5 minutes" -> timer',
      r is not None and r[0] == "timer" and timers.parse_duration(r[1]) == 300, str(r))
r = modes.classify("tu peux mettre un minuteur de dix minutes")
check('classify politesse "tu peux mettre un minuteur…" -> timer',
      r is not None and r[0] == "timer" and timers.parse_duration(r[1]) == 600, str(r))
r = modes.classify("règle un minuteur sur dix minutes")
check('classify "règle un minuteur sur dix minutes" -> timer',
      r is not None and r[0] == "timer" and timers.parse_duration(r[1]) == 600, str(r))
r = modes.classify("mets un minuteur de 10 minutes pour les pâtes")
check("classify minuteur avec libellé « pour les pâtes »",
      r is not None and r[0] == "timer" and timers.parse_duration(r[1]) == 600
      and r[2] == "les pates", str(r))
check("classify question sur minuteur -> timer_count (réponse locale JARVIS)",
      (modes.classify("combien de temps reste sur le minuteur") or ("",))[0] == "timer_count")
r = modes.classify("arrête le minuteur")
check('classify "arrête le minuteur" -> timer_cancel',
      r is not None and r[0] == "timer_cancel", str(r))

# --- Nova 2.7 : garde-fou média « phrase entière » ---
r = modes.classify("monte le son s'il te plaît")
check("media couvre la phrase -> volUp", r is not None and r[0] == "media"
      and r[1] == "volUp", str(r))
check("media enfoui dans une phrase riche -> IA",
      modes.classify("baisse le son des que tu peux et previens paul") is None)
r = modes.classify("mets en pause la musique")
check("media pause + article -> playPause", r is not None and r[0] == "media"
      and r[1] == "playPause", str(r))

# --- Nova 2.7 : politesse strippée avant les règles rapides ---
r = modes.classify("est-ce que tu peux ouvrir youtube")
check('classify "est-ce que tu peux ouvrir youtube" -> open',
      r is not None and r[0] == "open" and "youtube.com" in r[1], str(r))
r = modes.classify("nova ouvre youtube")
check('classify "nova ouvre youtube" -> open',
      r is not None and r[0] == "open" and "youtube.com" in r[1], str(r))
r = modes.classify("j'aimerais que tu ouvres spotify")
check('classify "j\'aimerais que tu ouvres spotify" -> open',
      r is not None and r[0] == "open" and "spotify" in r[1], str(r))
check("strip_politeness empilée",
      core.strip_politeness("nova est-ce que tu peux ouvrir youtube") == "ouvrir youtube")
check("matches_phrase avec politesse en tête",
      core.matches_phrase("ouvre youtube", "est-ce que tu peux ouvre youtube"))

# --- Nova 2.7 : split_multi élargi ---
check("split_multi montre-moi + ouvre",
      core.split_multi("montre-moi le bureau et ouvre youtube")
      == ["montre-moi le bureau", "ouvre youtube"])
check("split_multi règle + mets",
      core.split_multi("règle la luminosité et mets un minuteur de cinq minutes")
      == ["règle la luminosité", "mets un minuteur de cinq minutes"])

# --- Nova 2.7 : agent planificateur ---
check("LLM_SCHEMA 12 étapes",
      core.LLM_SCHEMA["properties"]["steps"]["maxItems"] == 12)
nr = core._normalize_llm({"reply": "ok",
                          "steps": [{"action": "wait", "target": "1"}] * 14})
check("_normalize_llm borne à 12", len(nr["steps"]) == 12)
check("prompt : doctrine de décomposition",
      "Décompose TOUTE la demande" in core.LLM_SYSTEM_TEMPLATE
      and "étapes intermédiaires" in core.LLM_SYSTEM_TEMPLATE)
check("pause auto open -> type_text", core._auto_pause("open_app", "type_text") > 0)
check("pause auto absente sinon", core._auto_pause("type_text", "keys") == 0.0
      and core._auto_pause("wait", "type_text") == 0.0)

# --- Nova 2.8 : reformulation, minuteur visible, vraies applis ---
check("config relisten par défaut", core.DEFAULT_CONFIG.get("relisten_on_fail") is True)
check("config minuteur visible par défaut", core.DEFAULT_CONFIG.get("timer_style") == "web")
check("chemin web 10 minutes", core._timer_web_path(600) == "10minutes")
check("chemin web 90 secondes", core._timer_web_path(90) == "90seconds")
core.CFG["timer_style"] = "nova"   # pas d'onglet pendant les tests
tid3 = core.start_timer(60, "essai 2.8")
check("start_timer moteur interne", any(t["id"] == tid3 for t in timers.list_active()))
timers.cancel(tid3)
d = modes._do_timer("1 minute", "", "")
check("_do_timer style nova sans onglet", "onglet" not in d["detail"], d["detail"])
timers.cancel_all()
r = modes.classify("ouvre l'horloge")
check('classify "ouvre l\'horloge" -> ms-clock:',
      r is not None and r[0] == "open" and r[1] == "ms-clock:", str(r))
check("prompt : vraies applis en priorité",
      "vraies applications Windows" in core.LLM_SYSTEM_TEMPLATE)

# --- Nova 2.9 : volume précis, fenêtres, fuzzy, vision, mails, comptes ---
r = modes.classify("mets le volume à 30 %")
check('classify "mets le volume à 30 %" -> volume set',
      r == ("volume", "set", "30"), str(r))
r = modes.classify("volume à 50")
check('classify "volume à 50" -> volume set', r == ("volume", "set", "50"), str(r))
r = modes.classify("monte le son de 20")
check('classify "monte le son de 20" -> volume +20',
      r == ("volume", "rel", "+20"), str(r))
r = modes.classify("baisse le volume de 10")
check('classify "baisse le volume de 10" -> volume -10',
      r == ("volume", "rel", "-10"), str(r))
r = modes.classify("coupe le son de chrome")
check('classify "coupe le son de chrome" -> mute appli',
      r == ("volume", "mute_app", "chrome"), str(r))
r = modes.classify("monte le son")
check('classify "monte le son" -> media volUp (inchangé)',
      r is not None and r[0] == "media" and r[1] == "volUp", str(r))
r = modes.classify("bascule sur word")
check('classify "bascule sur word" -> window focus',
      r == ("window", "focus", "word"), str(r))
r = modes.classify("mets chrome et word côte à côte")
check('classify "côte à côte" -> window split',
      r == ("window", "split", "chrome||word"), str(r))
check("split_multi ne coupe pas le côte à côte",
      core.split_multi("mets chrome et word côte à côte") is None)
r = modes.classify("ouvre youtub")
check('fuzzy "ouvre youtub" -> youtube',
      r is not None and r[0] == "open" and "youtube.com" in r[1], str(r))
r = modes.classify("lance spotifi")
check('fuzzy "lance spotifi" -> spotify',
      r is not None and r[0] == "open" and "spotify" in r[1], str(r))
check("RE_SCREEN « lis ce mail »", bool(modes.RE_SCREEN.search("lis ce mail")))
check("RE_SCREEN « résume cette page »",
      bool(modes.RE_SCREEN.search(core.normalize("résume cette page"))))
check("RE_SCREEN « regarde mon écran »",
      bool(modes.RE_SCREEN.search(core.normalize("regarde ce qu'il y a sur mon écran"))))
check("RE_SCREEN ignore « ouvre youtube »",
      not modes.RE_SCREEN.search("ouvre youtube"))
r = modes.classify("lis mes mails")
check('classify "lis mes mails" -> mode mails', r is not None and r[0] == "mails", str(r))
check("vision : fournisseurs compatibles",
      core.VISION_PROVIDERS == ("anthropic", "openai", "gemini"))
check("config conversation continue par défaut",
      core.DEFAULT_CONFIG.get("continuous_conversation") is True)
check("config vision par défaut", core.DEFAULT_CONFIG.get("screen_vision") is True)
s = storage.stats_summary()
check("stats_summary structure",
      all(k in s for k in ("total", "rate", "today", "top")), str(s))
check("winext volume lisible", winext.get_volume() is None
      or isinstance(winext.get_volume(), int))
check("winext fenêtre inexistante -> None",
      winext.find_window("zz-fenetre-inexistante-42") is None)
check("comptes non connectés par défaut",
      integrations.google_connected() is False
      and integrations.spotify_connected() is False)

# --- Nova 2.10 : appli vs site, vision élargie, réactivité, réessayer ---
r = modes.classify("ouvre google chrome")
check('classify "ouvre google chrome" -> APPLICATION chrome',
      r == ("open", "chrome", "google chrome"), str(r))
r = modes.classify("ouvre chrome")
check('classify "ouvre chrome" -> app', r == ("open", "chrome", "chrome"), str(r))
r = modes.classify("lance firefox")
check('classify "lance firefox" -> app', r is not None and r[1] == "firefox", str(r))
r = modes.classify("ouvre google")
check('classify "ouvre google" -> site (inchangé)',
      r is not None and "google.com" in r[1], str(r))
core.CFG["custom_apps"] = {"photoshop": "photoshop.exe",
                           "mon site": "https://exemple.fr"}
r = modes.classify("ouvre photoshop")
check("custom_apps exe", r == ("open", "photoshop.exe", "photoshop"), str(r))
r = modes.classify("ouvre mon site")
check("custom_apps url", r is not None and r[1] == "https://exemple.fr", str(r))
core.CFG["custom_apps"] = {}
check("RE_SCREEN « regarde ça »",
      bool(modes.RE_SCREEN.search(core.normalize("regarde ça"))))
check("RE_SCREEN « qu'est-ce que tu vois »",
      bool(modes.RE_SCREEN.search("qu'est-ce que tu vois")))
check("RE_SCREEN « traduis ça »", bool(modes.RE_SCREEN.search("traduis ca")))
check("RE_SCREEN ignore « regarde la télévision »",
      not modes.RE_SCREEN.search(core.normalize("regarde la télévision")))
check("record_audio accepte end_silence",
      "end_silence" in core.record_audio.__code__.co_varnames)
check("prompt : réfléchir appli vs site",
      "APPLICATION INSTALLÉE" in core.LLM_SYSTEM_TEMPLATE)

# --- Nova 2.11 : automatisations v2 + vision look_screen ---
a = core._migrate_automation({"name": "x", "phrases": ["y"],
                              "action": {"type": "keys", "target": "a"}})
check("automatisation migrée : enabled par défaut", a.get("enabled") is True)
c = modes.automation_conflict({"phrases": ["ouvre youtube"]})
check("conflit détecté « ouvre youtube »", bool(c), repr(c))
c = modes.automation_conflict({"phrases": ["verrouille le pc"]})
check("conflit détecté « verrouille le pc »", bool(c), repr(c))
c = modes.automation_conflict({"phrases": ["eteins le pc dans une heure"]})
check("pas de conflit phrase originale", c == "", repr(c))
check("action look_screen déclarée", "look_screen" in core.LLM_ACTIONS)
check("prompt décrit look_screen", "look_screen" in core.LLM_SYSTEM_TEMPLATE)
nr = core._normalize_llm({"reply": "je regarde",
                          "steps": [{"action": "look_screen", "target": ""}]})
check("_normalize_llm garde look_screen",
      nr["steps"] and nr["steps"][0]["action"] == "look_screen")
check("stt_prompt amorce « écran »", "écran" in core.stt_prompt())

# --- Nova 2.12 : mémoire longue, briefing, transcription rapide ---
r = modes.classify("souviens-toi que ma plaque est ab 123 cd")
check('classify "souviens-toi que…" -> memory',
      r == ("memory", "remember", "ma plaque est ab 123 cd"), str(r))
r = modes.classify("retiens que je gare la voiture au niveau 2")
check('classify "retiens que…" -> memory', r is not None and r[0] == "memory", str(r))
r = modes.classify("souviens-toi de sortir les pâtes dans 10 minutes")
check("« souviens-toi … dans 10 minutes » = RAPPEL, pas un fait",
      r is not None and r[0] == "timer" and "pates" in r[2], str(r))
r = modes.classify("oublie le minuteur")
check('"oublie le minuteur" -> annulation minuteur (pas mémoire)',
      r is not None and r[0] == "timer_cancel", str(r))
r = modes.classify("oublie ma plaque")
check('"oublie ma plaque" -> memory forget',
      r == ("memory", "forget", "ma plaque"), str(r))
r = modes.classify("mon briefing")
check('"mon briefing" -> briefing', r is not None and r[0] == "briefing", str(r))
r = modes.classify("bonjour")
check('"bonjour" -> briefing', r is not None and r[0] == "briefing", str(r))
storage.add_fact("test 2.12 : ma plaque est AB-123-CD")
facts = storage.list_facts()
check("fait enregistré", any("AB-123-CD" in f["fact"] for f in facts))
check("fait injecté dans le cerveau IA", "AB-123-CD" in core._llm_system())
gone = storage.forget_fact("ma plaque")
check("forget_fact retrouve le bon fait", gone is not None and "AB-123-CD" in gone)
check("fait bien supprimé",
      not any("AB-123-CD" in f["fact"] for f in storage.list_facts()))
check("transcribe_routed accepte fast",
      "fast" in core.transcribe_routed.__code__.co_varnames)

# --- Nova 2.12 : correctifs de la revue adversariale ---
r = modes.classify("souviens-toi que j'habite dans le bâtiment 7")
check("« dans le bâtiment 7 » = FAIT, pas un minuteur de 7 min",
      r is not None and r[0] == "memory" and r[1] == "remember", str(r))
r = modes.classify("oublie le rappel")
check('"oublie le rappel" -> annulation, pas mémoire',
      r is not None and r[0] == "timer_cancel", str(r))
r = modes.classify("annule la minuterie")
check('"annule la minuterie" -> timer_cancel (article la)',
      r is not None and r[0] == "timer_cancel", str(r))
r = modes.classify("oublie ça")
check('"oublie ça" -> rétractation, pas suppression de fait',
      r == ("memory", "dismiss", ""), str(r))
storage.add_fact("test 2.12b : mon chat s'appelle Léo")
check("forget_fact ignore les mots-outils (pas de suppression parasite)",
      storage.forget_fact("mon adresse") is None)
check("le fait chat existe toujours",
      any("Léo" in f["fact"] for f in storage.list_facts()))
gone = storage.forget_fact("mon chat")
check("forget_fact cible le bon fait", gone is not None and "Léo" in gone)
check("TTS_END : garde anti-écho présente",
      "TTS_END" in open("app.py", encoding="utf-8").read())

# --- Nova 2.13 : héritage JARVIS ---
import files_mode
core.CFG["ha_entities"] = {
    "salon": {"type": "light", "id": "light.salon"},
    "prise télé": {"type": "switch", "id": "switch.tv"},
    "chambre": {"type": "sensor", "id": "sensor.chambre_temp"}}
r = modes.classify("allume la lumière du salon")
check("HA allumer", r == ("home", "on:light.salon", "salon"), str(r))
r = modes.classify("éteins la lumière du salon")
check("HA éteindre", r == ("home", "off:light.salon", "salon"), str(r))
r = modes.classify("mets le salon en bleu")
check("HA couleur", r == ("home", "color:light.salon", "bleu"), str(r))
r = modes.classify("mets la lumière du salon à 40%")
check("HA luminosité", r == ("home", "bright:light.salon", "40"), str(r))
r = modes.classify("allume la prise télé")
check("HA prise", r is not None and r[0] == "home" and r[1].startswith("plugon:"), str(r))
r = modes.classify("quelle température dans la chambre")
check("HA température", r is not None and r[0] == "home"
      and r[1].startswith("temp:"), str(r))
core.CFG["ha_entities"] = {}
check("sans HA config : « allume la lumière » n'est pas capté",
      modes.classify("allume la lumière du salon") is None
      or modes.classify("allume la lumière du salon")[0] != "home")
core.CFG["routines"] = {"boulot": ["chrome", "documents", "musique"]}
check("routine « au boulot »",
      modes.classify("au boulot") == ("routine", "boulot", ""))
check("routine « mode boulot »",
      modes.classify("mode boulot") == ("routine", "boulot", ""))
core.CFG["routines"] = {}
r = modes.classify("trie mes téléchargements")
check("fichiers : trier", r is not None and r[0] == "files"
      and r[1].startswith("sort:"), str(r))
r = modes.classify("cherche le fichier facture")
check("fichiers : chercher", r == ("files", "find:facture", ""), str(r))
check("resolve_folder téléchargements",
      files_mode.resolve_folder("telechargements") is not None)
r = modes.classify("ouvre mes téléchargements")
check("ouvrir un dossier connu", r is not None and r[0] == "open"
      and "Downloads" in r[1], str(r))
r = modes.classify("ajoute le lait à ma liste de courses")
check("liste : ajouter", r == ("list", "add:courses", "le lait"), str(r))
r = modes.classify("montre ma liste de courses")
check("liste : montrer", r == ("list", "show:courses", ""), str(r))
storage.list_clear("courses")
storage.list_add("lait", "courses")
storage.list_add("pain", "courses")
check("liste stockée", storage.list_items("courses") == ["lait", "pain"])
check("liste retrait", storage.list_remove("lait", "courses")
      and storage.list_items("courses") == ["pain"])
storage.list_clear("courses")
r = modes.classify("mets de la musique")
check("musique attitrée", r == ("music_default", "spotify", ""), str(r))
r = modes.classify("mets de la musique sur youtube")
check("musique attitrée youtube", r == ("music_default", "youtube", ""), str(r))
check("« joue jul sur youtube » reste une recherche",
      modes.classify("joue jul sur youtube")[0] == "music")
check("docs.new connu", "nouveau document" in modes.SITES)
check("RE_CLICK capture la cible",
      modes.RE_CLICK.match("clique sur le bouton lecture") is not None)
check("ask_vision_box existe", hasattr(core, "ask_vision_box"))
check("grid_windows existe", hasattr(winext, "grid_windows"))
check("ha_token dans SECRET_KEYS", "ha_token" in winext.SECRET_KEYS)

# --- Nova 2.14 : portage complet du JARVIS installé -------------------------
import fun_mode


def cls(p):
    r = modes.classify(p)
    return r[0] if r else None


# Vague 1 : voix et écoute
for p in ("merci", "stop", "au revoir", "c'est tout", "bonne nuit", "tais-toi"):
    check(f"dismiss « {p} »", cls(p) == "dismiss")
check("« merci de fermer chrome » n'est PAS un dismiss",
      cls("merci de fermer chrome") is None)
_app_src = open("app.py", encoding="utf-8").read()
check("anti-écho : la boucle d'éveil consulte l'état TTS réel",
      "tts_active()" in _app_src)
check("interruption vocale câblée", "INTERRUPT_RE" in _app_src
      and "_check_interrupt" in _app_src)
check("stop_tts coupe SAPI et MP3", "stop_mp3" in _app_src)
check("session sans mot d'éveil", "session_timeout" in _app_src)
check("bip d'accusé", "wake_ack_sound" in _app_src)
check("double clap mutualisé", "clap_threshold" in _app_src)
check("micro sélectionnable", hasattr(core, "list_mics")
      and "mic_device_index" in core.DEFAULT_CONFIG)
check("voix Edge configurée", core.DEFAULT_CONFIG["tts"].get("engine") == "sapi"
      and "edge_voice" in core.DEFAULT_CONFIG["tts"])
check("lecteur MP3 natif", hasattr(winext, "play_mp3")
      and hasattr(winext, "mp3_playing"))
check("état TTS réel dans le pont", hasattr(winext.tts_bridge, "speaking"))

# Vague 2 : compréhension et routage
r = modes.classify("rappelle-moi le sport à 15h30")
check("rappel heure fixe", r == ("timer_at", "15:30", "le sport"), str(r))
r = modes.classify("rappelle-moi à 9h de prendre le médicament")
check("rappel heure fixe inversé", r == ("timer_at", "09:00", "prendre le medicament"), str(r))
r = modes.classify("rappelle-moi le sport à 15h30 tous les jours")
check("rappel quotidien", r == ("timer_at", "15:30|d", "le sport"), str(r))
check("rejet 25 h", cls("rappelle-moi le sport à 25h30") != "timer_at")
check("non-régression rappel relatif",
      cls("rappelle-moi dans 10 minutes de sortir") == "timer")
check("ajuster minuteur", modes.classify("ajoute 5 minutes au minuteur")
      == ("timer_adjust", "+300", ""))
check("compter minuteurs", cls("combien de minuteurs") == "timer_count")
r = modes.classify("joue du jazz")
check("« joue du jazz » → musique", r is not None and r[0] == "music"
      and r[1] == "jazz", str(r))
check("« mets de la musique » reste attitrée", cls("mets de la musique") == "music_default")
check("fermer une appli", modes.classify("ferme chrome") == ("close", "chrome", ""))
check("« ferme la fenêtre » reste un raccourci", cls("ferme la fenetre") == "shortcut")
check("« stoppe la musique » reste média", cls("stoppe la musique") == "media")
check("veille PC", cls("mets le pc en veille") == "power")
check("arrêt = confirmation", modes.classify("eteins le pc")[1] == "off_ask")
check("arrêt différé direct", modes.classify("eteins le pc dans 30 minutes")[1] == "off:1800")
check("confirmation d'arrêt", cls("confirme l'arret du pc") == "power")
check("luminosité écran", modes.classify("mets la luminosite a 40")
      == ("bright", "set:40", ""))
check("heure à Tokyo", modes.classify("quelle heure est-il a tokyo")
      == ("info", "city_time", "tokyo"))
check("capitale", cls("quelle est la capitale du japon") == "info")
check("monnaie", cls("quelle est la monnaie de la suisse") == "info")
check("épellation", cls("epelle bonjour") == "info")
check("blague", cls("raconte-moi une blague") == "fun")
check("calcul mental", fun_mode.calcule("combien font 12 fois 8") == "Ça fait 96")
check("racine carrée", fun_mode.calcule("calcule la racine de 16") == "Ça fait 4")
check("« x » jamais global (pas de piège taxi)",
      fun_mode.calcule("calcule taxi sur paris") is None)
check("calcul : division / puissance / addition",
      fun_mode.calcule("calcule 10 divise par 4") == "Ça fait 2.5"
      and fun_mode.calcule("calcule 2 puissance 10") == "Ça fait 1024"
      and fun_mode.calcule("combien font 2 plus 2") == "Ça fait 4")
check("calcul sans eval : évaluateur AST équivalent",
      fun_mode._safe_eval("sqrt(16)/2") == 2.0
      and fun_mode._safe_eval("(2+3)*4") == 20)
check("calcul sans eval : code arbitraire rejeté",
      all(_calc_rejects(x) for x in
          ("__import__('os').system('x')", "(1).__class__", "lambda: 1")))
check("conversion km/miles", cls("50 km en miles") == "info")
check("mot de passe", cls("genere un mot de passe de 20 caracteres") == "info")
check("mot de passe : 16-64 chars", len(fun_mode.mot_de_passe(20)) == 20
      and len(fun_mode.mot_de_passe(200)) == 64)
check("compte à rebours Noël", cls("combien de jours avant noel") == "info")
check("batterie", cls("combien de batterie") == "sysinfo")
check("corbeille : vider", cls("vide la corbeille") == "trash")
check("« ouvre la corbeille » reste une ouverture", cls("ouvre la corbeille") == "open")
check("images", modes.classify("montre-moi des images de chats")
      == ("images", "chats", ""))
check("« montre la fenêtre de word » reste fenêtre",
      cls("montre la fenetre de word") == "window")
check("notes vocales : lire", cls("montre mes notes") == "notes_voice")
check("« montre ma liste de courses » reste liste",
      cls("montre ma liste de courses") == "list")
check("où est X", cls("ou est la tour eiffel") == "whereis")
check("« où est le fichier X » reste fichiers",
      cls("ou est le fichier facture") == "files")
check("aide vocale", cls("que peux-tu faire") == "help")
check("small-talk salut", modes.classify("salut") == ("smalltalk", "hello", ""))
check("small-talk ça va", cls("ca va") == "smalltalk")
check("« bonjour » reste le briefing", cls("bonjour") == "briefing")
check("action LLM fact", "fact" in core.LLM_ACTIONS)
check("action LLM home", "home" in core.LLM_ACTIONS)
check("contexte persistant", hasattr(storage, "conv_add")
      and hasattr(storage, "conv_recent"))
check("rappels persistés", hasattr(storage, "reminder_add"))
check("slots multi-tours", "PENDING_SLOT" in _app_src)
check("rattrapage IA", "ia_fallback_on_fail" in _app_src)

# Vague 3 : nouvelles fonctionnalités
check("YouTube recherche", modes.classify("cherche lofi sur youtube")
      == ("youtube", "search", "lofi"))
check("YouTube résumé", cls("resume cette video") == "youtube")
check("YouTube tendances", cls("les tendances gaming") == "youtube")
import time as _t
modes.PENDING_CHOICE.update(items=["u1", "u2"], t=_t.time())
check("choix vocal « le deuxième »",
      modes.classify("le deuxieme") == ("yt_choice", "1", ""))
modes.PENDING_CHOICE["items"] = []
check("« le deuxième » sans attente → rien", modes.classify("le deuxieme") is None)
check("sport classement", modes.classify("classement de la ligue 1")
      == ("sport", "table", "ligue 1"))
check("sport résultats", cls("resultats du psg") == "sport")
check("playlist nommée", modes.classify("joue la playlist discover weekly")
      == ("spotify_ctx", "playlist", "discover weekly"))
check("« lance ma playlist » reste attitrée", cls("lance ma playlist") == "music_default")
check("désinstaller", cls("desinstalle vlc") == "uninstall")
check("antivirus", cls("lance un scan antivirus") == "antivirus")
check("obsidian créer", cls("cree une note obsidian idees") == "obsidian")
check("obsidian chercher", cls("cherche vacances dans obsidian") == "obsidian")
check("dossier : créer", modes.classify("cree un dossier vacances 2026")[0] == "files")
check("tri par date", modes.classify("trie mes telechargements par date")[1]
      .startswith("sortdate:"))
check("tri simple intact", modes.classify("trie mes telechargements")[1]
      .startswith("sort:"))
check("contenu d'un dossier", cls("liste mes telechargements") == "files")
check("mosaïque", cls("ouvre mes quatre dossiers") == "files")
check("capture complète", cls("capture complete") == "screenshot")
check("« capture d'écran » reste le raccourci découpe",
      cls("capture d'ecran") == "shortcut")
check("agenda", cls("mon agenda") == "agenda")
check("gdoc créer", cls("cree un document nomme rapport") == "gdoc")
check("gdoc dicter", cls("ecris bonjour dans le doc") == "gdoc")
check("vision : écrire dans un champ",
      cls("ecris bonjour dans le champ de recherche") == "visionwrite")
check("webcam", cls("regarde-moi") == "camera")
check("« qu'est-ce que tu vois » reste l'écran", cls("qu'est-ce que tu vois") is None)
check("appel whatsapp", cls("appelle paul sur whatsapp") == "call")
check("URL dictée", modes.classify("ouvre lemonde.fr")
      == ("open", "https://lemonde.fr", "lemonde.fr"))
check("IP dictée", cls("va sur localhost:8123") == "open")
check("« ouvre la porte » ne part pas en URL", cls("ouvre la porte") is None)
check("volume par appli", modes.classify("monte le son de spotify")
      == ("volume", "app", "+20|spotify"))
check("« monte le son » reste média", cls("monte le son") == "media")
check("resolve_exe existe", hasattr(winext, "resolve_exe"))
check("close_app existe", hasattr(winext, "close_app"))
check("webcam winext", hasattr(winext, "camera_b64"))
check("grille par titres", hasattr(winext, "grid_windows_by_titles"))
check("clés youtube/serpapi déclarées",
      "youtube" in winext.SECRET_KEYS and "serpapi" in winext.SECRET_KEYS)
check("HA étendu", hasattr(integrations, "ha_climate_set")
      and hasattr(integrations, "ha_scene") and hasattr(integrations, "ha_all_states"))
check("Google agenda/docs", hasattr(integrations, "gcal_events")
      and hasattr(integrations, "gdoc_create"))
check("météo enrichie", hasattr(integrations, "weather_alerts"))
core.CFG["ha_entities"] = {
    "chauffage": {"type": "climate", "id": "climate.salon"},
    "porte": {"type": "lock", "id": "lock.entree"},
    "detente": {"type": "scene", "id": "scene.detente"}}
r = modes.classify("mets le chauffage à 20")
check("HA thermostat", r == ("home", "clim:climate.salon", "20"), str(r))
r = modes.classify("verrouille la porte")
check("HA verrou", r is not None and r[0] == "home"
      and r[1].startswith("lock:"), str(r))
check("« verrouille » seul reste win+l", cls("verrouille") == "shortcut")
r = modes.classify("active la scène détente")
check("HA scène", r is not None and r[0] == "home"
      and r[1].startswith("scene:"), str(r))
core.CFG["ha_entities"] = {}
check("modules 2.14 importables", all(__import__(m) is not None for m in
      ("yt_mode", "webinfo", "obsidian", "uninstall_mode", "iptv", "mobile")))
import webinfo
check("saison sportive dynamique (jamais en dur)",
      webinfo.saison_courante().count("-") == 1
      and str(_t.localtime().tm_year) in webinfo.saison_courante())

print("\n" + ("SMOKE FAILED: " + ", ".join(FAIL) if FAIL else "SMOKE OK"))
sys.exit(1 if FAIL else 0)
