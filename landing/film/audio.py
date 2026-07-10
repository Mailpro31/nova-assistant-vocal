# -*- coding: utf-8 -*-
"""Bande-son du film Nova — synthèse douce et « satisfaisante » (numpy).

Aucun sample externe : tout est synthétisé (cloches chaudes, ticks feutrés,
pop de reformulation, marimba des Styles, verrou, whoosh Turbo, accord final)
sur un pad ambiant très discret. Les événements sont calés sur les beats de
la timeline de cinematic.html. Sortie : nova-film-audio.wav (partagé FR/EN,
le minutage des deux versions étant identique).
"""
import struct
import wave

import numpy as np

SR = 44100
DUR = 26.6
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
    """Enveloppe douce (attaque lente, longue chute) — jamais de clic dur."""
    a = max(1, int(attack * SR))
    h = int(hold * SR)
    r = max(1, int(release * SR))
    e = np.ones(n)
    a = min(a, n)
    e[:a] = np.linspace(0, 1, a) ** 1.4
    dec_start = min(n, a + h)
    rel = n - dec_start
    if rel > 0:
        e[dec_start:] = np.linspace(1, 0, rel) ** curve
    return e


def sine(freq, n, phase=0.0):
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * freq * t + phase)


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


def soft_tone(freq, dur, gain=1.0, attack=0.02, release=None, wave="sine", vib=0.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = freq * (1 + vib * np.sin(2 * np.pi * 5 * t))
    ph = 2 * np.pi * np.cumsum(f) / SR
    if wave == "tri":
        s = 2 / np.pi * np.arcsin(np.sin(ph))
    else:
        s = np.sin(ph)
    s *= env(n, attack, release if release else dur * 0.7)
    return s * gain


def click(dur=0.05, freq=1800, gain=1.0):
    """Tick feutré : bruit filtré passe-bas très court."""
    n = int(dur * SR)
    noise = np.random.RandomState(int(freq)).randn(n)
    # lissage passe-bas simple (moyenne glissante)
    k = 40
    noise = np.convolve(noise, np.ones(k) / k, mode="same")
    tone = np.sin(2 * np.pi * freq * np.arange(n) / SR) * 0.5
    s = (noise * 0.6 + tone) * np.exp(-np.arange(n) / SR * 60)
    return s / (np.max(np.abs(s)) + 1e-9) * gain


def pop(gain=1.0):
    """Pop de reformulation : sinus qui glisse vers le bas + petit clic doux."""
    dur = 0.34
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 620 * np.exp(-t * 7) + 180        # glide descendant
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t * 9)
    sub = np.sin(2 * np.pi * 90 * t) * np.exp(-t * 12) * 0.5
    s = body + sub
    s *= env(n, 0.002, dur, curve=1.4)
    s = np.tanh(s * 1.3)
    return s / (np.max(np.abs(s)) + 1e-9) * gain


def thunk(gain=1.0):
    """Verrou feutré : basse courte + latch discret."""
    dur = 0.4
    n = int(dur * SR)
    t = np.arange(n) / SR
    low = np.sin(2 * np.pi * 84 * t) * np.exp(-t * 10)
    mid = np.sin(2 * np.pi * 150 * t) * np.exp(-t * 16) * 0.4
    s = low + mid
    s *= env(n, 0.003, dur, curve=1.6)
    latch = click(0.04, 2200, 0.25)                 # petit « clac » de loquet
    s[: len(latch)] += latch * 0.6
    return s / (np.max(np.abs(s)) + 1e-9) * gain


