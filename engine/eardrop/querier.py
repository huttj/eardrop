from __future__ import annotations

import logging
from datetime import datetime, timedelta

from .config import Config
from .database import Database

log = logging.getLogger(__name__)

QUERY_PROMPT = (
    "You are a personal assistant with access to transcripts from the user's "
    "meetings and conversations. Answer the user's question based on the "
    "transcripts provided below. Be specific and reference details from the "
    "transcripts. If the information isn't in the transcripts, say so.\n\n"
    "{context}\n\n"
    "Question: {question}\n\n"
    "Answer:"
)


def _parse_time_range(question: str) -> tuple[datetime | None, datetime | None]:
    """Extract time range from natural language question."""
    now = datetime.now()
    q = question.lower()

    if "today" in q:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    elif "yesterday" in q:
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, end
    elif "this week" in q:
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    elif "last week" in q:
        this_monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        start = this_monday - timedelta(days=7)
        return start, this_monday
    elif "this month" in q:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, now

    return None, None


def _build_context(db: Database, question: str, max_transcripts: int = 10) -> tuple[str, list[str]]:
    """Build context from relevant transcripts for the LLM."""
    recording_ids: list[str] = []
    context_parts: list[str] = []

    # Try time-based filtering first
    start, end = _parse_time_range(question)
    if start and end:
        recordings = db.list_recordings_in_range(start, end)
        for rec in recordings[:max_transcripts]:
            transcript = db.get_transcript(rec.id)
            if transcript:
                recording_ids.append(rec.id)
                summaries = db.get_summaries(rec.id)
                summary_text = summaries[0].summary_text if summaries else ""
                context_parts.append(
                    f"--- Recording: {rec.filename} ({rec.recorded_at}) ---\n"
                    f"Summary: {summary_text}\n"
                    f"Transcript: {transcript.full_text[:2000]}\n"
                )

    # Also do FTS search for keyword relevance
    # Extract simple keywords (skip common question words)
    skip = {"what", "did", "do", "i", "my", "any", "the", "a", "an", "is", "are",
            "was", "were", "have", "has", "had", "this", "that", "week", "today",
            "yesterday", "month", "last", "how", "who", "where", "when", "why"}
    keywords = [w for w in question.lower().split() if w not in skip and len(w) > 2]

    if keywords:
        fts_query = " OR ".join(keywords)
        try:
            results = db.search_transcripts(fts_query, limit=max_transcripts)
            for r in results:
                rid = r["recording_id"]
                if rid not in recording_ids:
                    recording_ids.append(rid)
                    transcript = db.get_transcript(rid)
                    if transcript:
                        context_parts.append(
                            f"--- Recording: {r['filename']} ({r['recorded_at']}) ---\n"
                            f"Transcript excerpt: {r['snippet']}\n"
                        )
        except Exception:
            log.exception("FTS search failed")

    if not context_parts:
        # Fallback: use most recent recordings
        recent = db.list_recordings(status="complete", limit=5)
        for rec in recent:
            transcript = db.get_transcript(rec.id)
            if transcript:
                recording_ids.append(rec.id)
                context_parts.append(
                    f"--- Recording: {rec.filename} ({rec.recorded_at}) ---\n"
                    f"Transcript: {transcript.full_text[:1000]}\n"
                )

    return "\n".join(context_parts), recording_ids


def query(question: str, db: Database, config: Config) -> str:
    """Answer a natural language question using transcript corpus."""
    import ollama

    context, recording_ids = _build_context(db, question)

    if not context:
        return "No transcripts found to answer your question."

    prompt = QUERY_PROMPT.format(context=context, question=question)

    log.info("Querying with %d context recordings", len(recording_ids))

    client = ollama.Client(host=config.ollama_base_url)
    response = client.generate(
        model=config.ollama_model,
        prompt=prompt,
    )

    answer = response["response"].strip()

    # Store the query
    db.insert_query(question, answer, recording_ids, config.ollama_model)

    return answer
