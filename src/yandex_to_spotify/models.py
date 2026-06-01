from dataclasses import dataclass, field


@dataclass(frozen=True)
class Track:
    title: str
    artists: tuple[str, ...]
    album: str | None = None
    duration_ms: int | None = None
    isrc: str | None = None

    @property
    def artists_str(self) -> str:
        return ", ".join(self.artists)

    def __str__(self) -> str:
        return f"{self.artists_str} — {self.title}"


@dataclass
class Playlist:
    title: str
    tracks: list[Track] = field(default_factory=list)
    description: str | None = None


@dataclass(frozen=True)
class PlaylistSummary:
    kind: str
    title: str
    track_count: int | None = None
