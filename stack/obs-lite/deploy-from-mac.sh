#!/usr/bin/env bash
# Compatibility wrapper → ./deploy.sh compose obs-lite
exec "$(cd "$(dirname "$0")/../.." && pwd)/deploy.sh" compose obs-lite "$@"
