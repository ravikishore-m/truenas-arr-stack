#!/usr/bin/env bash
# Organize FLAC downloads on the Skyhawk media dataset.
set -euo pipefail

INBOX="${INBOX:-/mnt/Skyhawk_8TB_HDD/Media/.music-inbox}"
LIBRARY="${LIBRARY:-/mnt/Skyhawk_8TB_HDD/Media/Music/Flac}"
TOOLS_DIR="${TOOLS_DIR:-/mnt/WD_Black_1TB_SSD/configs/flac-tools}"
VENV="${TOOLS_DIR}/.venv"
REPORT_DIR="${TOOLS_DIR}/reports"
STAGE_ROOT="${STAGE_ROOT:-/mnt/Skyhawk_8TB_HDD/Media/.music-staging}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
APPLY="${APPLY:-0}"

mkdir -p "${INBOX}" "${LIBRARY}" "${REPORT_DIR}"

if [[ -x "${VENV}/bin/python" ]]; then
  PY="${VENV}/bin/python"
else
  export PYTHONPATH="${TOOLS_DIR}/py${PYTHONPATH:+:${PYTHONPATH}}"
  PY="python3"
fi

if ! find "${INBOX}" -type f -iname '*.flac' -print -quit | grep -q .; then
  echo "No FLAC files in inbox: ${INBOX}"
  exit 0
fi

stage="${STAGE_ROOT}/${TIMESTAMP}/Incoming"
mkdir -p "${stage}"

shopt -s dotglob nullglob
for item in "${INBOX}"/*; do
  name="$(basename "${item}")"
  [[ "${name}" == "." || "${name}" == ".." ]] && continue
  mv "${item}" "${stage}/"
done
shopt -u dotglob

apply_args=()
if [[ "${APPLY}" == "1" ]]; then
  apply_args=(--apply)
fi

"${PY}" "${TOOLS_DIR}/normalize_flac_albums.py" \
  "${stage}" \
  "${apply_args[@]}" \
  --fetch-covers-online \
  --report "${REPORT_DIR}/normalize-${TIMESTAMP}.json"

if [[ "${APPLY}" == "1" ]]; then
  shopt -s nullglob
  for album_dir in "${stage}"/*/; do
    [[ -d "${album_dir}" ]] || continue
    name="$(basename "${album_dir}")"
    if ! find "${album_dir}" -iname '*.flac' -print -quit | grep -q .; then
      rm -rf "${album_dir}"
      continue
    fi
    if [[ "${name}" == "_Needs Review" ]]; then
      mkdir -p "${LIBRARY}/_Needs Review"
      mv "${album_dir}" "${LIBRARY}/_Needs Review/${TIMESTAMP}"
      continue
    fi
    dest="${LIBRARY}/${name}"
    if [[ -e "${dest}" ]]; then
      rsync -a --remove-source-files "${album_dir}/" "${dest}/"
      find "${album_dir}" -type d -empty -delete || true
    else
      mv "${album_dir}" "${dest}"
    fi
  done
  shopt -u nullglob
  if find "${stage}" -type f -iname '*.flac' -print -quit | grep -q .; then
    echo "FLAC files still in staging; leaving ${stage} in place"
  else
    rm -rf "${STAGE_ROOT}/${TIMESTAMP}"
  fi
  chown -R 568:568 "${LIBRARY}"
  find "${LIBRARY}" -type d -exec chmod 755 {} +
  find "${LIBRARY}" -type f -exec chmod 644 {} +
fi

echo "Pipeline complete. Report: ${REPORT_DIR}/normalize-${TIMESTAMP}.json"
