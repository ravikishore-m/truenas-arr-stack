"""Fetch album cover art from Cover Art Archive via MusicBrainz search."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "truenas-arr-flac-organizer/1.0 (local library tool)"
MB_BASE = "https://musicbrainz.org/ws/2"
CAA_BASE = "https://coverartarchive.org"
_LAST_REQUEST = 0.0
MIN_INTERVAL = 1.1


def _throttle() -> None:
    global _LAST_REQUEST
    wait = MIN_INTERVAL - (time.monotonic() - _LAST_REQUEST)
    if wait > 0:
        time.sleep(wait)
    _LAST_REQUEST = time.monotonic()


def _get_json(url: str) -> dict | list | None:
    _throttle()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None


def _get_bytes(url: str) -> bytes | None:
    _throttle()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return response.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None


def _escape_lucene(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def search_release_mbid(album: str, artist: str, year: str = "") -> str | None:
    album = album.strip()
    artist = artist.strip()
    if not album:
        return None

    clauses = [f'release:"{_escape_lucene(album)}"']
    if artist and artist.casefold() not in {"unknown artist", "various artists"}:
        clauses.append(f'artist:"{_escape_lucene(artist)}"')
    if year and year.isdigit():
        clauses.append(f"date:{year}")

    query = urllib.parse.quote(" AND ".join(clauses))
    payload = _get_json(f"{MB_BASE}/release/?query={query}&fmt=json&limit=5")
    if not isinstance(payload, dict):
        return None

    releases = payload.get("releases") or []
    if not releases:
        if artist:
            fallback_query = urllib.parse.quote(f'release:"{_escape_lucene(album)}"')
            payload = _get_json(f"{MB_BASE}/release/?query={fallback_query}&fmt=json&limit=5")
            if isinstance(payload, dict):
                releases = payload.get("releases") or []
    if not releases:
        return None

    def score(entry: dict) -> tuple[int, int]:
        title = (entry.get("title") or "").casefold()
        target = album.casefold()
        title_score = 2 if title == target else (1 if target in title or title in target else 0)
        year_score = 0
        if year.isdigit():
            entry_date = entry.get("date") or ""
            year_score = 2 if entry_date.startswith(year) else 0
        return (title_score, year_score)

    best = max(releases, key=score)
    return best.get("id")


def fetch_cover_bytes(album: str, artist: str, year: str = "") -> tuple[bytes, str] | None:
    mbid = search_release_mbid(album, artist, year)
    if not mbid:
        return None

    meta = _get_json(f"{CAA_BASE}/release/{mbid}")
    if not isinstance(meta, dict):
        return None

    images = meta.get("images") or []
    front = next((image for image in images if image.get("front")), None)
    if not front:
        front = images[0] if images else None
    if not front:
        return None

    image_url = front.get("image") or front.get("thumbnails", {}).get("large")
    if not image_url:
        return None

    data = _get_bytes(image_url)
    if not data:
        return None

    mime = (front.get("types") or [""])[0]
    suffix = ".png" if "png" in image_url.lower() or mime == "image/png" else ".jpg"
    return data, suffix
