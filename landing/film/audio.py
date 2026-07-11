# -*- coding: utf-8 -*-
"""Bande-son du film Nova v3 — bruitages présents et « satisfaisants » (numpy).

Aucun sample externe : tout est synthétisé — thock de touche mécanique, ticks
de frappe, POP de reformulation, swoosh d'envoi, coches de to-do, marimba des
Styles, cloche Ultra, verrou feutré, whoosh Turbo, cliquet accéléré du
compteur, accord final — sur un pad ambiant discret. Chaque événement est calé
sur la timeline de cinematic.html (16 plans, ~40 s). Sortie :
nova-film-audio.wav (partagé FR/EN, minutage identique).
"""
import struct
import wave

import numpy as np

SR = 44100
DUR = 40.4
N = int(SR * DUR)
buf = np.zeros(N, dtype=np.float64)


def at(t):
    return int(t * SR)


def add(sig, t, gain=1.0):
    """Mixe sig dans buf à l'instant t (secondes)."""
    i = at(t)
    j = min(N, i + len(sig))
    if i >= N:
        return
    buf[i:j] += sig[: j - i] * gain


def env(n, attack, release, hold=0.0, curve=2.0):
    """Enveloppe douce (attaque courte, longue chute) — jamais de clic dur."""
    a = max(1, int(attack * SR))
    h = int(hold * SR)
    e = np.ones(n)
    a = min(a, n)
    e[:a] = np.linspace(0, 1, a) ** 1.4
    dec_start = min(n, a + h)
    rel = n - dec_start
    if rel > 0:
        e[dec_start:] = np.linspace(1, 0, rel) ** curve
    return e


