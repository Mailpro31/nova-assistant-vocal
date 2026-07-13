"""Dock NATIF (PySide6/Qt) — remplace le dock WebView.

Pourquoi natif : une fenêtre flottante toujours-au-dessus a besoin d'une vraie
transparence par pixel. WebView2 ne sait pas la faire de façon fiable (sa vue
DirectComposition laisse transparaître le fond du formulaire hôte → le
« rectangle » que voyait l'utilisateur), et embarquer Chromium le fait ramer.
Qt, lui, a la transparence NATIVE (`WA_TranslucentBackground`) : la pilule et la
bulle flottent réellement, coins arrondis, aucun rectangle POSSIBLE — et c'est
léger (plus de moteur web en tâche de fond).

Même langage visuel que `ui/dock.html` (mêmes icônes SVG, même orbe « bille de
verre », mêmes teintes). API compatible WebDock/Pill (`show/hide/level/
open_settings/open_modes/refresh_prefs/destroy/serve`) → `main()` ne teste aucun
type. Pas d'`open_tray_menu` : le menu du tray reste le menu natif pystray
complet (Styles / Réglages / MàJ / Quitter). Tout appel venant d'un autre fil
(audio, clavier) est marshalé vers le fil GUI par signaux Qt (thread-safe).
"""
from __future__ import annotations

import os
import sys
import threading

from PySide6.QtCore import Qt, QObject, QTimer, QRectF, QPointF, Signal
from PySide6.QtGui import (QColor, QPainter, QRadialGradient, QLinearGradient,
                           QPainterPath, QFont, QPixmap, QIcon, QGuiApplication)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QApplication, QWidget, QHBoxLayout, QVBoxLayout,
                               QLabel)

import core

# ---------------------------------------------------------------- charte -----
CARD      = "#16181F"     # teinte des surfaces (pilule, bulle, menu)
CARD_HI   = "#1E212B"     # surface un peu plus claire (bulle)
EDGE      = QColor(255, 255, 255, 30)     # hairline
TXT       = "#F1F3FA"
TXT2      = "#AAB2C4"      # icônes au repos
TXT3      = "#7C8398"      # sous-titres
ACCENT    = "#0A84FF"      # bleu Apple — action unique
OK_TXT    = "#BFE9D2"
ERR_TXT   = "#F0C8B4"
FONT_STACK = "SF Pro Display, SF Pro Text, Segoe UI, Inter, system-ui, sans-serif"

# accents d'orbe par état (mi-dégradé de la « bille de verre »)
ORB_ACC = {
    "repos":     (0x9D, 0xB0, 0xDD),   # périwinkle
    "listening": (0x8F, 0xB4, 0xFF),   # bleu plus vif
    "thinking":  (0xB6, 0xA8, 0xE6),   # lavande
    "ok":        (0x8F, 0xCF, 0xB2),   # menthe
    "error":     (0xE0, 0xA8, 0x90),   # chaud
}

# icônes : EXACTEMENT les tracés de ui/dock.html (mêmes glyphes)
_SVG_GEAR = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
             'fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round" '
             'stroke-linejoin="round"><circle cx="12" cy="12" r="3.2"/><path d="M19 '
             '12a7 7 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14 2h-4l-.5 '
             '2.6a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6A7 7 0 0 0 5 12a7 7 0 0 0 .1 '
             '1.2l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 2 1.2L10 22h4l.5-2.6a7 7 0 0 0 '
             '2-1.2l2.4 1 2-3.4-2-1.6A7 7 0 0 0 19 12z"/></svg>')
_SVG_STAR = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
             'fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round" '
             'stroke-linejoin="round"><path d="M12 3l1.6 3.8L17.5 8l-2.8 2.7.7 '
             '4-3.4-1.9L8.6 14.7l.7-4L6.5 8z"/></svg>')
_SVG_CHECK = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
              'fill="none" stroke="{c}" stroke-width="2.4" stroke-linecap="round" '
              'stroke-linejoin="round"><path d="M4 12.5l5 5L20 6"/></svg>')


