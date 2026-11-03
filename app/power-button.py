#!/usr/bin/env python3
"""Watches the computer's power button (also UTM's power button). Tells Courage OS to say goodbye,
save and shut down safely. If the app doesn't answer, shuts down anyway."""
import subprocess
import time
import urllib.request

import evdev
from evdev import ecodes
import select


def power_keys():
    devs = []
    for path in evdev.list_devices():
        try:
            d = evdev.InputDevice(path)
            if ecodes.KEY_POWER in d.capabilities().get(ecodes.EV_KEY, []):
                devs.append(d)
        except OSError:
            pass
    return devs


def shutdown():
    try:
        urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8765/power", method="POST"), timeout=3)
        time.sleep(15)  # app says goodbye then powers off; this is the safety net
    except Exception:
        pass
    subprocess.run(["sync"])
    subprocess.run(["systemctl", "poweroff"])


while True:
    devs = power_keys()
    if not devs:
        time.sleep(5)
        continue
    r, _, _ = select.select(devs, [], [], 30)
    for d in r:
        try:
            for ev in d.read():
                if ev.type == ecodes.EV_KEY and ev.code == ecodes.KEY_POWER and ev.value == 1:
                    shutdown()
        except OSError:
            pass
