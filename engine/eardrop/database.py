from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from .config import Config
from .models import Recording, Speaker, Summary, Transcript, Utterance, Word

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recordings (
    id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    filename TEXT NOT NULL,
    duration_seconds REAL,
    language TEXT,
    file_hash TEXT NOT NULL,
    file_size_bytes INTEGER,
    recorded_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'pending'
        CHECK(status IN ('pending','transcribing','diarizing','summarizing','complete','error')),
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS speakers (
    id TEXT PRIMARY KEY,
    recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    alias TEXT,
    UNIQUE(recording_id, label)
);

CREATE TABLE IF NOT EXISTS transcripts (
    id TEXT PRIMARY KEY,
    recording_id TEXT NOT NULL UNIQUE REFERENCES recordings(id) ON DELETE CASCADE,
    full_text TEXT NOT NULL,
    utterances_json TEXT NOT NULL,
    words_json TEXT NOT NULL,
    model_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS summaries (
    id TEXT PRIMARY KEY,
    recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    summary_text TEXT NOT NULL,
    summary_type TEXT DEFAULT 'general',
    model_name TEXT,
    prompt_template TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS queries (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    recording_ids_json TEXT,
    model_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE IF NOT EXISTS transcripts_fts USING fts5(
    full_text,
    content='transcripts',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS summaries_fts USING fts5(
    summary_text,
    content='summaries',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS transcripts_ai AFTER INSERT ON transcripts BEGIN
    INSERT INTO transcripts_fts(rowid, full_text) VALUES (new.rowid, new.full_text);
END;
CREATE TRIGGER IF NOT EXISTS transcripts_ad AFTER DELETE ON transcripts BEGIN
    INSERT INTO transcripts_fts(transcripts_fts, rowid, full_text) VALUES('delete', old.rowid, old.full_text);
END;
CREATE TRIGGER IF NOT EXISTS transcripts_au AFTER UPDATE ON transcripts BEGIN
    INSERT INTO transcripts_fts(transcripts_fts, rowid, full_text) VALUES('delete', old.rowid, old.full_text);
    INSERT INTO transcripts_fts(rowid, full_text) VALUES (new.rowid, new.full_text);
END;

CREATE TRIGGER IF NOT EXISTS summaries_ai AFTER INSERT ON summaries BEGIN
    INSERT INTO summaries_fts(rowid, summary_text) VALUES (new.rowid, new.summary_text);
END;
CREATE TRIGGER IF NOT EXISTS summaries_ad AFTER DELETE ON summaries BEGIN
    INSERT INTO summaries_fts(summaries_fts, rowid, summary_text) VALUES('delete', old.rowid, old.summary_text);
END;
CREATE TRIGGER IF NOT EXISTS summaries_au AFTER UPDATE ON summaries BEGIN
    INSERT INTO summaries_fts(summaries_fts, rowid, summary_text) VALUES('delete', old.rowid, old.summary_text);
    INSERT INTO summaries_fts(rowid, summary_text) VALUES (new.rowid, new.summary_text);
END;

CREATE INDEX IF NOT EXISTS idx_recordings_status ON recordings(status);
CREATE INDEX IF NOT EXISTS idx_recordings_recorded_at ON recordings(recorded_at);
CREATE INDEX IF NOT EXISTS idx_recordings_file_hash ON recordings(file_hash);
CREATE INDEX IF NOT EXISTS idx_summaries_recording_id ON summaries(recording_id);
CREATE INDEX IF NOT EXISTS idx_speakers_recording_id ON speakers(recording_id);
"""


class Database:
    def __init__(self, config: Config) -> None:
        self.db_path = config.db_path
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def init_schema(self) -> None:
        self.conn.executescript(SCHEMA_SQL)
        self.conn.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
            ("version", str(SCHEMA_VERSION)),
        )
        self.conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # --- Recordings ---

    def insert_recording(self, rec: Recording) -> None:
        self.conn.execute(
            """INSERT INTO recordings
               (id, source_path, filename, duration_seconds, language,
                file_hash, file_size_bytes, recorded_at, status, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rec.id, rec.source_path, rec.filename, rec.duration_seconds,
                rec.language, rec.file_hash, rec.file_size_bytes,
                rec.recorded_at.isoformat() if rec.recorded_at else None,
                rec.status, rec.error_message,
            ),
        )
        self.conn.commit()

    def update_recording_status(self, recording_id: str, status: str,
                                error_message: str | None = None) -> None:
        self.conn.execute(
            "UPDATE recordings SET status = ?, error_message = ? WHERE id = ?",
            (status, error_message, recording_id),
        )
        self.conn.commit()

    def update_recording(self, recording_id: str, **kwargs: object) -> None:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [recording_id]
        self.conn.execute(f"UPDATE recordings SET {sets} WHERE id = ?", vals)
        self.conn.commit()

    def get_recording_by_hash(self, file_hash: str) -> Recording | None:
        row = self.conn.execute(
            "SELECT * FROM recordings WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        return self._row_to_recording(row) if row else None

    def get_recording(self, recording_id: str) -> Recording | None:
        row = self.conn.execute(
            "SELECT * FROM recordings WHERE id = ?", (recording_id,)
        ).fetchone()
        return self._row_to_recording(row) if row else None

    def list_recordings(self, status: str | None = None,
                        limit: int = 50, offset: int = 0) -> list[Recording]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM recordings WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (status, limit, offset),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM recordings ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [self._row_to_recording(r) for r in rows]

    def list_recordings_in_range(self, start: datetime, end: datetime) -> list[Recording]:
        rows = self.conn.execute(
            """SELECT * FROM recordings
               WHERE recorded_at >= ? AND recorded_at <= ?
               ORDER BY recorded_at DESC""",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        return [self._row_to_recording(r) for r in rows]

    @staticmethod
    def _row_to_recording(row: sqlite3.Row) -> Recording:
        return Recording(
            id=row["id"],
            source_path=row["source_path"],
            filename=row["filename"],
            file_hash=row["file_hash"],
            duration_seconds=row["duration_seconds"],
            language=row["language"],
            file_size_bytes=row["file_size_bytes"],
            recorded_at=datetime.fromisoformat(row["recorded_at"]) if row["recorded_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            status=row["status"],
            error_message=row["error_message"],
        )

    # --- Speakers ---

    def insert_speakers(self, recording_id: str, speakers: list[Speaker]) -> None:
        for s in speakers:
            self.conn.execute(
                "INSERT OR IGNORE INTO speakers (id, recording_id, label, alias) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), recording_id, s.label, s.alias),
            )
        self.conn.commit()

    def get_speakers(self, recording_id: str) -> list[Speaker]:
        rows = self.conn.execute(
            "SELECT label, alias FROM speakers WHERE recording_id = ?",
            (recording_id,),
        ).fetchall()
        return [Speaker(label=r["label"], alias=r["alias"]) for r in rows]

    # --- Transcripts ---

    def insert_transcript(self, transcript: Transcript) -> None:
        import json
        utterances_json = json.dumps([
            {"speaker": u.speaker, "start": u.start, "end": u.end, "text": u.text}
            for u in transcript.utterances
        ])
        words_json = json.dumps([
            {"word": w.word, "start": w.start, "end": w.end, "speaker": w.speaker}
            for w in transcript.words
        ])
        self.conn.execute(
            """INSERT INTO transcripts
               (id, recording_id, full_text, utterances_json, words_json, model_name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()), transcript.recording_id,
                transcript.full_text, utterances_json, words_json,
                transcript.model_name,
            ),
        )
        self.conn.commit()

    def get_transcript(self, recording_id: str) -> Transcript | None:
        import json
        row = self.conn.execute(
            "SELECT * FROM transcripts WHERE recording_id = ?",
            (recording_id,),
        ).fetchone()
        if not row:
            return None
        utterances = [
            Utterance(**u) for u in json.loads(row["utterances_json"])
        ]
        words = [
            Word(**w) for w in json.loads(row["words_json"])
        ]
        return Transcript(
            recording_id=row["recording_id"],
            full_text=row["full_text"],
            utterances=utterances,
            words=words,
            model_name=row["model_name"],
        )

    # --- Summaries ---

    def insert_summary(self, summary: Summary) -> None:
        self.conn.execute(
            """INSERT INTO summaries
               (id, recording_id, summary_text, summary_type, model_name)
               VALUES (?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()), summary.recording_id,
                summary.summary_text, summary.summary_type, summary.model_name,
            ),
        )
        self.conn.commit()

    def get_summaries(self, recording_id: str) -> list[Summary]:
        rows = self.conn.execute(
            "SELECT * FROM summaries WHERE recording_id = ?",
            (recording_id,),
        ).fetchall()
        return [
            Summary(
                recording_id=r["recording_id"],
                summary_text=r["summary_text"],
                summary_type=r["summary_type"],
                model_name=r["model_name"],
            )
            for r in rows
        ]

    # --- Queries ---

    def insert_query(self, question: str, answer: str,
                     recording_ids: list[str] | None = None,
                     model_name: str | None = None) -> None:
        import json
        self.conn.execute(
            """INSERT INTO queries (id, question, answer, recording_ids_json, model_name)
               VALUES (?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()), question, answer,
                json.dumps(recording_ids) if recording_ids else None,
                model_name,
            ),
        )
        self.conn.commit()

    # --- Search ---

    def search_transcripts(self, query: str, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            """SELECT t.recording_id, r.filename, r.recorded_at,
                      snippet(transcripts_fts, 0, '**', '**', '...', 32) AS snippet,
                      rank
               FROM transcripts_fts
               JOIN transcripts t ON t.rowid = transcripts_fts.rowid
               JOIN recordings r ON r.id = t.recording_id
               WHERE transcripts_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (query, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def search_summaries(self, query: str, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            """SELECT s.recording_id, r.filename, r.recorded_at,
                      snippet(summaries_fts, 0, '**', '**', '...', 32) AS snippet,
                      rank
               FROM summaries_fts
               JOIN summaries s ON s.rowid = summaries_fts.rowid
               JOIN recordings r ON r.id = s.recording_id
               WHERE summaries_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (query, limit),
        ).fetchall()
        return [dict(r) for r in rows]
