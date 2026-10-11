#!/usr/bin/env python3
"""USB music sync for TrueNAS.

detect → validate existing USB albums → copy missing/latest from NAS library → validate.

Intended to run from cron every minute. Quiet no-op when no USB stick is present.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

SOURCE = Path(os.environ.get("USB_MUSIC_SOURCE", "/mnt/Skyhawk_8TB_HDD/Media/Music/Flac"))
MOUNTPOINT = Path(os.environ.get("USB_MUSIC_MOUNT", "/mnt/usb-music"))
USB_FLAC = Path(os.environ.get("USB_MUSIC_DEST", str(MOUNTPOINT / "Flac")))
STATE_DIR = Path(os.environ.get("USB_MUSIC_STATE", "/mnt/WD_Black_1TB_SSD/configs/flac-tools/state"))
LOG_DIR = Path(os.environ.get("USB_MUSIC_LOG", "/mnt/WD_Black_1TB_SSD/configs/flac-tools/logs"))
LOCK = STATE_DIR / "usb-music-sync.lock"
STATE = STATE_DIR / "usb-music-sync.json"
MARKER = MOUNTPOINT / ".usb-music-sync-status.json"

AUDIO_EXT = {".flac", ".wav", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".alac", ".aiff", ".aif"}
SKIP_NAMES = {"loose", "_needs review", ".trash-storage", ".fseventsd", "spotiflac"}
NORM = re.compile(r"[^a-z0-9]+")


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}"
    print(line, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    # Avoid double-writes when cron already redirects stdout to this file.
    if os.environ.get("USB_MUSIC_LOG_FILE", "1") == "1":
        with (LOG_DIR / "usb-music-sync.log").open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def run(cmd: list[str], check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def normalize(name: str) -> str:
    name = name.casefold()
    name = re.sub(r"\[[^\[\]]*\]", " ", name)
    name = re.sub(r"\{[^{}]*\}", " ", name)
    name = re.sub(r"\((?:flac|wav|alac|mp3|hi-?res[^)]*|lossless|16-?bit[^)]*|24-?bit[^)]*)\)", " ", name, flags=re.I)
    name = NORM.sub(" ", name)
    return re.sub(r"\s+", " ", name).strip()


def album_stats(folder: Path) -> dict:
    files = []
    total = 0
    for path in folder.rglob("*"):
        if path.is_file() and path.suffix.lower() in AUDIO_EXT and not path.name.startswith("._"):
            size = path.stat().st_size
            files.append((str(path.relative_to(folder)), size))
            total += size
    return {"files": len(files), "bytes": total, "names": sorted(files)}


def inventory_all(root: Path) -> dict[str, list[dict]]:
    """All album folders grouped by normalized name (may be multiple physical dirs)."""
    grouped: dict[str, list[dict]] = {}
    if not root.is_dir():
        return grouped
    for child in root.iterdir():
        if not child.is_dir():
            continue
        if child.name.casefold() in SKIP_NAMES or child.name.startswith("."):
            continue
        stats = album_stats(child)
        if stats["files"] == 0:
            continue
        key = normalize(child.name)
        entry = {
            "name": child.name,
            "path": str(child),
            "mtime": child.stat().st_mtime,
            **{k: stats[k] for k in ("files", "bytes")},
        }
        grouped.setdefault(key, []).append(entry)
    return grouped


def inventory_best(root: Path) -> dict[str, dict]:
    """One best folder per normalized album (for quick lookup)."""
    out: dict[str, dict] = {}
    for key, entries in inventory_all(root).items():
        out[key] = max(entries, key=lambda e: (e["bytes"], e["files"]))
    return out


def usb_already_has(norm_key: str, src: dict, grouped: dict[str, list[dict]]) -> tuple[bool, Path | None]:
    """True if USB already holds this album (any folder with same norm, full size)."""
    for entry in grouped.get(norm_key, []):
        if entry["files"] >= src["files"] and entry["bytes"] >= src["bytes"]:
            return True, Path(entry["path"])
    return False, None


def dedupe_usb_folders(grouped: dict[str, list[dict]]) -> int:
    """Merge duplicate USB folders that share the same normalized album name."""
    merged = 0
    for _key, entries in list(grouped.items()):
        if len(entries) <= 1:
            continue
        entries.sort(key=lambda e: (e["bytes"], e["files"]), reverse=True)
        canonical = Path(entries[0]["path"])
        for dup in entries[1:]:
            dup_path = Path(dup["path"])
            if dup_path.resolve() == canonical.resolve():
                continue
            log(f"dedupe merge {dup_path.name} -> {canonical.name}")
            ok, _ = copy_album(dup_path, canonical)
            if ok:
                shutil.rmtree(dup_path, ignore_errors=True)
                merged += 1
    return merged


def cleanup_usb_empty_duplicates(root: Path) -> int:
    """Remove empty album dirs when another folder with the same norm already has tracks."""
    if not root.is_dir():
        return 0
    by_norm: dict[str, list[Path]] = {}
    for child in root.iterdir():
        if not child.is_dir() or child.name.casefold() in SKIP_NAMES:
            continue
        by_norm.setdefault(normalize(child.name), []).append(child)
    removed = 0
    for _key, dirs in by_norm.items():
        if len(dirs) <= 1:
            continue
        nonempty = [d for d in dirs if album_stats(d)["files"] > 0]
        if not nonempty:
            continue
        keep = max(nonempty, key=lambda d: album_stats(d)["bytes"])
        for d in dirs:
            if d == keep:
                continue
            if album_stats(d)["files"] == 0:
                shutil.rmtree(d, ignore_errors=True)
                log(f"dedupe removed empty duplicate {d.name} (kept {keep.name})")
                removed += 1
    return removed


def list_usb_partitions() -> list[dict]:
    """Return removable USB partitions suitable for music sync."""
    raw = run(["lsblk", "-J", "-o", "NAME,TYPE,FSTYPE,LABEL,SIZE,MOUNTPOINT,TRAN,RM,PATH"])
    if raw.returncode != 0:
        return []
    data = json.loads(raw.stdout or "{}")
    found = []

    def walk(node: dict, parent_tran: str | None = None, parent_rm: int | None = None) -> None:
        tran = node.get("tran") or parent_tran
        rm = node.get("rm") if node.get("rm") is not None else parent_rm
        children = node.get("children") or []
        if node.get("type") == "part" and tran == "usb" and int(rm or 0) == 1:
            fstype = (node.get("fstype") or "").lower()
            if fstype in {"exfat", "vfat", "fat32", "ntfs", "ext4"} or fstype == "":
                found.append(
                    {
                        "path": node.get("path") or f"/dev/{node.get('name')}",
                        "fstype": fstype or "auto",
                        "label": node.get("label") or "",
                        "size": node.get("size") or "",
                        "mountpoint": node.get("mountpoint") or "",
                    }
                )
        for child in children:
            walk(child, tran, rm)

    for dev in data.get("blockdevices") or []:
        walk(dev)
    return found


def ensure_mounted(part: dict) -> bool:
    MOUNTPOINT.mkdir(parents=True, exist_ok=True)
    current = run(["findmnt", "-n", "-o", "SOURCE", str(MOUNTPOINT)])
    if current.returncode == 0 and current.stdout.strip():
        src = current.stdout.strip()
        if src == part["path"] or src.endswith(Path(part["path"]).name):
            return True
        log(f"mountpoint busy by {src}; skipping")
        return False

    if part.get("mountpoint"):
        # already mounted elsewhere — use that path by bind-mounting
        run(["mount", "--bind", part["mountpoint"], str(MOUNTPOINT)])
        return run(["findmnt", str(MOUNTPOINT)]).returncode == 0

    fstype = part.get("fstype") or "auto"
    opts = "rw,noatime"
    if fstype in {"exfat", "vfat", "fat32"}:
        opts = "rw,noatime,uid=0,gid=0,umask=000"
    cmd = ["mount", "-t", fstype, "-o", opts, part["path"], str(MOUNTPOINT)]
    result = run(cmd)
    if result.returncode != 0:
        # retry without explicit type
        result = run(["mount", "-o", opts, part["path"], str(MOUNTPOINT)])
    if result.returncode != 0:
        log(f"mount failed: {(result.stderr or result.stdout).strip()}")
        return False
    return True


def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_success": 0, "copied": {}}


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE)


def copy_album(src: Path, dest: Path) -> tuple[bool, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Prefer rsync for resume + size checks; fall back to copytree.
    # exFAT/FAT cannot chown/chmod — omit ownership or rsync exits non-zero
    # even after a successful data copy.
    if shutil.which("rsync"):
        result = run(
            [
                "rsync",
                "-rltD",
                "--size-only",
                "--partial",
                "--no-owner",
                "--no-group",
                "--no-perms",
                "--omit-dir-times",
                f"{src}/",
                f"{dest}/",
            ]
        )
        if result.returncode not in (0, 23):
            return False, (result.stderr or result.stdout or "rsync failed").strip()[:300]
        # Exit 23 = partial due to attrs; verify bytes separately in validate_copy.
        return True, "rsync"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return True, "copytree"


def validate_copy(src_stats: dict, dest: Path) -> tuple[bool, str]:
    if not dest.is_dir():
        return False, "dest missing"
    dst = album_stats(dest)
    if dst["files"] < src_stats["files"]:
        return False, f"file count {dst['files']}<{src_stats['files']}"
    # allow tiny slack for exFAT allocation differences — compare exact bytes of audio files
    if dst["bytes"] != src_stats["bytes"]:
        return False, f"bytes {dst['bytes']}!={src_stats['bytes']}"
    return True, f"ok files={dst['files']} bytes={dst['bytes']}"


def acquire_lock() -> int | None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(LOCK, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


def main() -> int:
    fd = acquire_lock()
    if fd is None:
        log("already running")
        return 0

    try:
        if not SOURCE.is_dir():
            log(f"source missing: {SOURCE}")
            return 1

        parts = list_usb_partitions()
        if not parts:
            return 0  # quiet when no stick

        part = parts[0]
        log(f"detect {part['path']} fstype={part['fstype']} size={part['size']} label={part['label'] or '-'}")
        if not ensure_mounted(part):
            return 1

        USB_FLAC.mkdir(parents=True, exist_ok=True)

        # 1) validate existing USB inventory; merge duplicate folder names
        cleanup_usb_empty_duplicates(USB_FLAC)
        usb_grouped = inventory_all(USB_FLAC)
        if dedupe_usb_folders(usb_grouped):
            usb_grouped = inventory_all(USB_FLAC)
        cleanup_usb_empty_duplicates(USB_FLAC)
        usb_grouped = inventory_all(USB_FLAC)
        usb_inv = inventory_best(USB_FLAC)
        src_inv = inventory_best(SOURCE)
        usb_dir_count = sum(len(v) for v in usb_grouped.values())
        log(
            f"validate usb_albums={len(usb_inv)} usb_dirs={usb_dir_count} "
            f"source_albums={len(src_inv)}"
        )

        # 2) copy only if no USB folder (any name) already has full album incl. wav/flac
        pending = []
        for key, src in src_inv.items():
            has_it, _existing = usb_already_has(key, src, usb_grouped)
            if has_it:
                continue
            usb = usb_inv.get(key)
            if usb is None:
                pending.append(("missing", src))
            elif usb["files"] < src["files"] or usb["bytes"] < src["bytes"]:
                pending.append(("incomplete", src))
        pending.sort(key=lambda item: item[1]["mtime"], reverse=True)

        if not pending:
            status = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "device": part,
                "usb_albums": len(usb_inv),
                "source_albums": len(src_inv),
                "copied": 0,
                "failed": 0,
                "message": "nothing new to copy",
            }
            MARKER.write_text(json.dumps(status, indent=2), encoding="utf-8")
            log("validate nothing new to copy")
            run(["sync"])
            return 0

        log(f"copy candidates={len(pending)} (newest first)")
        state = load_state()
        copied = 0
        failed = 0
        results = []

        for reason, src in pending:
            src_path = Path(src["path"])
            norm_key = normalize(src_path.name)
            _has, existing_path = usb_already_has(norm_key, src, usb_grouped)
            if _has and existing_path:
                log(f"skip [{reason}] {src_path.name} (already on USB as {existing_path.name})")
                continue
            dest_path = USB_FLAC / src_path.name
            existing = usb_inv.get(norm_key)
            if existing:
                dest_path = Path(existing["path"])

            log(f"copy [{reason}] {src_path.name} -> {dest_path.name}")
            ok, detail = copy_album(src_path, dest_path)
            if not ok:
                failed += 1
                results.append({"album": src_path.name, "ok": False, "error": detail})
                log(f"FAIL copy {src_path.name}: {detail}")
                continue

            # 3) validate after copy
            vok, vdetail = validate_copy(src, dest_path)
            if not vok:
                failed += 1
                results.append({"album": src_path.name, "ok": False, "error": vdetail})
                log(f"FAIL validate {src_path.name}: {vdetail}")
                continue

            copied += 1
            results.append({"album": src_path.name, "ok": True, "detail": vdetail, "reason": reason})
            state["copied"][normalize(src_path.name)] = {
                "name": src_path.name,
                "ts": time.time(),
                "files": src["files"],
                "bytes": src["bytes"],
            }
            log(f"OK {src_path.name} {vdetail}")

        state["last_success"] = time.time()
        save_state(state)
        run(["sync"])

        status = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "device": part,
            "usb_albums_before": len(usb_inv),
            "usb_albums_after": len(inventory_best(USB_FLAC)),
            "copied": copied,
            "failed": failed,
            "results": results[:50],
        }
        MARKER.write_text(json.dumps(status, indent=2), encoding="utf-8")
        log(f"done copied={copied} failed={failed}")
        return 0 if failed == 0 else 2
    finally:
        try:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
        except Exception:
            pass
        os.close(fd)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"error: {exc}")
        raise
