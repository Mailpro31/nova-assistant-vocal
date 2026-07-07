# -*- coding: utf-8 -*-
"""
Intégrations réseau (portées de RoadSpeak) :
- détection de connectivité (ping léger, jamais bloquant),
- Twilio REST : SMS et appels réels (pas d'API publique Phone Link — honnête),
- Microsoft Graph : envoi de mails Outlook (OAuth device-code, une fois),
- Groq Whisper : reconnaissance vocale cloud opt-in.
"""

import io
import json
import threading
import time
import wave

import winext

# ---------------------------------------------------------- connectivité ----

_online = {"value": False}


def is_online():
    return _online["value"]


def _check_once():
    try:
        import requests
        r = requests.head("https://www.gstatic.com/generate_204", timeout=2.5)
        return r.status_code in (204, 200)
    except Exception:
        return False


def start_connectivity_loop():
    def loop():
        while True:
            _online["value"] = _check_once()
            time.sleep(20)
    threading.Thread(target=loop, daemon=True).start()


# ---------------------------------------------------------------- Twilio ----

def twilio_ready(cfg):
    return (winext.has_secret("twilio_sid") and winext.has_secret("twilio_token")
            and bool(cfg.get("twilio", {}).get("from_number")))


def _twilio_post(path, params):
    import requests
    sid = winext.get_secret("twilio_sid")
    token = winext.get_secret("twilio_token")
    if not sid or not token:
        raise RuntimeError("Twilio non configuré")
    r = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}{path}",
        auth=(sid, token), data=params, timeout=10)
    if r.status_code >= 400:
        try:
            msg = r.json().get("message", "")
        except Exception:
            msg = r.text[:150]
        raise RuntimeError(f"Twilio HTTP {r.status_code} : {msg}")
    return r.json()


def send_sms(cfg, to, body):
    return _twilio_post("/Messages.json", {
        "To": to, "From": cfg["twilio"]["from_number"], "Body": body}).get("sid", "ok")


def place_call(cfg, to, say_text=None):
    if say_text:
        esc = (say_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        twiml = f'<Response><Say language="fr-FR" loop="3">{esc}</Say></Response>'
    else:
        twiml = '<Response><Say language="fr-FR">Appel passé par Nova.</Say><Pause length="60"/></Response>'
    return _twilio_post("/Calls.json", {
        "To": to, "From": cfg["twilio"]["from_number"], "Twiml": twiml}).get("sid", "ok")


# ------------------------------------------------------- Microsoft Graph ----

_GRAPH_TENANT = "consumers"
_GRAPH_SCOPES = "offline_access Mail.Send User.Read"
_graph_poll = {"thread": None, "stop": False, "status": ""}


def graph_connected():
    return winext.has_secret("graph_refresh_token")


def graph_disconnect():
    winext.set_secret("graph_refresh_token", "")
    _graph_poll["stop"] = True
    return True


def graph_start_device_code():
    """Retourne {userCode, verificationUri} et lance le polling en arrière-plan."""
    import requests
    client_id = winext.get_secret("graph_client_id")
    if not client_id:
        raise RuntimeError("Client ID Azure absent (Réglages > Microsoft)")
    r = requests.post(
        f"https://login.microsoftonline.com/{_GRAPH_TENANT}/oauth2/v2.0/devicecode",
        data={"client_id": client_id, "scope": _GRAPH_SCOPES}, timeout=10)
    data = r.json()
    if r.status_code >= 400:
        raise RuntimeError(data.get("error_description", "device code refusé")[:200])

    _graph_poll["stop"] = False
    _graph_poll["status"] = "en attente"

    def poll():
        deadline = time.time() + data.get("expires_in", 900)
        interval = data.get("interval", 5)
        while not _graph_poll["stop"] and time.time() < deadline:
            time.sleep(interval)
            try:
                tr = requests.post(
                    f"https://login.microsoftonline.com/{_GRAPH_TENANT}/oauth2/v2.0/token",
                    data={"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                          "client_id": client_id, "device_code": data["device_code"]},
                    timeout=10)
                tj = tr.json()
                if tr.status_code == 200 and tj.get("refresh_token"):
                    winext.set_secret("graph_refresh_token", tj["refresh_token"])
                    _graph_poll["status"] = "connecté"
                    return
                if tj.get("error") not in ("authorization_pending", "slow_down", None):
                    _graph_poll["status"] = "échec"
                    return
            except Exception:
                pass
        if _graph_poll["status"] == "en attente":
            _graph_poll["status"] = "expiré"

    _graph_poll["thread"] = threading.Thread(target=poll, daemon=True)
    _graph_poll["thread"].start()
    return {"userCode": data["user_code"], "verificationUri": data["verification_uri"]}


def graph_status():
    return {"connected": graph_connected(), "pending": _graph_poll["status"]}


def _graph_access_token():
    import requests
    client_id = winext.get_secret("graph_client_id")
    refresh = winext.get_secret("graph_refresh_token")
    if not client_id or not refresh:
        return None
    r = requests.post(
        f"https://login.microsoftonline.com/{_GRAPH_TENANT}/oauth2/v2.0/token",
        data={"grant_type": "refresh_token", "client_id": client_id,
              "refresh_token": refresh, "scope": _GRAPH_SCOPES}, timeout=10)
    data = r.json()
    if r.status_code >= 400:
        return None
    if data.get("refresh_token"):
        winext.set_secret("graph_refresh_token", data["refresh_token"])
    return data.get("access_token")


def graph_send_mail(to, subject, body):
    import requests
    token = _graph_access_token()
    if not token:
        return False
    r = requests.post(
        "https://graph.microsoft.com/v1.0/me/sendMail",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": {"subject": subject,
                          "body": {"contentType": "Text", "content": body},
                          "toRecipients": [{"emailAddress": {"address": to}}]}},
        timeout=10)
    return r.status_code == 202


