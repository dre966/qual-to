"""Install and manage Tor on the Ubuntu host.

Starts `tor` as a SOCKS5 proxy (9050) and DNS proxy (9053) so that the
emulator (wrapped in torsocks) routes all its traffic through Tor.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from pathlib import Path

from config import TOR_DNS_PORT, TOR_SOCKS_ADDR, TOR_SOCKS_PORT

log = logging.getLogger("avd_tor_ocr.tor_proxy")


def is_tor_running() -> bool:
    """Return True if something is listening on the Tor SOCKS port."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", TOR_SOCKS_PORT)) == 0


def start_tor() -> subprocess.Popen:
    """Start the Tor daemon in the foreground (captured as a subprocess).

    Returns the Popen so the caller can terminate it later.
    """
    if is_tor_running():
        log.info("Tor already running on %s", TOR_SOCKS_ADDR)
        return None  # type: ignore[return-value]

    log.info("Starting Tor (SOCKS5 %s, DNS %d)...", TOR_SOCKS_ADDR, TOR_DNS_PORT)

    # torrc overrides so we run as a non-daemon foreground process we can
    # control from Python. DNSPort lets apps resolve through Tor too.
    torrc = "\n".join(
        [
            f"SocksPort {TOR_SOCKS_PORT}",
            f"DNSPort {TOR_DNS_PORT}",
            "Log notice stdout",
            "PidFile /tmp/avd_tor_ocr/tor.pid",
            "DataDirectory /tmp/avd_tor_ocr/tor_data",
        ]
    )
    torrc_dir = Path("/tmp/avd_tor_ocr")
    torrc_dir.mkdir(parents=True, exist_ok=True)
    torrc_path = torrc_dir / "torrc"
    torrc_path.write_text(torrc)

    proc = subprocess.Popen(
        ["tor", "-f", str(torrc_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # Wait for the SOCKS port to become available.
    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("Tor process exited early during startup")
        if is_tor_running():
            log.info("Tor is ready on %s", TOR_SOCKS_ADDR)
            return proc
        time.sleep(0.5)

    raise RuntimeError("Tor did not become ready on port %d" % TOR_SOCKS_PORT)


def stop_tor(proc: subprocess.Popen | None) -> None:
    """Stop a Tor process started by :func:`start_tor`."""
    if proc is None:
        return
    log.info("Stopping Tor...")
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def torsocks_env() -> dict[str, str]:
    """Return an environment dict that forces torsocks to use our Tor SOCKS proxy."""
    env = os.environ.copy()
    env["TORSOCKS_CONF"] = "/tmp/avd_tor_ocr/torsocks.conf"
    # Point torsocks at our Tor SOCKS port.
    Path("/tmp/avd_tor_ocr").mkdir(parents=True, exist_ok=True)
    Path("/tmp/avd_tor_ocr/torsocks.conf").write_text(
        f"TorAddress 127.0.0.1\nTorPort {TOR_SOCKS_PORT}\n"
    )
    return env
