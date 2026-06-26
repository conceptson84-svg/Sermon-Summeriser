# App icon

Put your church logo here as **`icon.png`** to set the app icon.

Best results:
- **Square** (e.g. 1024×1024)
- **Transparent background** (PNG)
- Simple, high-contrast — it gets shown as small as 16×16

Then the build scripts run `make_icon.py` automatically, which generates:
- `icon.icns` — used for the macOS `.app`
- `icon.ico` — used for the Windows `.exe`

To generate the icons manually without building:

```bash
python make_icon.py
```

Note: a proper `.icns` is built with macOS's `iconutil`, so build the Mac icon
on a Mac. The `.ico` for Windows works from any OS.
