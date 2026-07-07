# -*- coding: utf-8 -*-
"""
Intégrations Windows natives (portées de RoadSpeak) :
- secrets chiffrés DPAPI (les clés API ne sont plus stockées en clair),
- presse-papiers + collage Ctrl+V dans l'app active,
- touches multimédia système (Spotify, VLC... sans OAuth),
- synthèse vocale SAPI via un process PowerShell persistant (offline, gratuit),
- géolocalisation Windows (mode urgence).
"""

import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import sys
import threading
import time

APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))

# ------------------------------------------------------------- DPAPI --------

class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob_to_bytes(blob):
    data = ctypes.string_at(blob.pbData, blob.cbData)
    ctypes.windll.kernel32.LocalFree(blob.pbData)
    return data


def _dpapi_protect(data: bytes) -> bytes:
    blob_in = _DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)),
                                                ctypes.POINTER(ctypes.c_char)))
    blob_out = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        raise OSError("CryptProtectData a échoué")
    return _blob_to_bytes(blob_out)


def _dpapi_unprotect(data: bytes) -> bytes:
    blob_in = _DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)),
                                                ctypes.POINTER(ctypes.c_char)))
    blob_out = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        raise OSError("CryptUnprotectData a échoué")
    return _blob_to_bytes(blob_out)


SECRET_KEYS = ("anthropic", "openai", "gemini", "deepseek", "groq",
               "mistral", "xai", "openrouter",
               "picovoice", "twilio_sid", "twilio_token",
               "graph_client_id", "graph_refresh_token",
               "google_client_id", "google_client_secret", "google_refresh",
               "spotify_client_id", "spotify_refresh", "ha_token",
               "youtube", "serpapi", "mobile_token")

_secrets_file = os.path.join(APP_DIR, "secrets.json")
_secrets_lock = threading.Lock()
_secrets = {}


def _load_secrets():
    global _secrets
    try:
        with open(_secrets_file, "r", encoding="utf-8") as f:
            _secrets = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _secrets = {}


_load_secrets()


def _persist_secrets():
    tmp = _secrets_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_secrets, f)
    os.replace(tmp, _secrets_file)


def set_secret(key, value):
    """value vide = suppression. Jamais renvoyé à l'UI."""
    if key not in SECRET_KEYS:
        raise ValueError(f"secret inconnu : {key}")
    with _secrets_lock:
        if not value:
            _secrets.pop(key, None)
        else:
            try:
                import base64
                enc = _dpapi_protect(value.encode("utf-8"))
                _secrets[key] = base64.b64encode(enc).decode("ascii")
            except OSError:
                _secrets[key] = "plain:" + value  # repli improbable (DPAPI absent)
        _persist_secrets()
    return True


def get_secret(key):
    v = _secrets.get(key, "")
    if not v:
        return ""
    if v.startswith("plain:"):
        return v[6:]
    try:
        import base64
        return _dpapi_unprotect(base64.b64decode(v)).decode("utf-8")
    except Exception:
        return ""


def has_secret(key):
    return bool(_secrets.get(key))


def secrets_presence():
    return {k: has_secret(k) for k in SECRET_KEYS}


# -------------------------------------------------------- presse-papiers ----

CF_UNICODETEXT = 13
GMEM_MOVEABLE_ZEROINIT = 0x2042


def set_clipboard(text):
    u32 = ctypes.windll.user32
    k32 = ctypes.windll.kernel32
    data = text.encode("utf-16-le") + b"\x00\x00"
    for _ in range(5):
        if u32.OpenClipboard(0):
            break
        time.sleep(0.05)
    else:
        return False
    try:
        u32.EmptyClipboard()
        h = k32.GlobalAlloc(GMEM_MOVEABLE_ZEROINIT, len(data))
        p = k32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        k32.GlobalUnlock(h)
        u32.SetClipboardData(CF_UNICODETEXT, h)
    finally:
        u32.CloseClipboard()
    return True


def paste_into_active_app(text):
    """Clipboard + Ctrl+V simulé — la pilule ne vole pas le focus (overrideredirect)."""
    if not set_clipboard(text):
        return False
    time.sleep(0.15)
    import keyboard
    keyboard.send("ctrl+v")
    return True


