# -*- coding: utf-8 -*-
"""
Infos web à la voix (portées de JARVIS, TechEnClair) :
sport (TheSportsDB), recherche parlée, images et restaurants
(SerpAPI quand une clé est configurée, secours gratuits sinon),
géolocalisation approximative par IP. Tout se dégrade proprement :
None ou liste vide en cas d'échec, jamais d'exception à l'appelant.
"""

import re

import winext


def _log(context, err):
    """Trace l'erreur dans nova.log quand core est disponible, sinon silence.
    La clé SerpAPI est expurgée : elle apparaît dans l'URL des exceptions
    requests (ConnectionError/Timeout portent la query-string complète)."""
    try:
        import core
        core.log_err(context, re.sub(r"api_key=[^&\s'\"]+", "api_key=***", str(err)))
    except Exception:
        pass


# ------------------------------------------------------------------ sport ----

# TheSportsDB, clé publique de test « 3 » (documentée, pas un secret)
THESPORTSDB = "https://www.thesportsdb.com/api/v1/json/3"

# ligues connues : « le classement de la premier league »
LIGUE_IDS = {
    "ligue 1": "4334", "premier league": "4328", "liga": "4335",
    "bundesliga": "4331", "serie a": "4332", "champions league": "4480",
}


def saison_courante():
    """Saison de football en cours, calculée sur la date (ex. « 2025-2026 »)."""
    import datetime
    d = datetime.date.today()
    return f"{d.year}-{d.year + 1}" if d.month >= 8 else f"{d.year - 1}-{d.year}"


def _ligue_id(ligue):
    """Nom vocal de ligue → id TheSportsDB (Ligue 1 par défaut)."""
    nom = (ligue or "ligue 1").strip().lower()
    if nom in ("ligue des champions", "c1"):
        nom = "champions league"
    return nom, LIGUE_IDS.get(nom, LIGUE_IDS["ligue 1"])


def _chercher_equipe(nom):
    """Nom vocal d'équipe → (id, nom officiel) ou (None, None)."""
    import requests
    r = requests.get(f"{THESPORTSDB}/searchteams.php",
                     params={"t": nom}, timeout=5)
    teams = r.json().get("teams") or []
    if not teams:
        return None, None
    return teams[0].get("idTeam"), teams[0].get("strTeam") or nom


def resultats_equipe(nom):
    """Derniers matchs d'une équipe.
    Retourne {equipe, matchs: [{date, domicile, exterieur, score}], reply}
    ou None si équipe inconnue / réseau indisponible."""
    try:
        import requests
        team_id, team_name = _chercher_equipe(nom)
        if not team_id:
            return None
        r = requests.get(f"{THESPORTSDB}/eventslast.php",
                         params={"id": team_id}, timeout=5)
        data = r.json()
        evs = data.get("results")
        if not evs:  # variante d'API : liste chronologique complète
            evs = list(reversed((data.get("events") or [])[-6:]))
        if not evs:
            return None
        matchs = [{
            "date": m.get("dateEvent", "?"),
            "domicile": m.get("strHomeTeam", "?"),
            "exterieur": m.get("strAwayTeam", "?"),
            "score": f"{m.get('intHomeScore', '?')}-{m.get('intAwayScore', '?')}",
        } for m in evs[:6]]
        d = matchs[0]  # le plus récent en tête
        reply = (f"Dernier match de {team_name} : {d['domicile']} "
                 f"{d['score']} {d['exterieur']}, le {d['date']}.")
        return {"equipe": team_name, "matchs": matchs, "reply": reply}
    except Exception as e:
        _log("webinfo.resultats_equipe", e)
        return None


def prochain_match(nom):
    """Prochain match d'une équipe.
    Retourne {equipe, date, heure, domicile, exterieur, reply} ou None."""
    try:
        import requests
        team_id, team_name = _chercher_equipe(nom)
        if not team_id:
            return None
        r = requests.get(f"{THESPORTSDB}/eventsnext.php",
                         params={"id": team_id}, timeout=5)
        evs = r.json().get("events") or []
        if not evs:
            return None
        m = evs[0]
        date_m = m.get("dateEvent") or "date inconnue"
        heure = (m.get("strTime") or "")[:5]
        home = m.get("strHomeTeam", "?")
        away = m.get("strAwayTeam", "?")
        reply = f"Prochain match de {team_name} : {home} contre {away}, le {date_m}"
        if heure:
            reply += f" à {heure}"
        return {"equipe": team_name, "date": date_m, "heure": heure,
                "domicile": home, "exterieur": away, "reply": reply + "."}
    except Exception as e:
        _log("webinfo.prochain_match", e)
        return None


def classement(ligue=""):
    """Classement de la saison en cours (Ligue 1 par défaut).
    Retourne {ligue, saison, table: top 10, reply: top 5 à lire} ou None."""
    try:
        import requests
        nom, lid = _ligue_id(ligue)
        saison = saison_courante()
        r = requests.get(f"{THESPORTSDB}/lookuptable.php",
                         params={"l": lid, "s": saison}, timeout=8)
        table = r.json().get("table") or []
        if not table:
            return None
        rows = [{
            "rang": eq.get("intRank", "?"),
            "equipe": eq.get("strTeam", "?"),
            "points": eq.get("intPoints", "?"),
            "joues": eq.get("intPlayed", "?"),
        } for eq in table[:10]]
        top5 = ", ".join(f"{x['rang']}. {x['equipe']} {x['points']} points"
                         for x in rows[:5])
        return {"ligue": nom, "saison": saison, "table": rows,
                "reply": f"Classement {nom} : {top5}."}
    except Exception as e:
        _log("webinfo.classement", e)
        return None


