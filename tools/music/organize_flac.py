#!/usr/bin/env python3
"""Safely organize a FLAC library in place from embedded metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from mutagen.flac import FLAC, Picture


INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
YEAR = re.compile(r"(?:19|20)\d{2}")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def clean_name(value: str, fallback: str) -> str:
    value = unicodedata.normalize("NFC", value).strip()
    value = INVALID_CHARS.sub("_", value)
    value = re.sub(r"\s+", " ", value).rstrip(". ")
    return value[:180] or fallback


def first(audio: FLAC, key: str) -> str:
    values = audio.get(key, [])
    return values[0].strip() if values else ""


def number(value: str) -> int | None:
    match = re.match(r"\s*(\d+)", value)
    return int(match.group(1)) if match else None


def picture_suffix(picture: Picture) -> str:
    mime = picture.mime.lower()
    if "png" in mime or picture.data.startswith(b"\x89PNG"):
        return ".png"
    return ".jpg"


def picture_score(picture: Picture) -> tuple[int, int, int]:
    return (
        1 if picture.type == 3 else 0,
        picture.width * picture.height,
        len(picture.data),
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 10_000):
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Unable to choose a unique path for {path}")


@dataclass
class Track:
    source: Path
    original_parent: Path
    audio: FLAC
    album: str
    year: str
    title: str
    track: int
    disc: int
    album_artist: str

    @property
    def album_key(self) -> tuple[str, str]:
        return (self.album.casefold(), self.year)


def move_preserving(source: Path, destination: Path, apply: bool) -> None:
    if source == destination:
        return
    if apply:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    review = root / "_Needs Review"
    flac_paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() == ".flac"
        and review not in path.parents
    )

    tracks: list[Track] = []
    actions: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    best_picture: dict[tuple[str, str], Picture] = {}
    external_pictures: dict[Path, list[Path]] = defaultdict(list)

    for path in root.rglob("*"):
        if (
            path.is_file()
            and review not in path.parents
            and path.suffix.lower() in IMAGE_SUFFIXES
        ):
            external_pictures[path.parent].append(path)

    for source in flac_paths:
        relative = source.relative_to(root)
        if source.name.startswith("._"):
            destination = review / "System Junk" / relative
            actions.append({"action": "move_sidecar", "from": str(source), "to": str(destination)})
            move_preserving(source, unique_path(destination), args.apply)
            counts["system_sidecars"] += 1
            continue

        try:
            audio = FLAC(source)
        except Exception as error:
            destination = review / "Corrupt or Invalid" / relative
            actions.append(
                {
                    "action": "move_invalid",
                    "from": str(source),
                    "to": str(destination),
                    "reason": str(error),
                }
            )
            move_preserving(source, unique_path(destination), args.apply)
            counts["invalid"] += 1
            continue

        album = first(audio, "album")
        title = first(audio, "title")
        track_number = number(first(audio, "tracknumber"))
        artist = first(audio, "artist")
        album_artist = first(audio, "albumartist") or artist
        missing = [
            name
            for name, value in (
                ("album", album),
                ("title", title),
                ("tracknumber", track_number),
                ("artist", artist),
            )
            if not value
        ]
        if missing:
            destination = review / "Missing Metadata" / relative
            actions.append(
                {
                    "action": "move_missing_metadata",
                    "from": str(source),
                    "to": str(destination),
                    "reason": ", ".join(missing),
                }
            )
            move_preserving(source, unique_path(destination), args.apply)
            counts["missing_metadata"] += 1
            continue

        date = first(audio, "date")
        year_match = YEAR.search(date)
        year = year_match.group(0) if year_match else ""
        disc = number(first(audio, "discnumber")) or 1
        album_name = clean_name(album, "Unknown Album")
        folder_name = f"{album_name} ({year})" if year else album_name
        prefix = f"{disc}-{track_number:02d}" if disc > 1 else f"{track_number:02d}"
        filename = clean_name(f"{prefix} - {title}", f"{prefix} - Unknown Title") + ".flac"

        track = Track(
            source=source,
            original_parent=source.parent,
            audio=audio,
            album=album,
            year=year,
            title=title,
            track=track_number,
            disc=disc,
            album_artist=album_artist,
        )
        tracks.append(track)
        counts["valid"] += 1

        for picture in audio.pictures:
            current = best_picture.get(track.album_key)
            if current is None or picture_score(picture) > picture_score(current):
                best_picture[track.album_key] = picture

        track.destination = root / folder_name / filename  # type: ignore[attr-defined]

    destinations: dict[Path, list[Track]] = defaultdict(list)
    for track in tracks:
        destinations[track.destination].append(track)  # type: ignore[attr-defined]
    primary_for_destination = {
        destination: sorted(
            group,
            key=lambda item: (
                item.source.parent == root,
                0 if item.audio.pictures else 1,
                str(item.source).casefold(),
            ),
        )[0]
        for destination, group in destinations.items()
    }

    clean_tracks: list[Track] = []
    for track in tracks:
        destination: Path = track.destination  # type: ignore[attr-defined]
        reason = ""
        if (
            len(destinations[destination]) > 1
            and track is not primary_for_destination[destination]
        ):
            reason = "multiple tracks map to the same filename"
        elif destination.exists() and destination != track.source:
            same = (
                destination.stat().st_size == track.source.stat().st_size
                and sha256(destination) == sha256(track.source)
            )
            reason = "duplicate of existing destination" if same else "destination already exists"

        if reason:
            relative = track.source.relative_to(root)
            destination = review / "Collisions and Duplicates" / relative
            actions.append(
                {
                    "action": "move_collision",
                    "from": str(track.source),
                    "to": str(destination),
                    "reason": reason,
                }
            )
            move_preserving(track.source, unique_path(destination), args.apply)
            counts["collisions"] += 1
            continue

        actions.append(
            {"action": "organize", "from": str(track.source), "to": str(destination)}
        )
        move_preserving(track.source, destination, args.apply)
        track.source = destination
        clean_tracks.append(track)
        counts["organized"] += 1

    albums: dict[tuple[str, str], list[Track]] = defaultdict(list)
    for track in clean_tracks:
        albums[track.album_key].append(track)

    for album_key, album_tracks in albums.items():
        album_dir = album_tracks[0].source.parent
        picture = best_picture.get(album_key)

        if picture is None:
            candidates: list[Path] = []
            for track in album_tracks:
                candidates.extend(external_pictures.get(track.original_parent, []))
            if candidates:
                preferred = sorted(
                    candidates,
                    key=lambda path: (
                        0 if path.stem.casefold() in {"cover", "folder", "front"} else 1,
                        path.name.casefold(),
                    ),
                )[0]
                suffix = ".png" if preferred.suffix.lower() == ".png" else ".jpg"
                cover = album_dir / f"cover{suffix}"
                if args.apply and preferred.resolve() != cover.resolve() and not cover.exists():
                    shutil.copy2(preferred, cover)
                counts["covers_from_external"] += 1
                actions.append(
                    {"action": "cache_external_cover", "from": str(preferred), "to": str(cover)}
                )
            else:
                counts["albums_missing_art"] += 1
            continue

        suffix = picture_suffix(picture)
        cover = album_dir / f"cover{suffix}"
        if args.apply and not cover.exists():
            cover.write_bytes(picture.data)
        counts["covers_from_embedded"] += 1
        actions.append({"action": "cache_embedded_cover", "to": str(cover)})

        for track in album_tracks:
            if track.audio.pictures:
                continue
            if args.apply:
                refreshed = FLAC(track.source)
                refreshed.add_picture(picture)
                refreshed.save()
            counts["tracks_art_embedded"] += 1
            actions.append({"action": "embed_album_cover", "to": str(track.source)})

    report = {
        "mode": "apply" if args.apply else "dry-run",
        "root": str(root),
        "counts": dict(sorted(counts.items())),
        "actions": actions,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report["counts"], indent=2))
    print(f"Report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
