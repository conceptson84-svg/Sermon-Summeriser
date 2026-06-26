"""Live input-level meter for the 'Test audio' indicator.

Opens its own short-lived monitor stream on the selected device so a volunteer
can confirm the mixer feed is being picked up BEFORE starting the service. It is
independent of AudioCapture (which runs during the service); the UI stops the
meter before Start so the two never contend for the device.

Exposes a 0.0–1.0 level read by the UI on a timer — no cross-thread Tk calls.
"""

from __future__ import annotations

import logging
import threading

from .capture import resolve_input_channels

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000


class AudioMeter:
    def __init__(self, device_index=None):
        self._device_index = device_index
        self._stream = None
        self._level = 0.0
        self._lock = threading.Lock()

    def _callback(self, indata, frames, time_info, status):  # pragma: no cover - hw
        import numpy as np

        if status:
            log.debug("meter status: %s", status)
        # indata: (frames, channels) int16. Peak across the block, normalized.
        peak = float(np.max(np.abs(indata))) / 32768.0 if indata.size else 0.0
        # Slight gain so normal speech fills a useful portion of the bar; clamp.
        level = min(1.0, peak * 1.4)
        with self._lock:
            self._level = level

    def start(self):  # pragma: no cover - requires hardware
        import sounddevice as sd

        channels = resolve_input_channels(self._device_index)
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            blocksize=int(SAMPLE_RATE * 0.05),  # 50 ms = responsive meter
            device=self._device_index,
            channels=channels,
            dtype="int16",
            callback=self._callback,
        )
        self._stream.start()

    def level(self) -> float:
        with self._lock:
            return self._level

    def stop(self):  # pragma: no cover - requires hardware
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:  # noqa: BLE001
                log.debug("meter stop error: %s", e)
            self._stream = None
        with self._lock:
            self._level = 0.0