# -------------------------------------------------------- touches média -----

MEDIA_VK = {
    "playPause": 0xB3, "stop": 0xB2, "next": 0xB0, "prev": 0xB1,
    "volUp": 0xAF, "volDown": 0xAE, "mute": 0xAD,
}

MEDIA_LABELS = {
    "playPause": "lecture / pause", "stop": "stop", "next": "piste suivante",
    "prev": "piste précédente", "volUp": "volume plus fort",
    "volDown": "volume plus bas", "mute": "son coupé ou rétabli",
}


def send_media_key(action):
    vk = MEDIA_VK.get(action)
    if not vk:
        return False
    repeat = 4 if action in ("volUp", "volDown") else 1
    for _ in range(repeat):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
        time.sleep(0.04)
    return True


# ------------------------------------------------------------- TTS SAPI -----
# Process PowerShell persistant : zéro dépendance pip, démarre en ~1 s puis
# chaque phrase part instantanément. Les annonces prioritaires (urgence,
# alertes OBD) interrompent la lecture en cours.

_TTS_SCRIPT = r"""
$ErrorActionPreference = 'Continue'
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SetOutputToDefaultAudioDevice()
[Console]::Out.WriteLine('RS:{"type":"ready"}')
while ($true) {
  $line = [Console]::In.ReadLine()
  if ($null -eq $line) { break }
  try { $o = $line | ConvertFrom-Json } catch { continue }
  try {
    switch ($o.cmd) {
      'speak' {
        $synth.SpeakAsyncCancelAll()
        if ($null -ne $o.rate) { $synth.Rate = [Math]::Max(-10, [Math]::Min(10, [int]$o.rate)) }
        if ($null -ne $o.volume) { $synth.Volume = [Math]::Max(0, [Math]::Min(100, [int]$o.volume)) }
        if ($o.voice) { try { $synth.SelectVoice([string]$o.voice) } catch {} }
        $null = $synth.SpeakAsync([string]$o.text)
      }
      'stop' { $synth.SpeakAsyncCancelAll() }
      'state' {
        $s = if ($synth.State -eq [System.Speech.Synthesis.SynthesizerState]::Speaking) { 'true' } else { 'false' }
        [Console]::Out.WriteLine('RS:{"type":"tts_state","speaking":' + $s + '}')
      }
      'voices' {
        $names = @($synth.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }) -join '|'
        [Console]::Out.WriteLine('RS:{"type":"voices","names":"' + $names + '"}')
      }
      'geo' {
        $lat = 'null'; $lon = 'null'
        try {
          Add-Type -AssemblyName System.Device
          $w = New-Object System.Device.Location.GeoCoordinateWatcher
          $w.Start($false)
          $deadline = (Get-Date).AddSeconds(5)
          while ((Get-Date) -lt $deadline -and $w.Position.Location.IsUnknown) { Start-Sleep -Milliseconds 200 }
          if (-not $w.Position.Location.IsUnknown) {
            $lat = $w.Position.Location.Latitude.ToString([System.Globalization.CultureInfo]::InvariantCulture)
            $lon = $w.Position.Location.Longitude.ToString([System.Globalization.CultureInfo]::InvariantCulture)
          }
          $w.Stop()
        } catch {}
        [Console]::Out.WriteLine('RS:{"type":"geo","lat":' + $lat + ',"lon":' + $lon + '}')
      }
      'quit' { break }
    }
  } catch {}
}
"""


