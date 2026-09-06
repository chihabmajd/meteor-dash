# Configuring meteor-dash

meteor-dash runs with no config. This checklist covers the optional modules and the
integrity checks, which are the only parts that cannot be auto-detected.

## 1. See what is detected

```bash
python3 -m meteordash --check | python3 -m json.tool | head -40
```

Check that CPU temperature, each GPU, fans and battery appear. If a GPU or battery is
missing, disable that panel in `[panels]`. `[hardware]` is normally left empty and only
overridden when detection is wrong.

Identify the root disk for SMART, and see which optional tools are present:

```bash
findmnt -no SOURCE,FSTYPE -T /
lsblk -dno NAME,MODEL,SIZE
for t in nvidia-smi smartctl checkupdates mpv; do
  command -v $t >/dev/null && echo "$t: yes" || echo "$t: no"
done
```

## 2. Write config.toml

Start from `config.example.toml` and keep only what differs from the defaults.

```toml
[panels]
vault = true
movies = true

[[disks]]
mount = "/"
label = "root"

[vault]
source = "folders"
folders = [
  { path = "~/Projects",  label = "Projects", kind = "projects" },
  { path = "~/Downloads", label = "Downloads", stale_days = 90 },
  { path = "~/Movies",    label = "Movies" },
]

[movies]
folder = "~/Movies"

[health]
watch_user_units = ["my-daemon.service"]
[health.watch_files]
"Firewall rules" = "/etc/nftables.conf"
```

`kind = "projects"` gives per-project status indicators. `watch_user_units` and
`watch_files` are the integrity checks: a systemd user unit that should stay active, or
a config file whose absence would break something.

If you already generate a markdown storage report, set `[vault] source = "markdown"` and
`markdown_path` instead of `folders`; its tables are rendered generically.

Thresholds rarely need touching.

## 3. Install the mpv hook

Only needed for movie watched-tracking. `scripts/install.sh` does it, or copy
`scripts/mpv-history.lua` to `~/.config/mpv/scripts/`.

## 4. Verify

```bash
python3 -m meteordash
```

Open the URL and confirm each enabled zone shows data. If a health advisory reports that
SMART needs root, see the sudoers note in `HEALTH_SIGNALS.md`.
