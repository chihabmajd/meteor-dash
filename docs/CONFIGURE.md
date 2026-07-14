# Configuring meteor-dash

This checklist covers the optional modules and the integrity checks, which
are the only parts that cannot be auto-detected.

**Goal:** generate `./config.toml` tailored to this machine. Detect what you can;
only ask the user about *preferences* you cannot infer.

---

## Step 1 — Probe the hardware (don't ask, detect)

Run these and use the results to fill `[hardware]`, `[[disks]]`, and thresholds.
Everything auto-detects, so you usually leave `[hardware]` empty — only override
when detection is wrong.

```bash
python3 -m meteordash --check | head -c 4000   # one-shot JSON of what it sees
```

Sanity-check that CPU temp, each GPU, fans, and battery appear. If a GPU or
battery is missing, note it (you may disable that panel). Identify the root disk
and its device for SMART:

```bash
findmnt -no SOURCE,FSTYPE -T /
lsblk -dno NAME,MODEL,SIZE
```

Check which optional tools exist (drives which health signals work):

```bash
for t in nvidia-smi smartctl checkupdates mpv; do command -v $t >/dev/null && echo "$t: yes" || echo "$t: no"; done
```

## Step 2 — Ask the user (preferences only)

Ask a *short* set of questions — ideally as multiple-choice. Suggested:

1. **Which optional zones do you want?**
   - Storage tracking (folder sizes, projects, growth)?
   - Movie backlog with watched-tracking?
2. **If storage tracking:** which folders should it watch? Offer sensible
   defaults from what exists: `~/Projects`, `~/Downloads`, `~/Documents`,
   `~/Documents`, `~/Movies`, `~/Music`. For a code folder, mark `kind = "projects"`
   so it gets per-project status LEDs. For `~/Downloads`, set `stale_days = 90`.
3. **If movies:** confirm the movies folder (default `~/Movies`) and offer to
   install the mpv watch-history hook (`scripts/install.sh`, or copy
   `scripts/mpv-history.lua` to `~/.config/mpv/scripts/`).
4. **Any "must stay true" integrity checks?** e.g. a systemd --user service that
   should stay active, or a config file whose absence would break something.
   These become `[health] watch_user_units` and `[health.watch_files]`.

Don't ask about thresholds unless the user brings it up — the defaults are good.

## Step 3 — Write config.toml

Start from `config.example.toml`, keep only what differs from defaults, and fill
the modules the user opted into. Minimal example:

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
watch_user_units = ["my-daemon.service"]     # only if the user named one
[health.watch_files]
# "Some guard" = "/etc/somewhere/important.conf"
```

**Power-user note:** if the user already has a pipeline that generates a markdown
storage report (tables of folder sizes, projects, etc.), set
`[vault] source = "markdown"` and `markdown_path = "..."` instead of `folders`.
meteor-dash will render its tables generically.

## Step 4 — Verify

```bash
python3 -m meteordash --check | python3 -m json.tool | head -40   # no crash, panels populated
python3 -m meteordash            # then open the URL and eyeball it
```

Confirm each enabled zone shows data. If a health advisory says SMART "needs
root", point the user at the sudoers note in `docs/HEALTH_SIGNALS.md`. Done.
