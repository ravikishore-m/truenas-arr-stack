#!/usr/bin/env bash
# Deploy Deco → Prometheus exporter. Requires deco.env with DECO_PASSWORD.
set -euo pipefail

OBS="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$OBS/../.." && pwd)"
KEY="${TRUENAS_SSH_KEY:-$REPO/ops/.nas-keys/id_ed25519_truenas}"
NAS_HOST="${NAS_HOST:-192.168.68.56}"
NAS_USER="${NAS_USER:-truenas_admin}"
NAS="${NAS_USER}@${NAS_HOST}"
LOCAL_ENV="${DECO_ENV_FILE:-$REPO/ops/secrets/deco.env}"

SSH=(ssh -i "$KEY" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=20)
SCP=(scp -i "$KEY" -o IdentitiesOnly=yes -o BatchMode=yes)

if [[ ! -f "$LOCAL_ENV" ]]; then
  echo "Missing $LOCAL_ENV"
  echo "Copy ops/secrets/deco.env.example → ops/secrets/deco.env and set DECO_PASSWORD"
  echo "(Deco web UI / app admin password for http://192.168.68.1 )"
  exit 1
fi

tar czf /tmp/deco-exporter-bundle.tgz -C "$OBS" \
  deco-exporter docker-compose.yml prometheus.yml \
  grafana-provisioning/dashboards/json/house-bandwidth.json \
  grafana-provisioning/dashboards/dashboards.yml

"${SCP[@]}" /tmp/deco-exporter-bundle.tgz "$LOCAL_ENV" "$NAS:/tmp/"
"${SSH[@]}" "$NAS" 'bash -s' << 'REMOTE'
set -euo pipefail
OBS=/mnt/WD_Black_1TB_SSD/configs/obs-lite
rm -rf /tmp/deco-bundle
mkdir -p /tmp/deco-bundle
tar xzf /tmp/deco-exporter-bundle.tgz -C /tmp/deco-bundle
sudo mkdir -p "$OBS/deco-exporter" "$OBS/deco-exporter-state" "$OBS/grafana-provisioning/dashboards/json"
sudo cp -a /tmp/deco-bundle/deco-exporter/. "$OBS/deco-exporter/"
sudo cp /tmp/deco-bundle/docker-compose.yml "$OBS/"
sudo cp /tmp/deco-bundle/prometheus.yml "$OBS/"
sudo cp /tmp/deco-bundle/grafana-provisioning/dashboards/json/house-bandwidth.json \
  "$OBS/grafana-provisioning/dashboards/json/"
sudo cp /tmp/deco.env "$OBS/deco.env"
sudo chmod 600 "$OBS/deco.env"
cd "$OBS"
sudo docker compose build deco-exporter
sudo docker compose up -d deco-exporter prometheus grafana
sleep 8
echo "=== deco metrics ==="
curl -s http://127.0.0.1:9105/metrics | grep -E '^deco_' | head -40 || true
echo "=== scrape_ok ==="
curl -s 'http://127.0.0.1:30090/api/v1/query?query=deco_scrape_ok' || true
echo
sudo docker logs obs-deco-exporter 2>&1 | tail -30
REMOTE

echo ""
echo "Grafana: http://${NAS_HOST}:30091  →  RKplex → Whole House Bandwidth (Deco)"
