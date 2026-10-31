#!/usr/bin/env bash
# avd.sh — spawn, route through Tor, and delete an Android AVD on a headless Ubuntu server
#
#   ./avd.sh create --tor     # fresh AVD, boots headless, routes through Tor
#   ./avd.sh create           # fresh AVD, no Tor
#   ./avd.sh delete           # kill emulator and delete the AVD
#   ./avd.sh start --tor      # start existing AVD with Tor
#   ./avd.sh start            # start existing AVD without Tor
#
# Requires: ANDROID_SDK_ROOT set, sdkmanager/avdmanager/emulator on PATH,
#           tor + torsocks installed, tesseract + python deps installed.

set -euo pipefail

###############################################################################
# Config
###############################################################################
AVD_NAME="${AVD_NAME:-qualoo_avd}"
API_LEVEL="${API_LEVEL:-30}"
SYSTEM_IMAGE="system-images;android-${API_LEVEL};google_apis;x86_64"
DEVICE="pixel_6"
SDCARD="512M"
GPU="off"
BOOT_TIMEOUT=300

export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$HOME/android-sdk}"
export ANDROID_HOME="$ANDROID_SDK_ROOT"
export PATH="$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$ANDROID_SDK_ROOT/platform-tools:$PATH"

ADB="$ANDROID_SDK_ROOT/platform-tools/adb"
EMULATOR="$ANDROID_SDK_ROOT/emulator/emulator"
AVDMANAGER="$ANDROID_SDK_ROOT/cmdline-tools/latest/bin/avdmanager"
SDKMANAGER="$ANDROID_SDK_ROOT/cmdline-tools/latest/bin/sdkmanager"

###############################################################################
# Helpers
###############################################################################
log() { echo "[avd.sh] $*"; }

ensure_sdk_components() {
  log "Ensuring SDK components are installed..."
  sdkmanager --list --verbose >/dev/null 2>&1 || true
  yes | sdkmanager --licenses >/dev/null 2>&1 || true
  sdkmanager "platform-tools" "cmdline-tools;latest" "emulator" "$SYSTEM_IMAGE" >/dev/null 2>&1 || true
}

avd_exists() {
  [ -f "$ANDROID_SDK_ROOT/.android/avd/${AVD_NAME}.avd" ]
}

create_avd() {
  if avd_exists; then
    log "AVD '$AVD_NAME' already exists."
    return 0
  fi
  log "Creating AVD '$AVD_NAME' (api=$API_LEVEL, device=$DEVICE)..."
  echo "no" | avdmanager create avd \
    -n "$AVD_NAME" \
    -k "$SYSTEM_IMAGE" \
    -d "$DEVICE" \
    -c "$SDCARD" \
    --force >/dev/null 2>&1 || true
  log "AVD '$AVD_NAME' created."
}

delete_avd() {
  log "Killing any running emulator..."
  "$ADB" emu kill >/dev/null 2>&1 || true
  pkill -f "emulator.*$AVD_NAME" >/dev/null 2>&1 || true
  sleep 2

  if avd_exists; then
    log "Deleting AVD '$AVD_NAME'..."
    echo "no" | avdmanager delete avd -n "$AVD_NAME" >/dev/null 2>&1 || true
    log "AVD '$AVD_NAME' deleted."
  else
    log "AVD '$AVD_NAME' does not exist."
  fi
}

wait_for_boot() {
  log "Waiting for device to boot..."
  "$ADB" wait-for-device >/dev/null 2>&1 || true

  local elapsed=0
  while [ $elapsed -lt $BOOT_TIMEOUT ]; do
    local boot
    boot=$("$ADB" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' || echo "")
    if [ "$boot" = "1" ]; then
      log "Device booted."
      return 0
    fi
    sleep 5
    elapsed=$((elapsed + 5))
  done
  log "WARNING: Timed out waiting for boot."
  return 1
}

start_emulator() {
  local use_tor="${1:-false}"

  # Make sure an old emulator isn't still running
  "$ADB" emu kill >/dev/null 2>&1 || true
  pkill -f "emulator.*$AVD_NAME" >/dev/null 2>&1 || true
  sleep 2

  create_avd

  local emulator_args=( -avd "$AVD_NAME" -no-window -no-audio -no-boot-anim -gpu "$GPU" )
  if [ "$use_tor" = "true" ]; then
    log "Starting emulator '$AVD_NAME' via torsocks (Tor routing)..."
    torsocks "$EMULATOR" "${emulator_args[@]}" >/dev/null 2>&1 &
  else
    log "Starting emulator '$AVD_NAME' (no Tor)..."
    "$EMULATOR" "${emulator_args[@]}" >/dev/null 2>&1 &
  fi

  wait_for_boot
}

###############################################################################
# CLI
###############################################################################
cmd="${1:-}"
shift || true

case "$cmd" in
  create)
    ensure_sdk_components
    if [ "${1:-}" = "--tor" ]; then
      start_emulator true
    else
      start_emulator false
    fi
    ;;
  start)
    if [ "${1:-}" = "--tor" ]; then
      start_emulator true
    else
      start_emulator false
    fi
    ;;
  delete)
    delete_avd
    ;;
  devices)
    "$ADB" devices
    ;;
  boot)
    wait_for_boot
    ;;
  *)
    echo "Usage: $0 {create|start} [--tor] | delete | devices | boot"
    echo "  create --tor   fresh AVD, headless, routes through Tor"
    echo "  create         fresh AVD, headless, no Tor"
    echo "  start --tor    start existing AVD with Tor"
    echo "  start          start existing AVD, no Tor"
    echo "  delete         kill emulator and delete the AVD"
    echo "  devices        list attached adb devices"
    echo "  boot           wait for already-running emulator to finish booting"
    exit 1
    ;;
esac
