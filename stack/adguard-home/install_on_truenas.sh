#!/usr/bin/env bash
set -euo pipefail

ROOT="${ADGUARD_ROOT:-/mnt/WD_Black_1TB_SSD/configs/adguard-home}"
cd "$ROOT"

if [[ ! -f conf/AdGuardHome.yaml ]]; then
  cp -f AdGuardHome.yaml.template conf/AdGuardHome.yaml
  echo "Seeded conf/AdGuardHome.yaml (default blocklists + DoH upstreams)"
fi

if docker info >/dev/null 2>&1; then
  DC=(docker compose)
elif sudo -n docker info >/dev/null 2>&1; then
  DC=(sudo docker compose)
else
  echo "ERROR: docker not available" >&2
  exit 1
fi

"${DC[@]}" pull
"${DC[@]}" up -d

HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
HOST_IP="${HOST_IP:-NAS_IP}"
echo ""
echo "AdGuard Home is up."
echo "  Setup / UI: http://${HOST_IP}:30054"
echo "  DNS (LAN):  ${HOST_IP}:53"
echo ""
echo "Point router custom DNS to ${HOST_IP} (see stack/adguard-home/DECO-DNS.md)."
