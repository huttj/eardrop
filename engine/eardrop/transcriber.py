from __future__ import annotations

import logging
from pathlib import Path

from .config import Config
from .models import TranscriptionResult, Word

log = logging.getLogger(__name__)

_model_cache: dict[str, object] = {}


def transcribe(audio_path: Path, config: Config) -> TranscriptionResult:
    """Transcribe an audio file using mlx-whisper with word-level timestamps."""
    import mlx_whisper

    log.info("Transcribing %s with model %s", audio_path.name, config.whisper_model)

    result = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=config.whisper_model,
        word_timestamps=True,
    )

    words: list[Word] = []
    for segment in result.get("segments", []):
        for w in segment.get("words", []):
            words.append(Word(
                word=w["word"].strip(),
                start=w["start"],
                end=w["end"],
            ))

    language = result.get("language", "en")
    full_text = result.get("text", "").strip()

    log.info("Transcribed %d words, language=%s", len(words), language)

    return TranscriptionResult(
        language=language,
        segments=result.get("segments", []),
        words=words,
    )
