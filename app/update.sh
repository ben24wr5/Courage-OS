#!/bin/bash
# Downloads a newer Courage OS app (a .tar.gz of the "courage" folder) from the update address and installs it.
set -euo pipefail
URL="$1"
TMP=$(mktemp -d)
curl -fsSL "$URL" -o "$TMP/app.tar.gz"
tar -xzf "$TMP/app.tar.gz" -C "$TMP"
[ -f "$TMP/courage/main.py" ] || { echo "not a Courage OS update"; exit 1; }
rm -rf /opt/courage/app/courage.old
mv /opt/courage/app/courage /opt/courage/app/courage.old
mv "$TMP/courage" /opt/courage/app/courage
echo updated
