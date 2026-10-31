# qual-to

Install an APK on a running Android AVD, route traffic through Tor, and OCR-log screen states via ADB. Runs on a headless Ubuntu server; developed from `C:\qualoo` (Windows).

## Your server workflow

1. **Spawn the AVD** with your existing script (not in this repo):

```bash
chmod +x avd.sh
./avd.sh create --tor   # fresh AVD, headless, traffic through Tor
```

2. **Install `qualoo.apk`, launch it, and OCR-log screen states:**

```bash
python3 qualoo_install_ocr.py --apk ~/qualoo.apk --states 10 --interval 5
```

If you know the package/activity, launch it directly:

```bash
python3 qualoo_install_ocr.py --apk ~/qualoo.apk \
  --package com.qualoo.app --activity .MainActivity --states 10 --interval 5
```

Each state saves `screenshots/state_001.png` and prints the OCR'd text. Captured with `adb exec-out screencap -p` (headless-safe), OCR'd via Tesseract/pytesseract.

## One-shot server setup (run once)

```bash
git clone https://github.com/dre966/qual-to.git
cd qual-to
bash install_ubuntu.sh
```

Add to `~/.bashrc`:

```bash
export ANDROID_SDK_ROOT=$HOME/android-sdk
export PATH=$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$ANDROID_SDK_ROOT/platform-tools:$PATH
```

## Files

| File | Purpose |
|------|---------|
| `qualoo_install_ocr.py` | Install APK on a running AVD, launch app, screenshot + OCR-log states |
| `install_ubuntu.sh` | One-shot Ubuntu server setup (SDK, Tor, Tesseract, Python deps) |
| `main.py` / `pipeline.py` | Full create-AVD → Tor → install → OCR pipeline (alternative) |
| `avd_manager.py`, `tor_proxy.py`, `adb_tools.py`, `ocr.py`, `config.py` | Core modules |
| `requirements.txt` | Python dependencies |

## Tor routing

`tor` runs on the Ubuntu host as a SOCKS5 proxy (port `9050`). The emulator is launched wrapped in `torsocks`, forcing its TCP traffic through Tor.
