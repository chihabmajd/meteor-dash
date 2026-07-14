# meteor-dash

A local, single-page **telemetry + health HUD** for Linux laptops — a dark
industrial command deck for your machine. It auto-detects your CPU, GPUs
(Nvidia / AMD / Intel), fans, battery and disks, runs a **health advisory
engine** over real signals (SMART wear, thermal throttling, battery wear,
failed services, pending kernel updates, memory pressure…), and can optionally
track your storage and movie backlog.

No cloud, no daemon zoo, no dependencies beyond Python 3.11+. It reads sysfs,
`nvidia-smi`, and `smartctl`, serves one page on `localhost`, and gets out of
the way.

## Why

Vendor dashboards are typically Windows-only and closed. meteor-dash
gives you the useful 20% — live telemetry and *actionable* health warnings — in
a page you own and can read the source of.

## Quick start

```bash
git clone https://github.com/YOU/meteor-dash ~/Projects/meteor-dash
cd ~/Projects/meteor-dash
python3 -m meteordash            # runs with sensible auto-detected defaults
# open http://localhost:8777
```

That's it — it works with **no config**. To customise, copy the schema:

```bash
cp config.example.toml config.toml   # then edit
# or run scripts/install.sh for the guided setup (+ mpv hook + launcher)
```

## What it shows

| Zone | Contents |
|---|---|
| **System Telemetry** | CPU (temp/load/clock), one card per GPU, fans, memory, battery |
| **System Integrity** | your "must stay true" checks — named services active, guard files present |
| **Health Advisories** | SMART/NVMe wear & errors, thermal throttle, battery wear, failed units, pending updates, swap/OOM pressure, load average |
| **Storage Ops** *(opt)* | tracked-folder sizes, projects, growth — from live folders or a markdown report |
| **Movies** *(opt)* | backlog with **precise** watched tracking + click-to-mark |

## Configuration

Everything lives in `config.toml`; every value is optional (see
[`config.example.toml`](config.example.toml) for the fully-documented schema).
Highlights:

- `[panels]` — turn zones on/off
- `[thresholds]` — where gauges/advisories go amber/red
- `[health]` — which signals to run; `watch_user_units` / `watch_files` for your
  own integrity checks
- `[vault]` / `[movies]` — the optional personal modules (off by default)

## Health signals & sources

The advisory thresholds follow published guidance (NVMe `critical_warning`,
SMART `percentage_used`, reallocated sectors, drive temp limits, etc.). See
[`docs/HEALTH_SIGNALS.md`](docs/HEALTH_SIGNALS.md).

> **SMART needs root.** `smartctl` can't open the drive as a normal user; the
> panel shows an "info" note until you allow it (a sudoers line or a small
> helper — see the health-signals doc). Everything else runs unprivileged.

## Movie watched-tracking

The old-school way (guessing from file access time) is unreliable — `relatime`
hides real plays and thumbnailers fake them. meteor-dash uses, in order:

1. an explicit `watched.txt` (and the **click-to-mark** button writes to it)
2. **mpv play history** via `scripts/mpv-history.lua` (auto, precise)
3. the atime heuristic only as a flagged last resort

## Requirements

- Python **3.11+** (stdlib only — uses `tomllib`)
- Optional: `nvidia-smi` (Nvidia telemetry), `smartmontools` (SMART),
  `pacman-contrib`/`checkupdates` (Arch update count), `mpv` (watch history)

## License

MIT — see [LICENSE](LICENSE).
