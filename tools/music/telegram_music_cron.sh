#!/usr/bin/env bash
# TrueNAS cron: extract finished Telegram music downloads into Jellyfin library.
# No conversion/transcode. No album-folder renames of existing library items.
set -euo pipefail

TOOLS="${TOOLS:-/mnt/WD_Black_1TB_SSD/configs/flac-tools}"
LIBRARY="${LIBRARY:-/mnt/Skyhawk_8TB_HDD/Media/Music/Flac}"
JELLYFIN_URL="${JELLYFIN_URL:-http://127.0.0.1:30013}"
JELLYFIN_API_KEY="${JELLYFIN_API_KEY:-5b31ef3410314d5e9f22afcb446ac856}"
LOG_DIR="${TOOLS}/logs"
mkdir -p "${TOOLS}/state" "${LOG_DIR}" "${TOOLS}/reports"

exec 9>"${TOOLS}/state/telegram-music.lock"
if ! flock -n 9; then
  echo "$(date -Is) telegram music job already running"
  exit 0
fi

if [[ -x "${TOOLS}/.venv/bin/python" ]]; then
  PY="${TOOLS}/.venv/bin/python"
else
  export PYTHONPATH="${TOOLS}/py${PYTHONPATH:+:${PYTHONPATH}}"
  PY="python3"
fi

export JELLYFIN_URL JELLYFIN_API_KEY

echo "$(date -Is) start telegram music import" | tee -a "${LOG_DIR}/telegram-music-cron.log"
before="$(find "${LIBRARY}" -type f \( -iname '*.flac' -o -iname '*.wav' -o -iname '*.mp3' -o -iname '*.m4a' \) 2>/dev/null | wc -l | tr -d ' ')"

set +e
"${PY}" "${TOOLS}/process_telegram_downloads.py" >> "${LOG_DIR}/telegram-music.log" 2>&1
extract_rc=$?
set -e

after="$(find "${LIBRARY}" -type f \( -iname '*.flac' -o -iname '*.wav' -o -iname '*.mp3' -o -iname '*.m4a' \) 2>/dev/null | wc -l | tr -d ' ')"
echo "$(date -Is) extract_rc=${extract_rc} audio ${before}->${after}" | tee -a "${LOG_DIR}/telegram-music-cron.log"

# Music library is detached from Jellyfin for faster UI.
# Imports still land on disk; do not trigger Jellyfin music refresh.
if [[ "${after}" -gt "${before}" ]]; then
  echo "$(date -Is) imported new audio (${before}->${after}); jellyfin music refresh skipped (library detached)" | tee -a "${LOG_DIR}/telegram-music-cron.log"
fi

echo "$(date -Is) done" | tee -a "${LOG_DIR}/telegram-music-cron.log"
exit "${extract_rc}"