class TtsBridge:
    def __init__(self):
        self.proc = None
        self.lock = threading.Lock()
        self._responses = []
        self._resp_event = threading.Event()
        # état RÉEL de la synthèse (JARVIS : le micro sait quand l'assistant
        # parle, au lieu d'une estimation en caractères/seconde)
        self.speaking = False
        self._speak_deadline = 0.0
        self._speak_min = 0.0
        self._poll_evt = threading.Event()
        self._poller_started = False

    def _ensure(self):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                return True
            script = os.path.join(APP_DIR, "novatts.ps1")
            try:
                with open(script, "w", encoding="utf-8-sig") as f:
                    f.write(_TTS_SCRIPT)
                self.proc = subprocess.Popen(
                    ["powershell.exe", "-NoProfile", "-NonInteractive",
                     "-ExecutionPolicy", "Bypass", "-File", script],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                    creationflags=subprocess.CREATE_NO_WINDOW)
                threading.Thread(target=self._reader, daemon=True).start()
                if not self._poller_started:
                    self._poller_started = True
                    threading.Thread(target=self._state_poller, daemon=True).start()
                return True
            except Exception:
                self.proc = None
                return False

    def _reader(self):
        proc = self.proc
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("RS:"):
                try:
                    r = json.loads(line[3:])
                except json.JSONDecodeError:
                    continue
                if r.get("type") == "tts_state":
                    # jamais remonter speaking=False avant ~0,6 s : SpeakAsync
                    # peut ne pas avoir encore démarré au premier sondage
                    if r.get("speaking"):
                        self.speaking = True
                    elif time.time() > self._speak_min:
                        self.speaking = False
                    continue
                self._responses.append(r)
                self._resp_event.set()

    def _state_poller(self):
        """Sonde l'état du synthétiseur pendant qu'une phrase est en cours :
        speaking passe à False dès la fin réelle de la voix."""
        while True:
            self._poll_evt.wait()
            idle = 0
            while self.speaking and time.time() < self._speak_deadline:
                if not self._send({"cmd": "state"}):
                    break
                time.sleep(0.15)
                if not self.speaking:
                    idle += 1
                    if idle >= 2:
                        break
                else:
                    idle = 0
            self.speaking = False
            self._poll_evt.clear()

    def _send(self, obj):
        if not self._ensure():
            return False
        try:
            self.proc.stdin.write(json.dumps(obj) + "\n")
            self.proc.stdin.flush()
            return True
        except Exception:
            self.proc = None
            return False

    def _request(self, obj, rtype, timeout=8.0):
        self._responses.clear()
        self._resp_event.clear()
        if not self._send(obj):
            return None
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._resp_event.wait(0.2)
            for r in list(self._responses):
                if r.get("type") == rtype:
                    return r
            self._resp_event.clear()
        return None

    def speak(self, text, rate=1, volume=100, voice=""):
        now = time.time()
        self._speak_min = now + 0.6
        self._speak_deadline = now + 4.0 + len(text) * 0.12
        ok = self._send({"cmd": "speak", "text": text, "rate": rate,
                         "volume": volume, "voice": voice})
        self.speaking = bool(ok)
        if ok:
            self._poll_evt.set()
        return ok

    def stop(self):
        self.speaking = False
        self._speak_min = 0.0
        return self._send({"cmd": "stop"})

    def voices(self):
        r = self._request({"cmd": "voices"}, "voices")
        return [v for v in (r or {}).get("names", "").split("|") if v]

    def geolocate(self):
        """(lat, lon) ou (None, None) — n'attend jamais plus de ~6 s."""
        r = self._request({"cmd": "geo"}, "geo", timeout=7.0)
        if r and r.get("lat") is not None:
            return r["lat"], r["lon"]
        return None, None

    def dispose(self):
        self._send({"cmd": "quit"})


tts_bridge = TtsBridge()


# ------------------------------------------------------- lecteur MP3 (MCI) --
# Voix neuronale edge-tts : le MP3 généré est joué par l'API MCI de Windows
# (winmm.dll) — natif, zéro dépendance, arrêtable et interrogeable.

_mci_lock = threading.Lock()
_MCI_ALIAS = "novatts_mp3"


def _mci(cmd):
    buf = ctypes.create_unicode_buffer(160)
    err = ctypes.windll.winmm.mciSendStringW(cmd, buf, 160, None)
    return err, buf.value


def play_mp3(path, volume=100):
    """Joue un MP3 (asynchrone). True si la lecture a démarré."""
    with _mci_lock:
        _mci(f"close {_MCI_ALIAS}")
        err, _ = _mci(f'open "{path}" type mpegvideo alias {_MCI_ALIAS}')
        if err:
            # certains systèmes n'acceptent pas 'type mpegvideo' : sans type
            err, _ = _mci(f'open "{path}" alias {_MCI_ALIAS}')
            if err:
                return False
        v = max(0, min(100, int(volume)))
        _mci(f"setaudio {_MCI_ALIAS} volume to {v * 10}")
        err, _ = _mci(f"play {_MCI_ALIAS}")
        return err == 0


