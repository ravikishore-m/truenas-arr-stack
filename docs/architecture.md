# Architecture

```
Phone / Laptop
      │
      ├─ LAN ──────────► TrueNAS (NAS_HOST)
      │                      │
      └─ Tailscale ──────────┤
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
    Catalog Apps        Compose stacks      Custom apps
    (TrueNAS Apps)      (this repo)         (JSON compose)
         │                   │                   │
    Jellyfin            obs-lite            telegram-files
    Seerr               (Grafana/Prom/      Feishin
    Radarr               Netdata)
    Sonarr              adguard-home
    Prowlarr
    qBittorrent
    Bazarr
    Tailscale
    Navidrome
         │
         ▼
   MEDIA_POOL (Movies / TV / Music / Downloads)
   CONFIG_POOL (per-app configs + compose data)
```

## Repo layout

| Path | Purpose |
|------|---------|
| `deploy.sh` | Single CLI for deploy/ops |
| `deploy/` | SSH, dirs, compose, app start, status |
| `stack/` | Docker Compose stacks + custom app JSON |
| `tools/music` | FLAC organize / Telegram music pipeline |
| `tools/usb` | USB music sync job |
| `docs/` | Install + remote access guides |
| `secrets/` | SSH keys + local env (gitignored) |
| `extras/observability` | Optional heavy k8s/helm stack (not required) |

## Day-to-day

```bash
./deploy.sh status    # are services up?
./deploy.sh apps      # start catalog apps after reboot
./deploy.sh compose   # redeploy Grafana/AdGuard
```
