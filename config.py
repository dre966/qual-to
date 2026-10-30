"""Configuration constants for the AVD + Tor + OCR pipeline."""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Android SDK
# ---------------------------------------------------------------------------
ANDROID_SDK_ROOT = Path(os.environ.get("ANDROID_SDK_ROOT", os.path.expanduser("~/android-sdk")))
CMDLINE_TOOLS_BIN = ANDROID_SDK_ROOT / "cmdline-tools" / "latest" / "bin"
PLATFORM_TOOLS = ANDROID_SDK_ROOT / "platform-tools"
EMULATOR_BIN = ANDROID_SDK_ROOT / "emulator" / "emulator"
AVDMANAGER_BIN = CMDLINE_TOOLS_BIN / "avdmanager"
SDKMANAGER_BIN = CMDLINE_TOOLS_BIN / "sdkmanager"
ADB_BIN = PLATFORM_TOOLS / "adb"

DEFAULT_API_LEVEL = "30"
DEFAULT_SYSTEM_IMAGE = f"system-images;android-{DEFAULT_API_LEVEL};google_apis;x86_64"
DEFAULT_TAG = "google_apis"
DEFAULT_ABI = "google_apis/x86_64"

# ---------------------------------------------------------------------------
# AVD / emulator
# ---------------------------------------------------------------------------
DEFAULT_AVD_NAME = "qualoo_avd"
DEFAULT_DEVICE = "pixel_6"          # hardware profile passed to avdmanager -d
DEFAULT_SDCARD = "512M"
EMULATOR_BOOT_TIMEOUT_SEC = 300
EMULATOR_POLL_INTERVAL_SEC = 5

# ---------------------------------------------------------------------------
# Tor
# ---------------------------------------------------------------------------
TOR_SOCKS_PORT = 9050
TOR_DNS_PORT = 9053
TOR_SOCKS_ADDR = f"127.0.0.1:{TOR_SOCKS_PORT}"

# ---------------------------------------------------------------------------
# ADB
# ---------------------------------------------------------------------------
ADB_CONNECT_TIMEOUT_SEC = 120
ADB_INSTALL_TIMEOUT_SEC = 300
ADB_SCREENCAP_TIMEOUT_SEC = 60

# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------
TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "tesseract")
OCR_LANG = "eng"

# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
SCREENSHOTS_DIR = PROJECT_ROOT / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)
