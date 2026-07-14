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
import math
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

# Sonde Qt (sous-processus JETABLE, lancé par _qt_runtime_ok) : tente juste de
# construire QApplication puis sort — 0 = Qt utilisable. Le fichier du plugin de
# plateforme Qt peut être présent mais échouer à CHARGER (DLL dépendante ou
# runtime VC++ absent) ; QApplication appelle alors abort(), une erreur C fatale
# NON rattrapable par try/except, qui tuerait Nova SANS repli. En la testant
# dans cet enfant qu'on peut laisser mourir, le processus principal survit et
# retombe proprement sur le dock web. DOIT court-circuiter AVANT le mutex
# d'instance unique (sinon l'enfant sortirait 0 sans rien tester) et AVANT tout
# le reste du démarrage (_make_ui, onboarding, warmup…).
if "--qt-probe" in sys.argv:
    try:
        from PySide6.QtWidgets import QApplication
        QApplication([]).quit()
    except BaseException:
        os._exit(1)
    os._exit(0)

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
SET_OK = "#30D158"        # état succès (palette CLAUDE.md)
SET_ERR = "#E7A08F"       # état erreur
SET_DANGER_BG, SET_DANGER_FG = "#3A2620", "#E7C9BF"   # bouton destructif

# état courant (mode + profil de puissance sélectionnés dans le menu)
STATE = {"mode": core.CFG.get("mode", modes_registry.DEFAULT_MODE_ID),
         "profile": core.CFG.get("profile", power_profiles.DEFAULT_ID)}
try:
    # Un Style verrouillé hérité d'une version précédente (ex. « messages »,
    # offert en Free avant la v3.1.4) ou d'une licence rétrogradée ne doit pas
    # rester « actif » : l'UI le montrerait sélectionné-mais-verrouillé et
    # chaque dictée serait silencieusement dégradée. On revient au mode par
    # défaut (Automatique) SANS réécrire la config : si l'utilisateur passe
    # Pro, son choix d'origine se réactive tout seul.
    if not licensing.mode_allowed(STATE["mode"]):
        STATE["mode"] = modes_registry.DEFAULT_MODE_ID
except Exception:
    pass


resource_path = core.resource_path

# Dossier de travail = racine des RESSOURCES embarquées (là où vit ui/), PAS le
# dossier de l'exe. Le serveur interne de pywebview résout « ui/dock.html »
# relativement au dossier courant : depuis PyInstaller 6 les données embarquées
# sont sous _internal/ (= sys._MEIPASS) alors que l'exe est un cran au-dessus →
# chdir vers le dossier de l'exe renvoyait « 404 ui/dock.html ». En dev, _MEIPASS
# est absent → APP_DIR (qui contient déjà ui/). Fige aussi un cwd CONNU quand
# l'updater ou le démarrage automatique de Windows relance Nova depuis un autre
# dossier. Les données inscriptibles (config.json, journaux) passent par des
# chemins ABSOLUS basés sur APP_DIR (core._path) → indépendantes du cwd.
try:
    os.chdir(getattr(sys, "_MEIPASS", core.APP_DIR))
except Exception:
    pass

