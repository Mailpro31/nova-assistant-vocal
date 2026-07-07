# -*- coding: utf-8 -*-
"""
Banc de mesure de la pipeline STT de Nova (BRIEF.md, Phase 1).

Synthétise des commandes vocales françaises (SAPI, 16 kHz), les mélange à un
bruit routier synthétique à plusieurs rapports signal/bruit (SNR), les passe
dans la VRAIE pipeline de core.py (transcribe / transcribe_quick), et mesure
le WER (taux d'erreur sur les mots) et la latence.

Le même banc, relancé après une modification de core.py, donne l'avant/après.
Lancer :  .venv\\Scripts\\python.exe bench_stt.py            (Nova.exe fermé)
          .venv\\Scripts\\python.exe bench_stt.py --snr 5 0  (SNR ciblés)

Rien n'est modifié dans core.py par ce fichier : il ne fait que mesurer.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import unicodedata
import wave

import numpy as np

import core
import modes

# La console Windows redirigée est en cp1252 : force l'UTF-8 pour les
# caractères « ═ » « » « → » des tableaux, sinon UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SR = 16000
CACHE = os.path.join(os.environ.get("TEMP", "."), "nova_bench_wav")
os.makedirs(CACHE, exist_ok=True)

# Commandes représentatives d'un usage EN CONDUITE (courtes, mains occupées).
# (phrase, intention attendue de modes.classify) — l'intention est ce qui
# compte vraiment : « dix minutes » et « 10 minutes » donnent le même timer.
CASES = [
    ("Nova appelle Paul", "call"),
    ("mets un minuteur de dix minutes", "timer"),
    ("va à la gare de Lyon", "navigation"),
    ("mets du jazz sur Spotify", "music"),
    ("monte le son", "media"),
    ("envoie un message à Marie j'arrive bientôt", "message"),
    ("quelle est la météo à Paris", "weather"),
    ("ouvre Google Maps", "open"),
    ("rappelle-moi d'acheter du pain dans une heure", "timer"),
    ("mets la chanson suivante", "media"),
    ("mets le volume à trente", "volume"),
    ("ouvre Spotify", "open"),
]
PHRASES = [c[0] for c in CASES]

# variantes orthographiques qui ne sont PAS des erreurs pour l'assistant
_DIGITS = {"zero": "0", "un": "1", "une": "1", "deux": "2", "trois": "3",
           "quatre": "4", "cinq": "5", "six": "6", "sept": "7", "huit": "8",
           "neuf": "9", "dix": "10", "onze": "11", "douze": "12", "quinze": "15",
           "vingt": "20", "trente": "30", "quarante": "40", "cinquante": "50",
           "soixante": "60", "cent": "100"}


# ----------------------------------------------------------------- outils ----

def _norm(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    words = "".join(c if c.isalnum() or c == " " else " " for c in t).split()
    # « dix » ≡ « 10 » : variante d'écriture, pas une erreur de reconnaissance
    return [_DIGITS.get(w, w) for w in words if w]


def wer(ref, hyp):
    """Taux d'erreur sur les mots (Levenshtein au niveau mot), en %."""
    r, h = _norm(ref), _norm(hyp)
    if not r:
        return 0.0 if not h else 100.0
    d = np.zeros((len(r) + 1, len(h) + 1), dtype=int)
    d[:, 0] = np.arange(len(r) + 1)
    d[0, :] = np.arange(len(h) + 1)
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + cost)
    return 100.0 * d[len(r), len(h)] / len(r)


def synth(text):
    """Voix Windows (SAPI) → mono 16 kHz float32. Mis en cache par phrase."""
    path = os.path.join(CACHE, "".join(c if (c.isascii() and c.isalnum()) else "_"
                                       for c in text)[:60] + ".wav")
    if not os.path.exists(path):
        safe = text.replace("'", "''")          # échappe l'apostrophe PowerShell
        ps = ("Add-Type -AssemblyName System.Speech;"
              "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
              "$f=New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo("
              "16000,[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,"
              "[System.Speech.AudioFormat.AudioChannel]::Mono);"
              f"$s.SetOutputToWaveFile('{path}',$f);$s.Speak('{safe}');$s.Dispose()")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       check=True, capture_output=True, timeout=60)
    with wave.open(path, "rb") as w:
        pcm = w.readframes(w.getnframes())
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0


