"""Dock Nova en QML (PySide6/Qt Quick) — OPT-IN (`dock_ui="qml"`).

Pourquoi QML : coins arrondis natifs, dégradés radiaux réels et ANIMATIONS
fluides (respiration de l'orbe, équaliseur, fondus) — le look macOS premium sans
WebView, donc sans les plantages du moteur web.

Fiabilité du lancement : le crash historique venait de Qt qui s'initialisait
APRÈS les moteurs natifs (faster-whisper / ctranslate2) → conflit de DLL et
`abort()` C. Ici `QApplication` est construit TÔT (dès l'instanciation, avant
`_warmup_engines()` de app.main) : Qt charge ses DLL en premier, le conflit
disparaît. Le tout reste opt-in et retombe sur la pilule tkinter au moindre
échec (règle « jamais de plantage »).

API publique identique à Pill/QtDock (`show/hide/level/open_settings/open_modes/
refresh_prefs/destroy/serve`) → `app.main()` ne teste aucun type. Les appels
venant d'autres fils (audio ~30×/s, clavier) sont marshalés vers le fil GUI par
signaux Qt (jamais de widget/propriété touché hors du fil GUI).
"""
from __future__ import annotations

import json
import os
import sys
import threading

from PySide6.QtCore import QObject, QUrl, QTimer, Signal, Slot, Property
from PySide6.QtQml import QQmlApplicationEngine
import PySide6.QtQuick  # noqa: F401  (force PyInstaller à embarquer le runtime QML)

import core


