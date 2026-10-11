#!/usr/bin/env python3
"""Extract finished Telegram downloads and organize them into the music library.

In-progress downloads are left alone. A file is extracted only after Telegram
marks it completed, the bytes on disk match, and the file has stopped growing.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HOST_DATA = Path("/mnt/WD_Black_1TB_SSD/configs/telegram-files")
CONTAINER_PREFIX = "/app/data"
INBOX = Path("/mnt/Skyhawk_8TB_HDD/Media/.music-inbox")
DUMP = Path("/mnt/Skyhawk_8TB_HDD/Media/Music/Telegram")
TOOLS = Path("/mnt/WD_Black_1TB_SSD/configs/flac-tools")
LEDGER_PATH = TOOLS / "state" / "processed.json"
FFMPEG_IMAGE = "ghcr.io/jellyfin/jellyfin:12.1"
SETTLE_SECONDS = 20

AUDIO = {".flac", ".wav", ".mp3", ".m4a", ".aac", ".ogg", ".aiff", ".aif", ".alac", ".wma", ".opus"}
ARCHIVE = {".zip", ".rar", ".7z"}
VIDEO = {".mkv", ".mp4", ".avi", ".m2ts", ".ts", ".wmv", ".webm"}
CONVERT = {".wav", ".aiff", ".aif"}


def log(message: str) -> None:
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {message}", flush=True)


def load_ledger() -> dict:
    if not LEDGER_PATH.exists():
        return {"files": {}}
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def save_ledger(ledger: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = LEDGER_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    temporary.replace(LEDGER_PATH)


def host_path(local_path: str) -> Path | None:
    if not local_path:
        return None
    if local_path.startswith(CONTAINER_PREFIX):
        relative = local_path[len(CONTAINER_PREFIX) :].lstrip("/")
        return HOST_DATA / relative
    if local_path.startswith("/"):
        return Path(local_path)
    return None


def file_key(row: sqlite3.Row) -> str:
    return f"{row['id']}|{row['unique_id']}"


def readiness(path: Path, expected: int, status: str) -> str:
    if status != "completed":
        return status or "pending"
    if not path.is_file():
        return "missing"
    stat = path.stat()
    if expected and stat.st_size < int(expected * 0.99):
        return "incomplete"
    if time.time() - stat.st_mtime < SETTLE_SECONDS:
        return "settling"
    return "ready"


def audio_video_counts(path: Path) -> tuple[int, int]:
    audio = video = 0
    suffix = path.suffix.lower()
    if suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                ext = Path(info.filename).suffix.lower()
                if ext in AUDIO:
                    audio += 1
                elif ext in VIDEO:
                    video += 1
        return audio, video
    listing = subprocess.run(["7z", "l", "-ba", str(path)], capture_output=True, text=True)
    for line in listing.stdout.splitlines():
        lowered = line.lower().rstrip()
        if any(lowered.endswith(ext) for ext in AUDIO):
            audio += 1
        elif any(lowered.endswith(ext) for ext in VIDEO):
            video += 1
    return audio, video


def safe_stem(name: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in " ._-()[]" else "_" for char in name)
    return cleaned[:180].strip() or "album"


def norm_album_key(name: str) -> str:
    lowered = name.lower()
    lowered = re.sub(r"\[[^\]]*\]", " ", lowered)
    lowered = re.sub(r"\([^)]*\)", " ", lowered)
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def loose_name_tokens(stem: str) -> list[str]:
    parts = re.split(r"[-–—|]", stem)
    tokens: list[str] = []
    for part in parts:
        part = re.sub(r"^\s*\d+[\.)]\s*", "", part.strip())
        key = norm_album_key(part)
        if len(key) >= 4:
            tokens.append(key)
    whole = norm_album_key(stem)
    if len(whole) >= 4 and whole not in tokens:
        tokens.append(whole)
    return tokens


def primary_audio_dir(album_root: Path) -> Path:
    counts: dict[Path, int] = {}
    for path in album_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in AUDIO and not path.name.startswith("._"):
            counts[path.parent] = counts.get(path.parent, 0) + 1
    if not counts:
        return album_root
    return max(counts, key=lambda folder: (counts[folder], -len(folder.parts)))


def find_library_album_for_loose(library: Path, file_name: str, *, exclude: Path | None = None) -> Path | None:
    """Pick an existing library album folder that this loose track belongs in."""
    stem = Path(file_name).stem
    tokens = loose_name_tokens(stem)
    if not tokens:
        return None
    stem_key = norm_album_key(stem)
    best: Path | None = None
    best_score = 0
    for candidate in library.iterdir():
        if not candidate.is_dir() or candidate.name.startswith("."):
            continue
        if exclude is not None and candidate.resolve() == exclude.resolve():
            continue
        key = norm_album_key(candidate.name)
        if not key or key == stem_key:
            continue
        words = set(key.split())
        score = 0
        for token in tokens:
            if token in key:
                score = max(score, len(token))
            for word in token.split():
                if len(word) >= 4 and word in words:
                    score = max(score, 10 + len(word))
        if score > best_score:
            best_score = score
            best = candidate
    if best_score >= 4:
        return best
    return None


def build_media_album_groups(rows: list[sqlite3.Row]) -> dict[int, list[sqlite3.Row]]:
    groups: dict[int, list[sqlite3.Row]] = {}
    for row in rows:
        album_id = int(row["media_album_id"] or 0)
        if album_id:
            groups.setdefault(album_id, []).append(row)
    return groups


def inbox_folder_for_loose(
    row: sqlite3.Row,
    groups: dict[int, list[sqlite3.Row]],
    library: Path,
) -> str:
    """Where to stage a loose audio file before library import."""
    library.mkdir(parents=True, exist_ok=True)
    file_name = row["file_name"] or ""
    album_id = int(row["media_album_id"] or 0)
    if album_id and album_id in groups:
        members = groups[album_id]
        for member in members:
            name = member["file_name"] or ""
            if Path(name).suffix.lower() in ARCHIVE:
                return safe_stem(Path(name).stem)
        for member in members:
            name = member["file_name"] or ""
            if Path(name).suffix.lower() in AUDIO:
                matched = find_library_album_for_loose(library, name)
                if matched:
                    return matched.name
        stems = [Path(m["file_name"]).stem for m in members if (m["file_name"] or "").lower().endswith(tuple(AUDIO))]
        if stems:
            prefix = os.path.commonprefix(stems).strip(" ._-")
            if len(prefix) >= 4:
                return safe_stem(prefix)
    matched = find_library_album_for_loose(library, file_name)
    if matched:
        return matched.name
    return album_folder_name(Path(file_name))


def extract_archive(path: Path) -> bool:
    audio, video = audio_video_counts(path)
    musicish = any(token in path.name.lower() for token in ("flac", "wav", "mp3", "soundtrack", "score", " ost"))
    if video and audio == 0:
        log(f"skip video {path.name}")
        return False
    if audio == 0 and not musicish:
        log(f"skip no-audio {path.name}")
        return False
    destination = INBOX / safe_stem(path.stem)
    destination.mkdir(parents=True, exist_ok=True)
    log(f"extract {path.name} audio={audio} video={video}")
    if path.suffix.lower() == ".zip":
        subprocess.run(["unzip", "-n", "-q", str(path), "-d", str(destination)], check=False)
    else:
        subprocess.run(["7z", "x", "-y", f"-o{destination}", str(path)], check=False)
    return True


def album_folder_name(path: Path) -> str:
    """One folder per download — same rule as zip extract (no Loose bucket)."""
    return safe_stem(path.stem)


def copy_audio(
    path: Path,
    row: sqlite3.Row | None = None,
    groups: dict[int, list[sqlite3.Row]] | None = None,
    library: Path | None = None,
) -> None:
    if row is not None and groups is not None and library is not None:
        folder_name = inbox_folder_for_loose(row, groups, library)
    else:
        folder_name = album_folder_name(path)
    dest_dir = INBOX / folder_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / path.name
    if not target.exists() or target.stat().st_size != path.stat().st_size:
        shutil.copy2(path, target)
        log(f"copied {path.name} -> {dest_dir.name}/")


def drain_previous_extract(ledger: dict) -> None:
    """Move the one-time raw extract aside and remember archives already unpacked."""
    if ledger.get("dump_seeded") or not DUMP.exists():
        return
    files = [path for path in DUMP.rglob("*") if path.is_file()]
    audio_files = [path for path in files if path.suffix.lower() in AUDIO]
    if not audio_files:
        ledger["dump_seeded"] = True
        save_ledger(ledger)
        return
    newest = max(path.stat().st_mtime for path in files)
    INBOX.mkdir(parents=True, exist_ok=True)
    for child in list(DUMP.iterdir()):
        target = INBOX / child.name
        if target.exists():
            target = INBOX / "telegram-import" / child.name
            target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(child), str(target))
    shutil.rmtree(DUMP, ignore_errors=True)
    ledger["dump_seeded"] = True
    ledger["dump_newest_mtime"] = newest
    save_ledger(ledger)
    log(f"moved previous Telegram extract into inbox ({len(audio_files)} audio files)")


def seed_already_extracted(ledger: dict, rows: list[sqlite3.Row]) -> None:
    if not ledger.get("dump_seeded") or ledger.get("dump_seed_applied"):
        return
    cutoff = float(ledger.get("dump_newest_mtime") or 0)
    for row in rows:
        path = host_path(row["local_path"] or "")
        if path is None or not path.is_file():
            continue
        if path.stat().st_mtime <= cutoff + 5:
            ledger["files"][file_key(row)] = {
                "size": int(row["size"] or 0),
                "name": row["file_name"] or path.name,
                "extracted": True,
            }
    ledger["dump_seed_applied"] = True
    save_ledger(ledger)
    log(f"seeded {len(ledger['files'])} archives already extracted")


def recover_staging() -> None:
    staging = Path("/mnt/Skyhawk_8TB_HDD/Media/.music-staging")
    if not staging.exists():
        return
    INBOX.mkdir(parents=True, exist_ok=True)
    for run_dir in list(staging.iterdir()):
        incoming = run_dir / "Incoming"
        source = incoming if incoming.exists() else run_dir
        for child in list(source.iterdir()):
            target = INBOX / child.name
            if target.exists():
                target = INBOX / f"{child.name}-recovered"
            shutil.move(str(child), str(target))
            log(f"recovered staging {child.name}")
        shutil.rmtree(run_dir, ignore_errors=True)


def convert_wavs() -> None:
    """Intentionally disabled — import original audio as-is (no ffmpeg/transcode)."""
    wavs = [
        path
        for path in INBOX.rglob("*")
        if path.is_file() and path.suffix.lower() in CONVERT and not path.name.startswith("._")
    ]
    if wavs:
        log(f"skipping convert for {len(wavs)} wav/aiff file(s); importing originals")


def relocate_loose_wavs_into_albums(library: Path) -> int:
    """Move single loose .wav folders into the album folder they belong to."""
    moved = 0
    for album_dir in list(library.iterdir()):
        if not album_dir.is_dir() or album_dir.name.startswith("."):
            continue
        audio_files = [
            path
            for path in album_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in AUDIO and not path.name.startswith("._")
        ]
        if len(audio_files) != 1:
            continue
        track = audio_files[0]
        if track.suffix.lower() not in CONVERT:
            continue
        target_album = find_library_album_for_loose(library, track.name, exclude=album_dir)
        if target_album is None:
            continue
        dest_dir = primary_audio_dir(target_album)
        dest = dest_dir / track.name
        if dest.exists() and dest.stat().st_size == track.stat().st_size:
            track.unlink(missing_ok=True)
        elif dest.exists():
            dest = dest_dir / f"{track.stem}-{int(time.time())}{track.suffix}"
            shutil.move(str(track), str(dest))
            moved += 1
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(track), str(dest))
            moved += 1
            log(f"relocated {track.name} -> {target_album.name}/{dest_dir.name}/")
        leftovers = [path for path in album_dir.rglob("*") if path.is_file() and not path.name.startswith("._")]
        if not leftovers:
            shutil.rmtree(album_dir, ignore_errors=True)
            log(f"removed empty album folder {album_dir.name}")
    return moved


def migrate_library_loose(library: Path) -> int:
    """Move legacy Loose/ tracks into per-title album folders."""
    loose = library / "Loose"
    if not loose.is_dir():
        return 0
    moved = 0
    for src in loose.iterdir():
        if not src.is_file() or src.suffix.lower() not in AUDIO:
            continue
        dest_dir = library / album_folder_name(src)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if dest.exists() and dest.stat().st_size == src.stat().st_size:
            src.unlink(missing_ok=True)
            continue
        if dest.exists():
            dest = dest_dir / f"{src.stem}-{int(time.time())}{src.suffix}"
        shutil.move(str(src), str(dest))
        moved += 1
    if loose.exists() and not any(loose.iterdir()):
        loose.rmdir()
    if moved:
        log(f"migrated {moved} file(s) from Loose/ into album folders")
    return moved


def import_inbox_audio() -> int:
    """Move extracted inbox folders into the Jellyfin music library without converting."""
    library = Path("/mnt/Skyhawk_8TB_HDD/Media/Music/Flac")
    library.mkdir(parents=True, exist_ok=True)
    migrate_library_loose(library)
    relocated = relocate_loose_wavs_into_albums(library)
    if relocated:
        log(f"relocated {relocated} loose wav(s) into album folders")
    audio_exts = AUDIO
    moved_albums = 0
    moved_files = 0

    children = [p for p in INBOX.iterdir() if not p.name.startswith(".") and p.name != "Loose"]
    if not children:
        log("inbox empty")
        return 0

    for child in children:
        audio_files = [
            p
            for p in (child.rglob("*") if child.is_dir() else [child])
            if p.is_file() and p.suffix.lower() in audio_exts and not p.name.startswith("._")
        ]
        if not audio_files:
            # drop empty / junk extract dirs
            if child.is_dir():
                leftovers = [p for p in child.rglob("*") if p.is_file() and not p.name.startswith("._")]
                if not leftovers:
                    shutil.rmtree(child, ignore_errors=True)
            continue

        if child.is_file():
            matched = find_library_album_for_loose(library, child.name)
            dest_dir = primary_audio_dir(matched) if matched else library / album_folder_name(child)
            if not matched:
                dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / child.name
            if dest.exists() and dest.stat().st_size == child.stat().st_size:
                child.unlink(missing_ok=True)
                continue
            if dest.exists():
                dest = dest_dir / f"{child.stem}-{int(time.time())}{child.suffix}"
            shutil.move(str(child), str(dest))
            moved_files += 1
            continue

        album_name = safe_stem(child.name)
        matched = find_library_album_for_loose(library, audio_files[0].name)
        dest = matched if matched else library / album_name
        if dest.exists():
            # merge new audio into existing album folder
            track_dir = primary_audio_dir(dest) if dest.is_dir() else dest
            for src in audio_files:
                target = track_dir / src.name
                if target.exists() and target.stat().st_size == src.stat().st_size:
                    src.unlink(missing_ok=True)
                    continue
                if target.exists():
                    target = track_dir / f"{src.stem}-{int(time.time())}{src.suffix}"
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(target))
                moved_files += 1
            # copy covers if present
            for cover in child.rglob("*"):
                if cover.is_file() and cover.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                    target = dest / cover.name
                    if not target.exists():
                        shutil.move(str(cover), str(target))
            shutil.rmtree(child, ignore_errors=True)
        else:
            shutil.move(str(child), str(dest))
            moved_albums += 1
            moved_files += len(audio_files)

    # permissions for jellyfin (apps uid 568)
    try:
        subprocess.run(["chown", "-R", "568:568", str(library)], check=False)
    except Exception:
        pass
    log(f"imported albums_moved={moved_albums} audio_files={moved_files}")
    return moved_files


def open_database() -> sqlite3.Connection:
    database = HOST_DATA / "data.db"
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def main() -> int:
    INBOX.mkdir(parents=True, exist_ok=True)
    ledger = load_ledger()
    ledger.setdefault("files", {})
    recover_staging()
    drain_previous_extract(ledger)

    connection = open_database()
    rows = connection.execute(
        """
        SELECT id, unique_id, file_name, local_path, download_status, size, mime_type, media_album_id
        FROM file_record
        """
    ).fetchall()
    connection.close()
    seed_already_extracted(ledger, rows)
    library = Path("/mnt/Skyhawk_8TB_HDD/Media/Music/Flac")
    media_groups = build_media_album_groups(rows)

    waiting = 0
    extracted = 0
    for row in rows:
        path = host_path(row["local_path"] or "")
        name = row["file_name"] or (path.name if path else "")
        suffix = Path(name).suffix.lower()
        if suffix not in ARCHIVE | AUDIO:
            continue
        if path is None:
            continue
        state = readiness(path, int(row["size"] or 0), row["download_status"] or "")
        if state != "ready":
            if state in {"downloading", "incomplete", "settling", "pending"}:
                waiting += 1
                log(f"waiting {name}: {state}")
            continue
        key = file_key(row)
        previous = ledger["files"].get(key) or {}
        if previous.get("extracted") and int(previous.get("size") or -1) == int(row["size"] or 0):
            continue
        try:
            if suffix in ARCHIVE:
                did_extract = extract_archive(path)
            else:
                copy_audio(path, row, media_groups, library)
                did_extract = True
        except Exception as error:
            log(f"failed {name}: {error}")
            continue
        if did_extract:
            ledger["files"][key] = {
                "size": int(row["size"] or 0),
                "name": name,
                "extracted": True,
            }
            extracted += 1
            save_ledger(ledger)

    if waiting:
        log(f"{waiting} download(s) still in progress")
    if extracted:
        log(f"extracted or copied {extracted} finished download(s)")

    # No conversion — import FLAC/WAV/MP3 as-is into the Jellyfin library.
    convert_wavs()
    imported = import_inbox_audio()
    if imported == 0:
        log("nothing new to import")
        return 0
    log("library updated")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        log(f"error: {error}")
        sys.exit(1)
