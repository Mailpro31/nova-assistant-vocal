# -*- coding: utf-8 -*-
"""Rendu du film Nova v4 : cinematic.html → nova-film3.mp4 / nova-film3-en.mp4.

Rendu déterministe image par image (seek(t)) via Playwright, images PNG
poussées directement dans ffmpeg (aucun fichier temporaire — l'allocation
disque de session est limitée), muxées avec la bande-son stéréo. Posters
extraits d'un plan représentatif (l'e-mail reformulé). FR et EN partagent la
même bande-son (minutage identique).
"""
import subprocess
import sys
import time

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

FF = imageio_ffmpeg.get_ffmpeg_exe()
SRC = "file:///home/user/nova-assistant-vocal/landing/film/cinematic.html?capture=1"
AUDIO = "/home/user/nova-assistant-vocal/landing/film/nova-film-audio.wav"
DEST = "/home/user/nova-assistant-vocal/landing"
FPS = 30
W, H = 1600, 900
POSTER_T = 8.62   # e-mail reformulé + coche (le « payoff »)

JOBS = [
    ("fr", f"{DEST}/nova-film3.mp4", f"{DEST}/film3-poster.jpg"),
    ("en", f"{DEST}/nova-film3-en.mp4", f"{DEST}/film3-poster-en.jpg"),
]


def encode(page, lang, out_mp4, out_poster):
    page.evaluate(f"window.setLang('{lang}')")
    dur = page.evaluate("window.DUR")
    nframes = round(dur * FPS)
    cmd = [
        FF, "-y", "-f", "image2pipe", "-vcodec", "png", "-framerate", str(FPS),
        "-i", "-", "-i", AUDIO,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "21", "-preset", "medium",
        "-movflags", "+faststart", "-c:a", "aac", "-b:a", "160k", "-shortest",
        "-loglevel", "error", out_mp4,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.time()
    for f in range(nframes):
        page.evaluate("window.seek(%f)" % (f / FPS))
        png = page.screenshot(type="png")
        proc.stdin.write(png)
        if f % 150 == 0:
            print(f"  [{lang}] frame {f}/{nframes}", flush=True)
    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        sys.exit(f"ffmpeg a échoué ({lang}) code {rc}")
    # poster
    page.evaluate("window.seek(%f)" % POSTER_T)
    page.screenshot(path=out_poster, type="jpeg", quality=88)
    print(f"  [{lang}] terminé en {time.time()-t0:.0f}s → {out_mp4}", flush=True)


with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
        args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
              "--force-color-profile=srgb", "--disable-lcd-text"])
    pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(SRC)
    pg.wait_for_function("window.__ready===true", timeout=8000)
    for lang, mp4, poster in JOBS:
        encode(pg, lang, mp4, poster)
    b.close()
    if errs:
        sys.exit("erreurs page: " + "; ".join(errs[:4]))

print("OK — MP4 + posters générés")
