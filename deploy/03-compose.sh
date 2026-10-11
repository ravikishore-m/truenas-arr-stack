#!/usr/bin/env bash
# Deploy docker-compose stacks (obs-lite, adguard-home) to the NAS.
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
require_key

STACK="${1:-all}"

deploy_obs() {
  local src="$REPO_ROOT/stack/obs-lite"
  echo "==> obs-lite → $OBS_REMOTE"
  tar czf /tmp/obs-lite-bundle.tgz -C "$src" \
    docker-compose.yml prometheus.yml install_on_truenas.sh grafana-provisioning \
    deco-exporter 2>/dev/null || \
  tar czf /tmp/obs-lite-bundle.tgz -C "$src" \
    docker-compose.yml prometheus.yml install_on_truenas.sh grafana-provisioning

  nas_scp /tmp/obs-lite-bundle.tgz "$NAS:/tmp/"

  if [[ -f "$SECRETS_DIR/deco.env" ]]; then
    nas_scp "$SECRETS_DIR/deco.env" "$NAS:/tmp/deco.env"
  fi

  nas_ssh "OBS_ROOT='$OBS_REMOTE' bash -s" <<'REMOTE'
set -euo pipefail
rm -rf /tmp/obs-lite-bundle
mkdir -p /tmp/obs-lite-bundle
tar xzf /tmp/obs-lite-bundle.tgz -C /tmp/obs-lite-bundle
chmod +x /tmp/obs-lite-bundle/install_on_truenas.sh
/tmp/obs-lite-bundle/install_on_truenas.sh /tmp/obs-lite-bundle
if [[ -f /tmp/deco.env ]]; then
  cp /tmp/deco.env "${OBS_ROOT}/deco.env"
  chmod 600 "${OBS_ROOT}/deco.env"
fi
REMOTE
  echo "    Grafana  http://${NAS_HOST}:30091"
  echo "    Netdata  http://${NAS_HOST}:19999"
}

deploy_adguard() {
  local src="$REPO_ROOT/stack/adguard-home"
  echo "==> adguard-home → $ADGUARD_REMOTE"
  nas_ssh "sudo mkdir -p '$ADGUARD_REMOTE/work' '$ADGUARD_REMOTE/conf' && sudo chown -R ${NAS_USER}:${NAS_USER} '$ADGUARD_REMOTE'"

  # Prefer AdGuardHome.yaml.template name expected by install script
  nas_rsync "$src/docker-compose.yml" "$NAS:$ADGUARD_REMOTE/"
  nas_rsync "$src/install_on_truenas.sh" "$NAS:$ADGUARD_REMOTE/"
  if [[ -f "$src/AdGuardHome.yaml" ]]; then
    nas_rsync "$src/AdGuardHome.yaml" "$NAS:$ADGUARD_REMOTE/AdGuardHome.yaml.template"
  fi

  nas_ssh "ADGUARD_ROOT='$ADGUARD_REMOTE' bash '$ADGUARD_REMOTE/install_on_truenas.sh'"
  echo "    UI  http://${NAS_HOST}:30054"
  echo "    DNS ${NAS_HOST}:53"
}

case "$STACK" in
  all)
    deploy_obs
    deploy_adguard
    ;;
  obs-lite|obs) deploy_obs ;;
  adguard-home|adguard) deploy_adguard ;;
  *) die "Unknown stack: $STACK (use: all|obs-lite|adguard-home)" ;;
esac

echo "Compose stacks deployed."
