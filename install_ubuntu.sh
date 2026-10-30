#!/usr/bin/env bash
# install_ubuntu.sh
# One-shot setup for an Ubuntu server that will run the AVD + Tor + OCR app.
# Run as a user with sudo:  bash install_ubuntu.sh

set -euo pipefail

echo "==> Updating package index"
sudo apt-get update -y

echo "==> Installing core packages"
sudo apt-get install -y \
    openjdk-17-jdk \
    wget \
    curl \
    unzip \
    tor \
    torsocks \
    tesseract-ocr \
    python3 \
    python3-pip \
    python3-venv

echo "==> Installing Android command-line tools"
SDK_ROOT="${ANDROID_SDK_ROOT:-$HOME/android-sdk}"
CMDLINE_ZIP="commandlinetools-linux-11076708_latest.zip"
CMDLINE_URL="https://dl.google.com/android/repository/${CMDLINE_ZIP}"

mkdir -p "$SDK_ROOT/cmdline-tools"
cd "$SDK_ROOT/cmdline-tools"

if [ ! -f "$CMDLINE_ZIP" ]; then
    echo "Downloading Android command-line tools..."
    wget -q "$CMDLINE_URL" -O "$CMDLINE_ZIP"
fi

unzip -o -q "$CMDLINE_ZIP"
# sdkmanager expects tools under cmdline-tools/latest/bin
mkdir -p latest
mv -n cmdline-tools/* latest/ 2>/dev/null || true

export ANDROID_SDK_ROOT="$SDK_ROOT"
export ANDROID_HOME="$SDK_ROOT"
export PATH="$SDK_ROOT/cmdline-tools/latest/bin:$SDK_ROOT/platform-tools:$PATH"

echo "==> Installing SDK components"
yes | sdkmanager --licenses >/dev/null 2>&1 || true
sdkmanager "platform-tools" "cmdline-tools;latest" "emulator" || true

echo "==> Installing Python dependencies"
python3 -m pip install --upgrade pip
python3 -m pip install pytesseract Pillow pyyaml

echo "==> Done"
echo "Add the following to your shell (e.g. ~/.bashrc) and re-source:"
echo "  export ANDROID_SDK_ROOT=$SDK_ROOT"
echo "  export ANDROID_HOME=\$ANDROID_SDK_ROOT"
echo "  export PATH=\$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:\$ANDROID_SDK_ROOT/platform-tools:\$PATH"
echo ""
echo "Then run:  python main.py --apk ./app.apk"
