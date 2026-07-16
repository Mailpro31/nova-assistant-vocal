# -*- coding: utf-8 -*-
"""Bande-son du film Nova v4 — stéréo, réverbe, musique et SFX « satisfaisants ».

Tout est synthétisé (numpy, zéro sample externe) et calé à la trame près sur la
timeline de cinematic.html (19 plans, 42 s). Nouveautés v4 :

- STÉRÉO : panoramiques par événement (loi à puissance constante), whooshs de
  coupe alternés gauche/droite.
- RÉVERBE par convolution (RI synthétique 1,3 s, aigus amortis, canaux
  décorrélés) sur un bus d'envoi — cloches, pops et accords respirent.
- LIT MUSICAL : pad chaud continu + arpège pentatonique feutré (~110 BPM)
  pendant le montage central (14,8 → 33,2 s) pour porter le rythme des plans.
- DUCKING : le lit s'efface doucement (-5 dB max) sous chaque SFX, comme un
  mix broadcast — les transitoires restent nets.
- Sons fréquents (frappe) : hauteur et niveau légèrement randomisés, jamais
  deux ticks identiques.

Sortie : nova-film-audio.wav (stéréo, partagé FR/EN — minutage identique).
"""
import struct
import wave

import numpy as np

SR = 44100
DUR = 42.0
N = int(SR * DUR)

# Trois bus stéréo : lit musical, SFX secs, envoi réverbe.
bed = np.zeros((N, 2), dtype=np.float64)
dry = np.zeros((N, 2), dtype=np.float64)
send = np.zeros((N, 2), dtype=np.float64)

# Coupes de plans (miroir exact de CUTS dans cinematic.html).
CUTS = [1.7, 3.5, 5.0, 7.2, 9.4, 11.2, 13.0, 14.8, 17.9, 19.9,
        23.1, 24.9, 27.0, 28.8, 30.8, 33.2, 35.4, 36.9]


def at(t):
    return int(t * SR)


def pan_gains(pan):
    """Loi à puissance constante : pan ∈ [-1 (G), +1 (D)]."""
    th = (pan + 1) * np.pi / 4
    return np.cos(th), np.sin(th)


def add(sig, t, gain=1.0, pan=0.0, bus="dry", verb=0.0):
    """Mixe un signal mono dans les bus à l'instant t (s).

    verb ∈ [0..1] : part envoyée à la réverbe (en plus du son sec)."""
    i = at(t)
    if i >= N:
        return
    j = min(N, i + len(sig))
    s = sig[: j - i] * gain
    gl, gr = pan_gains(pan)
    target = bed if bus == "bed" else dry
    target[i:j, 0] += s * gl
    target[i:j, 1] += s * gr
    if verb > 0:
        send[i:j, 0] += s * gl * verb
        send[i:j, 1] += s * gr * verb


def env(n, attack, release, hold=0.0, curve=2.0):
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


def pluck(freq, dur=0.55, gain=1.0):
    """Corde feutrée pour l'arpège : attaque soufflée + sinus amorti."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 2 * t)
    tone *= np.exp(-t * 7.5)
    noise = np.random.RandomState(int(freq) % 997).randn(n)
    noise = np.convolve(noise, np.ones(24) / 24, mode="same") * np.exp(-t * 90) * 0.5
    s = tone + noise
    s *= env(n, 0.002, dur, curve=1.2)
    return s / (np.max(np.abs(s)) + 1e-9) * gain


def sub_tone(freq, dur, gain=1.0):
    n = int(dur * SR)
    s = np.sin(2 * np.pi * freq * np.arange(n) / SR)
    return s * env(n, 0.05, dur * 0.7) * gain


def click(dur=0.05, freq=1800, gain=1.0, seed=None):
    """Tick feutré ; hauteur/niveau à randomiser côté appelant pour la frappe."""
    n = int(dur * SR)
    noise = np.random.RandomState(seed if seed is not None else int(freq)).randn(n)
    noise = np.convolve(noise, np.ones(40) / 40, mode="same")
    tone = np.sin(2 * np.pi * freq * np.arange(n) / SR) * 0.5
    s = (noise * 0.6 + tone) * np.exp(-np.arange(n) / SR * 60)
    return s / (np.max(np.abs(s)) + 1e-9) * gain


def thock(gain=1.0):
    """Touche mécanique feutrée : corps grave + souffle bref."""
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
    """Pop de reformulation : glissando descendant + sub court."""
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


def boop(f0, f1, dur=0.16, gain=1.0):
    """Boop rebondissant (saut du badge) : glissando montant très doux."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f0 + (f1 - f0) * (t / dur) ** 0.7
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) * np.exp(-t * 16)
    s *= env(n, 0.003, dur, curve=1.2)
    return s / (np.max(np.abs(s)) + 1e-9) * gain


