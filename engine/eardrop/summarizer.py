from __future__ import annotations

import logging

from .config import Config
from .models import Summary, Utterance

log = logging.getLogger(__name__)

PROMPT_TEMPLATES = {
    "general": (
        "You are summarizing a transcript of a conversation or meeting.\n"
        "Provide a concise summary covering the key topics discussed, "
        "decisions made, and any important context.\n\n"
        "Transcript:\n{transcript}\n\n"
        "Summary:"
    ),
    "action_items": (
        "You are reviewing a transcript of a conversation or meeting.\n"
        "Extract all action items, tasks, and TODOs mentioned. "
        "For each, note who is responsible if mentioned.\n\n"
        "Transcript:\n{transcript}\n\n"
        "Action items:"
    ),
    "key_points": (
        "You are reviewing a transcript of a conversation or meeting.\n"
        "List the key points and takeaways as concise bullet points.\n\n"
        "Transcript:\n{transcript}\n\n"
        "Key points:"
    ),
}


def _format_transcript(utterances: list[Utterance]) -> str:
    lines: list[str] = []
    for u in utterances:
        lines.append(f"[{u.speaker}]: {u.text}")
    return "\n".join(lines)


def summarize(
    recording_id: str,
    utterances: list[Utterance],
    config: Config,
    summary_type: str = "general",
) -> Summary:
    """Generate a summary of the transcript using Ollama."""
    import ollama

    transcript_text = _format_transcript(utterances)

    template = PROMPT_TEMPLATES.get(summary_type, PROMPT_TEMPLATES["general"])
    prompt = template.format(transcript=transcript_text)

    log.info("Generating %s summary for recording %s using %s",
             summary_type, recording_id, config.ollama_model)

    client = ollama.Client(host=config.ollama_base_url)
    response = client.generate(
        model=config.ollama_model,
        prompt=prompt,
    )

    summary_text = response["response"].strip()
    log.info("Generated summary (%d chars)", len(summary_text))

    return Summary(
        recording_id=recording_id,
        summary_text=summary_text,
        summary_type=summary_type,
        model_name=config.ollama_model,
    )


def summarize_all_types(
    recording_id: str,
    utterances: list[Utterance],
    config: Config,
) -> list[Summary]:
    """Generate all summary types for a recording."""
    summaries: list[Summary] = []
    for summary_type in PROMPT_TEMPLATES:
        try:
            s = summarize(recording_id, utterances, config, summary_type)
            summaries.append(s)
        except Exception:
            log.exception("Failed to generate %s summary", summary_type)
    return summaries
