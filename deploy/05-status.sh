#!/usr/bin/env bash
# Quick health check of LAN endpoints + container names.
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

check_http() {
  local name="$1" url="$2"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "$url" 2>/dev/null || echo "000")
  printf "  %-14s %-6s %s\n" "$name" "$code" "$url"
}

echo "=== LAN endpoints ($NAS_HOST) ==="
check_http "Jellyfin"   "http://${NAS_HOST}:30013/health"
check_http "Seerr"      "http://${NAS_HOST}:30357/api/v1/status"
check_http "Radarr"     "http://${NAS_HOST}:7878/ping"
check_http "Sonarr"     "http://${NAS_HOST}:8989/ping"
check_http "Prowlarr"   "http://${NAS_HOST}:9696/ping"
check_http "Bazarr"     "http://${NAS_HOST}:6767/api/system/status"
check_http "qBit"       "http://${NAS_HOST}:30024"
check_http "Grafana"    "http://${NAS_HOST}:30091/api/health"
check_http "Netdata"    "http://${NAS_HOST}:19999/api/v1/info"
check_http "AdGuard"    "http://${NAS_HOST}:30054"
check_http "Navidrome"  "http://${NAS_HOST}:30043"
check_http "Homepage"   "http://${NAS_HOST}:30310"

if [[ -f "$TRUENAS_SSH_KEY" ]]; then
  echo ""
  echo "=== Docker (compose stacks) ==="
  nas_ssh 'sudo docker ps --format "table {{.Names}}\t{{.Status}}" 2>/dev/null | grep -E "NAME|obs-|adguard" || docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "NAME|obs-|adguard"' \
    || echo "  (SSH unavailable)"
fi
