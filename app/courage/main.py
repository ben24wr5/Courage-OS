"""COURAGE OS main program: runs the green screen's back end on http://127.0.0.1:8765."""
import asyncio
import datetime
import json
import os
import random
import subprocess
import threading

from aiohttp import web

from . import offline, system, web as live
from .brain import Brain, MOODS, KeyError_

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.expanduser("~/.courage")
CONFIG = os.path.join(DATA, "config.json")
MODELS = os.environ.get("COURAGE_MODELS", "/opt/courage/models")
PORT = 8765

WAKEUPS = [("HUH?", "Oh. It's you again."), ("WHAT?!", "I was having a lovely dream."), ("UGH.", "Five more minutes..."),
           ("WHO DARES?", "Oh. Only you."), ("HMPH.", "You again? Don't you sleep?"),
           ("OI!", "I was resting my circuits."), ("*YAWN*", "Fine. I'm awake. Happy now?"),
           ("NOT NOW...", "Oh, go on then. What is it?"), ("ZZ-WHAT?", "Right. Yes. Awake. Obviously.")]
GOODBYES = ["Leaving already? Fine. Saving your notes. Shutting down.",
            "Finally, some peace. Saving everything. Goodnight.",
            "Off I go. Don't wake me unless it's important."]


class Courage:
    def __init__(self):
        os.makedirs(DATA, exist_ok=True)
        self.cfg = self._load()
        self.clients = set()
        self.loop = None
        self.brain = Brain(self.cfg.get("api_key"))
        self.player = system.Player()
        self.busy = threading.Lock()
        self.photos, self.photo_i = [], 0
        self.wifi_pending = None
        self.ears = self.voice = None

    # ---------- storage ----------
    def _load(self):
        try:
            with open(CONFIG) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {"users": {}, "user": "", "city": "", "last_wake": -1}

    def save(self):
        tmp = CONFIG + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.cfg, f, indent=1)
        os.chmod(tmp, 0o600)
        os.replace(tmp, CONFIG)

    @property
    def me(self):
        name = self.cfg.get("user") or "friend"
        return self.cfg.setdefault("users", {}).setdefault(name, {"memory": [], "notes": [], "mood": "grumpy",
                                                                   "colour": "default"})

    # ---------- talking to the screen ----------
    def send(self, msg):
        if not self.loop:
            return
        data = json.dumps(msg)
        for ws in list(self.clients):
            asyncio.run_coroutine_threadsafe(ws.send_str(data), self.loop)

    def status(self):
        b = system.battery()
        return {"t": "status", "battery": b, "charging": system.charging(), "wifi": system.wifi_on(),
                "bt": system.bt_status() != "off", "mood": self.me["mood"], "colour": self.me["colour"],
                "user": self.cfg.get("user", "")}

    def show(self, head, body="", pic=None, svg="", say=None):
        self.send({"t": "show", "head": head, "body": body, "pic": pic, "svg": svg})
        if say:
            self.player.duck(True)
            self.send({"t": "speaking", "on": True})
            self.voice.say(say, done=lambda: (self.player.duck(False), self.send({"t": "speaking", "on": False})))

    # ---------- startup ----------
    def wake_up(self):
        i = random.randrange(len(WAKEUPS))
        if i == self.cfg.get("last_wake"):
            i = (i + 1) % len(WAKEUPS)
        self.cfg["last_wake"] = i
        self.save()
        head, line = WAKEUPS[i]
        self.send({"t": "wake", "head": head, "line": line.upper()})
        self.voice.say(line)
        if not self.cfg.get("api_key"):
            self.send({"t": "setup"})
            return
        threading.Timer(4, lambda: self.handle("(SYSTEM: Courage OS just booted. Greet the user by name if known "
                                                "and give one short surprising fact of the day.)", typed=True,
                                                quiet_heard=True)).start()

    # ---------- the main loop: something was said ----------
    def heard(self, text):
        self.handle(text)

    def handle(self, text, typed=False, quiet_heard=False):
        if not self.busy.acquire(blocking=False):
            return
        try:
            if self.wifi_pending and typed:
                return self._finish_wifi(text)
            if not quiet_heard:
                self.send({"t": "heard", "text": text.upper()})
            self.send({"t": "thinking"})
            is_online = live.online()
            if not self.cfg.get("api_key"):
                self.send({"t": "setup"})
                return
            if not is_online:
                r = offline.answer(text, self.me["notes"])
            else:
                try:
                    r = self.brain.ask(text, self.context(is_online))
                except Exception as e:
                    print("brain error:", e, flush=True)
                    if isinstance(e, KeyError_):
                        self.show("MY BRAIN KEY IS WRONG.", "RE-ENTER YOUR GEMINI API KEY.", say="My brain key isn't working.")
                        self.send({"t": "setup"})
                        return
                    r = offline.answer(text, self.me["notes"])
            for fact in r.get("remember", []):
                if fact not in self.me["memory"]:
                    self.me["memory"].append(fact)
            self.me["memory"] = self.me["memory"][-60:]
            pic = None
            if r.get("image") and is_online and not r.get("svg"):
                pic = live.picture(r["image"])
            self.show(r.get("head", ""), r.get("body", ""), pic, r.get("svg", ""), say=r.get("say"))
            for a in r.get("actions", []):
                try:
                    self.act(a)
                except Exception as e:
                    print("action error:", a, e, flush=True)
            self.save()
            self.send(self.status())
        finally:
            self.busy.release()

    def context(self, is_online):
        me = self.me
        city = self.cfg.get("city", "")
        return {
            "now": datetime.datetime.now().strftime("%A %d %B %Y, %H:%M"),
            "user": self.cfg.get("user") or "unknown (ask their name)",
            "memory": "; ".join(me["memory"]) or "nothing yet",
            "notes": "; ".join(me["notes"]) or "none",
            "mood": me["mood"],
            "battery": (f"{system.battery()}%" if system.battery() is not None else "plugged in (no battery)"),
            "online": "yes" if is_online else "no",
            "bt": system.bt_status(),
            "city": city or "unknown",
            "weather": live.weather(city) if is_online else "offline",
            "news": live.news() if is_online else "offline",
            "music": ", ".join(os.path.basename(f) for f in system.music_files()[:40]) or "none yet",
            "photos": f"{len(system.photo_files())} photos",
        }

    # ---------- actions ----------
    def act(self, a):
        t = a.get("type")
        me = self.me
        if t == "note_add" and a.get("text"):
            me["notes"].append(a["text"])
        elif t == "notes_clear":
            me["notes"] = []
        elif t == "music":
            cmd = a.get("cmd", "play")
            if cmd == "play":
                if not self.player.play_music(a.get("query", "")):
                    self.show("NO MUSIC FOUND.", "PUT SONGS IN THE MUSIC FOLDER ON THE USB.", say="There's no music on me yet.")
            elif cmd == "pause":
                self.player.pause()
            elif cmd == "resume":
                self.player.resume()
            elif cmd == "next":
                self.player.next()
            else:
                self.player.stop()
        elif t == "radio":
            if a.get("cmd") == "stop":
                self.player.stop()
            else:
                st = live.radio_station(a.get("query", "BBC Radio 1"))
                if st:
                    self.player.play([st[1]], st[0])
                    self.send({"t": "body", "text": f"TUNED IN TO {st[0].upper()}."})
        elif t == "photos":
            cmd = a.get("cmd", "show")
            if cmd == "show":
                self.photos, self.photo_i = system.photo_files(), 0
            elif cmd == "next":
                self.photo_i += 1
            elif cmd == "back":
                self.photo_i -= 1
            if cmd == "stop" or not self.photos:
                self.send({"t": "photo", "url": None})
            else:
                self.photo_i %= len(self.photos)
                self.send({"t": "photo", "url": f"/photo/{self.photo_i}",
                           "label": f"PHOTO {self.photo_i + 1} OF {len(self.photos)}"})
        elif t == "volume":
            system.volume(a.get("value", "up"))
        elif t == "brightness":
            system.brightness(a.get("value", "up"))
        elif t == "wifi":
            if a.get("cmd") == "connect" and a.get("ssid"):
                self.wifi_pending = a["ssid"]
                self.send({"t": "password", "ssid": a["ssid"]})
            else:
                nets = system.wifi_scan()
                if nets:
                    self.send({"t": "pick", "kind": "wifi", "title": "PICK YOUR WI-FI:",
                               "items": [n[0] for n in nets], "notes": [f"{n[1]}%" for n in nets]})
                else:
                    self.send({"t": "body", "text": "NO WI-FI FOUND."})
        elif t == "bluetooth":
            cmd = a.get("cmd", "scan")
            if cmd == "scan":
                names = system.bt("scan")
                if names:
                    self.send({"t": "pick", "kind": "bt", "title": "PICK WHAT TO CONNECT:", "items": names[:10]})
                else:
                    self.send({"t": "body", "text": "NOTHING FOUND. PUT IT IN PAIRING MODE AND SAY 'SCAN BLUETOOTH' AGAIN."})
            else:
                ok = system.bt(cmd, a.get("name", ""))
                self.send({"t": "body", "text": ("DONE." if ok else "COULDN'T FIND IT. SAY 'SCAN BLUETOOTH' FIRST.")})
        elif t == "colour":
            me["colour"] = a.get("value", "default")
        elif t == "mood" and a.get("value") in MOODS:
            me["mood"] = a["value"]
        elif t == "user" and a.get("name"):
            self.cfg["user"] = a["name"].strip().title()
            self.brain.reset()
        elif t == "city" and a.get("name"):
            self.cfg["city"] = a["name"]
        elif t == "update":
            threading.Thread(target=self._update, daemon=True).start()
        elif t == "screensaver":
            self.send({"t": "sleep"})

    def picked(self, kind, item):
        if not item:
            return
        if kind == "wifi":
            self.wifi_pending = item
            self.send({"t": "password", "ssid": item})
            self.voice.say("Type the password. I won't say it out loud.")
        elif kind == "bt":
            self.send({"t": "show", "head": "CONNECTING...", "body": item.upper(), "pic": None, "svg": ""})
            ok = system.bt("connect", item)
            if ok:
                self.show("CONNECTED.", f"{item.upper()}. SOUND NOW PLAYS THROUGH IT. NEXT TIME IT CONNECTS BY ITSELF.",
                          say="Connected.")
            else:
                self.show("THAT DIDN'T WORK.", "IS IT STILL IN PAIRING MODE? SAY 'SCAN BLUETOOTH' TO TRY AGAIN.",
                          say="That didn't work. Is it still in pairing mode?")
            self.send(self.status())

    def _finish_wifi(self, password):
        ssid, self.wifi_pending = self.wifi_pending, None
        self.send({"t": "thinking"})
        ok = system.wifi_connect(ssid, password)
        if ok:
            self.show("CONNECTED.", f"ON {ssid.upper()}. FULL BRAIN POWER RESTORED.", say="Connected. Full brain power.")
        else:
            self.show("THAT DIDN'T WORK.", "WRONG PASSWORD? SAY 'CONNECT TO MY WI-FI' TO TRY AGAIN.", say="That didn't work.")
        self.send(self.status())

    def _update(self):
        url = self.cfg.get("update_url")
        if not url or not os.path.exists("/opt/courage/update.sh"):
            self.show("NO UPDATES SET UP.", "THERE'S NO UPDATE ADDRESS YET. REBUILD THE ISO TO GET A NEWER VERSION.",
                      say="No update address is set up yet.")
            return
        r = subprocess.run(["sudo", "-n", "/opt/courage/update.sh", url], capture_output=True, text=True)
        self.show("UPDATED." if r.returncode == 0 else "UPDATE FAILED.", "RESTART ME TO USE IT." if r.returncode == 0 else "",
                  say="Updated." if r.returncode == 0 else "The update failed.")

    # ---------- setup and power ----------
    def setup(self, data):
        key = (data.get("key") or "").strip()
        b = Brain(key)
        try:
            b.check_key()
        except Exception as e:
            print("key check:", e, flush=True)
            self.send({"t": "setup", "error": "THAT KEY DIDN'T WORK. CHECK IT AND TRY AGAIN. (ARE YOU ONLINE?)"})
            return
        self.cfg["api_key"] = key
        if data.get("name"):
            self.cfg["user"] = data["name"].strip().title()
        if data.get("city"):
            self.cfg["city"] = data["city"].strip()
        self.brain = b
        self.save()
        self.send({"t": "ready"})
        self.handle("(SYSTEM: Setup just finished. Welcome them, and in two short sentences explain they can just talk "
                    "to you, or type.)", typed=True, quiet_heard=True)

    def _setup_wifi_scan(self):
        self.send({"t": "wifi_list", "online": live.online(), "nets": [n[0] for n in system.wifi_scan()]})

    def _setup_wifi_join(self, ssid, pw):
        ok = bool(ssid) and system.wifi_connect(ssid, pw)
        self.send({"t": "wifi_result", "ok": ok, "ssid": ssid})
        self.send(self.status())

    def power_off(self):
        self.player.stop()
        self.save()
        line = random.choice(GOODBYES)
        self.send({"t": "goodbye", "head": "LEAVING ALREADY? FINE.", "body": "SAVING YOUR NOTES... SHUTTING DOWN COURAGE OS."})
        done = threading.Event()
        self.voice.say(line, done=done.set)
        done.wait(8)
        self.send({"t": "off"})
        subprocess.run(["sync"])
        subprocess.Popen(["sudo", "-n", "systemctl", "poweroff"])

    # ---------- web server ----------
    async def ws(self, request):
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        self.clients.add(ws)
        await ws.send_str(json.dumps(self.status()))
        first = len(self.clients) == 1 and not getattr(self, "_woke", False)
        if first:
            self._woke = True
            threading.Thread(target=self.wake_up, daemon=True).start()
        async for m in ws:
            try:
                d = json.loads(m.data)
            except (TypeError, ValueError):
                continue
            if d.get("t") == "typed" and d.get("text"):
                threading.Thread(target=self.handle, args=(d["text"],), kwargs={"typed": True}, daemon=True).start()
            elif d.get("t") == "setup":
                threading.Thread(target=self.setup, args=(d,), daemon=True).start()
            elif d.get("t") == "wifi_scan":
                threading.Thread(target=self._setup_wifi_scan, daemon=True).start()
            elif d.get("t") == "wifi_join":
                threading.Thread(target=self._setup_wifi_join, args=(d.get("ssid", ""), d.get("pw", "")),
                                 daemon=True).start()
            elif d.get("t") == "picked":
                threading.Thread(target=self.picked, args=(d.get("kind"), d.get("item", "")), daemon=True).start()
            elif d.get("t") == "status":
                await ws.send_str(json.dumps(self.status()))
        self.clients.discard(ws)
        return ws

    async def photo(self, request):
        i = int(request.match_info["i"])
        if 0 <= i < len(self.photos):
            return web.FileResponse(self.photos[i])
        raise web.HTTPNotFound()

    async def power(self, request):
        if request.remote not in ("127.0.0.1", "::1"):
            raise web.HTTPForbidden()
        threading.Thread(target=self.power_off, daemon=True).start()
        return web.Response(text="ok")

    def run(self):
        from .ears import Ears
        from .voice import Voice
        self.ears = Ears(os.path.join(MODELS, "whisper"),
                         on_text=self.heard,
                         on_level=lambda lvl, talking: self.send({"t": "level", "v": round(lvl, 2), "talking": talking}))
        self.voice = Voice(os.path.join(MODELS, "voice", "voice.onnx"), self.ears)
        app = web.Application()
        app.router.add_get("/ws", self.ws)
        app.router.add_get("/photo/{i}", self.photo)
        app.router.add_post("/power", self.power)
        app.router.add_get("/", lambda r: web.FileResponse(os.path.join(BASE, "screen", "index.html")))
        app.router.add_static("/screen/", os.path.join(BASE, "screen"))

        async def on_start(app):
            self.loop = asyncio.get_running_loop()
            self.ears.start()

        app.on_startup.append(on_start)
        web.run_app(app, host="127.0.0.1", port=PORT, print=None)


def main():
    Courage().run()


if __name__ == "__main__":
    main()
