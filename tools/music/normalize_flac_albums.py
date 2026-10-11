#!/usr/bin/env python3
"""Normalize a FLAC library to exactly `Album (Year)/Track - Title.flac`."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from cover_art_fetch import fetch_cover_bytes
from mutagen.flac import FLAC, Picture


YEAR = re.compile(r"(?:19|20)\d{2}")
ENCLOSED_YEAR = re.compile(r"[\(\[\{]\s*((?:19|20)\d{2})\s*[\)\]\}]")
INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
FROM_ALBUM = re.compile(r'\(\s*From\s+["“_]?(.+?)["”_]?\s*\)', re.IGNORECASE)
REVIEW = "_Needs Review"


@dataclass
class Track:
    source: Path
    audio: FLAC
    album: str
    year: str
    title: str
    artist: str
    track: int
    disc: int
    tags_changed: bool = False


def first(audio: FLAC, key: str) -> str:
    values = audio.get(key, [])
    return values[0].strip() if values else ""


def parse_number(value: str, fallback: int = 0) -> int:
    match = re.match(r"\s*(\d+)", value)
    return int(match.group(1)) if match else fallback


def filename_track(path: Path) -> int:
    match = re.match(r"\s*(\d+)", path.stem)
    return int(match.group(1)) if match else 0


def clean_fs(value: str, fallback: str) -> str:
    value = unicodedata.normalize("NFC", value)
    value = INVALID.sub("_", value)
    value = re.sub(r"\s+", " ", value).strip().rstrip(". ")
    return value[:180] or fallback


def clean_title(value: str) -> str:
    value = FROM_ALBUM.sub("", value)
    value = re.sub(r"\s*\[\s*TELUGU\s*\]\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*\{(?:Aata|Bunny|Vikramarkudu)\}\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(
        r"\s*\((?:Aata|Bunny|Vikramarkudu|Donga Donga|Gang Master|Super Police|Padma Vyuham|Duet|Master|Raakshasudu)\)\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\.{2,}\s*$", "", value)
    return re.sub(r"\s+", " ", value).strip(" -_")


def quality_label(audio: FLAC) -> str:
    """Apple-style label from the file's real bit depth and sample rate.

    Hi-Res Lossless: 24-bit and above 48 kHz.
    Hi-Res: 24-bit up to 48 kHz, or any file above 48 kHz.
    Lossless: CD and 16-bit up to 48 kHz.
    """
    info = audio.info
    bits = int(getattr(info, "bits_per_sample", 0) or 0)
    rate = int(getattr(info, "sample_rate", 0) or 0)
    if bits >= 24 and rate > 48000:
        return "Hi-Res Lossless"
    if bits >= 24 or rate > 48000:
        return "Hi-Res"
    return "Lossless"


def clean_album_name(value: str) -> str:
    value = value.replace("_", " ")
    value = FROM_ALBUM.sub(lambda match: match.group(1), value)
    value = re.sub(
        r"\s*\((?:Original Motion Picture Soundtrack|Original Score)\)\s*",
        " ",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\s*\((?:Deluxe Edition|Extended Version|Cinematic Edition|The Moonlight Edition)\)\s*",
        " ",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\s*-\s*(?:EP|Single|TELUGU)\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*\[\s*TELUGU\s*\]\s*", " ", value, flags=re.IGNORECASE)
    value = re.sub(
        r"\s*\(\s*(?:Telugu|Tamil|Hindi|Malayalam)\s*\)\s*",
        " ",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\s*-\s*(?:Telugu|Tamil|Hindi|Malayalam)(?=\s|$)", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*-\s*FLAC\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*-\s*(?:A2ZCity|TeluguWap)\.net\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*-\s*TamilWavMusicBox\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*\{[^{}]*(?:Music|CD|AMIL|SFCD|ACD|FLAC)[^{}]*\}\s*", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*\[[^\[\]]*(?:FLAC|bit|Hi-Res|AMAZON|ACD|Edition)[^\[\]]*\]\s*", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*\[\s*Bonus With [^\[\]]+\]\s*", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+CD[-\s]*\d+(?:/\d+)?\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*[/_-]\s*Mani Sharma\s*$", "", value, flags=re.IGNORECASE)
    value = ENCLOSED_YEAR.sub(" ", value)
    value = re.sub(r"\s+", " ", value).strip(" -_/")
    if value.casefold() == "2020 top hits":
        value = "Top Hits"
    return value


def album_year(album: str, date: str, fallback_path: Path) -> str:
    enclosed = ENCLOSED_YEAR.findall(album)
    if enclosed:
        return enclosed[0]
    path_years = ENCLOSED_YEAR.findall(" ".join(fallback_path.parts))
    if path_years:
        return path_years[0]
    match = YEAR.search(date)
    return match.group(0) if match else ""


def special_album(album: str, title: str, track: int) -> tuple[str, str, int] | None:
    folded = album.casefold()
    if "aata (2007)" in folded and "vikramarkudu" in folded:
        return ("Aata", "2007", track) if track <= 6 else ("Vikramarkudu", "2006", track - 6)
    if "antham (1992)" in folded and "gentleman" in folded:
        return "Gentleman", "1993", max(1, track - 6)
    if "bunny (2005)" in folded and "manmadha" in folded:
        return "Bunny", "2005", track
    if folded == "bunny - mass":
        return ("Bunny", "2005", track) if track <= 6 else ("Mass", "2004", track - 6)
    if "chanti (1992)" in folded and "dalapathi" in folded:
        return "Dalapathi", "1991", max(1, track - 8)
    if "hitler (1997)" in folded and "master (1997)" in folded:
        return "Master", "1997", max(1, track - 6)
    if "swathi muthyam" in folded and "raakshasudu" in folded:
        return "Raakshasudu", "1986", max(1, track - 8)
    if folded == "anaganaga oka roju - deyyam":
        return "Anaganaga Oka Roju", "1997", track
    if folded == "ayithe & little soldiers":
        return ("Ayithe", "2003", track) if track <= 6 else ("Little Soldiers", "1996", max(1, track - 9))
    if folded == "bharateeyudu - maina":
        return ("Bharateeyudu", "1996", track) if track <= 5 else ("Maina", "1992", track - 5)
    if folded.startswith("kshemamga velli labhamga randi - chala bagundhi"):
        return "Chala Bagundhi", "2000", max(1, track - 5)
    if folded.startswith("merupu kalalu - iddaru"):
        return "Merupu Kalalu", "1997", track
    if folded == "varsham - yuva":
        return ("Varsham", "2004", track) if track <= 6 else ("Yuva", "2004", track - 6)
    if folded.startswith("mukha mukhi & hits"):
        if track <= 6:
            return "Mukha Mukhi", "2000", track
        sources = {
            "donga donga": ("Donga Donga", "1993"),
            "gang master": ("Gang Master", "1994"),
            "super police": ("Super Police", "1994"),
            "padma vyuham": ("Padma Vyuham", "1992"),
            "duet": ("Duet", "1994"),
        }
        for marker, (name, year) in sources.items():
            if marker in title.casefold():
                local_track = 2 if marker == "donga donga" and track == 8 else 1
                return name, year, local_track
    return None


def infer_missing(path: Path, audio: FLAC) -> tuple[str, str, str, str, int]:
    relative = str(path).casefold()
    stem = path.stem
    track = filename_track(path) or parse_number(first(audio, "tracknumber"), 1)
    title = first(audio, "title")
    artist = first(audio, "artist")
    album = first(audio, "album")
    year = album_year(album, first(audio, "date"), path)

    known = [
        ("3 (2012)", "3", "2012"),
        ("a aa (2016)", "A Aa", "2016"),
        ("bhadra (2005)", "Bhadra", "2005"),
        ("indra (2002)", "Indra", "2002"),
        ("jeans (1998)", "Jeans", "1998"),
        ("manam (2014)", "Manam", "2014"),
        ("mukunda", "Mukunda", "2014"),
        ("sakuni (2012)", "Sakuni", "2012"),
        ("samara simha reddy", "Samarasimha Reddy", "1999"),
        ("thupakki", "Thuppakki", "2012"),
    ]
    for marker, known_album, known_year in known:
        if marker in relative:
            album, year = known_album, known_year
            break

    if not title:
        raw = re.sub(r"^\s*\d+\s*[-.]?\s*", "", stem)
        if " - " in raw:
            left, right = raw.rsplit(" - ", 1)
            if not artist and len(left) < 100:
                artist = left.replace("_", ", ")
            raw = right
        title = raw.strip(" -.").replace("_", " ")
    if not artist:
        artist = "Unknown Artist"
    return album, year, clean_title(title), artist, track


def unique_destination(path: Path, source: Path, reserved: set[Path]) -> Path:
    if path == source:
        reserved.add(path)
        return path
    if path not in reserved and not path.exists():
        reserved.add(path)
        return path
    for index in range(2, 10_000):
        candidate = path.with_name(f"{path.stem} (Duplicate {index}){path.suffix}")
        if candidate not in reserved and not candidate.exists():
            reserved.add(candidate)
            return candidate
    raise RuntimeError(f"Could not choose a unique destination for {path}")


def best_picture(tracks: list[Track]) -> Picture | None:
    pictures = [picture for track in tracks for picture in track.audio.pictures]
    if not pictures:
        return None
    return max(
        pictures,
        key=lambda picture: (
            picture.type == 3,
            picture.width * picture.height,
            len(picture.data),
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--fetch-covers-online",
        action="store_true",
        help="Download missing cover.jpg/png from Cover Art Archive (MusicBrainz)",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    review = root / REVIEW
    review_sources = [
        review / "Collisions and Duplicates",
        review / "Missing Metadata",
    ]
    paths = [
        path
        for path in root.rglob("*.flac")
        if not path.name.startswith("._") and review not in path.parents
    ]
    for source_root in review_sources:
        if source_root.exists():
            paths.extend(
                path
                for path in source_root.rglob("*.flac")
                if not path.name.startswith("._")
            )

    tracks: list[Track] = []
    counts: Counter[str] = Counter()
    actions: list[dict[str, str]] = []

    for path in sorted(set(paths)):
        try:
            audio = FLAC(path)
        except Exception as error:
            actions.append({"action": "skip_unreadable", "path": str(path), "reason": str(error)})
            counts["unreadable_skipped"] += 1
            continue

        album, year, title, artist, track_no = infer_missing(path, audio)
        disc = parse_number(first(audio, "discnumber"), 1)
        special = special_album(album, first(audio, "title") or path.stem, track_no)
        if special:
            album, year, track_no = special
        else:
            from_match = FROM_ALBUM.search(first(audio, "album"))
            if from_match:
                album = from_match.group(1)
            if not year:
                year = album_year(album, first(audio, "date"), path)

        cleaned_album = clean_album_name(album)
        if not cleaned_album:
            cleaned_album = "Unknown Album"
        if cleaned_album == "1989" and not year:
            year = "2014"
        if not year:
            year = "Unknown Year"
        quality = quality_label(audio)
        display_album = cleaned_album if quality == "Lossless" else f"{cleaned_album} [{quality}]"
        counts[f"quality_{quality.replace(' ', '_').lower()}"] += 1

        original_values = {
            "album": first(audio, "album"),
            "date": first(audio, "date"),
            "title": first(audio, "title"),
            "artist": first(audio, "artist"),
            "tracknumber": first(audio, "tracknumber"),
            "quality": first(audio, "quality"),
        }
        normalized_values = {
            "album": display_album,
            "date": year,
            "title": title,
            "artist": artist,
            "tracknumber": str(max(1, track_no)),
            "quality": quality,
        }
        existing_comment = first(audio, "comment")
        if not existing_comment or existing_comment in {"Lossless", "Hi-Res", "Hi-Res Lossless"}:
            normalized_values["comment"] = quality
        needs_repair = any(not original_values[key] for key in ("album", "date", "title", "artist", "tracknumber"))
        needs_special_update = special is not None or FROM_ALBUM.search(original_values["album"])
        tags_changed = needs_repair or bool(needs_special_update) or original_values["quality"] != quality

        tracks.append(
            Track(
                source=path,
                audio=audio,
                album=display_album,
                year=year,
                title=title,
                artist=artist,
                track=max(1, track_no),
                disc=disc,
                tags_changed=tags_changed,
            )
        )
        if tags_changed:
            counts["tags_repaired"] += 1
        if args.apply:
            for key, value in normalized_values.items():
                audio[key] = [value]
            audio.save()
            counts["tags_written"] += 1

    reserved: set[Path] = set()
    album_tracks: dict[Path, list[Track]] = defaultdict(list)
    for track in tracks:
        folder = root / clean_fs(f"{track.album} ({track.year})", "Unknown Album (Unknown Year)")
        prefix = f"{track.disc}-{track.track:02d}" if track.disc > 1 else f"{track.track:02d}"
        filename = clean_fs(f"{prefix} - {track.title}", f"{prefix} - Unknown Title") + ".flac"
        destination = unique_destination(folder / filename, track.source, reserved)
        album_tracks[folder].append(track)
        actions.append({"action": "organize", "from": str(track.source), "to": str(destination)})
        if track.source != destination:
            counts["files_moved"] += 1
            if args.apply:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(track.source), str(destination))
            track.source = destination

    for folder, folder_tracks in album_tracks.items():
        artists = {track.artist for track in folder_tracks}
        album_artist = next(iter(artists)) if len(artists) == 1 else "Various Artists"
        if args.apply:
            for track in folder_tracks:
                current = FLAC(track.source)
                if first(current, "albumartist") != album_artist:
                    current["albumartist"] = [album_artist]
                    current.save()
                    counts["albumartist_set"] += 1

        cover_jpg = folder / "cover.jpg"
        cover_png = folder / "cover.png"
        if cover_jpg.exists() or cover_png.exists():
            continue
        picture = best_picture(folder_tracks)
        cover_bytes: bytes | None = None
        suffix = ".jpg"
        source = "embedded"
        if picture:
            suffix = ".png" if "png" in picture.mime.lower() or picture.data.startswith(b"\x89PNG") else ".jpg"
            cover_bytes = picture.data
        elif args.fetch_covers_online:
            sample = folder_tracks[0]
            fetched = fetch_cover_bytes(sample.album, sample.artist, sample.year)
            if fetched:
                cover_bytes, suffix = fetched
                source = "cover_art_archive"

        if not cover_bytes:
            counts["albums_without_art"] += 1
            continue

        cover = folder / f"cover{suffix}"
        actions.append({"action": "create_cover_cache", "source": source, "to": str(cover)})
        counts["cover_caches_created"] += 1
        if source == "cover_art_archive":
            counts["covers_from_internet"] += 1
        if args.apply:
            folder.mkdir(parents=True, exist_ok=True)
            cover.write_bytes(cover_bytes)
            embed_picture = picture
            if embed_picture is None:
                embed_picture = Picture()
                embed_picture.type = 3
                embed_picture.mime = "image/png" if suffix == ".png" else "image/jpeg"
                embed_picture.desc = "Cover"
                embed_picture.data = cover_bytes
            for track in folder_tracks:
                if track.audio.pictures:
                    continue
                refreshed = FLAC(track.source)
                refreshed.add_picture(embed_picture)
                refreshed.save()
                counts["tracks_art_embedded"] += 1

    report = {
        "mode": "apply" if args.apply else "dry-run",
        "counts": dict(sorted(counts.items())),
        "actions": actions,
    }
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report["counts"], indent=2))
    print(f"Report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