def _ensure_qapp():
    """Construit (ou récupère) le QApplication. Appelé TÔT — avant les moteurs
    natifs — pour charger les DLL Qt en premier (corrige le crash au lancement)."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is not None:
        return app
    try:                                   # icône barre des tâches (Windows)
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("NovaSpeak.Nova")
    except Exception:
        pass
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    try:
        from PySide6.QtGui import QIcon
        import app as A
        app.setWindowIcon(QIcon(A.resource_path("icon.ico")))
    except Exception:
        pass
    return app


def _valid_hex(v):
    hx = str(v or "").strip()
    if len(hx) == 7 and hx[0] == "#":
        try:
            int(hx[1:], 16)
            return hx
        except ValueError:
            return ""
    return ""


def _clamp_opacity(v):
    try:
        return max(0.55, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 1.0


def _g(attr):
    """Getter d'une Property Qt adossée à un attribut d'instance."""
    return lambda self: getattr(self, attr)


def _s(attr, sig):
    """Setter d'une Property Qt : n'émet le signal `sig` que si la valeur change
    (évite les repeints QML inutiles, ex. le niveau audio identique)."""
    def setter(self, v):
        if getattr(self, attr) != v:
            setattr(self, attr, v)
            getattr(self, sig).emit()
    return setter


class _Bridge(QObject):
    """Pont Python ↔ QML : propriétés liées par le QML (état, niveau, textes…) et
    slots appelés par le QML (clics roue/étoile/Style). Vit sur le fil GUI."""

    stateChanged = Signal()
    levelChanged = Signal()
    pillShownChanged = Signal()
    bubbleShownChanged = Signal()
    bubbleTextChanged = Signal()
    bubbleSubChanged = Signal()
    menuShownChanged = Signal()
    modesJsonChanged = Signal()
    currentModeChanged = Signal()
    dockPositionChanged = Signal()
    dockOpacityChanged = Signal()
    orbColorChanged = Signal()
    pttKeyChanged = Signal()

    gearClicked = Signal()
    starClicked = Signal()
    modePicked = Signal(str)

    def __init__(self):
        super().__init__()
        self._state = "repos"
        self._level = 0.0
        self._pillShown = True
        self._bubbleShown = False
        self._bubbleText = ""
        self._bubbleSub = ""
        self._menuShown = False
        self._modesJson = "[]"
        self._currentMode = "auto"
        self._dockPosition = "bottom-center"
        self._dockOpacity = 1.0
        self._orbColor = ""
        self._pttKey = ""

    # Property déclarées explicitement (chaque setter n'émet que si ça change).
    state = Property(str, _g("_state"), _s("_state", "stateChanged"), notify=stateChanged)
    level = Property(float, _g("_level"), _s("_level", "levelChanged"), notify=levelChanged)
    pillShown = Property(bool, _g("_pillShown"), _s("_pillShown", "pillShownChanged"), notify=pillShownChanged)
    bubbleShown = Property(bool, _g("_bubbleShown"), _s("_bubbleShown", "bubbleShownChanged"), notify=bubbleShownChanged)
    bubbleText = Property(str, _g("_bubbleText"), _s("_bubbleText", "bubbleTextChanged"), notify=bubbleTextChanged)
    bubbleSub = Property(str, _g("_bubbleSub"), _s("_bubbleSub", "bubbleSubChanged"), notify=bubbleSubChanged)
    menuShown = Property(bool, _g("_menuShown"), _s("_menuShown", "menuShownChanged"), notify=menuShownChanged)
    modesJson = Property(str, _g("_modesJson"), _s("_modesJson", "modesJsonChanged"), notify=modesJsonChanged)
    currentMode = Property(str, _g("_currentMode"), _s("_currentMode", "currentModeChanged"), notify=currentModeChanged)
    dockPosition = Property(str, _g("_dockPosition"), _s("_dockPosition", "dockPositionChanged"), notify=dockPositionChanged)
    dockOpacity = Property(float, _g("_dockOpacity"), _s("_dockOpacity", "dockOpacityChanged"), notify=dockOpacityChanged)
    orbColor = Property(str, _g("_orbColor"), _s("_orbColor", "orbColorChanged"), notify=orbColorChanged)
    pttKey = Property(str, _g("_pttKey"), _s("_pttKey", "pttKeyChanged"), notify=pttKeyChanged)

    @Slot()
    def gear(self):
        self.gearClicked.emit()

    @Slot()
    def star(self):
        self.starClicked.emit()

    @Slot(str)
    def pick(self, mode_id):
        self.modePicked.emit(mode_id)


class QmlDock(QObject):
    """Contrôleur du dock QML. API identique à Pill/QtDock."""

    _sig_show = Signal(str, str, str)
    _sig_hide = Signal(int)
    _sig_level = Signal(float)
    _sig_modes = Signal()
    _sig_prefs = Signal()
    _sig_settings = Signal()
    _sig_quit = Signal()

    def __init__(self, on_settings, on_select_mode):
        # QApplication TÔT (avant les moteurs) — c'est le correctif du crash.
        self._app = _ensure_qapp()
        super().__init__()
        self._on_settings = on_settings
        self._on_select_mode = on_select_mode
        self._bridge = _Bridge()
        self._engine = None
        self._ready = False
        self._hide_timer = None
        self._watcher = None
        self._settings_view = None

    # ---- API thread-safe (émet ; le slot s'exécute sur le fil GUI) ----
    def show(self, state, text="", sub=""):
        self._sig_show.emit(state, text or "", sub or "")

    def hide(self, delay=0.0):
        self._sig_hide.emit(int(delay * 1000))

    def level(self, rms):
        self._sig_level.emit(float(rms))

    def open_settings(self):
        # marshalé vers le fil GUI : le tray (autre fil) peut l'appeler, or une
        # fenêtre Qt ne se crée QUE sur le fil GUI.
        self._sig_settings.emit()

    def open_modes(self):
        self._sig_modes.emit()

    def refresh_prefs(self):
        self._sig_prefs.emit()

    def destroy(self):
        self._sig_quit.emit()

    # ---- cycle de vie : possède le fil PRINCIPAL ----
    def serve(self, build_tray):
        import app as A
        self._connect()
        self._load_qml()
        A._rebind_ptt()
        A._tray_icon = build_tray()
        threading.Thread(target=A._tray_icon.run, daemon=True).start()
        try:
            core.install_freeze_watchdog()
        except Exception:
            pass
        self._beat = QTimer()
        self._beat.timeout.connect(core.heartbeat)
        self._beat.start(1000)
        self._app.exec()

    def _load_qml(self):
        import app as A
        self._sync_prefs()
        self._engine = QQmlApplicationEngine()
        self._add_qml_import_paths()
        # Avertissements du moteur QML (module introuvable, plugin illisible,
        # erreur de binding…) : sous --noconsole ils partent dans un stderr
        # PERDU → le rendu échoue « sans raison ». On les mémorise et on les
        # journalise pour diagnostiquer un échec de chargement sans console.
        warns = []

        def _on_warn(errs):
            for e in errs:
                try:
                    warns.append(e.toString())
                except Exception:
                    warns.append(str(e))
            core.log_err("qml_warn", " | ".join(warns[-6:]))
        self._engine.warnings.connect(_on_warn)
        self._engine.rootContext().setContextProperty("nova", self._bridge)
        qml = A.resource_path(os.path.join("qml", "Main.qml"))
        self._engine.load(QUrl.fromLocalFile(qml))
        if not self._engine.rootObjects():
            detail = " | ".join(warns) or "aucun détail Qt (stderr perdu)"
            raise RuntimeError(f"QML Main.qml non chargé : {detail}")
        self._bridge.gearClicked.connect(self.open_settings)
        self._bridge.starClicked.connect(self._toggle_menu)
        self._bridge.modePicked.connect(self._pick_mode)
        self._ready = True
        self._arm_launch_guard()
        self._install_config_watch()

    def _add_qml_import_paths(self):
        """Enregistre le dossier des plugins QML embarqués. Dans l'exe figé
        (PyInstaller), les modules QML (QtQuick, QtQuick.Window…) vivent sous
        _MEIPASS/PySide6/qml, mais le moteur ne cherche PAS toujours là par
        défaut → « import QtQuick » échoue et Main.qml ne se charge pas (repli
        pilule). On ajoute donc explicitement les emplacements possibles. En dev
        (PySide6 pip) le moteur les trouve seul : ce sont des no-op sans effet."""
        base = getattr(sys, "_MEIPASS", None)
        if not base:
            return
        for sub in (("PySide6", "qml"), ("PySide6", "Qt", "qml"),
                    ("_internal", "PySide6", "qml")):
            d = os.path.join(base, *sub)
            try:
                if os.path.isdir(d):
                    self._engine.addImportPath(d)
            except Exception:
                pass

    def _arm_launch_guard(self):
        """Auto-réparation : efface le marqueur de crash QML DÈS la 1re frame
        rendue. Un abort GPU, s'il a lieu, survient PENDANT ce premier rendu —
        recevoir frameSwapped prouve donc que le rendu (matériel ou logiciel)
        tient. On connecte toutes les fenêtres (la première à peindre gagne) et
        on n'efface qu'une fois (drapeau) pour ne pas retirer un fichier à chaque
        frame. Best-effort : un échec ici ne doit jamais empêcher le dock."""
        try:
            import app as A
            done = {"v": False}

            def _ok():
                if done["v"]:
                    return
                done["v"] = True
                A._qml_launch_ok()
            for obj in self._engine.rootObjects():
                sig = getattr(obj, "frameSwapped", None)
                if sig is not None:
                    sig.connect(_ok)
            # Filet temporel : en mode fantôme la pilule démarre masquée → aucun
            # rendu → frameSwapped ne viendrait jamais. Or une fenêtre masquée ne
            # sollicite pas le GPU (aucun abort possible) : si la boucle tient
            # 6 s, le lancement est sain — on efface aussi par ce biais.
            QTimer.singleShot(6000, _ok)
        except Exception as e:
            core.log_err("qml_guard", e)

    def _connect(self):
        self._sig_show.connect(self._do_show)
        self._sig_hide.connect(self._do_hide)
        self._sig_level.connect(self._do_level)
        self._sig_modes.connect(self._toggle_menu)
        self._sig_prefs.connect(self._sync_prefs)
        self._sig_settings.connect(self._do_open_settings)
        self._sig_quit.connect(self._do_quit)

    def _do_open_settings(self):
        """Ouvre les Réglages QML EN PROCESS (fil GUI). Repli : ancienne fenêtre
        (processus webview) si le QML échoue → « jamais de plantage »."""
        try:
            if self._settings_view is not None:
                self._settings_view.show()
                self._settings_view.raise_()
                return
        except Exception:
            self._settings_view = None
        try:
            import qmlsettings
            self._settings_view = qmlsettings.open_settings(self._app)
            return
        except Exception as e:
            core.log_err("qml_settings_open", e)
        try:
            self._on_settings()                 # repli webview (processus séparé)
        except Exception as e:
            core.log_err("qml_settings_fallback", e)

    # ---- préférences (config → pont) ----
    def _sync_prefs(self):
        self._bridge.dockPosition = str(core.CFG.get("dock_position") or "bottom-center")
        self._bridge.dockOpacity = _clamp_opacity(core.CFG.get("dock_opacity", 1.0))
        self._bridge.orbColor = _valid_hex(core.CFG.get("orb_color"))
        self._bridge.pttKey = (core.CFG.get("ptt_key") or "").upper()
        if not self._bridge.bubbleShown:
            self._bridge.pillShown = not bool(core.CFG.get("dock_ghost"))

    def _install_config_watch(self):
        """La fenêtre Réglages (processus séparé) écrit config.json → on recharge
        et ré-applique en direct (comme le dock QPainter)."""
        try:
            from PySide6.QtCore import QFileSystemWatcher
            self._cfg_path = core._path("config.json")
            self._watcher = QFileSystemWatcher()
            if os.path.exists(self._cfg_path):
                self._watcher.addPath(self._cfg_path)
            self._watcher.fileChanged.connect(self._on_config_changed)
        except Exception as e:
            core.log_err("qml_watch", e)

    def _on_config_changed(self, path):
        try:
            core.reload_config()
            import app
            app._resync_state_from_config()
        except Exception:
            pass
        self._sync_prefs()
        try:
            if path and os.path.exists(path) and path not in self._watcher.files():
                self._watcher.addPath(path)
        except Exception:
            pass

    # ---- slots (fil GUI) ----
    def _do_show(self, state, text, sub):
        if not self._ready:
            return
        if self._hide_timer:
            self._hide_timer.stop()
        labels = {"repos": "Prête", "listening": "Je t'écoute…",
                  "thinking": "Un instant…", "ok": "Collé", "error": "—"}
        self._bridge.menuShown = False
        self._bridge.state = state
        self._bridge.bubbleText = text or labels.get(state, "")
        self._bridge.bubbleSub = sub or ""
        self._bridge.pillShown = True
        self._bridge.bubbleShown = True

    def _do_hide(self, ms):
        if not self._ready:
            return
        if self._hide_timer:
            self._hide_timer.stop()
        self._hide_timer = QTimer()
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._finish_hide)
        self._hide_timer.start(max(0, ms))

    def _finish_hide(self):
        self._bridge.bubbleShown = False
        self._bridge.state = "repos"
        if bool(core.CFG.get("dock_ghost")):
            self._bridge.pillShown = False

    def _do_level(self, rms):
        if self._ready:
            self._bridge.level = max(0.0, min(1.0, float(rms) * 14.0))

    def _toggle_menu(self):
        if not self._ready:
            return
        if self._bridge.menuShown:
            self._bridge.menuShown = False
            return
        self._bridge.modesJson = json.dumps(self._current_modes())
        self._bridge.currentMode = str(core.CFG.get("mode") or "auto")
        self._bridge.menuShown = True

    def _current_modes(self):
        import modes_registry
        import licensing
        try:
            tier = licensing.current_tier()
        except Exception:
            tier = None
        out = []
        for m in modes_registry.all_modes():
            try:
                ok = licensing.mode_allowed(m["id"], tier)
            except Exception:
                ok = True
            out.append({"id": m["id"], "label": m["label"], "allowed": bool(ok),
                        "lock": "" if ok else "NÉCESSITE NOVA ULTRA"})
        return out

    def _pick_mode(self, mode_id):
        self._bridge.menuShown = False
        try:
            self._on_select_mode(mode_id)
        except Exception as e:
            core.log_err("qml_setmode", e)

    def _do_quit(self):
        try:
            if self._app:
                self._app.quit()
        except Exception:
            pass
