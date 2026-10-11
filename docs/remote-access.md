# Remote access via Tailscale

**Node:** `truenas-arr`  
**Tailscale IP:** `100.107.194.4`  
**MagicDNS:** `truenas-arr.tailaf4d33.ts.net`

Connect your phone/laptop to Tailscale (same account), then open:

## App launcher (HTTPS, Tailnet only)
https://truenas-arr.tailaf4d33.ts.net:8443/

## Running apps

| App | URL |
|-----|-----|
| TrueNAS UI | https://truenas-arr.tailaf4d33.ts.net/ |
| Jellyfin | http://truenas-arr.tailaf4d33.ts.net:30013 |
| Seerr | http://truenas-arr.tailaf4d33.ts.net:30357 |
| Radarr | http://truenas-arr.tailaf4d33.ts.net:7878 |
| Sonarr | http://truenas-arr.tailaf4d33.ts.net:8989 |
| Prowlarr | http://truenas-arr.tailaf4d33.ts.net:9696 |
| Bazarr | http://truenas-arr.tailaf4d33.ts.net:6767 |
| qBittorrent | http://truenas-arr.tailaf4d33.ts.net:30024 |
| Arr Dashboard | http://truenas-arr.tailaf4d33.ts.net:30310 |
| Navidrome | http://truenas-arr.tailaf4d33.ts.net:30043 |
| Feishin | http://truenas-arr.tailaf4d33.ts.net:30048 |
| File Browser | http://truenas-arr.tailaf4d33.ts.net:30051 |
| MeTube | http://truenas-arr.tailaf4d33.ts.net:30094 |
| Telegram Files | http://truenas-arr.tailaf4d33.ts.net:30096 |
| AdGuard Home | http://truenas-arr.tailaf4d33.ts.net:30054 |
| Grafana | http://truenas-arr.tailaf4d33.ts.net:30091 |
| Prometheus | http://truenas-arr.tailaf4d33.ts.net:30090 |
| Netdata | http://truenas-arr.tailaf4d33.ts.net:19999 |

IP form: `http://100.107.194.4:PORT`

## Notes
- Apps were already bound to `0.0.0.0` — reachable on the Tailscale IP as soon as Tailscale is connected.
- Homepage bookmark/service **hrefs** use MagicDNS for remote clicks; widgets still use LAN IP for on-NAS monitoring.
- Landing page is kept alive by cron `ts-landing.sh` every 5 minutes.
