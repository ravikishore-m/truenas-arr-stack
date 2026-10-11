#!/usr/bin/env bash
set -euo pipefail

export KUBECONFIG=/mnt/WD_Black_1TB_SSD/vms/k3s-files/kube/kubeconfig.yaml
OPT=/mnt/WD_Black_1TB_SSD/vms/k3s-files/observability
BIN=/mnt/WD_Black_1TB_SSD/vms/k3s-files/bin
mkdir -p "$OPT" "$BIN"

# Prefer kubeconfig from k3s output; fallback to container copy
if [[ ! -f "$KUBECONFIG" ]]; then
  sudo docker cp k3s:/output/kubeconfig.yaml "$KUBECONFIG" 2>/dev/null || \
  sudo docker exec k3s cat /etc/rancher/k3s/k3s.yaml > /tmp/k3s.yaml
  if [[ -f /tmp/k3s.yaml ]]; then
    sed 's/127.0.0.1/192.168.68.56/g' /tmp/k3s.yaml > "$KUBECONFIG"
  fi
fi
# Rewrite localhost to host IP for host-side kubectl
sed -i 's/127.0.0.1/192.168.68.56/g' "$KUBECONFIG" || true
chmod 644 "$KUBECONFIG"

# Install kubectl/helm into dataset bin if missing
if [[ ! -x "$BIN/kubectl" ]]; then
  curl -fsSL -o "$BIN/kubectl" "https://dl.k8s.io/release/v1.31.4/bin/linux/amd64/kubectl"
  chmod +x "$BIN/kubectl"
fi
if [[ ! -x "$BIN/helm" ]]; then
  curl -fsSL https://get.helm.sh/helm-v3.16.4-linux-amd64.tar.gz | tar -xz -C /tmp
  mv /tmp/linux-amd64/helm "$BIN/helm"
  chmod +x "$BIN/helm"
fi
export PATH="$BIN:$PATH"

for i in $(seq 1 60); do
  if kubectl get nodes >/dev/null 2>&1; then
    break
  fi
  sleep 5
done
kubectl get nodes
kubectl get pods -A

kubectl create namespace observability --dry-run=client -o yaml | kubectl apply -f -

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n observability \
  -f "$OPT/values-kube-prometheus.yaml" \
  --set prometheus.service.type=NodePort \
  --set prometheus.service.nodePort=30090 \
  --set alertmanager.service.type=NodePort \
  --set alertmanager.service.nodePort=30093 \
  --timeout 25m \
  --wait

helm upgrade --install loki grafana/loki \
  -n observability \
  -f "$OPT/values-loki.yaml" \
  --timeout 20m \
  --wait

helm upgrade --install prometheus-blackbox-exporter prometheus-community/prometheus-blackbox-exporter \
  -n observability \
  --timeout 10m \
  --wait

# Alloy for cluster logs into Loki
cat <<'EOF' > "$OPT/alloy-values.yaml"
alloy:
  configMap:
    content: |
      logging {
        level = "info"
      }
      discovery.kubernetes "pods" {
        role = "pod"
      }
      loki.source.kubernetes "pods" {
        targets    = discovery.kubernetes.pods.targets
        forward_to = [loki.write.default.receiver]
      }
      loki.write "default" {
        endpoint {
          url = "http://loki.observability.svc.cluster.local:3100/loki/api/v1/push"
        }
      }
EOF

helm upgrade --install alloy grafana/alloy \
  -n observability \
  -f "$OPT/alloy-values.yaml" \
  --timeout 10m \
  --wait || true

kubectl apply -f "$OPT/alertmanager-config.yaml" || true
kubectl apply -f "$OPT/grafana-dashboards.yaml" || true

echo "=== DONE ==="
kubectl get svc -n observability
kubectl get pods -n observability
