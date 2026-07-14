"""Movie backlog with *precise* watched tracking.

Replaces the old atime heuristic (unreliable under relatime; false-positives
from thumbnailers/copies) with real signals, in priority order:
  1. an explicit watched list  (watched_file, one title/filename per line)
  2. mpv play history          (mpv_log, written by scripts/mpv-history.lua)
  3. atime heuristic           (last resort, flagged as low-confidence)

`mark_watched()` powers the dashboard's click-to-mark button.
"""
from __future__ import annotations
import json
import os
import re
from pathlib import Path

from ..config import expand

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".m4v", ".webm", ".wmv", ".flv"}


def _norm(title):
    """Normalise a filename/title to a comparable key: drop year, quality, ext."""
    t = re.sub(r"\.[a-z0-9]{2,4}$", "", title, flags=re.I)
    t = re.sub(r"[._]", " ", t)
    t = re.sub(r"\b(19|20)\d{2}\b.*$", "", t)  # cut at the year and everything after
    t = re.sub(r"\b(1080p|720p|2160p|4k|bluray|web-?rip|x264|x265|hevc|aac|dvdrip)\b.*$",
               "", t, flags=re.I)
    t = re.sub(r"[^a-z0-9 ]", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def _load_watched_list(path):
    if not path or not os.path.exists(path):
        return set()
    keys = set()
    for line in Path(path).read_text(errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            keys.add(_norm(line))
    return keys


def _load_mpv_finished(path, frac):
    """Return set of normalised keys played past `frac` of their duration."""
    keys = set()
    if not path or not os.path.exists(path):
        return keys
    for line in Path(path).read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        pos, dur = e.get("pos"), e.get("duration")
        name = e.get("filename") or e.get("path", "")
        if not name:
            continue
        if dur and pos and dur > 0 and (pos / dur) >= frac:
            keys.add(_norm(os.path.basename(name)))
        elif e.get("watched"):
            keys.add(_norm(os.path.basename(name)))
    return keys


def _entries(folder):
    out = []
    root = Path(folder)
    if not root.exists():
        return out
    for entry in root.iterdir():
        if entry.name.startswith("."):
            continue
        if entry.is_file() and entry.suffix.lower() in VIDEO_EXTS:
            videos = [entry]
        elif entry.is_dir():
            videos = [f for f in entry.rglob("*") if f.suffix.lower() in VIDEO_EXTS]
        else:
            videos = []
        if not videos:
            continue
        size = sum(f.stat().st_size for f in videos)
        mtime = max(f.stat().st_mtime for f in videos)
        atime = max(f.stat().st_atime for f in videos)
        out.append({"name": entry.name, "size": size, "mtime": mtime, "atime": atime})
    return out


def collect(cfg):
    mc = cfg["movies"]
    folder = expand(mc.get("folder", "~/Movies"))
    watched_file = expand(mc.get("watched_file", "~/.config/meteor-dash/watched.txt"))
    mpv_log = expand(mc.get("mpv_log", "~/.config/meteor-dash/mpv-history.jsonl"))
    frac = float(mc.get("finished_fraction", 0.85))

    wl = _load_watched_list(watched_file)
    ml = _load_mpv_finished(mpv_log, frac)
    entries = _entries(folder)
    out = []
    for e in entries:
        key = _norm(e["name"])
        if key in wl:
            watched, how = True, "marked"
        elif key in ml:
            watched, how = True, "mpv"
        elif (e["atime"] - e["mtime"]) > 300:
            watched, how = True, "atime?"      # low confidence
        else:
            watched, how = False, ""
        out.append({"name": e["name"], "size": e["size"], "mtime": e["mtime"],
                    "watched": watched, "how": how})
    out.sort(key=lambda m: (m["watched"], -m["size"]))
    watched_n = sum(1 for m in out if m["watched"])
    backlog = sum(m["size"] for m in out if not m["watched"])
    return {"ok": bool(entries), "total": len(out), "watched": watched_n,
            "backlog": backlog, "movies": out, "watched_file": watched_file}


def mark_watched(cfg, title):
    """Append a title to the watched list (click-to-mark). Idempotent."""
    watched_file = expand(cfg["movies"].get(
        "watched_file", "~/.config/meteor-dash/watched.txt"))
    os.makedirs(os.path.dirname(watched_file), exist_ok=True)
    existing = _load_watched_list(watched_file)
    if _norm(title) in existing:
        return True
    with open(watched_file, "a") as f:
        f.write(title.strip() + "\n")
    return True
