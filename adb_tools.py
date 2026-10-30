"""ADB wrapper: wait for device, install APK, capture screenshots, run shell."""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

from config import (
    ADB_BIN,
    ADB_CONNECT_TIMEOUT_SEC,
    ADB_INSTALL_TIMEOUT_SEC,
    ADB_SCREENCAP_TIMEOUT_SEC,
)

log = logging.getLogger("avd_tor_ocr.adb_tools")


def _run(cmd: list[str], timeout: int | None = None, **kwargs) -> subprocess.CompletedProcess:
    log.debug("Running: %s", " ".join(cmd))
    return subprocess.run(cmd, timeout=timeout, check=True, **kwargs)


def adb(*args: str, timeout: int | None = None, **kwargs) -> subprocess.CompletedProcess:
    """Run an adb command."""
    return _run([str(ADB_BIN), *args], timeout=timeout, **kwargs)


def wait_for_device(timeout_sec: int = ADB_CONNECT_TIMEOUT_SEC) -> None:
    """Block until the emulator/device is online and fully booted."""
    log.info("Waiting for ADB device (timeout %ds)...", timeout_sec)
    _run([str(ADB_BIN), "wait-for-device"], timeout=timeout_sec)

    # Wait until Android has finished booting.
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            res = adb("shell", "getprop", "sys.boot_completed", timeout=10)
            if res.stdout.strip() == "1":
                log.info("Device booted (sys.boot_completed=1)")
                return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
        time.sleep(3)
    raise TimeoutError("Device did not finish booting within timeout")


def install_apk(apk_path: str | Path, timeout_sec: int = ADB_INSTALL_TIMEOUT_SEC) -> None:
    """Install an APK on the connected device."""
    apk_path = Path(apk_path)
    if not apk_path.exists():
        raise FileNotFoundError(f"APK not found: {apk_path}")
    log.info("Installing APK: %s", apk_path)
    adb("install", "-r", str(apk_path), timeout=timeout_sec)
    log.info("APK installed successfully")


def screencap(output_path: str | Path, timeout_sec: int = ADB_SCREENCAP_TIMEOUT_SEC) -> Path:
    """Capture the device screen to a local PNG file.

    Uses `adb exec-out screencap -p` to stream raw PNG bytes (works headless).
    """
    output_path = Path(output_path)
    log.info("Capturing screenshot to %s", output_path)
    res = adb("exec-out", "screencap", "-p", timeout=timeout_sec)
    output_path.write_bytes(res.stdout)
    log.info("Screenshot saved (%d bytes)", output_path.stat().st_size)
    return output_path


def shell(*args: str, timeout: int | None = None) -> subprocess.CompletedProcess:
    """Run a shell command on the device."""
    return adb("shell", *args, timeout=timeout)
