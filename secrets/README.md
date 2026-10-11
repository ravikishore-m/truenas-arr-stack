# Secrets (local only)

This directory holds machine-local credentials. **Nothing private is committed.**

| File | Purpose |
|------|---------|
| `.nas-keys/id_ed25519_truenas` | SSH private key (`./deploy.sh ssh`) |
| `.nas-keys/truenas_api.key` | Optional TrueNAS API key |
| `deco.env` | Optional Deco router password for bandwidth exporter |

```bash
cp deco.env.example deco.env   # then edit
```
