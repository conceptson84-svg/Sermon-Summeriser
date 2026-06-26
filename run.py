#!/usr/bin/env python3
"""Entry point for the Church Sermon Summarizer.

Wires the pipeline and launches the control panel + second-screen slide window.

    python run.py            # run the app
    python run.py --devices  # list audio input devices and exit
"""

from __future__ import annotations

import argparse
import logging
import sys

from sermon_summarizer.config import (
    Config, default_config_path, default_exports_dir, ensure_config,
)


def main():
    parser = argparse.ArgumentParser(description="Church Sermon Summarizer")
    parser.add_argument("--config", default=None,
                        help="Path to config.json (default: per-OS user data dir)")
    parser.add_argument("--devices", action="store_true", help="List audio input devices and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.devices:
        from sermon_summarizer.audio.capture import list_input_devices
        for d in list_input_devices():
            print(f"[{d['index']}] {d['name']}")
        return 0

    cfg_path = args.config or str(default_config_path())
    ensure_config(cfg_path)  # seed from the bundled example on first run
    cfg = Config.load(cfg_path)

    # Lazy imports so --devices and --help don't require the heavy deps.
    from sermon_summarizer.audio.capture import AudioCapture
    from sermon_summarizer.transcribe.whisper_worker import WhisperTranscriber
    from sermon_summarizer.summarize.summarizer import Summarizer, NullSummarizer
    from sermon_summarizer.app.controller import ServiceController
    from sermon_summarizer.app.ui import ControlPanel
    from sermon_summarizer.slides.renderer import SlideWindow

    # Launch even without a key — the volunteer can paste one into the control
    # panel. Until then a no-op summariser keeps the app running.
    if cfg.has_key_for_provider():
        summarizer = Summarizer.from_config(cfg)
    else:
        summarizer = NullSummarizer()
        print(f"No API key for '{cfg.provider}' yet — enter one in the control panel.",
              file=sys.stderr)
    transcriber = WhisperTranscriber(
        model_size=cfg.whisper_model_size, cpu_threads=cfg.whisper_cpu_threads)
    capture = AudioCapture(device_index=cfg.audio_device_index)

    controller = ServiceController(
        capture=capture, transcriber=transcriber, summarizer=summarizer, config=cfg)

    panel = ControlPanel.__new__(ControlPanel)  # build root first
    # Build the UI, then attach the second-screen window to its Tk root.
    panel.__init__(controller, slide_window=None, config=cfg,
                   export_dir=str(default_exports_dir()))
    slide_window = SlideWindow(panel.root, screen_index=cfg.second_screen_index,
                               church_name=cfg.church_name, theme=cfg.theme,
                               font_scale=cfg.font_scale,
                               background_image=cfg.background_image,
                               logo_image=cfg.logo_image)
    panel._slide_window = slide_window
    slide_window.bind_nav(panel._nav_prev, panel._nav_next)

    panel._capture = capture
    controller._on_deck_update = panel.on_deck_update
    controller._on_status = panel.set_status
    capture._on_status = panel.set_status
    transcriber._on_status = panel.set_status  # first-run model download feedback

    if cfg.has_key_for_provider():
        panel.set_status(f"Ready — provider: {cfg.provider}. Press Start.")
    else:
        panel.set_status(f"No API key for '{cfg.provider}'. Add one in AI engine, then Start.")

    panel.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
