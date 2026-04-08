from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from .config import Config
from .models import Recording, Speaker, Summary, Transcript

log = logging.getLogger(__name__)


def export_transcript_json(
    recording: Recording,
    transcript: Transcript,
    speakers: list[Speaker],
    summaries: list[Summary],
    config: Config,
) -> Path:
    """Write a transcript JSON file to the output directory (iCloud Drive).

    Uses atomic write (temp file + rename) to prevent iCloud from syncing
    partial files.
    """
    config.output_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "version": "1.0",
        "recording_id": recording.id,
        "source_file": recording.filename,
        "recorded_at": recording.recorded_at.isoformat() if recording.recorded_at else None,
        "processed_at": recording.created_at.isoformat() if recording.created_at else None,
        "duration_seconds": recording.duration_seconds,
        "language": recording.language,
        "speakers": {
            s.label: {"label": s.label, "alias": s.alias}
            for s in speakers
        },
        "utterances": [
            {
                "speaker": u.speaker,
                "start": u.start,
                "end": u.end,
                "text": u.text,
            }
            for u in transcript.utterances
        ],
        "full_text": transcript.full_text,
        "summaries": {
            s.summary_type: s.summary_text
            for s in summaries
        },
    }

    output_path = config.output_dir / f"{recording.id}.json"

    # Atomic write: write to temp file in same dir, then rename
    fd, tmp_path = tempfile.mkstemp(
        dir=str(config.output_dir), suffix=".json.tmp"
    )
    try:
        with open(fd, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        Path(tmp_path).rename(output_path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise

    log.info("Exported transcript to %s", output_path)
    return output_path
