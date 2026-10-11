# TrueNAS catalog apps (install once)

TrueNAS SCALE app schemas change between versions, so **first install is done in the Apps UI**. After that, `./deploy.sh apps` starts them.

## Required apps

Install from **Apps → Discover** (or Custom App where noted):

| App | Role | Suggested host port | Notes |
|-----|------|---------------------|-------|
| Jellyfin | Media server | `30013` | Mount Movies + TV; enable Intel QSV if available |
| Seerr / Jellyseerr | Requests | `30357` | Point at Radarr + Sonarr + Jellyfin |
| Radarr | Movies | `7878` | Root folder → Movies; download client → qBit |
| Sonarr | TV | `8989` | Root folder → TV; download client → qBit |
| Prowlarr | Indexers | `9696` | Sync indexers to Radarr/Sonarr; FlareSolverr optional |
| qBittorrent | Downloads | `30024` | Incomplete + completed under Downloads |
| Bazarr | Subtitles | `6767` | Wire to Radarr/Sonarr |
| Tailscale | Remote access | — | Same Tailscale account as phone/laptop |
| Navidrome | Music | `30043` | Music library path |
| Homepage | Dashboard | `30310` | Optional bookmarks |
| File Browser | Files | `30051` | Optional |
| MeTube | YouTube DL | `30094` | Optional |

### Custom apps (JSON in `stack/custom/`)

| App | File | Port |
|-----|------|------|
| telegram-files | `stack/custom/telegram-files.json` | `30096` |
| Feishin | `stack/custom/feishin.json` | `30048` |

In TrueNAS: **Apps → Discover → Custom App** (or Install via YAML) and paste/adapt the compose from those files. Replace `TELEGRAM_API_*` and pool paths to match `.env`.

## Dataset mounts (typical)

Create datasets (or directories) then map into apps:

```
CONFIG_POOL/configs/<app>     → app config
MEDIA_POOL/Downloads          → qBit + *arr download client
MEDIA_POOL/Media/Movies       → Radarr + Jellyfin
MEDIA_POOL/Media/TV           → Sonarr + Jellyfin
MEDIA_POOL/Media/Music        → Navidrome
```

Paths come from `.env` (`CONFIG_POOL`, `MEDIA_POOL`). Run `./deploy.sh dirs` to create the tree.

## After install

```bash
./deploy.sh apps
./deploy.sh status
```

Wire once in each UI:

1. **Prowlarr** → add indexers → Apps → sync to Radarr/Sonarr  
2. **Radarr/Sonarr** → download client = qBittorrent; quality profile (e.g. Ultra-HD 2–10 GB)  
3. **Seerr** → Jellyfin + Radarr + Sonarr  
4. **Tailscale** → approve subnet routes / exit node only if you want phone internet via NAS  

See `docs/remote-access.md` for Tailscale URLs.
