#!/usr/bin/env bash
# Compatibility wrapper → ./deploy.sh ssh
exec "$(cd "$(dirname "$0")/.." && pwd)/deploy.sh" ssh "$@"
