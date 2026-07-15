"""Fenêtre Réglages en QML (Qt Quick) — pour le dock QML, EN PROCESS (plus de
sous-processus webview). Pont `SettingsBridge` : lecture des réglages courants et
écriture VIA LES FONCTIONS EXISTANTES de app.py (`_toggle_cloud`, `_set_profile`,
`_apply_stt_opts`, `licensing.activate`) — donc AUCUNE logique dupliquée et aucun
comportement cassé. Racine QML = Item, hébergée par un QQuickView (fenêtre
frameless translucide → coins arrondis).
"""
from __future__ import annotations

import json
import os
import time
import webbrowser

from PySide6.QtCore import QObject, QUrl, Qt, Signal, Slot, Property
from PySide6.QtQuick import QQuickView

import core
import licensing


def _g(attr):
    return lambda self: getattr(self, attr)


def _profiles_json():
    """Les trois profils de puissance (lexique CLAUDE.md : Nova Air/Aura/Apex)."""
    return json.dumps([
        {"id": "normal", "label": "Nova Air", "hint": "léger et vif"},
        {"id": "eleve", "label": "Nova Aura", "hint": "le meilleur équilibre"},
        {"id": "ultra", "label": "Nova Apex", "hint": "intelligence maximale"},
    ])


class SettingsBridge(QObject):
    cloudOnChanged = Signal()
    canTurboChanged = Signal()
    profileIdChanged = Signal()
    latencyMinChanged = Signal()
    orbColorChanged = Signal()
    dockPositionChanged = Signal()
    offlineStateChanged = Signal()
    licTextChanged = Signal()

    closeRequested = Signal()
    dragRequested = Signal()

    def __init__(self):
        super().__init__()
        self._profilesJson = _profiles_json()
        self._cloudOn = False
        self._canTurbo = True
        self._profileId = "normal"
        self._latencyMin = True
        self._orbColor = ""
        self._dockPosition = "bottom-center"
        self._offlineState = "Intelligence privée"
        self._offlineColor = "#98989F"
        self._licText = ""
        self._licColor = "#98989F"
        self._refresh()

    # ---- lecture (config → pont) ----
    def _refresh(self):
        stt = core.CFG.get("stt") or {}
        self._cloudOn = bool(stt.get("cloud_enabled"))
        try:
            self._canTurbo = bool(licensing.has("cloud_stt"))
        except Exception:
            self._canTurbo = True
        self._profileId = str(core.CFG.get("profile") or "normal")
        self._latencyMin = stt.get("live", True) is not False
        self._orbColor = str(core.CFG.get("orb_color") or "")
        self._dockPosition = str(core.CFG.get("dock_position") or "bottom-center")
        self._refresh_license()

    def _refresh_license(self):
        try:
            st = licensing.status()
            if not st.get("active"):
                self._licText = "Version complète (licences non activées)."
                self._licColor = "#98989F"
            elif st.get("tier") == licensing.FREE:
                q = licensing.quota_status()
                self._licText = ("Version : Gratuit — %s/%s reformulations aujourd'hui "
                                 "· dictée illimitée." % (q.get("used", 0), q.get("limit", 0)))
                self._licColor = "#98989F"
            else:
                exp = ("licence perpétuelle" if not st.get("expiry")
                       else "expire le " + time.strftime(
                           "%d/%m/%Y", time.localtime(st["expiry"])))
                self._licText = "Version : %s — %s." % (
                    str(st.get("tier", "")).capitalize(), exp)
                self._licColor = "#30D158"
        except Exception as e:
            core.log_err("qml_lic", e)
            self._licText = "État de licence indisponible."
            self._licColor = "#98989F"

    # ---- Property ----
    profilesJson = Property(str, _g("_profilesJson"), constant=True)
    cloudOn = Property(bool, _g("_cloudOn"), notify=cloudOnChanged)
    canTurbo = Property(bool, _g("_canTurbo"), notify=canTurboChanged)
    profileId = Property(str, _g("_profileId"), notify=profileIdChanged)
    latencyMin = Property(bool, _g("_latencyMin"), notify=latencyMinChanged)
    orbColor = Property(str, _g("_orbColor"), notify=orbColorChanged)
    dockPosition = Property(str, _g("_dockPosition"), notify=dockPositionChanged)
    offlineState = Property(str, _g("_offlineState"), notify=offlineStateChanged)
    offlineColor = Property(str, _g("_offlineColor"), notify=offlineStateChanged)
    licText = Property(str, _g("_licText"), notify=licTextChanged)
    licColor = Property(str, _g("_licColor"), notify=licTextChanged)

    # ---- slots (écriture : réutilisent app.py) ----
    @Slot(bool)
    def setCloud(self, v):
        try:
            import app
            if bool(v) != bool((core.CFG.get("stt") or {}).get("cloud_enabled")):
                app._toggle_cloud()
        except Exception as e:
            core.log_err("qml_setcloud", e)
        self._cloudOn = bool((core.CFG.get("stt") or {}).get("cloud_enabled"))
        self.cloudOnChanged.emit()

    @Slot(str)
    def setProfile(self, pid):
        try:
            import app
            app._set_profile(pid, silent=True)
        except Exception as e:
            core.log_err("qml_setprofile", e)
        self._profileId = str(core.CFG.get("profile") or "normal")
        self.profileIdChanged.emit()

    @Slot(bool)
    def setLatency(self, v):
        try:
            import app
            app._apply_stt_opts({"live": bool(v)})
        except Exception as e:
            core.log_err("qml_setlatency", e)
        self._latencyMin = (core.CFG.get("stt") or {}).get("live", True) is not False
        self.latencyMinChanged.emit()

    @Slot(str)
    def setOrbColor(self, hx):
        hx = "" if hx in (None, "") else str(hx)
        try:
            core.save_config({"orb_color": hx})
        except Exception as e:
            core.log_err("qml_orb", e)
        self._orbColor = hx
        self.orbColorChanged.emit()

    @Slot(str)
    def setDockPosition(self, pid):
        try:
            core.save_config({"dock_position": str(pid)})
        except Exception as e:
            core.log_err("qml_dockpos", e)
        self._dockPosition = str(pid)
        self.dockPositionChanged.emit()

    @Slot(str)
    def activate(self, key):
        try:
            res = licensing.activate((key or "").strip())
            if not res.get("ok"):
                self._licText = res.get("error", "Clé invalide.")
                self._licColor = "#E7A08F"
                self.licTextChanged.emit()
                return
        except Exception as e:
            core.log_err("qml_activate", e)
            self._licText = "Activation impossible."
            self._licColor = "#E7A08F"
            self.licTextChanged.emit()
            return
        self._refresh()               # licence + gating Turbo ré-évalués
        for s in (self.licTextChanged, self.canTurboChanged, self.cloudOnChanged):
            s.emit()

    @Slot()
    def upgrade(self):
        try:
            webbrowser.open("https://novaspeak.app/#tarifs")
        except Exception:
            pass

    @Slot()
    def close(self):
        self.closeRequested.emit()

    @Slot()
    def startDrag(self):
        self.dragRequested.emit()


def open_settings(app_instance):
    """Ouvre la fenêtre Réglages QML EN PROCESS (fil GUI). Retourne le QQuickView
    (à conserver côté appelant pour qu'il ne soit pas ramassé). Lève si le QML ne
    charge pas → l'appelant retombe sur l'ancienne fenêtre."""
    import app as A
    bridge = SettingsBridge()
    view = QQuickView()
    view.setFlags(Qt.Window | Qt.FramelessWindowHint)
    view.setColor(Qt.transparent)
    view.setResizeMode(QQuickView.SizeRootObjectToView)
    view.resize(760, 540)
    view.setTitle("Nova — Réglages")
    view.rootContext().setContextProperty("settings", bridge)
    bridge.closeRequested.connect(view.close)
    bridge.dragRequested.connect(view.startSystemMove)
    qml = A.resource_path(os.path.join("qml", "Settings.qml"))
    view.setSource(QUrl.fromLocalFile(qml))
    if view.status() == QQuickView.Error:
        for e in view.errors():
            core.log_err("qml_settings_qml", e.toString())
        raise RuntimeError("Settings.qml non chargé")
    view._bridge = bridge          # garde une réf forte au pont
    view.show()
    view.raise_()
    return view
