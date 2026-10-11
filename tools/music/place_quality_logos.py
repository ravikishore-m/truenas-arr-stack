#!/usr/bin/env python3
"""Remove Jellyfin clear-logo files so Apple badges come from UI injection only."""
from __future__ import annotations
from pathlib import Path

LIBRARY = Path("/mnt/Skyhawk_8TB_HDD/Media/Music/Flac")

def main() -> None:
    removed = 0
    for album in sorted(p for p in LIBRARY.iterdir() if p.is_dir()):
        logo = album / "logo.png"
        if logo.exists():
            logo.unlink()
            removed += 1
        # also clear folder.jpg-style clear logos we may have named differently
        for name in ("clearlogo.png", "logo.jpg", "clearlogo.jpg"):
            p = album / name
            if p.exists():
                p.unlink()
                removed += 1
    print({"removed_logos": removed})

if __name__ == "__main__":
    main()
