#!/usr/bin/env bash
# Demand-based app scaler for TrueNAS (Docker Apps — not Kubernetes HPA).
# Keeps always-on apps running; starts optional apps only when needed; stops idle ones.
set -euo pipefail

ALWAYS_ON="${ALWAYS_ON:-jellyfin}"
OPTIONAL="${OPTIONAL:-telegram-files}"
IDLE_MINUTES="${IDLE_MINUTES:-60}"
TELEGRAM_DATA="${TELEGRAM_DATA:-/mnt/WD_Black_1TB_SSD/configs/telegram-files}"
STATE_DIR="${STATE_DIR:-/mnt/WD_Black_1TB_SSD/configs/ops-scaler}"
LOG="${STATE_DIR}/scaler.log"

mkdir -p "${STATE_DIR}"
ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "$(ts) $*" | tee -a "${LOG}" >/dev/null; echo "$(ts) $*"; }

app_state() {
  midclt call app.get_instance "$1" 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("state",""))' 2>/dev/null || echo UNKNOWN
}

ensure_running() {
  local name="$1" state
  state="$(app_state "${name}")"
  if [[ "${state}" != "RUNNING" ]]; then
    log "start ${name} (was ${state})"
    midclt call app.start "${name}" >/dev/null || true
  fi
}

ensure_stopped() {
  local name="$1" state
  state="$(app_state "${name}")"
  if [[ "${state}" == "RUNNING" ]]; then
    log "stop ${name}"
    midclt call app.stop "${name}" >/dev/null || true
  fi
}

telegram_idle() {
  # Idle if no temp growth and no recent document writes beyond IDLE_MINUTES
  python3 - <<PY
import os, time
from pathlib import Path
root = Path("${TELEGRAM_DATA}")
idle_sec = ${IDLE_MINUTES} * 60
now = time.time()
paths = []
for p in root.rglob("*"):
    if p.is_file():
        paths.append(p.stat().st_mtime)
if not paths:
    print("idle")
    raise SystemExit
newest = max(paths)
print("idle" if (now - newest) > idle_sec else "busy")
PY
}

ACTION="${1:-status}"

case "${ACTION}" in
  ensure-streaming)
    for a in ${ALWAYS_ON}; do ensure_running "${a}"; done
    ;;
  telegram-on)
    ensure_running telegram-files
    ;;
  telegram-off)
    ensure_stopped telegram-files
    ;;
  idle-scale-down)
    for a in ${ALWAYS_ON}; do ensure_running "${a}"; done
    if [[ "$(telegram_idle)" == "idle" ]]; then
      ensure_stopped telegram-files
    else
      log "telegram busy; leave running"
    fi
    ;;
  status)
    for a in ${ALWAYS_ON} ${OPTIONAL}; do
      echo "${a}: $(app_state "${a}")"
    done
    echo "telegram activity: $(telegram_idle)"
    ;;
  *)
    echo "Usage: $0 {status|ensure-streaming|telegram-on|telegram-off|idle-scale-down}"
    exit 1
    ;;
esac
