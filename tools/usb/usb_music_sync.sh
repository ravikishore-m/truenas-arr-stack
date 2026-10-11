#!/usr/bin/env bash
# TrueNAS cron wrapper: sync latest Telegram/NAS albums to attached USB stick.
set -euo pipefail

TOOLS="${TOOLS:-/mnt/WD_Black_1TB_SSD/configs/flac-tools}"
export PYTHONPATH="${TOOLS}/py${PYTHONPATH:+:${PYTHONPATH}}"
export USB_MUSIC_SOURCE="${USB_MUSIC_SOURCE:-/mnt/Skyhawk_8TB_HDD/Media/Music/Flac}"
export USB_MUSIC_MOUNT="${USB_MUSIC_MOUNT:-/mnt/usb-music}"
export USB_MUSIC_DEST="${USB_MUSIC_DEST:-${USB_MUSIC_MOUNT}/Flac}"
export USB_MUSIC_STATE="${USB_MUSIC_STATE:-${TOOLS}/state}"
export USB_MUSIC_LOG="${USB_MUSIC_LOG:-${TOOLS}/logs}"
# Script prints to stdout; cron capture handles persistence. Disable internal file dup.
export USB_MUSIC_LOG_FILE=0

mkdir -p "${USB_MUSIC_STATE}" "${USB_MUSIC_LOG}"
exec python3 "${TOOLS}/usb_music_sync.py" >> "${USB_MUSIC_LOG}/usb-music-sync.log" 2>&1
