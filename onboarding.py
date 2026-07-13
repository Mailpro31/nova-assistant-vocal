# -*- coding: utf-8 -*-
"""Assistant de bienvenue (1er lancement) — 100 % NATIF tkinter.

Historiquement rendu en pywebview (onboarding.html) ; abandonné car le moteur
web plantait/renvoyait « 404 » sur certaines machines (comme le dock). On le
refait donc en tkinter pur, comme la pilule et les Réglages : AUCUN WebView,
aucune vidéo à muxer, aucune ressource externe → il s'affiche PARTOUT, sans
jamais bloquer le démarrage. Il configure réellement l'app (touche push-to-talk,
profil de puissance, langue, moteur local/Turbo) en réutilisant EXACTEMENT la
logique du menu tray / des Réglages — aucune règle dupliquée. Ne s'affiche
qu'une fois (`CFG["onboarding_done"]`), et se marque « fait » quoi qu'il arrive
(fermeture, croix, erreur tkinter) : jamais de reboucle, jamais de blocage.
"""

import core
import licensing
import power_profiles

# Palette — même langage visuel que la pilule et les Réglages (CLAUDE.md).
BG = "#1F1F22"
CARD = "#2C2C30"
INSET = "#1A1A1D"
FG = "#F2F2F4"
MUT = "#98989F"
DIM = "#7C8398"
LINE = "#37373B"
ACCENT = "#0A84FF"
WHITE = "#FFFFFF"
OK = "#30D158"
ULTRA = "#C9B6F0"

# tkinter renvoie des keysym « bruts » ; on les ramène au format de la lib
# `keyboard` (celui que lit _rebind_ptt). Les cas courants suffisent : la
# plupart des gens choisissent une touche de fonction (F9 par défaut).
_KEYSYM = {
    "control_l": "ctrl", "control_r": "ctrl",
    "alt_l": "alt", "alt_r": "alt", "iso_level3_shift": "alt gr",
    "shift_l": "shift", "shift_r": "shift",
    "prior": "page up", "next": "page down",
    "return": "enter", "escape": "esc", "caps_lock": "caps lock",
}


def _norm_key(keysym):
    k = (keysym or "").strip().lower()
    return _KEYSYM.get(k, k)


def needs_onboarding():
    return not core.CFG.get("onboarding_done")


# --- logique de configuration (identique au tray / aux Réglages) -------------
def set_ptt_key(key):
    key = _norm_key(key)
    if key:
        core.save_config({"ptt_key": key})
    return core.CFG.get("ptt_key", "f9")


def set_profile(profile_id):
    return power_profiles.select_and_apply(profile_id, core.save_config,
                                           licensing.has("power_profiles"))


def set_language(code):
    core.save_config({"language": code})
    return code


def set_cloud(enabled):
    if enabled and not licensing.has("cloud_stt"):
        return False                       # Turbo verrouillé (nécessite Ultra)
    core.save_config({"stt": {"cloud_enabled": bool(enabled)},
                      "provider": "auto" if enabled else "ollama"})
    return bool(enabled)


def run():
    """Affiche l'assistant natif (bloquant, thread principal). Marque toujours
    l'onboarding « fait » à la sortie — jamais de reboucle. Toute erreur tkinter
    est avalée : l'app démarre ensuite normalement avec les valeurs par défaut."""
    try:
        _run_wizard()
    except Exception as e:
        core.log_err("onboarding", e)
    finally:
        core.save_config({"onboarding_done": True})


