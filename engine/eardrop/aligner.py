from __future__ import annotations

import bisect
import logging

from .models import DiarizationSegment, Utterance, Word

log = logging.getLogger(__name__)


def align(words: list[Word], segments: list[DiarizationSegment]) -> list[Word]:
    """Assign speaker labels to words using midpoint-in-segment matching.

    For each word, computes its temporal midpoint and finds which diarization
    segment contains that midpoint. This is the standard WhisperX approach.
    """
    if not segments:
        # No diarization — assign all to single speaker
        for w in words:
            w.speaker = "SPEAKER_00"
        return words

    # Build sorted list of segment start times for binary search
    seg_starts = [s.start for s in segments]

    for w in words:
        midpoint = (w.start + w.end) / 2.0

        # Find the rightmost segment whose start <= midpoint
        idx = bisect.bisect_right(seg_starts, midpoint) - 1

        if idx >= 0 and segments[idx].start <= midpoint <= segments[idx].end:
            w.speaker = segments[idx].speaker
        elif idx >= 0:
            # Midpoint falls in a gap — assign to nearest segment
            nearest = _find_nearest_segment(midpoint, idx, segments)
            w.speaker = nearest.speaker
        else:
            # Before all segments
            w.speaker = segments[0].speaker

    assigned = sum(1 for w in words if w.speaker is not None)
    log.info("Aligned %d/%d words with speaker labels", assigned, len(words))
    return words


def _find_nearest_segment(
    midpoint: float, idx: int, segments: list[DiarizationSegment]
) -> DiarizationSegment:
    """Find the segment nearest to the midpoint when it falls in a gap."""
    best = segments[idx]
    best_dist = abs(midpoint - best.end)

    # Check the next segment too
    if idx + 1 < len(segments):
        next_seg = segments[idx + 1]
        next_dist = abs(next_seg.start - midpoint)
        if next_dist < best_dist:
            best = next_seg

    return best


def group_into_utterances(words: list[Word]) -> list[Utterance]:
    """Group consecutive words with the same speaker into utterances."""
    if not words:
        return []

    utterances: list[Utterance] = []
    current_speaker = words[0].speaker or "UNKNOWN"
    current_words: list[Word] = [words[0]]

    for w in words[1:]:
        speaker = w.speaker or "UNKNOWN"
        if speaker == current_speaker:
            current_words.append(w)
        else:
            utterances.append(_words_to_utterance(current_speaker, current_words))
            current_speaker = speaker
            current_words = [w]

    # Don't forget the last group
    utterances.append(_words_to_utterance(current_speaker, current_words))

    log.info("Grouped %d words into %d utterances", len(words), len(utterances))
    return utterances


def _words_to_utterance(speaker: str, words: list[Word]) -> Utterance:
    text = " ".join(w.word for w in words)
    return Utterance(
        speaker=speaker,
        start=words[0].start,
        end=words[-1].end,
        text=text,
    )
