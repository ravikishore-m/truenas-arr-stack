#!/usr/bin/env bash
# Deploy obs-lite stack on TrueNAS (run on NAS as root or via sudo).
set -euo pipefail

OBS_ROOT="${OBS_ROOT:-/mnt/WD_Black_1TB_SSD/configs/obs-lite}"
SRC="${1:-/tmp/obs-lite-bundle}"

mkdir -p "$OBS_ROOT"/{prometheus-data,grafana-data,netdata-config,netdata-lib,netdata-cache}
mkdir -p "$OBS_ROOT/grafana-provisioning/dashboards/json"

cp -f "$SRC/docker-compose.yml" "$OBS_ROOT/"
cp -f "$SRC/prometheus.yml" "$OBS_ROOT/"
# Reset provisioning (avoid duplicate datasource.yml leftovers)
rm -rf "$OBS_ROOT/grafana-provisioning"
cp -rf "$SRC/grafana-provisioning" "$OBS_ROOT/grafana-provisioning"

# deco-exporter needs deco.env (compose env_file); seed placeholder if missing
if [[ ! -f "$OBS_ROOT/deco.env" ]]; then
  if [[ -f "$SRC/deco.env.example" ]]; then
    cp -f "$SRC/deco.env.example" "$OBS_ROOT/deco.env"
  else
    printf 'DECO_HOST=192.168.68.1\nDECO_USER=admin\nDECO_PASSWORD=changeme\n' > "$OBS_ROOT/deco.env"
  fi
  chmod 600 "$OBS_ROOT/deco.env"
fi
if [[ -d "$SRC/deco-exporter" ]]; then
  rm -rf "$OBS_ROOT/deco-exporter"
  cp -rf "$SRC/deco-exporter" "$OBS_ROOT/deco-exporter"
fi

chmod 644 "$OBS_ROOT/prometheus.yml" "$OBS_ROOT/docker-compose.yml"
chmod -R a+rX "$OBS_ROOT/grafana-provisioning"
# Grafana container uid 472; Prometheus runs as root in compose
chown -R 472:472 "$OBS_ROOT/grafana-data" 2>/dev/null || true
chown -R 65534:65534 "$OBS_ROOT/prometheus-data" 2>/dev/null || true

cd "$OBS_ROOT"
if docker info >/dev/null 2>&1; then
  DC=(docker compose)
elif sudo -n docker info >/dev/null 2>&1; then
  DC=(sudo docker compose)
else
  echo "ERROR: docker needs sudo. On TrueNAS run once (as root):" >&2
  echo '  echo "truenas_admin ALL=(ALL) NOPASSWD: /usr/bin/docker" | sudo tee /etc/sudoers.d/truenas-docker' >&2
  exit 1
fi
"${DC[@]}" pull
"${DC[@]}" up -d

HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
HOST_IP="${HOST_IP:-NAS_IP}"
echo ""
echo "Grafana:    http://${HOST_IP}:30091  (admin / GRAFANA_PASSWORD)"
echo "Netdata:    http://${HOST_IP}:19999"
echo "Prometheus: http://${HOST_IP}:30090"
