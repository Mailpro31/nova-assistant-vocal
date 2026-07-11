# -*- coding: utf-8 -*-
"""Assistant de bienvenue (1er lancement) : vidéo d'ambiance en fond + étapes
« Suivant » qui configurent réellement l'app (touche push-to-talk, profil de
puissance, langue, local/cloud). Ne s'affiche qu'une fois — `CFG["onboarding_done"]`.

Rendu en HTML (onboarding/onboarding.html) via pywebview : la façon la plus
simple d'obtenir vidéo + son + animations soignées sans réinventer un lecteur
vidéo en tkinter (pas de VLC à installer, pas de mux audio/vidéo maison).
pywebview n'est utilisé QUE pour cet écran ponctuel — pilule, tray et Réglages
restent tkinter/pystray, inchangés. `import webview` reste local à `run()` :
le reste de l'app (et la CI, qui n'installe pas pywebview) n'en dépend jamais.
"""

import os

import core
import licensing
import modes_registry
import power_profiles

VIDEO_PATH = core.resource_path(os.path.join("assets", "onboarding.mp4"))
HTML_PATH = core.resource_path(os.path.join("onboarding", "onboarding.html"))


def needs_onboarding():
    return not core.CFG.get("onboarding_done")


def video_url():
    """file:// vers la vidéo si elle a été déposée dans assets/onboarding.mp4,
    sinon "" — l'écran affiche alors un simple dégradé de secours, jamais
    d'erreur si l'utilisateur n'a pas encore fourni son montage."""
    if os.path.isfile(VIDEO_PATH):
        return "file:///" + VIDEO_PATH.replace("\\", "/")
    return ""


class Api:
    """Pont JS → Python exposé à la page onboarding.html. Chaque méthode
    réutilise EXACTEMENT la même logique que le menu tray / la fenêtre
    Réglages (aucune règle de configuration dupliquée)."""

    def state(self):
        hw = power_profiles.detect_hardware()
        return {
            "modes": [{"id": m["id"], "label": m["label"], "hotkey": m["hotkey"]}
                     for m in modes_registry.all_modes()],
            "profiles": power_profiles.evaluate(hw, licensing.has("power_profiles")),
            "hardware": hw,
            "languages": [{"code": c, "label": lbl} for c, lbl in core.LANGUAGES],
            "ptt_key": core.CFG.get("ptt_key", "f9"),
            "language": core.CFG.get("language", "fr"),
            "cloud_enabled": bool(core.CFG.get("stt", {}).get("cloud_enabled")),
            "video_url": video_url(),
        }

    def set_ptt_key(self, key):
        key = (key or "").strip().lower()
        if key:
            core.save_config({"ptt_key": key})
        return core.CFG.get("ptt_key")

    def set_profile(self, profile_id):
        """Sélection bornée à ce que la machine encaisse — même séquence que le
        tray (`power_profiles.select_and_apply`) : jamais de profil instable."""
        return power_profiles.select_and_apply(profile_id, core.save_config,
                                               licensing.has("power_profiles"))

    def set_language(self, code):
        core.save_config({"language": code})
        return code

    def set_cloud(self, enabled):
        stt = dict(core.CFG.get("stt", {}))
        stt["cloud_enabled"] = bool(enabled)
        core.save_config({"stt": stt, "provider": "auto" if enabled else "ollama"})
        return bool(enabled)

    def finish(self):
        """Ferme la fenêtre ; `run()` marque l'onboarding fait à la sortie,
        que la fermeture vienne d'ici ou d'un clic sur la croix de la fenêtre."""
        import webview
        if webview.windows:
            webview.windows[0].destroy()


def run():
    """Affiche l'assistant (bloquant, thread principal). Marque l'onboarding
    fait même si la fenêtre est fermée manuellement — jamais de reboucle."""
    import webview
    webview.create_window(
        "Bienvenue sur Nova", HTML_PATH, width=880, height=620,
        resizable=False, js_api=Api())
    webview.start()
    core.save_config({"onboarding_done": True})