def _svg_pixmap(svg_tpl, px, color=TXT2, dpr=2.0):
    """Rend un glyphe SVG en QPixmap net (haute densité)."""
    svg = svg_tpl.format(c=color)
    ren = QSvgRenderer(svg.encode("utf-8"))
    pm = QPixmap(int(px * dpr), int(px * dpr))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    ren.render(p)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def _orb_accent():
    """Override utilisateur (#RRGGBB) sinon None → accent par état."""
    hx = str(core.CFG.get("orb_color", "") or "").strip().lstrip("#")
    if len(hx) == 6:
        try:
            return (int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16))
        except ValueError:
            return None
    return None


# ============================================================= l'orbe ========
class NovaOrb(QWidget):
    """« Bille de verre » peinte au QPainter (dégradés radiaux) : identité de
    Nova, sans WebGL (donc jamais de plantage renderer, léger sur toute machine).
    Respire en douceur au repos et enfle avec le niveau audio pendant la dictée.
    """

    def __init__(self, diameter=40, parent=None):
        super().__init__(parent)
        self._d = diameter
        self.setFixedSize(diameter, diameter)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._state = "repos"
        self._level = 0.0          # cible (0..1) posée par le fil audio
        self._lvl_s = 0.0          # niveau lissé
        self._phase = 0.0          # respiration
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)      # ~30 fps PENDANT l'activité (s'arrête au repos)

    def set_state(self, state):
        self._state = state if state in ORB_ACC else "repos"
        self._wake()
        self.update()

    def set_level(self, rms):
        # même échelle que la pilule tkinter d'origine (rms*14, borné)
        self._level = max(0.0, min(1.0, float(rms) * 14.0))
        if self._level > 0.02:
            self._wake()

    def _wake(self):
        """Relance l'animation dès qu'il se passe quelque chose (état/niveau)."""
        if not self._timer.isActive():
            self._timer.start(33)

    def _tick(self):
        # lissage du niveau (attaque vive, chute douce) + respiration lente
        tgt = self._level
        self._lvl_s += (tgt - self._lvl_s) * (0.5 if tgt > self._lvl_s else 0.12)
        self._level *= 0.85        # décroissance de la cible entre deux mesures
        self._phase += 0.045
        self.update()
        # AU REPOS, orbe stabilisée et son retombé → on ARRÊTE le timer : plus
        # aucun réveil 30×/s en continu (batterie ; c'était le reproche « trop
        # lourd »). Il repart au moindre changement d'état / de niveau (_wake).
        if self._state == "repos" and self._lvl_s < 0.015 and self._level < 0.015:
            self._timer.stop()

    def showEvent(self, e):
        self._wake()
        super().showEvent(e)

    def hideEvent(self, e):
        self._timer.stop()         # caché (mode ghost) : aucun réveil
        super().hideEvent(e)

    def paintEvent(self, _e):
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = h = self._d
        breathe = 0.965 + 0.035 * math.sin(self._phase)        # 0.93..1.0
        scale = breathe + 0.16 * self._lvl_s                    # enfle avec le son
        d = w * min(1.0, scale)
        cx, cy = w / 2.0, h / 2.0
        r = d / 2.0
        acc = _orb_accent() or ORB_ACC.get(self._state, ORB_ACC["repos"])
        ar, ag, ab = acc
        # corps : dégradé radial verre (clair en haut-gauche → accent → sombre)
        g = QRadialGradient(cx - r * 0.28, cy - r * 0.34, r * 1.28)
        g.setColorAt(0.0, QColor(255, 255, 255))
        g.setColorAt(0.30, QColor(min(255, ar + 60), min(255, ag + 58), min(255, ab + 46)))
        g.setColorAt(0.66, QColor(ar, ag, ab))
        g.setColorAt(1.0, QColor(int(ar * 0.52), int(ag * 0.54), int(ab * 0.62)))
        p.setBrush(g)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), r, r)
        # halo lumineux quand le son monte (écoute)
        if self._lvl_s > 0.02:
            glow = QRadialGradient(cx, cy, r * 1.7)
            a = int(90 * self._lvl_s)
            glow.setColorAt(0.55, QColor(ar, ag, ab, a))
            glow.setColorAt(1.0, QColor(ar, ag, ab, 0))
            p.setBrush(glow)
            p.drawEllipse(QPointF(cx, cy), r * 1.7, r * 1.7)
        # reflet spéculaire (petite tache blanche en haut-gauche)
        spec = QRadialGradient(cx - r * 0.34, cy - r * 0.40, r * 0.55)
        spec.setColorAt(0.0, QColor(255, 255, 255, 235))
        spec.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(spec)
        p.drawEllipse(QPointF(cx - r * 0.30, cy - r * 0.36), r * 0.42, r * 0.34)
        p.end()


