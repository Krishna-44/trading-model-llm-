# AIFOS on Raspberry Pi — deployment status & bridge

This ties the AIFOS build work to the Pi-setup effort. Short version: **the code
is 100% Pi-ready and already "merged"** — the Pi clones `main`, so it gets every
improvement automatically. The only blocker is **hardware** (the Pi never booted).

## What the Pi runs (and gets for free via `git clone`)

The Pi runs the **paper-forward marathon on :8001** — the exact same FastAPI app
that runs on the Mac via launchd. Cloning `main` pulls all of this session's work:

- **Strategies** — the full library incl. the promoted, cooking-validated trend
  set: `ema_trend_fast` (10/30/100), `supertrend_fast` (7/4/15), and
  `ema_trend_fib` (13/34/89 — the most MC-robust discovery, 3/4 markets robust +
  cost-survive 3/4). `heikin_trend` on-watch. Cooking keeps discovering 24/7.
- **Safety gates (all block-only, all tested)** — bad-tick execution guard
  (refuses corrupt quotes like the EURINR 9197 that once booked −4.13M),
  directional-balance / portfolio-heat (no 100%-one-sided book), persistent
  run-to-ruin halt (survives restarts), min-hold churn guard (no flip-flop
  commission bleed), vol-regime + event-window gates, correlation gate.
- **Live-money safety** — monitor-only now enforced on *every* live broker path +
  the deployment gate; live trading stays OFF until 6/6 readiness gates pass.

So there is nothing to "port" — `main` IS the Pi build.

## Deployment steps (once hardware is ready)

```bash
# on the Pi (64-bit Raspberry Pi OS / Ubuntu, Pi 4 4GB+ or Pi 5):
git clone <repo-url> ~/ai-trading-os
cd ~/ai-trading-os
./scripts/raspberry-pi-setup.sh        # python3.11 venv + deps + installs systemd units
sudo systemctl enable --now aifos-paper.service aifos-paper-watchdog.timer
journalctl -u aifos-paper -f           # watch it boot the marathon
curl -s localhost:8001/api/health      # {"status":"ok"}
```

The systemd unit (`scripts/aifos-paper.service`) mirrors the macOS launchd plist:
`Restart=always` (KeepAlive), `RestartSec=10` (throttle), `MemoryMax=1500M` (Pi
OOM protection), watchdog companion timer. Marathon arms at boot.

## Config parity note

| Var | macOS launchd (active) | Pi systemd | Why |
|---|---|---|---|
| `AIFOS_CONFIDENCE_THRESHOLD` | `0.10` | `0.30` | Mac = aggressive debug bar; Pi = more selective. Both are forward-test bars BELOW the production `0.62`. Align to taste. |
| everything else | — | — | identical (broker=paper, marathon-on-start, max-positions=8, llm=none) |

## Hardware blockers (the actual gate — unchanged)

The Pi has **never booted**. To deploy it needs:
1. **A proper Pi 5 PSU — 5V/5A (27W) USB-C.** A phone charger is insufficient and
   causes brownout/throttling/SD-corruption.
2. **A reliable boot drive — a USB SSD, NOT an SD card.** The autonomous loop
   writes SQLite every cycle; SD cards die in months under that load, and the
   flaky reader/dongle corrupted writes mid-flash last time (I/O error).
3. **Network onboarding** — Pi 5 WiFi is `brcmfmac43455`; Bookworm uses
   NetworkManager (`nmcli`), not `wpa_supplicant`. Use the imager's network preset
   or ethernet for first boot.

Once those three are sorted, the deploy above is ~10 minutes and fully hands-off.

## Security reminders (from chat)
- Rotate the AngelOne PIN + API key + Gemini key that were shared in chat.
- Change the Pi password after first boot; don't paste WiFi creds in chat.
- Real money only at 6/6 readiness gates, ₹2,000 cap — never before.
