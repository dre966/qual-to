"""Login automation flow on top of the running AVD.

Flow:
  1. Launch the app
  2. Create an account (select one of the proxy images)
  3. Poll the real email inbox for the OTP
  4. Log in with the OTP
  5. Enter a one-time referral code

Referral codes are generated **lazily** (one at a time, on demand) — no mass
generation. Generated + used codes are tracked in a JSON state file so they
survive restarts and are never reused.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import string
import subprocess
import sys
import time
from pathlib import Path

from adb_tools import ADB_BIN, install_apk, screencap, shell, wait_for_device
from ocr import ocr_image
from config import SCREENSHOTS_DIR, OCR_LANG

log = logging.getLogger("qual-to.login_flow")

STATE_FILE = Path(os.environ.get("LOGIN_STATE_FILE", "login_state.json"))
REFERRAL_CODE_LENGTH = 8


# --------------------------------------------------------------------------- #
# ADB helpers
# --------------------------------------------------------------------------- #
def adb(*args: str, timeout: int | None = None) -> subprocess.CompletedProcess:
    cmd = [str(ADB_BIN), *args]
    log.debug("adb: %s", " ".join(cmd))
    return subprocess.run(cmd, timeout=timeout, check=True)


def tap(x: int, y: int) -> None:
    adb("shell", "input", "tap", str(x), str(y))

def text(s: str) -> None:
    # input text does not support spaces directly; replace with %s
    adb("shell", "input", "text", s.replace(" ", "%s"))

def keyevent(key: str | int) -> None:
    adb("shell", "input", "keyevent", str(key))


def screenshot_state(label: str) -> str:
    path = SCREENSHOTS_DIR / f"{label}.png"
    screencap(path)
    return ocr_image(path, lang=OCR_LANG)


# --------------------------------------------------------------------------- #
# Referral code manager (lazy, one-at-a-time)
# --------------------------------------------------------------------------- #
class ReferralCodeManager:
    def __init__(self, state_file: Path = STATE_FILE) -> None:
        self.state_file = Path(state_file)
        self.state = self._load()

    def _load(self) -> dict:
        if self.state_file.exists():
            return json.loads(self.state_file.read_text())
        return {"generated": [], "used": []}

    def _save(self) -> None:
        self.state_file.write_text(json.dumps(self.state, indent=2))

    def _generate(self) -> str:
        alphabet = string.ascii_uppercase + string.digits
        return "".join(__import__("secrets").choice(alphabet) for _ in range(REFERRAL_CODE_LENGTH))

    def get_code(self) -> str:
        """Return a fresh unused code, generating exactly one if needed."""
        for code in self.state["generated"]:
            if code not in self.state["used"]:
                return code

        # Lazy generation: create one new code only when needed.
        code = self._generate()
        while code in self.state["generated"]:
            code = self._generate()
        self.state["generated"].append(code)
        self._save()
        log.info("Generated referral code (lazy, n=1): %s", code)
        return code

    def mark_used(self, code: str) -> None:
        if code not in self.state["used"]:
            self.state["used"].append(code)
            self._save()
            log.info("Marked referral code used: %s", code)


# --------------------------------------------------------------------------- #
# Email OTP poller
# --------------------------------------------------------------------------- #
class EmailOTPoller:
    """Poll a real inbox for an OTP email. Override poll_once() for your provider."""

    def __init__(self, email: str, timeout_sec: int = 300, poll_interval: float = 5.0) -> None:
        self.email = email
        self.timeout_sec = timeout_sec
        self.poll_interval = poll_interval

    def poll_once(self) -> str | None:
        """Return the OTP string if found, else None. Implement per provider."""
        raise NotImplementedError

    def wait_for_otp(self) -> str:
        deadline = time.time() + self.timeout_sec
        while time.time() < deadline:
            otp = self.poll_once()
            if otp:
                log.info("OTP received for %s", self.email)
                return otp
            log.debug("No OTP yet, retrying in %ss...", self.poll_interval)
            time.sleep(self.poll_interval)
        raise TimeoutError(f"No OTP received for {self.email} within {self.timeout_sec}s")


class ImapOTPoller(EmailOTPoller):
    """IMAP poller for the OTP email. Configure IMAP_HOST, IMAP_USER, IMAP_PASS."""

    def __init__(
        self,
        email: str,
        imap_host: str,
        imap_user: str | None = None,
        imap_pass: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(email, **kwargs)
        self.imap_host = imap_host
        self.imap_user = imap_user or email
        self.imap_pass = imap_pass or os.environ.get("IMAP_PASS", "")

    def poll_once(self) -> str | None:
        try:
            import imaplib  # imported lazily so stdlib-only runs don't require it
        except ImportError:
            log.warning("imaplib not available; cannot poll email")
            return None

        try:
            mail = imaplib.IMAP4_SSL(self.imap_host)
            mail.login(self.imap_user, self.imap_pass)
            mail.select("inbox")
            typ, data = mail.search(None, 'UNSEEN SUBJECT "OTP"')
            if typ != "OK":
                return None

            for num in data[0].split():
                typ, msg_data = mail.fetch(num, "(RFC822)")
                if typ != "OK":
                    continue
                # naive OTP extraction: look for a 6-digit number
                import email as email_module
                import re
                msg = email_module.message_from_bytes(msg_data[0][1])
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode(errors="ignore")
                            break
                else:
                    body = msg.get_payload(decode=True).decode(errors="ignore")
                m = re.search(r"\b(\d{6})\b", body)
                if m:
                    mail.store(num, "+FLAGS", "\\Seen")
                    mail.logout()
                    return m.group(1)
            mail.logout()
        except Exception as exc:  # noqa: BLE001
            log.warning("IMAP poll error: %s", exc)
        return None


# --------------------------------------------------------------------------- #
# Login automation orchestrator
# --------------------------------------------------------------------------- #
class LoginAutomation:
    def __init__(
        self,
        apk: str | Path | None = None,
        package: str | None = None,
        referral_manager: ReferralCodeManager | None = None,
        otp_poller: EmailOTPoller | None = None,
    ) -> None:
        self.apk = apk
        self.package = package
        self.referral = referral_manager or ReferralCodeManager()
        self.otp_poller = otp_poller

    def install(self) -> None:
        if self.apk:
            install_apk(self.apk)

    def launch(self) -> None:
        if not self.package:
            raise ValueError("Package name required to launch")
        log.info("Launching %s", self.package)
        adb("shell", "monkey", "-p", self.package, "-c", "android.intent.category.LAUNCHER", "1")
        time.sleep(3)

    def create_account(self, proxy_image_coords: tuple[int, int]) -> None:
        """Tap through registration and select a proxy image at (x, y)."""
        log.info("Creating account with proxy image at %s", proxy_image_coords)
        # Override/tap coordinates to match your app's registration UI.
        tap(*proxy_image_coords)
        time.sleep(2)
        # Example: tap "Continue" / "Create" — adjust to your app.
        # tap(500, 800)

    def enter_otp(self, otp: str) -> None:
        log.info("Entering OTP: %s", otp)
        text(otp)
        time.sleep(1)
        keyevent("66")  # ENTER

    def enter_referral_code(self) -> str:
        code = self.referral.get_code()
        log.info("Entering referral code: %s", code)
        text(code)
        time.sleep(1)
        keyevent("66")  # ENTER
        return code

    def run(
        self,
        *,
        email: str,
        proxy_image_coords: tuple[int, int],
        otp_timeout_sec: int = 300,
    ) -> str:
        """Run the full login flow. Returns the referral code used."""
        wait_for_device()
        self.install()
        self.launch()
        self.create_account(proxy_image_coords)

        if not self.otp_poller:
            raise ValueError("OTP poller required")
        otp = self.otp_poller.wait_for_otp() if hasattr(self.otp_poller, "wait_for_otp") else self.otp_poller.wait_for_otp()

        self.enter_otp(otp)
        code = self.enter_referral_code()
        self.referral.mark_used(code)
        log.info("Login complete. Referral code used: %s", code)
        return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Automate app login: register, OTP, referral code.")
    parser.add_argument("--apk", help="Path to APK to install")
    parser.add_argument("--package", required=True, help="App package name (e.g. com.qualoo.app)")
    parser.add_argument("--email", required=True, help="Email to poll for OTP")
    parser.add_argument("--proxy-x", type=int, required=True, help="X coordinate of proxy image in UI")
    parser.add_argument("--proxy-y", type=int, required=True, help="Y coordinate of proxy image in UI")
    parser.add_argument("--imap-host", help="IMAP host for OTP polling")
    parser.add_argument("--imap-user", help="IMAP username (defaults to --email)")
    parser.add_argument("--state-file", default=str(STATE_FILE), help="Referral code state JSON file")
    parser.add_argument("--otp-timeout", type=int, default=300, help="Seconds to wait for OTP")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    referral = ReferralCodeManager(state_file=Path(args.state_file))
    poller: EmailOTPoller | None = None
    if args.imap_host:
        poller = ImapOTPoller(
            email=args.email,
            imap_host=args.imap_host,
            imap_user=args.imap_user,
            timeout_sec=args.otp_timeout,
        )

    bot = LoginAutomation(
        apk=args.apk,
        package=args.package,
        referral_manager=referral,
        otp_poller=poller,
    )

    bot.run(
        email=args.email,
        proxy_image_coords=(args.proxy_x, args.proxy_y),
        otp_timeout_sec=args.otp_timeout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
