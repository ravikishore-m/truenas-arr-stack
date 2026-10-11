#!/usr/bin/env bash
# One entrypoint for the TrueNAS *arr media stack.
#
# Fresh NAS:
#   cp .env.example .env   # edit paths/IP
#   ./deploy.sh ssh
#   ./deploy.sh dirs
#   # Install catalog apps in TrueNAS UI (see docs/catalog-apps.md)
#   ./deploy.sh compose
#   ./deploy.sh apps
#   ./deploy.sh status
#
# Day-to-day:
#   ./deploy.sh apps      # start everything
#   ./deploy.sh status
#   ./deploy.sh compose obs-lite
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DEPLOY="$ROOT/deploy"
CMD="${1:-help}"
shift || true

chmod +x "$DEPLOY"/*.sh "$ROOT/deploy.sh" 2>/dev/null || true

case "$CMD" in
  ssh|bootstrap-ssh)
    exec "$DEPLOY/01-ssh.sh" "$@"
    ;;
  dirs|mkdirs)
    exec "$DEPLOY/02-dirs.sh" "$@"
    ;;
  compose|stacks)
    exec "$DEPLOY/03-compose.sh" "$@"
    ;;
  apps|start)
    exec "$DEPLOY/04-apps.sh" "${1:-start}"
    ;;
  stop)
    exec "$DEPLOY/04-apps.sh" stop
    ;;
  list|list-apps)
    exec "$DEPLOY/04-apps.sh" list
    ;;
  status|health)
    exec "$DEPLOY/05-status.sh" "$@"
    ;;
  all|fresh)
    # Automated portion of a fresh install (catalog apps still need UI once).
    "$DEPLOY/01-ssh.sh"
    "$DEPLOY/02-dirs.sh"
    "$DEPLOY/03-compose.sh" all
    "$DEPLOY/04-apps.sh" start
    "$DEPLOY/05-status.sh"
    echo ""
    echo "If catalog apps were missing, install them once via TrueNAS Apps UI:"
    echo "  → docs/catalog-apps.md"
    ;;
  help|-h|--help|"")
    cat <<'EOF'
TrueNAS *arr stack — deploy helper

Usage:
  ./deploy.sh ssh              Setup SSH key auth (one-time)
  ./deploy.sh dirs             Create config/media directories on NAS
  ./deploy.sh compose [name]   Deploy compose stacks (all|obs-lite|adguard)
  ./deploy.sh apps             Start TrueNAS catalog apps
  ./deploy.sh stop             Stop catalog apps
  ./deploy.sh list             List installed apps
  ./deploy.sh status           Health-check LAN endpoints
  ./deploy.sh all              ssh → dirs → compose → apps → status

First-time on a fresh NAS:
  1. cp .env.example .env && edit NAS_HOST / pool paths
  2. ./deploy.sh ssh
  3. Install apps from docs/catalog-apps.md (TrueNAS UI)
  4. ./deploy.sh all

Docs: README.md  docs/catalog-apps.md  docs/remote-access.md
EOF
    ;;
  *)
    echo "Unknown command: $CMD" >&2
    echo "Run: ./deploy.sh help" >&2
    exit 1
    ;;
esac
