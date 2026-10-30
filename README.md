# Android AVD + Tor + ADB OCR Automation

A headless Ubuntu server app that:
1. Creates a new Android Virtual Device (AVD)
2. Routes all emulator traffic through Tor
3. Installs an APK
4. Captures the screen via ADB and OCRs it with Tesseract

Designed to run on an **Ubuntu server** (headless, no GUI). Developed/maintained from `C:\qualoo` (Windows) but executed on the Ubuntu target.

## Project layout

```
avd_tor_ocr/
├── install_ubuntu.sh   # One-shot setup for the Ubuntu server
├── requirements.txt    # Python dependencies
├── config.py           # Paths and tunable constants
├── avd_manager.py      # AVD creation + emulator lifecycle
├── tor_proxy.py        # Tor install/start + torsocks wrapping
├── adb_tools.py        # ADB wait/install/screencap/shell
├── ocr.py              # Tesseract OCR wrapper
├── pipeline.py         # End-to-end orchestration
├── main.py             # CLI entry point
└── .gitignore
```

## Prerequisites on the Ubuntu server

Run `install_ubuntu.sh` as a user with `sudo`. It installs:
- `android-sdk` command-line tools (sdkmanager, avdmanager, emulator, adb)
- `tor` + `torsocks`
- `tesseract-ocr` + `python3-pip`
- OpenJDK (required by the Android tools)

## Quick start

```bash
# 1. Prepare the Ubuntu server (run once)
bash install_ubuntu.sh

# 2. Copy this project to the server and install Python deps
pip install -r requirements.txt

# 3. Export Android SDK location (adjust to your install path)
export ANDROID_SDK_ROOT=$HOME/android-sdk
export PATH=$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$ANDROID_SDK_ROOT/platform-tools:$PATH

# 4. Run the full pipeline
python main.py \
  --apk ./app.apk \
  --avd-name qualoo_avd \
  --api-level 30 \
  --ocr-text "Hello"
```

## How Tor routing works

- `tor` runs on the Ubuntu host as a SOCKS5 proxy (port `9050`) and DNS proxy (port `9053`).
- The emulator is launched wrapped in `torsocks`, so every TCP connection the emulator (and apps inside it) makes is forced through Tor.
- After boot, an HTTP proxy is also set inside the emulator so Android apps that read the system proxy use Tor.

> Note: UDP traffic and some app-specific proxy bypasses are not covered by this setup. For full-system transparent Tor routing you would need iptables/redsocks on the host.

## OCR

Screenshots are pulled with `adb exec-out screencap -p` (raw PNG, works headless) and passed to Tesseract via `pytesseract`. You can OCR the whole screen or a cropped region.
