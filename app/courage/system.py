"""Computer controls: volume, brightness, battery, Wi-Fi, Bluetooth, music, radio, photos."""
import glob
import os
import random
import re
import subprocess

HOME = os.path.expanduser("~")
MUSIC_DIRS = [os.path.join(HOME, "Music"), "/cdrom/music"]
PHOTO_DIRS = [os.path.join(HOME, "Pictures"), "/cdrom/photos"]


def run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception as e:
        return f"error: {e}"


def battery():
    caps = glob.glob("/sys/class/power_supply/BAT*/capacity")
    if not caps:
        return None
    try:
        return int(open(caps[0]).read().strip())
    except (OSError, ValueError):
        return None


def charging():
    st = glob.glob("/sys/class/power_supply/BAT*/status")
    return bool(st) and open(st[0]).read().strip() == "Charging"


def volume(value):
    sink = "@DEFAULT_AUDIO_SINK@"
    if value == "up":
        run(["wpctl", "set-volume", "-l", "1.0", sink, "10%+"])
    elif value == "down":
        run(["wpctl", "set-volume", sink, "10%-"])
    elif value == "mute":
        run(["wpctl", "set-mute", sink, "toggle"])
    elif str(value).isdigit():
        run(["wpctl", "set-volume", sink, f"{min(100, int(value))}%"])


def brightness(value):
    if value == "up":
        run(["sudo", "-n", "brightnessctl", "set", "10%+"])
    elif value == "down":
        run(["sudo", "-n", "brightnessctl", "set", "10%-"])
    elif str(value).isdigit():
        run(["sudo", "-n", "brightnessctl", "set", f"{min(100, max(5, int(value)))}%"])


def wifi_on():
    return run(["nmcli", "-t", "-f", "STATE", "general"]).startswith("connected")


def wifi_scan():
    out = run(["nmcli", "-t", "-f", "SSID,SIGNAL", "device", "wifi", "list", "--rescan", "yes"])
    nets = []
    for line in out.splitlines():
        ssid, _, sig = line.rpartition(":")
        if ssid and ssid not in [n[0] for n in nets]:
            nets.append((ssid.replace("\\:", ":"), sig))
    return nets[:8]


def wifi_connect(ssid, password):
    out = run(["sudo", "-n", "nmcli", "device", "wifi", "connect", ssid, "password", password], timeout=45)
    return "successfully" in out


def bt(cmd, name=""):
    if cmd == "scan":
        run(["bluetoothctl", "--timeout", "8", "scan", "on"], timeout=12)
        out = run(["bluetoothctl", "devices"])
        return [l.split(" ", 2)[2] for l in out.splitlines() if l.count(" ") >= 2]
    out = run(["bluetoothctl", "devices"])
    for line in out.splitlines():
        parts = line.split(" ", 2)
        if len(parts) == 3 and name.lower() in parts[2].lower():
            mac = parts[1]
            if cmd == "connect":
                run(["bluetoothctl", "pair", mac], timeout=20)
                run(["bluetoothctl", "trust", mac])
                return "Connection successful" in run(["bluetoothctl", "connect", mac], timeout=20)
            run(["bluetoothctl", "disconnect", mac])
            return True
    return False


def bt_status():
    out = run(["bluetoothctl", "show"])
    if "Powered: yes" not in out:
        return "off"
    conn = run(["bluetoothctl", "devices", "Connected"])
    names = [l.split(" ", 2)[2] for l in conn.splitlines() if l.count(" ") >= 2]
    return ("connected to " + ", ".join(names)) if names else "on, nothing connected"


def music_files():
    files = []
    for d in MUSIC_DIRS:
        for ext in ("mp3", "m4a", "flac", "ogg", "wav", "opus"):
            files += glob.glob(os.path.join(d, "**", "*." + ext), recursive=True)
    return sorted(files)


def photo_files():
    files = []
    for d in PHOTO_DIRS:
        for ext in ("jpg", "jpeg", "png", "gif", "webp", "JPG", "JPEG", "PNG"):
            files += glob.glob(os.path.join(d, "**", "*." + ext), recursive=True)
    return sorted(files)


class Player:
    """Plays music files or a radio stream with mpv, controlled over its IPC socket."""
    SOCK = "/tmp/courage-mpv.sock"

    def __init__(self):
        self.proc = None
        self.now = ""

    def _ipc(self, *args):
        import json
        import socket
        try:
            s = socket.socket(socket.AF_UNIX)
            s.connect(self.SOCK)
            s.send((json.dumps({"command": list(args)}) + "\n").encode())
            s.close()
        except OSError:
            pass

    def play(self, items, label):
        self.stop()
        self.proc = subprocess.Popen(["mpv", "--no-video", "--really-quiet", f"--input-ipc-server={self.SOCK}"] + items)
        self.now = label

    def play_music(self, query=""):
        files = music_files()
        if not files:
            return None
        if query:
            q = re.sub(r"[^a-z0-9 ]", "", query.lower())
            match = [f for f in files if all(w in f.lower() for w in q.split())]
            files = match or files
        else:
            random.shuffle(files)
        self.play(files, os.path.splitext(os.path.basename(files[0]))[0])
        return self.now

    def pause(self):
        self._ipc("set_property", "pause", True)

    def resume(self):
        self._ipc("set_property", "pause", False)

    def next(self):
        self._ipc("playlist-next")

    def duck(self, on):
        self._ipc("set_property", "volume", 35 if on else 100)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.proc = None
        self.now = ""
