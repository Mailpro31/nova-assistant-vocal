# -*- coding: utf-8 -*-
"""Nova v3 — dictée vocale minimaliste (clone Speechly, Windows).

Push-to-talk : on MAINTIENT une touche, on parle, on relâche → Whisper transcrit
(local faster-whisper ou cloud Groq), l'IA reformate selon le MODE choisi
(registre `modes_registry`), et le texte est collé AU CURSEUR dans l'app active.
UI : une pilule flottante (5 états) + une icône barre des tâches (pystray) avec
le choix du mode, la langue, le moteur Local/Cloud et les Custom Variables.

Aucun mot d'éveil, aucune domotique, aucun contrôle PC : tout ça vit dans la
branche d'archive `v2-full-archive`. Ajouter un mode = une entrée dans
`modes_registry.MODES`, rien d'autre à toucher ici.
"""

import collections
import ctypes
import json
import os
import queue
import sys
import threading
import time

import keyboard

import core
import auto_mode
import integrations
import licensing
import modes_registry
import onboarding
import power_profiles
import storage
import updater
import winext

APP_NAME = "Nova"

# instance unique (Windows) : une 2e exécution se referme aussitôt
try:
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "NovaSpeechlyLiteMutex")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        sys.exit(0)
except Exception:
    pass

BLUE, GREEN, ORANGE = "#3FA9FF", "#22C55E", "#E0913A"

# Palette de la fenêtre Réglages tkinter — même langage que dock.html (CLAUDE.md)
SET_BG = "#1F1F22"        # fond fenêtre
SET_FG = "#F2F2F4"        # texte principal
SET_MUT = "#98989F"       # texte secondaire
SET_INSET = "#1A1A1D"     # champs / listes / séparateurs discrets
SET_LINE = "#2E2E30"      # hairline (rgba(255,255,255,.065) composé sur SET_BG)
SET_ACCENT = "#0A84FF"    # accent unique (boutons d'action)
SET_WHITE = "#FFFFFF"     # texte sur accent
SET_OK = "#8FE7B0"        # état succès
SET_ERR = "#E7A08F"       # état erreur
SET_DANGER_BG, SET_DANGER_FG = "#3A2620", "#E7C9BF"   # bouton destructif

# état courant (mode + profil de puissance sélectionnés dans le menu)
STATE = {"mode": core.CFG.get("mode", modes_registry.DEFAULT_MODE_ID),
         "profile": core.CFG.get("profile", power_profiles.DEFAULT_ID)}


resource_path = core.resource_path


def _ph(entry, text):
    """Texte indicatif gris dans un champ tkinter vide (effacé au focus).
    Retourne un getter qui renvoie '' tant que l'indicatif est affiché."""
    if not entry.get():
        entry.insert(0, text)
        entry.config(fg=SET_MUT)

    def on_in(_e):
        if entry.get() == text:
            entry.delete(0, "end")
            entry.config(fg=SET_FG)

    def on_out(_e):
        if not entry.get():
            entry.insert(0, text)
            entry.config(fg=SET_MUT)
    entry.bind("<FocusIn>", on_in)
    entry.bind("<FocusOut>", on_out)
    return lambda: "" if entry.get() == text else entry.get()


def _lock(unlocked, *widgets):
    """Grise les widgets d'une section de réglages sous son palier."""
    if not unlocked:
        for w in widgets:
            w.config(state="disabled")
