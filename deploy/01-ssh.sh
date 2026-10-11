#!/usr/bin/env bash
# One-time SSH key setup for TrueNAS (key stays in secrets/, gitignored).
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

KEY_DIR="$(dirname "$TRUENAS_SSH_KEY")"
mkdir -p "$KEY_DIR"
chmod 700 "$KEY_DIR"

if [[ ! -f "$TRUENAS_SSH_KEY" ]]; then
  ssh-keygen -t ed25519 -f "$TRUENAS_SSH_KEY" -N "" -C "truenas-arr@$(hostname -s 2>/dev/null || echo mac)"
  echo "Created $TRUENAS_SSH_KEY"
fi

# shellcheck disable=SC2046
SSH_BASE=(-i "$TRUENAS_SSH_KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new)

if ssh "${SSH_BASE[@]}" -o BatchMode=yes -o ConnectTimeout=5 "$NAS" true 2>/dev/null; then
  echo "Key auth OK → $NAS"
  exit 0
fi

echo ""
echo "=== Add this public key in TrueNAS UI ==="
echo "  Credentials → Users → ${NAS_USER} → Edit → Authorized SSH Public Key"
echo "  Paste, Save, then re-run: ./deploy.sh ssh"
echo ""
cat "${TRUENAS_SSH_KEY}.pub"
echo ""

if [[ "${TRUENAS_SSH_COPY_ID:-}" == "1" ]]; then
  ssh-copy-id -i "${TRUENAS_SSH_KEY}.pub" \
    -o PreferredAuthentications=password -o PubkeyAuthentication=no \
    -o NumberOfPasswordPrompts=1 "$NAS"
fi

if ! ssh "${SSH_BASE[@]}" -o BatchMode=yes -o ConnectTimeout=8 "$NAS" true 2>/dev/null; then
  die "Key auth not active yet. Add the key in TrueNAS UI, then re-run."
fi

echo "OK: key-only SSH → $NAS"
