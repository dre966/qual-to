"""End-to-end pipeline: create AVD, route through Tor, install APK, OCR screen."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from adb_tools import install_apk, screencap, wait_for_device
from avd_manager import AVDManager
from config import DEFAULT_API_LEVEL, DEFAULT_AVD_NAME, SCREENSHOTS_DIR
from ocr import ocr_image
from tor_proxy import start_tor, stop_tor

log = logging.getLogger("avd_tor_ocr.pipeline")


def run_pipeline(
    *,
    apk: str | Path | None,
    avd_name: str = DEFAULT_AVD_NAME,
    api_level: str = DEFAULT_API_LEVEL,
    use_tor: bool = True,
    wipe_data: bool = True,
    ocr: bool = True,
    screenshot_name: str = "screen.png",
) -> str:
    """Run the full automation pipeline.

    Returns the OCR'd text (empty string if OCR disabled).
    """
    tor_proc = None
    mgr = AVDManager(avd_name=avd_name, api_level=api_level)

    try:
        # 1. SDK + AVD
        mgr.ensure_sdk_tools()
        mgr.create_avd()

        # 2. Tor
        if use_tor:
            tor_proc = start_tor()

        # 3. Start emulator (via torsocks so all traffic goes through Tor)
        proc = mgr.boot_and_wait(use_torsocks=use_tor, headless=True, wipe_data=wipe_data, gpu="off")

        # 4. Install APK
        if apk:
            install_apk(apk)

        # 5. Capture + OCR
        ocr_text = ""
        if ocr:
            screenshot_path = SCREENSHOTS_DIR / screenshot_name
            screencap(screenshot_path)
            ocr_text = ocr_image(screenshot_path)
            log.info("OCR complete: %d chars", len(ocr_text))

        return ocr_text

    finally:
        # 6. Cleanup
        mgr.stop_emulator()
        if tor_proc is not None:
            stop_tor(tor_proc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create an AVD, route via Tor, install an APK, and OCR the screen."
    )
    parser.add_argument("--apk", help="Path to the APK to install")
    parser.add_argument("--avd-name", default=DEFAULT_AVD_NAME, help="AVD name")
    parser.add_argument("--api-level", default=DEFAULT_API_LEVEL, help="Android API level")
    parser.add_argument("--no-tor", action="store_true", help="Disable Tor routing")
    parser.add_argument("--no-wipe", action="store_true", help="Do not wipe data on boot")
    parser.add_argument("--no-ocr", action="store_true", help="Skip OCR step")
    parser.add_argument("--screenshot", default="screen.png", help="Screenshot filename")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    ocr_text = run_pipeline(
        apk=args.apk,
        avd_name=args.avd_name,
        api_level=args.api_level,
        use_tor=not args.no_tor,
        wipe_data=not args.no_wipe,
        ocr=not args.no_ocr,
        screenshot_name=args.screenshot,
    )

    if ocr_text:
        print("\n=== OCR RESULT ===")
        print(ocr_text)
        print("=== END ===\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
