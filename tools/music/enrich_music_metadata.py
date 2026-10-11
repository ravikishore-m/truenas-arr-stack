#!/usr/bin/env python3
"""Enrich FLAC albums from MusicBrainz + iTunes Search (no Apple login).

Writes real provider IDs / covers / cleaned titles into tags so Jellyfin can
refresh like movies. Quality (Lossless / Hi-Res / Hi-Res Lossless) is derived
only from bit depth + sample rate — never from downloaded marketing artwork.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path

from mutagen.flac import FLAC, Picture

USER_AGENT = "truenas-arr-music-enricher/1.0 (home library; contact: local)"
MB_BASE = "https://musicbrainz.org/ws/2"
CAA_BASE = "https://coverartarchive.org"
ITUNES_BASE = "https://itunes.apple.com"
AUDIODB_BASE = "https://www.theaudiodb.com/api/v1/json/2"

QUALITY_BRACKET = re.compile(
    r"\s*\[(?:Hi-Res\s*Lossless|Hi-Res|Lossless)\]\s*",
    re.IGNORECASE,
)
YEAR_IN_NAME = re.compile(r"\s*[\(\[\{]?\s*((?:19|20)\d{2})\s*[\)\]\}]?\s*$")
INVALID_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_LAST = 0.0
MIN_GAP = 1.05


@dataclass
class Match:
    source: str
    album: str
    artist: str
    year: str = ""
    genre: str = ""
    mbid: str = ""
    release_group: str = ""
    itunes_id: str = ""
    cover_url: str = ""
    overview: str = ""


def throttle(gap: float = MIN_GAP) -> None:
    global _LAST
    wait = gap - (time.monotonic() - _LAST)
    if wait > 0:
        time.sleep(wait)
    _LAST = time.monotonic()


def get_json(url: str, timeout: int = 30) -> dict | list | None:
    throttle()
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def get_bytes(url: str, timeout: int = 45) -> bytes | None:
    throttle(0.4)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None


def first(audio: FLAC, key: str) -> str:
    vals = audio.get(key) or []
    return (vals[0] or "").strip() if vals else ""


def set_tag(audio: FLAC, key: str, value: str) -> bool:
    value = (value or "").strip()
    if not value:
        return False
    cur = first(audio, key)
    if cur == value:
        return False
    audio[key] = [value]
    return True


def quality_label(audio: FLAC) -> str:
    bits = int(getattr(audio.info, "bits_per_sample", 0) or 0)
    rate = int(getattr(audio.info, "sample_rate", 0) or 0)
    if bits >= 24 and rate > 48000:
        return "Hi-Res Lossless"
    if bits >= 24 or rate > 48000:
        return "Hi-Res"
    return "Lossless"


def strip_quality(name: str) -> str:
    return QUALITY_BRACKET.sub(" ", name or "").strip()


def clean_search_album(name: str) -> str:
    name = strip_quality(name)
    name = YEAR_IN_NAME.sub("", name)
    name = re.sub(r"\s*\((?:Original(?: Motion Picture)? Soundtrack|Original Score|OST)\)\s*", " ", name, flags=re.I)
    name = re.sub(r"\s+", " ", name).strip(" -_")
    return name


def clean_fs(value: str, fallback: str = "Unknown Album") -> str:
    value = unicodedata.normalize("NFC", value or "")
    value = INVALID_FS.sub("_", value)
    value = re.sub(r"\s+", " ", value).strip().rstrip(". ")
    return value[:180] or fallback


def album_seed(folder: Path) -> tuple[str, str, str, list[Path]]:
    tracks = sorted(folder.rglob("*.flac"))
    if not tracks:
        return "", "", "", []
    audio = FLAC(tracks[0])
    album = first(audio, "album") or strip_quality(folder.name)
    album = clean_search_album(album)
    artist = first(audio, "albumartist") or first(audio, "artist") or "Various Artists"
    year = ""
    date = first(audio, "date")
    if date:
        m = re.search(r"((?:19|20)\d{2})", date)
        if m:
            year = m.group(1)
    if not year:
        m = re.search(r"\((20\d{2}|19\d{2})\)", folder.name)
        if m:
            year = m.group(1)
    return album, artist, year, tracks


def score_title(candidate: str, target: str) -> int:
    a, b = (candidate or "").casefold(), (target or "").casefold()
    if not a or not b:
        return 0
    if a == b:
        return 5
    # Reject "Song (From \"Album\")" singles when we want the full album
    if "from \"" in a or "from “" in a or a.endswith(" - single") or " - single" in a:
        # only accept if target itself looks like a single
        if "single" not in b and "from " not in b:
            return 0
    if a in b or b in a:
        return 3
    at, bt = set(a.split()), set(b.split())
    if not at or not bt:
        return 0
    return int(3 * len(at & bt) / max(len(at), len(bt)))


def is_bad_album_match(matched_album: str, target_album: str) -> bool:
    m = (matched_album or "").casefold()
    t = (target_album or "").casefold()
    if not m or not t:
        return True
    if " - single" in m or m.endswith(" single"):
        return True
    if "from \"" in m or "from “" in m:
        return True
    # title must share meaningful overlap
    return score_title(matched_album, target_album) < 3


def search_musicbrainz(album: str, artist: str, year: str) -> Match | None:
    clauses = [f'release:"{album.replace(chr(34), "")}"']
    if artist and artist.casefold() not in {"unknown artist", "various artists", "va"}:
        clauses.append(f'artist:"{artist.replace(chr(34), "")}"')
    if year.isdigit():
        clauses.append(f"date:{year}")
    query = urllib.parse.quote(" AND ".join(clauses))
    data = get_json(f"{MB_BASE}/release/?query={query}&fmt=json&limit=8")
    if not isinstance(data, dict) or not data.get("releases"):
        query = urllib.parse.quote(f'release:"{album.replace(chr(34), "")}"')
        data = get_json(f"{MB_BASE}/release/?query={query}&fmt=json&limit=8")
    if not isinstance(data, dict):
        return None
    releases = data.get("releases") or []
    if not releases:
        return None

    def rank(entry: dict) -> tuple:
        title = entry.get("title") or ""
        credit = ""
        ac = entry.get("artist-credit") or []
        if ac:
            credit = ac[0].get("name") or ""
        date = entry.get("date") or ""
        ys = 2 if year and date.startswith(year) else 0
        return (score_title(title, album), score_title(credit, artist), ys, int(entry.get("score") or 0))

    best = max(releases, key=rank)
    if score_title(best.get("title") or "", album) < 3 and int(best.get("score") or 0) < 80:
        return None

    artist_name = artist
    ac = best.get("artist-credit") or []
    if ac:
        artist_name = ac[0].get("name") or artist
    date = best.get("date") or year
    y = re.search(r"((?:19|20)\d{2})", date)
    rg = ((best.get("release-group") or {}).get("id")) or ""
    tags = best.get("tags") or []
    genre = ""
    if tags:
        genre = max(tags, key=lambda t: t.get("count") or 0).get("name") or ""

    cover_url = ""
    mbid = best.get("id") or ""
    if mbid:
        caa = get_json(f"{CAA_BASE}/release/{mbid}")
        if isinstance(caa, dict):
            images = caa.get("images") or []
            front = next((i for i in images if i.get("front")), images[0] if images else None)
            if front:
                cover_url = front.get("image") or (front.get("thumbnails") or {}).get("large") or ""

    return Match(
        source="musicbrainz",
        album=best.get("title") or album,
        artist=artist_name,
        year=(y.group(1) if y else year),
        genre=genre,
        mbid=mbid,
        release_group=rg,
        cover_url=cover_url,
    )


def search_itunes(album: str, artist: str, year: str) -> Match | None:
    term = album
    if artist and artist.casefold() not in {"various artists", "va", "unknown artist"}:
        term = f"{album} {artist}"
    params = urllib.parse.urlencode(
        {"term": term, "entity": "album", "media": "music", "limit": 12, "country": "in"}
    )
    data = get_json(f"{ITUNES_BASE}/search?{params}")
    if not isinstance(data, dict):
        # retry without country bias
        params = urllib.parse.urlencode({"term": term, "entity": "album", "media": "music", "limit": 12})
        data = get_json(f"{ITUNES_BASE}/search?{params}")
    if not isinstance(data, dict):
        return None
    results = data.get("results") or []
    if not results:
        return None

    def rank(entry: dict) -> tuple:
        return (
            score_title(entry.get("collectionName") or "", album),
            score_title(entry.get("artistName") or "", artist),
            2 if year and str(entry.get("releaseDate") or "").startswith(year) else 0,
        )

    best = max(results, key=rank)
    if score_title(best.get("collectionName") or "", album) < 3:
        return None
    # Prefer full albums over tracks marketed as singles
    cname = best.get("collectionName") or ""
    if is_bad_album_match(cname, album):
        # try next-best non-single
        alts = sorted(results, key=rank, reverse=True)
        best = next((e for e in alts if not is_bad_album_match(e.get("collectionName") or "", album)), None)
        if not best:
            return None
        cname = best.get("collectionName") or ""
    date = best.get("releaseDate") or ""
    y = re.search(r"((?:19|20)\d{2})", date)
    art = best.get("artworkUrl100") or ""
    if art:
        art = re.sub(r"/\d+x\d+bb", "/1200x1200bb", art)
        art = art.replace("100x100bb", "1200x1200bb")
    return Match(
        source="itunes",
        album=cname or album,
        artist=best.get("artistName") or artist,
        year=(y.group(1) if y else year),
        genre=best.get("primaryGenreName") or "",
        itunes_id=str(best.get("collectionId") or ""),
        cover_url=art,
    )


def search_audiodb(album: str, artist: str) -> Match | None:
    if not album:
        return None
    q_album = urllib.parse.quote(album)
    q_artist = urllib.parse.quote(artist or "")
    data = None
    if artist and artist.casefold() not in {"various artists", "va"}:
        data = get_json(f"{AUDIODB_BASE}/searchalbum.php?s={q_artist}&a={q_album}")
    if not isinstance(data, dict) or not data.get("album"):
        data = get_json(f"{AUDIODB_BASE}/searchalbum.php?a={q_album}")
    if not isinstance(data, dict):
        return None
    albums = data.get("album") or []
    if not albums:
        return None
    best = max(
        albums,
        key=lambda e: (
            score_title(e.get("strAlbum") or "", album),
            score_title(e.get("strArtist") or "", artist),
        ),
    )
    if score_title(best.get("strAlbum") or "", album) < 3:
        return None
    return Match(
        source="audiodb",
        album=best.get("strAlbum") or album,
        artist=best.get("strArtist") or artist,
        year=str(best.get("intYearReleased") or ""),
        genre=best.get("strGenre") or "",
        overview=(best.get("strDescriptionEN") or "")[:2000],
        cover_url=best.get("strAlbumThumb") or best.get("strAlbumCDart") or "",
    )


def resolve_match(album: str, artist: str, year: str) -> Match | None:
    mb = search_musicbrainz(album, artist, year)
    it = search_itunes(album, artist, year)
    adb = search_audiodb(album, artist)

    candidates = [m for m in (mb, it, adb) if m and not is_bad_album_match(m.album, album)]
    if not candidates:
        return None
    # Prefer MusicBrainz, then iTunes, then AudioDB among good matches
    order = {"musicbrainz": 0, "itunes": 1, "audiodb": 2}
    primary = sorted(candidates, key=lambda m: (order.get(m.source, 9), -score_title(m.album, album)))[0]

    # Merge cover / overview / ids from siblings
    for other in candidates:
        if other is primary:
            continue
        if not primary.cover_url and other.cover_url:
            primary.cover_url = other.cover_url
        if not primary.genre and other.genre:
            primary.genre = other.genre
        if not primary.itunes_id and other.itunes_id:
            primary.itunes_id = other.itunes_id
        if not primary.overview and other.overview:
            primary.overview = other.overview
        if not primary.year and other.year:
            primary.year = other.year
        if not primary.mbid and other.mbid:
            primary.mbid = other.mbid
            primary.release_group = other.release_group
    return primary


def embed_cover(audio: FLAC, data: bytes, mime: str = "image/jpeg") -> None:
    pic = Picture()
    pic.type = 3
    pic.mime = mime
    pic.desc = "Cover"
    pic.data = data
    audio.clear_pictures()
    audio.add_picture(pic)


def apply_to_album(
    folder: Path,
    match: Match | None,
    tracks: list[Path],
    dry_run: bool,
    *,
    rename: bool = True,
) -> dict:
    album, artist, year, _ = album_seed(folder)
    result = {
        "folder": str(folder),
        "search_album": album,
        "search_artist": artist,
        "matched": bool(match),
        "source": match.source if match else None,
        "tracks": len(tracks),
        "changed_tracks": 0,
        "cover": False,
        "renamed_to": None,
    }
    if not tracks:
        return result

    cover_bytes = None
    cover_mime = "image/jpeg"
    if match and match.cover_url and not dry_run:
        raw = get_bytes(match.cover_url)
        if raw and len(raw) > 1000:
            cover_bytes = raw
            if match.cover_url.lower().endswith(".png"):
                cover_mime = "image/png"
            result["cover"] = True
            try:
                if cover_mime == "image/png":
                    (folder / "cover.png").write_bytes(cover_bytes)
                else:
                    (folder / "cover.jpg").write_bytes(cover_bytes)
                    (folder / "folder.jpg").write_bytes(cover_bytes)
            except OSError as exc:
                result["cover_error"] = str(exc)

    display_album = clean_search_album((match.album if match else album) or album)
    display_artist = (match.artist if match else artist) or artist
    display_year = (match.year if match else year) or year
    display_genre = (match.genre if match else "") or ""

    for path in tracks:
        audio = FLAC(path)
        changed = False
        q = quality_label(audio)
        changed |= set_tag(audio, "quality", q)
        # Keep technical fields for players / future UI
        bits = getattr(audio.info, "bits_per_sample", "?")
        rate = getattr(audio.info, "sample_rate", "?")
        changed |= set_tag(audio, "encodedby", f"{bits}bit/{rate}Hz")

        if match:
            changed |= set_tag(audio, "album", display_album)
            if display_artist:
                changed |= set_tag(audio, "albumartist", display_artist)
            if display_year:
                changed |= set_tag(audio, "date", display_year)
            if display_genre:
                changed |= set_tag(audio, "genre", display_genre)
            if match.mbid:
                changed |= set_tag(audio, "musicbrainz_albumid", match.mbid)
            if match.release_group:
                changed |= set_tag(audio, "musicbrainz_releasegroupid", match.release_group)
            if match.itunes_id:
                changed |= set_tag(audio, "comment", f"itunes:album:{match.itunes_id}")
            if match.overview:
                # Vorbis description / album description for some scrapers
                changed |= set_tag(audio, "description", match.overview[:4000])

        # Always strip quality brackets from album tag if present
        cur_album = first(audio, "album")
        cleaned = strip_quality(cur_album)
        if cleaned and cleaned != cur_album:
            changed |= set_tag(audio, "album", cleaned)
            display_album = cleaned

        if cover_bytes is not None:
            embed_cover(audio, cover_bytes, cover_mime)
            changed = True

        if changed and not dry_run:
            audio.save()
            result["changed_tracks"] += 1

    result["final_album"] = display_album
    result["final_artist"] = display_artist
    try:
        result["quality_sample"] = quality_label(FLAC(tracks[0]))
    except Exception as exc:
        result["quality_sample"] = f"error:{exc}"

    # Rename folder last: Album (Year) without [Hi-Res] (paths above stay valid until here)
    # Keep original title when online match is a different work / single.
    # Default cron uses --no-rename so Jellyfin paths are never moved under it.
    rename_album = display_album
    if match and is_bad_album_match(match.album, album):
        rename_album = album
    if not dry_run and rename and rename_album:
        new_name = clean_fs(rename_album)
        # Prefer local year over remaster year when they disagree a lot
        use_year = display_year
        if year and display_year and year != display_year:
            use_year = year
        if use_year:
            new_name = f"{new_name} ({use_year})"
        dest = folder.parent / new_name
        if dest != folder and not dest.exists():
            try:
                folder.rename(dest)
                result["renamed_to"] = str(dest)
            except OSError as exc:
                result["rename_error"] = str(exc)

    if match:
        result["match"] = asdict(match)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--library", default="/mnt/Skyhawk_8TB_HDD/Media/Music/Flac")
    ap.add_argument("--report", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-rename", action="store_true", help="Tag/cover only; do not rename album folders")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="", help="Substring filter on folder name")
    ap.add_argument("--skip-jellyfin-refresh", action="store_true")
    args = ap.parse_args()

    root = Path(args.library)
    albums = sorted(p for p in root.iterdir() if p.is_dir() and p.name != "_Needs Review")
    if args.only:
        albums = [p for p in albums if args.only.casefold() in p.name.casefold()]
    if args.limit:
        albums = albums[: args.limit]

    report = {"albums": [], "matched": 0, "unmatched": 0, "covers": 0}
    for folder in albums:
        album, artist, year, tracks = album_seed(folder)
        if not tracks:
            continue
        print(f"→ {folder.name}  search={album!r} / {artist!r}", flush=True)
        match = resolve_match(album, artist, year)
        if match:
            print(f"  ✓ {match.source}: {match.album} — {match.artist} ({match.year})", flush=True)
            report["matched"] += 1
        else:
            print("  ✗ no online match — tagging quality only", flush=True)
            report["unmatched"] += 1
        try:
            row = apply_to_album(
                folder, match, tracks, args.dry_run, rename=not args.no_rename
            )
        except Exception as exc:
            print(f"  !! failed: {exc}", flush=True)
            report["albums"].append(
                {"folder": str(folder), "error": str(exc), "matched": bool(match)}
            )
            continue
        if row.get("cover"):
            report["covers"] += 1
        report["albums"].append(row)

    report["total"] = len(report["albums"])
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
        print(f"report → {args.report}")
    print(json.dumps({k: report[k] for k in ("total", "matched", "unmatched", "covers")}, indent=2))

    # Kick Jellyfin Music library refresh so ProviderIds / art / titles pick up
    if not args.dry_run and not args.skip_jellyfin_refresh:
        try:
            refresh_jellyfin_music()
        except Exception as exc:
            print(f"jellyfin refresh skipped: {exc}")


def refresh_jellyfin_music() -> None:
    key = os.environ.get("JELLYFIN_API_KEY", "5b31ef3410314d5e9f22afcb446ac856")
    base = os.environ.get("JELLYFIN_URL", "http://127.0.0.1:30013")
    headers = {"Authorization": f'MediaBrowser Token="{key}"'}
    req = urllib.request.Request(f"{base}/Library/VirtualFolders", headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        libs = json.loads(resp.read().decode())
    music = next((l for l in libs if (l.get("Name") or "").lower() == "music"), None)
    if not music:
        print("no Music library found")
        return
    iid = music["ItemId"]
    url = (
        f"{base}/Items/{iid}/Refresh?Recursive=true"
        "&ImageRefreshMode=FullRefresh&MetadataRefreshMode=FullRefresh"
        "&ReplaceAllImages=false&ReplaceAllMetadata=true"
    )
    req = urllib.request.Request(url, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        print("jellyfin music refresh", resp.status)


if __name__ == "__main__":
    main()

