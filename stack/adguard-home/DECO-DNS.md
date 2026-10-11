# Whole-home ad block (Deco X60 + AdGuard on TrueNAS)

AdGuard runs on **192.168.68.56** and filters DNS for every device that uses it.

## 1. Finish AdGuard setup (once)

1. Open **http://192.168.68.56:30054**
2. Complete the wizard:
   - **Listen interface**: all (`0.0.0.0`)
   - **DNS port**: `53`
   - **Admin UI port**: keep `3000` inside the container (you reach it via **30054** on the NAS)
   - Create an admin user
3. In **Settings → DNS settings**, upstreams are already DoH (Cloudflare + Google). Save.

## 2. Point the whole network at AdGuard (Deco)

In the **Deco** app (main Wi‑Fi, not guest):

1. **More** → **Advanced** → **IPv4** (or **Internet** → **DNS**)
2. **Connection type** / DNS: **Manual**
3. **Primary DNS**: `192.168.68.56`
4. **Secondary DNS**: leave **empty** or use the same `192.168.68.56`  
   (Do **not** use 1.1.1.1 or 8.8.8.8 as secondary — phones/TVs may bypass filtering.)
5. Save and reboot Deco if prompted.

Guest Wi‑Fi: enable “use same DNS as main network” if available, or set the same primary DNS on the guest SSID.

## 3. Verify

On a phone on Wi‑Fi (Wi‑Fi off → on to refresh DHCP):

- Browse to **http://192.168.68.56:30054** → **Dashboard** should show queries.
- Visit `https://adguard.com/test/` — should show AdGuard DNS is used.

## 4. Optional

- **Settings → Client settings**: per-device rules, kid devices, etc.
- **Filters → DNS blocklists**: enable more lists if you want stricter blocking.
- Reserve **192.168.68.56** for the NAS in Deco so DNS never breaks.

## AdGuard vs Pi-hole here

| | AdGuard Home | Pi-hole |
|---|--------------|---------|
| Deco as router | Custom DNS only (what we use) | Same |
| UI / per-client | Strong | Good |
| TrueNAS | This stack | Works, similar DNS step |

Pi-hole would use the same Deco step; only the UI container differs.