# ----------------------------------------------------------------- météo ----

def weather(city=""):
    """Météo actuelle via wttr.in (gratuit, sans clé). city vide = ville par
    défaut des réglages, sinon localisation estimée par IP.
    Retourne {temp, feels, desc, city, humidite, vent}."""
    import urllib.parse
    import requests
    if not city:
        try:
            import core as _core
            city = (_core.CFG.get("city") or "").strip()
        except Exception:
            pass
    url = f"https://fr.wttr.in/{urllib.parse.quote(city)}?format=j1"
    r = requests.get(url, timeout=8, headers={"User-Agent": "curl/8"})
    r.raise_for_status()
    j = r.json()
    cur = j["current_condition"][0]
    desc = ((cur.get("lang_fr") or [{}])[0].get("value")
            or cur["weatherDesc"][0]["value"]).strip()
    area = (j.get("nearest_area") or [{}])[0]
    name = city or (area.get("areaName") or [{}])[0].get("value", "")
    return {"temp": cur.get("temp_C", "?"), "feels": cur.get("FeelsLikeC", ""),
            "desc": desc, "city": name,
            "humidite": cur.get("humidity", ""),
            "vent": cur.get("windspeedKmph", "")}


def weather_alerts(city=""):
    """Alertes météo sur 3 jours (Open-Meteo, sans clé) : orages, neige,
    fortes pluies (> 20 mm), vent violent (> 60 km/h). Liste de phrases,
    vide si rien à signaler (JARVIS)."""
    import requests
    if not city:
        try:
            import core as _core
            city = (_core.CFG.get("city") or "").strip()
        except Exception:
            pass
    try:
        if city:
            g = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                             params={"name": city, "count": 1, "language": "fr"},
                             timeout=6).json()
            hit = (g.get("results") or [{}])[0]
            lat, lon = hit.get("latitude"), hit.get("longitude")
        else:
            ip = requests.get("https://ipapi.co/json", timeout=4).json()
            lat, lon = ip.get("latitude"), ip.get("longitude")
        if lat is None or lon is None:
            return []
        f = requests.get("https://api.open-meteo.com/v1/forecast", timeout=8,
                         params={"latitude": lat, "longitude": lon,
                                 "forecast_days": 3, "timezone": "auto",
                                 "daily": "weathercode,precipitation_sum,"
                                          "windspeed_10m_max"}).json()
        d = f.get("daily") or {}
        jours = ("aujourd'hui", "demain", "après-demain")
        out = []
        for i in range(min(3, len(d.get("time") or []))):
            code = (d.get("weathercode") or [])[i] or 0
            rain = (d.get("precipitation_sum") or [])[i] or 0
            wind = (d.get("windspeed_10m_max") or [])[i] or 0
            if code in (95, 96, 99):
                out.append(f"orages {jours[i]}")
            if code in (71, 73, 75, 85, 86):
                out.append(f"neige {jours[i]}")
            if rain > 20:
                out.append(f"fortes pluies {jours[i]} ({rain:.0f} mm)")
            if wind > 60:
                out.append(f"vent violent {jours[i]} ({wind:.0f} km/h)")
        return out
    except Exception:
        return []


