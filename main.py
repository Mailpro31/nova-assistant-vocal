# -*- coding: utf-8 -*-
"""
Assistant vocal Windows
-----------------------
Raccourci global (Ctrl+Alt+Espace par défaut) -> micro -> transcription Whisper (local)
-> interprétation : règles simples, puis IA (Ollama local ou API Claude) en secours
-> exécution : ouvrir des sites, lancer des applications, recherches web.

Configuration : config.json / commands.json (à côté de ce fichier ou de l'exe).
"""

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.parse
import webbrowser
import winsound

import numpy as np
import sounddevice as sd
import keyboard

APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))

DEFAULT_CONFIG = {
    "hotkey": "ctrl+alt+space",
    "whisper_model": "small",          # tiny / base / small / medium (qualité vs vitesse)
    "language": "fr",
    "llm_mode": "auto",                # auto / claude / ollama / off
    "claude_api_key": "",              # ou variable d'environnement ANTHROPIC_API_KEY
    "claude_model": "claude-haiku-4-5",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "qwen2.5:3b",
    "max_record_seconds": 12,
    "silence_seconds": 1.2,
    "silence_threshold": 0.01,
}

LLM_SYSTEM = (
    "Tu es le cerveau d'un assistant vocal Windows. L'utilisateur vient de dicter une commande "
    "vocale (transcrite automatiquement, elle peut contenir de petites erreurs).\n"
    "Réponds UNIQUEMENT avec un objet JSON de la forme :\n"
    '{"action": "open_url" | "open_app" | "web_search" | "none", "target": "...", "reply": "..."}\n'
    "- open_url : target est une URL complète (https://...). Choisis l'URL la plus utile "
    "(ex. \"va sur mes vidéos youtube\" -> https://www.youtube.com/feed/history).\n"
    "- open_app : target est un exécutable Windows (notepad, calc, explorer, mspaint...), "
    "un URI d'application (spotify:, ms-settings:) ou un chemin complet.\n"
    "- web_search : target contient les termes de recherche.\n"
    "- none : demande incompréhensible ou impossible ; explique pourquoi dans reply.\n"
    "reply est une confirmation très courte en français (ex. \"J'ouvre YouTube\")."
)

LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["open_url", "open_app", "web_search", "none"]},
        "target": {"type": "string"},
        "reply": {"type": "string"},
    },
    "required": ["action", "target", "reply"],
    "additionalProperties": False,
}


def load_json(name, default):
    path = os.path.join(APP_DIR, name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)
        return default


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(load_json("config.json", DEFAULT_CONFIG))
    return cfg


CFG = load_config()
COMMANDS = load_json("commands.json", [])
_busy = threading.Lock()
_model = None
_model_lock = threading.Lock()


# ---------------------------------------------------------------- overlay ---

class Overlay(threading.Thread):
    """Petite fenêtre flottante en bas de l'écran (tkinter dans son propre thread)."""

    def __init__(self):
        super().__init__(daemon=True)
        self.q = queue.Queue()

    def run(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1e1e2e")
        self.label = tk.Label(self.root, text="", font=("Segoe UI", 14),
                              fg="white", bg="#1e1e2e", padx=26, pady=14)
        self.label.pack()
        self.root.after(80, self._poll)
        self.root.mainloop()

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg is None:
                    self.root.withdraw()
                else:
                    text, color = msg
                    self.label.config(text=text, fg=color)
                    self.root.update_idletasks()
                    w = self.root.winfo_reqwidth()
                    h = self.root.winfo_reqheight()
                    sw = self.root.winfo_screenwidth()
                    sh = self.root.winfo_screenheight()
                    self.root.geometry(f"+{(sw - w) // 2}+{sh - h - 120}")
                    self.root.deiconify()
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def show(self, text, color="white"):
        self.q.put((text, color))

    def hide(self):
        self.q.put(None)


overlay = Overlay()


# ---------------------------------------------------------------- audio -----

def record_audio():
    """Enregistre jusqu'à un silence prolongé (ou timeout). Retourne float32 16 kHz ou None."""
    sr = 16000
    frames = []
    started = False
    silence_start = None
    t0 = time.time()
    with sd.InputStream(samplerate=sr, channels=1, dtype="float32") as stream:
        while True:
            block, _ = stream.read(int(sr * 0.1))
            frames.append(block.copy())
            rms = float(np.sqrt(np.mean(block ** 2)))
            now = time.time()
            if rms > CFG["silence_threshold"]:
                started = True
                silence_start = None
            elif started:
                if silence_start is None:
                    silence_start = now
                elif now - silence_start > CFG["silence_seconds"]:
                    break
            if now - t0 > CFG["max_record_seconds"]:
                break
            if not started and now - t0 > 5:
                break
    if not started:
        return None
    return np.concatenate(frames).flatten()


def get_model():
    global _model
    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel
            _model = WhisperModel(CFG["whisper_model"], device="cpu", compute_type="int8")
    return _model


def transcribe(audio):
    segments, _info = get_model().transcribe(audio, language=CFG["language"], beam_size=5,
                                             vad_filter=True)
    return " ".join(s.text for s in segments).strip()


# ---------------------------------------------------------------- cerveau ---

def normalize(text):
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def interpret_rules(text):
    n = normalize(text).strip(" .!?")
    for cmd in COMMANDS:
        for kw in cmd.get("keywords", []):
            if normalize(kw) in n:
                return {"action": cmd["action"], "target": cmd["target"],
                        "reply": cmd.get("reply", cmd.get("name", "OK"))}
    m = re.search(r"\b(?:recherche|cherche|google)\s+(.{2,})", n)
    if m:
        return {"action": "web_search", "target": m.group(1),
                "reply": f"Je cherche « {m.group(1)} »"}
    return None


def resolve_llm_mode():
    mode = CFG.get("llm_mode", "auto")
    if mode != "auto":
        return mode
    if CFG.get("claude_api_key") or os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    try:
        import requests
        requests.get(CFG["ollama_url"] + "/api/tags", timeout=0.8)
        return "ollama"
    except Exception:
        return "off"


def ask_claude(text):
    from anthropic import Anthropic
    client = Anthropic(api_key=CFG.get("claude_api_key") or None)
    msg = client.messages.create(
        model=CFG.get("claude_model", "claude-haiku-4-5"),
        max_tokens=300,
        system=LLM_SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": LLM_SCHEMA}},
        messages=[{"role": "user", "content": text}],
    )
    raw = next(b.text for b in msg.content if b.type == "text")
    return json.loads(raw)


def ask_ollama(text):
    import requests
    resp = requests.post(
        CFG["ollama_url"] + "/api/chat",
        json={
            "model": CFG["ollama_model"],
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": LLM_SYSTEM},
                {"role": "user", "content": text},
            ],
        },
        timeout=60,
    )
    resp.raise_for_status()
    return json.loads(resp.json()["message"]["content"])


