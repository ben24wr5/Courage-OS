#!/bin/bash
# ============================================================================
#  COURAGE OS  ·  one-command ISO builder
#  Builds ONE ISO that boots on Intel/AMD PCs (x86_64) AND runs in UTM on
#  Apple M-chip Macs (arm64). Run on Ubuntu 24.04 (a UTM virtual machine is
#  fine):   sudo ./build.sh
#  Result:  courage-os.iso  (next to this script)
# ============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${WORK:-$HERE/build}"
OUT="$HERE/courage-os.iso"
SUITE=noble
ARCHES="${ARCHES:-amd64 arm64}"

say() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "Run it with sudo:  sudo ./build.sh"
grep -q 'VERSION_ID="24.04"' /etc/os-release || echo "Warning: this was written for Ubuntu 24.04."
mkdir -p "$WORK"
FREE_GB=$(( $(df --output=avail -k "$WORK" | tail -1) / 1024 / 1024 ))
[ "$FREE_GB" -ge 25 ] || die "Need about 25 GB of free disk space here, only ${FREE_GB} GB free."

# ---------------------------------------------------------------- host tools
say "Installing the build tools"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq debootstrap qemu-user-static binfmt-support \
  squashfs-tools xorriso dosfstools mtools curl ca-certificates >/dev/null
systemctl restart systemd-binfmt 2>/dev/null || true

