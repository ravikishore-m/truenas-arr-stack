# TrueNAS *arr media stack

Deploy Jellyfin + Seerr + Radarr/Sonarr/Prowlarr/qBit (+ observability & AdGuard) on TrueNAS SCALE with one CLI.

## Quick start (fresh NAS)

```bash
cp .env.example .env
# edit NAS_HOST, CONFIG_POOL, MEDIA_POOL

./deploy.sh ssh          # paste printed pubkey into TrueNAS → Users → SSH
./deploy.sh dirs         # create config + media folders

# Install catalog apps once in TrueNAS UI — see docs/catalog-apps.md

./deploy.sh compose      # Grafana / Netdata / AdGuard
./deploy.sh apps         # start everything
./deploy.sh status
```

Or after SSH + catalog apps are ready:

```bash
./deploy.sh all
```

## Day-to-day

| Command | What it does |
|---------|----------------|
| `./deploy.sh status` | Ping Jellyfin, *arr, Grafana, … |
| `./deploy.sh apps` | Start catalog apps after reboot |
| `./deploy.sh compose` | Redeploy obs-lite + AdGuard |
| `./deploy.sh compose obs-lite` | Redeploy Grafana stack only |
| `./deploy.sh stop` | Stop catalog apps |

## Layout

```
deploy.sh          ← you only need this
deploy/            SSH, dirs, compose, app start, status
stack/             docker-compose (obs-lite, adguard) + custom app JSON
tools/music/       FLAC / Telegram music helpers
tools/usb/         USB music sync
docs/              catalog install + Tailscale remote access
secrets/           SSH keys & passwords (gitignored)
extras/            optional heavy observability (k8s/helm)
```

## Secrets

```bash
cp secrets/deco.env.example secrets/deco.env   # optional Deco bandwidth exporter
# SSH key is created by ./deploy.sh ssh → secrets/.nas-keys/
```

Never commit `.env` or `secrets/` private files.

## Docs

- [Catalog apps install](docs/catalog-apps.md) — required TrueNAS UI step
- [Architecture](docs/architecture.md)
- [Remote access (Tailscale)](docs/remote-access.md)

## LAN ports (defaults)

| Service | Port |
|---------|------|
| Jellyfin | 30013 |
| Seerr | 30357 |
| Radarr | 7878 |
| Sonarr | 8989 |
| Prowlarr | 9696 |
| Bazarr | 6767 |
| qBittorrent | 30024 |
| Grafana | 30091 |
| Netdata | 19999 |
| AdGuard UI | 30054 |
| AdGuard DNS | 53 |
