# -*- coding: utf-8 -*-
"""
Lecteur IPTV (porté de JARVIS) : chargement de playlists M3U/M3U8,
XSPF et PLS depuis un fichier local ou une URL, recherche tolérante
de chaînes, et serveur HTTP local de lecture (127.0.0.1:8767) avec
transcodage ffmpeg quand il est disponible dans le PATH.
Rien ne démarre au chargement du module : le serveur est lancé
paresseusement au premier stream_url().
"""

import os
import re
import json
import base64
import threading
import subprocess
import unicodedata
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# hôte et port du serveur local (8766 est pris par l'OAuth Spotify)
HOTE = "127.0.0.1"
PORT = 8767

# état du module : chaînes en mémoire + serveur HTTP
_chaines = []          # [{nom, url, logo, groupe}]
_serveur = None
_thread = None
_verrou = threading.Lock()
_ffmpeg_ok = None      # cache de la détection ffmpeg


def _log_err(contexte, err):
    """Erreurs vers le journal de Nova quand core est là, sinon silence."""
    try:
        import core
        core.log_err(contexte, err)
    except Exception:
        pass


def _normalise(texte):
    """Minuscules sans accents, pour les comparaisons tolérantes."""
    texte = unicodedata.normalize("NFD", (texte or "").lower())
    return "".join(c for c in texte if unicodedata.category(c) != "Mn").strip()


# ---------------------------------------------------------------- parseurs --

def _parse_m3u(contenu):
    """#EXTINF avec tvg-logo / tvg-name / group-title, puis l'URL qui suit."""
    res = []
    lignes = contenu.splitlines()
    i = 0
    while i < len(lignes):
        ligne = lignes[i].strip()
        if ligne.startswith("#EXTINF"):
            meta = ligne.split(":", 1)[1] if ":" in ligne else ""
            attrs, nom = (meta.rsplit(",", 1) + [""])[:2] if "," in meta else (meta, "")
            nom = nom.strip()
            m_logo = re.search(r'tvg-logo="([^"]*)"', attrs)
            m_nom = re.search(r'tvg-name="([^"]*)"', attrs)
            m_grp = re.search(r'group-title="([^"]*)"', attrs)
            if not nom and m_nom:
                nom = m_nom.group(1)
            # l'URL est la prochaine ligne non vide qui n'est pas un commentaire
            i += 1
            while i < len(lignes) and (not lignes[i].strip()
                                       or lignes[i].strip().startswith("#")):
                i += 1
            if i < len(lignes) and lignes[i].strip():
                res.append({"nom": nom or lignes[i].strip(),
                            "url": lignes[i].strip(),
                            "logo": m_logo.group(1) if m_logo else "",
                            "groupe": m_grp.group(1) if m_grp else ""})
        i += 1
    return res


def _parse_xspf(contenu):
    """Playlist XSPF : balises track/location/title/image (avec ou sans ns)."""
    res = []
    try:
        import xml.etree.ElementTree as ET
        racine = ET.fromstring(contenu)
    except Exception as e:
        _log_err("iptv.xspf", e)
        return res

    def _texte(piste, nom):
        for el in piste.iter():
            if el.tag.split("}")[-1] == nom:
                return (el.text or "").strip()
        return ""

    for piste in racine.iter():
        if piste.tag.split("}")[-1] != "track":
            continue
        url = _texte(piste, "location")
        if url:
            res.append({"nom": _texte(piste, "title") or url, "url": url,
                        "logo": _texte(piste, "image"), "groupe": ""})
    return res


def _parse_pls(contenu):
    """Playlist PLS : paires FileN= / TitleN=."""
    fichiers, titres = {}, {}
    for ligne in contenu.splitlines():
        m = re.match(r"^File(\d+)=(.+)$", ligne.strip(), re.IGNORECASE)
        if m:
            fichiers[m.group(1)] = m.group(2).strip()
        m = re.match(r"^Title(\d+)=(.+)$", ligne.strip(), re.IGNORECASE)
        if m:
            titres[m.group(1)] = m.group(2).strip()
    return [{"nom": titres.get(n, url), "url": url, "logo": "", "groupe": ""}
            for n, url in sorted(fichiers.items(), key=lambda kv: int(kv[0]))]


