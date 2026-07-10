"""
Wi-Fi and Bluetooth control -- the real thing, via the same command-line
tools you'd use by hand over SSH: `nmcli` (NetworkManager, the default
on current Raspberry Pi OS) for Wi-Fi, `bluetoothctl` (BlueZ) for
Bluetooth. Settings just drives these from the touchscreen.

Scanning and connecting can each take several seconds, and this OS's
render loop is single-threaded -- blocking it would freeze the whole
UI, touch input included. So every real operation here runs on a
background daemon thread and publishes its result into a small,
lock-protected snapshot; the Settings screen polls that snapshot every
frame (it opts into continuous rendering while a Wi-Fi/Bluetooth
section is open, the same way a game opts into `wants_animation`)
instead of blocking on the subprocess call itself.

Everything degrades gracefully if nmcli/bluetoothctl aren't installed
or there's no adapter present -- `available` reports that up front, and
every operation is wrapped so a missing tool or a failed command turns
into a status message for the UI, never an exception into it.
"""

import re
import shutil
import subprocess
import threading


def _have(cmd):
    return shutil.which(cmd) is not None


def _run(args, timeout=10):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout, r.stderr
    except FileNotFoundError:
        return False, "", f"{args[0]} not found"
    except subprocess.TimeoutExpired:
        return False, "", "timed out"
    except Exception as e:
        return False, "", str(e)


def _terse_split(line):
    """nmcli -t output escapes a literal ':' inside a field as '\\:'."""
    return [p.replace("\\:", ":") for p in re.split(r"(?<!\\):", line)]


# ================================ Wi-Fi =====================================

class WifiControl:
    def __init__(self):
        self.lock = threading.Lock()
        self.available = _have("nmcli")
        self.networks = []       # [{"ssid","signal","secure","connected"}]
        self.scanning = False
        self.status = None
        self.busy = False

    def snapshot(self):
        with self.lock:
            return {"available": self.available, "networks": list(self.networks),
                     "scanning": self.scanning, "status": self.status, "busy": self.busy}

    def is_radio_on(self):
        if not self.available:
            return None
        ok, out, _ = _run(["nmcli", "radio", "wifi"], timeout=5)
        return out.strip() == "enabled" if ok else None

    def set_radio(self, on):
        if not self.available:
            return
        threading.Thread(target=_run, args=(["nmcli", "radio", "wifi", "on" if on else "off"],),
                          daemon=True).start()

    def scan_async(self):
        if not self.available:
            with self.lock:
                self.status = "Wi-Fi needs NetworkManager (nmcli) - not available on this system"
            return
        with self.lock:
            if self.scanning:
                return
            self.scanning = True
            self.status = None
        threading.Thread(target=self._scan, daemon=True).start()

    def _scan(self):
        ok, out, err = _run(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE",
                              "dev", "wifi", "list", "--rescan", "yes"], timeout=15)
        networks = []
        if ok:
            seen = set()
            for line in out.strip().splitlines():
                parts = _terse_split(line)
                if len(parts) < 4:
                    continue
                ssid, signal, security, in_use = parts[0], parts[1], parts[2], parts[3]
                if not ssid or ssid in seen:
                    continue
                seen.add(ssid)
                try:
                    sig = int(signal)
                except ValueError:
                    sig = 0
                networks.append({"ssid": ssid, "signal": sig,
                                  "secure": bool(security.strip().strip("-")),
                                  "connected": in_use.strip() == "*"})
            networks.sort(key=lambda n: (not n["connected"], -n["signal"]))
        with self.lock:
            self.networks = networks
            self.scanning = False
            if not ok:
                self.status = f"Scan failed: {(err or out).strip() or 'unknown error'}"

    def connect_async(self, ssid, password=None):
        if not self.available:
            return
        with self.lock:
            self.busy = True
            self.status = f"Connecting to {ssid}\u2026"
        threading.Thread(target=self._connect, args=(ssid, password), daemon=True).start()

    def _connect(self, ssid, password):
        args = ["nmcli", "dev", "wifi", "connect", ssid]
        if password:
            args += ["password", password]
        ok, out, err = _run(args, timeout=25)
        with self.lock:
            self.busy = False
            self.status = f"Connected to {ssid}" if ok else \
                f"Couldn't connect: {(err or out).strip()[:80]}"
        self._scan()

    def disconnect_async(self, ssid):
        if not self.available:
            return
        with self.lock:
            self.busy = True
            self.status = f"Disconnecting\u2026"
        threading.Thread(target=self._disconnect, args=(ssid,), daemon=True).start()

    def _disconnect(self, ssid):
        ok, out, err = _run(["nmcli", "con", "down", ssid], timeout=10)
        with self.lock:
            self.busy = False
            self.status = "Disconnected" if ok else f"Couldn't disconnect: {err.strip()[:80]}"
        self._scan()

    def forget_async(self, ssid):
        if not self.available:
            return
        with self.lock:
            self.busy = True
            self.status = f"Forgetting {ssid}\u2026"
        threading.Thread(target=self._forget, args=(ssid,), daemon=True).start()

    def _forget(self, ssid):
        ok, out, err = _run(["nmcli", "con", "delete", ssid], timeout=10)
        with self.lock:
            self.busy = False
            self.status = "Forgotten" if ok else f"Couldn't forget: {err.strip()[:80]}"
        self._scan()


