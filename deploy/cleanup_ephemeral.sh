#!/usr/bin/env bash
# Wipe ephemeral ops artifacts: old metrics WAL leftovers, app logs, scaler noise.
# Metrics TSDB itself is already capped by Prometheus retention (24h / 1GB).
set -euo pipefail

LOG_MAX_DAYS="${LOG_MAX_DAYS:-1}"
PATHS=(
  /mnt/WD_Black_1TB_SSD/configs/jellyfin/log
  /mnt/WD_Black_1TB_SSD/configs/telegram-files/logs
  /mnt/WD_Black_1TB_SSD/configs/ops-scaler
  /mnt/WD_Black_1TB_SSD/configs/obs-lite/prometheus-data
)

echo "$(date -Is) cleanup start"
# Truncate / delete application log files older than LOG_MAX_DAYS
find /mnt/WD_Black_1TB_SSD/configs/jellyfin/log -type f -mtime +"${LOG_MAX_DAYS}" -delete 2>/dev/null || true
find /mnt/WD_Black_1TB_SSD/configs/telegram-files/logs -type f -mtime +"${LOG_MAX_DAYS}" -delete 2>/dev/null || true
# Keep scaler log tiny
if [[ -f /mnt/WD_Black_1TB_SSD/configs/ops-scaler/scaler.log ]]; then
  tail -n 200 /mnt/WD_Black_1TB_SSD/configs/ops-scaler/scaler.log > /tmp/scaler.log.$$
  mv /tmp/scaler.log.$$ /mnt/WD_Black_1TB_SSD/configs/ops-scaler/scaler.log
fi
# Docker container log rotation is host-managed; truncate large json logs for our obs containers if any
for c in obs-prometheus obs-grafana obs-cadvisor obs-node-exporter telegram-files; do
  f=$(sudo docker inspect --format='{{.LogPath}}' "$c" 2>/dev/null || true)
  if [[ -n "${f}" && -f "${f}" ]]; then
    size=$(stat -c%s "$f" 2>/dev/null || echo 0)
    if (( size > 50*1024*1024 )); then
      sudo truncate -s 0 "$f" || true
      echo "truncated docker log $c"
    fi
  fi
done
echo "$(date -Is) cleanup done"
