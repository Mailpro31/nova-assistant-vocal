# -*- coding: utf-8 -*-
"""
Minuteurs et rappels vocaux : « mets un minuteur de 10 minutes »,
« rappelle-moi de sortir le gâteau dans 25 minutes ». Alerte vocale
prioritaire à l'échéance (branchée par app.py via `notify`).
"""

import re
import threading
import time
import uuid

_timers = {}
_lock = threading.Lock()
notify = None  # callback(label) — branché par app.py

_WORD_NUMBERS = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11,
    "douze": 12, "quinze": 15, "vingt": 20, "trente": 30, "quarante": 40,
    "cinquante": 50, "soixante": 60,
}

_UNITS = {
    "h": 3600, "heure": 3600, "heures": 3600,
    "min": 60, "mn": 60, "minute": 60, "minutes": 60,
    "s": 1, "sec": 1, "seconde": 1, "secondes": 1,
}


def parse_duration(text):
    """« 10 minutes », « une heure et demie », « 1 h 30 », « 45 secondes »,
    « un quart d'heure » → secondes, ou None si rien de compréhensible."""
    if not text:
        return None
    t = " " + text.lower().strip() + " "
    for w, v in _WORD_NUMBERS.items():
        t = re.sub(rf"\b{w}\b", str(v), t)
    if re.search(r"\bquart d'?heure\b", t):
        return 900
    if re.search(r"\bdemi[- ]?heure\b", t):
        return 1800
    total = 0
    # « 1 h 30 » : minutes collées après l'heure sans unité
    m = re.search(r"(\d+)\s*h(?:eures?)?\s+(\d{1,2})\b(?!\s*(?:h|min|s))", t)
    if m:
        total = int(m.group(1)) * 3600 + int(m.group(2)) * 60
        t = t[:m.start()] + t[m.end():]
    for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(h|heures?|min|mn|minutes?|s|sec|secondes?)\b", t):
        val = float(m.group(1).replace(",", "."))
        unit = m.group(2).rstrip("s") if m.group(2) not in _UNITS else m.group(2)
        total += int(val * _UNITS.get(m.group(2), _UNITS.get(unit, 60)))
    if re.search(r"\bet demie?\b", t):
        total += 1800 if "heure" in t or re.search(r"\d\s*h\b", t) else 30
    if total == 0:
        # nombre seul : on suppose des minutes (« minuteur de 10 »)
        m = re.search(r"\b(\d+)\b", t)
        if m:
            total = int(m.group(1)) * 60
    return total or None


def human(seconds):
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h} h")
    if m:
        parts.append(f"{m} min")
    if s and not h:
        parts.append(f"{s} s")
    return " ".join(parts) or "0 s"


def start(seconds, label=""):
    tid = uuid.uuid4().hex[:6]
    t = threading.Timer(seconds, _fire, [tid])
    t.daemon = True
    with _lock:
        _timers[tid] = {"id": tid, "label": label.strip(), "ends": time.time() + seconds,
                        "seconds": seconds, "timer": t}
    t.start()
    return tid


def _fire(tid):
    with _lock:
        info = _timers.pop(tid, None)
    if info and notify:
        try:
            notify(info["label"])
        except Exception:
            pass


def cancel(tid):
    with _lock:
        info = _timers.pop(tid, None)
    if info:
        info["timer"].cancel()
    return info is not None


def adjust(delta):
    """« Ajoute 5 minutes au minuteur » : réarme le minuteur le plus proche
    de l'échéance à ±delta secondes. Retourne (label, restant_s) ou None."""
    with _lock:
        items = sorted(_timers.values(), key=lambda i: i["ends"])
        if not items:
            return None
        info = items[0]
        _timers.pop(info["id"], None)
    info["timer"].cancel()
    remaining = max(5, int(info["ends"] - time.time()) + int(delta))
    start(remaining, info["label"])
    return info["label"], remaining


# ------------------------------------- rappels à heure fixe (JARVIS) --------
# « Rappelle-moi le sport à 15 h 30 » — persistés en SQLite, vérifiés toutes
# les 15 s (valeur JARVIS), les quotidiens (date vide) reviennent chaque jour.

notify_reminder = None   # callback(text) — branché par app.py
_rem_fired = {}          # id → date du dernier déclenchement (anti-doublon)


def start_reminder_loop():
    import storage

    def loop():
        while True:
            try:
                hhmm = time.strftime("%H:%M")
                today = time.strftime("%Y-%m-%d")
                for r in storage.reminders_list():
                    if r["triggered"] and r["date"]:
                        continue                    # daté déjà déclenché
                    if r["date"] and r["date"] != today:
                        continue                    # daté pour un autre jour
                    if r["time"] <= hhmm and _rem_fired.get(r["id"]) != today:
                        _rem_fired[r["id"]] = today
                        if r["date"]:
                            storage.reminder_mark(r["id"])
                        if notify_reminder:
                            try:
                                notify_reminder(r["text"])
                            except Exception:
                                pass
                storage.reminders_clear_done()
            except Exception:
                pass
            time.sleep(15)

    threading.Thread(target=loop, daemon=True).start()


def cancel_all():
    with _lock:
        items = list(_timers.values())
        _timers.clear()
    for info in items:
        info["timer"].cancel()
    return len(items)


def list_active():
    now = time.time()
    with _lock:
        return sorted(
            ({"id": i["id"], "label": i["label"], "remaining": max(0, int(i["ends"] - now)),
              "seconds": i["seconds"]} for i in _timers.values()),
            key=lambda x: x["remaining"])
