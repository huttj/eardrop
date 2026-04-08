from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime
from pathlib import Path

from .aligner import align, group_into_utterances
from .config import Config
from .database import Database
from .diarizer import diarize
from .exporter import export_transcript_json
from .models import Recording, Speaker, Summary, Transcript
from .summarizer import summarize_all_types
from .transcriber import transcribe

log = logging.getLogger(__name__)


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _get_duration(path: Path) -> float | None:
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(str(path))
        return len(audio) / 1000.0
    except Exception:
        log.warning("Could not determine duration for %s", path.name)
        return None


def process_recording(audio_path: Path, config: Config, db: Database) -> str:
    """Process a single audio file through the full pipeline.

    Returns the recording ID.
    """
    log.info("=== Processing %s ===", audio_path.name)

    # 1. Check for duplicates
    fhash = _file_hash(audio_path)
    existing = db.get_recording_by_hash(fhash)
    if existing:
        log.info("Duplicate detected (recording %s), skipping", existing.id)
        return existing.id

    # 2. Create recording entry
    recording_id = str(uuid.uuid4())
    duration = _get_duration(audio_path)
    stat = audio_path.stat()

    recording = Recording(
        id=recording_id,
        source_path=str(audio_path),
        filename=audio_path.name,
        file_hash=fhash,
        duration_seconds=duration,
        file_size_bytes=stat.st_size,
        recorded_at=datetime.fromtimestamp(stat.st_mtime),
        status="pending",
    )
    db.insert_recording(recording)

    try:
        # 3. Transcribe
        db.update_recording_status(recording_id, "transcribing")
        transcription = transcribe(audio_path, config)
        recording.language = transcription.language
        db.update_recording(recording_id, language=transcription.language)

        # 4. Diarize
        db.update_recording_status(recording_id, "diarizing")
        diarization_segments = diarize(audio_path, config)

        # 5. Align
        words = align(transcription.words, diarization_segments)
        utterances = group_into_utterances(words)
        full_text = " ".join(w.word for w in words)

        # 6. Store speakers
        unique_speakers = list({w.speaker for w in words if w.speaker})
        speakers = [Speaker(label=s) for s in sorted(unique_speakers)]
        db.insert_speakers(recording_id, speakers)

        # 7. Store transcript
        transcript = Transcript(
            recording_id=recording_id,
            full_text=full_text,
            utterances=utterances,
            words=words,
            model_name=config.whisper_model,
        )
        db.insert_transcript(transcript)

        # 8. Summarize
        db.update_recording_status(recording_id, "summarizing")
        summaries: list[Summary] = []
        try:
            summaries = summarize_all_types(recording_id, utterances, config)
            for s in summaries:
                db.insert_summary(s)
        except Exception:
            log.exception("Summarization failed (non-fatal)")

        # 9. Export JSON
        export_transcript_json(recording, transcript, speakers, summaries, config)

        # 10. Done
        db.update_recording_status(recording_id, "complete")
        log.info("=== Completed %s (recording %s) ===", audio_path.name, recording_id)

    except Exception as e:
        log.exception("Pipeline failed for %s", audio_path.name)
        db.update_recording_status(recording_id, "error", str(e))
        raise

    return recording_id