def mp3_playing():
    """True tant que le MP3 est en cours de lecture."""
    with _mci_lock:
        err, v = _mci(f"status {_MCI_ALIAS} mode")
    if err:
        return False
    v = (v or "").lower()
    # les chaînes MCI sont en principe en anglais ; par prudence, tout état
    # non explicitement terminal compte comme « en lecture »
    return bool(v) and v not in ("stopped", "paused", "not ready")


def stop_mp3():
    with _mci_lock:
        _mci(f"stop {_MCI_ALIAS}")
        _mci(f"close {_MCI_ALIAS}")
    return True


# ------------------------------------------------ contrôle système (2.9) ----

def screenshot_b64(max_w=1024, quality=70):
    """Capture l'écran → JPEG base64 (envoyé UNIQUEMENT au fournisseur IA
    choisi par l'utilisateur, jamais ailleurs, et jamais stocké)."""
    import base64
    import io
    from PIL import ImageGrab
    img = ImageGrab.grab()
    if img.width > max_w:
        img = img.resize((max_w, int(img.height * max_w / img.width)))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode()


def _master_volume():
    """Interface IAudioEndpointVolume (pycaw). CoInitialize par thread."""
    import comtypes
    from pycaw.pycaw import AudioUtilities
    try:
        comtypes.CoInitialize()
    except Exception:
        pass
    dev = AudioUtilities.GetSpeakers()
    try:
        return dev.EndpointVolume            # pycaw ≥ 2024 (AudioDevice)
    except AttributeError:
        from ctypes import POINTER, cast
        from pycaw.pycaw import IAudioEndpointVolume
        iface = dev.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None)
        return cast(iface, POINTER(IAudioEndpointVolume))


def get_volume():
    """Volume maître 0-100, ou None si indisponible."""
    try:
        return round(_master_volume().GetMasterVolumeLevelScalar() * 100)
    except Exception:
        return None


def set_volume(pct):
    """Fixe le volume maître (0-100). True si ok."""
    try:
        v = _master_volume()
        v.SetMasterVolumeLevelScalar(max(0, min(100, int(pct))) / 100.0, None)
        if int(pct) > 0:
            v.SetMute(0, None)
        return True
    except Exception:
        return False


def change_volume(delta):
    """Volume relatif (+/- points). Retourne le nouveau %, ou None."""
    cur = get_volume()
    if cur is None:
        return None
    pct = max(0, min(100, cur + int(delta)))
    return pct if set_volume(pct) else None


def set_app_mute(name_sub, mute=None):
    """Coupe/rétablit le son d'une application (« chrome », « spotify »…).
    mute=None bascule. Retourne les noms de process touchés."""
    import comtypes
    from pycaw.pycaw import AudioUtilities
    try:
        comtypes.CoInitialize()
    except Exception:
        pass
    q = name_sub.lower().strip().replace(" ", "")
    done = []
    for s in AudioUtilities.GetAllSessions():
        p = s.Process
        if not p:
            continue
        try:
            pname = p.name().lower()
        except Exception:
            continue
        if q in pname.replace(" ", "") or q in pname.replace(".exe", ""):
            v = s.SimpleAudioVolume
            m = (not v.GetMute()) if mute is None else bool(mute)
            v.SetMute(m, None)
            done.append(pname.replace(".exe", ""))
    return done


