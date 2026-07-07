# -*- coding: utf-8 -*-
"""
YouTube à la voix (porté de JARVIS, youtube_api.py) : recherche multi-résultats,
infos vidéo et chaîne, tendances, dernières vidéos d'une chaîne, résumé par
sous-titres. Tout passe par l'API YouTube Data v3 ; la clé vit dans le coffre
(winext), jamais dans le code. Les fonctions rendent des structures ou None,
la mise en phrase reste dans modes.py.
"""

import re

import winext

_BASE = "https://www.googleapis.com/youtube/v3"
_TIMEOUT = 7  # secondes, appliqué à toutes les requêtes

# catégories vocales → ID de catégorie YouTube (valeurs de JARVIS)
CATEGORIES = {
    "musique": "10",
    "jeux": "20", "jeu": "20", "gaming": "20",
    "sport": "17", "sports": "17",
    "science": "28", "technologie": "28", "tech": "28",
    "cinéma": "1", "cinema": "1", "film": "1",
    "actualité": "25", "actualites": "25", "info": "25", "infos": "25",
    "comédie": "23", "comedie": "23", "humour": "23",
}


# ------------------------------------------------------------- utilitaires --

def _log(contexte, e):
    """Erreur journalisée via core quand il est importable, sinon silence.
    La clé API est expurgée : elle apparaît dans les URLs des exceptions requests."""
    try:
        import core
        core.log_err(contexte, re.sub(r"key=[^&\s'\"]+", "key=***", str(e)))
    except Exception:
        pass


def _cle():
    return winext.get_secret("youtube")


def ready():
    """Vrai si la clé API YouTube est configurée dans le coffre."""
    return bool(_cle())


def _get(endpoint, params):
    """GET sur l'API YouTube (clé et timeout ajoutés). Lève en cas d'échec réseau."""
    import requests
    params = dict(params)
    params["key"] = _cle()
    r = requests.get(f"{_BASE}/{endpoint}", params=params, timeout=_TIMEOUT)
    return r.json()


def _extraire_id(url_ou_id):
    """Extrait le video ID (11 caractères) d'une URL YouTube, ou le rend tel quel."""
    m = re.search(r"(?:v=|youtu\.be/|/embed/|/v/)([a-zA-Z0-9_-]{11})", url_ou_id or "")
    if m:
        return m.group(1)
    if re.match(r"^[a-zA-Z0-9_-]{11}$", (url_ou_id or "").strip()):
        return (url_ou_id or "").strip()
    return ""


def _duree(duree_iso):
    """Convertit une durée ISO 8601 (PT4M13S) en « 4 min 13 sec »."""
    m = re.search(r"(\d+)H", duree_iso or "")
    heures = int(m.group(1)) if m else 0
    m = re.search(r"(\d+)M", duree_iso or "")
    minutes = int(m.group(1)) if m else 0
    m = re.search(r"(\d+)S", duree_iso or "")
    secondes = int(m.group(1)) if m else 0
    parties = []
    if heures:
        parties.append(f"{heures}h")
    if minutes:
        parties.append(f"{minutes} min")
    if secondes:
        parties.append(f"{secondes} sec")
    return " ".join(parties) if parties else "durée inconnue"


def _nombre(n):
    """1234567 → « 1,2 million », 8500 → « 8 500 ». Virgule décimale française
    (JARVIS laissait le point anglo-saxon) ; les « ,0 » inutiles sont retirés."""
    if n >= 1_000_000_000:
        v = f"{n / 1_000_000_000:.1f}".replace(".", ",")
        v = v[:-2] if v.endswith(",0") else v
        return f"{v} milliard{'s' if n >= 2_000_000_000 else ''}"
    if n >= 1_000_000:
        v = f"{n / 1_000_000:.1f}".replace(".", ",")
        v = v[:-2] if v.endswith(",0") else v
        return f"{v} million{'s' if n >= 2_000_000 else ''}"
    if n >= 1_000:
        return f"{n:,}".replace(",", " ")
    return str(n)


def _chaine_id(nom):
    """Retourne (channel_id, titre officiel) pour un nom de chaîne, ou ("", "")."""
    try:
        data = _get("search", {"part": "snippet", "q": nom,
                               "type": "channel", "maxResults": 1})
        items = data.get("items", [])
        if not items:
            return "", ""
        return items[0]["id"]["channelId"], items[0]["snippet"]["title"]
    except Exception as e:
        _log("yt chaine_id", e)
        return "", ""


