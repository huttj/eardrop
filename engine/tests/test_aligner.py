from eardrop.aligner import align, group_into_utterances
from eardrop.models import DiarizationSegment, Word


def _make_words(*specs: tuple[str, float, float]) -> list[Word]:
    return [Word(word=w, start=s, end=e) for w, s, e in specs]


def _make_segments(*specs: tuple[float, float, str]) -> list[DiarizationSegment]:
    return [DiarizationSegment(start=s, end=e, speaker=sp) for s, e, sp in specs]


def test_basic_alignment():
    words = _make_words(
        ("Hello", 0.0, 0.5),
        ("world", 0.6, 1.0),
        ("how", 2.0, 2.3),
        ("are", 2.4, 2.6),
        ("you", 2.7, 3.0),
    )
    segments = _make_segments(
        (0.0, 1.5, "SPEAKER_00"),
        (1.8, 3.5, "SPEAKER_01"),
    )

    result = align(words, segments)

    assert result[0].speaker == "SPEAKER_00"
    assert result[1].speaker == "SPEAKER_00"
    assert result[2].speaker == "SPEAKER_01"
    assert result[3].speaker == "SPEAKER_01"
    assert result[4].speaker == "SPEAKER_01"


def test_no_segments_assigns_single_speaker():
    words = _make_words(("Hello", 0.0, 0.5), ("world", 0.6, 1.0))
    result = align(words, [])
    assert all(w.speaker == "SPEAKER_00" for w in result)


def test_word_in_gap_assigned_to_nearest():
    words = _make_words(("gap", 1.5, 1.8))
    segments = _make_segments(
        (0.0, 1.0, "SPEAKER_00"),
        (2.0, 3.0, "SPEAKER_01"),
    )
    result = align(words, segments)
    # Midpoint 1.65 is closer to SPEAKER_00 end (1.0) than SPEAKER_01 start (2.0)
    # Distance to SPEAKER_00: |1.65 - 1.0| = 0.65
    # Distance to SPEAKER_01: |2.0 - 1.65| = 0.35
    assert result[0].speaker == "SPEAKER_01"


def test_word_before_all_segments():
    words = _make_words(("early", 0.0, 0.3))
    segments = _make_segments((1.0, 2.0, "SPEAKER_00"),)
    result = align(words, segments)
    assert result[0].speaker == "SPEAKER_00"


def test_group_into_utterances_basic():
    words = [
        Word("Hello", 0.0, 0.5, "A"),
        Word("world", 0.6, 1.0, "A"),
        Word("Hi", 1.5, 1.8, "B"),
        Word("there", 1.9, 2.2, "B"),
    ]
    utterances = group_into_utterances(words)

    assert len(utterances) == 2
    assert utterances[0].speaker == "A"
    assert utterances[0].text == "Hello world"
    assert utterances[0].start == 0.0
    assert utterances[0].end == 1.0
    assert utterances[1].speaker == "B"
    assert utterances[1].text == "Hi there"


def test_group_into_utterances_alternating():
    words = [
        Word("a", 0.0, 0.5, "A"),
        Word("b", 0.6, 1.0, "B"),
        Word("c", 1.1, 1.5, "A"),
    ]
    utterances = group_into_utterances(words)
    assert len(utterances) == 3


def test_group_into_utterances_empty():
    assert group_into_utterances([]) == []
