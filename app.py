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
import os
import queue
import sys
import threading
import time

import keyboard

import core
import auto_mode
import integrations
import modes_registry
import power_profiles
import storage
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

# état courant (mode + profil de puissance sélectionnés dans le menu)
STATE = {"mode": core.CFG.get("mode", modes_registry.DEFAULT_MODE_ID),
         "profile": core.CFG.get("profile", power_profiles.DEFAULT_ID)}


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


# ============================================================ pilule flottante
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

    # ---- thread tkinter ----
    def run(self):
        import tkinter as tk
        import tkinter.font as tkfont
        self.tk = tk
        self.root = tk.Tk()
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
            c.create_oval(20, cy - 5, 30, cy + 5, fill="#3A3D46", outline="")
            label = modes_registry.label_of(STATE["mode"])
            c.create_text(44, cy, anchor="w", fill="#6E7280", font=self.font,
                          text=f"{label} — prêt")
            key = (core.CFG.get("ptt_key") or "").upper()
            if key:
                tw = self.font_badge.measure(key)
                x2 = self.W - 18
                self._rounded(c, x2 - tw - 16, cy - 11, x2, cy + 11, 6,
                              fill="#26272E", outline="#3A3D46")
                c.create_text(x2 - 8 - tw / 2, cy, fill="#9AA0AE",
                              font=self.font_badge, text=key)

        elif st == "listening":
            for i in range(self.N_BARS):
                x = 18 + i * 5.6
                lv = self.levels[i] if i < len(self.levels) else 0.2
                hh = max(3, lv * 20)
                c.create_rectangle(x, cy - hh / 2, x + 3, cy + hh / 2,
                                   fill=BLUE, outline="")
            c.create_text(104, cy, anchor="w",
                          fill="#6E7280" if not self._text else "#ECEFF7",
                          font=self.font, text=self._text or "Je t'écoute…")

        elif st == "thinking":
            c.create_oval(14, cy - 17, 48, cy + 17, fill="#1E2A3C", outline="")
            c.create_arc(20, cy - 10, 42, cy + 10, start=0, extent=110,
                         style="arc", outline=BLUE, width=2)
            c.create_text(60, cy, anchor="w", fill="#C9CEDC", font=self.font,
                          text=self._text or "Reformulation…", width=self.W - 84)

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
        win.configure(bg="#15161A")
        win.geometry("560x520")
        win.attributes("-topmost", True)

        def on_close():
            self._settings_win = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", on_close)

        pad = {"padx": 16, "pady": 6}
        tk.Label(win, text="Custom Variables", bg="#15161A", fg="#ECEFF7",
                 font=("Segoe UI", 15, "bold")).pack(anchor="w", **pad)
        tk.Label(win, text="Quand je dis…  →  le texte collé à la place "
                 "(100 % local, jamais envoyé à une IA)",
                 bg="#15161A", fg="#8A8F9C", font=("Segoe UI", 9)).pack(anchor="w",
                                                                        padx=16)

        row = tk.Frame(win, bg="#15161A")
        row.pack(fill="x", padx=16, pady=8)
        e_trig = tk.Entry(row, width=16, bg="#26272E", fg="#ECEFF7",
                          insertbackground="#ECEFF7", relief="flat")
        e_trig.pack(side="left", ipady=4)
        tk.Label(row, text="→", bg="#15161A", fg="#8A8F9C").pack(side="left", padx=8)
        e_val = tk.Entry(row, width=30, bg="#26272E", fg="#ECEFF7",
                         insertbackground="#ECEFF7", relief="flat")
        e_val.pack(side="left", ipady=4)

        listbox = tk.Listbox(win, height=8, bg="#1A1B20", fg="#ECEFF7",
                             selectbackground="#2A3B55", relief="flat",
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

        btns = tk.Frame(win, bg="#15161A")
        btns.pack(fill="x", padx=16)
        tk.Button(btns, text="+ Ajouter", command=add_var, bg="#2A3B55",
                  fg="#DCE6F7", relief="flat", padx=12, pady=4).pack(side="left")
        tk.Button(btns, text="Supprimer la sélection", command=del_var,
                  bg="#3A2620", fg="#E7C9BF", relief="flat", padx=12,
                  pady=4).pack(side="left", padx=8)

        # moteur + touche push-to-talk
        sep = tk.Frame(win, bg="#2A2C33", height=1)
        sep.pack(fill="x", padx=16, pady=12)
        eng = tk.Frame(win, bg="#15161A")
        eng.pack(fill="x", padx=16)
        cloud = tk.BooleanVar(value=bool(core.CFG.get("stt", {}).get("cloud_enabled")))

        def toggle_engine():
            stt = dict(core.CFG.get("stt", {}))
            stt["cloud_enabled"] = bool(cloud.get())
            core.save_config({"stt": stt})
        tk.Checkbutton(eng, text="Moteur Cloud (Groq + IA, plus rapide) — sinon "
                       "100 % local", variable=cloud, command=toggle_engine,
                       bg="#15161A", fg="#ECEFF7", selectcolor="#26272E",
                       activebackground="#15161A", activeforeground="#ECEFF7",
                       relief="flat").pack(anchor="w")

        # profil de puissance : les profils trop lourds sont grisés (jamais de
        # plantage RAM). L'utilisateur ne voit aucun nom de modèle.
        prof = tk.Frame(win, bg="#15161A")
        prof.pack(fill="x", padx=16, pady=(10, 0))
        hw = power_profiles.detect_hardware()
        tk.Label(prof, text="Profil de puissance :", bg="#15161A",
                 fg="#ECEFF7").pack(anchor="w")
        tk.Label(prof, text=f"Machine détectée : {hw['ram_total_gb']} Go RAM"
                 + (f" · {hw['gpu_name']}" if hw["has_gpu"] else " · pas de GPU"),
                 bg="#15161A", fg="#8A8F9C", font=("Segoe UI", 8)).pack(anchor="w")
        prof_var = tk.StringVar(value=STATE.get("profile", "normal"))

        def choose_profile():
            _set_profile(prof_var.get())
            prof_var.set(STATE.get("profile", "normal"))   # reflète le repli éventuel

        for ev in power_profiles.evaluate(hw):
            txt = ev["label"] + (f"   🔒 {ev['reason']}" if ev["locked"]
                                 else (f"   ⚠ {ev['warning']}" if ev["warning"] else ""))
            tk.Radiobutton(prof, text=txt, value=ev["id"], variable=prof_var,
                           command=choose_profile,
                           state=("disabled" if ev["locked"] else "normal"),
                           bg="#15161A", fg="#ECEFF7", selectcolor="#26272E",
                           activebackground="#15161A", activeforeground="#ECEFF7",
                           relief="flat").pack(anchor="w")

        kb = tk.Frame(win, bg="#15161A")
        kb.pack(fill="x", padx=16, pady=8)
        tk.Label(kb, text="Touche push-to-talk :", bg="#15161A",
                 fg="#ECEFF7").pack(side="left")
        e_key = tk.Entry(kb, width=10, bg="#26272E", fg="#ECEFF7",
                         insertbackground="#ECEFF7", relief="flat")
        e_key.insert(0, core.CFG.get("ptt_key", "f9"))
        e_key.pack(side="left", padx=8, ipady=3)

        def save_key():
            k = e_key.get().strip().lower()
            if k:
                core.save_config({"ptt_key": k})
                _rebind_ptt()
        tk.Button(kb, text="Appliquer", command=save_key, bg="#2A3B55",
                  fg="#DCE6F7", relief="flat", padx=10, pady=3).pack(side="left")

        refresh()


pill = Pill()


# ============================================================ push-to-talk ===
_ptt_active = threading.Event()   # une session est en cours
_ptt_stop = threading.Event()     # la touche a été relâchée
_ptt_handles = []


def _resolve_prompt(mode_id):
    """Mode concret → son system_prompt. « auto » est résolu selon l'app active
    au moment du collage (jamais avant)."""
    if mode_id == "auto":
        mode_id = auto_mode.current_mode()
    return modes_registry.prompt_of(mode_id), mode_id


def _ptt_session():
    """Enregistre tant que la touche est tenue, puis transcrit → (Custom
    Variables) → reformate selon le mode → colle au curseur. Repli texte brut
    si l'IA échoue : le curseur n'est jamais vide (garde-fou Phase 5b)."""
    try:
        pill.show("listening", "")
        t_release = None
        audio = core.record_audio(on_level=pill.level, stop=_ptt_stop,
                                  end_silence=999)
        t_release = time.time()
        if audio is None:
            pill.show("error", "Je n'ai rien entendu")
            pill.hide(1.6)
            return
        pill.show("thinking", "Transcription…")
        text, engine = core.transcribe_routed(audio)
        if not text:
            pill.show("error", "Je n'ai pas compris")
            pill.hide(1.6)
            return
        pill.show("thinking", f"« {text[:60]} »")
        text = core.fill_personal(text)               # Custom Variables, 100 % local
        # gestion mémoire séquentielle : on libère le STT avant le LLM sur les
        # petites configs, pour ne jamais tenir les deux gros modèles en RAM
        if core.CFG.get("seq_memory"):
            core.unload_whisper()
        prompt, concrete = _resolve_prompt(STATE["mode"])
        # cascade de repli universelle : IA → format_rules → texte brut. Chaque
        # étage est protégé : jamais de plantage, jamais de curseur vide.
        try:
            out = core.format_message(text, prompt)    # repli format_rules intégré
        except Exception as e:
            core.log_err("reformulate", e)
            out = ""
        if not out:
            out = core.format_rules(text) or text
        pasted = winext.paste_into_active_app(out)
        dt = time.time() - t_release
        if pasted:
            pill.show("ok", modes_registry.label_of(concrete),
                      f"{engine} · {dt:.1f}s")
            pill.hide(1.6)
        else:
            pill.show("error", "Collage impossible (presse-papiers)")
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
    if _ptt_active.is_set():
        return
    _ptt_active.set()
    _ptt_stop.clear()
    threading.Thread(target=_ptt_session, daemon=True).start()


def _on_ptt_release(_e=None):
    _ptt_stop.set()


def _rebind_ptt():
    """(Re)branche la touche push-to-talk d'après la config."""
    global _ptt_handles
    for h in _ptt_handles:
        try:
            keyboard.remove_hotkey(h)
        except Exception:
            pass
    _ptt_handles = []
    key = core.CFG.get("ptt_key", "f9")
    try:
        _ptt_handles.append(keyboard.on_press_key(key, _on_ptt_press, suppress=False))
        _ptt_handles.append(keyboard.on_release_key(key, _on_ptt_release, suppress=False))
    except Exception as e:
        core.log_err("ptt_bind", e)


# ============================================================ barre des tâches
def _set_mode(mode_id):
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
    stt["cloud_enabled"] = to_cloud
    core.save_config({"stt": stt, "provider": "auto" if to_cloud else "ollama"})


def _set_profile(profile_id):
    """Sélection d'un profil de puissance : refusée si la machine ne le supporte
    pas (repli sur le plus lourd sûr). Câble STT + LLM local sans exposer les
    noms de modèles."""
    hw = power_profiles.detect_hardware()
    safe = power_profiles.safe_selection(profile_id, hw)
    power_profiles.apply_profile(safe, core.save_config)
    STATE["profile"] = safe
    pill.show("ok", f"Profil : {power_profiles.get_profile(safe)['label']}")
    pill.hide(1.4)


def _build_tray():
    from PIL import Image
    import pystray
    from pystray import Menu, MenuItem

    try:
        img = Image.open(resource_path("icon.png"))
    except Exception:
        img = Image.new("RGB", (64, 64), (0x0A, 0x63, 0xE8))

    def mode_item(m):
        return MenuItem(f"{m['hotkey']}. {m['label']}",
                        lambda _i, _it, mid=m["id"]: _set_mode(mid),
                        checked=lambda _it, mid=m["id"]: STATE["mode"] == mid,
                        radio=True)

    langs = [("auto", "Auto (détection)"), ("fr", "Français"), ("en", "English"),
             ("es", "Español"), ("de", "Deutsch"), ("it", "Italiano"),
             ("pt", "Português")]

    def lang_item(code, label):
        return MenuItem(label,
                        lambda _i, _it, c=code: _set_language(c),
                        checked=lambda _it, c=code: core.CFG.get("language") == c,
                        radio=True)

    def profile_item(ev):
        # profil trop lourd = verrouillé (grisé) + raison ; sinon avertissement discret
        suffix = (f"  🔒 {ev['reason']}" if ev["locked"]
                  else ("  ⚠" if ev["warning"] else ""))
        return MenuItem(ev["label"] + suffix,
                        lambda _i, _it, pid=ev["id"]: _set_profile(pid),
                        checked=lambda _it, pid=ev["id"]: STATE.get("profile") == pid,
                        radio=True, enabled=not ev["locked"])

    prof_items = [profile_item(ev)
                  for ev in power_profiles.evaluate(power_profiles.detect_hardware())]

    menu = Menu(
        MenuItem("Mode", Menu(*[mode_item(m) for m in modes_registry.all_modes()])),
        MenuItem("Profil de puissance", Menu(*prof_items)),
        MenuItem("Langue", Menu(*[lang_item(c, lbl) for c, lbl in langs])),
        MenuItem("Moteur Cloud (Groq + IA)", lambda _i, _it: _toggle_cloud(),
                 checked=lambda _it: bool(core.CFG.get("stt", {}).get("cloud_enabled"))),
        Menu.SEPARATOR,
        MenuItem("Réglages (Custom Variables)…", lambda _i, _it: pill.open_settings()),
        MenuItem("Quitter", lambda icon, _it: icon.stop()),
    )
    return pystray.Icon(APP_NAME, img, "Nova — dictée vocale", menu)


def main():
    # profil de puissance : on borne la sélection sauvegardée à ce que la machine
    # encaisse réellement (garantie « sans bug, sans saturation RAM »)
    hw = power_profiles.detect_hardware()
    safe = power_profiles.safe_selection(core.CFG.get("profile", "normal"), hw)
    power_profiles.apply_profile(safe, core.save_config)
    STATE["profile"] = safe
    core.log_err("startup", f"matériel={hw} → profil={safe}")

    integrations.start_connectivity_loop()   # sonde en ligne (active le STT cloud)
    pill.start()
    _rebind_ptt()
    pill.show("repos", "")
    pill.hide(2.5)
    icon = _build_tray()
    icon.run()                       # bloquant (thread principal)
    # sortie du tray = on quitte proprement
    os._exit(0)


if __name__ == "__main__":
    main()
