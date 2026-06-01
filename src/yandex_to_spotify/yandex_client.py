from __future__ import annotations

from yandex_music import Client
from yandex_music.exceptions import YandexMusicError

from yandex_to_spotify.models import Playlist, PlaylistSummary, Track


class YandexClient:
    def __init__(self, token: str):
        if not token:
            raise ValueError("YANDEX_MUSIC_TOKEN is empty")
        self._client = Client(token).init()

    def list_playlists(self) -> list[PlaylistSummary]:
        playlists = self._client.users_playlists_list()
        result: list[PlaylistSummary] = []
        for p in playlists:
            kind = str(p.kind)
            title = p.title or f"playlist-{kind}"
            count = getattr(p, "track_count", None)
            result.append(PlaylistSummary(kind=kind, title=title, track_count=count))
        liked = self._client.users_likes_tracks()
        if liked is not None:
            liked_count = len(getattr(liked, "tracks", []) or [])
            result.insert(
                0,
                PlaylistSummary(kind="liked", title="Мне нравится", track_count=liked_count or None),
            )
        return result

    def fetch_playlist(self, kind: str) -> Playlist:
        if kind == "liked":
            return self._fetch_liked()
        owner_uid = self._client.me.account.uid
        playlist = self._client.users_playlists(kind=int(kind), user_id=owner_uid)
        if isinstance(playlist, list):
            playlist = playlist[0]
        tracks = self._extract_tracks(playlist.tracks)
        return Playlist(
            title=playlist.title or f"playlist-{kind}",
            description=getattr(playlist, "description", None),
            tracks=tracks,
        )

    def _fetch_liked(self) -> Playlist:
        liked = self._client.users_likes_tracks()
        full_tracks = liked.fetch_tracks()
        tracks = [self._to_track(t) for t in full_tracks if t]
        return Playlist(title="Мне нравится (Yandex)", tracks=tracks)

    def _extract_tracks(self, track_shorts) -> list[Track]:
        ids = [f"{ts.id}:{ts.album_id}" if ts.album_id else str(ts.id) for ts in track_shorts]
        if not ids:
            return []
        try:
            full = self._client.tracks(ids)
        except YandexMusicError:
            full = [ts.fetch_track() for ts in track_shorts]
        return [self._to_track(t) for t in full if t]

    @staticmethod
    def _to_track(t) -> Track:
        artists = tuple(a.name for a in (t.artists or []) if a and a.name)
        album = None
        if t.albums:
            album = t.albums[0].title
        isrc = None
        # yandex-music exposes ISRC inconsistently across versions: sometimes on the
        # track itself, sometimes under .meta_data.
        raw_isrc = getattr(t, "isrc", None)
        if raw_isrc:
            isrc = raw_isrc
        else:
            meta = getattr(t, "meta_data", None)
            if meta is not None:
                isrc = getattr(meta, "isrc", None)
        return Track(
            title=t.title or "",
            artists=artists or ("Unknown",),
            album=album,
            duration_ms=t.duration_ms,
            isrc=isrc,
        )
