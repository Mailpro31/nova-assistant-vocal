# -*- coding: utf-8 -*-
"""
Accès mobile de Nova sur le réseau local : un petit serveur HTTP
(bibliothèque standard uniquement) sert la page ui_mobile/ et relaie
les échanges vers l'application — commandes texte, audio du micro du
téléphone (transcrit sur le PC par faster-whisper) et lecture de la
réponse en WAV. Rien ne sort du réseau local.

Opt-in : aucun port n'est ouvert tant que start() n'est pas appelé.
Un jeton d'appairage optionnel protège toutes les requêtes (?k=...) ;
côté app.py, il peut venir de winext.get_secret("mobile_token").

Branchement côté app.py :
    import mobile
    url = mobile.start({
        "run":        lambda texte: ...,    # lance la commande vocale
        "state":      lambda: {...},        # état courant (voir plus bas)
        "transcribe": lambda audio: "...",  # bytes webm/opus -> texte
        "say_wav":    lambda texte: b"...", # texte -> WAV en mémoire (ou None)
    }, port=8080, token="")
    ...
    mobile.stop()

Forme conseillée pour l'état (la page tolère les champs absents) :
    {"listening": bool, "status": "repos",
     "last": {"text": "...", "reply": "...", "ts": 171234.5},
     "timers": ["Pâtes — 8 min", ...]}
"""

import hmac
import json
import os
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

# état du module : un seul serveur à la fois
_server = None
_thread = None
_handlers = {}
_token = ""

_MAX_AUDIO = 16 * 1024 * 1024   # corps audio de /talk (webm/opus)
_MAX_JSON = 64 * 1024           # corps JSON de /command
_MAX_TTS = 400                  # longueur du texte lu par /tts

# fichiers servis (liste blanche : rien d'autre ne sort du dossier)
_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


def _log_err(context, err):
    """Erreur consignée via core si disponible, silencieuse sinon."""
    try:
        import core
        core.log_err(context, err)
    except Exception:
        pass