def resolve_exe(name):
    """« discord » → chemin de l'exécutable réel : App Paths du registre
    (HKLM puis HKCU), puis PATH, puis les dossiers usuels — c'est la cascade
    qui rend le lancement d'applis de JARVIS si fiable. None si introuvable."""
    import shutil
    import winreg
    name = (name or "").strip()
    if not name:
        return None
    exe = name if name.lower().endswith(".exe") else name + ".exe"
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            k = winreg.OpenKey(
                root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
                      "\\" + exe)
            path, _ = winreg.QueryValueEx(k, None)
            winreg.CloseKey(k)
            path = os.path.expandvars(str(path).strip('"'))
            if os.path.isfile(path):
                return path
        except OSError:
            continue
    w = shutil.which(name) or shutil.which(exe)
    if w:
        return w
    for pattern in (r"%LOCALAPPDATA%\Programs\{n}\{e}",
                    r"%LOCALAPPDATA%\{n}\{e}",
                    r"%APPDATA%\{n}\{e}",
                    r"%PROGRAMFILES%\{n}\{e}"):
        p = os.path.expandvars(pattern.format(n=name, e=exe))
        if os.path.isfile(p):
            return p
    # emplacements connus d'applis populaires qui ne s'enregistrent pas
    hints = {
        "spotify": r"%APPDATA%\Spotify\Spotify.exe",
        "claude": r"%LOCALAPPDATA%\AnthropicClaude\claude.exe",
        "obs": r"%PROGRAMFILES%\obs-studio\bin\64bit\obs64.exe",
        "obs64": r"%PROGRAMFILES%\obs-studio\bin\64bit\obs64.exe",
        "minecraftlauncher": r"%PROGRAMFILES(X86)%\Minecraft Launcher\MinecraftLauncher.exe",
        "telegram": r"%APPDATA%\Telegram Desktop\Telegram.exe",
    }
    h = hints.get(name.lower())
    if h:
        p = os.path.expandvars(h)
        if os.path.isfile(p):
            return p
    if name.lower() == "discord":
        # Discord vit dans un dossier versionné app-x.y.z
        import glob
        cands = sorted(glob.glob(os.path.expandvars(
            r"%LOCALAPPDATA%\Discord\app-*\Discord.exe")))
        if cands:
            return cands[-1]
    return None


def set_app_volume(name_sub, pct=None, delta=None):
    """Volume d'UNE application (pycaw SimpleAudioVolume — JARVIS le faisait
    au clavier, ici c'est précis). Retourne (noms_touchés, nouveau_pct)."""
    import comtypes
    from pycaw.pycaw import AudioUtilities
    try:
        comtypes.CoInitialize()
    except Exception:
        pass
    q = name_sub.lower().strip().replace(" ", "")
    done, newp = [], None
    for s in AudioUtilities.GetAllSessions():
        p = s.Process
        if not p:
            continue
        try:
            pname = p.name().lower()
        except Exception:
            continue
        if q in pname.replace(" ", "") or q in pname.replace(".exe", ""):
            v = s.SimpleAudioVolume
            if delta is not None:
                newp = max(0, min(100, v.GetMasterVolume() * 100 + delta))
            else:
                newp = max(0, min(100, int(pct or 0)))
            v.SetMasterVolume(newp / 100.0, None)
            done.append(pname.replace(".exe", ""))
    return done, (round(newp) if newp is not None else None)


def camera_b64(max_w=1024, quality=70):
    """Photo webcam → JPEG base64, encodée EN MÉMOIRE (jamais de fichier),
    envoyée uniquement au fournisseur IA choisi. Chauffe ~2 s pour laisser
    l'exposition se régler (JARVIS). None si pas de webcam/OpenCV."""
    try:
        import cv2
    except ImportError:
        return None
    import base64
    for idx in (0, 1):
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        try:
            if not cap.isOpened():
                continue
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            t0 = time.time()
            frame = None
            while time.time() - t0 < 2.0:
                ok, f = cap.read()
                if ok:
                    frame = f
                time.sleep(0.1)
            if frame is None:
                continue
            h, w = frame.shape[:2]
            if w > max_w:
                frame = cv2.resize(frame, (max_w, int(h * max_w / w)))
            ok, buf = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            if ok:
                return base64.b64encode(buf.tobytes()).decode()
        finally:
            cap.release()
    return None


def spotify_ui_search_play(query):
    """Repli SANS compte Spotify : pilote l'application au clavier (séquence
    et timings exacts de JARVIS). Fragile par nature — dernier recours."""
    import keyboard
    exe = os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe")
    if find_window("spotify"):
        focus_window("spotify")
    elif os.path.isfile(exe):
        subprocess.Popen([exe])
        time.sleep(4.0)
    else:
        try:
            os.startfile("spotify:")
            time.sleep(4.0)
        except OSError:
            return False
    time.sleep(0.5)
    keyboard.send("ctrl+l")
    time.sleep(0.5)
    keyboard.send("ctrl+k")
    time.sleep(0.4)
    keyboard.send("ctrl+a")
    time.sleep(0.1)
    if not set_clipboard(query):
        return False
    keyboard.send("ctrl+v")
    time.sleep(0.2)
    keyboard.send("enter")
    time.sleep(2.0)
    keyboard.send("enter")
    time.sleep(1.0)
    keyboard.send("enter")
    time.sleep(0.5)
    keyboard.send("enter")
    return True


