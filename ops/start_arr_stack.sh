#!/usr/bin/env bash
# Compatibility wrapper → ./deploy.sh apps
exec "$(cd "$(dirname "$0")/.." && pwd)/deploy.sh" apps "$@"
