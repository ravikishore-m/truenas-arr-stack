#!/usr/bin/env bash
# Shared helpers for deploy scripts. Source only — do not execute.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Load .env if present (does not override already-exported vars)
if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
  set +a
fi

export NAS_HOST="${NAS_HOST:-192.168.68.56}"
export NAS_USER="${NAS_USER:-truenas_admin}"
export NAS="${NAS_USER}@${NAS_HOST}"

export CONFIG_POOL="${CONFIG_POOL:-/mnt/WD_Black_1TB_SSD}"
export MEDIA_POOL="${MEDIA_POOL:-/mnt/Skyhawk_8TB_HDD}"
export CONFIG_ROOT="${CONFIG_ROOT:-${CONFIG_POOL}/configs}"
export STACKS_ROOT="${STACKS_ROOT:-${CONFIG_POOL}/stacks}"
export DOWNLOADS="${DOWNLOADS:-${MEDIA_POOL}/Downloads}"
export MEDIA_ROOT="${MEDIA_ROOT:-${MEDIA_POOL}/Media}"
export OBS_REMOTE="${OBS_REMOTE:-${CONFIG_ROOT}/obs-lite}"
export ADGUARD_REMOTE="${ADGUARD_REMOTE:-${CONFIG_ROOT}/adguard-home}"

export SECRETS_DIR="${SECRETS_DIR:-$REPO_ROOT/secrets}"
export TRUENAS_SSH_KEY="${TRUENAS_SSH_KEY:-$SECRETS_DIR/.nas-keys/id_ed25519_truenas}"
export NAS_SSH_KEY="$TRUENAS_SSH_KEY"
export TRUENAS_API_KEY_FILE="${TRUENAS_API_KEY_FILE:-$SECRETS_DIR/.nas-keys/truenas_api.key}"

# Catalog apps managed via TrueNAS Apps
CATALOG_APPS=(
  sonarr radarr prowlarr qbittorrent bazarr seerr jellyfin
  tailscale navidrome homepage filebrowser metube
)

# Docker compose stacks we deploy from this repo
COMPOSE_STACKS=(obs-lite adguard-home)

die() { echo "ERROR: $*" >&2; exit 1; }

require_key() {
  [[ -f "$TRUENAS_SSH_KEY" ]] || die "SSH key missing. Run: ./deploy.sh ssh"
}

SSH_OPTS=(-i "$TRUENAS_SSH_KEY" -o IdentitiesOnly=yes -o BatchMode=yes
          -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)

nas_ssh() {
  require_key
  ssh "${SSH_OPTS[@]}" "$NAS" "$@"
}

nas_scp() {
  require_key
  scp "${SSH_OPTS[@]}" "$@"
}

nas_rsync() {
  require_key
  rsync -avz -e "ssh -i $TRUENAS_SSH_KEY -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=accept-new" "$@"
}

nas_midclt() {
  if [[ -f "$TRUENAS_API_KEY_FILE" ]] && command -v midclt >/dev/null 2>&1; then
    midclt --uri "wss://${NAS_HOST}/api/current" -K "$TRUENAS_API_KEY_FILE" "$@" \
      || midclt --uri "ws://${NAS_HOST}/api/current" --plain -K "$TRUENAS_API_KEY_FILE" "$@"
  else
    nas_ssh midclt "$@"
  fi
}

load_lib() { :; } # noop marker for "already sourced"
