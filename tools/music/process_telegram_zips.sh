#!/usr/bin/env bash
# Unzip Telegram FLAC archives into the Music inbox, then organize.
set -euo pipefail

TELEGRAM_DIR="${TELEGRAM_DIR:-/mnt/Skyhawk_8TB_HDD/Downloads/Telegram}"
INBOX="${INBOX:-/mnt/Skyhawk_8TB_HDD/Downloads/Music}"
TOOLS_DIR="${TOOLS_DIR:-/mnt/WD_Black_1TB_SSD/configs/flac-tools}"
APPLY="${APPLY:-0}"

mkdir -p "${TELEGRAM_DIR}" "${INBOX}"

shopt -s nullglob
archives=(
  "${TELEGRAM_DIR}"/*.zip
  "${TELEGRAM_DIR}"/*.ZIP
  "${TELEGRAM_DIR}"/*.7z
  "${TELEGRAM_DIR}"/*.rar
)

if ((${#archives[@]} == 0)); then
  echo "No archives found in ${TELEGRAM_DIR}"
else
  for archive in "${archives[@]}"; do
    name="$(basename "${archive}")"
    stem="${name%.*}"
    dest="${INBOX}/${stem}"
    mkdir -p "${dest}"
    case "${archive,,}" in
      *.zip)
        unzip -n -q "${archive}" -d "${dest}" || true
        ;;
      *.7z)
        7z x -y -o"${dest}" "${archive}" || true
        ;;
      *.rar)
        unrar x -o- "${archive}" "${dest}/" || true
        ;;
    esac
    echo "Extracted: ${name} -> ${dest}"
  done
fi

export INBOX LIBRARY="${LIBRARY:-/mnt/Skyhawk_8TB_HDD/Media/Music/Flac}" TOOLS_DIR APPLY
exec "${TOOLS_DIR}/run_flac_pipeline.sh"