def interpret(text):
    result = interpret_rules(text)
    if result:
        return result
    mode = resolve_llm_mode()
    if mode == "claude":
        return ask_claude(text)
    if mode == "ollama":
        return ask_ollama(text)
    return None


# ---------------------------------------------------------------- actions ---

def execute(result):
    action = result.get("action")
    target = (result.get("target") or "").strip()
    if action == "open_url":
        if not target.lower().startswith(("http://", "https://")):
            target = "https://" + target
        webbrowser.open(target)
    elif action == "open_app":
        try:
            os.startfile(target)
        except OSError:
            subprocess.Popen(f'start "" "{target}"', shell=True)
    elif action == "web_search":
        webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(target))
    else:
        return False
    return True


# ---------------------------------------------------------------- flux ------

def listen_flow():
    if not _busy.acquire(blocking=False):
        return
    try:
        winsound.Beep(880, 120)
        overlay.show("🎤 J'écoute…", "#a6e3a1")
        audio = record_audio()
        if audio is None:
            overlay.show("Je n'ai rien entendu", "#f38ba8")
            time.sleep(1.5)
            return
        winsound.Beep(660, 100)
        overlay.show("⏳ Je réfléchis…", "#f9e2af")
        text = transcribe(audio)
        if not text:
            overlay.show("Je n'ai pas compris", "#f38ba8")
            time.sleep(1.5)
            return
        overlay.show(f"« {text} »")
        try:
            result = interpret(text)
        except Exception as e:
            overlay.show(f"Erreur IA : {e}", "#f38ba8")
            time.sleep(3)
            return
        if result and result.get("action") != "none" and execute(result):
            overlay.show("✅ " + result.get("reply", "C'est fait"), "#a6e3a1")
        elif result:
            overlay.show("🤷 " + (result.get("reply") or "Je ne peux pas faire ça"), "#f38ba8")
        else:
            overlay.show("🤷 Commande inconnue (aucune IA configurée)", "#f38ba8")
        time.sleep(2.2)
    finally:
        overlay.hide()
        _busy.release()


def on_hotkey():
    threading.Thread(target=listen_flow, daemon=True).start()


# ---------------------------------------------------------------- tray ------

def make_icon_image():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (30, 30, 46, 255))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([24, 8, 40, 38], radius=8, fill=(137, 180, 250, 255))
    d.arc([16, 20, 48, 50], 0, 180, fill=(205, 214, 244, 255), width=4)
    d.line([32, 50, 32, 58], fill=(205, 214, 244, 255), width=4)
    return img


def main():
    import pystray

    overlay.start()
    # Précharge le modèle Whisper en arrière-plan (téléchargé au premier lancement)
    threading.Thread(target=get_model, daemon=True).start()

    keyboard.add_hotkey(CFG["hotkey"], on_hotkey)

    def quit_app(icon, _item):
        icon.stop()
        os._exit(0)

    hotkey_label = CFG["hotkey"].replace("+", " + ").title()
    icon = pystray.Icon(
        "assistant-vocal",
        make_icon_image(),
        f"Assistant vocal ({hotkey_label})",
        menu=pystray.Menu(
            pystray.MenuItem(f"🎤 Écouter ({hotkey_label})", lambda i, it: on_hotkey(), default=True),
            pystray.MenuItem("Quitter", quit_app),
        ),
    )
    icon.run()


if __name__ == "__main__":
    main()
