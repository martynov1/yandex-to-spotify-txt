from __future__ import annotations

import spotipy
from spotipy.oauth2 import SpotifyOAuth

SCOPES = "playlist-modify-private playlist-modify-public user-read-private user-read-email"


class SpotifyClient:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, cache_path: str = ".spotify_cache"):
        if not (client_id and client_secret and redirect_uri):
            raise ValueError("Spotify credentials are not fully configured")
        auth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=SCOPES,
            cache_path=cache_path,
            open_browser=True,
        )
        self._sp = spotipy.Spotify(auth_manager=auth, requests_timeout=20, retries=3)
        self._user_id = self._sp.me()["id"]

    @property
    def user_id(self) -> str:
        return self._user_id

    def search_track(self, query: str) -> dict | None:
        result = self._sp.search(q=query, type="track", limit=5)
        items = result.get("tracks", {}).get("items", [])
        return items[0] if items else None

    def search_track_candidates(self, query: str, limit: int = 5) -> list[dict]:
        result = self._sp.search(q=query, type="track", limit=limit)
        return result.get("tracks", {}).get("items", []) or []

    def create_playlist(self, name: str, description: str | None = None, public: bool = False) -> str:
        playlist = self._sp.user_playlist_create(
            user=self._user_id,
            name=name,
            public=public,
            description=description or "",
        )
        return playlist["id"]

    def add_tracks(self, playlist_id: str, track_uris: list[str]) -> None:
        for i in range(0, len(track_uris), 100):
            chunk = track_uris[i : i + 100]
            self._sp.playlist_add_items(playlist_id, chunk)
