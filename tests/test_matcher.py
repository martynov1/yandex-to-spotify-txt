from __future__ import annotations

from yandex_to_spotify.matcher import ISRC_SCORE, find_best_match
from yandex_to_spotify.models import Track


def _candidate(
    id_: str,
    name: str,
    artists: list[str],
    duration_ms: int | None = None,
) -> dict:
    return {
        "id": id_,
        "uri": f"spotify:track:{id_}",
        "name": name,
        "artists": [{"name": a} for a in artists],
        "duration_ms": duration_ms,
    }


class FakeSpotify:
    """Minimal stand-in for SpotifyClient.search_track_candidates."""

    def __init__(self, responses: dict[str, list[dict]]):
        self._responses = responses
        self.queries: list[str] = []

    def search_track_candidates(self, query: str, limit: int = 5) -> list[dict]:
        self.queries.append(query)
        return self._responses.get(query, [])[:limit]


def test_isrc_match_short_circuits_fuzzy_search() -> None:
    track = Track(
        title="Some Song",
        artists=("Artist",),
        duration_ms=180_000,
        isrc="USRC17607839",
    )
    spotify = FakeSpotify(
        {"isrc:USRC17607839": [_candidate("abc", "Some Song", ["Artist"], 180_000)]}
    )

    result = find_best_match(spotify, track)

    assert result is not None
    assert result.score == ISRC_SCORE
    assert result.uri == "spotify:track:abc"
    # No fuzzy searches should be issued once ISRC hits.
    assert spotify.queries == ["isrc:USRC17607839"]


def test_isrc_miss_falls_back_to_fuzzy() -> None:
    track = Track(title="Hello", artists=("Adele",), isrc="MISSING")
    spotify = FakeSpotify(
        {
            "isrc:MISSING": [],
            'track:"Hello" artist:"Adele"': [_candidate("xyz", "Hello", ["Adele"])],
        }
    )

    result = find_best_match(spotify, track)

    assert result is not None
    assert result.uri == "spotify:track:xyz"
    # ISRC lookup was attempted (empty response) before falling back to fuzzy queries.
    assert spotify.queries[0] == "isrc:MISSING"
    assert len(spotify.queries) > 1


def test_below_threshold_returns_none() -> None:
    track = Track(title="Hello", artists=("Adele",))
    spotify = FakeSpotify(
        {
            'track:"Hello" artist:"Adele"': [
                _candidate("nope", "Completely Different", ["Stranger"])
            ],
        }
    )

    result = find_best_match(spotify, track, threshold=0.9)

    assert result is None


def test_noise_in_title_is_normalized() -> None:
    track = Track(title="Yesterday (Remastered 2009)", artists=("The Beatles",))
    spotify = FakeSpotify(
        {
            'track:"Yesterday (Remastered 2009)" artist:"The Beatles"': [
                _candidate("y1", "Yesterday", ["The Beatles"], 125_000)
            ]
        }
    )

    result = find_best_match(spotify, track)

    assert result is not None
    assert result.score >= 0.9


def test_duration_bonus_picks_correct_version() -> None:
    track = Track(title="Song", artists=("Band",), duration_ms=200_000)
    candidates = [
        _candidate("studio", "Song", ["Band"], 201_000),
        _candidate("live", "Song", ["Band"], 320_000),
    ]
    spotify = FakeSpotify({'track:"Song" artist:"Band"': candidates})

    result = find_best_match(spotify, track)

    assert result is not None
    assert result.uri == "spotify:track:studio"
