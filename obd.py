# -*- coding: utf-8 -*-
"""
OBD-II / ELM327 (porté de RoadSpeak) : lecture régime moteur, vitesse,
température liquide de refroidissement et codes défaut, via pyserial —
plus un mode simulé pour tout tester sans adaptateur.
Toute anomalie déclenche une annonce vocale prioritaire.
"""

import threading
import time

DTC_DESCRIPTIONS = {
    "P0217": "surchauffe moteur",
    "P0300": "ratés d'allumage détectés",
    "P0420": "efficacité catalyseur faible",
    "P0128": "thermostat liquide de refroidissement",
    "P0171": "mélange trop pauvre",
    "P0455": "fuite importante système évaporation",
}


def list_ports():
    try:
        from serial.tools import list_ports as lp
        return [{"path": p.device, "name": p.description or p.device} for p in lp.comports()]
    except Exception:
        return []


class ObdManager:
    def __init__(self, on_alert=None, on_update=None):
        self.on_alert = on_alert or (lambda text: None)
        self.on_update = on_update or (lambda snap: None)
        self.snapshot = self._empty()
        self._ser = None
        self._stop = threading.Event()
        self._thread = None
        self._alerted = set()
        self._last_coolant_alert = 0.0
        self.coolant_alert_c = 105
        self._mock_t0 = 0.0

    def _empty(self):
        return {"connected": False, "mock": False, "rpm": None, "speed": None,
                "coolant": None, "dtc": [], "error": ""}

    # ------------------------------------------------------------ contrôle --
    def connect(self, port, mock, coolant_alert_c=105, poll_ms=2000):
        self.disconnect()
        self.coolant_alert_c = coolant_alert_c
        self._stop.clear()
        self._alerted.clear()
        if mock:
            self.snapshot = {**self._empty(), "connected": True, "mock": True,
                             "rpm": 900, "speed": 0, "coolant": 70}
            self._mock_t0 = time.time()
            self._thread = threading.Thread(target=self._mock_loop, args=(poll_ms,), daemon=True)
            self._thread.start()
            self.on_update(self.snapshot)
            return True
        try:
            import serial
            self._ser = serial.Serial(port, 38400, timeout=1.5)
            for cmd in ("ATZ", "ATE0", "ATL0", "ATS0", "ATSP0"):
                self._command(cmd)
                time.sleep(0.3 if cmd == "ATZ" else 0.1)
            self.snapshot = {**self._empty(), "connected": True}
            self._thread = threading.Thread(target=self._real_loop, args=(poll_ms,), daemon=True)
            self._thread.start()
            self.on_update(self.snapshot)
            return True
        except Exception as e:
            self.snapshot = {**self._empty(), "error": str(e)[:120]}
            self.on_update(self.snapshot)
            return False

    def disconnect(self):
        self._stop.set()
        if self._ser:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
        self.snapshot = self._empty()
        self.on_update(self.snapshot)

    # ---------------------------------------------------------------- mock --
    def _mock_loop(self, poll_ms):
        import math
        while not self._stop.is_set():
            t = time.time() - self._mock_t0
            s = self.snapshot
            s["rpm"] = round(1500 + 900 * math.sin(t / 7) + 200 * math.sin(t / 1.7))
            s["speed"] = max(0, round(55 + 35 * math.sin(t / 11)))
            # la température grimpe pour démontrer l'alerte vocale (~2 min)
            s["coolant"] = min(112, round(70 + t / 3))
            if t > 90 and "P0217" not in s["dtc"]:
                s["dtc"] = ["P0217"]
            self._check_alerts()
            self.on_update(s)
            self._stop.wait(max(0.8, poll_ms / 1000))

    # ---------------------------------------------------------------- réel --
    def _command(self, cmd):
        if not self._ser:
            return ""
        try:
            self._ser.reset_input_buffer()
            self._ser.write((cmd + "\r").encode("ascii"))
            out = b""
            deadline = time.time() + 2.0
            while time.time() < deadline:
                chunk = self._ser.read(64)
                out += chunk
                if b">" in out:
                    break
            return out.decode("ascii", "replace").replace(">", "").strip()
        except Exception:
            return ""

    @staticmethod
    def _parse_bytes(resp, prefix):
        flat = "".join(c for c in resp if c in "0123456789ABCDEFabcdef").upper()
        idx = flat.find(prefix)
        if idx < 0:
            return None
        hexs = flat[idx + len(prefix):]
        return [int(hexs[i:i + 2], 16) for i in range(0, min(len(hexs) - 1, 8), 2)]

    def _real_loop(self, poll_ms):
        last_dtc = 0.0
        while not self._stop.is_set() and self._ser:
            s = self.snapshot
            b = self._parse_bytes(self._command("010C"), "410C")
            if b and len(b) >= 2:
                s["rpm"] = round((b[0] * 256 + b[1]) / 4)
            b = self._parse_bytes(self._command("010D"), "410D")
            if b:
                s["speed"] = b[0]
            b = self._parse_bytes(self._command("0105"), "4105")
            if b:
                s["coolant"] = b[0] - 40
            if time.time() - last_dtc > 30:
                last_dtc = time.time()
                codes = self._parse_dtc(self._command("03"))
                if codes is not None:
                    s["dtc"] = codes
            self._check_alerts()
            self.on_update(s)
            self._stop.wait(max(0.8, poll_ms / 1000))

    @staticmethod
    def _parse_dtc(resp):
        flat = "".join(c for c in resp if c in "0123456789ABCDEFabcdef").upper()
        idx = flat.find("43")
        if idx < 0:
            return None
        hexs = flat[idx + 2:]
        codes = []
        for i in range(0, len(hexs) - 3, 4):
            chunk = hexs[i:i + 4]
            if chunk == "0000":
                continue
            first = int(chunk[0], 16)
            letter = "PCBU"[first >> 2]
            codes.append(f"{letter}{first & 3:X}{chunk[1:]}")
        return codes

    # -------------------------------------------------------------- alertes -
    def _check_alerts(self):
        s = self.snapshot
        now = time.time()
        if (s["coolant"] is not None and s["coolant"] >= self.coolant_alert_c
                and now - self._last_coolant_alert > 300):
            self._last_coolant_alert = now
            self.on_alert(f"Attention. Température moteur élevée : {s['coolant']} degrés.")
        for code in s["dtc"]:
            if code not in self._alerted:
                self._alerted.add(code)
                desc = DTC_DESCRIPTIONS.get(code, "défaut moteur")
                self.on_alert(f"Attention. Code défaut {' '.join(code)} : {desc}.")