def _run_wizard():
    import tkinter as tk
    import tkinter.font as tkfont

    hw = power_profiles.detect_hardware()
    root = tk.Tk()
    root.title("Bienvenue sur Nova")
    root.configure(bg=BG)
    root.report_callback_exception = \
        lambda et, ev, tb: core.log_err("onb_tk", ev)
    W, H = 680, 560
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{W}x{H}+{(sw - W) // 2}+{max(0, (sh - H) // 2 - 20)}")
    try:
        root.attributes("-topmost", True)
        root.after(400, lambda: root.attributes("-topmost", False))
    except Exception:
        pass

    f_title = tkfont.Font(family="Segoe UI", size=22, weight="bold")
    f_h = tkfont.Font(family="Segoe UI", size=15, weight="bold")
    f_body = tkfont.Font(family="Segoe UI", size=11)
    f_small = tkfont.Font(family="Segoe UI", size=9)
    f_btn = tkfont.Font(family="Segoe UI", size=11, weight="bold")
    f_key = tkfont.Font(family="Consolas", size=13, weight="bold")

    state = {"i": 0, "cap": False}
    NSTEPS = 6

    # ---- ossature : contenu + barre du bas -------------------------------
    content = tk.Frame(root, bg=BG)
    content.pack(fill="both", expand=True, padx=34, pady=(30, 8))

    dots = tk.Frame(root, bg=BG)
    dots.pack(pady=(0, 2))
    dot_lbls = []
    for _k in range(NSTEPS):
        d = tk.Label(dots, text="●", bg=BG, fg=LINE, font=f_small)
        d.pack(side="left", padx=3)
        dot_lbls.append(d)

    bar = tk.Frame(root, bg=BG)
    bar.pack(fill="x", padx=34, pady=(4, 20))
    btn_prev = tk.Button(bar, text="Précédent", font=f_body, bg=CARD, fg=FG,
                         relief="flat", padx=14, pady=7, bd=0,
                         activebackground=LINE, activeforeground=FG,
                         cursor="hand2", command=lambda: _go(-1))
    btn_prev.pack(side="left")
    btn_next = tk.Button(bar, text="Suivant", font=f_btn, bg=ACCENT, fg=WHITE,
                         relief="flat", padx=22, pady=7, bd=0,
                         activebackground="#0A6CD8", activeforeground=WHITE,
                         cursor="hand2", command=lambda: _go(1))
    btn_next.pack(side="right")

    def _clear():
        for w in content.winfo_children():
            w.destroy()

    def _heading(txt, sub=""):
        tk.Label(content, text=txt, bg=BG, fg=FG, font=f_title,
                 anchor="w", justify="left").pack(anchor="w")
        if sub:
            tk.Label(content, text=sub, bg=BG, fg=MUT, font=f_body,
                     anchor="w", justify="left", wraplength=W - 90).pack(
                         anchor="w", pady=(6, 16))

    def _group():
        g = tk.Frame(content, bg=CARD, highlightbackground=LINE,
                     highlightthickness=1)
        g.pack(fill="x", pady=6)
        inner = tk.Frame(g, bg=CARD)
        inner.pack(fill="x", padx=16, pady=14)
        return inner

    # ---- étape 0 : accueil ----------------------------------------------
    def _step_welcome():
        tk.Label(content, text="Nova", bg=BG, fg=FG,
                 font=tkfont.Font(family="Segoe UI", size=30, weight="bold")
                 ).pack(anchor="w", pady=(30, 0))
        tk.Label(content, text="Bienvenue", bg=BG, fg=ACCENT, font=f_title
                 ).pack(anchor="w")
        tk.Label(content,
                 text=("Ta voix devient ton clavier. Maintiens une touche, "
                       "parle, relâche —\nle texte reformulé s'écrit là où est "
                       "ton curseur, dans n'importe quelle appli."),
                 bg=BG, fg=MUT, font=f_body, justify="left").pack(
                     anchor="w", pady=(16, 0))
        tk.Label(content,
                 text="Trois écrans de réglage, et tu es prêt.",
                 bg=BG, fg=DIM, font=f_small, justify="left").pack(
                     anchor="w", pady=(18, 0))

    # ---- étape 1 : touche de dictée -------------------------------------
    def _step_key():
        _heading("Ta touche de dictée",
                 "La touche que tu maintiens pour parler. F9 par défaut — "
                 "choisis-en une que tu n'utilises pas en tapant.")
        box = _group()
        cur = core.CFG.get("ptt_key", "f9")
        keylbl = tk.Label(box, text=(cur or "f9").upper(), bg=INSET, fg=ACCENT,
                          font=f_key, padx=18, pady=8)
        keylbl.pack(side="left")
        hint = tk.Label(box, text="Touche actuelle", bg=CARD, fg=MUT,
                        font=f_small)
        hint.pack(side="left", padx=14)

        def _start_capture():
            state["cap"] = True
            keylbl.configure(text="…", fg=OK)
            hint.configure(text="Appuie sur une touche")
            btn_cap.configure(text="En attente…")
            root.focus_force()

        def _on_key(ev):
            if not state["cap"]:
                return
            k = set_ptt_key(ev.keysym)
            state["cap"] = False
            keylbl.configure(text=(k or "f9").upper(), fg=ACCENT)
            hint.configure(text="Touche enregistrée")
            btn_cap.configure(text="Changer la touche")

        btn_cap = tk.Button(box, text="Changer la touche", font=f_body,
                            bg=ACCENT, fg=WHITE, relief="flat", padx=14, pady=6,
                            bd=0, activebackground="#0A6CD8",
                            activeforeground=WHITE, cursor="hand2",
                            command=_start_capture)
        btn_cap.pack(side="right")
        root.bind("<Key>", _on_key)

    # ---- étape 2 : profil de puissance ----------------------------------
    def _step_profile():
        _heading("Puissance de l'IA",
                 "Nova ajuste l'intelligence à ta machine. On a présélectionné "
                 "ce qu'elle encaisse le mieux.")
        box = _group()
        var = tk.StringVar(value=core.CFG.get("profile", "normal"))

        def _choose():
            applied = set_profile(var.get())
            var.set(applied)               # reflète un éventuel repli

        for ev in power_profiles.evaluate(hw, licensing.has("power_profiles")):
            note = (ev.get("reason") if ev["locked"]
                    else (ev.get("warning") or ""))
            txt = ev["label"] + (f"   — {note}" if note else "")
            tk.Radiobutton(box, text=txt, value=ev["id"], variable=var,
                           command=_choose, bg=CARD, fg=FG, font=f_body,
                           selectcolor=INSET, activebackground=CARD,
                           activeforeground=FG, relief="flat", anchor="w",
                           state=("disabled" if ev["locked"] else "normal")
                           ).pack(anchor="w", pady=2, fill="x")

    # ---- étape 3 : langue -----------------------------------------------
    def _step_language():
        _heading("Langue de dictée",
                 "Dans quelle langue tu parles. « Automatique » détecte tout "
                 "seul si tu jongles entre plusieurs.")
        box = _group()
        langs = list(core.LANGUAGES)
        by_label = {lbl: c for c, lbl in langs}
        cur = core.CFG.get("language", "fr")
        var = tk.StringVar(value=next((lbl for c, lbl in langs if c == cur),
                                      langs[0][1]))
        menu = tk.OptionMenu(box, var, *[lbl for _c, lbl in langs],
                             command=lambda lbl: set_language(
                                 by_label.get(lbl, "fr")))
        menu.configure(bg=INSET, fg=FG, font=f_body, relief="flat", bd=0,
                       highlightthickness=0, activebackground=INSET,
                       activeforeground=FG, width=26, anchor="w")
        try:
            menu["menu"].configure(bg=INSET, fg=FG, activebackground=ACCENT,
                                    activeforeground=WHITE)
        except Exception:
            pass
        menu.pack(anchor="w")

    # ---- étape 4 : moteur -----------------------------------------------
    def _step_engine():
        _heading("Le moteur d'intelligence",
                 "Qui applique tes Styles. L'Intelligence privée marche 100 % "
                 "hors ligne — c'est le défaut.")
        turbo_ok = licensing.has("cloud_stt")
        cur = bool(core.CFG.get("stt", {}).get("cloud_enabled")) and turbo_ok
        var = tk.StringVar(value="turbo" if cur else "local")

        def _choose():
            ok = set_cloud(var.get() == "turbo")
            if not ok:
                var.set("local")           # Turbo refusé (verrouillé)

        b1 = _group()
        tk.Radiobutton(b1, text="  Intelligence privée", value="local",
                       variable=var, command=_choose, bg=CARD, fg=FG,
                       font=f_h, selectcolor=INSET, activebackground=CARD,
                       activeforeground=FG, relief="flat", anchor="w").pack(
                           anchor="w")
        tk.Label(b1, text="Hors ligne, privé, sur ton ordinateur.", bg=CARD,
                 fg=MUT, font=f_small).pack(anchor="w", padx=(26, 0))

        b2 = _group()
        row = tk.Frame(b2, bg=CARD)
        row.pack(fill="x")
        tk.Radiobutton(row, text="  Turbo", value="turbo", variable=var,
                       command=_choose, bg=CARD, fg=FG, font=f_h,
                       selectcolor=INSET, activebackground=CARD,
                       activeforeground=FG, relief="flat", anchor="w",
                       state=("normal" if turbo_ok else "disabled")).pack(
                           side="left")
        if not turbo_ok:
            tk.Label(row, text="NÉCESSITE NOVA ULTRA", bg="#332C46", fg=ULTRA,
                     font=f_small, padx=8, pady=2).pack(side="right")
        tk.Label(b2, text="La vitesse maximale, via le réseau.", bg=CARD,
                 fg=MUT, font=f_small).pack(anchor="w", padx=(26, 0))

    # ---- étape 5 : prêt --------------------------------------------------
    def _step_ready():
        tk.Label(content, text="Tout est prêt", bg=BG, fg=FG, font=f_title
                 ).pack(anchor="w", pady=(40, 0))
        key = (core.CFG.get("ptt_key", "f9") or "f9").upper()
        tk.Label(content,
                 text=(f"Maintiens « {key} », parle, relâche — et regarde ton "
                       "texte s'écrire.\nLes Styles et les Réglages sont dans "
                       "l'icône de la barre des tâches."),
                 bg=BG, fg=MUT, font=f_body, justify="left").pack(
                     anchor="w", pady=(16, 0))
        tk.Label(content, text="Bonne dictée.", bg=BG, fg=OK, font=f_h).pack(
            anchor="w", pady=(22, 0))

    STEPS = [_step_welcome, _step_key, _step_profile, _step_language,
             _step_engine, _step_ready]

    def _render():
        state["cap"] = False
        try:
            root.unbind("<Key>")
        except Exception:
            pass
        _clear()
        i = state["i"]
        STEPS[i]()
        for k, d in enumerate(dot_lbls):
            d.configure(fg=(ACCENT if k == i else LINE))
        btn_prev.pack_forget()
        if i > 0:
            btn_prev.pack(side="left")
        if i == 0:
            btn_next.configure(text="Commencer")
        elif i == NSTEPS - 1:
            btn_next.configure(text="Terminer")
        else:
            btn_next.configure(text="Suivant")

    def _go(delta):
        nxt = state["i"] + delta
        if nxt < 0:
            return
        if nxt >= NSTEPS:
            _finish()
            return
        state["i"] = nxt
        _render()

    def _finish():
        try:
            root.destroy()
        except Exception:
            pass

    root.protocol("WM_DELETE_WINDOW", _finish)   # croix = terminer (pas d'erreur)
    _render()
    root.mainloop()
