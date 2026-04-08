from __future__ import annotations

import logging
from pathlib import Path

from .config import Config
from .models import DiarizationSegment

log = logging.getLogger(__name__)

_pipeline = None


def _get_pipeline(config: Config):
    global _pipeline
    if _pipeline is None:
        import torch
        from pyannote.audio import Pipeline

        log.info("Loading pyannote diarization pipeline...")
        _pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=config.hf_token,
        )
        # IMPORTANT: MPS produces wrong timestamps (pyannote issue #1337).
        # Always use CPU for correct results.
        _pipeline.to(torch.device("cpu"))
        log.info("Diarization pipeline loaded (CPU)")
    return _pipeline


def diarize(audio_path: Path, config: Config) -> list[DiarizationSegment]:
    """Run speaker diarization on an audio file. Returns time-aligned speaker segments."""
    pipeline = _get_pipeline(config)

    log.info("Diarizing %s", audio_path.name)
    diarization = pipeline(str(audio_path))

    segments: list[DiarizationSegment] = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append(DiarizationSegment(
            start=turn.start,
            end=turn.end,
            speaker=speaker,
        ))

    # Sort by start time
    segments.sort(key=lambda s: s.start)

    log.info("Found %d speaker segments, %d unique speakers",
             len(segments), len({s.speaker for s in segments}))
    return segments


def unload_pipeline() -> None:
    """Free the diarization pipeline from memory."""
    global _pipeline
    if _pipeline is not None:
        del _pipeline
        _pipeline = None
        import gc
        gc.collect()
        log.info("Diarization pipeline unloaded")
