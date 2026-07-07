# -*- coding: utf-8 -*-
"""
Nova — assistant vocal Windows.
Fenêtre bleu nuit type macOS (pywebview), pilule flottante (design 5 états),
mot d'éveil « Nova » (Whisper local ou Porcupine), modes intelligents
(message, navigation, média, appel, mémo, urgence), notes, automatisations,
multi-IA, Twilio, Microsoft Graph, OBD-II — le tout offline-first.
"""

import collections
import ctypes
import os
import queue
import re
import sys
import threading
import time
import winsound

import keyboard
import numpy as np
import webview

import core
import integrations
import modes
import obd as obdmod
import storage
import timers
import winext

APP_NAME = "Nova"
_busy = threading.Lock()
window = None

# ------------------------------------------------------ instance unique -----
_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "NovaAssistantVocalMutex")
if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    sys.exit(0)


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


# ------------------------------------------------------------ TTS -----------

TTS_END = {"t": 0.0}       # fin estimée de la synthèse (repli si l'état réel manque)
EDGE_BUSY = {"on": False}  # génération/lancement de la voix neuronale en cours
_EDGE_TMP = {"path": ""}   # dernier MP3 temporaire (supprimé au suivant)

# mots d'interruption : coupent la voix de Nova instantanément (JARVIS)
INTERRUPT_RE = re.compile(r"\b(?:tais[- ]toi|silence|chut|stop|arr[eê]te)\b")

SESSION = {"until": 0.0, "chain": 0}   # fenêtre de conversation sans « Nova »
# chain = nombre d'enchaînements consécutifs sans mot d'éveil (plafonné : la
# voix d'une TV ne peut pas entretenir la conversation à l'infini)
MIC_MUTED = {"on": False}  # coupure rapide du micro (tray / réglages)