class Pill(threading.Thread):
    """Pilule flottante façon Speechly : fond sombre, coins arrondis, 5 états
    (repos / écoute / traitement / succès / erreur). Thread tkinter dédié ;
    toute l'API publique passe par une file (thread-safe)."""

    W, H, R = 460, 60, 29
    BG = "#1A1B20"
    TRANSPARENT = "#010203"
    N_BARS = 13
    BORDERS = {"repos": "#3A3D46", "listening": "#2B517E", "thinking": "#3A3D46",
               "ok": "#2C6743", "error": "#7A4438"}

    def __init__(self):
        super().__init__(daemon=True)
        self.q = queue.Queue()
        self.levels = collections.deque([0.0] * self.N_BARS, maxlen=self.N_BARS)
        self._visible = False
        self._state = "repos"
        self._text = ""
        self._sub = ""
        self._alpha = 0.0
        self._alpha_target = 0.0
        self._hide_job = None

    # ---- API thread-safe ----
    def show(self, state, text="", sub=""):
        self.q.put(("show", state, text, sub))

    def set_text(self, text):
        self.q.put(("text", text))

    def hide(self, delay=0.0):
        self.q.put(("hide", delay))

    def level(self, rms):
        self.levels.append(min(1.0, rms * 14))

    def open_settings(self):
        self.q.put(("settings",))

    def open_modes(self):
        """La pilule n'a pas de menu déroulant : on oriente vers le tray (le
        menu des Styles « bonne interface » vit dans le dock web)."""
        self.show("repos", "Styles", "menu Nova dans la barre des tâches")
        self.hide(2.2)

    # ---- cycle de vie (partagé avec WebDock : main() ne teste aucun type) ----
    def serve(self, build_tray):
        """La pilule tourne dans son thread tkinter ; le tray prend le thread
        principal (comportement historique)."""
        global _tray_icon
        self.start()
        _rebind_ptt()
        self.show("repos", "")
        self.hide(2.5)
        _tray_icon = build_tray()
        _tray_icon.run()

    def destroy(self):
        pass   # la pilule se ferme avec le tray ; rien à détruire

    # ---- thread tkinter ----
    def run(self):
        import tkinter as tk
        import tkinter.font as tkfont
        self.tk = tk
        self.root = tk.Tk()
        # les exceptions des callbacks tkinter n'atteignent pas sys.excepthook :
        # tkinter les imprime sur stderr (invisible en .exe) — on les journalise
        self.root.report_callback_exception = \
            lambda et, ev, tb: core.log_err("tk_callback", ev)
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.0)
        try:
            self.root.attributes("-transparentcolor", self.TRANSPARENT)
        except Exception:
            pass
        self.root.configure(bg=self.TRANSPARENT)
        self.canvas = tk.Canvas(self.root, width=self.W, height=self.H,
                                bg=self.TRANSPARENT, highlightthickness=0)
        self.canvas.pack()
        self.font = tkfont.Font(family="Segoe UI", size=12)
        self.font_small = tkfont.Font(family="Segoe UI", size=9)
        self.font_badge = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        self._settings_win = None
        self._make_draggable(self.canvas, self.root, "pill_pos",
                             on_click=lambda _e: self._dismiss())
        self.root.after(50, self._tick)
        self.root.mainloop()

    # ---- géométrie / drag ----
    def _make_draggable(self, widget, win, cfg_key, on_click=None):
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

    def _saved_pos(self, cfg_key, w, h, sw, sh):
        pos = core.CFG.get(cfg_key)
        if (isinstance(pos, (list, tuple)) and len(pos) == 2
                and -w + 60 < pos[0] < sw - 60 and 0 <= pos[1] < sh - 24):
            return int(pos[0]), int(pos[1])
        return None

    def _place(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        pos = self._saved_pos("pill_pos", self.W, self.H, sw, sh)
        x, y = pos if pos else ((sw - self.W) // 2, int(sh * 0.72))
        self.root.geometry(f"{self.W}x{self.H}+{x}+{y}")

    def _dismiss(self):
        if self._hide_job:
            try:
                self.root.after_cancel(self._hide_job)
            except Exception:
                pass
            self._hide_job = None
        self._alpha = 0.0
        self._alpha_target = 0.0
        try:
            self.root.attributes("-alpha", 0.0)
        except Exception:
            pass
        self.root.withdraw()
        self._visible = False

    def _rounded(self, c, x1, y1, x2, y2, r, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return c.create_polygon(pts, smooth=True, **kw)

    # ---- dessin des 5 états ----
    def _redraw(self):
        c = self.canvas
        c.delete("all")
        st = self._state
        self._rounded(c, 2, 2, self.W - 2, self.H - 2, self.R,
                      fill=self.BG, outline=self.BORDERS.get(st, "#3A3D46"), width=1)
        cy = self.H // 2

        if st == "repos":
            # point-orbe : la bille de verre du site, version tkinter (3 ovales)
            c.create_oval(18, cy - 7, 32, cy + 7, fill="#7E92D6", outline="")
            c.create_oval(19, cy - 6, 30, cy + 5, fill="#AEBEEC", outline="")
            c.create_oval(21, cy - 5, 26, cy, fill="#DFE7FA", outline="")
            label = _mode_label(STATE["mode"])   # gère les modes sur mesure (custom:)
            c.create_text(44, cy, anchor="w", fill="#7C8398", font=self.font,
                          text=f"{label} — prête")
            key = (core.CFG.get("ptt_key") or "").upper()
            if key:
                tw = self.font_badge.measure(key)
                x2 = self.W - 18
                self._rounded(c, x2 - tw - 16, cy - 11, x2, cy + 11, 6,
                              fill="#26272E", outline="#3A3D46")
                c.create_text(x2 - 8 - tw / 2, cy, fill="#9AA0AE",
                              font=self.font_badge, text=key)

        elif st == "listening":
            # barres d'égaliseur périwinkle alternées, bouts ronds — la bulle du site
            for i in range(self.N_BARS):
                x = 20 + i * 6
                lv = self.levels[i] if i < len(self.levels) else 0.2
                hh = max(4, lv * 22)
                c.create_line(x, cy - hh / 2, x, cy + hh / 2, width=4,
                              capstyle="round",
                              fill="#9CC8F0" if i % 2 else "#AEBEEC")
            c.create_text(112, cy, anchor="w",
                          fill="#7C8398" if not self._text else "#ECEFF7",
                          font=self.font, text=self._text or "Nova écoute…")
            c.create_text(self.W - 20, cy, anchor="e", fill="#7C8398",
                          font=self.font_small, text="relâchez pour coller")

        elif st == "thinking":
            c.create_oval(14, cy - 17, 48, cy + 17, fill="#1E2A3C", outline="")
            c.create_arc(20, cy - 10, 42, cy + 10, start=0, extent=110,
                         style="arc", outline=BLUE, width=2)
            c.create_text(60, cy, anchor="w", fill="#C9CEDC", font=self.font,
                          text=self._text or "Un instant…", width=self.W - 84)

        elif st == "ok":
            c.create_oval(14, cy - 17, 48, cy + 17, fill="#1E3A2A", outline="")
            c.create_line(24, cy, 29, cy + 5, fill=GREEN, width=3, capstyle="round")
            c.create_line(29, cy + 5, 39, cy - 6, fill=GREEN, width=3, capstyle="round")
            c.create_text(60, cy, anchor="w", fill="#ECEFF7", font=self.font,
                          text=self._text or "Collé", width=self.W - 150)
            c.create_text(self.W - 20, cy, anchor="e", fill=GREEN,
                          font=self.font_badge, text=self._sub or "Collé")

        elif st == "error":
            c.create_oval(14, cy - 17, 48, cy + 17, fill="#3A2620", outline="")
            c.create_line(31, cy - 8, 31, cy + 2, fill=ORANGE, width=3, capstyle="round")
            c.create_oval(29.5, cy + 6, 32.5, cy + 9, fill=ORANGE, outline="")
            c.create_text(60, cy, anchor="w", fill="#ECEFF7", font=self.font,
                          text=self._text or "Erreur", width=self.W - 84)

    def _tick(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "show":
                    _, state, text, sub = msg
                    self._state, self._text, self._sub = state, text, sub
                    if self._hide_job:
                        try:
                            self.root.after_cancel(self._hide_job)
                        except Exception:
                            pass
                        self._hide_job = None
                    self._redraw()
                    self._place()
                    self.root.deiconify()
                    self._visible = True
                    self._alpha_target = 1.0
                elif msg[0] == "text":
                    self._text = msg[1]
                    if self._visible:
                        self._redraw()
                elif msg[0] == "hide":
                    delay = msg[1]
                    if delay > 0:
                        self._hide_job = self.root.after(int(delay * 1000),
                                                         self._dismiss)
                    else:
                        self._dismiss()
                elif msg[0] == "settings":
                    self._open_settings_window()
        except queue.Empty:
            pass
        # animation barres + fondu
        if self._visible:
            if self._state == "listening":
                self._redraw()
            self._alpha += (self._alpha_target - self._alpha) * 0.25
            try:
                self.root.attributes("-alpha", round(self._alpha, 2))
            except Exception:
                pass
        self.root.after(40, self._tick)

    # ---- fenêtre Réglages (Custom Variables + moteur + touche) ----
    def _open_settings_window(self):
        tk = self.tk
        if self._settings_win is not None:
            try:
                self._settings_win.deiconify()
                self._settings_win.lift()
                return
            except Exception:
                self._settings_win = None
        win = tk.Toplevel(self.root)
        self._settings_win = win
        win.title("Nova — Réglages")
        win.configure(bg=SET_BG)
        win.geometry("560x760")
        win.attributes("-topmost", True)

        def on_close():
            self._settings_win = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", on_close)

        # — Licence & version —
        tk.Label(win, text="Licence", bg=SET_BG, fg=SET_FG,
                 font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=16, pady=(14, 4))
        lic_state = tk.Label(win, text="", bg=SET_BG, fg=SET_MUT,
                             font=("Segoe UI", 9), justify="left")
        lic_state.pack(anchor="w", padx=16)

        def _lic_refresh():
            st = licensing.status()
            if not st["active"]:
                lic_state.config(text="Version complète (licences non activées).",
                                 fg=SET_MUT)
            elif st["tier"] == licensing.FREE:
                q = licensing.quota_status()
                lic_state.config(fg=SET_MUT,
                                 text=f"Version : Gratuit — {q['used']}/{q['limit']} "
                                      "caractères transcrits cette semaine.")
            else:
                exp = ("licence perpétuelle" if not st["expiry"] else
                       "expire le " + time.strftime("%d/%m/%Y",
                                                     time.localtime(st["expiry"])))
                lic_state.config(fg=SET_OK,
                                 text=f"Version : {st['tier'].capitalize()} — {exp}.")

        lic_row = tk.Frame(win, bg=SET_BG)
        lic_row.pack(fill="x", padx=16, pady=8)
        e_lic = tk.Entry(lic_row, width=34, bg=SET_INSET, fg=SET_FG,
                         insertbackground=SET_FG, relief="flat")
        e_lic.pack(side="left", ipady=4)
        e_lic.insert(0, core.CFG.get("license_key", ""))

        def _activate():
            res = licensing.activate(e_lic.get().strip())
            if res.get("ok"):
                _lic_refresh()
            else:
                lic_state.config(text=res.get("error", "Clé invalide."), fg=SET_ERR)

        tk.Button(lic_row, text="Activer", command=_activate, bg=SET_ACCENT,
                  fg=SET_WHITE, relief="flat", padx=12, pady=4).pack(side="left", padx=8)
        _lic_refresh()
        # stat de valeur hebdo (rétention) — même info que le dock (« Votre semaine »)
        try:
            wk = storage.week_stats()
            tk.Label(win, text=f"Cette semaine : {wk.get('count', 0)} dictées · "
                     f"≈ {wk.get('minutes', 0)} min de frappe évitées",
                     bg=SET_BG, fg=SET_MUT,
                     font=("Segoe UI", 9)).pack(anchor="w", padx=16)
        except Exception:
            pass
        tk.Frame(win, bg=SET_INSET, height=1).pack(fill="x", padx=16, pady=(8, 2))

        pad = {"padx": 16, "pady": 6}
        tk.Label(win, text="Raccourcis vocaux", bg=SET_BG, fg=SET_FG,
                 font=("Segoe UI", 15, "bold")).pack(anchor="w", **pad)
        tk.Label(win, text="Quand je dis…  →  le texte collé à la place "
                 "(100 % privé, jamais envoyé à une IA)",
                 bg=SET_BG, fg=SET_MUT, font=("Segoe UI", 9)).pack(anchor="w",
                                                                        padx=16)

        row = tk.Frame(win, bg=SET_BG)
        row.pack(fill="x", padx=16, pady=8)
        e_trig = tk.Entry(row, width=16, bg=SET_INSET, fg=SET_FG,
                          insertbackground=SET_FG, relief="flat")
        e_trig.pack(side="left", ipady=4)
        tk.Label(row, text="→", bg=SET_BG, fg=SET_MUT).pack(side="left", padx=8)
        e_val = tk.Entry(row, width=30, bg=SET_INSET, fg=SET_FG,
                         insertbackground=SET_FG, relief="flat")
        e_val.pack(side="left", ipady=4)

        listbox = tk.Listbox(win, height=8, bg=SET_INSET, fg=SET_FG,
                             selectbackground=SET_ACCENT, relief="flat",
                             highlightthickness=0)
        listbox.pack(fill="both", expand=True, padx=16, pady=8)

        def refresh():
            listbox.delete(0, "end")
            for v in core.custom_variables():
                listbox.insert("end", f"{v[0]}   →   {v[1]}")

        def add_var():
            trig, val = e_trig.get().strip(), e_val.get().strip()
            if not trig or not val:
                return
            items = [{"trigger": t, "value": va} for t, va in core.custom_variables()]
            items.append({"trigger": trig, "value": val})
            core.save_custom_variables(items)
            e_trig.delete(0, "end")
            e_val.delete(0, "end")
            refresh()

        def del_var():
            sel = listbox.curselection()
            if not sel:
                return
            items = [{"trigger": t, "value": va} for t, va in core.custom_variables()]
            del items[sel[0]]
            core.save_custom_variables(items)
            refresh()

        btns = tk.Frame(win, bg=SET_BG)
        btns.pack(fill="x", padx=16)
        tk.Button(btns, text="+ Ajouter", command=add_var, bg=SET_ACCENT,
                  fg=SET_WHITE, relief="flat", padx=12, pady=4).pack(side="left")
        tk.Button(btns, text="Supprimer la sélection", command=del_var,
                  bg=SET_DANGER_BG, fg=SET_DANGER_FG, relief="flat", padx=12,
                  pady=4).pack(side="left", padx=8)

        # — Personnalisation (palier Ultra) —
        def ultra_header(title, unlocked):
            tk.Label(win, text=title + ("" if unlocked else "   — NÉCESSITE NOVA ULTRA"),
                     bg=SET_BG, fg=SET_FG, font=("Segoe UI", 15, "bold")
                     ).pack(anchor="w", padx=16, pady=(0, 4))

        tk.Frame(win, bg=SET_LINE, height=1).pack(fill="x", padx=16, pady=12)
        can_orb = licensing.has("orb_customization")
        can_name = licensing.has("custom_naming")
        ultra_header("Personnalisation", can_orb or can_name)
        pcol = tk.Frame(win, bg=SET_BG)
        pcol.pack(fill="x", padx=16, pady=4)
        tk.Label(pcol, text="Couleur de l'orbe :", bg=SET_BG,
                 fg=SET_MUT).pack(side="left")
        e_color = tk.Entry(pcol, width=10, bg=SET_INSET, fg=SET_FG,
                           insertbackground=SET_FG, relief="flat")
        e_color.pack(side="left", padx=8, ipady=3)
        e_color.insert(0, core.CFG.get("orb_color", ""))
        pnam = tk.Frame(win, bg=SET_BG)
        pnam.pack(fill="x", padx=16, pady=4)
        tk.Label(pnam, text="Nom personnalisé :", bg=SET_BG,
                 fg=SET_MUT).pack(side="left")
        e_name = tk.Entry(pnam, width=20, bg=SET_INSET, fg=SET_FG,
                          insertbackground=SET_FG, relief="flat")
        e_name.pack(side="left", padx=8, ipady=3)
        e_name.insert(0, core.CFG.get("custom_name", ""))

        def save_perso():
            if can_orb:
                core.save_config({"orb_color": e_color.get().strip()})
            if can_name:
                core.save_config({"custom_name": e_name.get().strip()[:40]})
        b_perso = tk.Button(win, text="Enregistrer la personnalisation",
                            command=save_perso, bg=SET_ACCENT, fg=SET_WHITE,
                            relief="flat", padx=12, pady=4)
        b_perso.pack(anchor="w", padx=16, pady=(4, 0))
        _lock(can_orb, e_color)                 # verrou par fonctionnalité :
        _lock(can_name, e_name)                 # couleur et nom peuvent différer
        _lock(can_orb or can_name, b_perso)

        # — Modes sur mesure (palier Ultra) : selon l'app / l'onglet actif,
        #   appliquer SON prompt à la reformulation —
        tk.Frame(win, bg=SET_LINE, height=1).pack(fill="x", padx=16, pady=12)
        can_cm = licensing.has("custom_modes")
        ultra_header("Styles sur mesure", can_cm)
        tk.Label(win, text="Quand l'app ou l'onglet actif contient un de ces "
                 "mots, votre consigne reformule à votre façon.",
                 bg=SET_BG, fg=SET_MUT,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=16)

        cmrow = tk.Frame(win, bg=SET_BG)
        cmrow.pack(fill="x", padx=16, pady=(8, 2))
        e_cm_name = tk.Entry(cmrow, width=14, bg=SET_INSET, fg=SET_FG,
                             insertbackground=SET_FG, relief="flat")
        e_cm_name.pack(side="left", ipady=4)
        g_cm_name = _ph(e_cm_name, "Nom (ex. Jira)")
        e_cm_match = tk.Entry(cmrow, width=24, bg=SET_INSET, fg=SET_FG,
                              insertbackground=SET_FG, relief="flat")
        e_cm_match.pack(side="left", padx=8, ipady=4)
        g_cm_match = _ph(e_cm_match, "Mots-clés app/onglet (virgules)")
        t_cm_prompt = tk.Text(win, height=3, bg=SET_INSET, fg=SET_FG,
                              insertbackground=SET_FG, relief="flat",
                              font=("Segoe UI", 9), wrap="word")
        t_cm_prompt.pack(fill="x", padx=16, pady=4)

        cm_list = tk.Listbox(win, height=3, bg=SET_INSET, fg=SET_FG,
                             selectbackground=SET_ACCENT, relief="flat",
                             highlightthickness=0)
        cm_list.pack(fill="x", padx=16, pady=4)

        def cm_refresh():
            cm_list.delete(0, "end")
            for cm in core.CFG.get("custom_modes") or []:
                cm_list.insert("end", f"{cm.get('name', '?')}   ←   "
                               f"{', '.join(cm.get('match') or [])}")

        def cm_add():
            items = list(core.CFG.get("custom_modes") or [])
            items.append({"name": g_cm_name(),
                          "match": g_cm_match().split(","),
                          "prompt": t_cm_prompt.get("1.0", "end")})
            if len(core.save_custom_modes(items)) == len(items):  # ajout valide
                e_cm_name.delete(0, "end")
                e_cm_match.delete(0, "end")
                t_cm_prompt.delete("1.0", "end")
            cm_refresh()

        def cm_del():
            sel = cm_list.curselection()
            if not sel:
                return
            items = list(core.CFG.get("custom_modes") or [])
            del items[sel[0]]
            core.save_custom_modes(items)
            cm_refresh()

        cmb = tk.Frame(win, bg=SET_BG)
        cmb.pack(fill="x", padx=16)
        b_cm_add = tk.Button(cmb, text="+ Créer le Style", command=cm_add,
                             bg=SET_ACCENT, fg=SET_WHITE, relief="flat",
                             padx=12, pady=4)
        b_cm_add.pack(side="left")
        b_cm_del = tk.Button(cmb, text="Supprimer la sélection", command=cm_del,
                             bg=SET_DANGER_BG, fg=SET_DANGER_FG, relief="flat",
                             padx=12, pady=4)
        b_cm_del.pack(side="left", padx=8)
        cm_refresh()
        _lock(can_cm, e_cm_name, e_cm_match, t_cm_prompt, b_cm_add, b_cm_del)

        # moteur + touche push-to-talk
        sep = tk.Frame(win, bg=SET_LINE, height=1)
        sep.pack(fill="x", padx=16, pady=12)
        eng = tk.Frame(win, bg=SET_BG)
        eng.pack(fill="x", padx=16)
        cloud = tk.BooleanVar(value=bool(core.CFG.get("stt", {}).get("cloud_enabled")))

        def toggle_engine():
            if cloud.get() and not licensing.has("cloud_stt"):
                cloud.set(False)                # Turbo réservé à Ultra
                return
            if cloud.get():                     # activation = choix éclairé
                from tkinter import messagebox
                if not messagebox.askyesno(
                        "Activer Turbo ?",
                        "Vos dictées seront traitées en ligne, à la vitesse "
                        "maximale — elles ne restent alors plus exclusivement "
                        "sur votre appareil. Sans connexion, Nova repasse "
                        "automatiquement en Intelligence privée.\n\n"
                        "Activer Turbo ?", parent=win):
                    cloud.set(False)
                    return
            stt = dict(core.CFG.get("stt", {}))
            stt["cloud_enabled"] = bool(cloud.get())
            core.save_config({"stt": stt})
        can_turbo = licensing.has("cloud_stt")
        cb_cloud = tk.Checkbutton(
            eng, text="Turbo (plus rapide, via le réseau) — sinon "
            "Intelligence privée"
            + ("" if can_turbo else "   — NÉCESSITE NOVA ULTRA"),
            variable=cloud, command=toggle_engine,
            bg=SET_BG, fg=SET_FG, selectcolor=SET_INSET,
            activebackground=SET_BG, activeforeground=SET_FG, relief="flat")
        cb_cloud.pack(anchor="w")
        _lock(can_turbo, cb_cloud)

        # démarrage avec Windows : lit et écrit directement la clé Run (même
        # entrée que la case de l'installeur) — pas de copie dans config.json
        autostart = tk.BooleanVar(value=winext.get_autostart())

        def toggle_autostart():
            if not winext.set_autostart(autostart.get()):
                autostart.set(winext.get_autostart())   # échec → état réel
        tk.Checkbutton(eng, text="Lancer Nova au démarrage de Windows",
                       variable=autostart, command=toggle_autostart,
                       bg=SET_BG, fg=SET_FG, selectcolor=SET_INSET,
                       activebackground=SET_BG, activeforeground=SET_FG,
                       relief="flat").pack(anchor="w")

        # mises à jour automatiques (updater GitHub Releases, silencieux)
        autoupd = tk.BooleanVar(value=bool(core.CFG.get("auto_update", True)))
        tk.Checkbutton(eng, text="Mettre à jour Nova automatiquement",
                       variable=autoupd,
                       command=lambda: core.save_config(
                           {"auto_update": autoupd.get()}),
                       bg=SET_BG, fg=SET_FG, selectcolor=SET_INSET,
                       activebackground=SET_BG, activeforeground=SET_FG,
                       relief="flat").pack(anchor="w")

        # « Meilleure IA » (palier Ultra) : meilleur modèle local (selon la RAM)
        # ou cloud (petit modèle rapide et multilingue) pour la reformulation
        can_best = licensing.has("best_models")
        best_ai = tk.BooleanVar(value=bool(core.CFG.get("best_ai")))

        def toggle_best():
            if best_ai.get() and not can_best:
                best_ai.set(False)
                return
            core.save_config({"best_ai": bool(best_ai.get())})
        cb_best = tk.Checkbutton(
            eng, text="Meilleure IA — qualité maximale"
            + ("" if can_best else "   (Nécessite Nova Ultra)"),
            variable=best_ai, command=toggle_best, bg=SET_BG, fg=SET_FG,
            selectcolor=SET_INSET, activebackground=SET_BG,
            activeforeground=SET_FG, relief="flat")
        cb_best.pack(anchor="w")
        _lock(can_best, cb_best)

        # profil de puissance : les profils trop lourds sont grisés (jamais de
        # plantage RAM). L'utilisateur ne voit aucun nom de modèle.
        prof = tk.Frame(win, bg=SET_BG)
        prof.pack(fill="x", padx=16, pady=(10, 0))
        hw = power_profiles.detect_hardware()
        tk.Label(prof, text="Profil de puissance :", bg=SET_BG,
                 fg=SET_FG).pack(anchor="w")
        tk.Label(prof, text=f"Machine détectée : {hw['ram_total_gb']} Go de mémoire"
                 + (f" · {hw['gpu_name']}" if hw["has_gpu"]
                    else " · sans accélération graphique"),
                 bg=SET_BG, fg=SET_MUT, font=("Segoe UI", 8)).pack(anchor="w")
        prof_var = tk.StringVar(value=STATE.get("profile", "normal"))

        def choose_profile():
            _set_profile(prof_var.get())
            prof_var.set(STATE.get("profile", "normal"))   # reflète le repli éventuel

        for ev in power_profiles.evaluate(hw, _profiles_paid()):
            txt = ev["label"] + (f"   — {ev['reason']}" if ev["locked"]
                                 else (f"   — {ev['warning']}" if ev["warning"] else ""))
            tk.Radiobutton(prof, text=txt, value=ev["id"], variable=prof_var,
                           command=choose_profile,
                           state=("disabled" if ev["locked"] else "normal"),
                           bg=SET_BG, fg=SET_FG, selectcolor=SET_INSET,
                           activebackground=SET_BG, activeforeground=SET_FG,
                           relief="flat").pack(anchor="w")

        kb = tk.Frame(win, bg=SET_BG)
        kb.pack(fill="x", padx=16, pady=8)
        tk.Label(kb, text="Touche de dictée :", bg=SET_BG,
                 fg=SET_FG).pack(side="left")
        e_key = tk.Entry(kb, width=10, bg=SET_INSET, fg=SET_FG,
                         insertbackground=SET_FG, relief="flat")
        e_key.insert(0, core.CFG.get("ptt_key", "f9"))
        e_key.pack(side="left", padx=8, ipady=3)

        def save_key():
            k = e_key.get().strip().lower()
            if k:
                core.save_config({"ptt_key": k})
                _rebind_ptt()
        tk.Button(kb, text="Appliquer", command=save_key, bg=SET_ACCENT,
                  fg=SET_WHITE, relief="flat", padx=10, pady=3).pack(side="left")

        # raccourcis clavier : un par Style + ouverture du menu des Styles.
        # Pendant du groupe « Raccourcis clavier » du dock web (parité imposée
        # par CLAUDE.md) — champs texte simples, ex. « ctrl+alt+e », vide = off.
        hkf = tk.Frame(win, bg=SET_BG)
        hkf.pack(fill="x", padx=16, pady=(4, 0))
        tk.Label(hkf, text="Raccourcis clavier (ex. ctrl+alt+e — vide = aucun)",
                 bg=SET_BG, fg=SET_MUT, font=("Segoe UI", 8)).grid(
                     row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))
        hk_entries = {}
        hk_cfg = core.CFG.get("mode_hotkeys") or {}
        rows = [("__menu__", "Ouvrir le menu des Styles")] + \
               [(m["id"], m["label"]) for m in modes_registry.all_modes()]
        for i, (mid, label) in enumerate(rows, start=1):
            tk.Label(hkf, text=label, bg=SET_BG, fg=SET_MUT, width=24,
                     anchor="w").grid(row=i, column=0, sticky="w", pady=1)
            e = tk.Entry(hkf, width=14, bg=SET_INSET, fg=SET_FG,
                         insertbackground=SET_FG, relief="flat")
            e.insert(0, core.CFG.get("menu_hotkey", "") if mid == "__menu__"
                     else hk_cfg.get(mid, ""))
            e.grid(row=i, column=1, sticky="w", ipady=2, pady=1)
            hk_entries[mid] = e

        def save_hotkeys():
            vals = {m: e.get().strip().lower() for m, e in hk_entries.items()}
            core.save_config({
                "menu_hotkey": vals.pop("__menu__", ""),
                "mode_hotkeys": {m: k for m, k in vals.items() if k}})
            _rebind_style_hotkeys()
        tk.Button(hkf, text="Appliquer les raccourcis", command=save_hotkeys,
                  bg=SET_ACCENT, fg=SET_WHITE, relief="flat", padx=10,
                  pady=3).grid(row=len(rows) + 1, column=0, sticky="w",
                               pady=(4, 0))

        # Mes infos : champs de profil réutilisés par « mon adresse », « mon
        # e-mail »… dans le texte dicté (surtout le mode E-mail). 100 % local.
        sep2 = tk.Frame(win, bg=SET_LINE, height=1)
        sep2.pack(fill="x", padx=16, pady=12)
        tk.Label(win, text="Mes infos", bg=SET_BG, fg=SET_FG,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=16)
        info = core.personal_info()
        # clés = source unique storage.PERSONAL_FIELDS (jamais de dérive avec le
        # stockage) ; libellés propres à l'UI
        labels = {"prenom": "Prénom", "nom": "Nom", "email": "E-mail",
                  "telephone": "Téléphone", "adresse": "Adresse"}
        fields = [(k, labels.get(k, k)) for k in storage.PERSONAL_FIELDS]
        entries = {}
        me = tk.Frame(win, bg=SET_BG)
        me.pack(fill="x", padx=16, pady=4)
        for i, (key, label) in enumerate(fields):
            tk.Label(me, text=label, bg=SET_BG, fg=SET_MUT, width=10,
                     anchor="w").grid(row=i, column=0, sticky="w", pady=2)
            e = tk.Entry(me, width=40, bg=SET_INSET, fg=SET_FG,
                         insertbackground=SET_FG, relief="flat")
            e.insert(0, info.get(key, ""))
            e.grid(row=i, column=1, sticky="w", ipady=3, pady=2)
            entries[key] = e

        # informations personnalisées : paires libres « ce que je dis » → valeur,
        # pendant du groupe équivalent du dock web (parité CLAUDE.md)
        xf = tk.Frame(win, bg=SET_BG)
        xf.pack(fill="x", padx=16, pady=(8, 0))
        tk.Label(xf, text="Informations personnalisées (libellé → valeur)",
                 bg=SET_BG, fg=SET_MUT, font=("Segoe UI", 8)).grid(
                     row=0, column=0, columnspan=2, sticky="w")
        extra_rows = []

        def add_extra(label="", value=""):
            r = len(extra_rows) + 1
            e1 = tk.Entry(xf, width=22, bg=SET_INSET, fg=SET_FG,
                          insertbackground=SET_FG, relief="flat")
            e1.insert(0, label)
            e1.grid(row=r, column=0, sticky="w", ipady=2, pady=1)
            e2 = tk.Entry(xf, width=30, bg=SET_INSET, fg=SET_FG,
                          insertbackground=SET_FG, relief="flat")
            e2.insert(0, value)
            e2.grid(row=r, column=1, sticky="w", ipady=2, pady=1, padx=(6, 0))
            extra_rows.append((e1, e2))
        for it in (info.get("extra") or []):
            add_extra(str(it.get("label", "")), str(it.get("value", "")))
        tk.Button(win, text="Ajouter une information", command=add_extra,
                  bg=SET_INSET, fg=SET_FG, relief="flat", padx=10,
                  pady=3).pack(anchor="w", padx=16, pady=(4, 0))

        def save_me():
            o = {k: e.get().strip() for k, e in entries.items()}
            o["extra"] = [{"label": a.get().strip(), "value": b.get().strip()}
                          for a, b in extra_rows
                          if a.get().strip() and b.get().strip()]
            core.save_personal(o)
            pill.show("ok", "Infos enregistrées")
            pill.hide(1.2)
        tk.Button(win, text="Enregistrer mes infos", command=save_me,
                  bg=SET_ACCENT, fg=SET_WHITE, relief="flat", padx=12,
                  pady=4).pack(anchor="w", padx=16, pady=(4, 0))

        refresh()


# ================================================= dock web (organique, option)
DOCK_HTML = core.resource_path(os.path.join("ui", "dock.html"))


class WebDock:
    """Dock flottant rendu en webview (orbe organique WebGL, façon Speechly).

    Interface PAR DÉFAUT de Nova (`CFG["dock_ui"] == "web"`) : toutes les
    fenêtres (dock, bulle d'état, Styles, réglages) partagent le langage
    visuel du site. La pilule tkinter reste le repli automatique quand
    pywebview/WebView2 manque — jamais de démarrage cassé.
    Expose la MÊME API publique que Pill (`show/hide/level/open_settings` +
    `serve/destroy`) pour que le push-to-talk et le tray n'aient rien à changer.

    `webview.start()` est bloquant et DOIT tourner sur le thread principal : en
    mode web, `serve()` lance le tray en thread de fond puis cède le thread
    principal au dock. Tout le visuel (dock + orbe + bulle d'état + réglages en
    surimpression) vit dans la webview → aucun conflit de boucle d'événements
    tkinter/pywebview."""

    # tailles de fenêtre : compacte au repos (petite zone ancrée au bord),
    # agrandie quand le menu des modes ou les réglages s'ouvrent. La fenêtre
    # est OPAQUE et découpée par une région native aux formes réellement
    # visibles (pilule / bulle / menu / réglages) : aucune dépendance à la
    # transparence WebView2 (cassée sur certaines machines → carré blanc).
    COMPACT = (440, 170)
    MODES = (440, 470)
    SETTINGS = (880, 620)      # fenêtre paysage type Réglages macOS
    SETTINGS_MAX = (1180, 780)  # bouton vert (zoom) — borné à l'écran
    BG = "#101218"              # fond opaque sous les surfaces translucides

    def __init__(self):
        if not os.path.isfile(DOCK_HTML):   # exe incomplet → repli pilule,
            raise RuntimeError("dock.html introuvable")   # jamais de 404
        self._win = None
        self._lvl_n = 0
        self._panel = "compact"
        self._hwnd = None
        self._shown = False
        self._got_shape = False

    # ---- API compatible Pill ----
    def show(self, state, text="", sub=""):
        self._js("window.novaShow", state, text or "", sub or "")

    def hide(self, delay=0.0):
        self._js("window.novaHide", int(delay * 1000))

    def level(self, rms):
        # l'orbe lisse déjà le niveau (décroissance interne) : on peut réduire
        # la cadence des allers-retours JS sans perdre en fluidité.
        self._lvl_n = (self._lvl_n + 1) % 3
        if self._lvl_n == 0:
            self._js("window.novaLevel", float(rms))

    def open_settings(self):
        self._set_panel("settings")
        self._js("__openSettings")

    def open_modes(self):
        """Ouvre le menu déroulant des Styles du dock (raccourci clavier).
        Le clic simulé côté JS passe par le protocole `panel` habituel, qui
        redimensionne la fenêtre — un seul mécanisme."""
        self._js("window.novaOpenModes")

    # ---- pont Python → JS ----
    def _js(self, fn, *args):
        if self._win is None:
            return
        try:
            payload = ",".join(json.dumps(a) for a in args)
            self._win.evaluate_js(f"{fn}({payload})")
        except Exception:
            pass

    # ---- géométrie ----
    def _screen(self):
        try:
            u = ctypes.windll.user32
            return u.GetSystemMetrics(0), u.GetSystemMetrics(1)
        except Exception:
            return 1920, 1080

    def _set_panel(self, name):
        """Redimensionne la fenêtre du dock vers le panneau nommé (compact /
        modes / settings / settings_max). Taille dérivée du nom (bornée à
        l'écran), position dérivée de l'ancrage choisi (`dock_position`) pour
        la bulle, centrée pour les réglages. Les réglages ne restent PAS au
        premier plan (contrairement à la bulle, qui doit rester visible
        pendant la dictée)."""
        if self._win is None:
            return
        self._panel = name
        sw, sh = self._screen()
        w, h = getattr(self, name.upper(), self.COMPACT)
        w, h = min(w, sw - 24), min(h, sh - 24)
        if name.startswith("settings"):
            x, y = (sw - w) // 2, max(0, (sh - h) // 2)
        else:                       # bulle / menu : ancrage utilisateur
            anchor = str(core.CFG.get("dock_position") or "bottom-center")
            vert, _, horiz = anchor.partition("-")
            x = {"left": 24, "right": sw - w - 24}.get(horiz, (sw - w) // 2)
            y = 24 if vert == "top" else sh - h - 56
        try:
            self._win.resize(w, h)
            self._win.move(x, y)
            self._win.on_top = not name.startswith("settings")
        except Exception:
            pass
        self._apply_opacity()

    # ---- fenêtre native : région arrondie, opacité, hors barre des tâches ----
    def _get_hwnd(self):
        """Handle Win32 de la fenêtre (mémorisé). À la première acquisition,
        la fenêtre est retirée de la barre des tâches et d'Alt-Tab
        (WS_EX_TOOLWINDOW) : Nova ne vit que dans la zone de notification."""
        if self._hwnd:
            return self._hwnd
        hwnd = 0
        try:
            native = getattr(self._win, "native", None)
            handle = getattr(native, "Handle", None)
            if handle is not None:
                hwnd = int(getattr(handle, "ToInt64", lambda: handle)())
        except Exception:
            hwnd = 0
        if not hwnd:
            try:
                hwnd = ctypes.windll.user32.FindWindowW(None, "NovaDock")
            except Exception:
                hwnd = 0
        if hwnd:
            self._hwnd = hwnd
            try:  # tray uniquement : ni barre des tâches, ni Alt-Tab
                u = ctypes.windll.user32
                GWL_EXSTYLE, TOOL, APPWIN = -20, 0x00000080, 0x00040000
                st = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
                u.SetWindowLongW(hwnd, GWL_EXSTYLE, (st | TOOL) & ~APPWIN)
            except Exception as e:
                core.log_err("dock_exstyle", e)
        return self._hwnd

    def apply_shape(self, payload):
        """Découpe la fenêtre aux formes visibles rapportées par le JS
        ({vw, vh, shapes:[{x,y,w,h,r}]} en px CSS). L'échelle réelle est
        mesurée (client Win32 ÷ viewport JS) → correct quel que soit le DPI.
        Tout ce qui est hors région n'existe pas : pas de fond blanc, pas de
        zone cliquable fantôme. À la première forme, la fenêtre (créée cachée)
        est révélée — l'utilisateur ne voit jamais le rectangle nu."""
        try:
            hwnd = self._get_hwnd()
            if not hwnd:
                return
            import ctypes.wintypes as wt
            u, g = ctypes.windll.user32, ctypes.windll.gdi32
            self._got_shape = True          # le JS est vivant : plus de secours
            shapes = payload.get("shapes") or []
            if not shapes:
                # rien à montrer : en mode « invisible au repos », la fenêtre
                # disparaît complètement (SW_HIDE) — silencieuse, sans jamais
                # rien ouvrir dans la barre des tâches
                if core.CFG.get("dock_ghost"):
                    u.ShowWindow(hwnd, 0)                     # SW_HIDE
                return
            rc = wt.RECT()
            u.GetClientRect(hwnd, ctypes.byref(rc))
            vw, vh = float(payload.get("vw") or 0), float(payload.get("vh") or 0)
            if not (rc.right and rc.bottom and vw and vh):
                return
            sx, sy = rc.right / vw, rc.bottom / vh
            region = None
            for s in shapes:
                x1, y1 = int(s["x"] * sx), int(s["y"] * sy)
                x2 = int((s["x"] + s["w"]) * sx) + 1
                y2 = int((s["y"] + s["h"]) * sy) + 1
                r = int(min(float(s.get("r", 13)), s["w"] / 2, s["h"] / 2) * sx) * 2
                rgn = g.CreateRoundRectRgn(x1, y1, x2, y2, r, r)
                if region is None:
                    region = rgn
                else:
                    g.CombineRgn(region, region, rgn, 2)      # RGN_OR
                    g.DeleteObject(rgn)
            if region is not None:
                u.SetWindowRgn(hwnd, region, True)  # le système en devient proprio
            # SW_SHOWNOACTIVATE : la bulle (ré)apparaît SANS prendre le focus —
            # la fenêtre de l'utilisateur reste active pendant la dictée
            u.ShowWindow(hwnd, 4)
            self._shown = True
        except Exception as e:
            core.log_err("dock_shape", e)
        self._reveal()

    def _reveal(self):
        """Secours : ne montre la fenêtre nue QUE si le JS n'a jamais rapporté
        de forme (page cassée) — jamais d'app invisible, jamais de rectangle nu
        par-dessus le mode « invisible au repos »."""
        if self._shown or self._got_shape:
            return
        self._shown = True
        try:
            self._win.show()
        except Exception:
            pass

    def _apply_opacity(self):
        """Opacité choisie par l'utilisateur pour la bulle (réglages toujours
        pleinement opaques). WS_EX_LAYERED + LWA_ALPHA — best effort."""
        try:
            hwnd = self._get_hwnd()
            if not hwnd:
                return
            u = ctypes.windll.user32
            op = 1.0 if self._panel.startswith("settings") else \
                float(core.CFG.get("dock_opacity", 1.0) or 1.0)
            op = min(1.0, max(0.55, op))
            GWL_EXSTYLE, LAYERED, LWA_ALPHA = -20, 0x00080000, 0x2
            NOACT = 0x08000000
            st = u.GetWindowLongW(hwnd, GWL_EXSTYLE) | LAYERED
            # WS_EX_NOACTIVATE partout SAUF réglages : la bulle et ses menus ne
            # prennent JAMAIS l'activation (la dictée colle dans la bonne app),
            # mais les champs des réglages doivent pouvoir recevoir le clavier
            if self._panel.startswith("settings"):
                st &= ~NOACT
            else:
                st |= NOACT
            u.SetWindowLongW(hwnd, GWL_EXSTYLE, st)
            u.SetLayeredWindowAttributes(hwnd, 0, int(op * 255), LWA_ALPHA)
        except Exception as e:
            core.log_err("dock_opacity", e)

    def refresh_prefs(self):
        """Ré-applique position + opacité après un changement de réglage."""
        self._set_panel(self._panel)

    # ---- cycle de vie (bloquant, thread principal) ----
    def serve(self, build_tray):
        """webview.start() exige le thread principal : le tray tourne donc en
        thread de fond, le dock prend le thread principal."""
        global _tray_icon
        _rebind_ptt()
        _tray_icon = build_tray()
        threading.Thread(target=_tray_icon.run, daemon=True).start()
        import webview
        sw, sh = self._screen()
        w, h = self.COMPACT
        anchor = str(core.CFG.get("dock_position") or "bottom-center")
        vert, _, horiz = anchor.partition("-")
        x = {"left": 24, "right": sw - w - 24}.get(horiz, (sw - w) // 2)
        y = 24 if vert == "top" else sh - h - 56
        # Fenêtre OPAQUE créée CACHÉE : le JS rapporte les formes visibles,
        # apply_shape découpe la région native puis révèle la fenêtre. Si le
        # JS ne répond pas (page cassée), on révèle quand même après 5 s —
        # jamais d'app invisible.
        # focus=False : la bulle ne vole JAMAIS le focus clavier — la fenêtre
        # active reste celle de l'utilisateur (détection auto + collage fiables)
        self._win = webview.create_window(
            "NovaDock", DOCK_HTML, width=w, height=h, x=x, y=y,
            frameless=True, easy_drag=False, on_top=True, hidden=True,
            focus=False, background_color=self.BG, resizable=False,
            js_api=DockApi(self))
        threading.Timer(5.0, self._reveal).start()
        webview.start()

    def destroy(self):
        try:
            import webview
            if webview.windows:
                webview.windows[0].destroy()
        except Exception:
            pass


def _perso_caps():
    """Capacités du palier (licensing = seule autorité) — le JS ne compare
    jamais un tier en dur. Source UNIQUE, partagée par state() et
    license_status() pour que l'UI se déverrouille dès l'activation."""
    return {"orb": licensing.has("orb_customization"),
            "name": licensing.has("custom_naming"),
            "modes": licensing.has("custom_modes"),
            "best_ai": licensing.has("best_models"),
            "turbo": licensing.has("cloud_stt")}


class DockApi:
    """Pont JS → Python du dock. Chaque méthode réutilise EXACTEMENT la logique
    du tray / des Réglables tkinter (aucune règle de configuration dupliquée)."""

    def __init__(self, dock):
        self._dock = dock

    def state(self):
        hw = power_profiles.detect_hardware()
        return {
            "modes": [{"id": m["id"], "label": m["label"], "hotkey": m["hotkey"],
                       "allowed": licensing.mode_allowed(m["id"])}
                     for m in modes_registry.all_modes()],
            "profiles": power_profiles.evaluate(hw, _profiles_paid()),
            "hardware": hw,
            "languages": [{"code": c, "label": lbl} for c, lbl in core.LANGUAGES],
            "mode": STATE.get("mode", modes_registry.DEFAULT_MODE_ID),
            "profile": STATE.get("profile", power_profiles.DEFAULT_ID),
            "ptt_key": core.CFG.get("ptt_key", "f9"),
            "mode_hotkeys": core.CFG.get("mode_hotkeys") or {},
            "menu_hotkey": core.CFG.get("menu_hotkey", ""),
            "dock_prefs": {"position": core.CFG.get("dock_position", "bottom-center"),
                           "scale": core.CFG.get("dock_scale", 1.0),
                           "opacity": core.CFG.get("dock_opacity", 1.0),
                           "ghost": bool(core.CFG.get("dock_ghost"))},
            "language": core.CFG.get("language", "fr"),
            "cloud_enabled": bool((core.CFG.get("stt") or {}).get("cloud_enabled")),
            "autostart": winext.get_autostart(),
            "auto_update": bool(core.CFG.get("auto_update", True)),
            "app_version": core.APP_VERSION,
            "personal": core.personal_info(),
            "custom_vars": [{"trigger": t, "value": v}
                            for t, v in core.custom_variables()],
            "tier": licensing.status()["tier"],
            "perso": _perso_caps(),
            "orb_color": core.CFG.get("orb_color", ""),
            "custom_name": core.CFG.get("custom_name", ""),
            "custom_modes": core.CFG.get("custom_modes") or [],
            "best_ai": bool(core.CFG.get("best_ai")),
        }

    def set_autostart(self, on):
        """Démarrage avec Windows (clé Run HKCU). Renvoie l'état réel."""
        winext.set_autostart(bool(on))
        return winext.get_autostart()

    def set_auto_update(self, on):
        """Mises à jour automatiques (updater GitHub Releases)."""
        core.save_config({"auto_update": bool(on)})
        return bool(core.CFG.get("auto_update", True))

    def set_best_ai(self, on):
        """« Meilleure IA » (palier Ultra) : meilleur modèle local/cloud."""
        if not licensing.has("best_models"):
            return {"ok": False}
        core.save_config({"best_ai": bool(on)})
        return {"ok": True, "best_ai": bool(core.CFG.get("best_ai"))}

    # NB : ces méthodes de licence/perso alimentent l'écran de réglages du
    # DOCK web (dock.html, catégories Abonnement / Personnalisation / Modes
    # sur mesure) ; la fenêtre tkinter reste le pendant du mode pilule.
    def save_custom_modes(self, items):
        """Modes sur mesure (palier Ultra) : [{id?, name, match, prompt}]."""
        if not licensing.has("custom_modes"):
            return {"ok": False}
        return {"ok": True, "custom_modes": core.save_custom_modes(items or [])}

    def set_orb_color(self, hex_):
        """Couleur d'orbe personnalisée (palier Ultra). '' = défaut."""
        if not licensing.has("orb_customization"):
            return {"ok": False}
        core.save_config({"orb_color": (hex_ or "").strip()})
        return {"ok": True, "orb_color": core.CFG.get("orb_color", "")}

    def set_custom_name(self, name):
        """Nom personnalisé de l'app (palier Ultra)."""
        if not licensing.has("custom_naming"):
            return {"ok": False}
        core.save_config({"custom_name": (name or "").strip()[:40]})
        return {"ok": True, "custom_name": core.CFG.get("custom_name", "")}

    def set_mode(self, mode_id):
        _set_mode(mode_id)
        return STATE["mode"]              # reflète l'état réel (refus si verrouillé)

    def panel(self, name, open_):
        """Le dock signale quel panneau nommé est ouvert (modes, settings…) ;
        fermé = retour au dock compact. Un seul protocole de redimensionnement."""
        self._dock._set_panel(name if open_ else "compact")

    def shape(self, payload):
        """Formes réellement visibles (px CSS) → région native de la fenêtre."""
        self._dock.apply_shape(payload or {})

    def set_dock_prefs(self, prefs):
        """Préférences de la bulle : ancrage (6 positions), taille, opacité.
        Valide côté Python (le JS ne fait pas autorité) puis ré-applique."""
        prefs = prefs or {}
        cfg = {}
        pos = str(prefs.get("position") or "")
        if pos in ("top-left", "top-center", "top-right",
                   "bottom-left", "bottom-center", "bottom-right"):
            cfg["dock_position"] = pos
        try:
            sc = float(prefs.get("scale"))
            if sc in (1.0, 0.85):
                cfg["dock_scale"] = sc
        except (TypeError, ValueError):
            pass
        try:
            cfg["dock_opacity"] = min(1.0, max(0.55, float(prefs.get("opacity"))))
        except (TypeError, ValueError):
            pass
        if "ghost" in prefs:
            cfg["dock_ghost"] = bool(prefs.get("ghost"))
        if cfg:
            core.save_config(cfg)
            self._dock.refresh_prefs()
        return {"position": core.CFG.get("dock_position", "bottom-center"),
                "scale": core.CFG.get("dock_scale", 1.0),
                "opacity": core.CFG.get("dock_opacity", 1.0),
                "ghost": bool(core.CFG.get("dock_ghost"))}

    def open_upgrade(self):
        """« Passer à Pro » : ouvre les tarifs du site dans le navigateur."""
        import webbrowser
        webbrowser.open("https://novaspeak.app/#tarifs")

    def set_profile(self, profile_id):
        return _set_profile(profile_id, silent=True)

    def set_language(self, code):
        _set_language(code)
        return code

    def toggle_cloud(self):
        _toggle_cloud()
        return bool(core.CFG.get("stt", {}).get("cloud_enabled"))

    def set_ptt_key(self, key):
        key = (key or "").strip().lower()
        if key:
            core.save_config({"ptt_key": key})
            _rebind_ptt()
        return core.CFG.get("ptt_key")

    def set_mode_hotkey(self, mode_id, key):
        """Raccourci direct d'un Style ; clé vide = suppression du raccourci."""
        hk = dict(core.CFG.get("mode_hotkeys") or {})
        key = (key or "").strip().lower()
        if key:
            hk[str(mode_id)] = key
        else:
            hk.pop(str(mode_id), None)
        core.save_config({"mode_hotkeys": hk})
        _rebind_style_hotkeys()
        return hk

    def set_menu_hotkey(self, key):
        """Raccourci qui ouvre le menu des Styles ; vide = désactivé."""
        core.save_config({"menu_hotkey": (key or "").strip().lower()})
        _rebind_style_hotkeys()
        return core.CFG.get("menu_hotkey", "")

    def save_custom_vars(self, items):
        return core.save_custom_variables(items or [])

    def license_status(self):
        """Palier + quota + capacités, pour l'écran de licence du dock. Les
        capacités permettent au dock de déverrouiller l'UI dès l'activation,
        sans redémarrage (perso/cmodes/Turbo)."""
        st = licensing.status()
        st["quota"] = licensing.quota_status()
        st["perso"] = _perso_caps()
        return st

    def week_stats(self):
        """Stat de valeur de la semaine (rétention) — passe-plat défensif :
        le calcul (dont minutes) vit dans storage.week_stats, source unique."""
        try:
            return storage.week_stats()
        except Exception:
            return {"count": 0, "chars": 0, "minutes": 0}

    def activate_license(self, key):
        """Active une clé saisie dans le dock. → status enrichi de `ok`."""
        return licensing.activate((key or "").strip())

    def save_personal(self, info):
        core.save_personal(info or {})
        return core.personal_info()

    def check_update(self):
        _check_update()

    def quit(self):
        _request_quit(_tray_icon)


def _make_ui():
    """Choisit l'UI selon `CFG["dock_ui"]` : "web" (défaut) = le dock et les
    fenêtres du site (webview), "pill" = pilule tkinter. Repli automatique sur
    la pilule si le dock web ne peut pas être instancié (pywebview/WebView2
    absent ou cassé) — jamais de démarrage cassé."""
    if core.CFG.get("dock_ui", "web") != "pill":
        try:
            import webview  # noqa: F401 — vérifie la dispo AVANT de renoncer à la pilule
            return WebDock()
        except Exception as e:
            core.log_err("dock_ui", e)   # pywebview absent/cassé → repli sur la pilule
    return Pill()


pill = _make_ui()
_tray_icon = None


# ============================================================ push-to-talk ===
_ptt_active = threading.Event()   # une session est en cours
_ptt_stop = threading.Event()     # la touche a été relâchée
_ptt_handles = []


def _resolve_prompt(mode_id):
    """Mode concret → son system_prompt. « auto » est résolu selon l'app active
    au moment du collage (jamais avant)."""
    if not mode_id:                               # config « mode »: null / vide
        mode_id = modes_registry.DEFAULT_MODE_ID
    if mode_id == "auto":
        mode_id = auto_mode.current_mode()
    cm = _custom_of(mode_id)
    if cm:
        return cm["prompt"], mode_id
    if mode_id.startswith(CUSTOM_PREFIX) or not licensing.mode_allowed(mode_id):
        mode_id = "voice_to_text"     # custom verrouillé/supprimé, ou mode Pro en Free
    return modes_registry.prompt_of(mode_id), mode_id


CUSTOM_PREFIX = "custom:"


def _custom_of(mode_id):
    """Fiche du mode sur mesure si `mode_id` est « custom:<id> » ET débloqué
    (palier Ultra) ET toujours présent — sinon None. Seul point qui décode le
    préfixe et applique le verrou : les consommateurs (_resolve_prompt,
    _mode_label) ne font que l'appeler."""
    if isinstance(mode_id, str) and mode_id.startswith(CUSTOM_PREFIX) \
            and licensing.has("custom_modes"):
        return auto_mode.custom_mode(mode_id[len(CUSTOM_PREFIX):])
    return None


def _mode_label(mode_id):
    """Libellé d'un mode, y compris sur mesure (« custom:<id> » → son nom)."""
    cm = _custom_of(mode_id)
    if cm:
        return cm.get("name") or "Style perso"
    if isinstance(mode_id, str) and mode_id.startswith(CUSTOM_PREFIX):
        return modes_registry.label_of("voice_to_text")  # custom verrouillé/supprimé
    return modes_registry.label_of(mode_id)


def _ptt_session():
    """Enregistre tant que la touche est tenue, puis transcrit → (Custom
    Variables) → reformate selon le mode → colle au curseur. Repli texte brut
    si l'IA échoue : le curseur n'est jamais vide (garde-fou Phase 5b)."""
    try:
        pill.show("listening", "")
        # Palier Free : quota hebdomadaire de transcription (payant = illimité ;
        # dormant = illimité → aucun effet tant que les licences ne sont pas
        # activées par l'éditeur).
        if not licensing.can_transcribe():
            q = licensing.quota_status()
            pill.show("error", "Quota gratuit atteint",
                      f"{q['used']}/{q['limit']} car. cette semaine — passez à Pro")
            pill.hide(2.6)
            return
        t_release = None
        audio = core.record_audio(on_level=pill.level, stop=_ptt_stop,
                                  end_silence=999)
        t_release = time.time()
        if audio is None:
            pill.show("error", "Je n'ai rien entendu")
            pill.hide(1.6)
            return
        pill.show("thinking", "Un instant…")
        text, engine = core.transcribe_routed(audio)
        if not text:
            pill.show("error", "Je n'ai pas compris")
            pill.hide(1.6)
            return
        pill.show("thinking", f"« {text[:60]} »")
        licensing.record_transcription(text)          # comptabilise le quota Free
        # champs de profil toujours substitués (fonction de base) ; les Custom
        # Variables ne s'appliquent qu'au palier Pro
        text = core.fill_personal(text, custom_vars=licensing.has("custom_variables"))
        # gestion mémoire séquentielle : on libère le STT avant le LLM sur les
        # petites configs, pour ne jamais tenir les deux gros modèles en RAM
        if core.CFG.get("seq_memory"):
            core.unload_whisper()
        prompt, concrete = _resolve_prompt(STATE["mode"])
        # cascade de repli universelle : IA → format_rules → texte brut. Chaque
        # étage est protégé : jamais de plantage, jamais de curseur vide.
        styled = False
        try:
            out, styled = core.format_message_ex(text, prompt)
        except Exception as e:
            core.log_err("reformulate", e)
            out = ""
        if not out:
            out = core.format_rules(text) or text
        pasted = winext.paste_into_active_app(out)
        dt = time.time() - t_release
        if pasted and not styled:
            # honnêteté : le texte est collé mais SANS le Style demandé —
            # le dire, plutôt que d'afficher le Style comme si tout allait bien
            pill.show("error", "Collé sans Style — IA indisponible",
                      "L'Intelligence privée n'a pas répondu")
            pill.hide(2.6)
        elif pasted:
            # l'identifiant moteur (`cloud`, `local`…) reste technique : seul
            # l'affichage est rebrandé (lexique produit : Turbo / Intelligence privée)
            eng_label = "Turbo" if engine == "cloud" else "Intelligence privée"
            pill.show("ok", _mode_label(concrete),
                      f"{eng_label} · {dt:.1f}s")
            pill.hide(1.6)
        else:
            pill.show("error", "Impossible d'insérer le texte")
            pill.hide(2.0)
        try:
            storage.add_history(concrete, text, out, out, engine, True,
                                core.CFG.get("active_profile", ""))
        except Exception:
            pass
    except Exception as e:
        core.log_err("ptt_session", e)
        pill.show("error", "Erreur — réessaie")
        pill.hide(2.0)
    finally:
        _ptt_active.clear()


def _on_ptt_press(_e=None):
    # `_ptt_active` (levé ici, baissé dans le finally de _ptt_session) ignore
    # l'auto-répétition clavier pendant une session ET se ré-arme tout seul à la
    # fin de chaque session : jamais bloqué même si un événement « touche
    # relâchée » est perdu (changement de focus, glitch de hook…).
    if _ptt_active.is_set():
        return
    _ptt_active.set()
    _ptt_stop.clear()
    threading.Thread(target=_ptt_session, daemon=True).start()


def _on_ptt_release(_e=None):
    _ptt_stop.set()


def _rebind_ptt():
    """(Re)branche la touche push-to-talk d'après la config. Accepte une touche
    seule (« f9 ») ou une combinaison « ctrl+space », « alt+n »… : la dictée
    démarre quand TOUTES les touches sont enfoncées, s'arrête dès que l'une
    d'elles est relâchée (même geste maintenir-parler-relâcher)."""
    global _ptt_handles
    for h in _ptt_handles:
        try:
            keyboard.unhook(h)      # handles de on_press_key/on_release_key
        except Exception:
            pass
    _ptt_handles = []
    key = core.CFG.get("ptt_key", "f9")
    parts = [p.strip() for p in str(key).split("+") if p.strip()]
    try:
        if len(parts) <= 1:
            _ptt_handles.append(
                keyboard.on_press_key(key, _on_ptt_press, suppress=False))
            _ptt_handles.append(
                keyboard.on_release_key(key, _on_ptt_release, suppress=False))
            return
        def chord_press(_e=None):
            try:
                if all(keyboard.is_pressed(p) for p in parts):
                    _on_ptt_press()
            except Exception:
                pass
        for p in parts:
            _ptt_handles.append(
                keyboard.on_press_key(p, chord_press, suppress=False))
            _ptt_handles.append(
                keyboard.on_release_key(p, _on_ptt_release, suppress=False))
    except Exception as e:
        core.log_err("ptt_bind", e)
    finally:
        _rebind_style_hotkeys()   # même point d'entrée : serve() et réglages


_style_hotkeys = []               # handles keyboard.add_hotkey (Styles + menu)


def _rebind_style_hotkeys():
    """(Re)branche les raccourcis directs des Styles (`mode_hotkeys`) et celui
    du menu des Styles (`menu_hotkey`). Chaque liaison est indépendante et
    défensive : un raccourci invalide est journalisé puis ignoré — jamais de
    plantage, jamais de dictée morte."""
    global _style_hotkeys
    for h in _style_hotkeys:
        try:
            keyboard.remove_hotkey(h)
        except Exception:
            pass
    _style_hotkeys = []
    for mode_id, key in (core.CFG.get("mode_hotkeys") or {}).items():
        key = str(key or "").strip().lower()
        if not key:
            continue
        try:
            _style_hotkeys.append(keyboard.add_hotkey(
                key, lambda m=mode_id: _hotkey_set_mode(m), suppress=False))
        except Exception as e:
            core.log_err("style_hotkey", e)
    menu = str(core.CFG.get("menu_hotkey") or "").strip().lower()
    if menu:
        try:
            _style_hotkeys.append(keyboard.add_hotkey(
                menu, lambda: pill.open_modes(), suppress=False))
        except Exception as e:
            core.log_err("menu_hotkey", e)


def _hotkey_set_mode(mode_id):
    """Bascule de Style par raccourci clavier : sans le menu sous les yeux,
    l'utilisateur a besoin d'une confirmation visible du Style désormais actif."""
    _set_mode(mode_id)
    if STATE.get("mode") == mode_id:              # refusé si Style verrouillé
        pill.show("ok", _mode_label(mode_id), "Style actif")
        pill.hide(1.4)


# ============================================================ barre des tâches
def _set_mode(mode_id):
    if not licensing.mode_allowed(mode_id):       # mode réservé aux paliers payants
        pill.show("error", "Style réservé à Pro", "Débloquez tous les Styles")
        pill.hide(2.0)
        return
    STATE["mode"] = mode_id
    core.save_config({"mode": mode_id})
    pill.show("repos", "")
    pill.hide(1.2)


def _set_language(lang):
    core.save_config({"language": lang})
    core.CFG["language"] = lang


def _toggle_cloud():
    """Bascule Local ↔ Cloud pour STT ET reformulation (GOAL Partie 4 : local
    par défaut, cloud proposé jamais imposé)."""
    stt = dict(core.CFG.get("stt", {}))
    to_cloud = not stt.get("cloud_enabled")
    if to_cloud and not licensing.has("cloud_stt"):   # Turbo réservé à Ultra
        pill.show("error", "Turbo réservé à Pro", "La vitesse maximale, via le réseau")
        pill.hide(2.2)
        return
    stt["cloud_enabled"] = to_cloud
    core.save_config({"stt": stt, "provider": "auto" if to_cloud else "ollama"})


def _set_profile(profile_id, silent=False):
    """Sélection d'un profil de puissance : refusée si la machine ne le supporte
    pas (repli sur le plus lourd sûr). Câble STT + LLM local sans exposer les
    noms de modèles. `silent` (dock web, qui reflète déjà le choix) saute la
    bulle. Retourne l'id réellement appliqué (repli éventuel)."""
    forced = profile_id != "normal" and not licensing.has("power_profiles")
    if forced:
        profile_id = "normal"                        # profils avancés réservés à Pro
    safe = power_profiles.select_and_apply(profile_id, core.save_config,
                                           _profiles_paid())
    STATE["profile"] = safe
    if not silent and forced:
        pill.show("error", "Profils avancés → Pro", "Élevé / Ultra débloqués en Pro")
        pill.hide(2.2)
    elif not silent:
        pill.show("ok", f"Profil : {power_profiles.get_profile(safe)['label']}")
        pill.hide(1.4)
    return safe


def _request_quit(icon=None):
    """Quitte proprement quelle que soit l'UI : arrête le tray puis ferme l'UI
    (`destroy()` — no-op pour la pilule, ferme la webview pour le dock, ce qui
    rend la main à `serve()` et termine le process)."""
    try:
        if icon is not None:
            icon.stop()
    except Exception:
        pass
    pill.destroy()


def _profiles_paid():
    """L'utilisateur peut-il choisir les profils Élevé/Ultra ? (abonnement
    Pro/Ultra). Dormant → True (no-op), la RAM reste seule à décider."""
    return licensing.has("power_profiles")


def _app_display_name():
    """Nom affiché : personnalisé si palier Ultra + nom défini, sinon « Nova »."""
    name = (core.CFG.get("custom_name") or "").strip()
    return name if (name and licensing.has("custom_naming")) else "Nova"


def _license_tray_label():
    """Libellé dynamique du palier dans le menu (ouvre les Réglages au clic)."""
    st = licensing.status()
    if not st["active"]:
        return "Version : complète"
    if st["tier"] == licensing.FREE:
        q = licensing.quota_status()
        return f"Gratuit — {q['remaining']} car. restants… (Activer une licence)"
    return f"Version : {st['tier'].capitalize()}"


def _check_update(manual=True):
    """Vraie mise à jour : compare à la dernière release ; si plus récente,
    télécharge et installe en silencieux puis relance Nova. Feedback dans la
    pilule/bulle ; jamais bloquant (thread de fond, best-effort)."""
    def work():
        info = updater.check_latest()
        if info and info["newer"]:
            pill.show("thinking", f"Mise à jour vers {info['version']}…")
            if not updater.download_and_install():   # False = rien n'est parti
                if manual:
                    # plan B : l'installation silencieuse a échoué (antivirus,
                    # réseau filtré…) — on ouvre le téléchargement direct dans
                    # le navigateur, l'utilisateur n'est jamais coincé
                    try:
                        import webbrowser
                        webbrowser.open(updater.SETUP_URL)
                        pill.show("error",
                                  "Installation auto impossible — "
                                  "le téléchargement s'ouvre dans le navigateur")
                        pill.hide(4.0)
                    except Exception:
                        pill.show("error",
                                  "Mise à jour impossible — réessaie plus tard")
                        pill.hide(2.6)
                else:
                    pill.hide(0)
        elif manual:
            if info:
                pill.show("ok", "Nova est à jour", "à jour")
                pill.hide(2.0)
            else:
                pill.show("error", "Impossible de vérifier — hors ligne ?")
                pill.hide(2.4)
    threading.Thread(target=work, daemon=True).start()


def _auto_update_check():
    """Au lancement : vérifie en fond (si activé) et met à jour tout seul.
    6 s de délai pour laisser l'app démarrer et le réseau s'établir."""
    if not (core.CFG.get("auto_update", True) and updater.is_frozen()):
        return

    def work():
        time.sleep(6)
        _check_update(manual=False)
    threading.Thread(target=work, daemon=True).start()


def _build_tray():
    from PIL import Image
    import pystray
    from pystray import Menu, MenuItem

    try:
        img = Image.open(resource_path("icon.png"))
    except Exception:
        img = Image.new("RGB", (64, 64), (0x0A, 0x63, 0xE8))

    # NB pystray : l'action d'un MenuItem doit avoir AU PLUS 2 paramètres
    # (co_argcount ≤ 2, cf. _base._assert_action) — un 3e paramètre de capture
    # « x=val » lève ValueError et empêche tout le tray de se construire. Chaque
    # fabrique ayant déjà sa propre variable locale, la fermeture est sûre sans
    # capture par défaut.
    def mode_item(m):
        mid = m["id"]
        return MenuItem(f"{m['hotkey']}. {m['label']}",
                        lambda _i, _it: _set_mode(mid),
                        checked=lambda _it: STATE["mode"] == mid,
                        radio=True)

    def lang_item(code, label):
        return MenuItem(label,
                        lambda _i, _it: _set_language(code),
                        checked=lambda _it: core.CFG.get("language") == code,
                        radio=True)

    def profile_item(ev):
        # profil verrouillé (grisé) + raison ; sinon avertissement discret
        pid = ev["id"]
        suffix = (f"  — {ev['reason']}" if ev["locked"]
                  else ("  — plus demandeur" if ev["warning"] else ""))
        return MenuItem(ev["label"] + suffix,
                        lambda _i, _it: _set_profile(pid),
                        checked=lambda _it: STATE.get("profile") == pid,
                        radio=True, enabled=not ev["locked"])

    prof_items = [profile_item(ev)
                  for ev in power_profiles.evaluate(
                      power_profiles.detect_hardware(), _profiles_paid())]

    menu = Menu(
        MenuItem("Style", Menu(*[mode_item(m) for m in modes_registry.all_modes()])),
        MenuItem("Profil de puissance", Menu(*prof_items)),
        MenuItem("Langue", Menu(*[lang_item(c, lbl) for c, lbl in core.LANGUAGES])),
        MenuItem("Turbo (plus rapide, via le réseau)", lambda _i, _it: _toggle_cloud(),
                 checked=lambda _it: bool(core.CFG.get("stt", {}).get("cloud_enabled"))),
        Menu.SEPARATOR,
        MenuItem(lambda _it: _license_tray_label(),
                 lambda _i, _it: pill.open_settings()),
        MenuItem("Réglages…", lambda _i, _it: pill.open_settings()),
        MenuItem("Vérifier les mises à jour", lambda _i, _it: _check_update()),
        MenuItem("Quitter", lambda icon, _it: _request_quit(icon)),
    )
    return pystray.Icon(APP_NAME, img, f"{_app_display_name()} — dictée vocale", menu)


def _hook_uncaught():
    """Toute exception non rattrapée (thread principal ou threads de fond)
    finit dans nova.log au lieu de disparaître avec la console — en .exe
    fenêtré il n'y a AUCUNE console, c'est la seule trace d'un plantage."""
    sys.excepthook = lambda t, v, tb: core.log_err("uncaught", v)
    threading.excepthook = lambda a: core.log_err("uncaught_thread", a.exc_value)


def main():
    _hook_uncaught()
    # profil de puissance : bootstrap AVANT tout le reste, y compris l'onboarding
    # (best-effort, peut échouer ou être fermé sans être terminé) — la garantie
    # « jamais de saturation RAM » ne doit jamais dépendre de l'écran d'accueil.
    hw = power_profiles.detect_hardware()
    safe = power_profiles.select_and_apply(core.CFG.get("profile", "normal"),
                                           core.save_config, _profiles_paid())
    core.log_err("startup", f"matériel={hw} → profil={safe}")

    if onboarding.needs_onboarding():
        try:
            onboarding.run()          # bloquant, une seule fois (1er lancement)
        except Exception as e:
            core.log_err("onboarding", e)   # jamais bloquant : on démarre quand même

    STATE["profile"] = core.CFG.get("profile", safe)   # reflète un choix fait dans l'onboarding

    integrations.start_connectivity_loop()   # sonde en ligne (active le STT cloud)
    _auto_update_check()                      # MàJ auto en fond (jamais bloquant)

    # abonnement : renouvelle le jeton de licence s'il approche de l'expiration
    # (best-effort, en fond — hors ligne, la période de grâce du jeton suffit)
    threading.Thread(target=licensing.refresh_if_needed, daemon=True).start()

    # Chaque UI possède sa propre boucle (pilule tkinter ou dock webview) via
    # `serve()` : main() n'a aucun type à tester. Bloquant jusqu'à la fermeture.
    pill.serve(_build_tray)
    os._exit(0)


def _preload_models():
    """Lancé par l'installateur (« Nova.exe --preload-models ») : applique le
    profil de puissance adapté à la machine puis télécharge le modèle de
    l'Intelligence privée — la première dictée fonctionne ainsi immédiatement,
    même hors ligne. Ne lève jamais (l'installation n'échoue pas pour autant :
    le modèle se téléchargera au premier lancement)."""
    try:
        power_profiles.select_and_apply(core.CFG.get("profile", "normal"),
                                        core.save_config)
        core.get_model()                       # télécharge et valide le modèle
        core.log_err("preload", f"Intelligence privée prête "
                                f"({core.CFG.get('whisper_model')})")
    except Exception as e:
        core.log_err("preload", e)


if __name__ == "__main__":
    if "--preload-models" in sys.argv:
        _preload_models()
        sys.exit(0)
    main()
