#!/bin/bash
# ============================================================================
#  COURAGE OS · build the ISO from the macOS Terminal
#  Needs Docker Desktop (free): https://www.docker.com/products/docker-desktop/
#  Run:   ./build-mac.sh
#  Result: courage-os.iso in this folder
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker Desktop isn't installed."
  echo "Get it free from https://www.docker.com/products/docker-desktop/ , open it once, then run ./build-mac.sh again."
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Starting Docker Desktop..."
  open -a Docker || true
  for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 3; done
  docker info >/dev/null 2>&1 || { echo "Docker didn't start. Open the Docker app, wait for it, and try again."; exit 1; }
fi

echo "Building Courage OS. This takes 1-2 hours the first time. Leave the Mac plugged in and awake."
caffeinate -dims &
CAF=$!
trap 'kill $CAF 2>/dev/null || true' EXIT

# The Linux build runs inside Docker's built-in Linux. Downloads are kept in a Docker volume,
# so a second build is much faster. Only the finished ISO is copied back to this folder.
docker run --rm --privileged \
  -v "$PWD":/src:ro \
  -v courage-os-build:/build \
  -v "$PWD":/out \
  ubuntu:24.04 bash -c '
    set -e
    rm -rf /build/src && cp -r /src /build/src
    cd /build/src
    WORK=/build/work ./build.sh
    cp /build/src/courage-os.iso /out/courage-os.iso
  '

echo
echo "Done! courage-os.iso is in: $PWD"
echo "Next: flash it to your USB with balenaEtcher, or open it in UTM."