# -------------------------------------------------------- recherche parlée ----

def _serpapi_texte(q):
    """Recherche Google via SerpAPI → texte court, ou None (pas de clé, échec)."""
    if not winext.has_secret("serpapi"):
        return None
    try:
        import requests
        r = requests.get("https://serpapi.com/search.json",
                         params={"engine": "google", "q": q,
                                 "api_key": winext.get_secret("serpapi"),
                                 "hl": "fr", "gl": "fr"}, timeout=10)
        data = r.json()
        news = data.get("news_results") or []
        if news:
            lignes = []
            for n in news[:3]:
                src = n.get("source") or "source inconnue"
                if isinstance(src, dict):
                    src = src.get("name") or "source inconnue"
                lignes.append(f"{n.get('title', '')} (via {src})")
            return "Dernières actualités : " + ". ".join(lignes)
        organic = data.get("organic_results") or []
        if organic:
            lignes = []
            for res in organic[:3]:
                titre = res.get("title", "")
                snippet = res.get("snippet", "")
                lignes.append(f"{titre} : {snippet}" if snippet else titre)
            return "Voici ce que j'ai trouvé : " + ". ".join(lignes)
    except Exception as e:
        _log("webinfo.serpapi", e)
    return None


def _duckduckgo_texte(q):
    """Réponse instantanée DuckDuckGo (gratuit, sans clé) → texte ou None."""
    try:
        import requests
        r = requests.get("https://api.duckduckgo.com/",
                         params={"q": q, "format": "json", "no_html": "1"},
                         timeout=8)
        return (r.json().get("AbstractText") or "").strip() or None
    except Exception as e:
        _log("webinfo.duckduckgo", e)
        return None


def web_search_speak(q):
    """Recherche web → texte court à lire à voix haute.
    None si rien d'exploitable (l'appelant ouvre alors le navigateur)."""
    q = (q or "").strip()
    if not q:
        return None
    return _serpapi_texte(q) or _duckduckgo_texte(q)


# ----------------------------------------------------------------- images ----

def _images_serpapi(q, nb):
    if not winext.has_secret("serpapi"):
        return []
    try:
        import requests
        r = requests.get("https://serpapi.com/search.json",
                         params={"engine": "google_images", "q": q,
                                 "api_key": winext.get_secret("serpapi"),
                                 "hl": "fr", "gl": "fr", "num": nb},
                         timeout=10)
        urls = []
        for img in (r.json().get("images_results") or [])[:nb]:
            src = img.get("original") or img.get("thumbnail")
            if src and src.startswith(("http://", "https://")):
                urls.append(src)
        return urls
    except Exception as e:
        _log("webinfo.images_serpapi", e)
        return []


def _images_duckduckgo(q, nb):
    """Images DuckDuckGo sans clé : jeton vqd extrait de la page, puis i.js."""
    try:
        import requests
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                 "AppleWebKit/537.36"}
        r = requests.get("https://duckduckgo.com/",
                         params={"q": q, "iax": "images", "ia": "images"},
                         headers=headers, timeout=8)
        m = re.search(r'vqd=["\']?([\d-]+)', r.text)
        if not m:
            return []
        r2 = requests.get("https://duckduckgo.com/i.js",
                          params={"l": "fr-fr", "o": "json", "q": q,
                                  "vqd": m.group(1), "f": ",,,,,", "p": "1"},
                          headers=headers, timeout=8)
        urls = []
        for item in (r2.json().get("results") or [])[:nb]:
            src = item.get("image")
            if src and src.startswith(("http://", "https://")):
                urls.append(src)
        return urls
    except Exception as e:
        _log("webinfo.images_duckduckgo", e)
        return []


def chercher_images(q, nb=6):
    """Recherche d'images → liste d'URLs http(s) ([] si échec)."""
    q = (q or "").strip()
    if not q:
        return []
    return _images_serpapi(q, nb) or _images_duckduckgo(q, nb)


# ------------------------------------------------------------- restaurants ----

def restaurants(ville=""):
    """Restaurants proches → liste [{nom, note, adresse, type}].
    Sans clé SerpAPI : liste vide (l'appelant retombe sur Google Maps).
    Téléphone et site ne sont jamais inventés, donc jamais renvoyés."""
    ville = (ville or "").strip() or city_from_ip()
    if not winext.has_secret("serpapi"):
        return []
    try:
        import requests
        r = requests.get("https://serpapi.com/search.json",
                         params={"engine": "google",
                                 "q": f"restaurants à {ville}",
                                 "api_key": winext.get_secret("serpapi"),
                                 "hl": "fr", "gl": "fr"}, timeout=8)
        lr = r.json().get("local_results")
        places = lr.get("places") if isinstance(lr, dict) else (lr or [])
        out = []
        for p in places or []:
            nom = (p.get("title") or "").strip()
            if not nom:
                continue
            out.append({"nom": nom,
                        "note": p.get("rating", 4.2),
                        "adresse": p.get("address") or ville,
                        "type": p.get("type") or "Restaurant"})
        return out[:6]
    except Exception as e:
        _log("webinfo.restaurants", e)
        return []


# ---------------------------------------------------------- géolocalisation ----

def city_from_ip():
    """Ville approximative par géolocalisation IP → « Ville, Pays »
    (secours : Paris, France)."""
    try:
        import requests
        r = requests.get("https://ipapi.co/json/", timeout=4)
        if r.status_code == 200:
            data = r.json()
            city = data.get("city")
            country = data.get("country_name")
            if city:
                return f"{city}, {country}" if country else city
    except Exception as e:
        _log("webinfo.city_from_ip", e)
    return "Paris, France"
