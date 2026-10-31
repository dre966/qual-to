# qual-to

Automate an Android Virtual Device on a headless Ubuntu server:
1. Create/start an AVD (via your `avd.sh`)
2. Route emulator traffic through Tor
3. Install an APK
4. Screenshot via ADB and OCR the screen with Tesseract

Run on the Ubuntu server; developed from `C:\qualoo` (Windows).

## Files

| File | Purpose |
|------|---------|
| `install_ubuntu.sh` | One-shot server setup (SDK, Tor, Tesseract, Python deps) |
| `qualoo_install_ocr.py` | Install APK on a running AVD, launch it, screenshot + OCR-log states |
| `main.py` / `pipeline.py` | Full create-AVD → Tor → install → OCR pipeline |
| `avd_manager.py`, `tor_proxy.py`, `adb_tools.py`, `ocr.py`, `config.py` | Core modules |
| `requirements.txt` | Python dependencies |

## Server setup (run once)

```bash
git clone https://github.com/dre966/qual-to.git
cd qual-to
bash install_ubuntu.sh
```

Add to your shell (`~/.bashrc`):

```bash
export ANDROID_SDK_ROOT=$HOME/android-sdk
export PATH=$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$ANDROID_SDK_ROOT/platform-tools:$PATH
```

## Usage

Spawn the AVD with your existing script:

```bash
chmod +x avd.sh
./avd.sh create --tor   # fresh AVD, headless, traffic through Tor
```

Install `qualoo.apk`, launch it, and OCR-log screen states:

```bash
python3 qualoo_install_ocr.py --apk ~/qualoo.apk --states 10 --interval 5
```

If you know the package/activity:

```bash
python3 qualoo_install_ocr.py --apk ~/qualoo.apk \
  --package com.qualoo.app --activity .MainActivity --states 10 --interval 5
```

Each state saves `screenshots/state_001.png` and prints the OCR'd text. Screenshots are captured with `adb exec-out screencap -p` (works headless) and OCR'd via Tesseract/pytesseract.

## How Tor routing works

`tor` runs on the Ubuntu host as a SOCKS5 proxy (port `9050`). The emulator is launched wrapped in `torsocks`, forcing its TCP traffic through Tor. UDP and app-specific proxy bypasses are not covered.