def road_noise(n, seed):
    """Bruit routier synthétique : grondement moteur/route basse fréquence
    (bruit brownien) + souffle pneus/vent (bande médiane). Déterministe."""
    rng = np.random.default_rng(seed)
    white = rng.standard_normal(n)
    brown = np.cumsum(white)                    # -6 dB/oct : domine le grave
    brown /= (np.max(np.abs(brown)) or 1)
    # souffle : bruit blanc atténué en aigu (moyenne glissante = passe-bas doux)
    hiss = np.convolve(rng.standard_normal(n), np.ones(8) / 8, mode="same")
    hiss /= (np.max(np.abs(hiss)) or 1)
    mix = 0.85 * brown + 0.15 * hiss
    return mix / (np.sqrt(np.mean(mix ** 2)) or 1)   # RMS = 1


def mix_snr(speech, snr_db, seed):
    """Mélange voix + bruit routier au SNR voulu (dB). SNR haut = clair."""
    noise = road_noise(len(speech), seed)
    s_rms = np.sqrt(np.mean(speech ** 2)) or 1e-9
    gain = s_rms / (10 ** (snr_db / 20))         # RMS bruit visé
    out = speech + gain * noise
    peak = np.max(np.abs(out)) or 1
    return (out / peak * 0.97).astype(np.float32)  # anti-saturation


# ----------------------------------------------------------------- mesure ----

def intent_ok(hyp, expected):
    """L'intention est-elle correctement reconnue ? (le vrai objectif d'un
    assistant : « dix minutes » ou « 10 minutes » donnent le même timer)."""
    try:
        r = modes.classify(hyp)
    except Exception:
        r = None
    return r is not None and r[0] == expected


def run(snr_levels, paths):
    print(f"Modèles : whisper_model={core.CFG['whisper_model']}  "
          f"wake_model={core.CFG['wake_model']}  "
          f"compute=int8  prompt={len(core.stt_prompt())} car.\n")
    core.transcribe(np.zeros(SR, dtype=np.float32))          # préchauffage
    core.transcribe_quick(np.zeros(SR, dtype=np.float32))

    results = {}
    for label, fn in paths:
        print(f"═══ Chemin « {label} » ═══")
        print(f"  {'condition':<11} {'WER':>6}  {'intention':>10}  {'latence':>8}")
        for snr in snr_levels:
            wers, lats, hits = [], [], 0
            for i, (phrase, exp) in enumerate(CASES):
                clean = synth(phrase)
                audio = clean if snr is None else mix_snr(clean, snr, seed=i + 1)
                t0 = time.time()
                hyp = fn(audio)
                lats.append(time.time() - t0)
                wers.append(wer(phrase, hyp))
                hits += intent_ok(hyp, exp)
            tag = "propre" if snr is None else f"SNR {snr:+d} dB"
            mw, ml = float(np.mean(wers)), float(np.mean(lats))
            print(f"  {tag:<11} {mw:5.1f}%  {hits:2d}/{len(CASES)} ok  {ml:6.2f}s")
            results[f"{label}/{tag}"] = {"wer": round(mw, 1),
                                         "intent": f"{hits}/{len(CASES)}",
                                         "lat": round(ml, 2)}
        print()
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snr", type=int, nargs="*", default=None)
    ap.add_argument("--tag", default="baseline", help="étiquette du run (JSON)")
    args = ap.parse_args()
    snr = [None, 5, 0, -5] if args.snr is None else args.snr

    paths = [
        ("précis (small, beam 5)", lambda a: core.transcribe(a)),
        # chemin commande RÉEL de production (transcribe_routed fast) : suit
        # automatiquement le modèle/beam/prompt utilisés au volant → avant/après
        ("rapide (chemin commande réel)", lambda a: core.transcribe_routed(a, fast=True)[0]),
    ]
    res = run(snr, paths)
    out = os.path.join(CACHE, f"bench_{args.tag}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print("Résultats →", out)


if __name__ == "__main__":
    main()
