# Courage OS — how to build it, run it, and add your Gemini API key

## 1. Build the ISO (one command, in the Mac Terminal)

1. Install **Docker Desktop** (free) from docker.com and open it once. It gives the Mac the Linux
   tools needed to build an operating system. You never have to touch it.
2. In Docker Desktop → Settings → Resources, give it at least **8 GB memory** and **60 GB disk**.
3. Open **Terminal**, go into this folder, and run:

```
cd ~/Downloads/courage-os
./build-mac.sh
```

It downloads everything, builds the Intel and Mac-chip versions and packs both into one file:
**`courage-os.iso`** (about 3-4 GB), right in this folder. It takes 1-2 hours the first time; keep the
Mac plugged in. Running it again is much faster.

(Already on Ubuntu 24.04? Run `sudo ./build.sh` instead.)

## 2. Put it on your 64 GB USB

On your Mac, use **balenaEtcher** (free): pick `courage-os.iso`, pick the USB stick, then Flash.

## 3. Start it

**Intel / AMD PC:** plug in the USB, turn on, tap the boot menu key (F12, F11, F9 or Esc), pick the USB.
Turn **Secure Boot off** in the PC's settings first, or it won't start.

**Intel Mac:** hold **Option** at start-up and pick the USB. Newer Intel Macs with the T2 chip need
Startup Security Utility → "No Security" + "Allow booting from external media".

**M1 iMac / M4 MacBook Air (UTM):**
1. UTM → Create a New Virtual Machine → **Virtualize** → **Linux**.
2. Boot ISO image: choose `courage-os.iso` (straight from the USB is fine).
3. Memory 4096 MB, 4 CPU cores, storage **8 GB** (this blank disk is where it saves your stuff).
4. In the VM settings, turn on sound input so it can hear you, and allow the microphone when the Mac asks.
5. Press play.

The first start makes its storage space and restarts once. That's normal.

## 4. Add your Gemini API key (the brain)

1. On any device, go to **aistudio.google.com** and sign in with your Google account.
2. Click **Get API key** → **Create API key**, and copy it. It starts with `AIza`.
   The free tier is enough for normal use; no card needed.
3. Start Courage OS. The first screen says **FIRST, MY BRAIN.**
4. Type the key into the top box, plus your name and town (for the weather), then press **WAKE UP**.

It checks the key straight away. If it says the key didn't work, check for typos and that you're online.
The key is saved on the USB (or the UTM disk), so you only do this once. **Never share the key.**

## 5. Using it

* **Just talk.** No buttons. Or start typing on the keyboard any time.
* **Moods:** "be nice", "be grumpy", "be extra rude".
* **Screen colour:** "make the screen blue" / "back to green".
* **Music:** put songs in the **Music** folder. Photos go in **Pictures**.
* **Wi-Fi:** "connect to my Wi-Fi", then type the password when asked. It never says it out loud.
* **Bluetooth:** "scan Bluetooth", then "connect my headphones". On the Macs, connect headphones on the Mac itself.
* **Turn off:** press the computer's **power button** once. In UTM, press UTM's power button at the top.
  Closing the UTM window also works, but it won't say goodbye first.

## Good to know

* With no internet it switches to its spare brain: time, date, notes, sums, music and volume only.
* "Make pictures" draws simple pictures using Gemini. Photos for answers come from Wikimedia Commons.
* Weather comes from Open-Meteo, news from BBC headlines and radio from radio-browser.info. All free, no extra keys.
* "Multiple users" switches when you tell it ("it's my sister now"). It can't tell voices apart by itself.
* "Updates" needs an update address set up. Without one, rebuild the ISO to get a new version.
* If the screen stays black, pick **Courage OS (safe graphics)** in the boot menu.
* Logs, if something goes wrong: `~/.courage-app.log` and `~/.courage-screen.log`.
