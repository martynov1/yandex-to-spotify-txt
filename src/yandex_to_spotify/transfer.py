from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from yandex_to_spotify.matcher import MatchResult, find_best_match
from yandex_to_spotify.models import Playlist, Track
from yandex_to_spotify.spotify_client import SpotifyClient

# Matches in [threshold, REVIEW_SCORE) are accepted but flagged for manual review.
REVIEW_SCORE = 0.8

ProgressCallback = Callable[[int, int, Track], None]
LogCallback = Callable[[str], None]


@dataclass
class MatchedTrack:
    source: Track
    uri: str
    score: float
    spotify_title: str
    spotify_artists: str

    @property
    def needs_review(self) -> bool:
        return self.score < REVIEW_SCORE


@dataclass
class TransferReport:
    playlist_id: str | None
    matched: list[MatchedTrack] = field(default_factory=list)
    unmatched: list[Track] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.matched) + len(self.unmatched)

    @property
    def match_rate(self) -> float:
        return (len(self.matched) / self.total * 100) if self.total else 0.0

    @property
    def review(self) -> list[MatchedTrack]:
        return [m for m in self.matched if m.needs_review]


def _to_matched(track: Track, result: MatchResult) -> MatchedTrack:
    cand = result.candidate
    return MatchedTrack(
        source=track,
        uri=cand["uri"],
        score=result.score,
        spotify_title=cand.get("name", ""),
        spotify_artists=", ".join(a["name"] for a in cand.get("artists", [])),
    )


def match_tracks(
    spotify: SpotifyClient,
    playlist: Playlist,
    threshold: float = 0.6,
    on_progress: ProgressCallback | None = None,
) -> tuple[list[MatchedTrack], list[Track]]:
    matched: list[MatchedTrack] = []
    unmatched: list[Track] = []
    total = len(playlist.tracks)
    for i, track in enumerate(playlist.tracks, start=1):
        result = find_best_match(spotify, track, threshold=threshold)
        if result:
            matched.append(_to_matched(track, result))
        else:
            unmatched.append(track)
        if on_progress:
            on_progress(i, total, track)
    return matched, unmatched


def transfer_playlist(
    spotify: SpotifyClient,
    playlist: Playlist,
    *,
    new_name: str | None = None,
    public: bool = False,
    threshold: float = 0.6,
    dry_run: bool = False,
    on_progress: ProgressCallback | None = None,
    on_log: LogCallback | None = None,
) -> TransferReport:
    log = on_log or (lambda _msg: None)
    target_name = new_name or playlist.title

    matched, unmatched = match_tracks(spotify, playlist, threshold, on_progress)

    if dry_run:
        log(f"Dry-run: плейлист «{target_name}» не будет создан.")
        return TransferReport(playlist_id=None, matched=matched, unmatched=unmatched)

    description = playlist.description or "Imported from Yandex Music"
    log(f"Создаю плейлист в Spotify: {target_name}")
    playlist_id = spotify.create_playlist(target_name, description=description, public=public)

    if matched:
        log(f"Добавляю {len(matched)} треков в плейлист…")
        spotify.add_tracks(playlist_id, [m.uri for m in matched])

    return TransferReport(playlist_id=playlist_id, matched=matched, unmatched=unmatched)