# --------------------------------------------------------------- recherche --

def chercher_multi(q, n=5):
    """Recherche : les N premiers résultats vidéo, enrichis (durée, vues) par
    un second appel /videos. Liste de dicts, vide si rien ou pas de clé."""
    if not ready() or not (q or "").strip():
        return []
    try:
        data = _get("search", {"part": "snippet", "q": q, "type": "video",
                               "maxResults": n, "relevanceLanguage": "fr"})
        items = data.get("items", [])
        if not items:
            return []
        ids = [it["id"]["videoId"] for it in items
               if it.get("id", {}).get("videoId")]
        # durées et statistiques en un seul appel groupé
        extras = {}
        try:
            d2 = _get("videos", {"part": "contentDetails,statistics",
                                 "id": ",".join(ids)})
            for it in d2.get("items", []):
                extras[it["id"]] = it
        except Exception as e:
            _log("yt chercher_multi détails", e)
        resultats = []
        for it in items:
            vid = it.get("id", {}).get("videoId", "")
            if not vid:
                continue
            ex = extras.get(vid, {})
            resultats.append({
                "titre": it["snippet"]["title"],
                "chaine": it["snippet"]["channelTitle"],
                "video_id": vid,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "duree": _duree(ex.get("contentDetails", {}).get("duration", "")),
                "vues": _nombre(int(ex.get("statistics", {}).get("viewCount", 0))),
            })
        return resultats
    except Exception as e:
        _log("yt chercher_multi", e)
        return []


def premiere_video(q):
    """URL du premier résultat pour une recherche, ou None."""
    if not ready() or not (q or "").strip():
        return None
    try:
        data = _get("search", {"part": "snippet", "q": q, "type": "video",
                               "maxResults": 1, "relevanceLanguage": "fr"})
        items = data.get("items", [])
        if not items:
            return None
        return f"https://www.youtube.com/watch?v={items[0]['id']['videoId']}"
    except Exception as e:
        _log("yt premiere_video", e)
        return None


# ------------------------------------------------------------------- infos --

def info_video(video_id):
    """Infos d'une vidéo (ID ou URL acceptés) : titre, chaîne, durée, vues,
    likes, date. None si introuvable ou pas de clé."""
    vid = _extraire_id(video_id)
    if not ready() or not vid:
        return None
    try:
        data = _get("videos", {"part": "snippet,statistics,contentDetails",
                               "id": vid})
        items = data.get("items", [])
        if not items:
            return None
        snip = items[0].get("snippet", {})
        stats = items[0].get("statistics", {})
        details = items[0].get("contentDetails", {})
        return {
            "titre": snip.get("title", "Titre inconnu"),
            "chaine": snip.get("channelTitle", "Chaîne inconnue"),
            "duree": _duree(details.get("duration", "")),
            "vues": _nombre(int(stats.get("viewCount", 0))),
            "likes": (_nombre(int(stats["likeCount"]))
                      if "likeCount" in stats else "non public"),
            "date": snip.get("publishedAt", "")[:10],
        }
    except Exception as e:
        _log("yt info_video", e)
        return None


def infos_chaine(nom):
    """Infos d'une chaîne cherchée par son nom : nom officiel, abonnés,
    nombre de vidéos, vues totales. None si introuvable ou pas de clé."""
    if not ready() or not (nom or "").strip():
        return None
    channel_id, titre = _chaine_id(nom)
    if not channel_id:
        return None
    try:
        data = _get("channels", {"part": "snippet,statistics", "id": channel_id})
        items = data.get("items", [])
        if not items:
            return None
        stats = items[0].get("statistics", {})
        return {
            "nom": titre,
            "abonnes": (_nombre(int(stats["subscriberCount"]))
                        if stats.get("subscriberCount") else "non public"),
            "videos": _nombre(int(stats.get("videoCount", 0))),
            "vues": _nombre(int(stats.get("viewCount", 0))),
        }
    except Exception as e:
        _log("yt infos_chaine", e)
        return None


# --------------------------------------------------------------- tendances --