# ------------------------------------------------------------ Groq (STT) ----

def groq_transcribe(audio_f32, language="fr", model="whisper-large-v3-turbo", prompt=""):
    """Whisper cloud (opt-in). audio_f32 : np.float32 16 kHz mono."""
    import numpy as np
    import requests
    key = winext.get_secret("groq")
    if not key:
        raise RuntimeError("clé Groq absente")
    pcm = (np.clip(audio_f32, -1, 1) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm)
    buf.seek(0)
    data = {"model": model, "language": language}
    if prompt:
        data["prompt"] = prompt[:200]
    r = requests.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {key}"},
        files={"file": ("audio.wav", buf, "audio/wav")},
        data=data, timeout=12)
    r.raise_for_status()
    return (r.json().get("text") or "").strip()


# --------------------------------------------- comptes Google & Spotify -----
# OAuth « application installée » : le navigateur s'ouvre une fois, le code
# revient sur 127.0.0.1, les jetons sont chiffrés (DPAPI) dans secrets.json.

OAUTH_STATUS = {"google": "", "spotify": ""}
_G_PORT, _S_PORT = 8765, 8766


def _catch_code(port, timeout=240):
    """Mini serveur local one-shot : récupère ?code=… du retour OAuth."""
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import parse_qs, urlparse
    box = {}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            box["code"] = (parse_qs(urlparse(self.path).query).get("code") or [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(("<body style='font-family:sans-serif;background:#0F1014;"
                              "color:#ECEFF7;display:grid;place-items:center;height:95vh'>"
                              "<h2>Nova est connecté — tu peux fermer cet onglet</h2>"
                              "</body>").encode("utf-8"))

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", port), H)
    srv.timeout = timeout
    srv.handle_request()
    srv.server_close()
    return box.get("code", "")


# ---- Google (Gmail lecture) ----

_g_token = {"access": "", "exp": 0.0}


def google_connected():
    return bool(winext.get_secret("google_refresh"))


def google_start():
    """Ouvre le consentement Google. Le Client ID/Secret vient de l'utilisateur
    (Google Cloud Console > Identifiants > ID client OAuth « Application de bureau »)."""
    import webbrowser
    from urllib.parse import urlencode
    cid = winext.get_secret("google_client_id")
    sec = winext.get_secret("google_client_secret")
    if not cid or not sec:
        raise RuntimeError("Renseigne d'abord le Client ID et le Secret Google")
    redirect = f"http://127.0.0.1:{_G_PORT}"
    OAUTH_STATUS["google"] = "en attente du navigateur…"
    # scopes élargis (JARVIS) : agenda en lecture + Docs/Sheets en écriture —
    # les comptes déjà reliés doivent se RECONNECTER pour en profiter
    webbrowser.open("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code",
        "scope": ("https://www.googleapis.com/auth/gmail.readonly "
                  "https://www.googleapis.com/auth/calendar.readonly "
                  "https://www.googleapis.com/auth/documents "
                  "https://www.googleapis.com/auth/spreadsheets"),
        "access_type": "offline", "prompt": "consent"}))

    def wait():
        import requests
        code = _catch_code(_G_PORT)
        if not code:
            OAUTH_STATUS["google"] = "échec (pas de code reçu)"
            return
        r = requests.post("https://oauth2.googleapis.com/token", timeout=15, data={
            "grant_type": "authorization_code", "code": code,
            "client_id": cid, "client_secret": sec, "redirect_uri": redirect})
        tj = r.json()
        if tj.get("refresh_token"):
            winext.set_secret("google_refresh", tj["refresh_token"])
            _g_token.update(access=tj.get("access_token", ""),
                            exp=time.time() + tj.get("expires_in", 3500) - 60)
            OAUTH_STATUS["google"] = "connecté"
        else:
            OAUTH_STATUS["google"] = "échec : " + str(tj.get("error", r.status_code))

    threading.Thread(target=wait, daemon=True).start()