wifi = WifiControl()


# ============================== Bluetooth ===================================

class BluetoothControl:
    def __init__(self):
        self.lock = threading.Lock()
        self.available = _have("bluetoothctl")
        self.devices = []      # [{"mac","name","paired","connected"}]
        self.scanning = False
        self.status = None
        self.busy = False

    def snapshot(self):
        with self.lock:
            return {"available": self.available, "devices": list(self.devices),
                     "scanning": self.scanning, "status": self.status, "busy": self.busy}

    def is_powered_on(self):
        if not self.available:
            return None
        ok, out, _ = _run(["bluetoothctl", "show"], timeout=5)
        return ("Powered: yes" in out) if ok else None

    def set_power(self, on):
        if not self.available:
            return
        threading.Thread(target=_run, args=(["bluetoothctl", "power", "on" if on else "off"],),
                          kwargs={"timeout": 8}, daemon=True).start()

    def scan_async(self, seconds=8):
        if not self.available:
            with self.lock:
                self.status = "Bluetooth needs bluetoothctl (BlueZ) - not available on this system"
            return
        with self.lock:
            if self.scanning:
                return
            self.scanning = True
            self.status = None
        threading.Thread(target=self._scan, args=(seconds,), daemon=True).start()

    def _list_devices(self, extra_args=None):
        ok, out, err = _run(["bluetoothctl", "devices"] + (extra_args or []), timeout=8)
        devices = []
        if ok:
            for line in out.strip().splitlines():
                parts = line.split(" ", 2)
                if len(parts) == 3 and parts[0] == "Device":
                    devices.append({"mac": parts[1], "name": parts[2]})
        return devices, ok, err

    def _scan(self, seconds):
        _run(["timeout", str(seconds), "bluetoothctl", "scan", "on"], timeout=seconds + 5)
        found, ok, err = self._list_devices()
        paired, _, _ = self._list_devices(["Paired"])
        connected, _, _ = self._list_devices(["Connected"])
        paired_macs = {d["mac"] for d in paired}
        connected_macs = {d["mac"] for d in connected}
        for d in found:
            d["paired"] = d["mac"] in paired_macs
            d["connected"] = d["mac"] in connected_macs
        # make sure paired-but-not-freshly-discovered devices still show up
        found_macs = {d["mac"] for d in found}
        for d in paired:
            if d["mac"] not in found_macs:
                d["paired"] = True
                d["connected"] = d["mac"] in connected_macs
                found.append(d)
        found.sort(key=lambda d: (not d.get("connected"), not d.get("paired"), d["name"]))
        with self.lock:
            self.devices = found
            self.scanning = False
            if not ok:
                self.status = f"Scan failed: {err.strip()[:80]}"

    def pair_async(self, mac):
        if not self.available:
            return
        with self.lock:
            self.busy = True
            self.status = "Pairing\u2026"
        threading.Thread(target=self._pair, args=(mac,), daemon=True).start()

    def _pair(self, mac):
        ok, out, err = _run(["bluetoothctl", "pair", mac], timeout=20)
        if ok:
            _run(["bluetoothctl", "trust", mac], timeout=8)
            ok, out, err = _run(["bluetoothctl", "connect", mac], timeout=15)
        with self.lock:
            self.busy = False
            self.status = "Paired & connected" if ok else f"Pairing failed: {(err or out).strip()[:80]}"
        self._scan(3)

    def connect_async(self, mac):
        if not self.available:
            return
        with self.lock:
            self.busy = True
            self.status = "Connecting\u2026"
        threading.Thread(target=self._connect, args=(mac,), daemon=True).start()

    def _connect(self, mac):
        ok, out, err = _run(["bluetoothctl", "connect", mac], timeout=15)
        with self.lock:
            self.busy = False
            self.status = "Connected" if ok else f"Couldn't connect: {(err or out).strip()[:80]}"
        self._scan(3)

    def disconnect_async(self, mac):
        if not self.available:
            return
        with self.lock:
            self.busy = True
            self.status = "Disconnecting\u2026"
        threading.Thread(target=self._disconnect, args=(mac,), daemon=True).start()

    def _disconnect(self, mac):
        ok, out, err = _run(["bluetoothctl", "disconnect", mac], timeout=10)
        with self.lock:
            self.busy = False
            self.status = "Disconnected" if ok else f"Couldn't disconnect: {err.strip()[:80]}"
        self._scan(3)

    def remove_async(self, mac):
        if not self.available:
            return
        with self.lock:
            self.busy = True
            self.status = "Removing\u2026"
        threading.Thread(target=self._remove, args=(mac,), daemon=True).start()

    def _remove(self, mac):
        ok, out, err = _run(["bluetoothctl", "remove", mac], timeout=10)
        with self.lock:
            self.busy = False
            self.status = "Removed" if ok else f"Couldn't remove: {err.strip()[:80]}"
        self._scan(3)


bluetooth = BluetoothControl()
