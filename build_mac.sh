#!/usr/bin/env bash
# Build the macOS app bundle. Run this ON A MAC.
# Output: dist/SermonSummarizer.app
set -e
cd "$(dirname "$0")"

echo "==> Setting up build environment"
python3 -m venv .venv-build
source .venv-build/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt

echo "==> Building with PyInstaller"
rm -rf build dist
pyinstaller sermon-summarizer.spec

echo
echo "==> Done. App bundle:"
echo "    dist/SermonSummarizer.app"
echo
echo "To distribute: right-click dist/SermonSummarizer.app -> Compress, and share"
echo "the resulting .zip. First launch: right-click the app -> Open (unsigned)."