def google_disconnect():
    winext.set_secret("google_refresh", "")
    _g_token.update(access="", exp=0.0)
    OAUTH_STATUS["google"] = ""
    return True


def _google_access():
    import requests
    if _g_token["access"] and time.time() < _g_token["exp"]:
        return _g_token["access"]
    refresh = winext.get_secret("google_refresh")
    if not refresh:
        raise RuntimeError("Google non connecté")
    r = requests.post("https://oauth2.googleapis.com/token", timeout=15, data={
        "grant_type": "refresh_token", "refresh_token": refresh,
        "client_id": winext.get_secret("google_client_id"),
        "client_secret": winext.get_secret("google_client_secret")})
    tj = r.json()
    if not tj.get("access_token"):
        raise RuntimeError("Jeton Google expiré — reconnecte le compte")
    _g_token.update(access=tj["access_token"],
                    exp=time.time() + tj.get("expires_in", 3500) - 60)
    return _g_token["access"]


def gmail_unread(n=3):
    """Les n derniers mails non lus : [{from, subject}]."""
    import requests
    tok = _google_access()
    h = {"Authorization": f"Bearer {tok}"}
    base = "https://gmail.googleapis.com/gmail/v1/users/me"
    ids = requests.get(f"{base}/messages", timeout=15, headers=h, params={
        "q": "is:unread category:primary", "maxResults": n}).json().get("messages", [])
    out = []
    for m in ids[:n]:
        d = requests.get(f"{base}/messages/{m['id']}", timeout=15, headers=h, params={
            "format": "metadata", "metadataHeaders": ["From", "Subject"]}).json()
        hdrs = {x["name"].lower(): x["value"]
                for x in d.get("payload", {}).get("headers", [])}
        sender = hdrs.get("from", "?").split("<")[0].strip(' "') or "?"
        out.append({"from": sender, "subject": hdrs.get("subject", "(sans objet)")})
    return out


def gcal_events(n=5):
    """Les n prochains événements de l'agenda principal : [{titre, debut}]."""
    import requests
    from datetime import datetime, timezone
    tok = _google_access()
    r = requests.get(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        timeout=15, headers={"Authorization": f"Bearer {tok}"},
        params={"timeMin": datetime.now(timezone.utc).isoformat(),
                "singleEvents": "true", "orderBy": "startTime",
                "maxResults": n})
    out = []
    for e in r.json().get("items", []):
        start = e.get("start", {})
        out.append({"titre": e.get("summary", "(sans titre)"),
                    "debut": start.get("dateTime", start.get("date", ""))})
    return out


# ---- Google Docs / Sheets (création et dictée à la voix, JARVIS) ----

_last_gdoc = {"id": "", "titre": ""}


