#!/usr/bin/env python3
"""Install arr-dashboard as a TrueNAS custom app."""

from __future__ import annotations

import json
import os
import subprocess
import time


def main() -> None:
    os.makedirs("/mnt/WD_Black_1TB_SSD/configs/arr-dashboard", exist_ok=True)
    compose = {
        "name": "arr-dashboard",
        "services": {
            "arr-dashboard": {
                "container_name": "arr-dashboard",
                "image": "khak1s/arr-dashboard:latest",
                "restart": "unless-stopped",
                "environment": {
                    "PUID": "568",
                    "PGID": "568",
                    "TZ": "Asia/Kolkata",
                },
                "ports": ["30310:3000"],
                "volumes": [
                    "/mnt/WD_Black_1TB_SSD/configs/arr-dashboard:/config",
                ],
                "cpus": 1.0,
                "mem_limit": "1536m",
            }
        },
    }
    # delete if exists
    subprocess.run(
        [
            "midclt",
            "call",
            "app.delete",
            "arr-dashboard",
            json.dumps({"remove_images": False, "remove_ix_volumes": False}),
        ],
        capture_output=True,
        text=True,
    )
    payload = {"app_name": "arr-dashboard", "custom_compose_config": compose}
    r = subprocess.run(
        ["midclt", "call", "app.custom.create", json.dumps(payload)],
        capture_output=True,
        text=True,
    )
    print("create_rc", r.returncode)
    print((r.stdout or r.stderr)[:1500])
    time.sleep(8)
    print(
        subprocess.check_output(
            [
                "sudo",
                "docker",
                "ps",
                "--filter",
                "name=arr-dashboard",
                "--format",
                "{{.Names}} {{.Status}} {{.Ports}}",
            ],
            text=True,
        )
    )
    print(
        subprocess.check_output(
            ["curl", "-s", "-o", "/dev/null", "-w", "http=%{http_code}\n", "http://127.0.0.1:30310/"],
            text=True,
        )
    )


if __name__ == "__main__":
    main()
