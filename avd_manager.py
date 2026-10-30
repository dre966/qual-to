"""AVD creation and emulator lifecycle management."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from pathlib import Path

from config import (
    ADB_BIN,
    ANDROID_SDK_ROOT,
    AVDMANAGER_BIN,
    DEFAULT_ABI,
    DEFAULT_API_LEVEL,
    DEFAULT_AVD_NAME,
    DEFAULT_DEVICE,
    DEFAULT_SDCARD,
    DEFAULT_SYSTEM_IMAGE,
    DEFAULT_TAG,
    EMULATOR_BIN,
    EMULATOR_BOOT_TIMEOUT_SEC,
    EMULATOR_POLL_INTERVAL_SEC,
    PLATFORM_TOOLS,
    SDKMANAGER_BIN,
)

log = logging.getLogger("avd_tor_ocr.avd_manager")


class AVDManager:
    def __init__(
        self,
        sdk_root: Path | None = None,
        avd_name: str | None = None,
        api_level: str | None = None,
    ) -> None:
        self.sdk_root = Path(sdk_root or ANDROID_SDK_ROOT)
        self.avd_name = avd_name or os.environ.get("AVD_NAME", DEFAULT_AVD_NAME)
        self.api_level = api_level or DEFAULT_API_LEVEL
        self.system_image = f"system-images;android-{self.api_level};{DEFAULT_TAG};x86_64"
        self.emulator_proc: subprocess.Popen | None = None

    # ------------------------------------------------------------------ #
    # SDK setup
    # ------------------------------------------------------------------ #
    def ensure_sdk_tools(self) -> None:
        """Install command-line tools, platform tools, and the system image."""
        self.sdk_root.mkdir(parents=True, exist_ok=True)

        required = [
            "platform-tools",
            "cmdline-tools;latest",
            self.system_image,
            "emulator",
        ]
        for component in required:
            log.info("Installing SDK component: %s", component)
            _run_sdkmanager(["--install", component])

        # Accept all SDK licenses (non-interactive).
        log.info("Accepting SDK licenses...")
        _run_sdkmanager(["--licenses"], input_b"y\n")

    # ------------------------------------------------------------------ #
    # AVD creation
    # ------------------------------------------------------------------ #
    def avd_exists(self) -> bool:
        avd_ini = self.sdk_root / ".android" / "avd" / f"{self.avd_name}.avd"
        return avd_ini.exists()

    def create_avd(self, force: bool = False) -> None:
        if self.avd_exists() and not force:
            log.info("AVD '%s' already exists, skipping creation", self.avd_name)
            return

        log.info("Creating AVD '%s' (api=%s, device=%s)...", self.avd_name, self.api_level, DEFAULT_DEVICE)
        cmd = [
            str(AVDMANAGER_BIN),
            "create",
            "avd",
            "-n",
            self.avd_name,
            "-k",
            self.system_image,
            "-d",
            DEFAULT_DEVICE,
            "-c",
            DEFAULT_SDCARD,
            "--force",
        ]
        _run_avdmanager(cmd)
        log.info("AVD '%s' created", self.avd_name)

    def delete_avd(self) -> None:
        if not self.avd_exists():
            log.info("AVD '%s' does not exist, nothing to delete", self.avd_name)
            return
        log.info("Deleting AVD '%s'...", self.avd_name)
        _run_avdmanager(["delete", "avd", "-n", self.avd_name])

    # ------------------------------------------------------------------ #
    # Emulator start / stop
    # ------------------------------------------------------------------ #
    def start_emulator(
        self,
        *,
        headless: bool = True,
        wipe_data: bool = False,
        no_audio: bool = True,
        gpu: str = "off",
        extra_args: list[str] | None = None,
    ) -> subprocess.Popen:
        """Launch the emulator and return the Popen handle.

        On a headless Ubuntu server use headless=True (-no-window -no-audio
        -gpu off) so no display is required.
        """
        if self.emulator_proc is not None and self.emulator_proc.poll() is None:
            raise RuntimeError("Emulator is already running")

        cmd = [str(EMULATOR_BIN), "-avd", self.avd_name]

        if headless:
            cmd += ["-no-window", "-no-audio", "-no-boot-anim"]
        if no_audio:
            cmd.append("-no-audio")
        cmd += ["-gpu", gpu]
        if wipe_data:
            cmd.append("-wipe-data")
        if extra_args:
            cmd.extend(extra_args)

        log.info("Starting emulator: %s", " ".join(cmd))
        env = os.environ.copy()
        env["ANDROID_SDK_ROOT"] = str(self.sdk_root)
        env["ANDROID_HOME"] = str(self.sdk_root)
        env["PATH"] = f"{PLATFORM_TOOLS}:{env.get('PATH', '')}"
        # Headless systems need an offscreen Qt platform.
        env.setdefault("QT_QPA_PLATFORM", "offscreen")

        self.emulator_proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        log.info("Emulator launched (pid %d)", self.emulator_proc.pid)
        return self.emulator_proc

    def start_emulator_via_torsocks(self, **kwargs) -> subprocess.Popen:
        """Launch the emulator wrapped in torsocks so all traffic goes through Tor.

        Requires the `torsocks` system package to be installed on the host.
        """
        cmd = ["torsocks", str(EMULATOR_BIN), "-avd", self.avd_name]
        if kwargs.get("headless", True):
            cmd += ["-no-window", "-no-audio", "-no-boot-anim"]
        cmd += ["-gpu", kwargs.get("gpu", "off")]
        if kwargs.get("wipe_data", False):
            cmd.append("-wipe-data")

        log.info("Starting emulator via torsocks: %s", " ".join(cmd))
        env = os.environ.copy()
        env["ANDROID_SDK_ROOT"] = str(self.sdk_root)
        env["ANDROID_HOME"] = str(self.sdk_root)
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["TORSOCKS_CONF"] = "/tmp/avd_tor_ocr/torsocks.conf"

        self.emulator_proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return self.emulator_proc

    def stop_emulator(self, timeout_sec: int = 60) -> None:
        """Gracefully shut down the emulator via adb, then kill the process."""
        if self.emulator_proc is None:
            return
        log.info("Stopping emulator...")
        try:
            subprocess.run([str(ADB_BIN), "emu", "kill"], timeout=15, check=False)
        except FileNotFoundError:
            pass
        try:
            self.emulator_proc.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            self.emulator_proc.kill()
        self.emulator_proc = None
        log.info("Emulator stopped")

    # ------------------------------------------------------------------ #
    # Convenience: full start sequence
    # ------------------------------------------------------------------ #
    def boot_and_wait(self, use_torsocks: bool = True, **emulator_kwargs) -> subprocess.Popen:
        """Start the emulator (optionally via torsocks) and wait until booted."""
        if use_torsocks:
            proc = self.start_emulator_via_torsocks(**emulator_kwargs)
        else:
            proc = self.start_emulator(**emulator_kwargs)

        from adb_tools import wait_for_device

        wait_for_device(timeout_sec=EMULATOR_BOOT_TIMEOUT_SEC)
        return proc


def _run_sdkmanager(args: list[str], input_b: bytes | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["ANDROID_SDK_ROOT"] = str(ANDROID_SDK_ROOT)
    env["ANDROID_HOME"] = str(ANDROID_SDK_ROOT)
    env["PATH"] = f"{PLATFORM_TOOLS}:{CMDLINE_TOOLS_BIN if False else ANDROID_SDK_ROOT / 'cmdline-tools' / 'latest' / 'bin'}:{env.get('PATH', '')}"
    cmd = [str(SDKMANAGER_BIN), *args]
    log.debug("Running sdkmanager: %s", " ".join(cmd))
    return subprocess.run(cmd, env=env, input=input_b, check=True)


def _run_avdmanager(args: list[str]) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["ANDROID_SDK_ROOT"] = str(ANDROID_SDK_ROOT)
    env["ANDROID_HOME"] = str(ANDROID_SDK_ROOT)
    cmd = [str(AVDMANAGER_BIN), *args]
    log.debug("Running avdmanager: %s", " ".join(cmd))
    return subprocess.run(cmd, env=env, check=True)


DEFAULT_AVD_NAME = os.environ.get("AVD_NAME", "qualoo_avd")