def _parse(contenu, indice=""):
    """Choisit le parseur selon l'extension puis, à défaut, le contenu."""
    ext = os.path.splitext(indice.split("?")[0])[1].lower()
    if ext in (".m3u", ".m3u8"):
        return _parse_m3u(contenu)
    if ext == ".xspf":
        return _parse_xspf(contenu)
    if ext == ".pls":
        return _parse_pls(contenu)
    debut = contenu.lstrip()[:400].lower()
    if debut.startswith("[playlist]"):
        return _parse_pls(contenu)
    if debut.startswith("<") and ("xspf" in debut or "<tracklist" in debut
                                  or "<playlist" in debut):
        return _parse_xspf(contenu)
    return _parse_m3u(contenu)


# ---------------------------------------------------------------- playlist --

def charge_playlist(source):
    """Charge une playlist (chemin local ou URL) et retourne les chaînes
    [{nom, url, logo, groupe}]. Les chaînes restent en mémoire module ;
    seuls la source et le compte sont persistés dans la config."""
    global _chaines
    source = (source or "").strip()
    if not source:
        return []
    try:
        if source.lower().startswith(("http://", "https://")):
            import requests  # import paresseux
            r = requests.get(source, headers={"User-Agent": "Nova/1.0"},
                             timeout=20)
            r.raise_for_status()
            contenu = r.text
        else:
            with open(source, "r", encoding="utf-8", errors="ignore") as f:
                contenu = f.read()
        _chaines = _parse(contenu, source)
    except Exception as e:
        _log_err("iptv.charge_playlist", e)
        return []
    if _chaines:
        try:
            import core
            core.save_config({"iptv": {"source": source,
                                       "chaines_count": len(_chaines)}})
        except Exception:
            pass
    return list(_chaines)


def chaines(filtre=""):
    """Liste des chaînes chargées, filtrée sur le nom ou le groupe."""
    f = _normalise(filtre)
    if not f:
        return list(_chaines)
    return [c for c in _chaines
            if f in _normalise(c["nom"]) or f in _normalise(c["groupe"])]


def trouve_chaine(nom):
    """Cherche une chaîne par nom (tolérant : exact, préfixe, inclusion,
    puis tous les mots présents). Retourne le dict ou None."""
    q = _normalise(nom)
    if not q or not _chaines:
        return None
    prefixe = inclusion = mots = None
    for c in _chaines:
        n = _normalise(c["nom"])
        if n == q:
            return c
        if prefixe is None and n.startswith(q):
            prefixe = c
        elif inclusion is None and q in n:
            inclusion = c
        elif mots is None and all(m in n for m in q.split()):
            mots = c
    return prefixe or inclusion or mots


# --------------------------------------------------------------------- flux --

def detect_type(url):
    """Type de flux : hls, dash, mp4 ou autre."""
    u = (url or "").lower().split("?")[0]
    if u.endswith(".m3u8") or "m3u8" in u:
        return "hls"
    if u.endswith(".mpd"):
        return "dash"
    if u.endswith((".mp4", ".m4v", ".webm", ".mov")):
        return "mp4"
    return "autre"


def _ffmpeg_dispo():
    """ffmpeg présent dans le PATH ? (résultat mis en cache)"""
    global _ffmpeg_ok
    if _ffmpeg_ok is None:
        import shutil
        _ffmpeg_ok = shutil.which("ffmpeg") is not None
    return _ffmpeg_ok


def _decode_u(jeton):
    """Décode le paramètre u= (URL en base64, variante standard ou urlsafe)."""
    try:
        jeton = jeton.replace(" ", "+").replace("-", "+").replace("_", "/")
        jeton += "=" * (-len(jeton) % 4)
        return base64.b64decode(jeton).decode("utf-8", "ignore").strip()
    except Exception:
        return ""


