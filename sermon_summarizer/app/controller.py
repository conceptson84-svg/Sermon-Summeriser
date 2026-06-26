"""Service orchestrator — ties the pipeline together.

    audio chunks -> transcribe -> rolling window
                                      |
                 every N minutes -> Claude summarize -> validated Points
                                      |
                                      v
                                 rolling Deck -> renderer (TV / NDI)

Runs the audio+transcription loop on one thread and the summarisation cadence on
another. Pause/resume gates both. The summary thread is the never-crash path:
ClaudeSummarizer.summarize() returns [] on any failure and the deck is simply
left unchanged (last slide stays on screen).
"""

from __future__ import annotations

import logging
import threading
import time

from .events import ServiceState
from ..slides.deck import Deck
from ..transcribe.window import TranscriptWindow

log = logging.getLogger(__name__)


class ServiceController:
    def __init__(
        self,
        capture,
        transcriber,
        summarizer,
        config,
        on_deck_update=None,
        on_status=None,
        clock=time.monotonic,
    ):
        self._capture = capture
        self._transcriber = transcriber
        self._summarizer = summarizer
        self._cfg = config
        self._on_deck_update = on_deck_update or (lambda deck: None)
        self._on_status = on_status or (lambda msg: None)
        self._clock = clock

        self.deck = Deck()
        self.window = TranscriptWindow(window_seconds=config.transcript_window_seconds, clock=clock)
        self.state = ServiceState.STOPPED

        self._paused = threading.Event()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def set_summarizer(self, summarizer) -> None:
        """Hot-swap the summariser (e.g. when the volunteer picks a different
        provider in the UI). Safe to call while running — the next cycle uses it."""
        self._summarizer = summarizer

    # --- lifecycle ---------------------------------------------------------
    def start(self):  # pragma: no cover - spawns hardware threads
        if self.state is ServiceState.RUNNING:
            return
        self._stop.clear()
        self._paused.clear()
        self.state = ServiceState.RUNNING
        self._capture.start()
        self._threads = [
            threading.Thread(target=self._audio_loop, name="audio", daemon=True),
            threading.Thread(target=self._summary_loop, name="summary", daemon=True),
        ]
        for t in self._threads:
            t.start()
        self._on_status("Service running")

    def pause(self):
        self._paused.set()
        self.state = ServiceState.PAUSED
        self._on_status("Paused")

    def resume(self):
        self._paused.clear()
        self.state = ServiceState.RUNNING
        self._on_status("Resumed")

    def stop(self):  # pragma: no cover - hardware teardown
        self._stop.set()
        self.state = ServiceState.STOPPED
        try:
            self._capture.stop()
        except Exception as e:  # noqa: BLE001
            log.warning("capture stop error: %s", e)
        self._on_status("Service stopped")

    # --- loops -------------------------------------------------------------
    def _audio_loop(self):  # pragma: no cover - requires hardware
        for chunk in self._capture.chunks():
            if self._stop.is_set():
                break
            if self._paused.is_set():
                continue
            text = self._transcriber.transcribe_pcm(chunk)
            if text:
                self.window.add(text)

    def _summary_loop(self):  # pragma: no cover - timing loop
        # Read the interval from config each cycle so changes made in the UI
        # take effect without restarting the service.
        next_run = self._clock() + self._cfg.summarize_interval_seconds
        while not self._stop.is_set():
            time.sleep(0.5)
            if self._paused.is_set() or self._clock() < next_run:
                continue
            next_run = self._clock() + self._cfg.summarize_interval_seconds
            self.run_summary_cycle()

    # --- testable unit -----------------------------------------------------
    def run_summary_cycle(self) -> int:
        """One summarisation cycle. Returns number of new points added.

        Pure-ish: depends only on injected summarizer + window + deck, so it is
        unit-tested in tests/test_resilience.py with a fake summarizer that
        raises / returns junk. Never raises.
        """
        transcript = self.window.text()
        if not transcript:
            return 0
        shown = [p.text for p in self.deck.all_points()]
        points = self._summarizer.summarize(transcript, already_shown=shown)  # [] on any failure
        added = self.deck.add_points(points)
        if added:
            self._on_deck_update(self.deck)
        return added