mounts=()
cleanup() {
  for (( i=${#mounts[@]}-1; i>=0; i-- )); do umount -lf "${mounts[$i]}" 2>/dev/null || true; done
}
trap cleanup EXIT

# ---------------------------------------------------------------- shared files
ASSETS="$WORK/assets"
mkdir -p "$ASSETS/whisper" "$ASSETS/voice"
fetch() { [ -s "$2" ] || curl -fL --retry 3 -o "$2" "$1"; }
say "Downloading the ears (Whisper speech model), the voice (British Piper voice) and the dotted font"
HF=https://huggingface.co
for f in config.json model.bin tokenizer.json vocabulary.txt; do
  fetch "$HF/Systran/faster-whisper-base.en/resolve/main/$f" "$ASSETS/whisper/$f"
done
# Better ears: Whisper small.en (much better than base, small enough to keep the ISO one file). Stored once on the ISO, shared by both chip types.
mkdir -p "$ASSETS/whisper-small.en"
for f in config.json model.bin tokenizer.json vocabulary.txt; do
  fetch "$HF/Systran/faster-whisper-small.en/resolve/main/$f" "$ASSETS/whisper-small.en/$f"
done
fetch "$HF/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx" "$ASSETS/voice/voice.onnx"
fetch "$HF/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx.json" "$ASSETS/voice/voice.onnx.json"
fetch "https://github.com/google/fonts/raw/main/ofl/dotgothic16/DotGothic16-Regular.ttf" "$ASSETS/DotGothic16.ttf"

ISO="$WORK/iso"
rm -rf "$ISO"; mkdir -p "$ISO/boot/grub" "$ISO/EFI/BOOT" "$ISO/.disk"
touch "$ISO/.courage-os"
echo "Courage OS 1.0 ($(date +%F))" > "$ISO/.disk/info"

# ---------------------------------------------------------------- one system per chip type
build_arch() {
  local ARCH=$1 CPU MIRROR R="$WORK/root-$1"
  case $ARCH in
    amd64) CPU=x86_64; MIRROR=http://archive.ubuntu.com/ubuntu ;;
    arm64) CPU=arm64;  MIRROR=http://ports.ubuntu.com/ubuntu-ports ;;
  esac

  if [ ! -f "$R/.base-done" ]; then
    say "[$ARCH] Downloading a bare Ubuntu 24.04 (this takes a while)"
    rm -rf "$R"
    debootstrap --arch="$ARCH" --variant=minbase "$SUITE" "$R" "$MIRROR"
    touch "$R/.base-done"
  fi

  for m in dev dev/pts proc sys run; do mkdir -p "$R/$m"; mount --bind "/$m" "$R/$m"; mounts+=("$R/$m"); done
  cp /etc/resolv.conf "$R/etc/resolv.conf" 2>/dev/null || echo "nameserver 1.1.1.1" > "$R/etc/resolv.conf"

  # Courage OS files
  rm -rf "$R/opt/courage"; mkdir -p "$R/opt/courage/models"
  cp -r "$HERE/app" "$R/opt/courage/app"
  cp "$ASSETS/DotGothic16.ttf" "$R/opt/courage/app/courage/screen/"
  cp -r "$ASSETS/voice" "$R/opt/courage/models/"  # the ears live once on the ISO, not in each half
  cp "$HERE/app/update.sh" "$R/opt/courage/update.sh"
  chmod +x "$R/opt/courage/update.sh" "$R/opt/courage/app/"*.sh "$R/opt/courage/app/"*.py

  cat > "$R/etc/apt/sources.list" <<EOF
deb $MIRROR $SUITE main restricted universe multiverse
deb $MIRROR $SUITE-updates main restricted universe multiverse
deb $MIRROR $SUITE-security main restricted universe multiverse
EOF

  # Macs (UTM) only need the small virtual-machine kernel; PCs need the full one plus drivers.
  local EXTRA="linux-image-virtual"
  [ "$ARCH" = amd64 ] && EXTRA="linux-image-generic linux-firmware intel-microcode amd64-microcode"

  say "[$ARCH] Installing the system, sound, Wi-Fi, Bluetooth and the Courage OS app"
  cat > "$R/tmp/inside.sh" <<EOF
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8
printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d; chmod +x /usr/sbin/policy-rc.d
# keep the ISO small: no manuals, docs or other languages
cat > /etc/dpkg/dpkg.cfg.d/01-courage-slim <<'X'
path-exclude=/usr/share/doc/*
path-include=/usr/share/doc/*/copyright
path-exclude=/usr/share/man/*
path-exclude=/usr/share/info/*
path-exclude=/usr/share/locale/*
path-include=/usr/share/locale/en*
path-include=/usr/share/locale/locale.alias
X
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  casper initramfs-tools systemd-sysv udev dbus dbus-user-session sudo locales tzdata kbd \
  network-manager wpasupplicant iw wireless-regdb bluez \
  pipewire pipewire-pulse pipewire-alsa wireplumber libspa-0.2-bluetooth alsa-ucm-conf \
  cage libgtk-3-0 python3 python3-venv python3-pip python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 python3-evdev \
  libportaudio2 mpv espeak-ng sox brightnessctl gdisk fdisk util-linux e2fsprogs curl ca-certificates \
  fonts-dejavu-core mesa-utils libgl1-mesa-dri plymouth-theme-spinner $EXTRA
locale-gen en_GB.UTF-8 >/dev/null; update-locale LANG=en_GB.UTF-8
ln -sf /usr/share/zoneinfo/Europe/London /etc/localtime
echo courage-os > /etc/hostname

# Python brain/ears/voice
python3 -m venv /opt/courage/venv
/opt/courage/venv/bin/pip install -q --upgrade pip
/opt/courage/venv/bin/pip install -q --no-cache-dir aiohttp requests numpy sounddevice faster-whisper "piper-tts==1.3.0"

# Boot straight into the green screen
mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<'X'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin courage --noclear %I \$TERM
X
cat > /opt/courage/start.sh <<'X'
#!/bin/bash
# Starts the back end, then the full-screen green screen. Restarts them if they ever crash.
export PYTHONPATH=/opt/courage/app
grep -q courage_safe_gfx /proc/cmdline && export COURAGE_SAFE_GFX=1 WEBKIT_DISABLE_COMPOSITING_MODE=1
( while true; do /opt/courage/venv/bin/python -m courage.main >>"\$HOME/.courage-app.log" 2>&1; sleep 2; done ) &
while true; do cage -s -- /usr/bin/python3 /opt/courage/app/kiosk.py >>"\$HOME/.courage-screen.log" 2>&1; sleep 2; done
X
chmod +x /opt/courage/start.sh
mkdir -p /etc/skel/Music /etc/skel/Pictures
cat >> /etc/skel/.bash_profile <<'X'
if [ "\$(tty)" = /dev/tty1 ]; then exec /opt/courage/start.sh; fi
X

# Power button: Courage OS says goodbye and saves first
mkdir -p /etc/systemd/logind.conf.d
printf '[Login]\nHandlePowerKey=ignore\nHandlePowerKeyLongPress=poweroff\n' > /etc/systemd/logind.conf.d/courage.conf
cat > /etc/systemd/system/courage-power.service <<'X'
[Unit]
Description=Courage OS power button
[Service]
ExecStart=/usr/bin/python3 /opt/courage/app/power-button.py
Restart=always
[Install]
WantedBy=multi-user.target
X
cat > /etc/systemd/system/courage-storage.service <<'X'
[Unit]
Description=Courage OS storage (keeps your settings between boots)
After=local-fs.target
[Service]
Type=oneshot
ExecStart=/opt/courage/app/make-storage.sh
[Install]
WantedBy=multi-user.target
X
systemctl enable courage-power.service courage-storage.service NetworkManager bluetooth >/dev/null 2>&1 || true
systemctl --global enable pipewire.socket pipewire-pulse.socket wireplumber.service >/dev/null 2>&1 || true

cat > /etc/sudoers.d/courage <<'X'
courage ALL=(root) NOPASSWD: /usr/bin/nmcli, /usr/bin/brightnessctl, /usr/bin/systemctl poweroff, /opt/courage/update.sh
X
chmod 440 /etc/sudoers.d/courage

# Bootloader for this chip type
apt-get install -y -qq --no-install-recommends grub-common grub-efi-$ARCH-bin
cat > /tmp/embed.cfg <<'X'
search --no-floppy --set=root --file /.courage-os
set prefix=(\$root)/boot/grub
configfile (\$root)/boot/grub/grub.cfg
X
grub-mkstandalone -O $CPU-efi -o /tmp/grub.efi \
  --modules="part_gpt part_msdos iso9660 fat search search_fs_file normal linux configfile echo test all_video gfxterm" \
  "boot/grub/grub.cfg=/tmp/embed.cfg"

# Slim it so the whole ISO fits in one file under 2 GB:
# drop firmware for server cards, phones and NVIDIA (the screen still works without it),
# keep Wi-Fi, Bluetooth and Intel/AMD graphics.
cd /lib/firmware 2>/dev/null && rm -rf nvidia mellanox netronome qed liquidio cxgb4 mrvl qcom dpaa2 bnx2x \
  ql2* phanfw* myri10ge* cbfw* ctfw* intel/ipu intel/vpu amdtee mediatek/mt8* ti-keystone vsc imx meson rockchip s5p* cnm amlogic qat* hfi1_* dvb-* v4l-* isci cavium qlogic 2>/dev/null; cd /
find /opt/courage/venv -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find /opt/courage/venv -type d -name tests -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf /usr/share/doc/* /usr/src/* /var/cache/* 2>/dev/null || true
echo COMPRESS=xz > /etc/initramfs-tools/conf.d/courage-small
update-initramfs -c -k all >/dev/null 2>&1 || update-initramfs -u -k all
apt-get clean
rm -f /usr/sbin/policy-rc.d /etc/resolv.conf
rm -rf /var/lib/apt/lists/* /tmp/inside.sh
EOF
  chroot "$R" /bin/bash /tmp/inside.sh

  say "[$ARCH] Packing it into the ISO"
  mkdir -p "$ISO/casper/$CPU"
  cp "$(ls -1 "$R"/boot/vmlinuz-* | sort -V | tail -1)" "$ISO/casper/$CPU/vmlinuz"
  cp "$(ls -1 "$R"/boot/initrd.img-* | sort -V | tail -1)" "$ISO/casper/$CPU/initrd"
  case $ARCH in
    amd64) cp "$R/tmp/grub.efi" "$WORK/BOOTX64.EFI" ;;
    arm64) cp "$R/tmp/grub.efi" "$WORK/BOOTAA64.EFI" ;;
  esac
  rm -f "$R/tmp/grub.efi"

  for (( i=${#mounts[@]}-1; i>=0; i-- )); do umount -lf "${mounts[$i]}" || true; done
  mounts=()
  rm -f "$ISO/casper/$CPU/filesystem.squashfs"
  mksquashfs "$R" "$ISO/casper/$CPU/filesystem.squashfs" -comp xz -b 1M -Xdict-size 100% -noappend -quiet \
    -e .base-done boot
  ls -lh "$ISO/casper/$CPU/"
  du -sx --block-size=1 "$R" | cut -f1 > "$ISO/casper/$CPU/filesystem.size"
}

for a in $ARCHES; do build_arch "$a"; done

# ---------------------------------------------------------------- boot menu (shared)
mkdir -p "$ISO/models"; cp -r "$ASSETS/whisper-small.en" "$ISO/models/"
say "Making the boot menu"
cat > "$ISO/boot/grub/grub.cfg" <<'EOF'
set timeout=2
set default=0
menuentry "Courage OS" {
  linux /casper/$grub_cpu/vmlinuz boot=casper live-media-path=/casper/$grub_cpu username=courage hostname=courage-os persistent quiet splash fsck.mode=skip ---
  initrd /casper/$grub_cpu/initrd
}
menuentry "Courage OS (safe graphics)" {
  linux /casper/$grub_cpu/vmlinuz boot=casper live-media-path=/casper/$grub_cpu username=courage hostname=courage-os persistent nomodeset courage_safe_gfx ---
  initrd /casper/$grub_cpu/initrd
}
EOF

EFI_IMG="$WORK/efi.img"
rm -f "$EFI_IMG"
mkfs.msdos -C "$EFI_IMG" 32768 >/dev/null
mmd -i "$EFI_IMG" ::/EFI ::/EFI/BOOT
for f in BOOTX64.EFI BOOTAA64.EFI; do
  [ -f "$WORK/$f" ] && mcopy -i "$EFI_IMG" "$WORK/$f" ::/EFI/BOOT/ && cp "$WORK/$f" "$ISO/EFI/BOOT/"
done

say "Writing courage-os.iso"
xorriso -as mkisofs -iso-level 3 -full-iso9660-filenames -joliet -joliet-long -rational-rock \
  -volid COURAGE_OS -partition_offset 16 \
  -append_partition 2 0xef "$EFI_IMG" -appended_part_as_gpt -iso_mbr_part_type a2a0d0eb-e5b9-3344-87c0-68b6b72699c7 \
  -e '--interval:appended_partition_2:all::' -no-emul-boot \
  -output "$OUT" "$ISO"

MAX=$((9*1000*1000*1000))
SIZE=$(stat -c %s "$OUT")
[ "$SIZE" -lt "$MAX" ] || die "The ISO is $((SIZE/1000/1000)) MB, over the 9 GB limit."
say "Done!  $(du -h "$OUT" | cut -f1)  ->  $OUT"
echo "Next: put it on a USB stick (see GUIDE.md), boot it, then type your Gemini API key on the first screen."