def whoosh(dur=0.75, gain=1.0):
    """Whoosh Turbo : bruit à travers un passe-bande montant + glissando."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = np.random.RandomState(99).randn(n)
    # bandpass mobile approché : moduler l'amplitude d'un filtrage passe-bas variable
    k = 30
    lp = np.convolve(noise, np.ones(k) / k, mode="same")
    sweep = np.sin(2 * np.pi * (np.linspace(0.4, 1.0, n)) * 0.5)  # forme d'accent
    rise = np.linspace(0, 1, n) ** 0.6
    gliss = np.sin(2 * np.pi * np.cumsum(200 + 900 * rise) / SR) * 0.25
    s = (lp * (0.5 + 0.5 * rise) + gliss)
    s *= np.sin(np.pi * np.linspace(0, 1, n)) ** 1.2   # cloche d'amplitude
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
    """Pad ambiant très discret sur toute la durée (cohésion, non intrusif)."""
    t = np.arange(N) / SR
    # accord La majeur grave qui évolue lentement
    voices = [110, 165, 220, 277]
    s = np.zeros(N)
    for i, f in enumerate(voices):
        det = 1 + 0.004 * np.sin(2 * np.pi * 0.05 * t + i)
        s += np.sin(2 * np.pi * f * det * t) * (0.6 - i * 0.1)
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.08 * t)
    s *= (0.35 + 0.65 * lfo)
    # fondu d'entrée/sortie global
    g = np.ones(N)
    fi = int(1.2 * SR)
    fo = int(2.0 * SR)
    g[:fi] = np.linspace(0, 1, fi) ** 1.5
    g[-fo:] = np.linspace(1, 0, fo) ** 1.5
    return s * g / (np.max(np.abs(s)) + 1e-9)


# ------------------------------------------------------------------ montage
np.random.seed(3)

# pad de fond (très bas)
buf += pad() * 0.12

# --- Scène 1 : matérialisation de l'orbe (~0.7) + shimmer + wordmark
add(bell(440, 2.6, 0.9, decay=2.2), 0.7)          # La
add(bell(659.25, 2.4, 0.5, decay=2.4), 0.82)      # Mi
add(bell(554.37, 2.4, 0.4, decay=2.6), 0.95)      # Do#
for k, f in enumerate([1318, 1760, 2093]):        # petites étoiles
    add(bell(f, 1.2, 0.10, decay=5.0), 0.6 + k * 0.13)
add(soft_tone(55, 1.4, 0.5, attack=0.05, wave="sine"), 1.5)  # sub sur « Nova »

# --- Scène 2 : tagline — swell doux
add(chord([220, 330, 440], 2.0, 0.14, attack=0.9), 2.7)

# --- Scène 3 : la boucle (touche, écoute, POP de reformulation, coche)
add(click(0.06, 1400, 0.5), 5.0)                  # appui touche F9
bed_n = int(2.2 * SR)                             # lit d'écoute (souffle bas)
_bed = np.random.RandomState(5).randn(bed_n)
_bed = np.convolve(_bed, np.ones(60) / 60, mode="same")
_bed *= np.sin(np.pi * np.linspace(0, 1, bed_n)) * 0.05
add(_bed, 5.05)
for k, tt in enumerate([5.25, 5.65, 6.05, 6.45, 6.9]):   # ticks par token
    add(click(0.05, 1200 + k * 120, 0.16), tt)
add(pop(0.95), 7.25)                              # LE pop satisfaisant
add(bell(1760, 1.0, 0.22, decay=5.5), 7.95)       # coche « collé »

# --- Scène 4 : Styles — marimba ascendante (pentatonique La)
sty_notes = [220.0, 277.18, 329.63, 369.99, 440.0]
for k, tt in enumerate([9.62, 10.62, 11.62, 12.62, 13.62]):
    add(bell(sty_notes[k], 0.9, 0.42, decay=6.0, inharm=1.0), tt)
    add(click(0.04, 2400, 0.10), tt)

# --- Scène 5 : confidentialité — le verrou se referme
add(chord([146.83, 220, 277.18], 2.2, 0.11, attack=1.0), 14.35)
add(thunk(0.85), 15.0)                            # cadenas

# --- Scène 6 : Turbo — whoosh
add(whoosh(0.8, 0.6), 17.45)
add(bell(880, 1.2, 0.3, decay=4.0), 18.0)

# --- Scène 7 : partout — cascade de 3 ticks doux
for k, tt in enumerate([20.6, 21.0, 21.4]):
    add(click(0.05, 1500 + k * 200, 0.2), tt)
    add(bell(sty_notes[k + 1], 0.7, 0.12, decay=6.5), tt)

# --- Scène 8 : résolution — accord chaud La majeur add9 + cloche finale
add(chord([220, 277.18, 329.63, 440, 554.37], 3.2, 0.26, attack=0.5), 23.35)
add(bell(440, 2.4, 0.4, decay=2.0), 24.0)
add(bell(659.25, 2.2, 0.24, decay=2.2), 24.15)

# ------------------------------------------------------------------ mastering
# soft-clip doux puis normalisation à ~ -1.5 dBFS
buf = np.tanh(buf * 1.05)
peak = np.max(np.abs(buf)) + 1e-9
buf = buf / peak * 0.84

# écriture WAV 16 bits mono
out = "/home/user/nova-assistant-vocal/landing/film/nova-film-audio.wav"
pcm = np.clip(buf, -1, 1)
pcm16 = (pcm * 32767).astype(np.int16)
with wave.open(out, "w") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(struct.pack("<%dh" % len(pcm16), *pcm16))

print("audio écrit:", out, "durée", round(len(pcm16) / SR, 2), "s")