def gdoc_create(titre, contenu=""):
    """Crée un Google Doc (+ contenu initial). Retourne son URL."""
    import requests
    tok = _google_access()
    h = {"Authorization": f"Bearer {tok}"}
    r = requests.post("https://docs.googleapis.com/v1/documents", timeout=15,
                      headers=h, json={"title": titre or "Document Nova"})
    r.raise_for_status()
    doc = r.json()
    _last_gdoc.update(id=doc["documentId"], titre=doc.get("title", titre))
    if contenu:
        requests.post(
            f"https://docs.googleapis.com/v1/documents/{doc['documentId']}:batchUpdate",
            timeout=15, headers=h,
            json={"requests": [{"insertText": {
                "location": {"index": 1}, "text": contenu}}]})
    return "https://docs.google.com/document/d/" + doc["documentId"]


def gdoc_append(contenu):
    """Ajoute une ligne à la FIN du dernier doc créé (le titre reste intact —
    corrige le bug JARVIS qui insérait à l'index 1). False si aucun doc."""
    import requests
    if not _last_gdoc["id"]:
        return False
    tok = _google_access()
    h = {"Authorization": f"Bearer {tok}"}
    r = requests.get(
        f"https://docs.googleapis.com/v1/documents/{_last_gdoc['id']}",
        timeout=15, headers=h)
    r.raise_for_status()
    end = r.json()["body"]["content"][-1].get("endIndex", 2) - 1
    rr = requests.post(
        f"https://docs.googleapis.com/v1/documents/{_last_gdoc['id']}:batchUpdate",
        timeout=15, headers=h,
        json={"requests": [{"insertText": {
            "location": {"index": max(1, end)}, "text": "\n" + contenu}}]})
    return rr.status_code == 200


def gsheet_create(titre):
    """Crée un Google Sheet. Retourne son URL."""
    import requests
    tok = _google_access()
    r = requests.post("https://sheets.googleapis.com/v4/spreadsheets", timeout=15,
                      headers={"Authorization": f"Bearer {tok}"},
                      json={"properties": {"title": titre or "Feuille Nova"}})
    r.raise_for_status()
    return r.json().get("spreadsheetUrl", "")


# ---- Spotify (lecture réelle) ----

_s_token = {"access": "", "exp": 0.0}
_s_verifier = {"v": ""}


def spotify_connected():
    return bool(winext.get_secret("spotify_refresh"))


def spotify_start():
    """Consentement Spotify en PKCE : seul le Client ID est nécessaire
    (developer.spotify.com > Dashboard > Create app, redirect http://127.0.0.1:8766)."""
    import base64
    import hashlib
    import secrets as pysecrets
    import webbrowser
    from urllib.parse import urlencode
    cid = winext.get_secret("spotify_client_id")
    if not cid:
        raise RuntimeError("Renseigne d'abord le Client ID Spotify")
    verifier = base64.urlsafe_b64encode(pysecrets.token_bytes(40)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    _s_verifier["v"] = verifier
    redirect = f"http://127.0.0.1:{_S_PORT}"
    OAUTH_STATUS["spotify"] = "en attente du navigateur…"
    webbrowser.open("https://accounts.spotify.com/authorize?" + urlencode({
        "client_id": cid, "response_type": "code", "redirect_uri": redirect,
        "code_challenge_method": "S256", "code_challenge": challenge,
        "scope": "user-modify-playback-state user-read-playback-state"}))

    def wait():
        import requests
        code = _catch_code(_S_PORT)
        if not code:
            OAUTH_STATUS["spotify"] = "échec (pas de code reçu)"
            return
        r = requests.post("https://accounts.spotify.com/api/token", timeout=15, data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": redirect, "client_id": cid,
            "code_verifier": _s_verifier["v"]})
        tj = r.json()
        if tj.get("refresh_token"):
            winext.set_secret("spotify_refresh", tj["refresh_token"])
            _s_token.update(access=tj.get("access_token", ""),
                            exp=time.time() + tj.get("expires_in", 3500) - 60)
            OAUTH_STATUS["spotify"] = "connecté"
        else:
            OAUTH_STATUS["spotify"] = "échec : " + str(tj.get("error", r.status_code))

    threading.Thread(target=wait, daemon=True).start()


