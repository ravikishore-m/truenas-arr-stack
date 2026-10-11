#!/usr/bin/env python3
"""Scrape TP-Link Deco local API → Prometheus (whole-home bandwidth)."""

from __future__ import annotations

import json
import os
import time
import traceback
from dataclasses import asdict, is_dataclass
from pathlib import Path

from prometheus_client import Gauge, Info, start_http_server

STATE_PATH = Path(os.environ.get("DECO_STATE", "/var/lib/deco-exporter/state.json"))
HOST = os.environ.get("DECO_HOST", "192.168.68.1")
USER = os.environ.get("DECO_USER", "admin")
PASSWORD = os.environ.get("DECO_PASSWORD", "")
PORT = int(os.environ.get("DECO_EXPORTER_PORT", "9105"))
INTERVAL = int(os.environ.get("DECO_SCRAPE_INTERVAL", "30"))
CAP_GB = float(os.environ.get("AIRTEL_CAP_GB", "3333"))

SCRAPE_OK = Gauge("deco_scrape_ok", "1 if last Deco scrape succeeded")
SCRAPE_SECONDS = Gauge("deco_scrape_duration_seconds", "Last scrape duration")
CLIENTS_ONLINE = Gauge("deco_clients_online", "Online client devices")
MESH_NODES = Gauge("deco_mesh_nodes", "Mesh nodes")
CPU = Gauge("deco_cpu_usage_ratio", "Deco CPU usage 0-1")
MEM = Gauge("deco_mem_usage_ratio", "Deco memory usage 0-1")
WAN_ONLINE = Gauge("deco_wan_online", "1 if WAN up")
HOUSE_DOWN_BPS = Gauge("deco_house_download_bps", "Whole-home download rate bytes/s")
HOUSE_UP_BPS = Gauge("deco_house_upload_bps", "Whole-home upload rate bytes/s")
CLIENT_DOWN_BPS = Gauge(
    "deco_client_download_bps", "Per-client download bytes/s", ["mac", "name"]
)
CLIENT_UP_BPS = Gauge(
    "deco_client_upload_bps", "Per-client upload bytes/s", ["mac", "name"]
)
# Gauges (persisted in state.json) so totals survive container restarts
HOUSE_DOWN_BYTES = Gauge(
    "deco_house_download_bytes_total",
    "Estimated whole-home download bytes since monitoring started",
)
HOUSE_UP_BYTES = Gauge(
    "deco_house_upload_bytes_total",
    "Estimated whole-home upload bytes since monitoring started",
)
CLIENT_DOWN_BYTES = Gauge(
    "deco_client_download_bytes_total",
    "Estimated per-client download bytes since monitoring started",
    ["mac", "name"],
)
CLIENT_UP_BYTES = Gauge(
    "deco_client_upload_bytes_total",
    "Estimated per-client upload bytes since monitoring started",
    ["mac", "name"],
)
CAP = Gauge("deco_airtel_cap_gb", "Configured Airtel FUP cap GB")
INFO = Info("deco_exporter", "Deco exporter metadata")


def _num(obj, *names, default=0.0) -> float:
    for n in names:
        if hasattr(obj, n):
            v = getattr(obj, n)
            if v is None:
                continue
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
        if isinstance(obj, dict) and n in obj and obj[n] is not None:
            try:
                return float(obj[n])
            except (TypeError, ValueError):
                pass
    return default


def _str(obj, *names, default="") -> str:
    for n in names:
        if hasattr(obj, n):
            v = getattr(obj, n)
            if v is not None:
                return str(v)
        if isinstance(obj, dict) and obj.get(n) is not None:
            return str(obj[n])
    return default


def _to_dict(obj):
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, dict):
        return obj
    return {k: getattr(obj, k) for k in dir(obj) if not k.startswith("_") and not callable(getattr(obj, k))}


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {"last_ts": 0.0, "seen": {}}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(STATE_PATH)


def rate_to_bps(value: float) -> float:
    """Normalize Deco rate fields (often kbps or B/s) to bytes/s."""
    # Heuristic: if looks like kbps (smallish), convert; if already large B/s keep
    # Deco / deco-cli commonly use kbps for client rates.
    if value <= 0:
        return 0.0
    # Treat values under 10_000_000 as kbps → B/s
    if value < 10_000_000:
        return value * 1000.0 / 8.0  # kbps → bytes/s
    return value


