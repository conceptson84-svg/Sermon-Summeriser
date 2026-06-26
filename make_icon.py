#!/usr/bin/env python3
"""Convert a source PNG logo into app icons for packaging.

Input:  assets/icon.png   (square, ideally 1024x1024, transparent background)
Output: assets/icon.icns  (macOS .app icon)
        assets/icon.ico   (Windows .exe icon)

The build scripts call this automatically when assets/icon.png exists.
Run manually with:  python make_icon.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SRC = Path("assets/icon.png")
ICNS = Path("assets/icon.icns")
ICO = Path("assets/icon.ico")


def _load_square(path: Path):
    from PIL import Image

    img = Image.open(path).convert("RGBA")
    w, h = img.size
    if w != h:
        # Pad to a centered square so the icon isn't distorted.
        side = max(w, h)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(img, ((side - w) // 2, (side - h) // 2), img)
        img = canvas
    return img


def make_ico(img):
    sizes = [(s, s) for s in (16, 32, 48, 64, 128, 256)]
    img.save(ICO, format="ICO", sizes=sizes)
    print(f"  wrote {ICO}")


def make_icns(img):
    # The reliable macOS path: build an .iconset and run iconutil.
    iconutil = shutil.which("iconutil")
    if sys.platform == "darwin" and iconutil:
        with tempfile.TemporaryDirectory() as tmp:
            iconset = Path(tmp) / "icon.iconset"
            iconset.mkdir()
            specs = [
                (16, "icon_16x16.png"), (32, "icon_16x16@2x.png"),
                (32, "icon_32x32.png"), (64, "icon_32x32@2x.png"),
                (128, "icon_128x128.png"), (256, "icon_128x128@2x.png"),
                (256, "icon_256x256.png"), (512, "icon_256x256@2x.png"),
                (512, "icon_512x512.png"), (1024, "icon_512x512@2x.png"),
            ]
            for size, name in specs:
                img.resize((size, size)).save(iconset / name)
            subprocess.run([iconutil, "-c", "icns", str(iconset), "-o", str(ICNS)],
                           check=True)
        print(f"  wrote {ICNS}")
        return
    # Fallback (non-mac, or no iconutil): let Pillow try.
    try:
        img.save(ICNS, format="ICNS")
        print(f"  wrote {ICNS} (Pillow)")
    except Exception as e:  # noqa: BLE001
        print(f"  skipped {ICNS}: {e} (build .icns on a Mac for the app icon)")


def main():
    if not SRC.exists():
        print(f"No {SRC} found — drop a square PNG there to set the app icon.")
        return 0
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print("Pillow needed: pip install pillow")
        return 1
    img = _load_square(SRC)
    print(f"Generating icons from {SRC} ({img.size[0]}x{img.size[1]})")
    make_ico(img)
    make_icns(img)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