def _url_sure(u):
    """N'autorise que http/https vers un hôte réel : bloque file/concat/pipe/
    rtsp (lecture de fichiers locaux via ffmpeg) et le loopback. Le serveur
    IPTV écoute sans authentification — une page web ouverte par l'utilisateur
    ne doit pas pouvoir s'en servir pour lire un fichier local ou relayer une
    requête (SSRF)."""
    try:
        p = urllib.parse.urlparse(u)
    except Exception:
        return False
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    h = p.hostname.lower()
    if h in ("localhost", "127.0.0.1", "::1") or h.startswith("127."):
        return False
    return True


# ------------------------------------------------------------------ serveur --

class _Requete(BaseHTTPRequestHandler):
    """Routes : /video?u=<url b64> (transcodage ou redirection) et /probe."""

    def log_message(self, *args):
        pass  # pas de log HTTP sur la console

    def do_GET(self):
        try:
            p = urllib.parse.urlparse(self.path)
            u = _decode_u(urllib.parse.parse_qs(p.query).get("u", [""])[0])
            if p.path == "/probe":
                self._json({"ok": bool(u), "ffmpeg": _ffmpeg_dispo()})
            elif p.path == "/video" and u and _url_sure(u):
                if _ffmpeg_dispo():
                    self._ffmpeg(u)
                else:
                    # pas de transcodage possible : le navigateur lit en direct
                    self.send_response(302)
                    self.send_header("Location", u)
                    self.end_headers()
            else:
                self.send_error(404)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        except Exception as e:
            _log_err("iptv.http", e)

    def _json(self, donnees):
        corps = json.dumps(donnees).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def _ffmpeg(self, url):
        """Remuxe le flux en MP4 fragmenté (vidéo copiée, audio AAC) et le
        streame par blocs ; ffmpeg est arrêté dès que le client coupe."""
        # -protocol_whitelist AVANT -i : ffmpeg ne peut ni lire un fichier
        # local ni suivre une redirection HTTP→file (défense en profondeur)
        cmd = ["ffmpeg", "-loglevel", "quiet",
               "-protocol_whitelist", "http,https,tcp,tls,crypto",
               "-i", url,
               "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
               "-movflags", "frag_keyframe+empty_moov+default_base_moof",
               "-f", "mp4", "-"]
        drapeaux = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,
                                creationflags=drapeaux)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            while True:
                bloc = proc.stdout.read(65536)
                if not bloc:
                    break
                self.wfile.write(bloc)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # client parti : on coupe ffmpeg juste après
        except Exception as e:
            _log_err("iptv.ffmpeg", e)
        finally:
            # anti-zombie : terminaison propre, sinon kill
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


def _demarre_serveur():
    """Démarre le serveur local à la demande (idempotent)."""
    global _serveur, _thread
    with _verrou:
        if _serveur is not None:
            return True
        try:
            _serveur = ThreadingHTTPServer((HOTE, PORT), _Requete)
            _thread = threading.Thread(target=_serveur.serve_forever,
                                       daemon=True, name="Nova-IPTV")
            _thread.start()
            return True
        except Exception as e:
            _log_err("iptv.serveur", e)
            _serveur = None
            return False


def stream_url(chaine):
    """URL à donner à un <video> : via le serveur local (transcodage) si
    ffmpeg est là, sinon l'URL du flux telle quelle. Accepte un dict
    chaîne, un nom de chaîne ou directement une URL."""
    if isinstance(chaine, str):
        c = trouve_chaine(chaine)
        url = c["url"] if c else (chaine.strip() if "://" in chaine else "")
    else:
        url = (chaine or {}).get("url", "")
    if not url:
        return ""
    if _ffmpeg_dispo() and _demarre_serveur():
        jeton = base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii")
        return f"http://{HOTE}:{PORT}/video?u={jeton}"
    return url


def stop_server():
    """Arrête proprement le serveur local (sans effet s'il ne tourne pas)."""
    global _serveur, _thread
    with _verrou:
        if _serveur is None:
            return
        try:
            _serveur.shutdown()
            _serveur.server_close()
        except Exception as e:
            _log_err("iptv.stop", e)
        _serveur = None
        _thread = None