def thunk(gain=1.0):
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


def whoosh(dur=0.75, gain=1.0, up=True, seed=99):
    """Whoosh : bruit filtré + glissando (montant/descendant)."""
    n = int(dur * SR)
    noise = np.random.RandomState(seed).randn(n)
    lp = np.convolve(noise, np.ones(30) / 30, mode="same")
    rise = np.linspace(0, 1, n) ** 0.6
    if not up:
        rise = rise[::-1]
    gliss = np.sin(2 * np.pi * np.cumsum(200 + 900 * rise) / SR) * 0.25
    s = (lp * (0.5 + 0.5 * rise) + gliss)
    s *= np.sin(np.pi * np.linspace(0, 1, n)) ** 1.2
    return s / (np.max(np.abs(s)) + 1e-9) * gain


def air(dur=0.26, gain=1.0, up=True, seed=5):
    """Micro-whoosh aérien des coupes : bande étroite, très court."""
    n = int(dur * SR)
    noise = np.random.RandomState(seed).randn(n)
    lp = np.convolve(noise, np.ones(14) / 14, mode="same")
    hp = lp - np.convolve(lp, np.ones(120) / 120, mode="same")
    rise = np.linspace(0, 1, n)
    if not up:
        rise = rise[::-1]
    s = hp * (0.35 + 0.65 * rise)
    s *= np.sin(np.pi * np.linspace(0, 1, n)) ** 1.4
    return s / (np.max(np.abs(s)) + 1e-9) * gain


def shutter(gain=1.0):
    """Pose d'écran : clic feutré + petit corps grave (façon obturateur doux)."""
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * 140 * t) * np.exp(-t * 26)
    cl = click(0.05, 2600, 0.8, seed=31)
    s = body * 0.8
    s[: len(cl)] += cl
    s *= env(n, 0.001, 0.22, curve=1.4)
    return s / (np.max(np.abs(s)) + 1e-9) * gain


