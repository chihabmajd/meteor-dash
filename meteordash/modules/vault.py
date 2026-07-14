"""Optional storage-intelligence module.

Two sources, chosen in config:
  source = "folders"   -> scan configured folders live (size, count, age,
                          project status). Works for anyone, zero prep.
  source = "markdown"  -> parse a pre-generated markdown report (e.g. a
                          personal Pilot.md pipeline). Power-user path.

Off by default; enabled via [vault] in config.toml.
"""
from __future__ import annotations
import os
import re
import subprocess
import time
from pathlib import Path

from ..config import expand

STACK_SIGNALS = [("requirements.txt", "Python"), ("pyproject.toml", "Python"),
                 ("package.json", "Node"), ("Cargo.toml", "Rust"), ("go.mod", "Go")]


def _du_bytes(path):
    try:
        r = subprocess.run(["du", "-sb", "--apparent-size", str(path)],
                           capture_output=True, text=True, timeout=30)
        return int(r.stdout.split()[0]) if r.returncode == 0 else 0
    except Exception:
        return 0


def _human(n):
    for u in ("B", "K", "M", "G", "T"):
        if n < 1024:
            return f"{n:.0f}{u}" if u == "B" else f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}P"


def _scan_folder(path, spec):
    p = Path(path)
    if not p.exists():
        return None
    size = _du_bytes(p)
    try:
        count = sum(1 for _ in p.rglob("*") if _.is_file())
    except OSError:
        count = 0
    mtime = p.stat().st_mtime
    entry = {"label": spec.get("label", p.name), "path": str(p),
             "bytes": size, "size": _human(size), "files": count,
             "modified": time.strftime("%Y-%m-%d", time.localtime(mtime)),
             "kind": spec.get("kind", "")}
    if spec.get("kind") == "projects":
        entry["children"] = _scan_projects(p, spec.get("stale_days", 60))
    if spec.get("stale_days"):
        entry["stale"] = _count_stale(p, spec["stale_days"])
    return entry


def _scan_projects(root, stale_days):
    out = []
    now = time.time()
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        mtime = d.stat().st_mtime
        stack = next((lbl for fn, lbl in STACK_SIGNALS if (d / fn).exists()), "")
        out.append({"name": d.name, "stack": stack, "size": _human(_du_bytes(d)),
                    "fresh": (now - mtime) <= stale_days * 86400,
                    "modified": time.strftime("%Y-%m-%d", time.localtime(mtime))})
    return out


def _count_stale(path, days):
    cutoff = time.time() - days * 86400
    try:
        files = [f for f in Path(path).iterdir() if f.is_file()]
    except OSError:
        return {"count": 0, "bytes": 0}
    stale = [f for f in files if f.stat().st_mtime < cutoff]
    return {"count": len(stale), "bytes": sum(f.stat().st_size for f in stale)}


def _from_folders(cfg):
    vc = cfg["vault"]
    folders = []
    for spec in vc.get("folders", []):
        e = _scan_folder(expand(spec["path"]), spec)
        if e:
            folders.append(e)
    folders.sort(key=lambda f: -f["bytes"])
    # disk of the first folder's filesystem
    disk = None
    if folders:
        try:
            s = os.statvfs(folders[0]["path"])
            total = s.f_blocks * s.f_frsize
            free = s.f_bavail * s.f_frsize
            disk = {"total": _human(total), "free": _human(free),
                    "pct": round(100 * (total - free) / total) if total else 0}
        except OSError:
            pass
    return {"ok": True, "source": "folders", "folders": folders, "disk": disk}


def _from_markdown(cfg):
    """Parse a markdown report into sections of tables/paragraphs (generic)."""
    path = expand(cfg["vault"].get("markdown_path", ""))
    if not path or not os.path.exists(path):
        return {"ok": False}
    lines = Path(path).read_text(errors="replace").splitlines()
    updated, i = "", 0
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            m = re.match(r"updated:\s*(.+)", lines[i].strip())
            if m:
                updated = m.group(1).strip()
            i += 1
        i += 1
    sections, cur = [], None
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("## "):
            cur = {"title": s[3:].strip(), "blocks": []}
            sections.append(cur)
        elif s.startswith("|") and cur is not None:
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in
                         re.split(r"(?<!\\)\|", lines[i].strip().strip("|"))]
                rows.append(cells)
                i += 1
            rows = [r for r in rows if not all(re.match(r"^-+$", c or "-") for c in r)]
            if rows:
                cur["blocks"].append({"t": "table", "head": rows[0], "rows": rows[1:]})
            continue
        elif s and cur is not None and not s.startswith("# ") and not s.startswith("> "):
            cur["blocks"].append({"t": "p", "text": s})
        i += 1
    return {"ok": True, "source": "markdown", "updated": updated, "sections": sections}


def collect(cfg):
    src = cfg["vault"].get("source", "folders")
    return _from_markdown(cfg) if src == "markdown" else _from_folders(cfg)
