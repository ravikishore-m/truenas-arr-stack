#!/usr/bin/env python3
"""Minimal Alertmanager webhook that restarts TrueNAS apps by heal label."""

from __future__ import annotations

import json
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 9191
ALLOWED = {"jellyfin", "telegram-files", "sonarr", "radarr", "prowlarr", "qbittorrent"}


def restart_app(name: str) -> str:
    if name not in ALLOWED:
        return f"ignored:{name}"
    stop = subprocess.run(["midclt", "call", "app.stop", name], capture_output=True, text=True)
    start = subprocess.run(["midclt", "call", "app.start", name], capture_output=True, text=True)
    return f"stop={stop.returncode};start={start.returncode}"


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return

        results = []
        for alert in payload.get("alerts", []):
            if alert.get("status") != "firing":
                continue
            heal = (alert.get("labels") or {}).get("heal")
            if heal:
                results.append({heal: restart_app(heal)})

        data = json.dumps({"results": results}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        print("[heal]", fmt % args)


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
