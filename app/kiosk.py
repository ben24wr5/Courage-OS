#!/usr/bin/env python3
"""Full-screen window that shows the green screen (runs inside the Cage kiosk compositor)."""
import os
import time
import urllib.request

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, WebKit2  # noqa: E402

URL = "http://127.0.0.1:8765/"

for _ in range(120):  # wait for the back end to start
    try:
        urllib.request.urlopen(URL, timeout=1)
        break
    except Exception:
        time.sleep(0.5)

win = Gtk.Window()
win.connect("destroy", Gtk.main_quit)
view = WebKit2.WebView()
s = view.get_settings()
s.set_enable_developer_extras(False)
s.set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.NEVER if os.environ.get("COURAGE_SAFE_GFX")
                                   else WebKit2.HardwareAccelerationPolicy.ON_DEMAND)
view.connect("context-menu", lambda *a: True)
view.load_uri(URL)
win.add(view)
win.fullscreen()
win.show_all()
Gtk.main()
