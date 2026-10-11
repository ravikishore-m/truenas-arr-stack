#!/usr/bin/env bash
set -euo pipefail
OBS=/mnt/WD_Black_1TB_SSD/configs/obs-lite
sudo chmod 644 "$OBS/prometheus.yml" "$OBS/docker-compose.yml"
sudo chmod -R a+rX "$OBS/grafana-provisioning"
sudo mkdir -p "$OBS/grafana-data" "$OBS/prometheus-data"
sudo chown -R 472:472 "$OBS/grafana-data"
sudo chmod -R u+rwX "$OBS/grafana-data"
sudo chown -R 65534:65534 "$OBS/prometheus-data" || true
sudo chmod -R u+rwX "$OBS/prometheus-data" || true

# Patch prometheus to run as root for TrueNAS ACL mounts
if ! grep -q 'user: "root"' "$OBS/docker-compose.yml"; then
  sudo python3 - <<'PY'
from pathlib import Path
p = Path("/mnt/WD_Black_1TB_SSD/configs/obs-lite/docker-compose.yml")
t = p.read_text()
old = """  prometheus:
    image: prom/prometheus:v2.55.1
    container_name: obs-prometheus
    restart: unless-stopped
    cpus: 1.0
    mem_limit: 1024m
"""
new = """  prometheus:
    image: prom/prometheus:v2.55.1
    container_name: obs-prometheus
    restart: unless-stopped
    user: "root"
    cpus: 1.0
    mem_limit: 1024m
"""
if old in t:
    p.write_text(t.replace(old, new))
    print("patched prometheus user root")
else:
    print("compose pattern not found")
PY
fi

cd "$OBS"
sudo docker compose up -d --force-recreate prometheus grafana
sleep 6
curl -s -o /dev/null -w "grafana:%{http_code}\n" http://127.0.0.1:30091/api/health
curl -s http://127.0.0.1:30091/api/health; echo
curl -s -o /dev/null -w "prom:%{http_code}\n" http://127.0.0.1:30090/-/ready
curl -s -o /dev/null -w "netdata:%{http_code}\n" http://127.0.0.1:19999/api/v1/info
sudo docker ps --format 'table {{.Names}}\t{{.Status}}' | grep obs
