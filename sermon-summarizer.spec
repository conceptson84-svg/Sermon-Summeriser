# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Church Sermon Summarizer.

Builds a one-folder bundle (most reliable for the heavy native deps). On macOS
it is additionally wrapped into a .app via the BUNDLE step.

Build:  pyinstaller sermon-summarizer.spec
Output: dist/SermonSummarizer/   (and dist/SermonSummarizer.app on macOS)
"""

import sys
from PyInstaller.utils.hooks import collect_all

datas = [("config.example.json", ".")]
binaries = []
hiddenimports = [
    "anthropic", "openai", "PIL", "reportlab", "pptx", "numpy",
]

# These packages ship native libraries / data files that PyInstaller's static
# analysis misses. collect_all pulls in their binaries, data, and submodules.
for pkg in ("faster_whisper", "ctranslate2", "sounddevice", "av",
            "tokenizers", "onnxruntime", "huggingface_hub"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass  # package may not be present on every build host

block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "tensorflow", "matplotlib"],  # not used; keep size down
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SermonSummarizer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI app — no terminal window
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="SermonSummarizer",
)

# macOS: wrap the folder into a double-clickable .app bundle.
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="SermonSummarizer.app",
        icon=None,  # add an .icns path here later for a custom icon
        bundle_identifier="org.church.sermonsummarizer",
        info_plist={
            "NSMicrophoneUsageDescription":
                "Sermon Summarizer listens to the mixer audio to transcribe the sermon.",
            "NSHighResolutionCapable": True,
        },
    )
