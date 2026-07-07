# -*- coding: utf-8 -*-
"""Test de bout en bout du mot d'éveil SANS micro : la voix Windows (SAPI)
synthétise « Nova, ouvre YouTube » en WAV 16 kHz, puis on passe l'audio dans
la vraie chaîne : transcribe_quick → wake_word_index → extraction commande.
Lancer : .venv\\Scripts\\python.exe test_wake.py (Nova.exe fermé)."""

import os
import subprocess
import sys
import wave

import numpy as np

import core

FAIL = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"  ({extra})" if extra else ""))
    if not cond:
        FAIL.append(name)


def synth(text, path):
    ps = (
        'Add-Type -AssemblyName System.Speech; '
        '$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
        '$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo('
        '16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, '
        '[System.Speech.AudioFormat.AudioChannel]::Mono); '
        f"$s.SetOutputToWaveFile('{path}', $fmt); "
        f"$s.Speak('{text}'); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   check=True, capture_output=True, timeout=60)


def load(path):
    with wave.open(path, "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1
        pcm = w.readframes(w.getnframes())
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0


wav = os.path.join(os.environ.get("TEMP", "."), "nova_wake_test.wav")
synth("Nova, ouvre YouTube", wav)
audio = load(wav)
check("synthèse WAV 16 kHz", len(audio) > 8000, f"{len(audio) / 16000:.1f} s")

text = core.transcribe_quick(audio, prompt="Nova.")
print(f"      transcription (modèle éveil) : « {text} »")
check("transcription non vide", bool(text))

import app  # noqa: E402  (mutex : lancer avec Nova.exe fermé)

idx = app.wake_word_index(text, "nova")
check("mot d'éveil trouvé", idx is not None, f"idx={idx}")

if idx is not None:
    after = " ".join(text.split()[idx + 1:]).strip(" ,.!?")
    print(f"      commande extraite : « {after} »")
    check("commande extraite après le mot d'éveil",
          len(after) >= 3 and "youtube" in core.normalize(after))

# tolérance : une lettre d'écart / ponctuation collée
check("fuzzy : « Nova. » (ponctuation)", app.wake_word_index("Nova. Ouvre le site", "nova") == 0)
check("fuzzy : « novah » (1 lettre)", app.wake_word_index("novah ouvre le site", "nova") == 0)
check("fuzzy : « no va » (coupé)", app.wake_word_index("no va ouvre le site", "nova") is not None)
check("fuzzy : pas de faux positif « bonjour »",
      app.wake_word_index("bonjour ouvre le site", "nova") is None)

print("\n" + ("WAKE TEST FAILED: " + ", ".join(FAIL) if FAIL else "WAKE TEST OK"))
sys.exit(1 if FAIL else 0)
