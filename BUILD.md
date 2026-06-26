# Building a distributable app

This packages the Sermon Summarizer into a double-clickable app so volunteers
don't need Python. It uses [PyInstaller](https://pyinstaller.org).

**You build separately on each OS** — a Mac build must be made on a Mac, a
Windows build on Windows. There is no cross-compiling.

## macOS

```bash
./build_mac.sh
```

Output: `dist/SermonSummarizer.app`

- Right-click the `.app` → **Compress** to get a `.zip`, and share that.
- Because it's unsigned, the first launch needs: right-click the app → **Open**
  → **Open** (one time). After that it opens normally.

## Windows

Double-click **`build_windows.bat`** (or run it in a terminal).

Output: `dist\SermonSummarizer\` (with `SermonSummarizer.exe` inside)

- Zip the whole `SermonSummarizer` folder and share it.
- Users unzip and run `SermonSummarizer.exe`. SmartScreen may warn (unsigned):
  **More info → Run anyway** (one time).

## What the user gets

- No Python or pip needed.
- On **first Start**, the app downloads the Whisper transcription model once
  (~150 MB, needs internet that one time). After that it works offline.
- Config is stored per-user, not inside the app:
  - macOS: `~/Library/Application Support/SermonSummarizer/config.json`
  - Windows: `%APPDATA%\SermonSummarizer\config.json`
- Exported PDFs/PPTX default to `~/Documents/SermonSummarizer/` (the End Service
  button also lets them pick a folder).

## Size

Expect ~150–300 MB unzipped. That's normal for a bundled Python app with
transcription libraries.

## Notes / troubleshooting

- If a library is missing at runtime ("ModuleNotFoundError"), add its name to
  `hiddenimports` in `sermon-summarizer.spec` and rebuild.
- The build creates a throwaway `.venv-build/` — safe to delete.
- To shrink the download or work fully offline from first launch, you can bundle
  the Whisper model instead of downloading it; ask and we'll wire that in.

## Not included yet (future)

- **Code signing / notarization** — removes the "unidentified developer" /
  SmartScreen warnings. Needs paid Apple ($99/yr) and Windows (~$200/yr)
  certificates.
- **Installer wizard** (DMG / MSI) and **auto-update**.