def spotify_disconnect():
    winext.set_secret("spotify_refresh", "")
    _s_token.update(access="", exp=0.0)
    OAUTH_STATUS["spotify"] = ""
    return True


def _spotify_access():
    import requests
    if _s_token["access"] and time.time() < _s_token["exp"]:
        return _s_token["access"]
    refresh = winext.get_secret("spotify_refresh")
    if not refresh:
        raise RuntimeError("Spotify non connecté")
    r = requests.post("https://accounts.spotify.com/api/token", timeout=15, data={
        "grant_type": "refresh_token", "refresh_token": refresh,
        "client_id": winext.get_secret("spotify_client_id")})
    tj = r.json()
    if not tj.get("access_token"):
        raise RuntimeError("Jeton Spotify expiré — reconnecte le compte")
    if tj.get("refresh_token"):
        winext.set_secret("spotify_refresh", tj["refresh_token"])
    _s_token.update(access=tj["access_token"],
                    exp=time.time() + tj.get("expires_in", 3500) - 60)
    return _s_token["access"]


def spotify_play_context(context_uri):
    """Lance une playlist/album entier (spotify:playlist:xxx) sur l'appareil
    actif. True si lancé, False sinon (l'appelant retombe sur le web)."""
    import requests
    tok = _spotify_access()
    h = {"Authorization": f"Bearer {tok}"}
    pr = requests.put("https://api.spotify.com/v1/me/player/play", timeout=15,
                      headers=h, json={"context_uri": context_uri})
    return pr.status_code in (200, 204)


def spotify_uri_from_url(text):
    """Lien ou URI Spotify → context_uri (playlist/album/artiste/titre)."""
    import re as _re
    m = _re.search(r"spotify[:/](?:.*?/)?(playlist|album|artist|track)"
                   r"[:/]([A-Za-z0-9]{22})", text or "")
    return f"spotify:{m.group(1)}:{m.group(2)}" if m else None


def spotify_play_item(query, kind="playlist"):
    """Cherche une playlist/album/artiste par nom et la lance sur l'appareil
    actif (JARVIS). Retourne le nom joué, ou None (repli web)."""
    import requests
    tok = _spotify_access()
    h = {"Authorization": f"Bearer {tok}"}
    r = requests.get("https://api.spotify.com/v1/search", timeout=15, headers=h,
                     params={"q": query, "type": kind, "limit": 1}).json()
    items = [i for i in ((r.get(kind + "s") or {}).get("items") or []) if i]
    if not items:
        return None
    it = items[0]
    return it.get("name") if spotify_play_context(it["uri"]) else None


def spotify_play(query):
    """Cherche un titre et le joue sur l'appareil actif. Retourne le nom joué,
    ou None si aucun appareil actif (l'appelant retombe sur le web)."""
    import requests
    tok = _spotify_access()
    h = {"Authorization": f"Bearer {tok}"}
    r = requests.get("https://api.spotify.com/v1/search", timeout=15, headers=h,
                     params={"q": query, "type": "track", "limit": 1}).json()
    items = r.get("tracks", {}).get("items", [])
    if not items:
        return None
    track = items[0]
    pr = requests.put("https://api.spotify.com/v1/me/player/play", timeout=15,
                      headers=h, json={"uris": [track["uri"]]})
    if pr.status_code == 404:      # aucun appareil Spotify actif
        return None
    pr.raise_for_status()
    return f"{track['name']} — {track['artists'][0]['name']}"


# ------------------------------------------------ Home Assistant (2.13) -----
# Domotique portée de JARVIS (TechEnClair) : lumières, prises, capteurs.
# URL dans config (ha_url), jeton chiffré DPAPI (secret « ha_token »),
# entités déclarées dans Réglages > Maison (nom vocal → entity_id).

def _ha_conf():
    import core
    return (core.CFG.get("ha_url") or "").rstrip("/"), winext.get_secret("ha_token")