# ================================================= fenêtres flottantes ========
class _Card(QWidget):
    """Fenêtre frameless translucide toujours-au-dessus, qui NE prend jamais le
    focus (la fenêtre active de l'utilisateur reste active : détection auto +
    collage fiables). Peint elle-même sa carte arrondie opaque + hairline."""

    def __init__(self, radius=16):
        super().__init__(None)
        self._radius = radius
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool | Qt.WindowDoesNotAcceptFocus
                            | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)
        p.fillPath(path, QColor(CARD))
        p.setPen(EDGE)
        p.drawPath(path)
        p.end()


class _IconButton(QWidget):
    """Bouton d'icône 44×44 (zone tactile), glyphe SVG centré, halo au survol.
    Ne prend jamais le focus ; clic → callback (sans activer la fenêtre)."""

    def __init__(self, svg_tpl, on_click, tip=""):
        super().__init__()
        self.setFixedSize(44, 44)
        self._svg = svg_tpl
        self._cb = on_click
        self._hover = False
        self._pm = _svg_pixmap(svg_tpl, 19, TXT2)
        self.setCursor(Qt.PointingHandCursor)
        if tip:
            self.setToolTip(tip)

    def enterEvent(self, _e):
        self._hover = True
        self._pm = _svg_pixmap(self._svg, 19, TXT)
        self.update()

    def leaveEvent(self, _e):
        self._hover = False
        self._pm = _svg_pixmap(self._svg, 19, TXT2)
        self.update()

    def mousePressEvent(self, _e):
        try:
            self._cb()
        except Exception as e:
            core.log_err("qt_btn", e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        if self._hover:
            p.setBrush(QColor(255, 255, 255, 16))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(2, 2, 40, 40, 12, 12)
        x = (self.width() - 19) / 2
        y = (self.height() - 19) / 2
        p.drawPixmap(int(x), int(y), self._pm)
        p.end()


class PillWindow(_Card):
    """La pilule : [réglages] | orbe | [Styles]. Coins pleinement arrondis."""

    def __init__(self, on_settings, on_styles):
        super().__init__(radius=28)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)
        self.gear = _IconButton(_SVG_GEAR, on_settings, "Réglages")
        self.orb = NovaOrb(40)
        self.star = _IconButton(_SVG_STAR, on_styles, "Styles")
        lay.addWidget(self.gear)
        lay.addWidget(self._sep())
        orbwrap = QWidget()
        ow = QHBoxLayout(orbwrap)
        ow.setContentsMargins(2, 0, 2, 0)
        ow.addWidget(self.orb)
        lay.addWidget(orbwrap)
        lay.addWidget(self._sep())
        lay.addWidget(self.star)
        self.adjustSize()

    def _sep(self):
        s = QWidget()
        s.setFixedSize(1, 22)
        s.setStyleSheet("background:rgba(255,255,255,0.10)")
        return s


class BubbleWindow(_Card):
    """Bulle d'état au-dessus de la pilule (Prête / J'écoute… / Collé…)."""

    def __init__(self):
        super().__init__(radius=16)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 9, 16, 9)
        lay.setSpacing(8)
        self.text = QLabel("Prête")
        self.text.setFont(QFont(FONT_STACK.split(",")[0].strip(), 10))
        self.text.setStyleSheet(f"color:{TXT};font-size:13px;font-family:{FONT_STACK}")
        self.sub = QLabel("")
        self.sub.setStyleSheet(f"color:{TXT3};font-size:11px;font-family:{FONT_STACK}")
        lay.addWidget(self.text)
        lay.addWidget(self.sub)

    def set_content(self, state, text, sub):
        self.text.setText(text or "")
        self.sub.setText(sub or "")
        col = OK_TXT if state == "ok" else ERR_TXT if state == "error" else TXT
        self.text.setStyleSheet(f"color:{col};font-size:13px;font-family:{FONT_STACK}")
        self.sub.setVisible(bool(sub))
        self.adjustSize()


