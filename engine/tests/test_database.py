import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from eardrop.config import Config
from eardrop.database import Database
from eardrop.models import Recording, Speaker, Summary, Transcript, Utterance, Word


@pytest.fixture
def db(tmp_path: Path) -> Database:
    config = Config(db_path=tmp_path / "test.db")
    d = Database(config)
    d.init_schema()
    yield d
    d.close()


@pytest.fixture
def sample_recording() -> Recording:
    return Recording(
        id="rec-001",
        source_path="/tmp/test.m4a",
        filename="test.m4a",
        file_hash="abc123",
        duration_seconds=60.0,
        language="en",
        file_size_bytes=1024,
        recorded_at=datetime(2026, 4, 8, 14, 30),
        status="pending",
    )


def test_insert_and_get_recording(db: Database, sample_recording: Recording):
    db.insert_recording(sample_recording)
    result = db.get_recording("rec-001")
    assert result is not None
    assert result.filename == "test.m4a"
    assert result.file_hash == "abc123"
    assert result.status == "pending"


def test_duplicate_hash_detection(db: Database, sample_recording: Recording):
    db.insert_recording(sample_recording)
    found = db.get_recording_by_hash("abc123")
    assert found is not None
    assert found.id == "rec-001"


def test_update_status(db: Database, sample_recording: Recording):
    db.insert_recording(sample_recording)
    db.update_recording_status("rec-001", "transcribing")
    rec = db.get_recording("rec-001")
    assert rec.status == "transcribing"


def test_update_status_with_error(db: Database, sample_recording: Recording):
    db.insert_recording(sample_recording)
    db.update_recording_status("rec-001", "error", "something broke")
    rec = db.get_recording("rec-001")
    assert rec.status == "error"
    assert rec.error_message == "something broke"


def test_insert_speakers(db: Database, sample_recording: Recording):
    db.insert_recording(sample_recording)
    speakers = [Speaker(label="SPEAKER_00"), Speaker(label="SPEAKER_01", alias="Alice")]
    db.insert_speakers("rec-001", speakers)
    result = db.get_speakers("rec-001")
    assert len(result) == 2
    labels = {s.label for s in result}
    assert "SPEAKER_00" in labels
    assert "SPEAKER_01" in labels


def test_insert_and_get_transcript(db: Database, sample_recording: Recording):
    db.insert_recording(sample_recording)
    transcript = Transcript(
        recording_id="rec-001",
        full_text="Hello world",
        utterances=[Utterance(speaker="A", start=0.0, end=1.0, text="Hello world")],
        words=[Word(word="Hello", start=0.0, end=0.5, speaker="A"),
               Word(word="world", start=0.6, end=1.0, speaker="A")],
        model_name="test-model",
    )
    db.insert_transcript(transcript)
    result = db.get_transcript("rec-001")
    assert result is not None
    assert result.full_text == "Hello world"
    assert len(result.utterances) == 1
    assert len(result.words) == 2


def test_insert_and_get_summary(db: Database, sample_recording: Recording):
    db.insert_recording(sample_recording)
    summary = Summary(
        recording_id="rec-001",
        summary_text="A greeting was exchanged.",
        summary_type="general",
        model_name="test-model",
    )
    db.insert_summary(summary)
    results = db.get_summaries("rec-001")
    assert len(results) == 1
    assert results[0].summary_text == "A greeting was exchanged."


def test_fts_search(db: Database, sample_recording: Recording):
    db.insert_recording(sample_recording)
    transcript = Transcript(
        recording_id="rec-001",
        full_text="We discussed the quarterly budget and hiring plans",
        utterances=[],
        words=[],
    )
    db.insert_transcript(transcript)
    results = db.search_transcripts("budget")
    assert len(results) == 1
    assert results[0]["recording_id"] == "rec-001"


def test_fts_no_results(db: Database, sample_recording: Recording):
    db.insert_recording(sample_recording)
    transcript = Transcript(
        recording_id="rec-001",
        full_text="Hello world",
        utterances=[],
        words=[],
    )
    db.insert_transcript(transcript)
    results = db.search_transcripts("nonexistent")
    assert len(results) == 0


def test_list_recordings_in_range(db: Database):
    for i, day in enumerate([5, 8, 12]):
        rec = Recording(
            id=f"rec-{i}",
            source_path=f"/tmp/test{i}.m4a",
            filename=f"test{i}.m4a",
            file_hash=f"hash{i}",
            recorded_at=datetime(2026, 4, day, 10, 0),
            status="complete",
        )
        db.insert_recording(rec)

    results = db.list_recordings_in_range(
        datetime(2026, 4, 7), datetime(2026, 4, 10)
    )
    assert len(results) == 1
    assert results[0].id == "rec-1"
