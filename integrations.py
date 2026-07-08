# -*- coding: utf-8 -*-
"""Intégrations réseau (nova-produit) :
- détection de connectivité (ping léger, jamais bloquant),
- Groq Whisper : reconnaissance vocale cloud opt-in.

Tout le reste (Twilio, Microsoft Graph, Gmail/Agenda/Docs, Spotify, météo) a été
retiré avec le pivot dictée — archivé dans la branche v2-full-archive.
"""

import io
import threading
import time
import wave

import winext

# ---------------------------------------------------------- connectivité ----

_online = {"value": False}


def is_online():
    return _online["value"]


def _check_once():
    try:
        import requests
        r = requests.head("https://www.gstatic.com/generate_204", timeout=2.5)
        return r.status_code in (204, 200)
    except Exception:
        return False


def start_connectivity_loop():
    def loop():
        while True:
            _online["value"] = _check_once()
            time.sleep(20)
    threading.Thread(target=loop, daemon=True).start()


# ------------------------------------------------------------ Groq (STT) ----

def groq_transcribe(audio_f32, language="fr", model="whisper-large-v3-turbo", prompt=""):
    """Whisper cloud (opt-in). audio_f32 : np.float32 16 kHz mono."""
    import numpy as np
    import requests
    key = winext.get_secret("groq")
    if not key:
        raise RuntimeError("clé Groq absente")
    pcm = (np.clip(audio_f32, -1, 1) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm)
    buf.seek(0)
    data = {"model": model, "language": language}
    if prompt:
        data["prompt"] = prompt[:200]
    r = requests.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {key}"},
        files={"file": ("audio.wav", buf, "audio/wav")},
        data=data, timeout=12)
    r.raise_for_status()
    return (r.json().get("text") or "").strip()
