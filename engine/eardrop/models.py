from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Word:
    word: str
    start: float
    end: float
    speaker: str | None = None


@dataclass
class Utterance:
    speaker: str
    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    language: str
    segments: list[dict]
    words: list[Word]


@dataclass
class DiarizationSegment:
    start: float
    end: float
    speaker: str


@dataclass
class Speaker:
    label: str
    alias: str | None = None


@dataclass
class Transcript:
    recording_id: str
    full_text: str
    utterances: list[Utterance]
    words: list[Word]
    model_name: str | None = None


@dataclass
class Summary:
    recording_id: str
    summary_text: str
    summary_type: str = "general"
    model_name: str | None = None


@dataclass
class Recording:
    id: str
    source_path: str
    filename: str
    file_hash: str
    duration_seconds: float | None = None
    language: str | None = None
    file_size_bytes: int | None = None
    recorded_at: datetime | None = None
    created_at: datetime | None = None
    status: str = "pending"
    error_message: str | None = None
    speakers: list[Speaker] = field(default_factory=list)
    transcript: Transcript | None = None
    summaries: list[Summary] = field(default_factory=list)