# Boîte noire (nova-crash.log + nova.log) : installée dès l'import pour couvrir
# TOUS les points d'entrée, y compris --preload-models qui n'atteint pas main().
core.install_crash_logging()


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
        # frontières des zones cliquables du dock de repos (recalculées à chaque
        # dessin) : par défaut tout le dock renvoie au comportement « écarter ».
        self._zone_gear = 0
        self._zone_star = self.W

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
                             on_click=self._on_pill_click)
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

    def _on_pill_click(self, e):
        """Clic simple (sans glisser) : sur le dock de repos, la roue dentée
        ouvre les Réglages et l'étoile oriente vers les Styles ; partout ailleurs
        (bulles transitoires), un clic écarte la bulle — comportement historique.
        Toujours défensif : un souci ici ne doit jamais figer la pilule."""
        try:
            if self._state == "repos":
                if e.x <= self._zone_gear:
                    self.open_settings()
                    return
                if e.x >= self._zone_star:
                    self.open_modes()
                    return
        except Exception as ex:
            core.log_err("pill_click", ex)
        self._dismiss()

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

    # ---- petite boîte à outils « verre » (Canvas, sans dépendance, sans lag) ----
    @staticmethod
    def _lerp(a, b, t):
        """Mélange deux couleurs hex — sert à FAUSSER une lueur radiale en
        empilant des ovales dégradés (tkinter ne sait pas faire d'alpha)."""
        a, b = a.lstrip("#"), b.lstrip("#")
        return "#%02x%02x%02x" % tuple(
            max(0, min(255, round(int(a[i:i + 2], 16)
                                  + (int(b[i:i + 2], 16) - int(a[i:i + 2], 16)) * t)))
            for i in (0, 2, 4))

    def _glow_orb(self, c, cx, cy, r, base):
        """Bille de verre + halo bleu façon site. Le halo est une pile d'ovales
        interpolés vers `base` (le fond de la capsule) → dégradé doux, opaque,
        zéro coût perceptible (≈10 ovales)."""
        for k in range(6, 0, -1):
            rr = r * (1 + 0.12 * k)
            col = self._lerp(base, "#8AA0EA", (7 - k) / 9)
            c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=col, outline="")
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#7E92D6", outline="")
        c.create_oval(cx - r + 2, cy - r + 1, cx + r - 3, cy + r - 4,
                      fill="#AEBEEC", outline="")
        c.create_oval(cx - r + 4, cy - r + 3, cx - r + 11, cy - r + 10,
                      fill="#DFE7FA", outline="")

    def _gear_icon(self, c, cx, cy, col, r=6):
        """Roue dentée au trait (réglages) — anneau + 8 dents + moyeu."""
        for a in range(0, 360, 45):
            dx, dy = math.cos(math.radians(a)), math.sin(math.radians(a))
            c.create_line(cx + dx * r, cy + dy * r,
                          cx + dx * (r + 3), cy + dy * (r + 3),
                          fill=col, width=2, capstyle="round")
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=col, width=2)
        c.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill=col, outline="")

    def _star_icon(self, c, cx, cy, col, r=8):
        """Étoile 5 branches au trait (Styles)."""
        pts = []
        for k in range(10):
            rad = r if k % 2 == 0 else r * 0.42
            a = math.radians(-90 + k * 36)
            pts += [cx + math.cos(a) * rad, cy + math.sin(a) * rad]
        c.create_polygon(pts, outline=col, fill="", width=2, joinstyle="round")

    def _draw_dock(self, c, cy):
        """État de repos : dock compact « verre » — Réglages · bille de verre ·
        Styles, centré dans la fenêtre. Le reste de la fenêtre est transparent
        (clé de couleur) donc rien n'est capté hors de la capsule. Les icônes
        gauche/droite sont cliquables (zones mémorisées pour _on_pill_click)."""
        wc = 176
        x0 = (self.W - wc) // 2
        x1 = x0 + wc
        self._rounded(c, x0, cy - 26, x1, cy + 26, 26,
                      fill="#212127", outline="#33333A", width=1)
        gx = x0 + 34                 # centre roue dentée (Réglages)
        sx = x1 - 34                 # centre étoile (Styles)
        ox = self.W // 2             # centre de la bille de verre
        for dvx in (gx + 24, sx - 24):
            c.create_line(dvx, cy - 13, dvx, cy + 13, fill="#34343C", width=1)
        self._gear_icon(c, gx, cy, "#9AA0AE")
        self._glow_orb(c, ox, cy, 12, "#212127")
        self._star_icon(c, sx, cy, "#9AA0AE")
        self._zone_gear = gx + 12    # clic ≤ ici → Réglages
        self._zone_star = sx - 12    # clic ≥ ici → Styles

    # ---- dessin des états ----
    def _redraw(self):
        c = self.canvas
        c.delete("all")
        st = self._state
        cy = self.H // 2

        if st == "repos":
            # dock compact centré (capsule à sa propre géométrie) — on ne dessine
            # PAS la capsule pleine largeur des bulles transitoires.
            self._draw_dock(c, cy)
            return

        self._rounded(c, 2, 2, self.W - 2, self.H - 2, self.R,
                      fill=self.BG, outline=self.BORDERS.get(st, "#3A3D46"), width=1)

        if st == "listening":
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
                    # isolé du tick : une exception pendant la CONSTRUCTION de la
                    # fenêtre (état de licence limite, etc.) ne doit jamais casser
                    # la boucle de la pilule — sinon self.root.after(40, _tick) plus
                    # bas ne se replanifie pas et la pilule se fige pour la session.
                    try:
                        self._open_settings_window()
                    except Exception as e:
                        core.log_err("settings_window", e)
                        self._settings_win = None   # fenêtre à moitié construite
        except queue.Empty:
            pass
        except Exception as e:
            core.log_err("pill_tick", e)      # jamais tuer la boucle de la pilule
        # animation barres + fondu — gardée : une exception ici ne doit PAS
        # empêcher la replanification (sinon la pilule se fige pour la session)
        try:
            if self._visible:
                if self._state == "listening":
                    self._redraw()
                self._alpha += (self._alpha_target - self._alpha) * 0.25
                try:
                    self.root.attributes("-alpha", round(self._alpha, 2))
                except Exception:
                    pass
        except Exception as e:
            core.log_err("pill_tick", e)
        try:
            self.root.after(40, self._tick)   # TOUJOURS replanifier
        except Exception:
            pass

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
        # hauteur bornée à l'écran : la fenêtre empile beaucoup de sections et
        # ne doit jamais dépasser le bureau (sinon les boutons du bas sortent de
        # l'écran, inatteignables). Le conteneur défilant ci-dessous rend tout
        # le contenu joignable quelle que soit la taille de l'écran.
        try:
            _sh = int(win.winfo_screenheight())
        except Exception:
            _sh = 760
        win.geometry("600x%d" % max(480, min(760, _sh - 80)))
        win.attributes("-topmost", True)

        # Conteneur défilant (Canvas + Scrollbar) : TOUS les widgets de contenu
        # ci-dessous sont parentés à `body`, pas à `win` — licence, raccourcis
        # vocaux, personnalisation, Styles, moteur, profil, vitesse, « Mes
        # infos »… dépassent le bas sur un petit écran. Sans ce conteneur, la
        # moitié basse (dont « Mes infos ») serait invisible et inatteignable.
        _canvas = tk.Canvas(win, bg=SET_BG, highlightthickness=0, bd=0)
        _vsb = tk.Scrollbar(win, orient="vertical", command=_canvas.yview)
        _canvas.configure(yscrollcommand=_vsb.set)
        _vsb.pack(side="right", fill="y")
        _canvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(_canvas, bg=SET_BG)
        _body_id = _canvas.create_window((0, 0), window=body, anchor="nw")
        # la zone défilable suit la hauteur réelle du contenu ; la largeur de
        # `body` suit celle du canvas (sinon le contenu ne s'étire pas en largeur)
        body.bind("<Configure>",
                  lambda _e: _canvas.configure(scrollregion=_canvas.bbox("all")))
        _canvas.bind("<Configure>",
                     lambda e: _canvas.itemconfigure(_body_id, width=e.width))

        # molette : liée tant que la fenêtre est ouverte (déliée dans on_close).
        # PAS de <Enter>/<Leave> sur le canvas — le frame `body` couvre tout le
        # viewport, donc le canvas reçoit un <Leave> (NotifyInferior) dès qu'on
        # survole le contenu → la molette mourrait PILE là où il faut défiler.
        # bind_all ne capte que les fenêtres Tk (la pilule n'est pas défilable) →
        # aucune molette volée à une autre application.
        def _on_wheel(e):
            # laisser un widget déjà défilable (Listbox des variables/Styles,
            # Text du Style sur mesure) gérer SA molette — sinon il défile ET la
            # page défile en même temps (double défilement désorientant)
            if isinstance(e.widget, (tk.Listbox, tk.Text)):
                return
            _canvas.yview_scroll(int(-(e.delta or 0) / 120), "units")
        _canvas.bind_all("<MouseWheel>", _on_wheel)

        def on_close():
            self._settings_win = None
            try:
                _canvas.unbind_all("<MouseWheel>")   # sinon la molette resterait
            except Exception:                        # liée après la fermeture
                pass
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", on_close)

        # — en-tête : identité Nova (orbe « bille de verre » façon pilule) + titre.
        # Purement décoratif : donne à la fenêtre le même langage visuel que la
        # pilule, sans rien changer au fonctionnement.
        head = tk.Frame(body, bg=SET_BG)
        head.pack(fill="x", padx=16, pady=(16, 2))
        _orb = tk.Canvas(head, width=34, height=34, bg=SET_BG,
                         highlightthickness=0, bd=0)
        _orb.pack(side="left")
        _orb.create_oval(4, 5, 30, 31, fill="#7E92D6", outline="")
        _orb.create_oval(6, 6, 26, 25, fill="#AEBEEC", outline="")
        _orb.create_oval(9, 8, 19, 17, fill="#DFE7FA", outline="")
        _htx = tk.Frame(head, bg=SET_BG)
        _htx.pack(side="left", padx=12)
        tk.Label(_htx, text="Réglages", bg=SET_BG, fg=SET_FG,
                 font=("Segoe UI", 19, "bold")).pack(anchor="w")
        tk.Label(_htx, text="Nova — dictée vocale", bg=SET_BG, fg=SET_MUT,
                 font=("Segoe UI", 9)).pack(anchor="w")
        tk.Frame(body, bg=SET_LINE, height=1).pack(fill="x", padx=16, pady=(10, 0))

        def _seclabel(text, top=18):
            """Libellé de section façon macOS : MAJUSCULES, gris, petit. Purement
            visuel — remplace les gros titres blancs par une hiérarchie sobre."""
            tk.Label(body, text=text.upper(), bg=SET_BG, fg=SET_MUT,
                     font=("Segoe UI", 10, "bold")).pack(
                         anchor="w", padx=16, pady=(top, 5))

        # — Licence & version —
        _seclabel("Licence", top=6)
        lic_state = tk.Label(body, text="", bg=SET_BG, fg=SET_MUT,
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

        lic_row = tk.Frame(body, bg=SET_BG)
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
            tk.Label(body, text=f"Cette semaine : {wk.get('count', 0)} dictées · "
                     f"≈ {wk.get('minutes', 0)} min de frappe évitées",
                     bg=SET_BG, fg=SET_MUT,
                     font=("Segoe UI", 9)).pack(anchor="w", padx=16)
        except Exception:
            pass
        tk.Frame(body, bg=SET_INSET, height=1).pack(fill="x", padx=16, pady=(8, 2))

        _seclabel("Raccourcis vocaux")
        tk.Label(body, text="Quand je dis…  →  le texte collé à la place "
                 "(100 % privé, jamais envoyé à une IA)",
                 bg=SET_BG, fg=SET_MUT, font=("Segoe UI", 9)).pack(anchor="w",
                                                                        padx=16)

        row = tk.Frame(body, bg=SET_BG)
        row.pack(fill="x", padx=16, pady=8)
        e_trig = tk.Entry(row, width=16, bg=SET_INSET, fg=SET_FG,
                          insertbackground=SET_FG, relief="flat")
        e_trig.pack(side="left", ipady=4)
        tk.Label(row, text="→", bg=SET_BG, fg=SET_MUT).pack(side="left", padx=8)
        e_val = tk.Entry(row, width=30, bg=SET_INSET, fg=SET_FG,
                         insertbackground=SET_FG, relief="flat")
        e_val.pack(side="left", ipady=4)

        listbox = tk.Listbox(body, height=8, bg=SET_INSET, fg=SET_FG,
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

        btns = tk.Frame(body, bg=SET_BG)
        btns.pack(fill="x", padx=16)
        tk.Button(btns, text="+ Ajouter", command=add_var, bg=SET_ACCENT,
                  fg=SET_WHITE, relief="flat", padx=12, pady=4).pack(side="left")
        tk.Button(btns, text="Supprimer la sélection", command=del_var,
                  bg=SET_DANGER_BG, fg=SET_DANGER_FG, relief="flat", padx=12,
                  pady=4).pack(side="left", padx=8)

        # — Personnalisation (palier Ultra) —
        def ultra_header(title, unlocked):
            row = tk.Frame(body, bg=SET_BG)
            row.pack(fill="x", anchor="w", padx=16, pady=(18, 5))
            tk.Label(row, text=title.upper(), bg=SET_BG, fg=SET_MUT,
                     font=("Segoe UI", 10, "bold")).pack(side="left")
            if not unlocked:
                tk.Label(row, text="NÉCESSITE NOVA ULTRA", bg="#332C46",
                         fg="#C9B6F0", font=("Segoe UI", 8, "bold"),
                         padx=7, pady=1).pack(side="left", padx=8)

        tk.Frame(body, bg=SET_LINE, height=1).pack(fill="x", padx=16, pady=12)
        can_orb = licensing.has("orb_customization")
        can_name = licensing.has("custom_naming")
        ultra_header("Personnalisation", can_orb or can_name)
        pcol = tk.Frame(body, bg=SET_BG)
        pcol.pack(fill="x", padx=16, pady=4)
        tk.Label(pcol, text="Couleur de l'orbe :", bg=SET_BG,
                 fg=SET_MUT).pack(side="left")
        e_color = tk.Entry(pcol, width=10, bg=SET_INSET, fg=SET_FG,
                           insertbackground=SET_FG, relief="flat")
        e_color.pack(side="left", padx=8, ipady=3)
        e_color.insert(0, core.CFG.get("orb_color", ""))
        pnam = tk.Frame(body, bg=SET_BG)
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
        b_perso = tk.Button(body, text="Enregistrer la personnalisation",
                            command=save_perso, bg=SET_ACCENT, fg=SET_WHITE,
                            relief="flat", padx=12, pady=4)
        b_perso.pack(anchor="w", padx=16, pady=(4, 0))
        _lock(can_orb, e_color)                 # verrou par fonctionnalité :
        _lock(can_name, e_name)                 # couleur et nom peuvent différer
        _lock(can_orb or can_name, b_perso)

        # — Modes sur mesure (palier Ultra) : selon l'app / l'onglet actif,
        #   appliquer SON prompt à la reformulation —
        tk.Frame(body, bg=SET_LINE, height=1).pack(fill="x", padx=16, pady=12)
        can_cm = licensing.has("custom_modes")
        ultra_header("Styles sur mesure", can_cm)
        tk.Label(body, text="Quand l'app ou l'onglet actif contient un de ces "
                 "mots, votre consigne reformule à votre façon.",
                 bg=SET_BG, fg=SET_MUT,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=16)

        cmrow = tk.Frame(body, bg=SET_BG)
        cmrow.pack(fill="x", padx=16, pady=(8, 2))
        e_cm_name = tk.Entry(cmrow, width=14, bg=SET_INSET, fg=SET_FG,
                             insertbackground=SET_FG, relief="flat")
        e_cm_name.pack(side="left", ipady=4)
        g_cm_name = _ph(e_cm_name, "Nom (ex. Jira)")
        e_cm_match = tk.Entry(cmrow, width=24, bg=SET_INSET, fg=SET_FG,
                              insertbackground=SET_FG, relief="flat")
        e_cm_match.pack(side="left", padx=8, ipady=4)
        g_cm_match = _ph(e_cm_match, "Mots-clés app/onglet (virgules)")
        t_cm_prompt = tk.Text(body, height=3, bg=SET_INSET, fg=SET_FG,
                              insertbackground=SET_FG, relief="flat",
                              font=("Segoe UI", 9), wrap="word")
        t_cm_prompt.pack(fill="x", padx=16, pady=4)

        cm_list = tk.Listbox(body, height=3, bg=SET_INSET, fg=SET_FG,
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

        cmb = tk.Frame(body, bg=SET_BG)
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
        sep = tk.Frame(body, bg=SET_LINE, height=1)
        sep.pack(fill="x", padx=16, pady=12)
        _seclabel("Moteur & dictée", top=0)
        eng = tk.Frame(body, bg=SET_BG)
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
            # patch minimal (seule la clé changée), cf. _toggle_cloud : évite
            # d'écraser un réglage de latence écrit en parallèle
            core.save_config({"stt": {"cloud_enabled": bool(cloud.get())}})
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

        # reformulation locale : état + installation en un clic (parité avec la
        # rangée « Reformulation hors ligne » du dock — règle CLAUDE.md).
        # Défensif de bout en bout : un échec d'import ou de sondage ne doit
        # jamais casser le reste de la fenêtre de réglages.
        try:
            import engine_setup as _es
            eng_row = tk.Frame(eng, bg=SET_BG)
            eng_row.pack(anchor="w", pady=(2, 0))
            eng_lbl = tk.Label(eng_row, text="Reformulation hors ligne : …",
                               bg=SET_BG, fg=SET_MUT)
            eng_lbl.pack(side="left")
            eng_btn = tk.Button(eng_row, text="Installer (≈ 2,5 Go)",
                                bg=SET_INSET, fg=SET_FG, relief="flat",
                                activebackground=SET_INSET,
                                activeforeground=SET_FG)
            # AUCUN appel tkinter depuis un fil de fond : le sondage HTTP (état
            # au repos, ≤1,5 s) tourne en fil de fond et dépose son résultat
            # dans une boîte ; la boucle after() du fil UI consomme la boîte.
            # Pendant une installation, snapshot() (simple dict, zéro HTTP)
            # suffit — le fil UI boucle directement dessus.
            _eng_box = []

            def _eng_probe():
                try:
                    _eng_box.append(_es.status())
                except Exception:
                    pass

            def _eng_apply(st):
                if st.get("ready"):
                    eng_lbl.config(fg=SET_OK,
                                   text="Reformulation hors ligne : prête")
                    eng_btn.pack_forget()
                elif st["phase"] in ("download", "install", "service", "model"):
                    pct = int((st.get("progress") or 0) * 100)
                    eng_lbl.config(fg=SET_MUT, text={
                        "download": "Téléchargement…",
                        "install": "Installation…",
                        "service": "Démarrage…",
                        "model": "Préparation de l'intelligence…",
                    }[st["phase"]] + f" {pct} %")
                    eng_btn.pack_forget()
                    win.after(1200, _eng_tick)
                else:
                    eng_lbl.config(fg=SET_MUT,
                                   text="Reformulation hors ligne : "
                                   + (st.get("error") or "non installée"))
                    eng_btn.pack(side="left", padx=(8, 0))

            def _eng_tick():
                try:
                    if not eng_lbl.winfo_exists():
                        return
                    snap = _es.snapshot()
                    if snap["phase"] in ("download", "install",
                                         "service", "model"):
                        snap["ready"] = False
                        _eng_apply(snap)             # zéro HTTP : direct
                    elif _eng_box:
                        _eng_apply(_eng_box.pop())   # résultat du sondage
                    else:
                        threading.Thread(target=_eng_probe,
                                         daemon=True).start()
                        win.after(700, _eng_tick)
                except Exception:
                    pass

            def _eng_install():
                _es.start()
                win.after(300, _eng_tick)
            eng_btn.config(command=_eng_install)
            _eng_tick()
        except Exception as e:
            core.log_err("engine_setup_tk", e)

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
        prof = tk.Frame(body, bg=SET_BG)
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

        kb = tk.Frame(body, bg=SET_BG)
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

        # langue de dictée (parité avec le paneLang du dock — règle CLAUDE.md :
        # toute option existe dans les DEUX écrans ; le tray n'a plus de
        # sous-menu Langue, cet écran de repli doit donc l'offrir)
        lgf = tk.Frame(body, bg=SET_BG)
        lgf.pack(fill="x", padx=16, pady=(0, 4))
        tk.Label(lgf, text="Langue de dictée :", bg=SET_BG,
                 fg=SET_FG).pack(side="left")
        _langs = list(core.LANGUAGES)          # source unique (dock + tkinter)
        _lang_by_label = {lbl: c for c, lbl in _langs}
        cur_code = core.CFG.get("language", "fr")
        lang_var = tk.StringVar(
            value=next((lbl for c, lbl in _langs if c == cur_code),
                       _langs[0][1]))
        lang_menu = tk.OptionMenu(
            lgf, lang_var, *[lbl for _c, lbl in _langs],
            command=lambda lbl: _set_language(_lang_by_label.get(lbl, "fr")))
        lang_menu.configure(bg=SET_INSET, fg=SET_FG, relief="flat", bd=0,
                            activebackground=SET_INSET,
                            activeforeground=SET_FG, highlightthickness=0)
        try:
            lang_menu["menu"].configure(bg=SET_INSET, fg=SET_FG)
        except Exception:
            pass
        lang_menu.pack(side="left", padx=8)

        # raccourcis clavier : un par Style + ouverture du menu des Styles.
        # Pendant du groupe « Raccourcis clavier » du dock web (parité imposée
        # par CLAUDE.md) — champs texte simples, ex. « ctrl+alt+e », vide = off.
        hkf = tk.Frame(body, bg=SET_BG)
        hkf.pack(fill="x", padx=16, pady=(4, 0))
        tk.Label(hkf, text="Raccourcis clavier (ex. ctrl+alt+e — vide = aucun)",
                 bg=SET_BG, fg=SET_MUT, font=("Segoe UI", 8)).grid(
                     row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))
        hk_entries = {}
        hk_cfg = core.CFG.get("mode_hotkeys") or {}
        # seuls les Styles du palier (même règle que le dock) : un raccourci
        # vers un Style verrouillé ne pourrait jamais fonctionner ; palier
        # calculé une fois (une vérification de signature par appel sinon)
        _tier = licensing.current_tier()
        rows = [("__menu__", "Ouvrir le menu des Styles"),
                ("__settings__", "Ouvrir les Réglages")] + \
               [(m["id"], m["label"]) for m in modes_registry.all_modes()
                if licensing.mode_allowed(m["id"], _tier)]
        for i, (mid, label) in enumerate(rows, start=1):
            tk.Label(hkf, text=label, bg=SET_BG, fg=SET_MUT, width=24,
                     anchor="w").grid(row=i, column=0, sticky="w", pady=1)
            e = tk.Entry(hkf, width=14, bg=SET_INSET, fg=SET_FG,
                         insertbackground=SET_FG, relief="flat")
            e.insert(0, core.CFG.get("menu_hotkey", "") if mid == "__menu__"
                     else core.CFG.get("settings_hotkey", "")
                     if mid == "__settings__" else hk_cfg.get(mid, ""))
            e.grid(row=i, column=1, sticky="w", ipady=2, pady=1)
            hk_entries[mid] = e

        def save_hotkeys():
            vals = {m: e.get().strip().lower() for m, e in hk_entries.items()}
            menu_k = vals.pop("__menu__", "")
            sett_k = vals.pop("__settings__", "")
            # dictionnaire COMPLET : save_config le remplace tel quel (c'est ce
            # qui rend la suppression d'un raccourci possible — la fusion
            # récursive, elle, ne supprime jamais). Les Styles hors palier,
            # absents de cet écran, sont préservés tels quels.
            hk = {m: k for m, k in (core.CFG.get("mode_hotkeys") or {}).items()
                  if m not in vals}
            hk.update({m: k for m, k in vals.items() if k})
            core.save_config({"menu_hotkey": menu_k,
                              "settings_hotkey": sett_k,
                              "mode_hotkeys": hk})
            _rebind_style_hotkeys()
        tk.Button(hkf, text="Appliquer les raccourcis", command=save_hotkeys,
                  bg=SET_ACCENT, fg=SET_WHITE, relief="flat", padx=10,
                  pady=3).grid(row=len(rows) + 1, column=0, sticky="w",
                               pady=(4, 0))

        # Vitesse de transcription (parité avec le dock — mêmes options)
        seps = tk.Frame(body, bg=SET_LINE, height=1)
        seps.pack(fill="x", padx=16, pady=12)
        _seclabel("Vitesse de transcription", top=2)
        _o = _stt_opts()                  # même source que le dock
        v_live = tk.BooleanVar(value=_o["live"])
        v_warm = tk.BooleanVar(value=_o["keep_warm_on"])
        v_prec = tk.BooleanVar(value=_o["precision_max"])
        v_qual = tk.BooleanVar(value=_o["quality_max"])
        v_inst = tk.BooleanVar(value=_o["instant_normal"])

        def save_stt():
            # même logique que le dock (_apply_stt_opts) : fusion, synchro du
            # modèle et pré-téléchargement — aucune dérive entre les écrans.
            opts = {"live": v_live.get(), "precision_max": v_prec.get(),
                    "instant_normal": v_inst.get()}
            # « Qualité maximale » : n'est renvoyée QUE si la machine la
            # supporte (case active). Sinon la case est grisée et sa valeur
            # masquée à False : la renvoyer inconditionnellement écraserait un
            # quality_max=true importé d'une machine ≥12 Go — le dock, lui, ne
            # touche jamais cette clé sur un PC non supporté. On préserve donc
            # la préférence de l'utilisateur, comme le dock.
            if _o["quality_supported"]:      # même source que le dock (payload state)
                opts["quality_max"] = v_qual.get()
            # keep_warm « auto » (résolu selon la RAM et le modèle) : épinglé
            # en booléen SEULEMENT si cette case diffère de l'état résolu —
            # sinon cocher n'importe quelle AUTRE case figeait l'automatisme
            # pour toujours (aucun chemin UI ne sait revenir à « auto »)
            if v_warm.get() != core.stt_keep_warm():   # = keep_warm_on, sans rebâtir le dict
                opts["keep_warm"] = v_warm.get()
            _apply_stt_opts(opts)
        sf = tk.Frame(body, bg=SET_BG)
        sf.pack(fill="x", padx=16, pady=4)
        # « Qualité maximale » grisée si la machine ne peut pas tenir le grand
        # moteur (~12 Go) — même gating que le dock, parité CLAUDE.md.
        q_ok = _o["quality_supported"]        # même source que le dock (payload state)
        for var, label, dis in (
                (v_live, "Pendant la dictée (recommandé)", False),
                (v_warm, "Moteur gardé en mémoire (~0,7 Go de RAM)", False),
                (v_prec, "Précision maximale (3-5× plus lent sur processeur)", False),
                (v_qual, "Qualité maximale (~1,5 Go, nécessite ~12 Go de RAM)",
                 not q_ok),
                (v_inst, "Collage éclair pour le Style Normal (sans IA)", False)):
            tk.Checkbutton(sf, text=label, variable=var, command=save_stt,
                           state=("disabled" if dis else "normal"),
                           bg=SET_BG, fg=SET_FG, selectcolor=SET_INSET,
                           disabledforeground=SET_MUT,
                           activebackground=SET_BG, activeforeground=SET_FG,
                           anchor="w").pack(anchor="w")

        # Mes infos : champs de profil réutilisés par « mon adresse », « mon
        # e-mail »… dans le texte dicté (surtout le mode E-mail). 100 % local.
        sep2 = tk.Frame(body, bg=SET_LINE, height=1)
        sep2.pack(fill="x", padx=16, pady=12)
        _seclabel("Mes infos", top=2)
        info = core.personal_info()
        # clés = source unique storage.PERSONAL_FIELDS (jamais de dérive avec le
        # stockage) ; libellés propres à l'UI
        labels = {"prenom": "Prénom", "nom": "Nom", "email": "E-mail",
                  "telephone": "Téléphone", "adresse": "Adresse"}
        fields = [(k, labels.get(k, k)) for k in storage.PERSONAL_FIELDS]
        entries = {}
        me = tk.Frame(body, bg=SET_BG)
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
        xf = tk.Frame(body, bg=SET_BG)
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
        tk.Button(body, text="Ajouter une information", command=add_extra,
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
        tk.Button(body, text="Enregistrer mes infos", command=save_me,
                  bg=SET_ACCENT, fg=SET_WHITE, relief="flat", padx=12,
                  pady=4).pack(anchor="w", padx=16, pady=(4, 0))

        refresh()


# ================================================= dock web (organique, option)
DOCK_HTML = core.resource_path(os.path.join("ui", "dock.html"))


def _dock_html():
    """Contenu de dock.html chargé EN MÉMOIRE, injecté tel quel dans la webview
    (paramètre `html=`) au lieu de pointer la fenêtre sur un fichier. Le serveur
    interne de pywebview résolvait « /ui/dock.html » relativement à un dossier
    courant qui, selon l'installation (exe vs _internal PyInstaller 6), pouvait
    ne pas contenir ui/ → page « 404 Not Found » au démarrage. En passant le HTML
    directement, AUCUN serveur ni chemin n'intervient : le 404 est IMPOSSIBLE.
    dock.html est autonome (CSS/JS/SVG inline, aucune ressource externe ni requête
    réseau) — vérifié : le rendu est identique à un chargement par fichier."""
    with open(DOCK_HTML, "r", encoding="utf-8") as f:
        return f.read()


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
    TRAYMENU = (290, 240)      # menu Nova du tray (4 rangées + séparateur)
    # Couleur de REPLI de la fenêtre (background_color) : la transparence réelle
    # est assurée par WebView2 (transparent=True) + fond de page alpha 0. Cette
    # teinte quasi-noire ne se voit QUE si un très vieux runtime WebView2
    # ignorait l'alpha — au pire un rectangle sombre (comme avant), jamais pire.
    # La page dock.html peint « transparent », pas cette valeur.
    KEY = "#0F1014"

    def __init__(self):
        if not os.path.isfile(DOCK_HTML):   # exe incomplet → repli pilule,
            raise RuntimeError("dock.html introuvable")   # jamais de 404
        self._win = None
        self._lvl_n = 0
        self._panel = "compact"
        self._hwnd = None
        self._shown = False
        self._got_shape = False
        self._last_shape_n = 0     # n° de la dernière forme appliquée (dédup)
        self._shape_epoch = 0      # id du CHARGEMENT de page courant : à chaque
                                   # reload WebView2 le compteur JS repart de 0,
                                   # l'epoch change → on remet _last_shape_n à 0
        self._shape_lock = threading.Lock()   # poste js_api ‖ watchdog :
                                              # jamais entrelacés (régression)
        self._push_ok = False      # un poste js_api est arrivé : pont prouvé
        # pont Python→JS NON bloquant : evaluate_js est un aller-retour SYNCHRONE
        # vers le fil UI (il PEND si le rendu rame/gèle). On empile et un fil
        # dédié draine → les fils AUDIO (level, ~30×/s) et CLAVIER (raccourcis)
        # ne bloquent JAMAIS sur l'UI. novaLevel est coalescé (seule la dernière
        # valeur compte) ; file bornée (anti-fuite si l'UI est wedgée).
        self._js_q = collections.deque()
        self._js_lock = threading.Lock()
        self._js_evt = threading.Event()
        self._js_pump_on = False

    # ---- API compatible Pill ----
    def show(self, state, text="", sub=""):
        # « Invisible au repos » a pu masquer la fenêtre native (SW_HIDE dans
        # _apply_shape_locked). Or une fenêtre WebView2 cachée SUSPEND son
        # rendu (requestAnimationFrame gelé) : le reportShape déclenché par
        # novaShow ne partirait jamais et la bulle ne réapparaîtrait PLUS.
        # On rallume donc côté Python AVANT de déléguer au JS — le rendu
        # repart, la forme est re-postée, la bulle revient toujours.
        self._ensure_native_visible()
        if self._panel == "traymenu":
            # menu tray abandonné (fermé côté JS sans que l'appel `panel` ne
            # soit revenu, pont muet…) : la dictée reprend la géométrie
            # normale SANS dépendre du pont — sinon la bulle resterait coincée
            # dans une fenêtre 290×240 au coin de l'écran
            self._set_panel("compact")
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
        self._ensure_native_visible()   # sinon réglages invisibles après ghost
        self._set_panel("settings")
        self._js("__openSettings")

    def open_modes(self):
        """Ouvre le menu déroulant des Styles du dock (raccourci clavier).
        Le clic simulé côté JS passe par le protocole `panel` habituel, qui
        redimensionne la fenêtre — un seul mécanisme."""
        self._ensure_native_visible()   # même piège que show() en mode ghost
        self._js("window.novaOpenModes")

    def open_tray_menu(self):
        """Menu Nova stylé ouvert depuis l'icône du tray — porte les actions du
        quotidien avec le langage visuel du dock ; le menu natif Windows
        (impossible à styler) est réduit au strict secours dans _build_tray.
        Réglages déjà ouverts → on les garde (les écraser en 290×240 rendrait
        la fenêtre inutilisable, le menu resterait invisible dessous)."""
        self._ensure_native_visible()
        if self._panel.startswith("settings"):
            return
        self._set_panel("traymenu")
        self._js("window.novaOpenTray")

    def _ensure_native_visible(self):
        """Ré-affiche la fenêtre native SANS voler le focus (SW_SHOWNOACTIVATE,
        idempotent si déjà visible). Indispensable après le SW_HIDE du mode
        « invisible au repos » : cachée, la fenêtre WebView2 gèle son rendu et
        le JS ne peut plus rapporter de forme — seul Python peut la rallumer.
        La région précédente (dernière forme non vide) reste appliquée le temps
        que reportShape re-découpe : jamais de rectangle nu."""
        try:
            hwnd = self._get_hwnd()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
        except Exception:
            pass

    # ---- pont Python → JS ----
    def _js(self, fn, *args):
        # NON bloquant : on empile et le fil pousseur draine (voir __init__).
        # JAMAIS d'evaluate_js synchrone ici — un appelant sur le fil audio ou
        # clavier gèlerait la dictée/les raccourcis si l'UI rame.
        if self._win is None:
            return
        with self._js_lock:
            if fn == "window.novaLevel":          # coalescing : un seul, le dernier
                self._js_q = collections.deque(
                    q for q in self._js_q if q[0] != "window.novaLevel")
            if len(self._js_q) > 200:             # garde-fou anti-fuite (UI wedgée)
                self._js_q.clear()
            self._js_q.append((fn, args))
            if not self._js_pump_on:
                self._js_pump_on = True
                threading.Thread(target=self._js_pump, daemon=True,
                                 name="js-pump").start()
        self._js_evt.set()

    def _js_pump(self):
        """Draine la file des appels JS : le SEUL endroit qui appelle evaluate_js
        (aller-retour synchrone vers le fil UI). S'il pend, seul CE fil attend —
        jamais l'audio ni le clavier ; la file coalescée/bornée ne fuit pas."""
        while True:
            self._js_evt.wait()
            self._js_evt.clear()
            while True:
                with self._js_lock:
                    if not self._js_q:
                        break
                    fn, args = self._js_q.popleft()
                try:
                    payload = ",".join(json.dumps(a) for a in args)
                    win = self._win
                    if win is not None:
                        win.evaluate_js(f"{fn}({payload})")
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
        elif name == "traymenu":
            # près de la zone de notification : coin de la zone de TRAVAIL
            # (SPI_GETWORKAREA suit la barre des tâches quel que soit son bord
            # ou sa hauteur) — repli plein écran avec marge fixe sinon
            try:
                import ctypes.wintypes as wt
                rcw = wt.RECT()
                ctypes.windll.user32.SystemParametersInfoW(
                    0x30, 0, ctypes.byref(rcw), 0)            # SPI_GETWORKAREA
                x, y = rcw.right - w - 12, rcw.bottom - h - 12
            except Exception:
                x, y = sw - w - 12, sh - h - 52
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
            # native.Handle peut être la VUE WebView2 (fenêtre ENFANT hébergée
            # en mode fenêtré), pas la Form frameless de plus haut niveau :
            # SetWindowRgn sur l'enfant découpe le contenu mais laisse la
            # fenêtre-hôte en rectangle opaque à fond BLANC tout autour — le
            # « carré blanc ». On remonte à la racine top-level (GA_ROOT) ;
            # no-op strict si hwnd est déjà le sommet (repli FindWindowW, ou
            # versions pywebview où Handle est déjà la Form).
            try:
                root = ctypes.windll.user32.GetAncestor(hwnd, 2)  # GA_ROOT
                if root:
                    hwnd = int(root)
            except Exception:
                pass
            self._hwnd = hwnd
            try:  # tray uniquement : ni barre des tâches, ni Alt-Tab
                u = ctypes.windll.user32
                GWL_EXSTYLE, TOOL, APPWIN = -20, 0x00000080, 0x00040000
                st = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
                u.SetWindowLongW(hwnd, GWL_EXSTYLE, (st | TOOL) & ~APPWIN)
            except Exception as e:
                core.log_err("dock_exstyle", e)
            # applique NOACTIVATE (+ opacité utilisateur éventuelle) dès la 1re
            # acquisition (self._hwnd déjà mémorisé → pas de récursion)
            self._apply_opacity()
        return self._hwnd

    def apply_shape(self, payload):
        """Découpe la fenêtre aux formes visibles rapportées par le JS
        ({vw, vh, shapes:[{x,y,w,h,r}]} en px CSS). L'échelle réelle est
        mesurée (client Win32 ÷ viewport JS) → correct quel que soit le DPI.
        Tout ce qui est hors région n'existe pas : pas de fond blanc, pas de
        zone cliquable fantôme. À la première forme, la fenêtre (créée cachée)
        est révélée — l'utilisateur ne voit jamais le rectangle nu."""
        try:
            with self._shape_lock:
                self._apply_shape_locked(payload)
        except Exception as e:
            core.log_err("dock_shape", e)
        # PAS de self._reveal() ici : sur le chemin de succès, _apply_shape_locked
        # révèle la fenêtre DÉCOUPÉE lui-même (ShowWindow). Appeler _reveal()
        # inconditionnellement révélait la fenêtre NON découpée (carré sombre)
        # quand _apply_shape_locked sortait tôt sur « if not hwnd » (handle
        # WebView2 pas encore résolu au démarrage, sans poser _got_shape) — le
        # flash de rectangle nu que l'architecture doit empêcher. Le secours
        # « page cassée » reste porté par le Timer 10 s (voir serve()).

    def _apply_shape_locked(self, payload):
        n = int(payload.get("n") or 0)
        ep = int(payload.get("epoch") or 0)
        # nouveau CHARGEMENT de page (reload WebView2 après crash du renderer,
        # re-navigation) : le compteur JS __shapeN repart de 0, l'epoch change.
        # Sans ce reset, la garde monotone rejetait toutes les formes du
        # nouveau document (n=1,2,3 ≤ ancien 50) → région figée pour toujours.
        if ep and ep != self._shape_epoch:
            self._shape_epoch = ep
            self._last_shape_n = 0
        # garde MONOTONE (pas une simple égalité) : DANS un même chargement, le
        # poste js_api et le watchdog arrivent par des fils différents — sans
        # elle, une forme PÉRIMÉE lue avant un poste plus récent pouvait être
        # appliquée après lui et faire régresser la région (retour du « carré »)
        if n and n <= self._last_shape_n:
            return
        hwnd = self._get_hwnd()
        if not hwnd:
            return
        import ctypes.wintypes as wt
        u, g = ctypes.windll.user32, ctypes.windll.gdi32
        shapes = payload.get("shapes") or []
        if not shapes:
            # rien à montrer : en mode « invisible au repos », la fenêtre
            # disparaît complètement (SW_HIDE) — silencieuse, sans jamais
            # rien ouvrir dans la barre des tâches
            if n:
                self._last_shape_n = n
            # SW_HIDE uniquement AU REPOS (panneau compact) : pendant qu'un
            # panneau piloté par Python s'ouvre (menu tray…), un rapport de
            # formes vides transitoire (resize AVANT que le JS n'affiche le
            # panneau) cachait la fenêtre — et une WebView2 cachée gèle son
            # rendu, donc plus aucun rapport ne venait la réveiller
            if core.CFG.get("dock_ghost") and self._panel == "compact":
                u.ShowWindow(hwnd, 0)                     # SW_HIDE
            return
        rc = wt.RECT()
        u.GetClientRect(hwnd, ctypes.byref(rc))
        vw, vh = float(payload.get("vw") or 0), float(payload.get("vh") or 0)
        if not (rc.right and rc.bottom and vw and vh):
            return      # fenêtre pas encore mesurable : n n'est PAS consommé —
                        # le watchdog ré-appliquera cette même forme plus tard
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
        if n:
            self._last_shape_n = n      # consommé une fois RÉELLEMENT appliquée
        self._shown = True
        # _got_shape UNIQUEMENT sur une forme NON VIDE réellement affichée : un
        # rapport vide (page cassée sans rendu, hors mode ghost) ne doit PAS
        # inhiber le secours _reveal — sinon la fenêtre ne serait jamais montrée
        self._got_shape = True

    def _reveal(self):
        """Secours : la fenêtre a été créée cachée pour éviter tout flash au
        démarrage. Si le JS n'a jamais rapporté de forme (démarrage WebView2 très
        lent après mise à jour, ou page cassée), on la RÉVÈLE quand même — mais
        elle est TRANSPARENTE (transparent=True), donc la montrer n'affiche RIEN
        tant que la page n'a pas peint : jamais de rectangle nu. Dès que la page
        peint (même tardivement), la bulle apparaît. NE force PLUS aucune opacité
        ni clé de couleur (c'était le bug qui rendait le « carré » permanent sur
        un démarrage lent). En mode « invisible au repos », on ne montre rien :
        la fenêtre reste masquée jusqu'à la 1re dictée."""
        if self._shown or self._got_shape:
            return
        if core.CFG.get("dock_ghost"):
            return
        self._shown = True
        try:
            self._win.show()
        except Exception:
            pass

    def _apply_opacity(self):
        """Transparence RÉELLE via WebView2 (transparent=True) : le fond de la
        page est alpha 0, donc PLUS de « carré » autour de la bulle sur aucune
        machine — la clé de couleur ET la découpe par région ne fonctionnent PAS
        avec la vue WebView2 (composée par DirectComposition, elle les ignore).
        On ne gère donc plus ici que : (1) WS_EX_NOACTIVATE — la bulle ne prend
        jamais le focus, sauf les réglages qui doivent recevoir le clavier ;
        (2) l'opacité utilisateur, appliquée UNIFORMÉMENT et seulement si < 1
        (à 1.0 on ne touche PAS au layering, la transparence WebView2 reste seule
        maîtresse : aucune interférence, aucun trou cliquable)."""
        try:
            hwnd = self._get_hwnd()
            if not hwnd:
                return
            u = ctypes.windll.user32
            GWL_EXSTYLE, LAYERED, NOACT, LWA_ALPHA = -20, 0x00080000, 0x08000000, 0x2
            settings = self._panel.startswith("settings")
            st = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
            # NOACTIVATE partout SAUF réglages (leurs champs reçoivent le clavier)
            st = (st & ~NOACT) if settings else (st | NOACT)
            u.SetWindowLongW(hwnd, GWL_EXSTYLE, st)
            op = float(core.CFG.get("dock_opacity", 1.0) or 1.0)
            if not settings and op < 0.999:
                # opacité utilisateur : alpha uniforme (les zones alpha 0 restent
                # invisibles, la bulle devient plus translucide)
                u.SetWindowLongW(hwnd, GWL_EXSTYLE, st | LAYERED)
                u.SetLayeredWindowAttributes(hwnd, 0, int(max(0.55, op) * 255),
                                             LWA_ALPHA)
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
        # Fenêtre TRANSPARENTE (transparent=True) : WebView2 compose son fond en
        # alpha 0 → aucun « carré/rectangle » autour de la bulle, sur TOUTES les
        # machines. C'est la seule transparence qui marche avec WebView2 (sa vue
        # DirectComposition ignore la clé de couleur et la découpe par région de
        # la fenêtre hôte — les deux échouaient sur la machine de l'utilisateur).
        # Créée
        # CACHÉE pour éviter tout flash au démarrage ; apply_shape révèle à la
        # 1re forme, sinon _reveal la montre après 15 s (jamais d'app invisible).
        # background_color sombre = repli si un très vieux runtime ignorait
        # l'alpha (au pire un rectangle sombre, comme avant — jamais pire).
        # focus=False : la bulle ne vole JAMAIS le focus clavier — la fenêtre
        # active reste celle de l'utilisateur (détection auto + collage fiables)
        self._win = webview.create_window(
            "NovaDock", html=_dock_html(), width=w, height=h, x=x, y=y,
            frameless=True, easy_drag=False, on_top=True, hidden=True,
            focus=False, transparent=True, background_color=self.KEY,
            resizable=False, js_api=DockApi(self))
        # 15 s : après une mise à jour, le premier démarrage de WebView2 peut
        # dépasser 10 s (démarrage à froid) — la fenêtre étant transparente, la
        # montrer n'affiche RIEN tant que la page n'a pas peint (pas de rectangle
        # nu) ; dès que la page peint, la bulle apparaît.
        threading.Timer(15.0, self._reveal).start()
        threading.Thread(target=self._shape_watchdog, daemon=True).start()
        # détecteur de GEL : si le fil principal (webview.start, ci-dessous) se
        # bloque, la page ne peut plus battre → le watchdog vide les piles dans
        # nova-crash.log (un « ne répond pas » n'est ni exception ni plantage,
        # donc rien n'atterrissait dans les journaux jusqu'ici)
        core.install_freeze_watchdog()
        webview.start()

    def _shape_watchdog(self):
        """Canal de secours du détourage. Le chemin normal est le POSTE : le JS
        appelle api('shape') via le pont js_api. Sur certaines machines ce pont
        ne s'injecte pas (course WebView2) — l'interface vivait mais la fenêtre
        restait un rectangle nu (« carré noir »). Ici Python vient RELIRE les
        formes lui-même par evaluate_js (sens Python→JS→retour, indépendant du
        pont). Sonde légère (le seul compteur), paquet complet uniquement s'il
        a changé ; et dès qu'UN poste arrive (_push_ok), le pont est prouvé sur
        cette machine — la boucle s'arrête, le régime de croisière n'a qu'un
        seul chemin."""
        sig_prev = None
        while not self._push_ok:
            time.sleep(0.4)
            w = self._win
            if w is None:
                continue
            try:
                # signature légère (epoch/n) : ne relit le paquet complet que
                # s'il a changé. L'epoch fait repérer un reload de page (n
                # repart de 0) — _apply_shape_locked remet alors le compteur à
                # zéro, sinon la garde monotone bloquerait le nouveau document.
                sig = w.evaluate_js(
                    "(function(s){s=window.__novaShapes;"
                    "return s?((s.epoch||0)+'/'+s.n):'';})()")
                if not sig or sig == sig_prev:
                    continue
                sig_prev = sig
                payload = json.loads(
                    w.evaluate_js("JSON.stringify(window.__novaShapes)"))
                self.apply_shape(payload)
            except Exception:
                pass                    # page pas encore prête / en fermeture

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


def _stt_opts():
    """Options de latence de la transcription (lecture) — source unique pour
    le dock ET l'écran tkinter. `keep_warm_on` est résolu ici : le JS ne peut
    pas connaître la RAM de la machine."""
    stt = core.CFG.get("stt") or {}
    q_ok = core.quality_max_supported()
    return {"live": stt.get("live", True) is not False,
            "keep_warm_on": core.stt_keep_warm(),
            "precision_max": bool(stt.get("precision_max")),
            # affiché = état EN EFFET : sur une machine qui ne peut pas tenir le
            # grand moteur, quality_max est ignoré par le moteur
            # (effective_stt_model re-vérifie la RAM) → l'UI le montre OFF. Sinon
            # un quality_max=true persisté PUIS une RAM devenue insuffisante
            # (import de config d'une machine ≥12 Go, psutil en échec →
            # _ram_total_gb=0) laissait l'interrupteur « ON + grisé + inerte »,
            # sans aucun moyen de le désactiver depuis les deux écrans.
            "quality_max": bool(stt.get("quality_max")) and q_ok,
            # résolu ici (comme keep_warm_on) : le JS ne connaît pas la RAM.
            # Faux → l'interrupteur « Qualité maximale » est grisé EN AMONT
            # (règle CLAUDE.md « griser les contrôles ») au lieu de basculer
            # puis se rétracter ; le refus synchrone de _apply_stt_opts reste
            # le filet défensif si un état d'UI périmé le rappelait quand même.
            "quality_supported": q_ok,
            "instant_normal": bool(core.CFG.get("instant_normal"))}


_stt_opts_lock = threading.Lock()   # deux bascules rapprochées (pont js_api =
                                    # un fil par appel) : pas d'écrasement RMW


def _apply_stt_opts(opts):
    """Options de latence (écriture) — logique UNIQUE pour les deux écrans :
    fusion, synchronisation du modèle, et pré-téléchargement du grand moteur
    en arrière-plan quand « qualité maximale » vient d'être activée (pour que
    la prochaine dictée n'attende pas ~1,5 Go)."""
    opts = opts or {}
    refused_quality = False
    with _stt_opts_lock:
        was_max = bool((core.CFG.get("stt") or {}).get("quality_max"))
        # patch MINIMAL : UNIQUEMENT les clés que cet écran gère. Ne jamais
        # ré-écrire tout le sous-dict stt — sinon un basculement Turbo
        # (cloud_enabled) simultané, écrit par _toggle_cloud sur un autre fil,
        # serait ré-écrasé par une copie périmée (lost update inter-appels).
        stt_patch = {}
        for k in ("live", "keep_warm", "precision_max", "quality_max"):
            if k in opts:
                stt_patch[k] = bool(opts[k])
        want_max = stt_patch.get("quality_max", was_max)
        # « Qualité maximale » demandée sur une machine qui ne peut pas tenir le
        # grand moteur (~1,5 Go + LLM) : refus SYNCHRONE et honnête plutôt que
        # de cocher la case, ne rien relever, puis annoncer « moteur amélioré
        # prêt » (l'UI mentait). La case revient à False, reflétée au retour.
        if want_max and not was_max and not core.quality_max_supported():
            stt_patch["quality_max"] = False
            want_max = False
            refused_quality = True
        patch = {"stt": stt_patch} if stt_patch else {}
        if "instant_normal" in opts:  # option de reformulation, hors bloc stt
            patch["instant_normal"] = bool(opts["instant_normal"])
        if patch:
            core.save_config(patch)
    if refused_quality:
        pill.show("error", "Mémoire insuffisante",
                  "Le moteur amélioré demande environ 12 Go de mémoire")
        pill.hide(2.8)
        return _stt_opts()
    if want_max != was_max:
        # JAMAIS sur le fil d'appel (pont js_api ou fenêtre tkinter) : la
        # synchro et le déchargement attendent le verrou du modèle, qu'un
        # chargement en cours peut tenir longtemps — l'interrupteur doit
        # répondre tout de suite, le travail lourd part en arrière-plan
        def _sync():
            core.sync_stt_model()
            if want_max:
                _preload_stt()
        threading.Thread(target=_sync, daemon=True).start()
    return _stt_opts()


def _preload_stt():
    """Télécharge/charge le moteur choisi tout de suite (feedback bulle),
    plutôt que de faire attendre la première dictée. Best-effort. Le
    téléchargement se fait HORS verrou modèle (il peut durer des minutes) :
    dictée et réglages restent réactifs pendant ce temps."""
    try:
        pill.show("thinking", "Préparation du moteur amélioré…",
                  "téléchargement unique — environ 1,5 Go")
        core.download_stt_model()
        core.get_model()
        pill.show("ok", "Moteur amélioré prêt")
        pill.hide(2.0)
    except Exception as e:
        core.log_err("stt_preload", e)
        pill.show("error", "Téléchargement du moteur impossible",
                  "réessaiera à la prochaine dictée")
        pill.hide(2.6)


class DockApi:
    """Pont JS → Python du dock. Chaque méthode réutilise EXACTEMENT la logique
    du tray / des Réglables tkinter (aucune règle de configuration dupliquée)."""

    def __init__(self, dock):
        self._dock = dock

    def state(self):
        hw = power_profiles.detect_hardware()
        # palier et libellé de verrou calculés UNE fois (licences actives :
        # chaque vérification sans tier explicite referait une signature
        # Ed25519 complète) ; le libellé vient d'ici, pas du JS — il suit le
        # palier réellement requis (FEATURES) si l'offre change
        tier = licensing.current_tier()
        lock = _mode_lock_label()
        modes = []
        for m in modes_registry.all_modes():
            ok = licensing.mode_allowed(m["id"], tier)
            modes.append({"id": m["id"], "label": m["label"],
                          "hotkey": m["hotkey"], "allowed": ok,
                          "lock": "" if ok else lock})
        return {
            "modes": modes,
            "profiles": power_profiles.evaluate(hw, _profiles_paid()),
            "hardware": hw,
            "languages": [{"code": c, "label": lbl} for c, lbl in core.LANGUAGES],
            "mode": STATE.get("mode", modes_registry.DEFAULT_MODE_ID),
            "profile": STATE.get("profile", power_profiles.DEFAULT_ID),
            "ptt_key": core.CFG.get("ptt_key", "f9"),
            "stt_opts": _stt_opts(),
            "mode_hotkeys": core.CFG.get("mode_hotkeys") or {},
            "menu_hotkey": core.CFG.get("menu_hotkey", ""),
            "settings_hotkey": core.CFG.get("settings_hotkey", ""),
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

    def heartbeat(self):
        """Battement du fil UI (~1×/s depuis dock.html). Ce message n'est reçu
        que si la boucle de messages du fil principal pompe → prouve que l'UI
        n'est pas gelée. Le détecteur de gel (core) s'en sert pour vider les
        piles si les battements s'arrêtent. Volontairement minimal."""
        core.heartbeat()

    def engine_setup_status(self):
        """État de la reformulation locale (prête / absente / installation en
        cours avec progression) — consommé par le panneau Général du dock."""
        import engine_setup
        return engine_setup.status()

    def engine_setup_start(self):
        """Bouton « Installer » des Réglages — idempotent, tout en fond."""
        import engine_setup
        return engine_setup.start()

    def shape(self, payload):
        """Formes réellement visibles (px CSS) → région native de la fenêtre.
        Un poste reçu = pont js_api prouvé : le chien de garde peut s'arrêter."""
        self._dock._push_ok = True
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

    def set_stt_opts(self, opts):
        return _apply_stt_opts(opts)

    def set_mode_hotkey(self, mode_id, key):
        """Raccourci direct d'un Style ; clé vide = suppression du raccourci."""
        hk = dict(core.CFG.get("mode_hotkeys") or {})
        key = (key or "").strip().lower()
        if key and not licensing.mode_allowed(str(mode_id)):
            return hk        # Style verrouillé : un raccourci ne marcherait jamais
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

    def set_settings_hotkey(self, key):
        """Raccourci qui ouvre la fenêtre Réglages ; vide = désactivé."""
        core.save_config({"settings_hotkey": (key or "").strip().lower()})
        _rebind_style_hotkeys()
        return core.CFG.get("settings_hotkey", "")

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


def _webview2_runtime_present():
    """Le MODULE pywebview s'importe toujours ; mais le RUNTIME WebView2
    (Evergreen, composant OS distinct) peut manquer — Windows LTSC/Server/N,
    poste neuf ou verrouillé par stratégie — et alors webview.start() PLANTE sans
    repli. On sonde la clé registre du runtime. Hors Windows (dev) : présent."""
    if sys.platform != "win32":
        return True
    try:
        import winreg
    except Exception:
        return True
    G = r"{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    for root, sub in (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\\" + G),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\\" + G),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\\" + G),
    ):
        try:
            with winreg.OpenKey(root, sub) as k:
                pv, _ = winreg.QueryValueEx(k, "pv")
                if pv and pv != "0.0.0.0":
                    return True
        except OSError:
            continue
    return False


def _qt_runtime_ok():
    """PySide6 importable, plugin de plateforme Qt présent ET QApplication qui se
    construit VRAIMENT. `QApplication()` APPELLE abort() (erreur C fatale, NON
    rattrapable par try/except) si le plugin « platforms » (qwindows) manque OU
    échoue à charger (DLL dépendante / runtime VC++ absent) — l'app mourrait
    alors SANS repli. Le fichier présent ne suffit donc pas : on sonde le vrai
    QApplication dans un sous-processus jetable (voir --qt-probe en tête de
    module) AVANT de choisir Qt ; échec → dock web / pilule. Symétrique de
    _webview2_runtime_present pour le chemin WebView2."""
    try:
        import PySide6  # noqa: F401
    except Exception:
        return False
    if not getattr(sys, "frozen", False):
        return True     # hors PyInstaller (dev) : PySide6 pip → plugins présents
    base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    plugin_dir = None
    for d in (os.path.join(base, "PySide6", "plugins", "platforms"),
              os.path.join(base, "_internal", "PySide6", "plugins", "platforms"),
              os.path.join(base, "PySide6", "Qt", "plugins", "platforms")):
        try:
            if os.path.isdir(d) and any(
                    f.lower().startswith("qwindows") for f in os.listdir(d)):
                plugin_dir = d
                break
        except OSError:
            pass
    if plugin_dir is None:
        core.log_err("dock_ui_qt", "plugin de plateforme Qt absent → repli web/pilule")
        return False
    # serve() en aura besoin, y compris quand la sonde est déjà en cache
    os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", plugin_dir)
    # fichier présent ≠ charge : QApplication se construit-il vraiment ? Résultat
    # mémoïsé sur disque PAR VERSION → une seule sonde après chaque mise à jour
    # (un lancement froid n'attend pas le spawn d'un enfant à chaque fois).
    cached = core._load("qt_probe.json", None)
    if isinstance(cached, dict) and cached.get("ver") == core.APP_VERSION \
            and isinstance(cached.get("ok"), bool):
        return cached["ok"]
    ok = _qt_probe_subprocess()
    core._save("qt_probe.json", {"ver": core.APP_VERSION, "ok": ok})
    return ok


def _qt_probe_subprocess():
    """Lance « Nova.exe --qt-probe » : un enfant qui tente QApplication() puis
    sort (0 = OK). Tout autre code — dont l'abort C d'un plugin qui ne charge
    pas — signifie « Qt inutilisable ici » → repli web. On journalise la raison
    Qt (stderr sous QT_DEBUG_PLUGINS) pour diagnostiquer la dépendance manquante
    lors d'une prochaine itération, sans jamais faire planter le processus."""
    import subprocess
    env = dict(os.environ)
    env["QT_DEBUG_PLUGINS"] = "1"          # Qt détaille l'échec de chargement
    flags = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW
    try:
        p = subprocess.run([sys.executable, "--qt-probe"], env=env,
                           capture_output=True, timeout=30, creationflags=flags)
    except Exception as e:
        core.log_err("qt_probe", e)         # spawn/timeout impossible → prudence
        return False
    if p.returncode == 0:
        return True
    tail = (p.stderr or b"")[-1200:].decode("utf-8", "replace").strip()
    core.log_err("qt_probe", f"QApplication KO (code {p.returncode}) → dock web. {tail}")
    return False


def _make_ui():
    """Choisit l'UI. DÉFAUT = pilule tkinter NATIVE : 100 % Python, AUCUN WebView
    (fini les « 404 Not Found » et les plantages du moteur web) ni conflit de DLL
    Qt — elle démarre PARTOUT. La fiabilité prime sur la finition (choix produit
    assumé, demandé par l'utilisateur). Le dock natif PySide6 reste en OPT-IN
    (`dock_ui="qt"`) pour les tests ; s'il échoue il retombe sur la pilule. Le
    dock WEB n'est PLUS sélectionné automatiquement — retiré du chemin par défaut
    car trop instable selon les machines (la classe WebDock reste en place pour
    un éventuel opt-in futur). On journalise le dock retenu (diagnostic)."""
    # dock QML (Qt Quick) : coins ronds natifs + animations, QApplication
    # construit TÔT (ici, à l'import — donc AVANT _warmup_engines) → l'ordre de
    # chargement des DLL est bon, le crash historique disparaît. Opt-in.
    if core.CFG.get("dock_ui") == "qml" and _qt_runtime_ok():
        try:
            dock = _new_qml_dock()
            core.log_err("dock_ui_chosen", "qml")
            return dock
        except Exception as e:
            core.log_err("dock_ui_qml", e)   # QML cassé → dock Qt puis pilule
    if core.CFG.get("dock_ui") == "qt" and _qt_runtime_ok():
        try:
            dock = _new_qt_dock()
            core.log_err("dock_ui_chosen", "qt")
            return dock
        except Exception as e:
            core.log_err("dock_ui_qt", e)   # PySide6 cassé → pilule native
    core.log_err("dock_ui_chosen", "pill")
    return Pill()


def _new_qt_dock():
    """Instancie le dock natif Qt (import paresseux de PySide6)."""
    from qtdock import QtDock
    return QtDock(on_settings=lambda: _open_settings_window(),
                  on_select_mode=lambda mid: _set_mode(mid))


def _new_qml_dock():
    """Instancie le dock QML (import paresseux de PySide6/Qt Quick)."""
    from qmldock import QmlDock
    return QmlDock(on_settings=lambda: _open_settings_window(),
                   on_select_mode=lambda mid: _set_mode(mid))


def _resync_state_from_config():
    """Recale l'état runtime (mode/profil) sur la config rechargée : la fenêtre
    Réglages (processus séparé tant que le dock est natif) a pu les changer.
    Appelé par le dock Qt quand il détecte une écriture de config.json."""
    STATE["mode"] = core.CFG.get("mode", modes_registry.DEFAULT_MODE_ID)
    if not licensing.mode_allowed(STATE["mode"]):
        STATE["mode"] = modes_registry.DEFAULT_MODE_ID
    STATE["profile"] = core.CFG.get("profile", STATE.get("profile"))


def _open_settings_window():
    """Ouvre les Réglages. Le dock natif (Qt) possède le fil principal ; la
    fenêtre Réglages est encore en webview et pywebview veut AUSSI le fil
    principal → on la lance dans un PROCESSUS séparé (les deux boucles ne
    cohabitent pas). L'échange se fait par config.json, que le dock surveille."""
    import subprocess
    try:
        if getattr(sys, "frozen", False):
            args = [sys.executable, "--settings"]
        else:
            args = [sys.executable, os.path.abspath(__file__), "--settings"]
        subprocess.Popen(args, close_fds=True)
    except Exception as e:
        core.log_err("settings_win", e)
        try:
            pill.show("error", "Réglages indisponibles — réessaie")
            pill.hide(2.4)
        except Exception:
            pass


class _SettingsHost:
    """Hôte du DockApi pour la fenêtre Réglages AUTONOME (processus séparé).
    La fenêtre étant une simple fenêtre webview de taille fixe (pas de dock natif
    à détourer/ancrer ici), on n'implémente que ce que DockApi appelle : redim.
    via `_set_panel`, et des no-op pour `apply_shape`/`refresh_prefs`/`_push_ok`
    (sinon AttributeError à chaque reportShape / changement de prefs du dock)."""

    def __init__(self):
        self._win = None
        self._panel = "settings"
        self._push_ok = False       # DockApi.shape y écrit (pont prouvé)

    def _set_panel(self, name):
        self._panel = name
        w, h = {"settings_max": (1180, 780)}.get(name, (880, 620))
        try:
            if self._win is not None:
                self._win.resize(w, h)
        except Exception:
            pass

    def apply_shape(self, payload):
        pass                        # fenêtre fixe : rien à détourer

    def refresh_prefs(self):
        pass                        # les prefs du dock ne concernent pas les Réglages


def _run_settings_process():
    """Processus « Nova.exe --settings » : fenêtre Réglages en webview (dock.html,
    panneau Réglages ouvert d'emblée). Aucune barre, redimensionnable ; les
    changements sont écrits dans config.json et repris EN DIRECT par le dock
    natif (qui surveille le fichier)."""
    # ce processus relit le disque avant chaque save → il n'écrase jamais un
    # changement écrit entre-temps par le processus du dock (anti lost-update)
    core._RELOAD_BEFORE_SAVE = True
    try:
        import webview
    except Exception as e:
        core.log_err("settings_proc", e)
        return
    if not os.path.isfile(DOCK_HTML):
        core.log_err("settings_proc", "dock.html introuvable")
        return
    host = _SettingsHost()
    host._win = webview.create_window(
        _app_display_name() + " — Réglages", html=_dock_html(), width=880,
        height=620, min_size=(720, 500), frameless=True, easy_drag=False,
        resizable=True, background_color="#1F1F22", js_api=DockApi(host))

    def _open():
        try:
            host._win.evaluate_js("window.__openSettings&&window.__openSettings()")
        except Exception:
            pass

    webview.start(_open)


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


def _mode_lock_label():
    """Badge d'un Style verrouillé, dérivé du palier réellement requis
    (licensing.FEATURES) — convention de la charte : « NÉCESSITE NOVA … »."""
    tier = licensing.FEATURES.get("all_modes", licensing.ULTRA)
    return f"NÉCESSITE NOVA {tier.upper()}"


def _ptt_session():
    """Enregistre tant que la touche est tenue, puis transcrit → (Custom
    Variables) → reformate selon le mode → colle au curseur. Repli texte brut
    si l'IA échoue : le curseur n'est jamais vide (garde-fou Phase 5b)."""
    live = None          # lié AVANT le try : le finally le référence sur TOUT
    #                      chemin de sortie, y compris un retour anticipé (quota
    #                      atteint) ou une exception AVANT la création du
    #                      LiveTranscriber — sinon UnboundLocalError dans le
    #                      finally sautait _ptt_active.clear() → PTT figé pour
    #                      le reste de la session.
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
        # transcription EN CONTINU (PC sans GPU) : les tranches terminées sont
        # transcrites pendant que la touche est tenue — à la relâche il ne
        # reste que la fin. Au moindre pépin : repli intégral classique sur le
        # MÊME audio complet (jamais de plantage, jamais de perte).
        rec_kw = {}
        if core.stt_live_enabled():
            try:
                frames, flock = [], threading.Lock()
                live = core.LiveTranscriber(
                    frames, flock,
                    on_partial=lambda t: pill.show("listening", t[-70:]))
                live.start()
                rec_kw = {"frames_out": frames, "frames_lock": flock}
            except Exception as e:
                core.log_err("stt_live", e)
                live, rec_kw = None, {}
        # récupération : si record_audio lève, l'exception remonte au except
        # externe (« Erreur — réessaie ») et le finally coupe le fil de fond.
        audio = core.record_audio(on_level=pill.level, stop=_ptt_stop,
                                  end_silence=999, **rec_kw)
        t_release = time.time()
        if audio is None:
            pill.show("error", "Je n'ai rien entendu")
            pill.hide(1.6)
            return
        pill.show("thinking", "Un instant…")
        text = live.finish() if live else None    # ne lève jamais (contrat)
        engine = "local"
        if not text:
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
        # petites configs — SAUF si « moteur en mémoire » (dès ~8 Go) : le
        # rechargement disque coûtait 2-4 s au début de CHAQUE dictée
        if core._seq_exclusive():        # invariant partagé (cf. core._should_warm_llm)
            core.unload_whisper()
        prompt, concrete = _resolve_prompt(STATE["mode"])
        if concrete == "voice_to_text" and core.CFG.get("instant_normal"):
            # collage éclair (réglage, off par défaut) : le Style Normal par
            # règles pures, SANS IA — latence quasi nulle, choix explicite de
            # l'utilisateur, donc styled=True (c'est le résultat demandé)
            out, styled = core.format_rules(text) or text, True
        else:
            # cascade de repli universelle : IA → format_rules → texte brut.
            # Chaque étage est protégé : jamais de plantage, jamais de
            # curseur vide.
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
        if live:
            live.stop()   # propriétaire UNIQUE du teardown du fil de fond :
                          # s'exécute sur TOUT chemin de sortie (retour anticipé,
                          # exception, succès). stop() = Event.set(), idempotent
                          # après finish() ou une reprise micro — plus de daemon
                          # orphelin, plus de double-arrêt à gérer ailleurs.
        _ptt_active.clear()


def _on_ptt_press(_e=None):
    # `_ptt_active` (levé ici, baissé dans le finally de _ptt_session) ignore
    # l'auto-répétition clavier pendant une session ET se ré-arme tout seul à la
    # fin de chaque session : jamais bloqué même si un événement « touche
    # relâchée » est perdu (changement de focus, glitch de hook…).
    # gardé comme chord_press : une exception dans un hook `keyboard` remonterait
    # dans le fil de la lib et pourrait casser TOUS les raccourcis
    try:
        if _ptt_active.is_set():
            return
        _ptt_active.set()
        _ptt_stop.clear()
        threading.Thread(target=_ptt_session, daemon=True).start()
    except Exception as e:
        core.log_err("ptt_press", e)
        _ptt_active.clear()        # jamais coincé « actif » sur un échec


def _on_ptt_release(_e=None):
    try:
        _ptt_stop.set()
    except Exception as e:
        core.log_err("ptt_release", e)


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
        if not licensing.mode_allowed(mode_id):
            # Style au-dessus du palier (résiliation, resserrement d'offre) :
            # raccourci laissé INERTE plutôt que de déclencher pour toujours
            # la bulle « Style réservé » — re-lié dès le prochain rebind
            # après activation d'une licence
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
    sett = str(core.CFG.get("settings_hotkey") or "").strip().lower()
    if sett:
        try:
            _style_hotkeys.append(keyboard.add_hotkey(
                sett, lambda: pill.open_settings(), suppress=False))
        except Exception as e:
            core.log_err("settings_hotkey", e)


def _hotkey_set_mode(mode_id):
    """Bascule de Style par raccourci clavier : sans le menu sous les yeux,
    l'utilisateur a besoin d'une confirmation visible du Style désormais actif.
    On se fie au RETOUR de _set_mode, pas à STATE : un Style verrouillé peut
    déjà être « sélectionné » (hérité) — l'égalité confirmerait alors à tort."""
    if _set_mode(mode_id):
        pill.show("ok", _mode_label(mode_id), "Style actif")
        pill.hide(1.4)


# ============================================================ barre des tâches
def _set_mode(mode_id):
    """→ True si le Style est réellement devenu actif, False si refusé."""
    if not licensing.mode_allowed(mode_id):       # mode réservé aux paliers payants
        pill.show("error", "Style réservé à Pro", "Débloquez tous les Styles")
        pill.hide(2.0)
        return False
    STATE["mode"] = mode_id
    core.save_config({"mode": mode_id})
    pill.show("repos", "")
    pill.hide(1.2)
    return True


def _set_language(lang):
    core.save_config({"language": lang})
    core.CFG["language"] = lang


def _toggle_cloud():
    """Bascule Local ↔ Cloud pour STT ET reformulation (GOAL Partie 4 : local
    par défaut, cloud proposé jamais imposé)."""
    to_cloud = not (core.CFG.get("stt") or {}).get("cloud_enabled")
    if to_cloud and not licensing.has("cloud_stt"):   # Turbo réservé à Ultra
        pill.show("error", "Turbo réservé à Pro", "La vitesse maximale, via le réseau")
        pill.hide(2.2)
        return
    # patch MINIMAL (seule la clé changée) : ne pas ré-écrire tout le sous-dict
    # stt, sinon un réglage de latence écrit en parallèle (autre fil js_api)
    # serait ré-écrasé par une copie périmée.
    core.save_config({"stt": {"cloud_enabled": to_cloud},
                      "provider": "auto" if to_cloud else "ollama"})


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


def _check_update(manual=True):
    """Vraie mise à jour : compare à la dernière release ; si plus récente,
    télécharge et installe en silencieux puis relance Nova. Feedback dans la
    pilule/bulle ; jamais bloquant (thread de fond, best-effort)."""
    def work():
        info = updater.check_latest()
        if info and info["newer"]:
            pill.show("thinking", f"Mise à jour vers {info['version']}…")
            res = updater.download_and_install()   # succès = ne revient jamais
            if not manual:                          # vérif de fond : silencieuse
                pill.hide(0)
            elif res == updater.BUSY:
                # une autre tentative tourne déjà : pas un échec — le dire
                pill.show("thinking", "Mise à jour déjà en cours…")
                pill.hide(2.2)
            elif res == updater.UNSUPPORTED:        # pas un .exe : développement
                pill.show("error", "Mise à jour auto indisponible "
                                   "(version de développement)")
                pill.hide(2.4)
            else:                                   # FAILED, demandé par l'utilisateur
                # plan B : l'installation silencieuse a échoué (antivirus,
                # réseau filtré…) — on ouvre le téléchargement direct dans le
                # navigateur. webbrowser.open signale l'échec en RENVOYANT
                # False (jamais d'exception sous Windows) : ne prétendre que
                # le navigateur s'ouvre que s'il s'est vraiment ouvert.
                opened = False
                try:
                    import webbrowser
                    opened = bool(webbrowser.open(updater.SETUP_URL))
                except Exception:
                    pass
                if opened:
                    pill.show("error",
                              "Installation auto impossible — "
                              "le téléchargement s'ouvre dans le navigateur")
                    pill.hide(4.0)
                else:
                    pill.show("error",
                              "Mise à jour impossible — réessaie plus tard")
                    pill.hide(2.6)
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


def _warmup_engines():
    """Au lancement : précharge les moteurs en arrière-plan (10 s de délai —
    priorité au démarrage de l'interface et à la vérification de mise à jour).
    Le choix GPU/CPU, lui, se résout TOUT DE SUITE (quelques secondes, zéro
    RAM) : il ne doit jamais rester à faire au premier appui de touche, où il
    retarderait l'ouverture du micro. La PREMIÈRE dictée de la session
    devient aussi rapide que les suivantes."""
    def work():
        try:
            core.gpu_active()          # résolution memoïsée du device
        except Exception:
            pass
        time.sleep(10)
        core.warmup_engines()
        try:
            # reformulation locale absente (service pas installé) : le dire UNE
            # fois, avec la marche à suivre — sinon chaque Style retombe en
            # silence sur le collage brut et l'utilisateur croit à une panne.
            # JAMAIS par-dessus une dictée en cours (la bulle « Je t'écoute… »
            # ne doit pas être remplacée), ni pendant qu'une installation
            # tourne déjà (l'indice serait faux).
            import engine_setup
            st = engine_setup.status()
            if (core.resolve_provider() == "ollama"
                    and st["phase"] == "idle" and not st["ready"]
                    and not _ptt_active.is_set()):
                pill.show("error", "Intelligence privée à terminer",
                          "Réglages → Installer la reformulation locale")
                pill.hide(5.0)
        except Exception:
            pass
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
                        radio=True,
                        # même règle de verrou que le menu du dock — grisé,
                        # ré-évalué à chaque ouverture (activation en session)
                        enabled=lambda _it: licensing.mode_allowed(mid))

    # Le menu natif est dessiné par WINDOWS : impossible à styler. Quand le
    # dock web est là, il porte son PROPRE menu Nova (open_tray_menu, langage
    # visuel du dock) — le natif est réduit au strict secours : ouvrir le menu
    # Nova (double-clic = défaut) et quitter (toujours accessible même si la
    # webview est morte). La pilule tkinter, sans dock, garde le menu complet.
    if hasattr(pill, "open_tray_menu"):
        menu = Menu(
            MenuItem("Ouvrir Nova", lambda _i, _it: pill.open_tray_menu(),
                     default=True),
            # garder la vérification de mise à jour en NATIF : elle marche
            # sans le pont web (pur Python) et c'est le remède le plus
            # probable quand justement la webview est cassée
            MenuItem("Vérifier les mises à jour", lambda _i, _it: _check_update()),
            MenuItem("Quitter Nova", lambda icon, _it: _request_quit(icon)),
        )
    else:
        menu = Menu(
            # élément par défaut : un DOUBLE-CLIC sur l'icône ouvre les Réglages
            MenuItem("Ouvrir les Réglages", lambda _i, _it: pill.open_settings(),
                     default=True),
            MenuItem("Style", Menu(*[mode_item(m) for m in modes_registry.all_modes()])),
            Menu.SEPARATOR,
            MenuItem("Vérifier les mises à jour", lambda _i, _it: _check_update()),
            MenuItem("Quitter Nova", lambda icon, _it: _request_quit(icon)),
        )
    return pystray.Icon(APP_NAME, img, f"{_app_display_name()} — dictée vocale", menu)