def set_brightness(pct):
    """Luminosité de l'écran (WMI — portables et écrans compatibles)."""
    pct = max(0, min(100, int(pct)))
    try:
        cmd = ("(Get-WmiObject -Namespace root/WMI -Class "
               f"WmiMonitorBrightnessMethods).WmiSetBrightness(1,{pct})")
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW)
        return r.returncode == 0
    except Exception:
        return False


def get_brightness():
    """Luminosité actuelle 0-100, ou None (écran de bureau sans WMI)."""
    try:
        cmd = ("(Get-WmiObject -Namespace root/WMI -Class "
               "WmiMonitorBrightness).CurrentBrightness")
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW)
        return int(r.stdout.strip().splitlines()[0])
    except Exception:
        return None


def change_brightness(delta):
    cur = get_brightness()
    if cur is None:
        return None
    pct = max(0, min(100, cur + int(delta)))
    return pct if set_brightness(pct) else None


# ---- fenêtres : basculer, côte à côte ----

def list_windows():
    """[(hwnd, titre)] des fenêtres visibles avec un titre."""
    user32 = ctypes.windll.user32
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
    def cb(h, _):
        if user32.IsWindowVisible(h):
            n = user32.GetWindowTextLengthW(h)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(h, buf, n + 1)
                out.append((h, buf.value))
        return 1

    user32.EnumWindows(cb, 0)
    return out


def active_window_title():
    """Titre de la fenêtre au premier plan (« Boîte de réception - Gmail »,
    « WhatsApp », « claude.ai/new — Chrome »…), ou "" si indéterminé.
    Base de détection du mode Automatique (auto_mode.py)."""
    try:
        user32 = ctypes.windll.user32
        h = user32.GetForegroundWindow()
        if not h:
            return ""
        n = user32.GetWindowTextLengthW(h)
        if not n:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(h, buf, n + 1)
        return buf.value or ""
    except Exception:
        return ""


def active_process_name():
    """Nom de l'exécutable au premier plan en minuscules (« outlook.exe »,
    « slack.exe », « code.exe »…), ou "" si indéterminé. Complète le titre
    pour les apps de bureau dont le titre est peu parlant."""
    try:
        user32 = ctypes.windll.user32
        h = user32.GetForegroundWindow()
        if not h:
            return ""
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        import psutil
        return psutil.Process(pid.value).name().lower()
    except Exception:
        return ""


def find_window(name):
    """Fenêtre dont le titre contient name (le titre le plus court gagne :
    c'est en général la fenêtre principale de l'appli)."""
    q = (name or "").lower().strip()
    if not q:
        return None
    cands = [(h, t) for h, t in list_windows() if q in t.lower()]
    return min(cands, key=lambda x: len(x[1])) if cands else None


def focus_window(name):
    """Met la fenêtre au premier plan. Retourne son titre, ou None."""
    w = find_window(name)
    if not w:
        return None
    u = ctypes.windll.user32
    # une pression ALT simulée lève le refus de SetForegroundWindow
    u.keybd_event(0x12, 0, 0, 0)
    u.keybd_event(0x12, 0, 2, 0)
    if u.IsIconic(w[0]):
        u.ShowWindow(w[0], 9)          # SW_RESTORE
    u.SetForegroundWindow(w[0])
    return w[1]