def _ui_dir():
    """Dossier ui_mobile/ : à côté de ce fichier, ou embarqué (PyInstaller)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "ui_mobile")


def get_local_ip():
    """IP de la machine sur le réseau local, obtenue par une connexion UDP
    fictive vers 8.8.8.8 (aucune donnée n'est envoyée)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.settimeout(2)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return "127.0.0.1"


def _dispatch_run(text):
    """Lance la commande dans un fil séparé : la réponse HTTP part tout de
    suite, le téléphone suit l'avancement en interrogeant /state."""
    fn = _handlers.get("run")
    if not fn:
        return

    def go():
        try:
            fn(text)
        except Exception as e:
            _log_err("mobile commande", e)

    threading.Thread(target=go, name="nova-mobile-cmd", daemon=True).start()


class _Handler(BaseHTTPRequestHandler):
    """Routes du serveur mobile. Aucun secret ne transite dans les réponses."""

    protocol_version = "HTTP/1.1"
    timeout = 30  # coupe les connexions muettes (délai réseau garanti)

    def log_message(self, fmt, *args):
        # journal HTTP coupé : la console de Nova reste lisible
        pass

    # ---- aides ------------------------------------------------------------
    def _allowed(self, query):
        """Vérifie le jeton d'appairage (comparaison à temps constant)."""
        if not _token:
            return True
        got = (query.get("k") or [""])[0]
        return hmac.compare_digest(got, _token)

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._bytes(data, "application/json; charset=utf-8", code)

    def _bytes(self, data, ctype, code=200, cache=False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=60" if cache else "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self, limit):
        """Lit le corps de la requête, borné à limit octets (None si invalide)."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if n <= 0 or n > limit:
            return None
        return self.rfile.read(n)

    # ---- routes GET --------------------------------------------------------
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if not self._allowed(query):
                self._json({"ok": False, "err": "jeton invalide"}, 403)
                return
            path = parsed.path
            if path in _FILES:
                self._static(path)
            elif path == "/state":
                self._route_state()
            elif path == "/tts":
                self._route_tts(query)
            else:
                self._json({"ok": False}, 404)
        except (ConnectionError, TimeoutError):
            pass  # le téléphone a raccroché : rien à faire
        except Exception as e:
            _log_err("mobile GET", e)

    def _static(self, path):
        """Sert un fichier de ui_mobile/ (liste blanche uniquement)."""
        name, ctype = _FILES[path]
        try:
            with open(os.path.join(_ui_dir(), name), "rb") as f:
                data = f.read()
        except OSError as e:
            _log_err("mobile fichier ui", e)
            self._json({"ok": False, "err": "interface introuvable"}, 404)
            return
        self._bytes(data, ctype, cache=True)

    def _route_state(self):
        """État courant de Nova, tel que fourni par app.py."""
        fn = _handlers.get("state")
        st = {}
        if fn:
            try:
                st = fn() or {}
            except Exception as e:
                _log_err("mobile état", e)
        if not isinstance(st, dict):
            st = {}
        self._json(st)

    def _route_tts(self, query):
        """Synthèse SAPI du PC renvoyée en WAV (404 si indisponible)."""
        text = ((query.get("text") or [""])[0] or "").strip()[:_MAX_TTS]
        if not text:
            self._json({"ok": False}, 400)
            return
        fn = _handlers.get("say_wav")
        wav = None
        if fn:
            try:
                wav = fn(text)
            except Exception as e:
                _log_err("mobile tts", e)
        if not wav:
            self._json({"ok": False}, 404)
            return
        self._bytes(bytes(wav), "audio/wav")

    # ---- routes POST -------------------------------------------------------
    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if not self._allowed(query):
                self._json({"ok": False, "err": "jeton invalide"}, 403)
                return
            if parsed.path == "/command":
                self._route_command()
            elif parsed.path == "/talk":
                self._route_talk()
            else:
                self._json({"ok": False}, 404)
        except (ConnectionError, TimeoutError):
            pass
        except Exception as e:
            _log_err("mobile POST", e)

    def _route_command(self):
        """Commande texte : {"text": "..."} -> file d'exécution de Nova."""
        body = self._body(_MAX_JSON)
        text = ""
        if body:
            try:
                text = (json.loads(body.decode("utf-8")).get("text") or "").strip()
            except Exception:
                text = ""
        if not text:
            self._json({"ok": False}, 400)
            return
        _dispatch_run(text)
        self._json({"ok": True})

    def _route_talk(self):
        """Audio du micro du téléphone (webm/opus) : transcription locale
        par faster-whisper, puis exécution comme une commande vocale."""
        body = self._body(_MAX_AUDIO)
        if not body:
            self._json({"ok": False}, 400)
            return
        fn = _handlers.get("transcribe")
        text = ""
        if fn:
            try:
                text = (fn(body) or "").strip()
            except Exception as e:
                _log_err("mobile transcription", e)
        if text:
            _dispatch_run(text)
        self._json({"text": text})


def _url(port):
    """URL à ouvrir sur le téléphone (jeton inclus s'il y en a un)."""
    u = "http://%s:%d/" % (get_local_ip(), port)
    if _token:
        u += "?k=" + quote(_token, safe="")
    return u


def start(handlers, port=8080, token=""):
    """Démarre le serveur mobile sur toutes les interfaces (0.0.0.0).

    handlers : dict fourni par app.py — clés "run", "state", "transcribe"
    et "say_wav" (voir l'en-tête du module). token : jeton d'appairage
    optionnel ; s'il est fourni, chaque requête doit porter ?k=<token>.

    Retourne l'URL à ouvrir sur le téléphone, ou "" en cas d'échec
    (port déjà pris, par exemple). Sans effet si déjà démarré.
    """
    global _server, _thread, _handlers, _token
    if _server is not None:
        return _url(_server.server_address[1])
    _handlers = dict(handlers or {})
    _token = token or ""
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    except OSError as e:
        _log_err("mobile start", e)
        _handlers, _token = {}, ""
        return ""
    srv.daemon_threads = True
    _server = srv
    _thread = threading.Thread(target=srv.serve_forever,
                               name="nova-mobile", daemon=True)
    _thread.start()
    return _url(port)


def stop():
    """Arrête le serveur mobile et libère le port. Sans effet sinon."""
    global _server, _thread, _handlers, _token
    srv, thr = _server, _thread
    _server, _thread = None, None
    _handlers, _token = {}, ""
    if srv is None:
        return
    try:
        srv.shutdown()
        srv.server_close()
    except Exception as e:
        _log_err("mobile stop", e)
    if thr is not None:
        try:
            thr.join(timeout=3)
        except Exception:
            pass