def bell(freq, dur, gain=1.0, decay=3.0, inharm=1.0):
    """Cloche chaude : partiels à décroissance exponentielle."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    partials = [(1.0, 1.0), (2.0 * inharm, 0.5), (3.0 * inharm, 0.28),
                (4.2 * inharm, 0.12), (5.4 * inharm, 0.06)]
    out = np.zeros(n)
    for mult, amp in partials:
        out += amp * np.sin(2 * np.pi * freq * mult * t) * np.exp(-t * decay * (0.7 + mult * 0.15))
    out *= env(n, 0.004, dur, curve=1.0)
    return out / 1.9 * gain


def sub_tone(freq, dur, gain=1.0):
    """Sinusoïde grave (impact doux sous le wordmark)."""
    n = int(dur * SR)
    s = np.sin(2 * np.pi * freq * np.arange(n) / SR)
    return s * env(n, 0.05, dur * 0.7) * gain


def click(dur=0.05, freq=1800, gain=1.0):
    """Tick feutré : bruit filtré passe-bas très court + partiel."""
    n = int(dur * SR)
    noise = np.random.RandomState(int(freq)).randn(n)
    k = 40
    noise = np.convolve(noise, np.ones(k) / k, mode="same")
    tone = np.sin(2 * np.pi * freq * np.arange(n) / SR) * 0.5
    s = (noise * 0.6 + tone) * np.exp(-np.arange(n) / SR * 60)
    return s / (np.max(np.abs(s)) + 1e-9) * gain


def thock(gain=1.0):
    """Touche mécanique feutrée : corps grave + souffle bref — le « thock »."""
    dur = 0.16
    n = int(dur * SR)
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * 105 * t) * np.exp(-t * 34)
    knock = np.sin(2 * np.pi * 210 * t) * np.exp(-t * 55) * 0.5
    noise = np.random.RandomState(11).randn(n)
    noise = np.convolve(noise, np.ones(70) / 70, mode="same") * np.exp(-t * 80) * 0.9
    s = body + knock + noise
    s *= env(n, 0.001, dur, curve=1.3)
    s = np.tanh(s * 1.6)
    return s / (np.max(np.abs(s)) + 1e-9) * gain


def pop(gain=1.0, f0=620.0):
    """Pop de reformulation : sinus qui glisse vers le bas + sub court."""
    dur = 0.34
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f0 * np.exp(-t * 7) + 180
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t * 9)
    sub = np.sin(2 * np.pi * 90 * t) * np.exp(-t * 12) * 0.5
    s = body + sub
    s *= env(n, 0.002, dur, curve=1.4)
    s = np.tanh(s * 1.3)
    return s / (np.max(np.abs(s)) + 1e-9) * gain


def thunk(gain=1.0):
    """Verrou feutré : basse courte + loquet discret."""
    dur = 0.4
    n = int(dur * SR)
    t = np.arange(n) / SR
    low = np.sin(2 * np.pi * 84 * t) * np.exp(-t * 10)
    mid = np.sin(2 * np.pi * 150 * t) * np.exp(-t * 16) * 0.4
    s = low + mid
    s *= env(n, 0.003, dur, curve=1.6)
    latch = click(0.04, 2200, 0.25)
    s[: len(latch)] += latch * 0.6
    return s / (np.max(np.abs(s)) + 1e-9) * gain


def whoosh(dur=0.75, gain=1.0, up=True):
    """Whoosh : bruit filtré + glissando (montant = envoi/Turbo)."""
    n = int(dur * SR)
    noise = np.random.RandomState(99).randn(n)
    k = 30
    lp = np.convolve(noise, np.ones(k) / k, mode="same")
    rise = np.linspace(0, 1, n) ** 0.6
    if not up:
        rise = rise[::-1]
    gliss = np.sin(2 * np.pi * np.cumsum(200 + 900 * rise) / SR) * 0.25
    s = (lp * (0.5 + 0.5 * rise) + gliss)
    s *= np.sin(np.pi * np.linspace(0, 1, n)) ** 1.2
    return s / (np.max(np.abs(s)) + 1e-9) * gain


def chord(freqs, dur, gain=1.0, attack=0.6, release=None):
    n = int(dur * SR)
    out = np.zeros(n)
    for f in freqs:
        out += np.sin(2 * np.pi * f * np.arange(n) / SR)
        out += 0.3 * np.sin(2 * np.pi * f * 2 * np.arange(n) / SR)
    out *= env(n, attack, release if release else dur * 0.5, curve=1.3)
    return out / (len(freqs) * 1.3) * gain


def pad():
    """Pad ambiant discret sur toute la durée (cohésion, non intrusif)."""
    t = np.arange(N) / SR
    voices = [110, 165, 220, 277]
    s = np.zeros(N)
    for i, f in enumerate(voices):
        det = 1 + 0.004 * np.sin(2 * np.pi * 0.05 * t + i)
        s += np.sin(2 * np.pi * f * det * t) * (0.6 - i * 0.1)
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.08 * t)
    s *= (0.35 + 0.65 * lfo)
    g = np.ones(N)
    fi = int(1.2 * SR)
    fo = int(2.2 * SR)
    g[:fi] = np.linspace(0, 1, fi) ** 1.5
    g[-fo:] = np.linspace(1, 0, fo) ** 1.5
    return s * g / (np.max(np.abs(s)) + 1e-9)


# ------------------------------------------------------------------ montage
np.random.seed(3)
buf += pad() * 0.10

# --- S1 [0–2.0] matérialisation : cloches + étoiles + sub sur « Nova »
add(bell(440.00, 2.2, 0.95, decay=2.2), 0.50)
add(bell(659.25, 2.0, 0.55, decay=2.4), 0.62)
add(bell(554.37, 2.0, 0.45, decay=2.6), 0.75)
for k, f in enumerate([1318, 1760, 2093]):
    add(bell(f, 1.1, 0.14, decay=5.0), 0.45 + k * 0.12)
add(sub_tone(55, 1.2, 0.55), 1.10)

# --- S2 [2.0–4.2] accroche : deux ticks doux + swell
add(click(0.05, 1500, 0.28), 2.20)
add(click(0.05, 1700, 0.24), 2.78)
add(chord([220, 330, 440], 1.9, 0.16, attack=0.8), 2.10)

# --- S3 [4.2–5.9] la touche : THOCK + shimmer de l'onde
add(thock(0.95), 4.65)
add(bell(1760, 0.9, 0.20, decay=5.5), 4.82)

# --- S4 [5.9–8.9] écoute : lit de souffle + ticks par mot dicté
bed_n = int(2.3 * SR)
_bed = np.random.RandomState(5).randn(bed_n)
_bed = np.convolve(_bed, np.ones(60) / 60, mode="same")
_bed *= np.sin(np.pi * np.linspace(0, 1, bed_n)) * 0.06
add(_bed, 6.15)
for k, tt in enumerate([6.35, 6.75, 7.15, 7.55, 7.95]):
    add(click(0.05, 1200 + k * 120, 0.22), tt)

# --- S5 [8.9] LE POP de reformulation + étincelle + coche
add(pop(1.00), 8.90)
add(bell(1760, 1.0, 0.30, decay=5.0), 9.15)
add(bell(2093, 0.8, 0.16, decay=6.0), 9.28)
add(bell(1568, 0.9, 0.30, decay=5.5), 9.58)          # la coche verte

# --- S6 [11.3–13.9] Messages : pop reçu, frappe, swoosh d'envoi
add(pop(0.45, f0=430.0), 11.60)
for k, tt in enumerate([12.20, 12.42, 12.64, 12.86, 13.05]):
    add(click(0.04, 1900 + k * 90, 0.13), tt)
add(whoosh(0.32, 0.55), 13.42)
add(bell(1976, 0.7, 0.22, decay=6.0), 13.62)

# --- S7 [13.9–16.4] To-do : lignes puis 3 coches ascendantes
for tt in (14.20, 14.42, 14.64):
    add(click(0.04, 1400, 0.10), tt)
for k, (tt, f) in enumerate(zip((14.90, 15.40, 15.90), (659.25, 783.99, 987.77))):
    add(click(0.05, 2100, 0.16), tt)
    add(bell(f, 0.8, 0.40 + k * 0.03, decay=5.0), tt + 0.02)

# --- S8 [16.4–18.6] Notes : marimba douce descendue posée
add(bell(440.00, 0.9, 0.30, decay=5.0), 16.70)
add(bell(554.37, 0.8, 0.26, decay=5.5), 17.05)
add(bell(659.25, 0.8, 0.26, decay=5.5), 17.40)

# --- S9 [18.6–21.2] Prompt IA : frappe légère + envoi deux-tons
for k in range(8):
    add(click(0.035, 1800 + (k % 3) * 140, 0.09), 18.95 + k * 0.17)
add(bell(659.25, 0.6, 0.28, decay=6.0), 20.60)
add(bell(880.00, 0.9, 0.34, decay=5.0), 20.72)

# --- S10 [21.2–24.7] Styles : marimba pentatonique, 5 marches
sty_notes = [220.0, 277.18, 329.63, 369.99, 440.0]
for k, tt in enumerate([21.30, 22.00, 22.70, 23.40, 24.10]):
    add(bell(sty_notes[k], 0.85, 0.46, decay=6.0), tt)
    add(click(0.04, 2400, 0.12), tt)

# --- S11 [24.7–26.9] Style sur mesure : cloche lumineuse Ultra
add(bell(659.25, 1.3, 0.42, decay=3.5), 24.95)
add(bell(880.00, 1.1, 0.26, decay=4.0), 25.12)
add(bell(1108.73, 0.9, 0.15, decay=5.5), 25.30)

# --- S12 [26.9–29.5] Intelligence privée : accord + verrou
add(chord([146.83, 220, 277.18], 2.0, 0.13, attack=0.9), 26.95)
add(thunk(0.95), 27.50)

# --- S13 [29.5–31.7] Turbo : whoosh + cloche brillante
add(whoosh(0.75, 0.70), 29.58)
add(bell(880, 1.1, 0.34, decay=4.0), 30.15)

# --- S14 [31.7–34.3] partout : cascade de 3 ticks + cloches
for k, tt in enumerate([31.95, 32.35, 32.75]):
    add(click(0.05, 1500 + k * 200, 0.20), tt)
    add(bell(sty_notes[k + 1], 0.7, 0.15, decay=6.5), tt)

# --- S15 [34.3–36.9] compteur : cliquet accéléré puis résolution
tt = 34.45
step = 0.15
kf = 0
while tt < 35.70:
    add(click(0.035, 900 + kf * 55, 0.14 + kf * 0.004), tt)
    tt += step
    step = max(0.05, step * 0.90)
    kf += 1
add(bell(880.00, 1.2, 0.40, decay=4.0), 36.05)
add(bell(1108.73, 1.0, 0.24, decay=4.5), 36.18)

# --- S16 [36.9–40.4] final : accord chaud + cloches
add(chord([220, 277.18, 329.63, 440, 554.37], 3.2, 0.28, attack=0.5), 36.95)
add(bell(440.00, 2.4, 0.45, decay=2.0), 37.50)
add(bell(659.25, 2.2, 0.26, decay=2.2), 37.65)
add(bell(1760.00, 1.4, 0.12, decay=4.5), 38.60)

# ------------------------------------------------------------------ mastering
# drive doux (relève le niveau moyen) puis normalisation à ~ -0.7 dBFS
buf = np.tanh(buf * 1.25)
peak = np.max(np.abs(buf)) + 1e-9
buf = buf / peak * 0.92

out = "/home/user/nova-assistant-vocal/landing/film/nova-film-audio.wav"
pcm16 = (np.clip(buf, -1, 1) * 32767).astype(np.int16)
with wave.open(out, "w") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(struct.pack("<%dh" % len(pcm16), *pcm16))

print("audio écrit:", out, "durée", round(len(pcm16) / SR, 2), "s")
