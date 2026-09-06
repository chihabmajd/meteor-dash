# meteor-dash

A single-page telemetry and health dashboard for Linux laptops, served on localhost.
Auto-detects CPU, GPUs (Nvidia / AMD / Intel), fans, battery and disks, and runs a set
of health checks over SMART wear, thermal throttling, battery wear, failed units,
pending updates and memory pressure.

Python 3.11+, standard library only. Reads sysfs, `nvidia-smi` and `smartctl`.

## Quick start

```bash
git clone https://github.com/chihabmajd/meteor-dash
cd meteor-dash
python3 -m meteordash        # http://localhost:8777
```

It runs with no config. To customise, `cp config.example.toml config.toml` and edit, or
run `scripts/install.sh` for a guided setup with the mpv hook and a desktop launcher.

## Panels

| Zone | Contents |
|---|---|
| System telemetry | CPU temp/load/clock, one card per GPU, fans, memory, battery |
| System integrity | Named services that must stay active, guard files that must exist |
| Health advisories | SMART/NVMe wear and errors, thermal throttle, battery wear, failed units, pending updates, swap and OOM pressure, load average |
| Storage (optional) | Tracked folder sizes and growth, from live folders or a markdown report |
| Movies (optional) | Backlog with watched-tracking and click-to-mark |

## Configuration

Everything lives in `config.toml` and every value is optional;
[`config.example.toml`](config.example.toml) documents the full schema and
[`docs/CONFIGURE.md`](docs/CONFIGURE.md) is a setup checklist.

- `[panels]` — enable or disable zones
- `[thresholds]` — where gauges turn amber and red
- `[health]` — which signals run, plus `watch_user_units` and `watch_files`
- `[vault]`, `[movies]` — optional modules, off by default

## Health signals

Advisory thresholds follow published guidance: NVMe `critical_warning`, SMART
`percentage_used`, reallocated sectors, drive temperature limits. See
[`docs/HEALTH_SIGNALS.md`](docs/HEALTH_SIGNALS.md).

`smartctl` cannot open a drive as a normal user, so the SMART panel shows an info note
until it is allowed through a sudoers line or a helper. Everything else runs unprivileged.

## Watched-tracking for movies

Access time is unreliable: `relatime` hides real plays and thumbnailers fake them.
meteor-dash uses, in order, an explicit `watched.txt` written by the click-to-mark
button, then mpv play history via `scripts/mpv-history.lua`, then the atime heuristic as
a flagged last resort.

## Optional dependencies

`nvidia-smi` for Nvidia telemetry, `smartmontools` for SMART, `pacman-contrib` for the
Arch update count, `mpv` for watch history.

## License

MIT — see [LICENSE](LICENSE).
