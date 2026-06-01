from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from yandex_to_spotify.models import Track
from yandex_to_spotify.spotify_client import SpotifyClient

# Strip suffixes like "(feat. X)", "(Original Mix)", "[Remastered 2011]" before matching.
_NOISE_RE = re.compile(
    r"\s*[\(\[][^)\]]*(feat\.?|ft\.?|with|prod\.?|remaster|remastered|original mix|version|edit)[^)\]]*[\)\]]",
    re.IGNORECASE,
)
_WS_RE = re.compile(r"\s+")

# Score assigned to an ISRC hit — bypasses fuzzy logic when Spotify returns a result.
ISRC_SCORE = 1.0


@dataclass(frozen=True)
class MatchResult:
    candidate: dict
    score: float

    @property
    def uri(self) -> str:
        return self.candidate["uri"]


def _normalize(text: str) -> str:
    text = _NOISE_RE.sub("", text)
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return _WS_RE.sub(" ", text).strip()


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _score_candidate(track: Track, candidate: dict) -> float:
    cand_title = candidate.get("name", "")
    cand_artists = ", ".join(a["name"] for a in candidate.get("artists", []))

    title_sim = _similarity(track.title, cand_title)
    artist_sim = _similarity(track.artists_str, cand_artists)
    score = 0.6 * title_sim + 0.4 * artist_sim

    if track.duration_ms and candidate.get("duration_ms"):
        diff = abs(track.duration_ms - candidate["duration_ms"])
        if diff < 3000:
            score += 0.05
        elif diff > 15000:
            score -= 0.1
    return score


def _isrc_lookup(client: SpotifyClient, isrc: str) -> dict | None:
    for cand in client.search_track_candidates(f"isrc:{isrc}", limit=1):
        return cand
    return None


def find_best_match(
    client: SpotifyClient, track: Track, threshold: float = 0.6
) -> MatchResult | None:
    if track.isrc:
        hit = _isrc_lookup(client, track.isrc)
        if hit:
            return MatchResult(candidate=hit, score=ISRC_SCORE)

    primary_artist = track.artists[0] if track.artists else ""
    queries = [
        f'track:"{track.title}" artist:"{primary_artist}"',
        f"{track.title} {primary_artist}",
        f"{track.title} {track.artists_str}",
    ]
    seen_ids: set[str] = set()
    best: MatchResult | None = None

    for q in queries:
        for cand in client.search_track_candidates(q, limit=5):
            cid = cand.get("id")
            if not cid or cid in seen_ids:
                continue
            seen_ids.add(cid)
            score = _score_candidate(track, cand)
            if best is None or score > best.score:
                best = MatchResult(candidate=cand, score=score)
        if best and best.score >= 0.9:
            break

    if best and best.score >= threshold:
        return best
    return None