def whirr(dur=0.7, gain=1.0):
    """Rotation feutrée (flèche de mise à jour) : souffle cyclique montant."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = np.random.RandomState(17).randn(n)
    lp = np.convolve(noise, np.ones(50) / 50, mode="same")
    cyc = 0.6 + 0.4 * np.sin(2 * np.pi * (6 + 4 * t / dur) * t)
    tone = np.sin(2 * np.pi * np.cumsum(320 + 160 * t / dur) / SR) * 0.18
    s = (lp * cyc + tone)
    s *= np.sin(np.pi * np.linspace(0, 1, n)) ** 1.1
    return s / (np.max(np.abs(s)) + 1e-9) * gain


def chord(freqs, dur, gain=1.0, attack=0.6, release=None):
    n = int(dur * SR)
    out = np.zeros(n)
    for f in freqs:
        out += np.sin(2 * np.pi * f * np.arange(n) / SR)
        out += 0.3 * np.sin(2 * np.pi * f * 2 * np.arange(n) / SR)
    out *= env(n, attack, release if release else dur * 0.5, curve=1.3)
    return out / (len(freqs) * 1.3) * gain


def mouse_click(gain=1.0):
    n = int(0.05 * SR)
    t = np.arange(n) / SR
    down = np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 130)
    noise = np.random.RandomState(7).randn(n)
    noise = np.convolve(noise, np.ones(20) / 20, mode="same") * np.exp(-t * 150)
    s = down * 0.7 + noise * 0.5
    return s / (np.max(np.abs(s)) + 1e-9) * gain


# ------------------------------------------------------------------ lit musical
def pad_stereo():
    """Pad chaud continu, canaux légèrement désaccordés (largeur douce)."""
    t = np.arange(N) / SR
    voices = [110, 165, 220, 277.18]
    out = np.zeros((N, 2))
    for ch, det0 in ((0, 1.0015), (1, 0.9985)):
        s = np.zeros(N)
        for i, f in enumerate(voices):
            det = det0 * (1 + 0.004 * np.sin(2 * np.pi * 0.05 * t + i + ch))
            s += np.sin(2 * np.pi * f * det * t) * (0.6 - i * 0.1)
        lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.08 * t + ch * 0.9)
        s *= (0.35 + 0.65 * lfo)
        out[:, ch] = s / (np.max(np.abs(s)) + 1e-9)
    g = np.ones(N)
    fi = int(1.0 * SR)
    fo = int(2.6 * SR)
    g[:fi] = np.linspace(0, 1, fi) ** 1.5
    g[-fo:] = np.linspace(1, 0, fo) ** 1.5
    return out * g[:, None]


bed += pad_stereo() * 0.085

# Arpège pentatonique feutré ~110 BPM (croches) pendant le montage central.
ARP_T0, ARP_T1 = 14.8, 33.2
ARP_STEP = 60.0 / 110.0 / 2.0            # croche à 110 BPM ≈ 0,273 s
ARP_NOTES = [220.0, 277.18, 329.63, 440.0, 329.63, 277.18]
_rs = np.random.RandomState(23)
tt, k = ARP_T0, 0
while tt < ARP_T1:
    fade = min(1.0, (tt - ARP_T0) / 0.9, (ARP_T1 - tt) / 0.9)
    f = ARP_NOTES[k % len(ARP_NOTES)] * (1 + _rs.randn() * 0.0015)
    add(pluck(f, 0.5, 0.055 * fade), tt, pan=(-0.35 if k % 2 else 0.35), bus="bed")
    tt += ARP_STEP
    k += 1

# ------------------------------------------------------------------ coupes
for i, c in enumerate(CUTS):
    up = i % 2 == 0
    pan = -0.5 if i % 2 == 0 else 0.5
    add(air(0.26, 0.15, up=up, seed=200 + i), c - 0.05, pan=pan, verb=0.12)

# ------------------------------------------------------------------ montage
np.random.seed(3)

# --- S1 mat [0–1.7] : cloches d'apparition + sub sous le wordmark
add(bell(440.00, 2.0, 0.95, decay=2.3), 0.32, pan=0.0, verb=0.35)
add(bell(659.25, 1.7, 0.55, decay=2.5), 0.45, pan=-0.2, verb=0.35)
add(bell(554.37, 1.7, 0.45, decay=2.7), 0.58, pan=0.2, verb=0.35)
for kk, f in enumerate([1318, 1760, 2093]):
    add(bell(f, 1.0, 0.13, decay=5.2), 0.30 + kk * 0.11, pan=(-0.3 + kk * 0.3), verb=0.5)
add(sub_tone(55, 1.1, 0.55), 0.92)
add(bell(1760, 0.8, 0.10, decay=6.0), 1.05, pan=0.35, verb=0.5)   # glint

# --- S2 tag [1.7–3.5] : deux mots qui claquent + trait
add(pop(0.5, f0=520.0), 1.84, pan=-0.12, verb=0.2)
add(pop(0.55, f0=640.0), 2.28, pan=0.12, verb=0.2)
add(air(0.3, 0.14, up=True, seed=41), 2.76, verb=0.2)
add(chord([220, 330, 440], 1.6, 0.13, attack=0.7), 1.80, verb=0.3)

# --- S3 key [3.5–5.0] : THOCK + shimmer
add(mouse_click(0.16), 3.90)
add(thock(0.95), 3.92)
add(bell(1760, 0.85, 0.18, decay=5.5), 4.06, pan=0.15, verb=0.4)

# --- S4 listen [5.0–7.2] : lit de souffle + ticks par mot (randomisés)
bed_n = int(2.0 * SR)
_bed = np.random.RandomState(5).randn(bed_n)
_bed = np.convolve(_bed, np.ones(60) / 60, mode="same")
_bed *= np.sin(np.pi * np.linspace(0, 1, bed_n)) * 0.055
add(_bed, 5.15)
_rw = np.random.RandomState(9)
for kk in range(6):
    f = 1150 + kk * 110 + _rw.randn() * 60
    add(click(0.05, f, 0.20 + _rw.rand() * 0.05, seed=60 + kk),
        5.25 + kk * 0.28, pan=(-0.2 + 0.08 * kk), verb=0.15)

# --- S5 pop [7.2–9.4] : LE pop + étincelles + coche
add(pop(1.00), 7.22, verb=0.3)
add(bell(1760, 1.0, 0.28, decay=5.0), 7.44, pan=-0.2, verb=0.5)
add(bell(2093, 0.8, 0.15, decay=6.0), 7.56, pan=0.2, verb=0.5)
add(bell(1568, 0.9, 0.30, decay=5.5), 8.08, pan=0.1, verb=0.45)   # coche verte
add(bell(2349, 0.7, 0.09, decay=6.5), 8.32, pan=0.3, verb=0.5)    # glint

# --- S6 chat [9.4–11.2] : reçu, frappe, envol
add(pop(0.45, f0=430.0), 9.56, pan=-0.3, verb=0.25)
_rc = np.random.RandomState(13)
for kk in range(5):
    f = 1850 + _rc.randn() * 120
    add(click(0.04, f, 0.11 + _rc.rand() * 0.04, seed=80 + kk), 9.98 + kk * 0.15, pan=0.25, verb=0.1)
add(whoosh(0.34, 0.55, up=True, seed=51), 10.90, pan=0.3, verb=0.3)
add(bell(1976, 0.7, 0.22, decay=6.0), 11.00, pan=0.25, verb=0.45)

# --- S7 todo [11.2–13.0] : lignes puis 3 coches + rayures
for kk, tt2 in enumerate((11.36, 11.49, 11.62)):
    add(click(0.04, 1400 + kk * 60, 0.09, seed=90 + kk), tt2, pan=-0.1, verb=0.1)
for kk, (tt2, f) in enumerate(zip((11.92, 12.22, 12.52), (659.25, 783.99, 987.77))):
    add(mouse_click(0.18), tt2 - 0.02)
    add(click(0.05, 2100, 0.15, seed=95 + kk), tt2, verb=0.1)
    add(bell(f, 0.8, 0.40 + kk * 0.03, decay=5.0), tt2 + 0.02, pan=(-0.15 + kk * 0.15), verb=0.4)
    add(air(0.18, 0.10, up=True, seed=120 + kk), tt2 + 0.10, pan=0.1, verb=0.1)   # rayure

# --- S8 prompt [13.0–14.8] : frappe + envoi deux-tons
_rp = np.random.RandomState(19)
for kk in range(9):
    f = 1750 + (kk % 3) * 130 + _rp.randn() * 70
    add(click(0.035, f, 0.08 + _rp.rand() * 0.03, seed=130 + kk), 13.18 + kk * 0.105, pan=-0.15, verb=0.08)
add(mouse_click(0.18), 14.28)
add(bell(659.25, 0.6, 0.26, decay=6.0), 14.32, pan=0.1, verb=0.4)
add(bell(880.00, 0.9, 0.32, decay=5.0), 14.44, pan=0.2, verb=0.45)

# --- S9 sty [14.8–17.9] : marimba pentatonique, indicateur qui glisse
sty_notes = [220.0, 277.18, 329.63, 369.99, 440.0]
for kk, tt2 in enumerate([14.82, 15.42, 16.04, 16.66, 17.28]):
    add(bell(sty_notes[kk], 0.85, 0.44, decay=6.0), tt2, pan=(-0.3 + kk * 0.15), verb=0.35)
    add(click(0.04, 2400, 0.11, seed=140 + kk), tt2, verb=0.1)
    if kk > 0:
        add(mouse_click(0.16), tt2 - 0.04)
        add(air(0.16, 0.08, up=True, seed=150 + kk), tt2 + 0.02, pan=0.0)

# --- S10 auto [17.9–19.9] : sauts du badge (boops) + morphs
add(boop(420, 640, 0.16, 0.30), 18.25, pan=-0.35, verb=0.2)          # apparition
add(boop(520, 780, 0.17, 0.38), 18.69, pan=0.0, verb=0.25)           # atterrissage 1
add(click(0.04, 2600, 0.10, seed=161), 18.72, verb=0.1)
add(boop(620, 930, 0.18, 0.42), 19.24, pan=0.35, verb=0.25)          # atterrissage 2
add(click(0.04, 2800, 0.10, seed=162), 19.27, verb=0.1)
add(pop(0.35, f0=480.0), 18.62, pan=0.0, verb=0.2)                   # caption 1
add(pop(0.38, f0=560.0), 19.10, pan=0.1, verb=0.2)                   # caption 2

# --- S11 models [19.9–23.1] : pose d'écran + balayage scintillant + swell
add(shutter(0.75), 20.00, verb=0.15)
sw = chord([110, 220, 277.18], 2.6, 0.10, attack=1.1)
add(sw, 20.05, verb=0.35)
for kk, f in enumerate([1567.98, 1760.0, 2093.0, 2349.3, 2637.0]):
    add(bell(f, 0.7, 0.11, decay=6.5), 20.55 + kk * 0.16, pan=(-0.4 + kk * 0.2), verb=0.55)
add(bell(880, 1.0, 0.16, decay=4.5), 21.35, pan=0.0, verb=0.4)       # halo
add(click(0.05, 1500, 0.10, seed=170), 20.95, verb=0.1)              # kicker
add(click(0.05, 1650, 0.10, seed=171), 21.45, verb=0.1)              # titre

# --- S12 custom [23.1–24.9] : cloche Ultra + chips à ressort + reflet
add(bell(659.25, 1.2, 0.40, decay=3.6), 23.32, pan=-0.1, verb=0.45)
add(bell(880.00, 1.0, 0.25, decay=4.1), 23.48, pan=0.1, verb=0.45)
add(bell(1108.73, 0.9, 0.14, decay=5.6), 23.64, pan=0.2, verb=0.5)
add(click(0.045, 2000, 0.12, seed=180), 23.50, verb=0.1)             # chip 1
add(click(0.045, 2150, 0.12, seed=181), 23.62, verb=0.1)             # chip 2
add(bell(2793, 0.5, 0.07, decay=7.0), 23.85, pan=0.25, verb=0.5)     # reflet badge

# --- S13 priv [24.9–27.0] : accord + convergence + verrou
add(chord([146.83, 220, 277.18], 1.9, 0.13, attack=0.9), 24.95, verb=0.4)
conv_n = int(0.9 * SR)
_cv = np.random.RandomState(6).randn(conv_n)
_cv = np.convolve(_cv, np.ones(80) / 80, mode="same")
_cv *= np.linspace(0.2, 1, conv_n) ** 1.4 * 0.10
add(_cv, 24.95, verb=0.2)
add(thunk(0.95), 25.80)
add(bell(1568, 0.7, 0.12, decay=6.0), 25.86, pan=0.15, verb=0.45)

# --- S14 turbo [27.0–28.8] : gros whoosh + anneau + cloche brillante
add(whoosh(0.85, 0.70, up=True, seed=61), 27.10, pan=-0.25, verb=0.3)
add(air(0.30, 0.20, up=True, seed=62), 27.55, pan=0.3, verb=0.25)    # anneau sonique
add(bell(880, 1.1, 0.32, decay=4.0), 27.92, pan=0.1, verb=0.45)

# --- S15 every [28.8–30.8] : cascade de cartes + frappe légère
for kk, tt2 in enumerate([28.94, 29.16, 29.38]):
    add(click(0.05, 1500 + kk * 200, 0.16, seed=190 + kk), tt2, pan=(-0.3 + kk * 0.3), verb=0.15)
    add(bell(sty_notes[kk + 1], 0.7, 0.13, decay=6.5), tt2, pan=(-0.3 + kk * 0.3), verb=0.4)
_re = np.random.RandomState(29)
for kk in range(7):
    f = 1900 + _re.randn() * 100
    add(click(0.03, f, 0.05 + _re.rand() * 0.02, seed=210 + kk), 29.25 + kk * 0.14, verb=0.05)

# --- S16 stat [30.8–33.2] : cliquet accéléré, résolution, « 3× »
tt2 = 30.94
step = 0.15
kf = 0
while tt2 < 32.05:
    add(click(0.035, 900 + kf * 55, 0.13 + kf * 0.004, seed=220 + kf), tt2,
        pan=(-0.2 + (kf % 5) * 0.1), verb=0.08)
    tt2 += step
    step = max(0.05, step * 0.90)
    kf += 1
add(bell(880.00, 1.1, 0.38, decay=4.0), 32.16, pan=-0.1, verb=0.45)
add(bell(1108.73, 0.9, 0.22, decay=4.5), 32.28, pan=0.1, verb=0.45)
add(pop(0.5, f0=700.0), 32.34, verb=0.25)                            # « 3× »

# --- S17 week [33.2–35.4] : roulement décéléré + cloche chaude + courbe
tt2 = 33.36
step = 0.085
kf = 0
while tt2 < 34.15:
    add(click(0.03, 1150 + kf * 40, 0.10, seed=240 + kf), tt2, pan=0.1 - (kf % 3) * 0.1, verb=0.08)
    tt2 += step
    step = min(0.16, step * 1.12)
    kf += 1
add(bell(587.33, 1.2, 0.34, decay=4.2), 34.28, pan=0.0, verb=0.45)
gl_n = int(0.7 * SR)
_gl = np.sin(2 * np.pi * np.cumsum(np.linspace(900, 1500, gl_n)) / SR)
_gl *= np.sin(np.pi * np.linspace(0, 1, gl_n)) ** 1.6 * 0.05
add(_gl, 33.80, pan=0.2, verb=0.4)                                   # courbe qui monte
add(click(0.05, 1600, 0.10, seed=260), 34.42, verb=0.1)              # sous-titre

# --- S18 upd [35.4–36.9] : rotation feutrée → coche + carillon deux notes
add(whirr(0.68, 0.30), 35.48, pan=-0.1, verb=0.2)
add(pop(0.4, f0=520.0), 36.16, verb=0.25)
add(bell(1318.5, 0.8, 0.26, decay=5.0), 36.20, pan=-0.15, verb=0.5)
add(bell(1760.0, 1.0, 0.30, decay=4.6), 36.34, pan=0.15, verb=0.5)

# --- S19 end [36.9–42.0] : accord final chaud + cloches + halo
add(chord([220, 277.18, 329.63, 440, 554.37], 3.4, 0.28, attack=0.5), 37.00, verb=0.5)
add(bell(440.00, 2.4, 0.45, decay=2.0), 37.52, pan=-0.1, verb=0.5)
add(bell(659.25, 2.2, 0.26, decay=2.2), 37.66, pan=0.1, verb=0.5)
add(pop(0.5, f0=600.0), 37.78, verb=0.3)                             # CTA
add(bell(1760.00, 1.4, 0.12, decay=4.5), 38.62, pan=0.2, verb=0.6)
add(bell(2093.00, 1.2, 0.08, decay=5.0), 39.55, pan=-0.25, verb=0.65)

# ------------------------------------------------------------------ réverbe
def reverb_ir(dur=1.3, damp=0.35, seed=1234):
    """RI synthétique : bruit décroissant, aigus amortis, canaux décorrélés."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    ir = np.zeros((n, 2))
    for ch in range(2):
        noise = np.random.RandomState(seed + ch).randn(n)
        k = 6
        noise = np.convolve(noise, np.ones(k) / k, mode="same")       # adoucit
        hf = noise - np.convolve(noise, np.ones(40) / 40, mode="same")
        noise = noise - hf * damp * (t / dur)                          # amortit les aigus dans la queue
        ir[:, ch] = noise * np.exp(-t * 4.6)
    ir[0, :] = 0.0
    # Normalisation en ÉNERGIE (L2 = 1 par canal) : la convolution conserve
    # grossièrement le niveau du signal envoyé au lieu de l'amplifier ~30×.
    ir /= (np.sqrt((ir ** 2).sum(axis=0, keepdims=True)) + 1e-9)
    return ir


