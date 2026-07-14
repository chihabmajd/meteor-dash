# Health signals & thresholds

The advisory engine (`meteordash/health.py`) turns raw system state into a small
set of *actionable* warnings. This documents each signal, why it matters, the
threshold used, and the source. Thresholds are configurable under
`[thresholds]` and `[health]` in `config.toml`.

## Storage — SMART (needs `smartmontools`)

| Signal | Meaning | meteor-dash action |
|---|---|---|
| NVMe `critical_warning` | controller flags a temperature/reliability problem; any non-zero = investigate now | **crit** — "back up now" |
| NVMe `media_errors` / SATA overall FAILED | media/data-integrity errors | **crit** |
| NVMe `percentage_used` | endurance "gas gauge": 0 = new, 100 = rated endurance reached | **warn ≥80%, crit ≥95%** |
| SATA `Reallocated_Sector_Ct` | remapped bad sectors; climbing = failing | **warn** if non-zero |
| Drive temperature | HDDs unreliable >50 °C; SSDs should stay <70 °C. Lowering temp ~5 °C measurably cuts failure rate | folds into thermal |

Sources: [NVM Express — error reporting & SMART log pages](https://nvmexpress.org/resource/features-for-error-reporting-smart-log-pages-failures-and-management-capabilities-in-nvme-architectures/),
[smartctl guide (Linuxize)](https://linuxize.com/post/smartctl-command-in-linux/),
[SMART disk monitoring (Linux Journal)](https://www.linuxjournal.com/article/6983).

### Letting SMART run without root

`smartctl` opens the block device directly, which needs privilege. Options:

- **sudoers (recommended):** allow just this command, no password —
  ```
  youruser ALL=(root) NOPASSWD: /usr/bin/smartctl -j -H -A /dev/nvme0n1
  ```
  then set `[[disks]] device` accordingly. (A future flag can prepend `sudo`.)
- Or run the dashboard's SMART probe from a small root timer that writes JSON to
  a world-readable file the module reads. Until then the panel shows an
  informational "needs root" note — it never fails.

## Thermal

- CPU/GPU temperature vs `[thresholds] cpu_temp` / `gpu_temp` (warn/crit °C).
- **Fan-stall detection:** all fans at 0 RPM while the CPU is hot ⇒ **crit**
  (possible cooling failure). Sustained operation near Tjmax implies throttling.

## Battery wear

`charge_full / charge_full_design` (or `energy_*`) gives health as a % of design
capacity; `cycle_count` when exposed. Warn under `[thresholds] battery_health`
(default 80%). A charge cap (e.g. 80%) slows calendar wear on laptops kept
plugged in.

## System services & updates

- **Failed units:** `systemctl --failed` — any failed unit is surfaced.
- **Pending updates:** on Arch, `checkupdates` (from `pacman-contrib`); a pending
  **kernel** update is highlighted because you should reboot after it. Other
  distros: wire your package manager's equivalent (contributions welcome).

## Memory pressure

- Swap in use >50% of swap size ⇒ **warn** (thrash risk).
- Linux **PSI** `/proc/pressure/memory` `some avg10 > 10%` ⇒ **warn** (real
  stalls waiting on memory).

## Load

`loadavg[0]` vs core count; >2× cores ⇒ **warn** (heavily loaded / possible
runaway). Expected during compiles or gaming — informational.

---

All probes are best-effort: a missing tool or permission yields an `info` note,
never a crash or a false "ok".
