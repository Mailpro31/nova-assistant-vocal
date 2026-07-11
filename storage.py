# -*- coding: utf-8 -*-
"""
Stockage SQLite (porté de RoadSpeak, schéma BRIEF §5) : historique complet
cherchable + profils multi-utilisateurs (vocabulaire, contacts).
sqlite3 est dans la bibliothèque standard — aucune dépendance.
"""

import json
import os
import sqlite3
import sys
import threading
import time
import uuid

APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
_DB = os.path.join(APP_DIR, "nova.db")
_lock = threading.Lock()
_conn = None

# Champs perso persistés (« Mes infos »). SOURCE UNIQUE : save_profile filtre
# là-dessus (une clé hors liste est silencieusement ignorée), et l'UI Réglages
# itère cette même liste — aucune dérive possible entre écran et stockage.
PERSONAL_FIELDS = ("prenom", "nom", "email", "telephone", "adresse")


def _db():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(_DB, check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                vocabulary TEXT,
                contacts TEXT,
                language TEXT DEFAULT 'fr',
                created_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS history (
                id TEXT PRIMARY KEY,
                profile_id TEXT,
                mode TEXT,
                raw_transcript TEXT,
                final_text TEXT,
                action_result TEXT,
                engine_used TEXT,
                ok INTEGER DEFAULT 1,
                created_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_history_created ON history(created_at DESC);
            CREATE TABLE IF NOT EXISTS facts (
                id TEXT PRIMARY KEY,
                fact TEXT NOT NULL,
                created_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS lists (
                id TEXT PRIMARY KEY,
                list TEXT NOT NULL,
                item TEXT NOT NULL,
                created_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS conversation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                time TEXT NOT NULL,
                date TEXT DEFAULT '',
                triggered INTEGER DEFAULT 0,
                created_at INTEGER
            );
        """)
        # migration : infos personnelles (« mon adresse » → valeur préremplie)
        cols = [r[1] for r in _conn.execute("PRAGMA table_info(profiles)").fetchall()]
        if "personal" not in cols:
            _conn.execute("ALTER TABLE profiles ADD COLUMN personal TEXT")
        _conn.commit()
    return _conn


# ------------------------------------------------------------- historique ---

def add_history(mode, raw, final="", result="", engine="", ok=True, profile_id=""):
    with _lock:
        _db().execute(
            "INSERT INTO history(id, profile_id, mode, raw_transcript, final_text,"
            " action_result, engine_used, ok, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (uuid.uuid4().hex[:10], profile_id, mode, raw, final, result, engine,
             1 if ok else 0, int(time.time() * 1000)))
        _db().commit()


def week_stats():
    """Dictées réussies, caractères produits et minutes de frappe évitées
    depuis lundi 00:00 (heure locale) — la stat de valeur affichée dans les
    Réglages (rétention : rappeler chaque semaine ce que Nova écrit pour vous).
    Borne volontairement simple (lundi local) : stat d'affichage, indépendante
    de la semaine ISO + grâce horloge du quota Free (licensing._effective_week).
    Conversion : ~5 caractères/mot, ~40 mots/min au clavier — source unique."""
    now = time.localtime()
    monday = time.mktime((now.tm_year, now.tm_mon, now.tm_mday - now.tm_wday,
                          0, 0, 0, 0, 0, -1)) * 1000
    row = _db().execute(
        "SELECT COUNT(*), COALESCE(SUM(LENGTH(COALESCE(NULLIF(final_text, ''),"
        " raw_transcript))), 0) FROM history WHERE ok = 1 AND created_at >= ?",
        (int(monday),)).fetchone()
    return {"count": row[0], "chars": row[1],
            "minutes": round(row[1] / 5 / 40)}


def list_history(search="", limit=60):
    q = "SELECT mode, raw_transcript, final_text, action_result, engine_used, ok, created_at FROM history"
    args = []
    if search:
        q += " WHERE raw_transcript LIKE ? OR final_text LIKE ? OR mode LIKE ?"
        args = [f"%{search}%"] * 3
    q += " ORDER BY created_at DESC LIMIT ?"
    args.append(max(1, min(500, limit)))
    rows = _db().execute(q, args).fetchall()
    return [{"mode": r[0], "text": r[1], "final": r[2], "result": r[3],
             "engine": r[4], "ok": bool(r[5]), "ts": r[6]} for r in rows]


def clear_history():
    with _lock:
        _db().execute("DELETE FROM history")
        _db().commit()
    return True


# ---------------------------------------------- mémoire longue (faits) ------

def add_fact(text):
    """« Souviens-toi que ma plaque est AB-123-CD » → fait durable, injecté
    dans le cerveau IA à chaque demande."""
    with _lock:
        _db().execute("INSERT INTO facts(id, fact, created_at) VALUES(?,?,?)",
                      (uuid.uuid4().hex[:8], text.strip(), int(time.time() * 1000)))
        _db().commit()
    return True


def list_facts(limit=40):
    rows = _db().execute(
        "SELECT id, fact, created_at FROM facts ORDER BY created_at DESC LIMIT ?",
        (limit,)).fetchall()
    return [{"id": r[0], "fact": r[1], "ts": r[2]} for r in rows]


def delete_fact(fid):
    with _lock:
        _db().execute("DELETE FROM facts WHERE id = ?", (fid,))
        _db().commit()
    return True


_STOPWORDS = {
    "mon", "ma", "mes", "ton", "ta", "tes", "son", "ses", "notre", "nos",
    "les", "des", "une", "aux", "est", "sont", "que", "qui", "quoi", "pas",
    "pour", "avec", "sur", "sous", "dans", "par", "c'est", "j'ai", "suis",
    "elle", "ils", "nous", "vous", "tout", "cette", "cela",
}


def forget_fact(query):
    """Supprime le fait qui ressemble le plus à la demande (mots communs,
    hors mots-outils : « mon », « est »… ne suffisent pas à matcher).
    Retourne le texte supprimé, ou None."""
    import unicodedata

    def norm(t):
        t = unicodedata.normalize("NFD", t.lower())
        return {w for w in "".join(c for c in t if unicodedata.category(c) != "Mn").split()
                if len(w) > 2 and w not in _STOPWORDS}

    q = norm(query)
    if not q:
        return None
    best, score = None, 0.0
    for f in list_facts(200):
        w = norm(f["fact"])
        if not w:
            continue
        s = len(q & w) / min(len(q), len(w))
        if s > score:
            best, score = f, s
    if best and score >= 0.5:
        delete_fact(best["id"])
        return best["fact"]
    return None


# ------------------------------------------------ listes vocales (2.13) -----

def list_items(name="courses"):
    rows = _db().execute(
        "SELECT item FROM lists WHERE list = ? ORDER BY created_at ASC",
        (name,)).fetchall()
    return [r[0] for r in rows]


def list_add(item, name="courses"):
    with _lock:
        _db().execute("INSERT INTO lists(id, list, item, created_at) VALUES(?,?,?,?)",
                      (uuid.uuid4().hex[:8], name, item.strip(),
                       int(time.time() * 1000)))
        _db().commit()
    return True


def list_remove(item, name="courses"):
    """Retire l'article dont le nom contient la requête. True si retiré."""
    q = item.strip().lower()
    with _lock:
        row = _db().execute(
            "SELECT id, item FROM lists WHERE list = ? AND lower(item) LIKE ?"
            " LIMIT 1", (name, f"%{q}%")).fetchone()
        if not row:
            return False
        _db().execute("DELETE FROM lists WHERE id = ?", (row[0],))
        _db().commit()
    return True


def list_clear(name="courses"):
    with _lock:
        _db().execute("DELETE FROM lists WHERE list = ?", (name,))
        _db().commit()
    return True


# -------------------------------------------- conversation persistante ------
# Contexte IA qui survit au redémarrage (JARVIS) : 100 % local, SQLite.

def conv_add(role, content):
    with _lock:
        _db().execute(
            "INSERT INTO conversation(role, content, created_at) VALUES(?,?,?)",
            (role, content[:3000], int(time.time() * 1000)))
        # purge : on ne garde que les 200 dernières lignes
        _db().execute(
            "DELETE FROM conversation WHERE id NOT IN"
            " (SELECT id FROM conversation ORDER BY id DESC LIMIT 200)")
        _db().commit()


def conv_recent(limit=30):
    """Les `limit` dernières lignes, dans l'ordre chronologique."""
    rows = _db().execute(
        "SELECT role, content FROM conversation ORDER BY id DESC LIMIT ?",
        (limit,)).fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


# ------------------------------------------ rappels à heure fixe (JARVIS) ---

def reminder_add(text, hhmm, daily=False, date=None):
    """date : 'YYYY-MM-DD' explicite (rappel futur « dans 3 jours »). Sinon
    aujourd'hui (ponctuel) ou vide (quotidien)."""
    rid = uuid.uuid4().hex[:8]
    if date is None:
        date = "" if daily else time.strftime("%Y-%m-%d")
    with _lock:
        _db().execute(
            "INSERT INTO reminders(id, text, time, date, triggered, created_at)"
            " VALUES(?,?,?,?,0,?)",
            (rid, text.strip()[:300], hhmm, date, int(time.time() * 1000)))
        _db().commit()
    return rid


def reminders_list(include_done=False):
    q = "SELECT id, text, time, date, triggered FROM reminders"
    if not include_done:
        q += " WHERE triggered = 0 OR date = ''"
    rows = _db().execute(q + " ORDER BY time ASC").fetchall()
    return [{"id": r[0], "text": r[1], "time": r[2], "date": r[3],
             "triggered": bool(r[4])} for r in rows]


def reminder_mark(rid, triggered=True):
    with _lock:
        _db().execute("UPDATE reminders SET triggered = ? WHERE id = ?",
                      (1 if triggered else 0, rid))
        _db().commit()


def reminder_delete(rid):
    with _lock:
        _db().execute("DELETE FROM reminders WHERE id = ?", (rid,))
        _db().commit()
    return True


def reminders_clear_done():
    """Purge les rappels datés déjà déclenchés (les quotidiens restent)."""
    with _lock:
        _db().execute("DELETE FROM reminders WHERE triggered = 1 AND date != ''")
        _db().commit()


def stats_summary():
    """Statistiques d'usage pour l'accueil : total, réussite, top modes, jour."""
    import datetime
    db = _db()
    total, ok = db.execute("SELECT COUNT(*), COALESCE(SUM(ok),0) FROM history").fetchone()
    top = db.execute(
        "SELECT mode, COUNT(*) FROM history GROUP BY mode"
        " ORDER BY COUNT(*) DESC LIMIT 5").fetchall()
    midnight = datetime.datetime.now().replace(hour=0, minute=0, second=0,
                                               microsecond=0)
    today = db.execute("SELECT COUNT(*) FROM history WHERE created_at >= ?",
                       (int(midnight.timestamp() * 1000),)).fetchone()[0]
    return {"total": total, "ok": ok,
            "rate": round(100 * ok / total) if total else 100,
            "today": today,
            "top": [{"mode": m, "count": c} for m, c in top]}


# ---------------------------------------------------------------- profils ---

def list_profiles():
    rows = _db().execute(
        "SELECT id, name, vocabulary, contacts, language, created_at, personal"
        " FROM profiles ORDER BY created_at ASC").fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r[0], "name": r[1],
            "vocabulary": _safe_json(r[2], []),
            "contacts": _safe_json(r[3], []),
            "language": r[4] or "fr",
            "created": r[5] or 0,
            "personal": _safe_json(r[6], {}),
        })
    return out


def save_profile(p):
    pid = p.get("id") or uuid.uuid4().hex[:8]
    contacts = [
        {"name": str(c.get("name", ""))[:60],
         "phone": str(c.get("phone", ""))[:30],
         "email": str(c.get("email", ""))[:100]}
        for c in (p.get("contacts") or []) if c.get("name")
    ]
    vocab = [str(v)[:80] for v in (p.get("vocabulary") or []) if str(v).strip()][:200]
    personal = {k: str(v)[:200] for k, v in (p.get("personal") or {}).items()
                if k in PERSONAL_FIELDS and str(v).strip()}
    with _lock:
        _db().execute(
            "INSERT INTO profiles(id, name, vocabulary, contacts, language, created_at,"
            " personal) VALUES(?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET name=excluded.name,"
            " vocabulary=excluded.vocabulary, contacts=excluded.contacts,"
            " language=excluded.language, personal=excluded.personal",
            (pid, str(p.get("name", "Profil"))[:60], json.dumps(vocab, ensure_ascii=False),
             json.dumps(contacts, ensure_ascii=False), str(p.get("language", "fr"))[:5],
             p.get("created") or int(time.time() * 1000),
             json.dumps(personal, ensure_ascii=False)))
        _db().commit()
    return pid


def delete_profile(pid):
    if len(list_profiles()) <= 1:
        return False
    with _lock:
        _db().execute("DELETE FROM profiles WHERE id=?", (pid,))
        _db().commit()
    return True


def ensure_default_profile():
    profiles = list_profiles()
    if profiles:
        return profiles[0]["id"]
    pid = save_profile({"name": "Profil 1", "language": "fr", "vocabulary": [], "contacts": []})
    return pid


def get_profile(pid):
    for p in list_profiles():
        if p["id"] == pid:
            return p
    return None


def _safe_json(s, default):
    try:
        return json.loads(s) if s else default
    except json.JSONDecodeError:
        return default
