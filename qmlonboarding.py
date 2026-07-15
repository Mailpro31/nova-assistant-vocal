"""Assistant de premier lancement en QML (Qt Quick) — pour le mode dock QML.

Bloquant (comme l'onboarding tkinter) : ouvre un QQuickView et tourne une boucle
d'évènements LOCALE jusqu'à « Terminer ». Réutilise EXACTEMENT les setters de
onboarding.py (`set_ptt_key/set_profile/set_language/set_cloud`) → configuration
identique, rien de dupliqué. N'est employé que si un QApplication existe déjà
(donc que le dock QML est actif) ; sinon l'appelant retombe sur l'onboarding
tkinter.
"""
from __future__ import annotations

import json
import os

from PySide6.QtCore import QObject, QUrl, Qt, QEventLoop, Signal, Slot, Property
from PySide6.QtQuick import QQuickView

import core
import licensing
import onboarding


def _g(attr):
    return lambda self: getattr(self, attr)


def _languages_json():
    return json.dumps([{"code": c, "label": lbl} for c, lbl in core.LANGUAGES])


def _profiles_json():
    return json.dumps([
        {"id": "normal", "label": "Nova Air", "hint": "léger et vif"},
        {"id": "eleve", "label": "Nova Aura", "hint": "le meilleur équilibre"},
        {"id": "ultra", "label": "Nova Apex", "hint": "intelligence maximale"},
    ])


class OnboardingBridge(QObject):
    stepChanged = Signal()
    pttKeyChanged = Signal()
    profileIdChanged = Signal()
    languageChanged = Signal()
    cloudChanged = Signal()
    finished = Signal()
    dragRequested = Signal()

    N_STEPS = 6

    def __init__(self):
        super().__init__()
        self._step = 0
        self._languagesJson = _languages_json()
        self._profilesJson = _profiles_json()
        self._pttKey = str(core.CFG.get("ptt_key", "f9") or "f9").upper()
        self._profileId = str(core.CFG.get("profile") or "normal")
        self._language = str(core.CFG.get("language") or "auto")
        self._cloud = bool((core.CFG.get("stt") or {}).get("cloud_enabled"))
        try:
            self._canTurbo = bool(licensing.has("cloud_stt"))
        except Exception:
            self._canTurbo = True

    nSteps = Property(int, lambda self: self.N_STEPS, constant=True)
    languagesJson = Property(str, _g("_languagesJson"), constant=True)
    profilesJson = Property(str, _g("_profilesJson"), constant=True)
    canTurbo = Property(bool, _g("_canTurbo"), constant=True)
    step = Property(int, _g("_step"), notify=stepChanged)
    pttKey = Property(str, _g("_pttKey"), notify=pttKeyChanged)
    profileId = Property(str, _g("_profileId"), notify=profileIdChanged)
    language = Property(str, _g("_language"), notify=languageChanged)
    cloud = Property(bool, _g("_cloud"), notify=cloudChanged)

    @Slot()
    def goNext(self):
        if self._step < self.N_STEPS - 1:
            self._step += 1
            self.stepChanged.emit()

    @Slot()
    def goPrev(self):
        if self._step > 0:
            self._step -= 1
            self.stepChanged.emit()

    @Slot(str)
    def setKey(self, key):
        try:
            onboarding.set_ptt_key(key)
        except Exception as e:
            core.log_err("qml_onb_key", e)
        self._pttKey = str(core.CFG.get("ptt_key", "f9") or "f9").upper()
        self.pttKeyChanged.emit()

    @Slot(str)
    def setProfile(self, pid):
        try:
            onboarding.set_profile(pid)
        except Exception as e:
            core.log_err("qml_onb_profile", e)
        self._profileId = str(core.CFG.get("profile") or "normal")
        self.profileIdChanged.emit()

    @Slot(str)
    def setLanguage(self, code):
        try:
            onboarding.set_language(code)
        except Exception as e:
            core.log_err("qml_onb_lang", e)
        self._language = code
        self.languageChanged.emit()

    @Slot(bool)
    def setCloud(self, v):
        try:
            self._cloud = bool(onboarding.set_cloud(bool(v)))
        except Exception as e:
            core.log_err("qml_onb_cloud", e)
            self._cloud = False
        self.cloudChanged.emit()

    @Slot()
    def finish(self):
        self.finished.emit()

    @Slot()
    def startDrag(self):
        self.dragRequested.emit()


def run_qml():
    """Ouvre l'assistant QML et BLOQUE jusqu'à « Terminer ». Lève si aucun
    QApplication n'existe (le dock n'est pas en mode QML) → repli tkinter."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("pas de QApplication — onboarding QML indisponible")
    import app as A
    bridge = OnboardingBridge()
    view = QQuickView()
    view.setFlags(Qt.Window | Qt.FramelessWindowHint)
    view.setColor(Qt.transparent)
    view.setResizeMode(QQuickView.SizeRootObjectToView)
    view.resize(700, 560)
    view.setTitle("Bienvenue sur Nova")
    view.rootContext().setContextProperty("onb", bridge)
    loop = QEventLoop()

    def _done():
        try:
            view.close()
        except Exception:
            pass
        loop.quit()
    bridge.finished.connect(_done)
    bridge.dragRequested.connect(view.startSystemMove)
    qml = A.resource_path(os.path.join("qml", "Onboarding.qml"))
    view.setSource(QUrl.fromLocalFile(qml))
    if view.status() == QQuickView.Error:
        for e in view.errors():
            core.log_err("qml_onb_qml", e.toString())
        raise RuntimeError("Onboarding.qml non chargé")
    # centre l'écran
    try:
        scr = app.primaryScreen().availableGeometry()
        view.setPosition(scr.x() + (scr.width() - view.width()) // 2,
                         scr.y() + (scr.height() - view.height()) // 2)
    except Exception:
        pass
    view.show()
    view.raise_()
    loop.exec()