def _tts_clean(text):
    """Le texte PARLÉ ne contient ni Markdown ni URL (la pilule garde
    le texte original)."""
    t = re.sub(r"[*_#`]+", "", text)
    t = re.sub(r"https?://\S+", "le lien", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def tts_active():
    """Nova est-elle en train de parler ? État RÉEL (SAPI sondé + lecteur MP3),
    l'estimation temporelle ne sert plus que de repli."""
    return (EDGE_BUSY["on"] or winext.tts_bridge.speaking
            or winext.mp3_playing() or time.time() < TTS_END["t"])


def stop_tts():
    """« Stop », « tais-toi », clic sur la pilule : coupe la voix immédiatement."""
    try:
        winext.tts_bridge.stop()
        winext.stop_mp3()
    except Exception:
        pass
    TTS_END["t"] = 0.0


def _say_sapi(spoken, t, priority=False):
    winext.tts_bridge.speak(spoken, rate=t.get("rate", 1),
                            volume=100 if priority else t.get("volume", 100),
                            voice=t.get("voice", ""))
    # repli estimé, corrigé par la vitesse configurée (rate SAPI -10..10)
    cps = max(8.0, 13.0 * (1 + 0.08 * float(t.get("rate", 1) or 0)))
    TTS_END["t"] = time.time() + 0.4 + len(spoken) / cps


def _say_edge(spoken, t):
    """Voix neuronale Microsoft Edge (opt-in, en ligne, aucune clé requise).
    Toute erreur retombe immédiatement sur la voix SAPI locale."""
    EDGE_BUSY["on"] = True
    try:
        import asyncio
        import edge_tts
        path = os.path.join(os.environ.get("TEMP", core.APP_DIR),
                            f"nova_tts_{int(time.time() * 1000)}.mp3")
        asyncio.run(edge_tts.Communicate(
            spoken, t.get("edge_voice") or "fr-FR-DeniseNeural").save(path))
        old = _EDGE_TMP.get("path")
        _EDGE_TMP["path"] = path
        if not winext.play_mp3(path, t.get("volume", 100)):
            raise RuntimeError("lecture MP3 impossible")
        TTS_END["t"] = time.time() + 0.4 + len(spoken) / 14.0
        if old and old != path:
            try:
                os.remove(old)
            except OSError:
                pass
    except Exception as e:
        core.log_err("edge_tts", e)
        _say_sapi(spoken, t)
    finally:
        EDGE_BUSY["on"] = False


def say(text, priority=False):
    """Confirmation vocale. priority=True (urgence, alertes OBD) parle même si
    le TTS est désactivé et interrompt la lecture en cours."""
    t = core.CFG.get("tts", {})
    if not text or (not t.get("enabled") and not priority):
        return
    spoken = _tts_clean(text)
    if not spoken:
        return
    # urgences : toujours la voix SAPI locale (zéro dépendance réseau)
    if not priority and t.get("engine") == "edge" and integrations.is_online():
        threading.Thread(target=_say_edge, args=(spoken, t), daemon=True).start()
        return
    _say_sapi(spoken, t, priority)


# ------------------------------------------------------------ pilule --------
# Design « Pilule — États » : 560x64, rayon 32, fond #1A1B20, 5 états
# (repos / écoute+transcription live / réflexion / succès / erreur)
# + bulle micro compacte pendant l'écoute continue.

BLUE, GREEN, ORANGE = "#0A84FF", "#30D158", "#FF6950"


class Pill(threading.Thread):
    W, H, R = 560, 64, 31
    BG = "#1A1B20"
    TRANSPARENT = "#010203"
    N_BARS = 14

    BORDERS = {"repos": "#3A3D46", "listening": "#2B517E", "thinking": "#3A3D46",
               "ok": "#2C6743", "error": "#7A4438"}

    def __init__(self):
        super().__init__(daemon=True)
        self.q = queue.Queue()
        self.levels = collections.deque([0.0] * self.N_BARS, maxlen=self.N_BARS)
        self._visible = False
        self._state = "repos"
        self._spin = 0.0
        self._alpha = 0.0          # fondu doux à l'apparition/disparition
        self._alpha_target = 0.0

    # ---- API (thread-safe) ----
    def show(self, state, text="", sub=""):
        self.q.put(("show", state, text, sub))

    def set_text(self, text):
        self.q.put(("text", text))

    def hide(self, delay=0.0):
        self.q.put(("hide", delay))

    def level(self, rms):
        self.levels.append(min(1.0, rms * 14))

    def refresh_bubble(self):
        self.q.put(("bubble",))

    # ---- interne (thread tk) ----
    def run(self):
        import tkinter as tk
        import tkinter.font as tkfont
        self.tk = tk
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.0)
        self.root.attributes("-transparentcolor", self.TRANSPARENT)
        self.root.configure(bg=self.TRANSPARENT)
        self.canvas = tk.Canvas(self.root, width=self.W, height=self.H,
                                bg=self.TRANSPARENT, highlightthickness=0)
        self.canvas.pack()
        self.font = tkfont.Font(family="Segoe UI", size=12)
        self.font_small = tkfont.Font(family="Segoe UI", size=9)
        self.font_badge = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        self._logo_img = self._make_logo(38, 11)
        self._hide_job = None
        self._text = ""
        self._sub = ""
        self._build_bubble()
        self._make_draggable(self.canvas, self.root, "pill_pos",
                             on_click=self._pill_clicked)
        self._btn_was_down = False
        self.root.after(50, self._tick)
        self.root.mainloop()

    # ---- fermeture au clic (pilule ou ailleurs sur l'écran) ----
    def _dismiss(self):
        SESSION["until"] = 0.0
        if self._state == "listening" and not DICTATION["on"]:
            LISTEN_CANCEL.set()
            WAKE_SKIP["t"] = time.time()
        if self._hide_job:
            self.root.after_cancel(self._hide_job)
            self._hide_job = None
        self._alpha = 0.0
        self._alpha_target = 0.0
        try:
            self.root.attributes("-alpha", 0.0)
        except Exception:
            pass
        self.root.withdraw()
        self._visible = False
        self._update_bubble_visibility()

    def _pill_clicked(self, e=None):
        """Clic (sans glisser) sur la pilule : on la range (et on coupe la
        voix si Nova parle). Sur le chip « Réessayer » (état erreur) : on
        relance la dernière commande."""
        if tts_active():
            stop_tts()
        if self._state == "thinking":
            return          # une action est en cours, le résultat arrive
        if self._state == "listening" and DICTATION["on"]:
            return          # en dictée, on clique où on veut sans l'arrêter
        if (self._state == "error" and e is not None
                and getattr(self, "_retry_box", None) and LAST_CMD["text"]):
            x1, y1, x2, y2 = self._retry_box
            if x1 <= e.x <= x2 and y1 <= e.y <= y2:
                self._dismiss()
                retry_last()
                return
        self._dismiss()

    def _click_check(self):
        """Clic n'importe où ailleurs sur l'écran : ferme la pilule
        (réglable : Réglages > Système > Disparition de la pilule)."""
        down = bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
        pressed = down and not self._btn_was_down
        self._btn_was_down = down
        if not pressed or not self._visible:
            return
        if core.CFG.get("pill_hide_mode", "timer") == "never":
            return
        if self._state == "thinking" or (self._state == "listening" and DICTATION["on"]):
            return
        pt = _POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        wx, wy = self.root.winfo_x(), self.root.winfo_y()
        if wx <= pt.x <= wx + self.W and wy <= pt.y <= wy + self.H:
            return          # clic sur la pilule : géré par _pill_clicked
        self._dismiss()

    def _make_draggable(self, widget, win, cfg_key, on_click=None):
        """Déplacement à la souris de la fenêtre flottante ; la position est
        mémorisée. Un clic sans mouvement déclenche on_click (bulle micro)."""
        st = {"x": 0, "y": 0, "ox": 0, "oy": 0, "moved": False}

        def press(e):
            st.update(x=e.x_root, y=e.y_root, ox=win.winfo_x(), oy=win.winfo_y(),
                      moved=False)

        def motion(e):
            dx, dy = e.x_root - st["x"], e.y_root - st["y"]
            if abs(dx) + abs(dy) > 4:
                st["moved"] = True
            if st["moved"]:
                win.geometry(f"+{st['ox'] + dx}+{st['oy'] + dy}")

        def release(e):
            if st["moved"]:
                core.save_config({cfg_key: [win.winfo_x(), win.winfo_y()]})
            elif on_click:
                on_click(e)

        widget.bind("<Button-1>", press)
        widget.bind("<B1-Motion>", motion)
        widget.bind("<ButtonRelease-1>", release)
        widget.configure(cursor="fleur")

    @staticmethod
    def _saved_pos(cfg_key, w, h, sw, sh):
        pos = core.CFG.get(cfg_key)
        if (isinstance(pos, (list, tuple)) and len(pos) == 2
                and -w + 60 < pos[0] < sw - 60 and 0 <= pos[1] < sh - 24):
            return int(pos[0]), int(pos[1])
        return None

    def _make_logo(self, size, radius):
        from PIL import Image, ImageDraw, ImageTk
        s = size * 4
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        top, bot = (0x3F, 0xA9, 0xFF), (0x0A, 0x63, 0xE8)
        grad = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        gd = ImageDraw.Draw(grad)
        for y in range(s):
            f = y / s
            gd.line([(0, y), (s, y)], fill=tuple(
                int(top[i] + (bot[i] - top[i]) * f) for i in range(3)) + (255,))
        mask = Image.new("L", (s, s), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=radius * 4, fill=255)
        img.paste(grad, (0, 0), mask)
        for (x, y, w, h) in ((22, 38, 12, 24), (44, 26, 12, 48), (66, 38, 12, 24)):
            k = s / 100
            d.rounded_rectangle([x * k, y * k, (x + w) * k, (y + h) * k],
                                radius=6 * k, fill=(255, 255, 255, 255))
        img = img.resize((size, size), Image.LANCZOS)
        return ImageTk.PhotoImage(img)

    def _rounded(self, c, x1, y1, x2, y2, r, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
               x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return c.create_polygon(pts, smooth=True, **kw)

    # ---- bulle micro compacte ----
    def _build_bubble(self):
        tk = self.tk
        self.bub = tk.Toplevel(self.root)
        self.bub.withdraw()
        self.bub.overrideredirect(True)
        self.bub.attributes("-topmost", True)
        self.bub.attributes("-transparentcolor", self.TRANSPARENT)
        self.bub.configure(bg=self.TRANSPARENT)
        self.bub_canvas = tk.Canvas(self.bub, width=128, height=44,
                                    bg=self.TRANSPARENT, highlightthickness=0)
        self.bub_canvas.pack()
        self.bub_border = self._rounded(self.bub_canvas, 1, 1, 127, 43, 21,
                                        fill="#1A1B20", outline="#3A3D46")
        # point d'état : vert pulsant = « parle quand tu veux », orange = occupé
        self.bub_dot = self.bub_canvas.create_oval(14, 18, 22, 26,
                                                   fill="#22C55E", outline="")
        self.bub_bars = []
        for i in range(9):
            x = 33 + i * 8
            self.bub_bars.append(self.bub_canvas.create_rectangle(
                x, 20, x + 3, 24, fill=BLUE, outline=""))
        self._make_draggable(self.bub_canvas, self.bub, "bubble_pos",
                             on_click=lambda _e: trigger("command"))
        self._bubble_wanted = False

    def _update_bubble_visibility(self):
        want = (core.CFG.get("continuous_listening") and core.CFG.get("show_bubble")
                and not self._visible)
        if want and not self._bubble_wanted:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            pos = self._saved_pos("bubble_pos", 128, 44, sw, sh)
            x, y = pos if pos else ((sw - 128) // 2, sh - 104)
            self.bub.geometry(f"128x44+{x}+{y}")
            self.bub.deiconify()
        elif not want and self._bubble_wanted:
            self.bub.withdraw()
        self._bubble_wanted = want

    # ---- dessin de la pilule ----
    def _redraw(self):
        c = self.canvas
        c.delete("all")
        st = self._state
        self._pill_border = self._rounded(
            c, 2, 2, self.W - 2, self.H - 2, self.R,
            fill=self.BG, outline=self.BORDERS.get(st, "#3A3D46"), width=1)
        cy = self.H // 2

        if st == "repos":
            c.create_image(33, cy, image=self._logo_img)
            c.create_text(62, cy, anchor="w", fill="#6E7280", font=self.font,
                          text=self._text or "Je t'écoute…")
            hk = (core.CFG.get("hotkey") or "").replace("ctrl", "Ctrl").replace(
                "alt", "Alt").replace("space", "Espace").replace("+", " + ")
            if hk:
                tw = self.font_badge.measure(hk)
                x2 = self.W - 20
                self._rounded(c, x2 - tw - 16, cy - 11, x2, cy + 11, 6,
                              fill="#26272E", outline="#3A3D46")
                c.create_text(x2 - 8 - tw / 2, cy, fill="#9AA0AE",
                              font=self.font_badge, text=hk)

        elif st == "listening":
            self.bar_items = []
            for i in range(self.N_BARS):
                x = 16 + i * 5.4
                self.bar_items.append(c.create_rectangle(
                    x, cy - 3, x + 3, cy + 3, fill=BLUE, outline=""))
            self.txt_item = c.create_text(
                104, cy, anchor="w",
                fill="#6E7280" if not self._text else "#ECEFF7", font=self.font,
                text=self._text or self._sub or "Je t'écoute — vas-y, parle")
            self.caret_item = c.create_rectangle(0, 0, 0, 0, fill=BLUE, outline="")

        elif st == "thinking":
            c.create_oval(14, cy - 19, 52, cy + 19, fill="#1E2A3C", outline="")
            self.arc_item = c.create_arc(22, cy - 11, 44, cy + 11, start=0, extent=100,
                                         style="arc", outline=BLUE, width=2)
            self.txt_item = c.create_text(66, cy, anchor="w", fill="#C9CEDC",
                                          font=self.font,
                                          text=self._text or "Nova réfléchit…",
                                          width=self.W - 90)

        elif st == "ok":
            c.create_oval(14, cy - 19, 52, cy + 19, fill="#1E3A2A", outline="")
            c.create_line(26, cy, 31, cy + 5, fill=GREEN, width=3, capstyle="round")
            c.create_line(31, cy + 5, 41, cy - 6, fill=GREEN, width=3, capstyle="round")
            c.create_text(66, cy, anchor="w", fill="#ECEFF7", font=self.font,
                          text=self._text, width=self.W - 160)
            c.create_text(self.W - 22, cy, anchor="e", fill=GREEN,
                          font=self.font_badge, text="Exécuté")

        elif st == "error":
            c.create_oval(14, cy - 19, 52, cy + 19, fill="#3A2620", outline="")
            c.create_line(33, cy - 8, 33, cy + 2, fill=ORANGE, width=3, capstyle="round")
            c.create_oval(31.5, cy + 6, 34.5, cy + 9, fill=ORANGE, outline="")
            # chip « Réessayer » : relance la dernière commande d'un clic
            self._retry_box = None
            tx_w = self.W - 90
            if LAST_CMD["text"]:
                lbl = "Réessayer"
                tw = self.font_badge.measure(lbl)
                bx2 = self.W - 16
                self._retry_box = (bx2 - tw - 22, cy - 12, bx2, cy + 12)
                self._rounded(c, *self._retry_box, 8, fill="#2A3B55",
                              outline="#3F5E8F")
                c.create_text(bx2 - 11 - tw / 2, cy, fill="#9FC1F5",
                              font=self.font_badge, text=lbl)
                tx_w = self._retry_box[0] - 74
            if self._sub:
                c.create_text(66, cy - 9, anchor="w", fill="#ECEFF7", font=self.font,
                              text=self._text, width=tx_w)
                c.create_text(66, cy + 11, anchor="w", fill="#8A8F9C",
                              font=self.font_small, text=self._sub, width=tx_w)
            else:
                c.create_text(66, cy, anchor="w", fill="#ECEFF7", font=self.font,
                              text=self._text, width=tx_w)

    def _place(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        pos = self._saved_pos("pill_pos", self.W, self.H, sw, sh)
        x, y = pos if pos else ((sw - self.W) // 2, int(sh * 0.30))
        self.root.geometry(f"{self.W}x{self.H}+{x}+{y}")

    def _tick(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "show":
                    _, state, text, sub = msg
                    self._state, self._text, self._sub = state, text, sub
                    if self._hide_job:
                        self.root.after_cancel(self._hide_job)
                        self._hide_job = None
                    self._redraw()
                    self._place()
                    self.root.deiconify()
                    self._visible = True
                    self._alpha_target = 1.0
                elif msg[0] == "text":
                    if self._state == "listening":
                        # on montre la FIN de la phrase (ce qui vient d'être dit),
                        # sur une seule ligne, comme une vraie transcription live
                        t = msg[1]
                        maxw = self.W - 134
                        if self.font.measure(t) > maxw:
                            while t and self.font.measure("…" + t) > maxw:
                                t = t[1:]
                            t = "…" + t
                        self._text = t
                        if hasattr(self, "txt_item"):
                            self.canvas.itemconfig(
                                self.txt_item,
                                text=t or self._sub or "Je t'écoute — vas-y, parle",
                                fill="#ECEFF7" if t else "#6E7280")
                    else:
                        self._text = msg[1]
                        if self._state == "thinking" and hasattr(self, "txt_item"):
                            self.canvas.itemconfig(self.txt_item, text=msg[1])
                elif msg[0] == "hide":
                    delay = msg[1]
                    if self._hide_job:
                        self.root.after_cancel(self._hide_job)
                        self._hide_job = None
                    # mode « au clic » / « jamais » : les disparitions
                    # automatiques différées sont ignorées, la pilule reste
                    if (core.CFG.get("pill_hide_mode", "timer") != "timer"
                            and delay > 0.3 and self._state in ("ok", "error")):
                        continue

                    def do_hide():
                        # fondu de sortie (~180 ms) avant de se ranger
                        self._alpha_target = 0.0
                        self._visible = False
                        self._update_bubble_visibility()
                        self.root.after(220, lambda: None if self._visible
                                        else self.root.withdraw())
                    self._hide_job = self.root.after(int(delay * 1000), do_hide)
                elif msg[0] == "bubble":
                    # force le repositionnement (ex. reset de position)
                    if self._bubble_wanted:
                        self.bub.withdraw()
                        self._bubble_wanted = False
        except queue.Empty:
            pass

        if self._visible and self._state == "listening" and hasattr(self, "bar_items"):
            # bordure pulsante bleue : le signe clair que Nova capte ta voix
            f = (np.sin(time.time() * 3.2) + 1) / 2
            col = "#%02X%02X%02X" % tuple(
                int(a + (b - a) * f) for a, b in
                ((0x2B, 0x3F), (0x51, 0xA9), (0x7E, 0xFF)))
            self.canvas.itemconfig(self._pill_border, outline=col)
            cy = self.H // 2
            lv = list(self.levels)
            for i, bid in enumerate(self.bar_items):
                amp = 3 + lv[i] * 19
                x = 16 + i * 5.4
                self.canvas.coords(bid, x, cy - amp, x + 3, cy + amp)
            # caret clignotant après le texte (masqué tant que rien n'est dit)
            if hasattr(self, "caret_item"):
                if self._text and int(time.time() * 2) % 2 == 0:
                    w = self.font.measure(self._text)
                    x = min(104 + w + 4, self.W - 26)
                    self.canvas.coords(self.caret_item, x, cy - 8, x + 2, cy + 8)
                else:
                    self.canvas.coords(self.caret_item, 0, 0, 0, 0)

        if self._visible and self._state == "thinking" and hasattr(self, "arc_item"):
            self._spin = (self._spin - 24) % 360
            self.canvas.itemconfig(self.arc_item, start=self._spin)

        if self._bubble_wanted:
            live = WAKE_LIVE["on"]
            lv = list(self.levels)[-9:]
            t = time.time()
            for i, bid in enumerate(self.bub_bars):
                if live:
                    # les barres suivent la VRAIE voix : si elles bougent
                    # quand tu parles, c'est que Nova t'entend
                    amp = 2.5 + lv[i] * 14
                else:
                    amp = 2.5 + 1.6 * abs(np.sin(t * 1.1 + i * 0.7))
                x = 33 + i * 8
                self.bub_canvas.coords(bid, x, 22 - amp, x + 3, 22 + amp)
                self.bub_canvas.itemconfig(bid, fill=BLUE if live else "#4A4E5A")
            if live:
                r = 3.0 + 1.4 * abs(np.sin(t * 2.6))
                self.bub_canvas.itemconfig(self.bub_dot, fill="#22C55E")
                self.bub_canvas.itemconfig(self.bub_border, outline="#2C6743")
            else:
                r = 3.5
                self.bub_canvas.itemconfig(self.bub_dot, fill="#E8A33D")
                self.bub_canvas.itemconfig(self.bub_border, outline="#3A3D46")
            self.bub_canvas.coords(self.bub_dot, 18 - r, 22 - r, 18 + r, 22 + r)

        # fondu doux (~150 ms) : la pilule glisse au lieu de sauter
        if abs(self._alpha - self._alpha_target) > 0.01:
            step = 0.34 if self._alpha_target > self._alpha else -0.34
            self._alpha = max(0.0, min(1.0, self._alpha + step))
            try:
                self.root.attributes("-alpha", self._alpha)
            except Exception:
                pass

        self._click_check()
        self._update_bubble_visibility()
        self.root.after(50, self._tick)


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


pill = Pill()


# --------------------------------------------------------------- flux vocal -

PLACEHOLDERS = {
    "command": "Je t'écoute…",
    "note": "Dicte ta note…",
}


def _history(mode, text, reply, engine, ok, final=""):
    storage.add_history(mode, text, final or reply, reply, engine, ok,
                        core.CFG.get("active_profile", ""))


def _erase_typed(done):
    """Efface le texte tapé en direct si la dictée est finalement abandonnée."""
    for _ in range(len(done)):
        try:
            keyboard.send("backspace")
        except Exception:
            break


def _sync_typed(done, final):
    """Remplace le texte tapé en direct par la transcription finale précise,
    en ne réécrivant que la partie qui diffère."""
    n = 0
    while n < min(len(done), len(final)) and done[n] == final[n]:
        n += 1
    for _ in range(len(done) - n):
        keyboard.send("backspace")
    if final[n:]:
        keyboard.write(final[n:], delay=0.003)


def _capture_utterance(live_typing, typed, cancel=None, end_silence=None,
                       min_voiced=0.0):
    """Enregistre une phrase : aperçu live dans la pilule toutes les ~0,5 s,
    frappe en direct au curseur si live_typing. Retourne l'audio (ou None)."""
    frames = []
    frames_lock = threading.Lock()
    recording = threading.Event()
    recording.set()

    def partials():
        last_len = 0
        prev = ""
        while recording.is_set():
            time.sleep(0.5)
            with frames_lock:
                if len(frames) == last_len or not frames:
                    continue
                last_len = len(frames)
                snap = np.concatenate(frames).flatten()
            if len(snap) < 6400:
                continue
            try:
                text = core.transcribe_quick(snap)
            except Exception:
                continue
            if not text or not recording.is_set():
                continue
            pill.set_text(text)
            if live_typing:
                # préfixe identique entre deux aperçus successifs = stable ;
                # on s'arrête au dernier espace pour ne jamais couper un mot
                n = 0
                while n < min(len(prev), len(text)) and prev[n] == text[n]:
                    n += 1
                stable = text[:n]
                cut = stable.rfind(" ")
                stable = stable[:cut + 1] if cut >= 0 else ""
                done = typed["text"]
                if stable.startswith(done) and len(stable) > len(done):
                    try:
                        keyboard.write(stable[len(done):], delay=0.002)
                        typed["text"] = stable
                    except Exception:
                        pass
            prev = text

    threading.Thread(target=partials, daemon=True).start()
    audio = core.record_audio(on_level=pill.level,
                              frames_out=frames, frames_lock=frames_lock,
                              cancel=cancel, end_silence=end_silence,
                              min_voiced=min_voiced)
    recording.clear()
    return audio


def listen_flow(mode="command", hint="", retry=False, follow=False):
    # micro coupé : aucune capture ni exécution (couvre trigger, relisten,
    # follow_listen, le raccourci clavier et le menu tray « Écouter »)
    if MIC_MUTED["on"]:
        return
    if not _busy.acquire(blocking=False):
        return
    try:
        LISTEN_CANCEL.clear()
        pill.show("listening", "", hint)
        pill.set_text("")

        # une commande n'est pas une dictée : fin de silence courte = réactivité
        # + filtre anti-bruit JARVIS (0,35 s de voix mini, jamais en note/dictée)
        try:
            audio = _capture_utterance(
                False, {"text": ""}, cancel=LISTEN_CANCEL,
                end_silence=min(0.8, float(core.CFG.get("silence_seconds", 1.2))),
                min_voiced=0.35 if mode != "note" else 0.0)
        except Exception as e:
            core.log_err("listen_flow", e)
            pill.show("error", "Micro indisponible",
                      "Vérifiez le branchement, ou le micro choisi (Réglages > Écoute)")
            pill.hide(3.0)
            return
        if LISTEN_CANCEL.is_set():
            pill.hide(0.1)            # annulé d'un clic : on se range sans bruit
            return
        if audio is None:
            if follow:
                pill.hide(0.2)        # conversation finie : silence = on se range
                return
            pill.show("error", "Je n'ai rien entendu", "Réessayez, ou vérifiez le micro")
            pill.hide(1.8)
            if not retry:
                relisten("Vas-y, parle — je t'écoute")
            return

        pill.show("thinking", "")
        # les notes méritent le modèle précis ; les commandes, la vitesse
        text, engine = core.transcribe_routed(audio, fast=(mode != "note"))
        if not text:
            pill.show("error", "Je n'ai pas compris", "Réessayez en articulant un peu plus")
            pill.hide(1.8)
            if not retry:
                relisten("Reformule — pas besoin de redire « Nova »")
            return
        pill.set_text(f"« {text} »")

        # comptage des enchaînements : une écoute déclenchée au mot d'éveil ou
        # au clic (follow=False) repart à zéro ; une réécoute automatique
        # (follow=True) incrémente — c'est ça que le plafond de 2 borne
        if follow:
            SESSION["chain"] = SESSION.get("chain", 0) + 1
        else:
            SESSION["chain"] = 0

        if mode == "note":
            core.add_note(text)
            pill.show("ok", "Note enregistrée")
            _history("note", text, "Note enregistrée", engine, True, text)
            say("Note enregistrée")
            pill.hide(2.0)
            return

        run_command(text, engine)
    finally:
        if _busy.locked():
            _busy.release()


# ------------------------------------------------------- dictée continue ----

LISTEN_CANCEL = threading.Event()   # clic ailleurs pendant l'écoute = annuler
WAKE_SKIP = {"t": 0.0}              # clic pendant l'éveil partiel = ignorer la phrase

DICTATION = {"on": False}
DICTATION_STOPS = ("fin de la dictee", "fin de dictee", "stop dictee",
                   "arrete la dictee", "termine la dictee", "stop la dictee")
DICTATION_STARTS = ("demarre la dictee", "lance la dictee", "mode dictee",
                    "dictee continue", "active la dictee", "prise de texte")


def toggle_dictation():
    """Démarre/arrête la dictée continue : tout ce qui est dit est tapé au
    curseur, phrase après phrase, jusqu'au raccourci ou « fin de la dictée »."""
    if DICTATION["on"]:
        DICTATION["on"] = False
        return
    threading.Thread(target=_dictation_session, daemon=True).start()


def _dictation_session():
    # jusqu'à 2,5 s de patience : « Nova, mode dictée » confirme puis démarre
    # 0,7 s plus tard — une écoute concurrente ne doit pas l'avaler
    if not _busy.acquire(timeout=2.5):
        return
    DICTATION["on"] = True
    live = core.CFG.get("dictation_live", True)
    last_speech = time.time()
    try:
        while DICTATION["on"]:
            pill.show("listening", "", "Dictée : parle, j'écris. « Fin de la dictée » pour arrêter")
            pill.set_text("")
            typed = {"text": ""}
            audio = _capture_utterance(live, typed)
            if not DICTATION["on"]:
                _erase_typed(typed["text"])
                break
            if audio is None:
                if time.time() - last_speech > 45:   # personne ne parle : on range
                    break
                continue
            last_speech = time.time()
            text, engine = core.transcribe_routed(audio)
            if not text:
                _erase_typed(typed["text"])
                continue
            n = core.normalize(text).strip(" .!?,")
            if any(n == s or n.endswith(" " + s) for s in DICTATION_STOPS):
                _erase_typed(typed["text"])
                break
            if core.CFG.get("dictation_punctuation", True):
                text = core.voice_punctuation(text)
            text = core.fill_personal(text)
            _sync_typed(typed["text"], text + " ")
            _history("dictée", text, "Dictée continue", engine, True, text)
    finally:
        DICTATION["on"] = False
        pill.show("ok", "Dictée terminée")
        pill.hide(1.4)
        if _busy.locked():
            _busy.release()


LLM_CTX = collections.deque(maxlen=30)  # 15 derniers échanges user/assistant (JARVIS)
try:
    # contexte persistant : la conversation survit au redémarrage (SQLite local)
    LLM_CTX.extend(storage.conv_recent(30))
except Exception:
    pass

# slots multi-tours (JARVIS) : « ouvre » tout seul → « J'ouvre quoi ? »
PENDING_SLOT = {"kind": None, "t": 0.0}
_SLOT_APP = {"ouvre", "lance", "ouvre l'application", "lance l'application",
             "ouvre le logiciel", "lance le logiciel", "ouvre une application"}
_SLOT_FOLDER = {"ouvre le dossier", "ouvre un dossier", "ouvre mon dossier"}


def run_command(text, engine, allow_split=True):
    """Pipeline complet : urgence → note → automatisations → modes → recherche → IA."""
    text = core.clean_speech(text)
    if allow_split:
        LAST_CMD.update(text=text, engine=engine)
    classified = None
    try:
        classified = modes.classify(text)
    except Exception:
        pass

    # mise en veille (« merci », « c'est tout », « au revoir »…) : on se range
    # sans bruit — pas de TTS, pas de réécoute, fin de la session
    if classified and classified[0] == "dismiss":
        SESSION["until"] = 0.0
        PENDING_SLOT["kind"] = None
        if tts_active():
            stop_tts()
        pill.hide(0.2)
        return

    # slots multi-tours (JARVIS) : un slot est ouvert → cette phrase est la
    # réponse (« chrome ») qu'on recolle à la commande incomplète
    if PENDING_SLOT["kind"] and time.time() - PENDING_SLOT["t"] < 25:
        kind = PENDING_SLOT["kind"]
        PENDING_SLOT["kind"] = None
        if classified is None and len(text.split()) <= 4:
            prefix = "ouvre le dossier " if kind == "folder" else "ouvre "
            run_command(prefix + text.strip(" .!?,"), engine, allow_split=False)
            return
    n0 = core.strip_politeness(core.normalize(text).strip(" .!?,"))
    if n0 in _SLOT_APP:
        PENDING_SLOT.update(kind="app", t=time.time())
        _finish("slot", text, "J'ouvre quoi ?", engine + "+règle", True)
        return
    if n0 in _SLOT_FOLDER:
        PENDING_SLOT.update(kind="folder", t=time.time())
        _finish("slot", text, "Quel dossier ?", engine + "+règle", True)
        return

    # plusieurs demandes dans la même phrase (« ouvre X et mets Y ») :
    # chaque morceau repasse dans le pipeline, dans l'ordre
    if allow_split and (not classified or classified[0] != "emergency"):
        parts = core.split_multi(text)
        if parts:
            for i, part in enumerate(parts):
                run_command(part, engine, allow_split=False)
                if i < len(parts) - 1:
                    time.sleep(0.5)   # laisse la pilule montrer chaque étape
            return

    # 1) urgence — priorité absolue
    if classified and classified[0] == "emergency":
        res = modes.handle("emergency", classified[1], classified[2], text)
        _finish("urgence", text, res["reply"], engine + "+règle", res["ok"], res["final"],
                priority_tts=True)
        return

    # 2) notes (déclencheurs historiques de Nova)
    n = core.normalize(text).strip(" .!?")

    # dictée continue à la voix (« Nova, mode dictée »)
    if any(n == s or n.startswith(s) for s in DICTATION_STARTS):
        _finish("dictée", text, "Dictée : je tape ce que tu dis. « Fin de la dictée » pour arrêter",
                engine + "+règle", True)
        threading.Timer(0.7, toggle_dictation).start()
        return
    for trig in core.NOTE_TRIGGERS:
        if n.startswith(core.normalize(trig)):
            content = text.strip()[len(trig):].strip(" ,.:") or text
            core.add_note(content)
            _finish("note", text, "Note enregistrée", engine + "+règle", True, content)
            return

    # 3) automatisations de l'utilisateur (priorité sur les modes génériques,
    # mais UNIQUEMENT si la phrase couvre toute la demande : « ouvre les
    # paramètres de l'écran » ne déclenche pas « ouvre les paramètres »)
    for auto in core.get_automations():
        if auto.get("enabled", True) is False:
            continue
        for phrase in auto.get("phrases", []):
            if core.matches_phrase(core.normalize(phrase), n):
                act = dict(auto["action"])
                ok = _safe_execute({"action": act.get("type"), "target": act.get("target"),
                                    "args": act.get("args", ""), "text": text})
                reply = auto.get("reply") or auto["name"]
                _finish("automatisation", text, reply if ok else "L'automatisation a échoué",
                        engine + "+règle", ok, reply)
                return

    # 4pré) webcam : photo + IA vision (« regarde-moi », « webcam »)
    if classified and classified[0] == "camera":
        if not core.CFG.get("screen_vision", True):
            _finish("camera", text, "Active la Vision de l'écran "
                    "(Réglages > Système) pour la webcam", engine, False)
            return
        pill.show("thinking", "Je regarde par la webcam…")
        img = None
        try:
            img = winext.camera_b64()
        except Exception as e:
            core.log_err("camera", e)
        if not img:
            _finish("camera", text, "Pas de webcam disponible sur ce PC",
                    engine, False)
            return
        try:
            result = core.ask_llm(text, context=list(LLM_CTX), image=img)
        except Exception as e:
            pill.show("error", "Vision impossible", str(e)[:90])
            _history("camera", text, f"Erreur : {e}", engine, False)
            pill.hide(3.6)
            return
        if result:
            _handle_llm(result, text, engine + "+webcam")
        return

    # 4pré-bis) écrire dans un champ par VISION : localiser, cliquer, coller
    if classified and classified[0] == "visionwrite":
        if not core.CFG.get("screen_vision", True):
            _finish("vision", text, "Active la Vision de l'écran "
                    "(Réglages > Système)", engine, False)
            return
        champ, texte = classified[1], classified[2]
        pill.show("thinking", f"Je cherche {champ}…")
        try:
            img = winext.screenshot_b64()
            w, h = winext.screen_size()
            spot = core.ask_vision_box("le champ de saisie : " + champ, img, w, h)
        except Exception as e:
            core.log_err("visionwrite", e)
            spot = None
        if not spot:
            _finish("vision", text, f"Je ne trouve pas {champ} à l'écran",
                    engine + "+vision", False)
            return
        winext.click_at(spot[0], spot[1])
        time.sleep(0.3)
        keyboard.send("ctrl+a")
        time.sleep(0.1)
        winext.set_clipboard(core.fill_personal(texte))
        keyboard.send("ctrl+v")
        time.sleep(0.1)
        keyboard.send("enter")
        _finish("vision", text, f"« {texte} » écrit dans {champ}",
                engine + "+vision", True)
        return

    # 4) modes intelligents (message / navigation / média / appel / profil)
    if classified:
        mode, target, body = classified
        try:
            res = modes.handle(mode, target, body, text)
        except Exception as e:
            res = {"ok": False, "reply": f"Erreur : {e}", "final": text, "detail": str(e)}
        # rattrapage IA (JARVIS) : la règle a échoué proprement → l'agent tente
        if (not res.get("ok") and core.CFG.get("ia_fallback_on_fail", True)
                and mode not in ("emergency", "home", "power", "close")
                and core.resolve_provider() != "off"):
            try:
                result = core.ask_llm(text, context=list(LLM_CTX))
            except Exception:
                result = None
            if result and (result.get("steps") or result.get("reply")):
                _handle_llm(result, text, engine + "+ia-secours")
                return
        if mode == "help":
            _show_help_page()
        _finish(mode, text, res["reply"], engine + "+règle", res["ok"], res["final"])
        _maybe_learn(mode, target, res["ok"], text)
        return

    # 4ter) clic par vision : « clique sur le bouton lecture »
    # (+ combiné JARVIS : « clique sur la barre de recherche et tape bonjour »)
    cm = modes.RE_CLICK.match(n)
    if core.CFG.get("screen_vision", True) and cm and not classified:
        target_desc = cm.group(1).strip(" ?.")
        extra = re.search(r"\s+et\s+(tape|ecris|cherche)\s+(.+)$", target_desc)
        if extra:
            target_desc = target_desc[:extra.start()].strip()
        pill.show("thinking", f"Je cherche « {target_desc} »…")
        try:
            img = winext.screenshot_b64()
            w, h = winext.screen_size()
            spot = core.ask_vision_box(target_desc, img, w, h)
        except Exception as e:
            core.log_err("vision_click", e)
            spot = None
        if spot:
            x, y, desc = spot
            dbl = any(k in n for k in ("musique", "chanson", "piste", "numero", "titre"))
            winext.click_at(x, y, double=dbl)
            if extra:
                time.sleep(0.3)
                keyboard.write(core.fill_personal(extra.group(2).strip()),
                               delay=0.004)
                if extra.group(1) == "cherche":
                    keyboard.send("enter")
                _finish("clic", text, f"J'ai cliqué sur {desc} et écrit le texte",
                        engine + "+vision", True)
                return
            _finish("clic", text, f"J'ai cliqué sur {desc}", engine + "+vision", True)
            return
        _finish("clic", text, f"Je n'ai pas trouvé « {target_desc} » à l'écran",
                engine + "+vision", False)
        return

    # 4bis) vision : la demande porte sur ce qui est affiché à l'écran
    if core.CFG.get("screen_vision", True) and modes.RE_SCREEN.search(n):
        pill.show("thinking", "Je regarde l'écran…")
        try:
            img = winext.screenshot_b64()
            result = core.ask_llm(text, context=list(LLM_CTX), image=img)
        except Exception as e:
            core.log_err("vision", e)
            pill.show("error", "Vision impossible", str(e)[:90])
            _history("vision", text, f"Erreur : {e}", engine, False)
            pill.hide(3.6)
            return
        if result:
            _handle_llm(result, text, engine + "+vision")
            return
        # aucune IA configurée : on laisse le pipeline normal répondre

    # 5) recherche web explicite — PARLÉE si possible (JARVIS/SerpAPI/DDG),
    # sinon navigateur comme avant
    m = re.search(r"\b(?:recherche|cherche|google)\s+(.{2,})", n)
    if m:
        q = m.group(1)
        spoken = None
        if integrations.is_online():
            try:
                import webinfo
                spoken = webinfo.web_search_speak(q)
            except Exception as e:
                core.log_err("websearch", e)
        if spoken:
            _finish("recherche", text, spoken, engine + "+web", True, q)
            return
        _safe_execute({"action": "web_search", "target": q})
        _finish("recherche", text, f"Je cherche « {q} »", engine + "+règle", True)
        return

    # 6) IA : comprend la demande libre et enchaîne les actions nécessaires
    try:
        result = core.ask_llm(text, context=list(LLM_CTX))
    except Exception as e:
        pill.show("error", "IA indisponible", str(e)[:90])
        _history("ia", text, f"Erreur : {e}", engine, False)
        pill.hide(3.6)
        return
    if result:
        _handle_llm(result, text, engine + "+ia")
    else:
        pill.show("error", "Je n'ai pas compris",
                  "Ajoutez une IA (page Intelligence) pour les demandes libres")
        _history("inconnu", text, "non reconnu", engine, False)
        pill.hide(2.6)
        LAST_FAIL.update(text=text, t=time.time())
        if allow_split:
            relisten()


def _handle_llm(result, text, engine):
    """Réponse IA {reply, steps} → exécution + pilule (IA texte et vision)."""
    import json as _json
    # l'IA demande à VOIR l'écran (action look_screen) : on la rappelle avec
    # la capture — la vision marche ainsi quelle que soit la formulation
    if "+vision" not in engine and any(
            s.get("action") == "look_screen" for s in result.get("steps", [])):
        if not core.CFG.get("screen_vision", True):
            _finish("ia", text, "Active la Vision de l'écran (Réglages > Système) "
                    "pour que je puisse regarder", engine, False)
            return
        pill.show("thinking", "Je regarde l'écran…")
        try:
            img = winext.screenshot_b64()
            result2 = core.ask_llm(text, context=list(LLM_CTX), image=img)
        except Exception as e:
            core.log_err("vision", e)
            pill.show("error", "Vision impossible", str(e)[:90])
            _history("vision", text, f"Erreur : {e}", engine, False)
            pill.hide(3.6)
            return
        if result2:
            result2["steps"] = [s for s in result2.get("steps", [])
                                if s.get("action") != "look_screen"]
            _handle_llm(result2, text, engine + "+vision")
            return
    result["steps"] = [s for s in result.get("steps", [])
                       if s.get("action") != "look_screen"]
    # mémoire courte : l'IA comprend les enchaînements (« mets-le plus fort »)
    LLM_CTX.append({"role": "user", "content": text})
    LLM_CTX.append({"role": "assistant",
                    "content": _json.dumps(result, ensure_ascii=False)})
    try:   # et persistante : la conversation survit au redémarrage (local)
        storage.conv_add("user", text)
        storage.conv_add("assistant", _json.dumps(result, ensure_ascii=False))
    except Exception:
        pass
    if result.get("steps"):
        done, total, blocked = core.execute_steps(result["steps"], text)
        reply = blocked or result.get("reply") or "C'est fait"
        ok = done == total and not blocked
        _finish("ia", text, reply if (ok or done) else
                (result.get("reply") or "Je n'ai pas réussi à le faire"),
                engine, ok or done > 0)
    else:
        # réponse sans action = une VRAIE réponse (question, calcul…) : succès
        reply = result.get("reply") or "Je ne peux pas faire ça"
        _finish("ia", text, reply, engine, bool(result.get("reply")))


LAST_FAIL = {"text": "", "t": 0.0}   # dernière phrase incomprise (apprentissage)
LAST_CMD = {"text": "", "engine": "local"}   # pour le chip « Réessayer »


def retry_last():
    """Relance la dernière commande (chip « Réessayer » de la pilule rouge)."""
    if LAST_CMD["text"]:
        run_spoken(LAST_CMD["text"], LAST_CMD["engine"] or "local")


def _maybe_learn(mode, target, ok, text):
    """Une phrase a échoué, puis une reformulation vers une action SÛRE
    (ouverture, raccourci) a réussi : Nova retient la première formulation."""
    if not ok or mode not in ("open", "shortcut"):
        return
    ft = LAST_FAIL["text"]
    if not ft or time.time() - LAST_FAIL["t"] > 150 or ft == text:
        return
    LAST_FAIL["text"] = ""
    try:
        # jamais apprendre une phrase qui déclenche déjà une commande
        # intégrée : l'automatisation la MASQUERAIT (minuteur, média…)
        if modes.classify(ft) is not None:
            return
    except Exception:
        return
    a = set(core.normalize(ft).split()) - core._FILLER_WORDS
    b = set(core.normalize(text).split()) - core._FILLER_WORDS
    if not a or not b or len(a & b) < max(1, min(len(a), len(b)) // 2):
        return
    fn = core.normalize(ft).strip(" .!?")
    for auto in core.get_automations():
        for p in auto.get("phrases", []):
            if core.matches_phrase(core.normalize(p), fn):
                return   # déjà couvert
    action_type = "keys" if mode == "shortcut" else \
        ("open_url" if str(target).startswith("http") else "open_app")
    core.save_automation({"name": f"Appris : {ft[:40]}", "phrases": [ft],
                          "action": {"type": action_type, "target": target},
                          "reply": "C'est fait"})
    def _notify():
        pill.show("ok", f"Nova a appris : « {ft[:38]} »")
        pill.hide(3.2)
    threading.Timer(3.0, _notify).start()


def _safe_execute(action):
    try:
        return core.execute(action)
    except Exception:
        return False


def _show_help_page():
    """« Que peux-tu faire ? » → la fenêtre s'ouvre sur la page Que dire ?"""
    try:
        if window:
            window.show()
            window.restore()
            window.evaluate_js(
                "document.querySelector('.nav-item[data-page=\"aide\"]').click()")
    except Exception as e:
        core.log_err("help_page", e)


def _finish(mode, text, reply, engine, ok, final="", priority_tts=False):
    if ok:
        pill.show("ok", reply)
    else:
        pill.show("error", reply, "Réessayez, ou créez une automatisation")
    _history(mode, text, reply, engine, ok, final)
    # tout ce que Nova dit entre dans le contexte IA (JARVIS) : « annule-le »,
    # « mets-le plus fort » marchent aussi après une commande règle
    if ok and "règle" in engine and reply and mode not in ("dictée", "note", "slot"):
        import json as _json
        entry = _json.dumps({"reply": "[dit à voix haute] " + reply},
                            ensure_ascii=False)
        if not (LLM_CTX and LLM_CTX[-1].get("content") == entry):
            LLM_CTX.append({"role": "user", "content": text})
            LLM_CTX.append({"role": "assistant", "content": entry})
            try:
                storage.conv_add("user", text)
                storage.conv_add("assistant", entry)
            except Exception:
                pass
    say(reply, priority=priority_tts)
    follow = (ok and core.CFG.get("continuous_conversation", True)
              and not engine.startswith(("texte", "mobile"))
              and mode not in ("urgence", "dictée") and not DICTATION["on"])
    h = max(1.8, min(3.2, len(reply) * 0.045)) if ok else 3.0
    if follow:
        # la pilule ne doit jamais s'estomper AVANT que la réécoute prenne
        # le relais (sinon clignotement) : le hide part toujours après
        h = max(h, max(1.2, min(2.6, 0.8 + len(reply) * 0.028)) + 0.4)
    pill.hide(h)
    # conversation continue : on rouvre l'écoute pour enchaîner sans « Nova »,
    # et la fenêtre de session reste ouverte (parler sans mot d'éveil pendant
    # session_timeout secondes). MAIS au plus 2 enchaînements consécutifs sans
    # mot d'éveil : sinon la voix ambiante (TV, tiers) entretiendrait la
    # conversation à l'infini jusqu'à l'agent LLM (open_url, keys, shell…)
    if follow and SESSION.get("chain", 0) < 2:
        SESSION["until"] = time.time() + float(core.CFG.get("session_timeout", 30) or 0)
        follow_listen(reply)


def trigger(mode="command"):
    threading.Thread(target=listen_flow, args=(mode,), daemon=True).start()


def relisten(hint="Reformule — pas besoin de redire « Nova »"):
    """Après une incompréhension : Nova rouvre l'écoute directement, sans
    mot d'éveil (une seule relance, réglable : Réglages > Écoute)."""
    if not core.CFG.get("relisten_on_fail", True) or DICTATION["on"]:
        return

    def go():
        time.sleep(1.6)          # laisse lire le message d'erreur
        deadline = time.time() + 12
        while tts_active() and time.time() < deadline:
            time.sleep(0.1)      # Nova finit de parler d'abord (état réel)
        if _busy.locked() or DICTATION["on"]:
            return
        listen_flow("command", hint=hint, retry=True)
    threading.Thread(target=go, daemon=True).start()


def follow_listen(reply=""):
    """Conversation continue : après une réponse, Nova écoute encore quelques
    secondes pour enchaîner sans redire « Nova ». Silence = on se range.
    Le délai s'adapte à la longueur de la réponse ; elle reste visible."""
    delay = max(1.2, min(2.6, 0.8 + len(reply) * 0.028))
    hint = (f"✓ {reply[:44]}…" if len(reply) > 44 else f"✓ {reply}") + \
        " · enchaîne, ou silence" if reply else "J'écoute — enchaîne"

    def go():
        time.sleep(delay)        # laisse lire la réponse
        deadline = time.time() + 12
        while tts_active() and time.time() < deadline:
            time.sleep(0.1)      # Nova finit de parler d'abord (état réel)
        if _busy.locked() or DICTATION["on"]:
            return               # une autre action a déjà repris la main
        listen_flow("command", hint=hint, retry=True, follow=True)
    threading.Thread(target=go, daemon=True).start()


def run_spoken(text, engine="local"):
    """Exécute une phrase déjà transcrite (mot d'éveil + commande d'une traite)."""
    def go():
        if not _busy.acquire(blocking=False):
            return
        # la fenêtre de session est consommée : le bruit de fond ne peut pas
        # enchaîner les commandes — _finish la réarme après chaque succès
        SESSION["until"] = 0.0
        try:
            pill.show("thinking", f"« {text} »")
            run_command(text, engine)
        finally:
            if _busy.locked():
                _busy.release()
    threading.Thread(target=go, daemon=True).start()


# ------------------------------------------------------------- mot d'éveil --

WAKE_STATUS = {"state": "inactif", "detail": "", "heard": ""}
WAKE_LIVE = {"on": False}   # True = le micro capte VRAIMENT (bulle : vert, barres réelles)


def _word_close(a, b):
    """Vraie si les deux mots ne diffèrent que d'une lettre (insertion,
    suppression ou substitution) : « nova » ≈ « novah », « nova »…"""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1 or min(la, lb) < 3:
        return False
    i = j = diff = 0
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
            continue
        diff += 1
        if diff > 1:
            return False
        if la == lb:
            i += 1
            j += 1
        elif la > lb:
            i += 1
        else:
            j += 1
    return diff + (la - i) + (lb - j) <= 1


def wake_word_index(raw, wake):
    """Position du mot d'éveil dans la phrase transcrite, ou None.
    Tolère la ponctuation, une lettre d'écart et le mot coupé en deux."""
    words = [core.normalize(w).strip(".,!?;:'\"") for w in raw.split()]
    for i, w in enumerate(words):
        # égalité (fuzzy 1 lettre) et NON sous-chaîne : « rénovation »,
        # « innovation », « supernova » contiennent « nova » mais ne sont
        # pas le mot d'éveil — sinon le reste de la phrase partait en commande
        if w == wake or _word_close(w, wake):
            return i
    for i in range(len(words) - 1):
        # mot coupé en deux par le STT (« no va ») : la CONCATÉNATION doit
        # être le mot d'éveil, pas juste le contenir
        combo = words[i] + words[i + 1]
        if combo == wake or _word_close(combo, wake):
            return i + 1
    return None


def _check_interrupt(mini):
    """Pendant que Nova parle : une mini-phrase vient de se terminer — si
    c'est un mot d'interruption (« stop », « tais-toi »…), on coupe la voix."""
    buf = mini["buf"]
    mini["buf"] = []
    mini["sil"] = None
    if len(buf) < 3:            # < 0,3 s : claquement ou écho, pas un mot
        return
    try:
        snap = np.concatenate(buf).flatten()
        txt = core.transcribe_quick(snap)
    except Exception:
        return
    n = core.normalize(txt or "")
    if n and len(n.split()) <= 4 and INTERRUPT_RE.search(n):
        stop_tts()
        pill.hide(0.2)


def _clap_action():
    """Double applaudissement détecté : selon le réglage, écoute ou lumière."""
    conf = core.CFG.get("double_clap", "off")
    if conf == "listen":
        trigger("command")
        return
    if conf.startswith("light:"):
        name = conf[6:].strip()
        try:
            eid, _nom = modes._ha_entity(name, ("light", "switch"))
            if not eid:
                return
            if eid.startswith("switch."):
                integrations.ha_call("switch", "toggle", eid)
            else:
                integrations.ha_light(eid, "toggle")
        except Exception as e:
            core.log_err("double_clap", e)


def wake_loop_whisper():
    """Écoute continue sans clé. Réécrite pour être vraiment utilisable :
    - petit modèle dédié (réaction ~0,5 s au lieu de plusieurs secondes),
    - seuil de voix adaptatif (suit le bruit ambiant du micro),
    - « Nova, ouvre YouTube » d'une seule traite : la commande qui suit le
      mot d'éveil est exécutée directement, sans deuxième écoute,
    - anti-écho par état TTS réel + mots d'interruption pendant que Nova parle,
    - fenêtre de session : enchaîner sans redire « Nova » (30 s),
    - double applaudissement (optionnel), filtre anti-bruit pré-ASR."""
    import sounddevice as sd
    sr = 16000

    def active():
        return (core.CFG.get("continuous_listening")
                and core.CFG.get("wake_engine") == "whisper")

    mic_fail = 0   # échecs consécutifs d'ouverture du micro configuré
    while True:
        if not active() or _busy.locked() or MIC_MUTED["on"]:
            WAKE_LIVE["on"] = False
            if not active():
                WAKE_STATUS["state"] = "inactif"
            elif MIC_MUTED["on"]:
                WAKE_STATUS.update(state="micro coupé", detail="")
            time.sleep(0.4 if MIC_MUTED["on"] else 0.6)
            continue
        try:
            WAKE_STATUS.setdefault("state", "inactif")
            if WAKE_STATUS["state"] != "actif":
                WAKE_STATUS.update(state="chargement du modèle…", detail="")
            core.get_wake_model()
        except Exception as e:
            core.log_err("wake_model", e)
            WAKE_STATUS.update(state="erreur",
                               detail="modèle d'éveil indisponible, "
                                      "vérifiez la connexion puis redémarrez")
            time.sleep(5)
            continue
        try:
            WAKE_STATUS.update(state="actif", detail="")
            pre = collections.deque(maxlen=12)   # 1,2 s de pré-enregistrement
            speech = []
            started = False
            silence_start = None
            t0 = time.time()
            wake_word = core.CFG.get("wake_word", "nova")
            wake = core.normalize(wake_word).replace(" ", "")
            prompt = wake_word.capitalize() + "."
            # détection partielle PENDANT l'enregistrement : dès que « Nova »
            # apparaît dans l'audio partiel, la pilule s'affiche (ressenti
            # immédiat) et la fin de phrase est raccourcie
            partial = {"busy": False, "woke": False, "shown": False}
            last_check = 0.0

            def _check_partial(snap):
                try:
                    raw_p = core.transcribe_quick(snap, prompt=prompt)
                    if not raw_p:
                        return
                    WAKE_STATUS["heard"] = raw_p[:90]
                    i = wake_word_index(raw_p, wake)
                    if i is None:
                        return
                    partial["woke"] = True
                    aft = " ".join(raw_p.split()[i + 1:]).strip(" ,.!?")
                    if not partial["shown"]:
                        partial["shown"] = True
                        pill.show("listening", "", "Je t'écoute…")
                    if aft:
                        pill.set_text(aft)
                except Exception:
                    pass
                finally:
                    partial["busy"] = False

            mini = {"buf": [], "t0": 0.0, "sil": None}   # interruption pendant le TTS
            clap = {"last": 0.0, "fired": 0.0}
            prev_rms = 0.0
            voiced_blocks = 0
            rms_voiced = 0.0
            # après 2 échecs sur le micro configuré (débranché à chaud), on
            # bascule sur le micro par défaut Windows au lieu de boucler
            dev_kw = core._mic_kw() if mic_fail < 2 else {}
            with sd.InputStream(samplerate=sr, channels=1, dtype="float32",
                                **dev_kw) as stream:
                WAKE_LIVE["on"] = True
                if dev_kw:
                    mic_fail = 0        # le micro configuré remarche
                while active() and not _busy.locked() and not MIC_MUTED["on"]:
                    block, _ = stream.read(int(sr * 0.1))
                    rms = float(np.sqrt(np.mean(block ** 2)))
                    pill.level(rms)          # la bulle réagit à la vraie voix
                    now = time.time()

                    if tts_active():
                        # Nova parle : on ne transcrit JAMAIS sa propre voix.
                        # Seuls les mots d'interruption sont écoutés (mini-
                        # phrases ≤ 2 s, fin de silence 0,35 s — JARVIS).
                        if rms > core.effective_threshold():
                            if not mini["buf"]:
                                mini["t0"] = now
                            mini["buf"].append(block.copy())
                            mini["sil"] = None
                        elif mini["buf"]:
                            if mini["sil"] is None:
                                mini["sil"] = now
                            elif now - mini["sil"] > 0.35:
                                _check_interrupt(mini)
                        if mini["buf"] and now - mini["t0"] > 2.0:
                            _check_interrupt(mini)
                        started = False
                        speech = []
                        silence_start = None
                        voiced_blocks, rms_voiced = 0, 0.0
                        pre.clear()
                        continue
                    if mini["buf"]:
                        mini["buf"] = []
                        mini["sil"] = None

                    # double applaudissement : pic bref précédé de calme —
                    # n'arme jamais l'enregistrement de parole
                    dc = core.CFG.get("double_clap", "off")
                    if dc and dc != "off" and not started:
                        ct = float(core.CFG.get("clap_threshold") or 0.037)
                        if rms > ct and prev_rms < ct * 0.4:
                            if (0.1 <= now - clap["last"] <= 0.8
                                    and now - clap["fired"] > 3.0):
                                clap.update(fired=now, last=0.0)
                                threading.Thread(target=_clap_action,
                                                 daemon=True).start()
                            else:
                                clap["last"] = now
                            prev_rms = rms
                            pre.append(block.copy())
                            continue
                    prev_rms = rms

                    if rms > core.effective_threshold():
                        if not started:
                            speech = list(pre)
                            started = True
                            t0 = now
                            voiced_blocks, rms_voiced = 0, 0.0
                        speech.append(block.copy())
                        silence_start = None
                        voiced_blocks += 1
                        rms_voiced += rms
                    elif started:
                        speech.append(block.copy())
                        if silence_start is None:
                            silence_start = now
                        elif now - silence_start > (0.35 if partial["woke"] else 0.45):
                            break
                    else:
                        core.update_noise(rms)
                        pre.append(block.copy())
                    if started and not partial["busy"] and now - last_check > 0.5 \
                            and len(speech) >= 6:
                        partial["busy"] = True
                        last_check = now
                        snap = np.concatenate(speech).flatten()
                        threading.Thread(target=_check_partial, args=(snap,),
                                         daemon=True).start()
                    if started and now - t0 > 7.0:
                        break
            WAKE_LIVE["on"] = False
            if not started or _busy.locked() or not active() or MIC_MUTED["on"]:
                # micro coupé pendant la capture : l'audio déjà enregistré est
                # jeté (jamais transcrit ni exécuté)
                if partial["shown"] and not _busy.locked():
                    pill.hide(0.1)
                continue
            audio = np.concatenate(speech).flatten()
            # le verdict « Nova » du fil partiel peut encore être en vol : on
            # lui laisse jusqu'à 0,3 s avant de jeter (sinon un « Nova » sec et
            # bref serait perdu par une course avec _check_partial)
            if not partial["woke"] and partial["busy"]:
                t_w = time.time()
                while partial["busy"] and time.time() - t_w < 0.3:
                    time.sleep(0.02)
            # filtre anti-bruit JARVIS : trop court OU trop peu de voix OU
            # trop faible en moyenne → jeté sans transcription (supprime les
            # hallucinations Whisper). « Nova » détecté en partiel = exempté.
            if len(audio) < sr * (0.35 if partial["woke"] else 0.5) or (
                    not partial["woke"]
                    and (voiced_blocks * 0.1 < 0.5
                         or rms_voiced / max(1, voiced_blocks) < core.voiced_rms_min())):
                if partial["shown"]:
                    pill.hide(0.1)
                continue
            raw = core.transcribe_quick(audio, prompt=prompt)
            if not raw:
                if partial["shown"]:
                    pill.hide(0.1)
                continue
            WAKE_STATUS["heard"] = raw[:90]
            if not wake:
                continue
            idx = wake_word_index(raw, wake)
            if idx is None:
                # fenêtre de session (JARVIS, 30 s) : après une réponse, on
                # enchaîne sans redire « Nova »
                nraw = core.normalize(raw).strip(" .!?,")
                if (time.time() < SESSION["until"] and len(nraw) >= 3
                        and "sous-titr" not in nraw and "sous titr" not in nraw):
                    if partial["shown"]:
                        pill.hide(0.1)
                    SESSION["chain"] = SESSION.get("chain", 0) + 1
                    run_spoken(raw.strip(" ,.!?"))
                    time.sleep(0.15)
                    continue
                if partial["shown"]:
                    pill.hide(0.1)
                continue
            if WAKE_SKIP["t"] > t0:      # l'utilisateur a cliqué pour annuler
                continue
            SESSION["chain"] = 0         # vraie interaction au mot d'éveil : on repart à zéro
            words = raw.split()
            after = " ".join(words[idx + 1:]).strip(" ,.!?")
            if len(after) >= 3:
                run_spoken(after)      # commande dans la même phrase : direct
            else:
                # accusé sonore : « Nova » entendu, tu peux parler (JARVIS)
                if core.CFG.get("wake_ack_sound", True):
                    threading.Thread(
                        target=lambda: winsound.Beep(880, 110),
                        daemon=True).start()
                trigger("command")     # mot d'éveil seul : écoute classique
            time.sleep(0.15)
        except Exception as e:
            WAKE_LIVE["on"] = False
            core.log_err("wake_loop", e)
            msg = str(e)
            if any(k in msg for k in ("Invalid", "device", "Errno", "PaError")):
                # micro perdu/débranché : recalibrage + re-détection rapide (JARVIS : 1 s)
                core.NOISE["floor"] = 0.0
                mic_fail += 1
                if mic_fail == 2:
                    # la liste PortAudio est figée depuis l'init : on la
                    # ré-énumère pour que le défaut Windows pointe un micro
                    # encore présent
                    try:
                        sd._terminate()
                        sd._initialize()
                    except Exception as e2:
                        core.log_err("wake_mic_rescan", e2)
                    core._MIC_CACHE["t"] = 0.0   # l'UI relira la vraie liste
                WAKE_STATUS.update(state="erreur", detail="micro perdu, re-détection…")
                time.sleep(1)
            else:
                WAKE_STATUS.update(state="erreur", detail=msg[:110])
                time.sleep(3)


PORCUPINE_STATUS = {"state": "inactif", "detail": ""}


def wake_loop_porcupine():
    """Écoute continue Porcupine (Picovoice) : léger et précis, clé gratuite."""
    import sounddevice as sd

    def _sig():
        c = core.CFG
        return (c.get("continuous_listening"), c.get("wake_engine"),
                c.get("porcupine_keyword"), c.get("porcupine_ppn"),
                c.get("porcupine_sensitivity"))

    while True:
        c = core.CFG
        if (not c.get("continuous_listening") or c.get("wake_engine") != "porcupine"
                or _busy.locked() or MIC_MUTED["on"]):
            PORCUPINE_STATUS["state"] = "micro coupé" if MIC_MUTED["on"] else "inactif"
            time.sleep(0.8)
            continue
        key = winext.get_secret("picovoice")
        if not key:
            PORCUPINE_STATUS.update(state="erreur",
                                    detail="AccessKey Picovoice absente (console.picovoice.ai)")
            time.sleep(3)
            continue
        porcupine = None
        try:
            import pvporcupine
            kw = c.get("porcupine_keyword", "jarvis")
            if kw == "custom" and c.get("porcupine_ppn"):
                porcupine = pvporcupine.create(
                    access_key=key, keyword_paths=[c["porcupine_ppn"]],
                    sensitivities=[c.get("porcupine_sensitivity", 0.6)])
            else:
                porcupine = pvporcupine.create(
                    access_key=key, keywords=[kw],
                    sensitivities=[c.get("porcupine_sensitivity", 0.6)])
            PORCUPINE_STATUS.update(state="actif", detail=kw)
            sig = _sig()
            with sd.InputStream(samplerate=porcupine.sample_rate, channels=1,
                                dtype="int16", blocksize=porcupine.frame_length,
                                **core._mic_kw()) as stream:
                while sig == _sig() and not _busy.locked() and not MIC_MUTED["on"]:
                    block, _ = stream.read(porcupine.frame_length)
                    if porcupine.process(block.flatten()) >= 0:
                        trigger("command")
                        time.sleep(1.0)
        except ImportError:
            PORCUPINE_STATUS.update(state="erreur", detail="pvporcupine non installé")
            time.sleep(5)
        except Exception as e:
            PORCUPINE_STATUS.update(state="erreur", detail=str(e)[:120])
            time.sleep(5)
        finally:
            if porcupine:
                try:
                    porcupine.delete()
                except Exception:
                    pass


# ------------------------------------------------------------------- OBD ----

def _obd_alert(text):
    say(text, priority=True)
    storage.add_history("véhicule", text, text, "obd", False,
                        core.CFG.get("active_profile", ""))


obd_manager = obdmod.ObdManager(on_alert=_obd_alert)


# --------------------------------------------------------------- minuteurs --

def _timer_done(label):
    msg = label or "Le minuteur est terminé"
    pill.show("ok", f"Rappel : {label}" if label else "Minuteur terminé")
    pill.hide(6.0)
    say(msg, priority=True)
    if TRAY["icon"]:
        try:   # notification Windows native (centre de notifications)
            TRAY["icon"].notify(msg, "Nova — minuteur")
        except Exception:
            pass
    storage.add_history("timer", label or "minuteur", msg, "timer", True,
                        core.CFG.get("active_profile", ""))


timers.notify = _timer_done


def _reminder_due(text):
    """Rappel à heure fixe atteint : pilule + voix + notification native."""
    msg = f"Rappel : {text}"
    pill.show("ok", msg)
    pill.hide(8.0)
    say(msg, priority=True)
    if TRAY["icon"]:
        try:
            TRAY["icon"].notify(text, "Nova — rappel")
        except Exception:
            pass
    storage.add_history("rappel", text, msg, "rappel", True,
                        core.CFG.get("active_profile", ""))


timers.notify_reminder = _reminder_due


def _notify_voice(msg):
    """Notification différée générique (fin de scan antivirus…)."""
    pill.show("ok", msg)
    pill.hide(6.0)
    say(msg, priority=True)


modes.av_notify = _notify_voice


# ------------------------------------------------------- accès mobile LAN ---

def _mobile_state():
    hist = storage.list_history(limit=1)
    return {"listening": _busy.locked(), "status": "ok",
            "last": hist[0] if hist else {},
            "timers": timers.list_active(), "mic_muted": MIC_MUTED["on"]}


def _mobile_transcribe(data):
    """Audio webm/opus du téléphone → texte, 100 % local (faster-whisper
    décode le webm via PyAV — jamais d'API cloud de reconnaissance)."""
    import tempfile
    p = os.path.join(tempfile.gettempdir(), f"nova_mob_{int(time.time() * 1000)}.webm")
    with open(p, "wb") as f:
        f.write(data)
    try:
        with core.transcribe_lock:
            segs, _info = core.get_model().transcribe(
                p, language=core.CFG["language"], beam_size=5, vad_filter=True)
            return " ".join(s.text for s in segs).strip()
    finally:
        try:
            os.remove(p)
        except OSError:
            pass


def _mobile_say_wav(text):
    """Réponse en WAV (SAPI hors ligne) pour l'app mobile."""
    import subprocess as sp
    import tempfile
    path = os.path.join(tempfile.gettempdir(),
                        f"nova_mob_tts_{int(time.time() * 1000)}.wav")
    ps = ("Add-Type -AssemblyName System.Speech;"
          "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
          f"$s.SetOutputToWaveFile('{path}');"
          "$s.Speak([Console]::In.ReadToEnd());$s.Dispose()")
    try:
        sp.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
               input=text, text=True, encoding="utf-8", capture_output=True,
               timeout=30, creationflags=sp.CREATE_NO_WINDOW)
        with open(path, "rb") as f:
            return f.read()
    except Exception as e:
        core.log_err("mobile_tts", e)
        return None
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _sync_mobile():
    """Démarre/arrête le serveur mobile selon le réglage (opt-in)."""
    try:
        import mobile
        if core.CFG.get("mobile_enabled"):
            mobile.start({"run": lambda t: run_spoken(t, "mobile"),
                          "state": _mobile_state,
                          "transcribe": _mobile_transcribe,
                          "say_wav": _mobile_say_wav},
                         port=int(core.CFG.get("mobile_port", 8080) or 8080),
                         token=winext.get_secret("mobile_token") or "")
        else:
            mobile.stop()
    except Exception as e:
        core.log_err("mobile", e)


# ------------------------------------------------------------------- API ----

class Api:
    # ---- état global ----
    def get_state(self):
        autos = core.get_automations()
        for a in autos:
            a["conflict"] = modes.automation_conflict(a)
        return {
            "config": core.CFG,
            "automations": autos,
            "notes": core.get_notes(),
            "history": storage.list_history(limit=30),
            "profiles": storage.list_profiles(),
            "secrets": winext.secrets_presence(),
            "status": {
                "whisper": core.model_status(),
                "provider": core.resolve_provider(),
                "providers": core.provider_health(),
                "ollama_running": core.ollama_models() is not None,
                "online": integrations.is_online(),
                "graph": integrations.graph_status(),
                "porcupine": PORCUPINE_STATUS,
                "wake": WAKE_STATUS,
                "obd": obd_manager.snapshot,
                "listening": _busy.locked(),
                "dictation": DICTATION["on"],
                "mics": core.list_mics(),
                "mic_muted": MIC_MUTED["on"],
                "tts_speaking": tts_active(),
                "timers": timers.list_active(),
                "reminders": storage.reminders_list(),
                "stats": storage.stats_summary(),
                "facts": storage.list_facts(),
                "accounts": {
                    "google": integrations.google_connected(),
                    "spotify": integrations.spotify_connected(),
                    "pending": integrations.OAUTH_STATUS,
                },
            },
        }

    def save_config(self, cfg):
        core.save_config(cfg)
        register_hotkeys()
        pill.refresh_bubble()
        return core.CFG

    def set_secret(self, key, value):
        winext.set_secret(key, value or "")
        return winext.secrets_presence()

    # ---- écoute ----
    def listen(self):
        trigger("command")
        return True

    def listen_note(self):
        trigger("note")
        return True

    def listen_dictate(self):
        toggle_dictation()
        return True

    def dictate(self):
        audio = core.record_audio()
        if audio is None:
            return ""
        text, _engine = core.transcribe_routed(audio)
        return text

    def run_text(self, text):
        """Exécute une phrase comme si elle avait été dictée (débogage)."""
        threading.Thread(target=run_command, args=(text, "texte"), daemon=True).start()
        return True

    # ---- notes ----
    def add_note(self, text, title=None):
        return core.add_note(text, title)

    def update_note(self, note_id, text, title):
        return core.update_note(note_id, text, title)

    def delete_note(self, note_id):
        return core.delete_note(note_id)

    # ---- automatisations ----
    def save_automation(self, auto):
        return core.save_automation(auto)

    def delete_automation(self, auto_id):
        return core.delete_automation(auto_id)

    def test_automation(self, auto_id):
        for a in core.get_automations():
            if a["id"] == auto_id:
                act = dict(a["action"])
                return core.execute({"action": act.get("type"), "target": act.get("target"),
                                     "args": act.get("args", ""), "type": act.get("type"),
                                     "text": a.get("phrases", [""])[0]})
        return False

    def suggest_automation(self, desc):
        """L'IA transforme une description libre en automatisation pré-remplie."""
        return core.suggest_automation(desc)

    # ---- minuteurs ----
    def cancel_timer(self, tid):
        return timers.cancel(tid)

    def delete_reminder(self, rid):
        return storage.reminder_delete(rid)

    # ---- pilule / bulle ----
    def reset_float_pos(self):
        core.save_config({"pill_pos": None, "bubble_pos": None})
        pill.refresh_bubble()
        return True

    # ---- historique ----
    def history(self, search="", limit=60):
        return storage.list_history(search, limit)

    def clear_history(self):
        return storage.clear_history()

    # ---- profils & contacts ----
    def save_profile(self, profile):
        pid = storage.save_profile(profile)
        if not core.CFG.get("active_profile"):
            core.save_config({"active_profile": pid})
        return storage.list_profiles()

    def delete_profile(self, pid):
        ok = storage.delete_profile(pid)
        if ok and core.CFG.get("active_profile") == pid:
            core.save_config({"active_profile": storage.list_profiles()[0]["id"]})
        return storage.list_profiles()

    def activate_profile(self, pid):
        core.save_config({"active_profile": pid})
        return True

    # ---- IA ----
    def test_provider(self, provider):
        return core.test_provider(provider)

    def suggest_models(self):
        return core.suggest_models()

    def ollama_pull(self, model):
        return core.ollama_pull(model)

    def pull_status(self):
        return core.pull_status()

    # ---- TTS ----
    def tts_test(self):
        t = core.CFG.get("tts", {})
        phrase = "Nova est prête. Bonne journée !"
        if t.get("engine") == "edge" and integrations.is_online():
            threading.Thread(target=_say_edge, args=(phrase, t),
                             daemon=True).start()
        else:
            _say_sapi(phrase, t)
        return True

    def tts_voices(self):
        return winext.tts_bridge.voices()

    def stop_tts(self):
        stop_tts()
        return True

    # ---- micro ----
    def set_mic_mute(self, on):
        MIC_MUTED["on"] = bool(on)
        return MIC_MUTED["on"]

    # ---- média ----
    def media_key(self, action):
        return winext.send_media_key(action)

    # ---- Microsoft Graph ----
    def delete_fact(self, fid):
        return storage.delete_fact(fid)

    def get_capabilities(self):
        """Tout ce que Nova sait faire, pour la page « Que dire ? »."""
        return {
            "sites": sorted(modes.SITES),
            "apps": sorted(set(list(modes.APPS) +
                               list(core.CFG.get("custom_apps") or {}))),
            "settings": sorted(set(modes.SETTINGS_PAGES)),
            "shortcuts": sorted(modes.SHORTCUTS_VOICE),
            "exemples": [
                ("Minuteurs & rappels", ["mets un minuteur de 10 minutes",
                                         "rappelle-moi dans 20 minutes de sortir les pâtes",
                                         "annule le minuteur"]),
                ("Volume & fenêtres", ["mets le volume à 30 %", "monte le son de 20",
                                       "coupe le son de chrome", "bascule sur word",
                                       "mets chrome et word côte à côte"]),
                ("Vision de l'écran", ["regarde mon écran", "qu'est-ce que tu vois ?",
                                       "lis ce mail", "résume cette page",
                                       "c'est quoi cette erreur ?"]),
                ("Mémoire", ["souviens-toi que ma plaque est AB-123-CD",
                             "c'est quoi ma plaque ?", "oublie ma plaque"]),
                ("Infos", ["quelle heure il est", "quel temps fait-il",
                           "mon briefing", "lis mes mails"]),
                ("Messages & musique", ["envoie un message à paul que j'arrive",
                                        "mets du jazz sur spotify",
                                        "chanson suivante", "va à la gare de lyon"]),
                ("Écriture", ["mode dictée", "écris une liste de courses dans le bloc-notes",
                              "note acheter du pain"]),
                ("Maison (Home Assistant)", ["allume la lumière du salon",
                                             "mets le salon en bleu",
                                             "mets la lumière à 40 %",
                                             "quelle température dans la chambre"]),
                ("Routines & musique", ["au boulot", "mode détente",
                                        "mets de la musique",
                                        "mets de la musique sur youtube"]),
                ("Fichiers & listes", ["trie mes téléchargements",
                                       "trie mes téléchargements par date",
                                       "cherche le fichier facture",
                                       "crée un dossier vacances",
                                       "ajoute le lait à ma liste de courses",
                                       "montre ma liste de courses"]),
                ("Écran (vision)", ["clique sur le bouton lecture",
                                    "écris bonjour dans le champ de recherche",
                                    "regarde-moi (webcam)"]),
                ("Conversation", ["merci (fin de conversation)",
                                  "stop (coupe la voix)",
                                  "que peux-tu faire ?", "salut", "ça va ?"]),
                ("Rappels à heure fixe", ["rappelle-moi le sport à 15 h 30",
                                          "rappelle-moi à 9 h de prendre le médicament",
                                          "ajoute 5 minutes au minuteur",
                                          "combien de temps il reste ?"]),
                ("PC", ["mets le PC en veille", "éteins le PC dans 30 minutes",
                        "redémarre le PC", "annule l'arrêt",
                        "mets la luminosité à 40", "ferme chrome",
                        "vide la corbeille", "combien de batterie ?",
                        "lance un scan antivirus", "désinstalle vlc"]),
                ("Infos instantanées", ["quelle heure est-il à Tokyo ?",
                                        "quelle est la capitale du Japon ?",
                                        "combien font 12 fois 8 ?",
                                        "50 km en miles", "raconte-moi une blague",
                                        "pile ou face", "génère un mot de passe",
                                        "combien de jours avant Noël ?"]),
                ("YouTube & musique", ["cherche lofi sur youtube (puis « le deuxième »)",
                                       "résume cette vidéo", "les tendances gaming",
                                       "joue du jazz", "joue la playlist discover weekly"]),
                ("Web & sorties", ["cherche la hauteur de la tour eiffel",
                                   "montre-moi des images de chats",
                                   "résultats du psg", "classement de la ligue 1",
                                   "trouve-moi un restaurant à lyon",
                                   "où est la tour eiffel ?"]),
                ("Google", ["mon agenda", "crée un document nommé rapport",
                            "écris mes idées dans le doc", "crée un tableur"]),
                ("Obsidian & télé", ["crée une note obsidian idées",
                                     "cherche vacances dans obsidian",
                                     "mets la télé", "zappe sur tf1"]),
            ],
        }

    # ---- domotique Home Assistant ----
    def ha_test(self):
        ok, msg = integrations.ha_test()
        return {"ok": ok, "msg": msg}

    def set_ha(self, url, entities):
        core.CFG["ha_url"] = (url or "").strip().rstrip("/")
        core.CFG["ha_entities"] = {
            str(k).strip()[:40]: {"type": v.get("type", "light"),
                                  "id": str(v.get("id", "")).strip()[:80]}
            for k, v in (entities or {}).items()
            if str(k).strip() and (v or {}).get("id")}
        core.save_config({})
        return {"url": core.CFG["ha_url"], "entities": core.CFG["ha_entities"]}

    def set_routines(self, routines):
        core.CFG["routines"] = {
            str(k).strip()[:40]: [str(s).strip()[:120] for s in (v or []) if str(s).strip()]
            for k, v in (routines or {}).items() if str(k).strip()}
        core.save_config({})
        return core.CFG["routines"]

    def set_music(self, spotify_uri, youtube_url):
        core.CFG["music"] = {"spotify_uri": (spotify_uri or "").strip(),
                             "youtube_url": (youtube_url or "").strip()}
        core.save_config({})
        return core.CFG["music"]

    def set_custom_apps(self, apps):
        core.CFG["custom_apps"] = {
            str(k).strip()[:40]: str(v).strip()[:200]
            for k, v in (apps or {}).items()
            if str(k).strip() and str(v).strip()}
        core.save_config({})
        return core.CFG["custom_apps"]

    # ---- IPTV ----
    def iptv_load(self, source):
        import iptv
        core.CFG["iptv"] = {"source": (source or "").strip()}
        core.save_config({})
        if not source:
            return {"ok": True, "count": 0}
        try:
            ch = iptv.charge_playlist(source)
            return {"ok": True, "count": len(ch)}
        except Exception as e:
            return {"ok": False, "error": str(e)[:120]}

    def iptv_channels(self, filtre=""):
        import iptv
        try:
            if not iptv.chaines():
                src = (core.CFG.get("iptv") or {}).get("source", "")
                if src:
                    iptv.charge_playlist(src)
            return iptv.chaines(filtre)[:200]
        except Exception:
            return []

    def iptv_play(self, nom):
        import webbrowser
        import iptv
        c = iptv.trouve_chaine(nom)
        if not c:
            return False
        webbrowser.open(iptv.stream_url(c))
        return True

    # ---- désinstallation (confirmée par le désinstallateur officiel) ----
    def uninstall_list(self):
        import uninstall_mode
        return uninstall_mode.list_programs()

    def uninstall_go(self, prog_id):
        import uninstall_mode
        return uninstall_mode.uninstall(prog_id)

    # ---- accès mobile ----
    def mobile_info(self):
        import mobile
        return {"enabled": bool(core.CFG.get("mobile_enabled")),
                "ip": mobile.get_local_ip(),
                "port": int(core.CFG.get("mobile_port", 8080) or 8080),
                "has_token": winext.has_secret("mobile_token")}

    def set_mobile(self, enabled, token=""):
        core.CFG["mobile_enabled"] = bool(enabled)
        tok = (token or "").strip()[:64]
        if tok:   # écrase le secret seulement si un jeton est fourni
            winext.set_secret("mobile_token", tok)
        core.CFG["mobile_token"] = ""   # jamais en clair dans config.json
        core.save_config({})
        _sync_mobile()
        return self.mobile_info()

    # ---- Home Assistant : entités disponibles (picker) + états live ----
    def ha_entities_available(self, domain=""):
        st = integrations.ha_all_states()
        return [s for s in st if not domain or s["domain"] == domain][:300]

    # ---- comptes Google / Spotify ----
    def account_start(self, name):
        try:
            (integrations.google_start if name == "google"
             else integrations.spotify_start)()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def account_disconnect(self, name):
        return (integrations.google_disconnect if name == "google"
                else integrations.spotify_disconnect)()

    def graph_start(self):
        try:
            return integrations.graph_start_device_code()
        except Exception as e:
            return {"error": str(e)}

    def graph_status(self):
        return integrations.graph_status()

    def graph_disconnect(self):
        return integrations.graph_disconnect()

    # ---- OBD ----
    def obd_ports(self):
        return obdmod.list_ports()

    def obd_connect(self):
        o = core.CFG.get("obd", {})
        return obd_manager.connect(o.get("port", ""), o.get("mock", True),
                                   o.get("coolant_alert_c", 105), o.get("poll_ms", 2000))

    def obd_disconnect(self):
        obd_manager.disconnect()
        return True

    # ---- divers ----
    def pick_ppn(self):
        try:
            res = window.create_file_dialog(
                webview.OPEN_DIALOG, file_types=("Mot d'éveil Porcupine (*.ppn)",))
            if res:
                path = res[0] if isinstance(res, (list, tuple)) else res
                core.save_config({"porcupine_ppn": path, "porcupine_keyword": "custom"})
                return path
        except Exception:
            pass
        return ""

    def open_url(self, url):
        import webbrowser
        if url.startswith(("http://", "https://")):
            webbrowser.open(url)
        return True

    def set_startup(self, enabled):
        import winreg
        exe = sys.argv[0]
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        try:
            for old in ("AssistantVocal",):
                try:
                    winreg.DeleteValue(key, old)
                except FileNotFoundError:
                    pass
            if enabled and getattr(sys, "frozen", False):
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe}"')
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        finally:
            winreg.CloseKey(key)
        return True

    def get_startup(self):
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run")
            winreg.QueryValueEx(key, APP_NAME)
            return True
        except FileNotFoundError:
            return False

    def win_close(self):
        if core.CFG.get("close_to_tray", True):
            window.hide()
        else:
            os._exit(0)
        return True

    def win_minimize(self):
        window.minimize()
        return True

    def win_maximize(self):
        window.toggle_fullscreen()
        return True

    def quit_app(self):
        winext.tts_bridge.dispose()
        os._exit(0)


# ------------------------------------------------------------------ hotkeys -

_hotkey_handles = []


def register_hotkeys():
    global _hotkey_handles
    for h in _hotkey_handles:
        try:
            keyboard.remove_hotkey(h)
        except (KeyError, ValueError):
            pass
    _hotkey_handles = []
    combos = (
        (core.CFG.get("hotkey"), lambda: trigger("command")),
        (core.CFG.get("note_hotkey"), lambda: trigger("note")),
        (core.CFG.get("dictation_hotkey"), toggle_dictation),
    )
    for combo, fn in combos:
        if not combo:
            continue
        try:
            _hotkey_handles.append(keyboard.add_hotkey(combo, fn))
        except ValueError:
            pass


# ------------------------------------------------------------------ tray ----

def make_icon_image():
    """Logo Nova (piste A « Onde ») : squircle dégradé bleu + barres blanches."""
    from PIL import Image, ImageDraw
    s = 256
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    grad = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    top, bot = (0x3F, 0xA9, 0xFF), (0x0A, 0x63, 0xE8)
    for y in range(s):
        f = y / s
        gd.line([(0, y), (s, y)], fill=tuple(
            int(top[i] + (bot[i] - top[i]) * f) for i in range(3)) + (255,))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([5, 5, s - 6, s - 6], radius=61, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    k = s / 100
    for (x, y, w, h) in ((22, 38, 12, 24), (44, 26, 12, 48), (66, 38, 12, 24)):
        d.rounded_rectangle([x * k, y * k, (x + w) * k, (y + h) * k],
                            radius=6 * k, fill=(255, 255, 255, 255))
    return img


TRAY = {"icon": None}   # référence pour les notifications natives


def start_tray():
    import pystray

    def show_window(icon, item):
        window.show()
        window.restore()

    def toggle_mute(icon, item):
        MIC_MUTED["on"] = not MIC_MUTED["on"]

    icon = pystray.Icon(
        APP_NAME.lower(), make_icon_image().resize((64, 64)), APP_NAME,
        menu=pystray.Menu(
            pystray.MenuItem("Ouvrir " + APP_NAME, show_window, default=True),
            pystray.MenuItem("Écouter", lambda i, it: trigger("command")),
            pystray.MenuItem("Micro coupé", toggle_mute,
                             checked=lambda item: MIC_MUTED["on"]),
            pystray.MenuItem("Note vocale", lambda i, it: trigger("note")),
            pystray.MenuItem("Dictée continue", lambda i, it: toggle_dictation()),
            pystray.MenuItem("Quitter", lambda i, it: (winext.tts_bridge.dispose(),
                                                       os._exit(0))),
        ),
    )
    TRAY["icon"] = icon
    icon.run_detached()


# ------------------------------------------------------------------ main ----

def main():
    global window
    pill.start()
    threading.Thread(target=core.get_model, daemon=True).start()
    threading.Thread(target=core.get_wake_model, daemon=True).start()
    threading.Thread(target=wake_loop_whisper, daemon=True).start()
    threading.Thread(target=wake_loop_porcupine, daemon=True).start()
    timers.start_reminder_loop()
    integrations.start_connectivity_loop()
    _sync_mobile()
    register_hotkeys()
    start_tray()

    window = webview.create_window(
        APP_NAME,
        resource_path(os.path.join("ui", "index.html")),
        js_api=Api(),
        width=1040, height=700, min_size=(880, 580),
        frameless=True, easy_drag=False,
        background_color="#141826",
    )

    def on_closing():
        if core.CFG.get("close_to_tray", True):
            window.hide()
            return False
        return True

    window.events.closing += on_closing
    webview.start(debug=False)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