def close_app(name):
    """« Ferme Chrome » (JARVIS) : d'abord WM_CLOSE sur la fenêtre trouvée
    (fermeture propre, non destructive — l'appli peut demander à sauvegarder),
    sinon terminate() des process du même nom. Retourne le nombre fermé."""
    q = (name or "").lower().strip()
    if not q:
        return 0
    w = find_window(q)
    if w:
        ctypes.windll.user32.PostMessageW(w[0], 0x0010, 0, 0)   # WM_CLOSE
        return 1
    done = 0
    try:
        import psutil
        qc = q.replace(" ", "")
        for p in psutil.process_iter(["name"]):
            try:
                pn = (p.info["name"] or "").lower().replace(".exe", "").replace(" ", "")
                if pn and (qc in pn or pn in qc):
                    p.terminate()
                    done += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
    return done


def _work_area():
    class _RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
    r = _RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)
    return r


def grid_windows_by_titles(titles):
    """Grille pour les fenêtres NOMMÉES du mode boulot : chaque cible lancée
    est retrouvée par son titre, les fenêtres parasites sont ignorées
    (fiabilise le mode boulot de JARVIS). Retourne le nombre positionné."""
    u = ctypes.windll.user32
    wins, seen = [], set()
    for t in titles:
        w = find_window(t)
        if w and w[0] not in seen:
            seen.add(w[0])
            wins.append(w)
    if len(wins) < 2:
        return grid_windows(max(2, len(titles)))
    r = _work_area()
    cols = 2
    rows = (len(wins) + cols - 1) // cols
    cw = (r.right - r.left) // cols
    ch = (r.bottom - r.top) // rows
    done = 0
    for i, (hw, _t) in enumerate(wins):
        cx, cy = i % cols, i // cols
        try:
            if u.IsIconic(hw):
                u.ShowWindow(hw, 9)
            u.MoveWindow(hw, r.left + cx * cw, r.top + cy * ch, cw, ch, True)
            done += 1
            time.sleep(0.2)     # laisse chaque fenêtre se redessiner (JARVIS)
        except Exception:
            pass
    return done


def grid_windows(n):
    """Dispose les n dernières fenêtres applicatives en grille (2×2, 2×3…),
    comme le « mode boulot » de JARVIS. Best-effort."""
    if n < 2:
        return 0
    u = ctypes.windll.user32
    wins = [(h, t) for h, t in list_windows()
            if t and t not in ("Nova", "Program Manager")][:n]
    if len(wins) < 2:
        return 0

    class _RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    r = _RECT()
    u.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)   # SPI_GETWORKAREA
    cols = 1 if len(wins) == 1 else 2
    rows = (len(wins) + cols - 1) // cols
    cw = (r.right - r.left) // cols
    ch = (r.bottom - r.top) // rows
    done = 0
    for i, (hw, _t) in enumerate(wins):
        cx, cy = i % cols, i // cols
        try:
            if u.IsIconic(hw):
                u.ShowWindow(hw, 9)         # SW_RESTORE
            u.MoveWindow(hw, r.left + cx * cw, r.top + cy * ch, cw, ch, True)
            done += 1
        except Exception:
            pass
    return done


def click_at(x, y, double=False):
    """Clic à des coordonnées écran absolues (vision : « clique sur… »)."""
    u = ctypes.windll.user32
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    for _ in range(2 if double else 1):
        u.mouse_event(0x0002, 0, 0, 0, 0)   # LEFTDOWN
        u.mouse_event(0x0004, 0, 0, 0, 0)   # LEFTUP
        time.sleep(0.05)
    return True


def screen_size():
    u = ctypes.windll.user32
    return u.GetSystemMetrics(0), u.GetSystemMetrics(1)


def side_by_side(name_a, name_b):
    """Deux fenêtres côte à côte (moitiés de l'écran). (titreA, titreB) ou None."""
    wa, wb = find_window(name_a), find_window(name_b)
    if not wa or not wb or wa[0] == wb[0]:
        return None
    u = ctypes.windll.user32

    class _RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    r = _RECT()
    u.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)   # SPI_GETWORKAREA
    half = (r.right - r.left) // 2
    for (hw, _t), x in ((wa, r.left), (wb, r.left + half)):
        if u.IsIconic(hw):
            u.ShowWindow(hw, 9)
        u.MoveWindow(hw, x, r.top, half, r.bottom - r.top, True)
    u.keybd_event(0x12, 0, 0, 0)
    u.keybd_event(0x12, 0, 2, 0)
    u.SetForegroundWindow(wa[0])
    return (wa[1], wb[1])
