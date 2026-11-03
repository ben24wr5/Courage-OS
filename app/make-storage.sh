#!/bin/bash
# Gives Courage OS somewhere to keep your API key, notes, music and settings between boots.
# Runs once at start-up as root. It only ever touches:
#   1. empty space at the END of the Courage OS USB stick itself, or
#   2. a completely blank virtual disk (vdX) in UTM, with no partitions and nothing on it.
# It never touches a disk that has anything on it.
set -u
LOG=/var/log/courage-storage.log
exec >>"$LOG" 2>&1
echo "=== $(date)"

if blkid -L casper-rw >/dev/null 2>&1; then echo "storage already exists"; exit 0; fi

# 1) UTM: a blank virtio disk
for d in /dev/vd?; do
  [ -b "$d" ] || continue
  if [ -z "$(lsblk -no NAME "$d" | tail -n +2)" ] && [ -z "$(blkid -p "$d" 2>/dev/null)" ]; then
    echo "using blank virtual disk $d"
    mkfs.ext4 -F -L casper-rw "$d" && { touch /run/courage-storage-made; systemctl reboot; }
    exit 0
  fi
done

# 2) The boot USB: add a partition in the free space after Courage OS
SRC=$(findmnt -no SOURCE /cdrom 2>/dev/null)
[ -n "$SRC" ] || { echo "no boot medium found"; exit 0; }
DISK="/dev/$(lsblk -no PKNAME "$SRC" 2>/dev/null | head -1)"
[ "$DISK" = "/dev/" ] && DISK="$SRC"
case "$DISK" in /dev/sr*|/dev/loop*) echo "boot medium is a CD/loop, nothing to do"; exit 0;; esac
[ "$(lsblk -dno RM "$DISK")" = "1" ] || [ "$(lsblk -dno TRAN "$DISK")" = "usb" ] || { echo "$DISK is not a USB stick, leaving it alone"; exit 0; }

SIZE=$(blockdev --getsize64 "$DISK")
PART_END=$(( ($(partx -g -o END "$DISK" 2>/dev/null | sort -n | tail -1) + 1) * 512 ))
ISO_SIZE=$(isosize "$DISK" 2>/dev/null || echo 0)
ISO_END=$(( PART_END > ISO_SIZE ? PART_END : ISO_SIZE ))
FREE=$(( SIZE - ISO_END ))
echo "disk $DISK size $SIZE iso_end $ISO_END free $FREE"
[ "$FREE" -gt $((2*1024*1024*1024)) ] || { echo "not enough free space"; exit 0; }

sgdisk -e "$DISK" || exit 0
sgdisk -n 0:0:0 -t 0:8300 -c 0:casper-rw "$DISK" || exit 0
partx -a "$DISK" 2>/dev/null; partx -u "$DISK" 2>/dev/null; sleep 2
NEW=$(lsblk -lnpo NAME,PARTLABEL "$DISK" | awk '$2=="casper-rw"{print $1}' | tail -1)
[ -b "$NEW" ] || { echo "new partition not visible yet, will finish after reboot"; systemctl reboot; exit 0; }
mkfs.ext4 -F -L casper-rw "$NEW" && { touch /run/courage-storage-made; systemctl reboot; }
