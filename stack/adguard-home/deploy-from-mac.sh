#!/usr/bin/env bash
# Compatibility wrapper → ./deploy.sh compose adguard
exec "$(cd "$(dirname "$0")/../.." && pwd)/deploy.sh" compose adguard "$@"