def tendances(categorie="", pays="FR"):
    """Top 5 des vidéos en tendance (chart mostPopular, France par défaut),
    filtrable par catégorie vocale. Liste de dicts {titre, chaine, vues, url}."""
    if not ready():
        return []
    params = {"part": "snippet,statistics", "chart": "mostPopular",
              "regionCode": (pays or "FR").upper(), "maxResults": 5}
    cat_id = CATEGORIES.get((categorie or "").lower().strip(), "")
    if cat_id:
        params["videoCategoryId"] = cat_id
    try:
        items = _get("videos", params).get("items", [])
        return [{
            "titre": it["snippet"]["title"],
            "chaine": it["snippet"]["channelTitle"],
            "vues": _nombre(int(it.get("statistics", {}).get("viewCount", 0))),
            "url": f"https://www.youtube.com/watch?v={it['id']}",
        } for it in items]
    except Exception as e:
        _log("yt tendances", e)
        return []


def dernieres_videos(nom_chaine, n=3):
    """Les N dernières vidéos publiées par une chaîne (recherche par nom,
    puis /search trié par date). Liste de dicts {titre, date, video_id, url}."""
    if not ready() or not (nom_chaine or "").strip():
        return []
    channel_id, _titre = _chaine_id(nom_chaine)
    if not channel_id:
        return []
    try:
        data = _get("search", {"part": "snippet", "channelId": channel_id,
                               "order": "date", "type": "video", "maxResults": n})
        resultats = []
        for it in data.get("items", []):
            vid = it.get("id", {}).get("videoId", "")
            if not vid:
                continue
            resultats.append({
                "titre": it["snippet"]["title"],
                "date": it["snippet"]["publishedAt"][:10],
                "video_id": vid,
                "url": f"https://www.youtube.com/watch?v={vid}",
            })
        return resultats
    except Exception as e:
        _log("yt dernieres_videos", e)
        return []


# ------------------------------------------------------------------ résumé --

def resume_video(video_id_ou_url):
    """Résume une vidéo à partir de ses sous-titres (français prioritaire,
    sinon anglais), tronqués à 3000 mots. Résumé par l'IA de Nova quand elle
    est disponible, sinon début de la transcription. Rend toujours un texte."""
    vid = _extraire_id(video_id_ou_url)
    if not vid:
        return "Je n'ai pas pu identifier cette vidéo."

    titre = "cette vidéo"
    info = info_video(vid)
    if info:
        titre = info["titre"]

    # import paresseux : la lib n'est chargée qu'ici
    try:
        from youtube_transcript_api import (YouTubeTranscriptApi,
                                            NoTranscriptFound,
                                            TranscriptsDisabled)
    except ImportError:
        return ("Le module youtube-transcript-api n'est pas installé, "
                "je ne peux pas résumer les vidéos.")

    try:
        try:
            # API moderne (>= 1.0) : instance puis fetch(languages=...)
            segments = YouTubeTranscriptApi().fetch(vid, languages=["fr", "en"])
        except (TypeError, AttributeError):
            # ancienne API (< 1.0) : méthode de classe équivalente
            segments = YouTubeTranscriptApi.get_transcript(vid, languages=["fr", "en"])
    except (NoTranscriptFound, TranscriptsDisabled):
        return (f"« {titre} » n'a pas de sous-titres disponibles, "
                "je ne peux donc pas la résumer.")
    except Exception as e:
        _log("yt sous-titres", e)
        return "Je n'ai pas réussi à récupérer les sous-titres de cette vidéo."

    morceaux = []
    for seg in segments:
        t = getattr(seg, "text", None)
        if t is None and isinstance(seg, dict):
            t = seg.get("text", "")
        if t:
            morceaux.append(t)
    texte = " ".join(morceaux)
    mots = texte.split()
    if len(mots) > 3000:
        texte = " ".join(mots[:3000])
    if not texte.strip():
        return f"Les sous-titres de « {titre} » sont vides, impossible de la résumer."

    resume = None
    try:
        import core
        system = ("Tu résumes des transcriptions de vidéos YouTube. "
                  "Réponds en français, en 4 à 5 phrases concises, sans préambule.")
        resume = core.llm_complete(system, f"Vidéo « {titre} ». Transcription :\n{texte}")
    except Exception as e:
        _log("yt resume ia", e)
    if resume:
        return f"Voici le résumé de « {titre} » : {resume.strip()}"

    return (f"Pas d'IA disponible pour résumer « {titre} ». "
            f"Début de la transcription : {texte[:500].strip()}…")
