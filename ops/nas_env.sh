#!/usr/bin/env bash
# Compatibility wrapper — prefer: source deploy/lib.sh
# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/deploy/lib.sh"
echo "NAS helpers loaded → ${NAS_USER}@${NAS_HOST} (SSH key + optional API key)"
