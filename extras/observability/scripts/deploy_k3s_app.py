#!/usr/bin/env python3
import json
import subprocess
import time


def main() -> None:
    compose = {
        "name": "k3s",
        "services": {
            "k3s": {
                "container_name": "k3s",
                "image": "rancher/k3s:v1.31.4-k3s1",
                "privileged": True,
                "network_mode": "host",
                "restart": "unless-stopped",
                "tmpfs": ["/run", "/var/run"],
                "environment": {
                    "K3S_KUBECONFIG_OUTPUT": "/output/kubeconfig.yaml",
                    "K3S_KUBECONFIG_MODE": "644",
                },
                "command": [
                    "server",
                    "--disable",
                    "traefik",
                    "--tls-san",
                    "192.168.68.56",
                    "--write-kubeconfig-mode",
                    "644",
                ],
                "volumes": [
                    "/mnt/WD_Black_1TB_SSD/vms/k3s-data:/var/lib/rancher/k3s",
                    "/mnt/WD_Black_1TB_SSD/vms/k3s-files/kube:/output",
                    "/etc/machine-id:/etc/machine-id:ro",
                ],
                "cpus": 4.0,
                "mem_limit": "6g",
            }
        },
    }
    payload = {"app_name": "k3s", "custom_compose_config": compose}
    r = subprocess.run(
        ["midclt", "call", "app.custom.create", json.dumps(payload)],
        capture_output=True,
        text=True,
    )
    print("create", r.returncode)
    print((r.stdout or r.stderr)[:2000])
    time.sleep(25)
    print(subprocess.check_output(["sudo", "docker", "ps", "-a", "--filter", "name=^k3s$", "--format", "{{.Names}} {{.Status}}"], text=True))
    print(subprocess.check_output(["sudo", "docker", "logs", "--tail", "50", "k3s"], text=True, stderr=subprocess.STDOUT))


if __name__ == "__main__":
    main()
