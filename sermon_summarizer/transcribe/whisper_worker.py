"""Local transcription via faster-whisper.

Runs the 'small' model on CPU with a hard thread cap so it can never starve OBS
during a live broadcast (eng review issue #2). Fully offline — sermon audio
never leaves the building.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

DEFAULT_MODEL_SIZE = "small"
# Hard cap so transcription leaves CPU headroom for OBS encoding. Tune down if
# OBS still drops frames on your media Mac.
DEFAULT_CPU_THREADS = 2


class WhisperTranscriber:
    def __init__(
        self,
        model_size: str = DEFAULT_MODEL_SIZE,
        cpu_threads: int = DEFAULT_CPU_THREADS,
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "faster-whisper not installed. Run: pip install faster-whisper"
            ) from e
        self._model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads,
        )
        self._cpu_threads = cpu_threads

    def transcribe_pcm(self, pcm_int16: bytes) -> str:  # pragma: no cover - heavy dep
        """Transcribe one chunk of 16 kHz mono int16 PCM. Returns '' if silence
        or on any decode error (caller just appends nothing)."""
        import numpy as np

        if not pcm_int16:
            return ""
        try:
            audio = np.frombuffer(pcm_int16, dtype=np.int16).astype(np.float32) / 32768.0
            segments, _info = self._model.transcribe(audio, language="en", vad_filter=True)
            return " ".join(seg.text.strip() for seg in segments).strip()
        except Exception as e:  # noqa: BLE001
            log.warning("transcription chunk failed: %s", e)
            return ""
