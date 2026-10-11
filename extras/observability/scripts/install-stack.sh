#!/usr/bin/env bash
# Run on the k3s VM after kubectl/helm are ready.
set -euo pipefail

NS=observability
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n "$NS" \
  -f /opt/observability/values-kube-prometheus.yaml \
  --set prometheus.service.type=NodePort \
  --set prometheus.service.nodePort=30090 \
  --set alertmanager.service.type=NodePort \
  --set alertmanager.service.nodePort=30093 \
  --wait --timeout 20m

helm upgrade --install loki grafana/loki \
  -n "$NS" \
  -f /opt/observability/values-loki.yaml \
  --wait --timeout 15m

helm upgrade --install prometheus-blackbox-exporter prometheus-community/prometheus-blackbox-exporter \
  -n "$NS" \
  --set service.type=ClusterIP \
  --wait --timeout 10m

kubectl apply -f /opt/observability/alertmanager-config.yaml
kubectl apply -f /opt/observability/grafana-dashboards.yaml

echo "Grafana NodePort: 30300  Prometheus: 30090"
kubectl get pods -n "$NS"