IR = reverb_ir()
nfft = 1
while nfft < N + len(IR):
    nfft *= 2
wet = np.zeros((N, 2))
for ch in range(2):
    Sf = np.fft.rfft(send[:, ch], nfft)
    Hf = np.fft.rfft(IR[:, ch], nfft)
    w = np.fft.irfft(Sf * Hf, nfft)[:N]
    wet[:, ch] = w
wet *= 1.6

# ------------------------------------------------------------------ ducking
# Enveloppe des SFX (mono) → le lit s'efface en douceur dessous.
sfx_mix = np.abs(dry).sum(axis=1)
k_env = int(0.010 * SR)
att = np.convolve(sfx_mix, np.ones(k_env) / k_env, mode="same")
k_rel = int(0.20 * SR)
rel = np.convolve(att, np.ones(k_rel) / k_rel, mode="same")
duck_env = np.maximum(att, rel)
duck_env /= (np.percentile(duck_env, 99.5) + 1e-9)
duck_env = np.clip(duck_env, 0, 1)
bed *= (1.0 - 0.42 * duck_env)[:, None]

# ------------------------------------------------------------------ mastering
mixdown = bed + dry + wet
mixdown = np.tanh(mixdown * 1.22)
peak = np.max(np.abs(mixdown)) + 1e-9
mixdown = mixdown / peak * 0.92

out = "/home/user/nova-assistant-vocal/landing/film/nova-film-audio.wav"
pcm16 = (np.clip(mixdown, -1, 1) * 32767).astype(np.int16)
inter = pcm16.reshape(-1)
with wave.open(out, "w") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(struct.pack("<%dh" % len(inter), *inter))

print("audio écrit:", out, "durée", round(len(pcm16) / SR, 2), "s (stéréo)")