def scrape_once(state: dict) -> dict:
    from tplink_deco_api import DecoClient

    t0 = time.time()
    CAP.set(CAP_GB)

    with DecoClient(HOST, USER, PASSWORD) as deco:
        clients = []
        try:
            clients = deco.get_client_list() or []
        except Exception:
            traceback.print_exc()

        totals = None
        try:
            totals = deco.get_client_totals()
        except Exception:
            pass

        perf = None
        try:
            perf = deco.get_performance()
        except Exception:
            pass

        inet = None
        try:
            inet = deco.get_internet_status()
        except Exception:
            pass

        devices = []
        try:
            devices = deco.get_device_list() or []
        except Exception:
            pass

        # Debug once: dump keys so we know available fields
        if not state.get("dumped_schema"):
            sample = {}
            if clients:
                sample["client"] = list(_to_dict(clients[0]).keys())
            if totals is not None:
                sample["totals"] = _to_dict(totals)
            if perf is not None:
                sample["perf"] = _to_dict(perf)
            print("DECO_SCHEMA", json.dumps(sample, default=str)[:4000], flush=True)
            state["dumped_schema"] = True

        if perf is not None:
            cpu = _num(perf, "cpu_usage", "cpu", "cpu_usage_ratio")
            mem = _num(perf, "mem_usage", "memory", "mem_usage_ratio")
            # Some firmwares return percent 0-100
            if cpu > 1.5:
                cpu /= 100.0
            if mem > 1.5:
                mem /= 100.0
            CPU.set(cpu)
            MEM.set(mem)

        wan_up = 1.0
        if inet is not None:
            # internet_status fields vary
            st = _str(inet, "internet_status", "status", "wan_status", default="online").lower()
            wan_up = 0.0 if st in {"offline", "disconnected", "0", "false"} else 1.0
        WAN_ONLINE.set(wan_up)

        MESH_NODES.set(float(len(devices)))

        online = [c for c in clients if _num(c, "online", default=1) or _str(c, "online").lower() in {"true", "1", "yes", ""}]
        # Prefer explicit online flag when present
        if any(hasattr(c, "online") for c in clients):
            online = [c for c in clients if bool(getattr(c, "online", False))]
        CLIENTS_ONLINE.set(float(len(online)))

        now = time.time()
        last = float(state.get("last_ts") or 0)
        dt = max(0.0, min(now - last, INTERVAL * 3)) if last else 0.0

        house_down = 0.0
        house_up = 0.0

        # Prefer aggregate totals if available
        if totals is not None:
            house_down = rate_to_bps(
                _num(
                    totals,
                    "down_speed",
                    "download_speed",
                    "down_kbps",
                    "download",
                    "down",
                    "rx_rate",
                )
            )
            house_up = rate_to_bps(
                _num(
                    totals,
                    "up_speed",
                    "upload_speed",
                    "up_kbps",
                    "upload",
                    "up",
                    "tx_rate",
                )
            )
            # Absolute byte counters from Deco if firmware exposes them
            d_bytes = _num(totals, "download_bytes", "rx_bytes", "down_bytes", "traffic_down")
            u_bytes = _num(totals, "upload_bytes", "tx_bytes", "up_bytes", "traffic_up")
            if d_bytes > 0 or u_bytes > 0:
                state["house_down"] = max(float(state.get("house_down") or 0), d_bytes)
                state["house_up"] = max(float(state.get("house_up") or 0), u_bytes)
                state["using_router_bytes"] = True

        CLIENT_DOWN_BPS.clear()
        CLIENT_UP_BPS.clear()

        sum_down = 0.0
        sum_up = 0.0
        client_bytes = state.setdefault("clients", {})
        for c in online if online else clients:
            mac = _str(c, "mac", "MAC", default="unknown").upper()
            name = _str(c, "name", "hostname", "client_name", default=mac)[:64] or mac
            down = rate_to_bps(
                _num(
                    c,
                    "down_speed",
                    "down_kbps",
                    "download",
                    "download_speed",
                    "rx_rate",
                    "down_rate",
                    "bandwidth_down",
                )
            )
            up = rate_to_bps(
                _num(
                    c,
                    "up_speed",
                    "up_kbps",
                    "upload",
                    "upload_speed",
                    "tx_rate",
                    "up_rate",
                    "bandwidth_up",
                )
            )
            CLIENT_DOWN_BPS.labels(mac=mac, name=name).set(down)
            CLIENT_UP_BPS.labels(mac=mac, name=name).set(up)
            sum_down += down
            sum_up += up
            cb = client_bytes.setdefault(mac, {"name": name, "d": 0.0, "u": 0.0})
            cb["name"] = name
            if dt > 0:
                cb["d"] += down * dt
                cb["u"] += up * dt
            CLIENT_DOWN_BYTES.labels(mac=mac, name=name).set(cb["d"])
            CLIENT_UP_BYTES.labels(mac=mac, name=name).set(cb["u"])

        if house_down <= 0 and house_up <= 0:
            house_down, house_up = sum_down, sum_up

        HOUSE_DOWN_BPS.set(house_down)
        HOUSE_UP_BPS.set(house_up)
        if dt > 0 and not state.get("using_router_bytes"):
            state["house_down"] = float(state.get("house_down") or 0) + house_down * dt
            state["house_up"] = float(state.get("house_up") or 0) + house_up * dt

        HOUSE_DOWN_BYTES.set(float(state.get("house_down") or 0))
        HOUSE_UP_BYTES.set(float(state.get("house_up") or 0))

        state["last_ts"] = now
        INFO.info({"host": HOST, "cap_gb": str(CAP_GB)})
        SCRAPE_OK.set(1)
        SCRAPE_SECONDS.set(time.time() - t0)
        return state


def main() -> None:
    if not PASSWORD:
        raise SystemExit("DECO_PASSWORD is required (Deco web UI / app password)")

    start_http_server(PORT)
    print(f"deco-exporter listening on :{PORT}, host={HOST}, interval={INTERVAL}s", flush=True)
    state = load_state()
    while True:
        try:
            state = scrape_once(state)
            save_state(state)
        except Exception as exc:
            SCRAPE_OK.set(0)
            print(f"scrape error: {exc}", flush=True)
            traceback.print_exc()
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