def ha_ready():
    url, tok = _ha_conf()
    return bool(url and tok)


def ha_call(domaine, service, entity_id, donnees=None):
    """POST /api/services/<domaine>/<service> — True si accepté."""
    import requests
    url, tok = _ha_conf()
    payload = {"entity_id": entity_id}
    if donnees:
        payload.update(donnees)
    r = requests.post(f"{url}/api/services/{domaine}/{service}",
                      headers={"Authorization": f"Bearer {tok}",
                               "Content-Type": "application/json"},
                      json=payload, timeout=6)
    return r.status_code in (200, 201)


def ha_state(entity_id, attribut=None):
    """État d'une entité (« on », « 21.5 »…), ou None si injoignable."""
    import requests
    url, tok = _ha_conf()
    try:
        r = requests.get(f"{url}/api/states/{entity_id}", timeout=6,
                         headers={"Authorization": f"Bearer {tok}"})
        data = r.json()
        if attribut:
            return data.get("attributes", {}).get(attribut)
        return data.get("state")
    except Exception:
        return None


def ha_light(entity_id, etat="on", brightness_pct=None, rgb=None):
    """Allume/éteint/bascule une lumière, avec luminosité (%) et couleur."""
    service = "toggle" if etat == "toggle" else \
        ("turn_on" if etat == "on" else "turn_off")
    donnees = {}
    if etat == "on":
        if brightness_pct is not None:
            donnees["brightness_pct"] = max(1, min(100, int(brightness_pct)))
        if rgb is not None:
            donnees["rgb_color"] = rgb
    return ha_call("light", service, entity_id, donnees)


def ha_scene(entity_id):
    """Active une scène Home Assistant."""
    return ha_call("scene", "turn_on", entity_id)


def ha_all_lights(on=True):
    """Toutes les lumières d'un coup (entity_id spécial « all »)."""
    return ha_call("light", "turn_on" if on else "turn_off", "all")


def ha_climate_set(entity_id, temp):
    """Consigne du thermostat (bornée par l'appelant, 5-30 °C)."""
    return ha_call("climate", "set_temperature", entity_id,
                   {"temperature": float(temp)})


def ha_lock(entity_id, lock=True):
    return ha_call("lock", "lock" if lock else "unlock", entity_id)


def ha_alarm(entity_id, arm=True):
    return ha_call("alarm_control_panel",
                   "alarm_arm_away" if arm else "alarm_disarm", entity_id)


def ha_vacuum(entity_id, action="start"):
    svc = {"start": "start", "stop": "stop", "pause": "pause",
           "dock": "return_to_base"}.get(action, "start")
    return ha_call("vacuum", svc, entity_id)


def ha_all_states():
    """Tous les états HA (picker d'entités + section « en direct » de l'UI).
    [] si injoignable. Le jeton ne sort JAMAIS d'ici."""
    import requests
    url, tok = _ha_conf()
    if not url or not tok:
        return []
    try:
        r = requests.get(f"{url}/api/states", timeout=10,
                         headers={"Authorization": f"Bearer {tok}"})
        out = []
        for s in r.json():
            eid = s.get("entity_id", "")
            out.append({"id": eid, "domain": eid.split(".", 1)[0],
                        "name": (s.get("attributes") or {}).get("friendly_name", eid),
                        "state": s.get("state", "")})
        return out
    except Exception:
        return []


def ha_test():
    """Vérifie la connexion : GET /api/ répond « API running »."""
    import requests
    url, tok = _ha_conf()
    if not url or not tok:
        return False, "URL ou jeton manquant"
    try:
        r = requests.get(f"{url}/api/", timeout=6,
                         headers={"Authorization": f"Bearer {tok}"})
        if r.status_code == 200:
            return True, "Connecté à Home Assistant"
        if r.status_code == 401:
            return False, "Jeton refusé (401) : régénérez un jeton longue durée"
        return False, f"Réponse inattendue ({r.status_code})"
    except Exception as e:
        return False, f"Injoignable : {str(e)[:80]}"
