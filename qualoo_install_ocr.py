"""qualoo_install_ocr.py

Extension for an already-running AVD (spawned by your ./avd.sh).

Workflow:
  1. wait for the emulator/device via adb
  2. install qualoo.apk (also tolerates the "qualoo,.apk" comma variant)
  3. launch the app (monkey launcher, or explicit package/activity)
  4. loop: adb screenshot -> save PNG -> OCR -> log the state

Run on the Ubuntu server where the emulator is running:

    python3 qualoo_install_ocr.py \
        --apk ~/qualoo.apk \
        --package com.qualoo.app \
        --states 10 \
        --interval 5

If you don't know the package name, omit --package and the script will
try to auto-detect it after install (matches "qualoo" in pm list packages).
"""

from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
import time
from pathlib import Path

from adb_tools import ADB_BIN, install_apk, screencap, shell, wait_for_device
from ocr import ocr_image
from config import SCREENSHOTS_DIR, OCR_LANG

log = logging.getLogger("qualoo_install_ocr")

APK_CANDIDATES = ["qualoo.apk", "qualoo,.apk"]


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    log.debug("Running: %s", " ".join(map(str, cmd)))
    return subprocess.run(cmd, check=True, **kwargs)


def adb(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return _run([str(ADB_BIN), *args], **kwargs)


def find_apk(apk: str | None) -> Path:
    """Resolve the APK path, tolerating the 'qualoo,.apk' comma variant."""
    if apk:
        p = Path(apk)
        if p.exists():
            return p
        raise FileNotFoundError(f"APK not found: {apk}")

    # No explicit path: look for qualoo.apk (and the comma variant) in cwd.
    for name in APK_CANDIDATES:
        p = Path(name)
        if p.exists():
            log.info("Auto-detected APK: %s", p)
            return p
    raise FileNotFoundError(
        "No APK specified and none of %s found in current directory" % APK_CANDIDATES
    )


def install(apk_path: Path) -> None:
    log.info("Installing APK: %s", apk_path)
    install_apk(apk_path)


def detect_package() -> str | None:
    """Try to auto-detect a qualoo-related package after install."""
    try:
        res = shell("pm", "list", "packages")
    except subprocess.CalledProcessError as exc:
        log.warning("Could not list packages: %s", exc)
        return None

    for line in res.stdout.splitlines():
        line = line.strip()
        m = re.search(r"package:(.+)", line)
        if not m:
            continue
        pkg = m.group(1)
        if "qualoo" in pkg.lower():
            log.info("Auto-detected package: %s", pkg)
            return pkg
    return None


def launch_app(package: str | None, activity: str | None) -> None:
    """Launch the app. Prefers explicit package/activity, falls back to monkey."""
    if package and activity:
        log.info("Launching %s/%s via am start", package, activity)
        adb("shell", "am", "start", "-n", f"{package}/{activity}")
        return

    if package:
        log.info("Launching package %s via monkey launcher", package)
        adb("shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")
        return

    log.warning("No package known; skipping app launch")


def screenshot_and_ocr(index: int) -> str:
    """Capture one screenshot, save it, OCR it, and return the text."""
    png_name = f"state_{index:03d}.png"
    png_path = SCREENSHOTS_DIR / png_name
    screencap(png_path)
    text = ocr_image(png_path, lang=OCR_LANG)
    log.info("State %d OCR (%d chars): %s", index, len(text), text.strip().replace("\n", " | ")[:200])
    return text


def run(
    *,
    apk: str | None,
    package: str | None,
    activity: str | None,
    states: int,
    interval: float,
    auto_launch: bool,
) -> None:
    wait_for_device()

    apk_path = find_apk(apk)
    install(apk_path)

    # Give the system a moment to register the new package.
    time.sleep(2)

    if auto_launch and package is None:
        package = detect_package()

    if auto_launch:
        launch_app(package, activity)

    # Let the app settle before the first screenshot.
    time.sleep(3)

    for i in range(states):
        log.info("=== State %d/%d ===", i + 1, states)
        screenshot_and_ocr(i + 1)
        if i < states - 1:
            time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install qualoo.apk on a running AVD, launch it, and OCR-log screen states."
    )
    parser.add_argument("--apk", help="Path to qualoo.apk (default: auto-detect qualoo.apk / qualoo,.apk)")
    parser.add_argument("--package", help="App package name (e.g. com.qualoo.app). Auto-detected if omitted.")
    parser.add_argument("--activity", help="Launcher activity (e.g. .MainActivity). Used with --package.")
    parser.add_argument("--states", type=int, default=10, help="Number of screenshot+OCR states to log")
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds between states")
    parser.add_argument("--no-launch", action="store_true", help="Install but do not launch the app")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    run(
        apk=args.apk,
        package=args.package,
        activity=args.activity,
        states=args.states,
        interval=args.interval,
        auto_launch=not args.no_launch,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
