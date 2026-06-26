"""Mixer audio capture via sounddevice.

Captures PCM from the selected input device (the mixer feed into the Mac) and
pushes fixed-size mono chunks onto a thread-safe queue for the transcription
worker.

Device-adaptive: not every device opens as mono. We query the device's input
channel count, capture at what it supports (capped at stereo), and downmix to
mono — Whisper wants 16 kHz mono. Detects device-gone and silence so the
control panel can warn the volunteer.
"""

from __future__ import annotations

import logging
import queue
import threading

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000  # Whisper expects 16 kHz mono.
CHUNK_SECONDS = 5.0  # Transcribe in 5-second chunks.


def list_input_devices() -> list[dict]:
    """Return available input devices so the UI can offer a picker."""
    import sounddevice as sd

    devices = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) > 0:
            devices.append({
                "index": idx,
                "name": dev["name"],
                "channels": dev["max_input_channels"],
            })
    return devices


def resolve_input_channels(device_index) -> int:
    """How many channels to open for this device (capped at stereo; callers
    downmix to mono). Raises if the device has no inputs."""
    import sounddevice as sd

    info = sd.query_devices(device_index, "input")
    max_in = int(info.get("max_input_channels", 0))
    if max_in < 1:
        raise RuntimeError(
            f"Selected audio device '{info.get('name', device_index)}' has no "
            f"input channels. Run `python run.py --devices` and pick an input."
        )
    return min(max_in, 2)


class AudioCapture:
    def __init__(self, device_index: int | None = None, on_status=None):
        self._device_index = device_index
        self._on_status = on_status or (lambda msg: None)
        self._queue: "queue.Queue[bytes]" = queue.Queue(maxsize=64)
        self._stream = None
        self._stop = threading.Event()
        self._channels = 1
        self._level = 0.0
        self._level_lock = threading.Lock()

    def set_device(self, device_index) -> None:
        """Change the input device. Takes effect the next time the service is
        started (the live stream is not hot-swapped mid-service)."""
        self._device_index = device_index

    def level(self) -> float:
        """Latest input level, 0.0–1.0, for the live activity meter."""
        with self._level_lock:
            return self._level

    def _resolve_channels(self) -> int:
        return resolve_input_channels(self._device_index)

    def _callback(self, indata, frames, time_info, status):  # pragma: no cover - hw
        import numpy as np

        if status:
            log.debug("audio status: %s", status)
        # indata is shape (frames, channels) int16. Downmix to mono int16.
        if indata.ndim == 2 and indata.shape[1] > 1:
            mono = indata.mean(axis=1).astype(np.int16)
        else:
            mono = indata.reshape(-1).astype(np.int16)
        # Track input level for the live activity meter.
        peak = float(np.max(np.abs(mono))) / 32768.0 if mono.size else 0.0
        with self._level_lock:
            self._level = min(1.0, peak * 1.4)
        data = mono.tobytes()
        try:
            self._queue.put_nowait(data)
        except queue.Full:
            # Drop oldest to stay real-time rather than block the audio thread.
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(data)
            except queue.Empty:
                pass

    def start(self):  # pragma: no cover - requires hardware
        import sounddevice as sd

        try:
            self._channels = self._resolve_channels()
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                blocksize=int(SAMPLE_RATE * CHUNK_SECONDS),
                device=self._device_index,
                channels=self._channels,
                dtype="int16",
                callback=self._callback,
            )
            self._stream.start()
            self._on_status(f"Audio capture started ({self._channels}ch → mono)")
        except Exception as e:  # noqa: BLE001
            self._on_status(f"AUDIO ERROR: {e}")
            raise

    def chunks(self):
        """Yield raw int16 mono PCM chunks until stopped. Blocks between chunks."""
        while not self._stop.is_set():
            try:
                yield self._queue.get(timeout=1.0)
            except queue.Empty:
                self._on_status("No audio — check mixer connection")

    def stop(self):  # pragma: no cover - requires hardware
        self._stop.set()
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._on_status("Audio capture stopped")