class _ModeRow(QWidget):
    def __init__(self, mode, active, on_pick):
        super().__init__()
        self._id = mode["id"]
        self._allowed = mode.get("allowed", True)
        self._cb = on_pick
        self._active = active
        self._hover = False
        self.setFixedHeight(40)
        self.setCursor(Qt.PointingHandCursor if self._allowed else Qt.ArrowCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(10)
        lab = QLabel(mode["label"])
        col = TXT if self._allowed else TXT3
        lab.setStyleSheet(f"color:{col};font-size:13.5px;font-family:{FONT_STACK}")
        lay.addWidget(lab)
        lay.addStretch(1)
        if not self._allowed and mode.get("lock"):
            badge = QLabel(mode["lock"])
            badge.setStyleSheet(
                "color:#C9B6F0;font-size:8.5px;font-family:%s;"
                "background:rgba(201,182,240,0.14);border-radius:7px;"
                "padding:2px 7px" % FONT_STACK)
            lay.addWidget(badge)
        elif active:
            chk = QLabel()
            chk.setPixmap(_svg_pixmap(_SVG_CHECK, 15, ACCENT))
            lay.addWidget(chk)

    def enterEvent(self, _e):
        self._hover = True
        self.update()

    def leaveEvent(self, _e):
        self._hover = False
        self.update()

    def mousePressEvent(self, _e):
        if self._allowed:
            self._cb(self._id)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        if self._active:
            p.setBrush(QColor(10, 132, 255, 34))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(4, 2, self.width() - 8, self.height() - 4, 10, 10)
        elif self._hover and self._allowed:
            p.setBrush(QColor(255, 255, 255, 14))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(4, 2, self.width() - 8, self.height() - 4, 10, 10)
        p.end()


class MenuWindow(_Card):
    """Menu des Styles au-dessus de la pilule (liste déroulante)."""

    def __init__(self, on_pick):
        super().__init__(radius=18)
        self._on_pick = on_pick
        self.setFixedWidth(268)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(6, 6, 6, 6)
        self._lay.setSpacing(2)

    def rebuild(self, modes, current):
        while self._lay.count():
            it = self._lay.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        for m in modes:
            self._lay.addWidget(_ModeRow(m, m["id"] == current, self._pick))
        self.adjustSize()

    def _pick(self, mode_id):
        self.hide()
        try:
            self._on_pick(mode_id)
        except Exception as e:
            core.log_err("qt_pick", e)


# ============================================================ contrôleur ======
class QtDock(QObject):
    """API publique identique à WebDock/Pill. Les appels venant d'autres fils
    (audio : level ~30×/s ; clavier : raccourcis) sont marshalés vers le fil GUI
    par signaux Qt — jamais de widget touché hors du fil GUI (règle stricte Qt).
    """

    _sig_show   = Signal(str, str, str)
    _sig_hide   = Signal(int)
    _sig_level  = Signal(float)
    _sig_modes  = Signal()
    _sig_prefs  = Signal()
    _sig_quit   = Signal()

    def __init__(self, on_settings, on_select_mode):
        # Le tray natif (pystray) porte déjà MàJ/Quitter/Réglages via les
        # fonctions de app.py — le dock n'a besoin que d'ouvrir les Réglages
        # (engrenage) et de choisir un Style (menu).
        super().__init__()
        self._on_settings = on_settings
        self._on_select_mode = on_select_mode
        self._app = None
        self._pill = self._bubble = self._menu = None
        self._hide_timer = None
        self._ready = False
        self._watcher = None

    # ---- API thread-safe (émet, le slot s'exécute sur le fil GUI) ----
    def show(self, state, text="", sub=""):
        self._sig_show.emit(state, text or "", sub or "")

    def hide(self, delay=0.0):
        self._sig_hide.emit(int(delay * 1000))

    def level(self, rms):
        self._sig_level.emit(float(rms))

    def open_settings(self):
        # action pure Python (lance le processus Réglages) → pas besoin du GUI
        try:
            self._on_settings()
        except Exception as e:
            core.log_err("qt_settings", e)

    def open_modes(self):
        self._sig_modes.emit()

    def refresh_prefs(self):
        self._sig_prefs.emit()

    def destroy(self):
        self._sig_quit.emit()

    # ---- cycle de vie : possède le fil PRINCIPAL (comme la pilule tkinter) ----
    def serve(self, build_tray):
        """Qt possède le fil principal ; le tray (pystray) tourne en fond."""
        import app as A
        # AppUserModelID AVANT toute fenêtre : Windows associe alors le process à
        # l'icône Nova (barre des tâches / notifications), quel que soit le cache
        # d'icônes du raccourci. No-op hors Windows.
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "NovaSpeak.Nova")
        except Exception:
            pass
        self._app = QApplication.instance() or QApplication(sys.argv[:1])
        self._app.setQuitOnLastWindowClosed(False)
        try:
            self._app.setWindowIcon(QIcon(A.resource_path("icon.ico")))
        except Exception:
            pass
        self._connect()           # AVANT _build : aucune mise à jour d'état/niveau
        self._build()             # précoce n'est perdue (slots déjà branchés)
        A._rebind_ptt()
        # tray en fil de fond (le fil principal est à Qt), comme WebDock
        A._tray_icon = build_tray()
        threading.Thread(target=A._tray_icon.run, daemon=True).start()
        core.install_freeze_watchdog()
        # battement du fil GUI → détecteur de gel (comme le battement JS du dock
        # web) : si le fil GUI se bloque, le watchdog vide les piles dans le log
        self._beat = QTimer()
        self._beat.timeout.connect(core.heartbeat)
        self._beat.start(1000)
        self._app.exec()

    def _build(self):
        self._pill = PillWindow(self.open_settings, self._toggle_menu)
        self._bubble = BubbleWindow()
        self._menu = MenuWindow(self._pick_mode)
        self._ready = True
        self._place_pill()
        if not core.CFG.get("dock_ghost"):
            self._pill.show()
        # La fenêtre Réglages tourne dans un AUTRE processus (webview) tant que le
        # dock est natif : elle écrit config.json → on surveille le fichier et on
        # recharge/ré-applique en direct (position, taille, opacité, orbe, ghost).
        try:
            from PySide6.QtCore import QFileSystemWatcher
            self._cfg_path = core._path("config.json")
            self._watcher = QFileSystemWatcher()
            if os.path.exists(self._cfg_path):
                self._watcher.addPath(self._cfg_path)
            self._watcher.fileChanged.connect(self._on_config_changed)
        except Exception as e:
            core.log_err("qt_watch", e)

    def _on_config_changed(self, path):
        core.reload_config()
        try:
            import app
            app._resync_state_from_config()   # mode/profil (changés dans Réglages)
        except Exception:
            pass
        self._place_pill()
        if core.CFG.get("dock_ghost"):
            if not self._bubble.isVisible():
                self._pill.hide()
        else:
            self._pill.show()
        if self._pill.orb:
            self._pill.orb.update()
        # certains enregistrements REMPLACENT le fichier (le watch se perd) : réarme
        try:
            if path and os.path.exists(path) and path not in self._watcher.files():
                self._watcher.addPath(path)
        except Exception:
            pass

    def _connect(self):
        self._sig_show.connect(self._do_show)
        self._sig_hide.connect(self._do_hide)
        self._sig_level.connect(self._do_level)
        self._sig_modes.connect(self._toggle_menu)
        self._sig_prefs.connect(self._place_pill)
        self._sig_quit.connect(self._do_quit)

    # ---- placement (zone de travail = hors barre des tâches) ----
    def _anchor(self):
        scr = QGuiApplication.primaryScreen()
        if scr is not None:
            a = scr.availableGeometry()
        else:                      # aucun écran énuméré (session déconnectée…)
            from PySide6.QtCore import QRect
            a = QRect(0, 0, 1920, 1080)
        pos = str(core.CFG.get("dock_position") or "bottom-center")
        vert, _, horiz = pos.partition("-")
        return a, vert, horiz

    def _place_pill(self):
        if not self._ready:
            return
        # opacité utilisateur (Réglages) appliquée à la fenêtre entière. NB : la
        # taille « Petite » (dock_scale) n'est pas encore honorée par le dock
        # natif — à suivre avec le portage Qt des Réglages.
        op = 1.0
        try:
            op = max(0.55, min(1.0, float(core.CFG.get("dock_opacity", 1.0) or 1.0)))
        except (TypeError, ValueError):
            op = 1.0
        self._pill.setWindowOpacity(op)
        self._pill.adjustSize()
        a, vert, horiz = self._anchor()
        pw, ph = self._pill.width(), self._pill.height()
        m = 16
        x = {"left": a.left() + m,
             "right": a.right() - pw - m}.get(horiz, a.left() + (a.width() - pw) // 2)
        y = (a.top() + m) if vert == "top" else (a.bottom() - ph - m)
        self._pill.move(int(x), int(y))

    def _above_pill(self, win, gap=10):
        """Positionne `win` juste au-dessus (ou dessous en ancrage haut) de la
        pilule, centré sur elle."""
        pg = self._pill.geometry()
        win.adjustSize()
        _a, vert, _h = self._anchor()
        cx = pg.center().x()
        x = int(cx - win.width() / 2)
        if vert == "top":
            y = pg.bottom() + gap
        else:
            y = pg.top() - win.height() - gap
        win.move(x, int(y))

    # ---- slots (fil GUI) ----
    def _do_show(self, state, text, sub):
        if not self._ready:
            return
        if self._hide_timer:
            self._hide_timer.stop()
        self._menu.hide()
        labels = {"repos": "Prête", "listening": "Je t'écoute…",
                  "thinking": "Un instant…", "ok": "Collé", "error": "—"}
        self._pill.show()
        self._pill.orb.set_state(state)
        self._bubble.set_content(state, text or labels.get(state, ""), sub)
        self._above_pill(self._bubble)
        self._bubble.show()

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
        self._bubble.hide()
        self._pill.orb.set_state("repos")
        if core.CFG.get("dock_ghost"):
            self._pill.hide()

    def _do_level(self, rms):
        if self._ready:
            self._pill.orb.set_level(rms)

    def _toggle_menu(self):
        if not self._ready:
            return
        if self._menu.isVisible():
            self._menu.hide()
            return
        modes = self._current_modes()
        self._menu.rebuild(modes, str(core.CFG.get("mode") or "auto"))
        self._above_pill(self._menu)
        self._menu.show()

    def _current_modes(self):
        """Liste des Styles + verrou, calculée comme DockApi.state() (pas de
        règle dupliquée)."""
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
            out.append({"id": m["id"], "label": m["label"], "allowed": ok,
                        "lock": "" if ok else "NÉCESSITE NOVA ULTRA"})
        return out

    def _pick_mode(self, mode_id):
        try:
            self._on_select_mode(mode_id)
        except Exception as e:
            core.log_err("qt_setmode", e)

    def _do_quit(self):
        try:
            if self._app:
                self._app.quit()
        except Exception:
            pass


# --------------------------------------------------------- démo / vérif ------
def _demo():
    """Rend chaque surface sur un faux « bureau » pour vérifier le rendu hors
    Windows (QT_QPA_PLATFORM=offscreen). Écrit des PNG dans le dossier courant."""
    app = QApplication(sys.argv[:1])

    def bg(w, h):
        pm = QPixmap(w, h)
        g = QLinearGradient(0, 0, w, h)
        g.setColorAt(0, QColor("#2b6cb0"))
        g.setColorAt(1, QColor("#6b46c1"))
        p = QPainter(pm)
        p.fillRect(0, 0, w, h, g)
        p.end()
        return pm

    def composite(widget, name, pad=40):
        widget.adjustSize()
        app.processEvents()        # laisse Qt finaliser la mise en page
        widget.repaint()
        shot = widget.grab()
        W, H = shot.width() + pad * 2, shot.height() + pad * 2
        canvas = bg(W, H)
        p = QPainter(canvas)
        p.drawPixmap(pad, pad, shot)
        p.end()
        canvas.save(name)
        print("wrote", name, shot.width(), "x", shot.height())

    pill = PillWindow(lambda: None, lambda: None)
    composite(pill, "demo_pill.png")
    b = BubbleWindow()
    b.set_content("listening", "Je t'écoute…", "")
    composite(b, "demo_bubble.png")
    b2 = BubbleWindow()
    b2.set_content("ok", "Collé", "Style E-mail")
    composite(b2, "demo_bubble_ok.png")
    menu = MenuWindow(lambda i: None)
    menu.rebuild([
        {"id": "auto", "label": "Automatique", "allowed": True, "lock": ""},
        {"id": "email", "label": "E-mail", "allowed": True, "lock": ""},
        {"id": "todo", "label": "To-do list", "allowed": True, "lock": ""},
        {"id": "pro", "label": "Compte rendu", "allowed": False,
         "lock": "NÉCESSITE NOVA ULTRA"},
    ], "email")
    composite(menu, "demo_menu.png")


if __name__ == "__main__":
    _demo()