def main():
    # profil de puissance : bootstrap AVANT tout le reste, y compris l'onboarding
    # (best-effort, peut échouer ou être fermé sans être terminé) — la garantie
    # « jamais de saturation RAM » ne doit jamais dépendre de l'écran d'accueil.
    # GARDÉ : un échec (écriture config disque, sonde matériel) ne doit JAMAIS
    # empêcher Nova de démarrer.
    safe = core.CFG.get("profile", "normal")
    try:
        hw = power_profiles.detect_hardware()
        safe = power_profiles.select_and_apply(safe, core.save_config,
                                               _profiles_paid())
        core.log_err("startup", f"matériel={hw} → profil={safe}")
    except Exception as e:
        core.log_err("startup_profile", e)

    if onboarding.needs_onboarding():
        try:
            onboarding.run()          # bloquant, une seule fois (1er lancement)
        except Exception as e:
            core.log_err("onboarding", e)   # jamais bloquant : on démarre quand même

    STATE["profile"] = core.CFG.get("profile", safe)   # reflète un choix fait dans l'onboarding

    integrations.start_connectivity_loop()   # sonde en ligne (active le STT cloud)
    _auto_update_check()                      # MàJ auto en fond (jamais bloquant)
    _warmup_engines()                         # moteurs prêts pour la 1re dictée

    # abonnement : renouvelle le jeton de licence s'il approche de l'expiration
    # (best-effort, en fond — hors ligne, la période de grâce du jeton suffit)
    threading.Thread(target=licensing.refresh_if_needed, daemon=True).start()

    # Chaque UI possède sa propre boucle (pilule tkinter ou dock webview) via
    # `serve()` : main() n'a aucun type à tester. Bloquant jusqu'à la fermeture.
    global pill
    try:
        pill.serve(_build_tray)
    except Exception as e:
        # DERNIER FILET : si le dock web échoue à l'exécution (runtime WebView2
        # présent mais cassé, échec de create_window/start), on ne MEURT pas — on
        # bascule sur la pilule tkinter (garde-fou « JAMAIS de plantage »).
        core.log_err("serve_fallback", e)
        try:
            if _tray_icon is not None:
                _tray_icon.stop()          # l'ancien tray du dock est déjà lancé
        except Exception:
            pass
        if not isinstance(pill, Pill):
            try:
                pill = Pill()
                pill.serve(_build_tray)    # reconstruit son propre tray
            except Exception as e2:
                core.log_err("serve_fallback2", e2)
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
    if "--settings" in sys.argv:
        # fenêtre Réglages autonome (webview), ouverte par le dock natif Qt qui
        # possède le fil principal dans l'autre processus — voir _open_settings_window
        _run_settings_process()
        sys.exit(0)
    main()
