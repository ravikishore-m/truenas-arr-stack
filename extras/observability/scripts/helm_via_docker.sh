#!/usr/bin/env bash
set -euo pipefail

OPT=/mnt/WD_Black_1TB_SSD/vms/k3s-files/observability
KC=/mnt/WD_Black_1TB_SSD/vms/k3s-files/kube/kubeconfig.yaml
sed -i 's/127.0.0.1/192.168.68.56/g' "$KC" || true

kubectl() {
  sudo docker exec -e KUBECONFIG=/output/kubeconfig.yaml k3s kubectl "$@"
}

helm() {
  sudo docker run --rm --network host \
    -v "$KC:/root/.kube/config:ro" \
    -v "$OPT:/opt/observability:ro" \
    alpine/helm:3.16.4 "$@"
}

echo "Waiting for API..."
for i in $(seq 1 40); do
  if kubectl get nodes; then
    break
  fi
  sleep 3
done

kubectl create namespace observability --dry-run=client -o yaml | kubectl apply -f -

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n observability \
  -f /opt/observability/values-kube-prometheus.yaml \
  --set prometheus.service.type=NodePort \
  --set prometheus.service.nodePort=30090 \
  --set alertmanager.service.type=NodePort \
  --set alertmanager.service.nodePort=30093 \
  --set grafana.service.type=NodePort \
  --set grafana.service.nodePort=30300 \
  --timeout 35m \
  --wait

helm upgrade --install loki grafana/loki \
  -n observability \
  -f /opt/observability/values-loki.yaml \
  --set gateway.service.type=NodePort \
  --set gateway.service.nodePort=3100 \
  --set gateway.enabled=true \
  --timeout 25m \
  --wait

helm upgrade --install prometheus-blackbox-exporter prometheus-community/prometheus-blackbox-exporter \
  -n observability \
  --timeout 15m \
  --wait

cat > /tmp/alloy-values.yaml <<'EOF'
alloy:
  configMap:
    content: |
      logging { level = "info" }
      discovery.kubernetes "pods" { role = "pod" }
      loki.source.kubernetes "pods" {
        targets    = discovery.kubernetes.pods.targets
        forward_to = [loki.write.default.receiver]
      }
      loki.write "default" {
        endpoint { url = "http://loki.observability.svc.cluster.local:3100/loki/api/v1/push" }
      }
EOF
sudo cp /tmp/alloy-values.yaml "$OPT/alloy-values.yaml"

helm upgrade --install alloy grafana/alloy \
  -n observability \
  -f /opt/observability/alloy-values.yaml \
  --timeout 15m \
  --wait

# Copy manifests into k3s and apply
sudo docker cp "$OPT/alertmanager-config.yaml" k3s:/tmp/alertmanager-config.yaml
sudo docker cp "$OPT/grafana-dashboards.yaml" k3s:/tmp/grafana-dashboards.yaml
kubectl apply -f /tmp/alertmanager-config.yaml || true
kubectl apply -f /tmp/grafana-dashboards.yaml || true

echo "=== SERVICES ==="
kubectl get svc -n observability
echo "=== PODS ==="
kubectl get pods -n observability
echo "DONE"
