#!/usr/bin/env python3
"""Deploy heal webhook + host Alloy as TrueNAS custom apps / systemd-like docker."""

from __future__ import annotations

import json
import os
import subprocess
import time


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True)


def ensure_dirs() -> None:
    for path in [
        "/mnt/WD_Black_1TB_SSD/vms/k3s-files/observability",
        "/mnt/WD_Black_1TB_SSD/vms/k3s-files/host-services",
    ]:
        os.makedirs(path, exist_ok=True)


def deploy_heal_webhook() -> None:
    compose = {
        "name": "heal-webhook",
        "services": {
            "heal-webhook": {
                "container_name": "heal-webhook",
                "image": "python:3.12-slim",
                "restart": "unless-stopped",
                "network_mode": "host",
                "volumes": [
                    "/mnt/WD_Black_1TB_SSD/vms/k3s-files/observability/heal_webhook.py:/app/heal_webhook.py:ro",
                    "/usr/bin/midclt:/usr/bin/midclt:ro",
                    "/var/run/middleware/.middlewared.sock:/var/run/middleware/.middlewared.sock",
                ],
                "command": ["python3", "/app/heal_webhook.py"],
                "cpus": 0.25,
                "mem_limit": "128m",
            }
        },
    }
    # midclt may not be usable inside container; run via host docker with privileged socket instead
    run(["midclt", "call", "app.delete", "heal-webhook", json.dumps({"remove_images": False, "remove_ix_volumes": False})])
    # Prefer raw docker for midclt access via host network + docker.sock isn't enough for midclt.
    # Run heal webhook on host with nohup python instead.
    subprocess.Popen(
        ["python3", "/mnt/WD_Black_1TB_SSD/vms/k3s-files/observability/heal_webhook.py"],
        stdout=open("/mnt/WD_Black_1TB_SSD/vms/k3s-files/observability/heal-webhook.log", "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    print("heal webhook started on :9191")


def deploy_host_alloy() -> None:
    alloy_config = """
logging { level = "info" }

discovery.docker "containers" {
  host = "unix:///var/run/docker.sock"
}

loki.source.docker "containers" {
  host       = "unix:///var/run/docker.sock"
  targets    = discovery.docker.containers.targets
  forward_to = [loki.write.default.receiver]
}

prometheus.exporter.unix "host" { }

prometheus.scrape "host" {
  targets    = prometheus.exporter.unix.host.targets
  forward_to = [prometheus.remote_write.default.receiver]
}

prometheus.remote_write "default" {
  endpoint {
    url = "http://192.168.68.56:30090/api/v1/write"
  }
}

loki.write "default" {
  endpoint {
    url = "http://192.168.68.56:3100/loki/api/v1/push"
  }
}
"""
    # Loki/Prometheus may only be NodePort inside cluster; expose via kubectl port later.
    # For host Alloy, scrape Netdata and push logs once Loki NodePort exists.
    cfg_path = "/mnt/WD_Black_1TB_SSD/vms/k3s-files/host-services/alloy.river"
    with open(cfg_path, "w", encoding="utf-8") as fh:
        fh.write(
            """
logging { level = "info" }

discovery.docker "containers" {
  host = "unix:///var/run/docker.sock"
}

loki.source.docker "containers" {
  host       = "unix:///var/run/docker.sock"
  targets    = discovery.docker.containers.targets
  labels     = { job = "docker", host = "truenas" }
  forward_to = [loki.write.default.receiver]
}

prometheus.scrape "netdata" {
  targets = [{"__address__" = "192.168.68.56:19999", "instance" = "truenas"}]
  metrics_path = "/api/v1/allmetrics"
  params = { format = ["prometheus"] }
  forward_to = [prometheus.remote_write.default.receiver]
}

prometheus.remote_write "default" {
  endpoint {
    url = "http://kube-prometheus-stack-prometheus.observability.svc:9090/api/v1/write"
  }
}

loki.write "default" {
  endpoint {
    url = "http://192.168.68.56:3100/loki/api/v1/push"
  }
}
"""
        )

    compose = {
        "name": "host-alloy",
        "services": {
            "host-alloy": {
                "container_name": "host-alloy",
                "image": "grafana/alloy:v1.5.1",
                "restart": "unless-stopped",
                "network_mode": "host",
                "pid": "host",
                "volumes": [
                    f"{cfg_path}:/etc/alloy/config.alloy:ro",
                    "/var/run/docker.sock:/var/run/docker.sock",
                    "/var/lib/docker/containers:/var/lib/docker/containers:ro",
                    "/:/rootfs:ro",
                    "/sys:/sys:ro",
                    "/proc:/host/proc:ro",
                ],
                "command": ["run", "/etc/alloy/config.alloy", "--storage.path=/var/lib/alloy/data"],
                "cpus": 0.5,
                "mem_limit": "512m",
            }
        },
    }
    run(["midclt", "call", "app.delete", "host-alloy", json.dumps({"remove_images": False, "remove_ix_volumes": False})])
    r = run(["midclt", "call", "app.custom.create", json.dumps({"app_name": "host-alloy", "custom_compose_config": compose})])
    print("host-alloy", r.returncode, (r.stdout or r.stderr)[:400])


def install_cron_demand_scale() -> None:
    script = "/mnt/WD_Black_1TB_SSD/vms/k3s-files/observability/demand_scale.sh"
    os.chmod(script, 0o755)
    # TrueNAS cron via midclt
    payload = {
        "enabled": True,
        "command": f"{script} stop",
        "description": "Stop *arr stack overnight to free RAM",
        "schedule": {"minute": "0", "hour": "3", "dom": "*", "month": "*", "dow": "*"},
        "user": "root",
        "stdout": True,
        "stderr": True,
    }
    # remove previous similar jobs if any
    jobs = json.loads(run(["midclt", "call", "cronjob.query"]).stdout or "[]")
    for job in jobs:
        if "demand_scale" in (job.get("command") or "") or "*arr stack" in (job.get("description") or ""):
            run(["midclt", "call", "cronjob.delete", str(job["id"])])
    r = run(["midclt", "call", "cronjob.create", json.dumps(payload)])
    print("cron stop", r.returncode, (r.stdout or r.stderr)[:300])

    payload2 = dict(payload)
    payload2["command"] = f"{script} start"
    payload2["description"] = "Start *arr stack in morning"
    payload2["schedule"] = {"minute": "0", "hour": "9", "dom": "*", "month": "*", "dow": "*"}
    r = run(["midclt", "call", "cronjob.create", json.dumps(payload2)])
    print("cron start", r.returncode, (r.stdout or r.stderr)[:300])


def main() -> None:
    ensure_dirs()
    deploy_heal_webhook()
    time.sleep(1)
    deploy_host_alloy()
    install_cron_demand_scale()


if __name__ == "__main__":
    main()
