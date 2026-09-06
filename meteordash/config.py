"""Config loading. Every value has a default; config.toml only overrides."""
from __future__ import annotations
import os
import tomllib
from pathlib import Path

DEFAULTS = {
    "server": {"host": "127.0.0.1", "port": 8777, "title": "meteor · command deck"},
    "panels": {
        "cpu": True, "gpu": True, "fans": True, "memory": True, "battery": True,
        "integrity": True, "health": True, "vault": False, "movies": False,
    },
    "thresholds": {
        "cpu_temp": {"warn": 75, "crit": 88},
        "gpu_temp": {"warn": 75, "crit": 85},
        "cpu_load": {"warn": 80, "crit": 95},
        "gpu_load": {"warn": 85, "crit": 97},
        "mem_pct": {"warn": 85, "crit": 95},
        "disk_pct": {"warn": 80, "crit": 92},
        "battery_health": {"warn": 80, "crit": 60},
        "nvme_wear": {"warn": 80, "crit": 95},
    },
    "hardware": {},
    "disks": [{"mount": "/", "label": "root"}],
    "health": {
        "smart": True, "thermal": True, "battery_wear": True, "failed_units": True,
        "pending_updates": True, "memory_pressure": True, "load": True,
        "watch_user_units": [], "watch_files": {},
    },
    "vault": {},
    "movies": {},
}


def _merge(base, override):
    """Deep-merge override into a copy of base."""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def expand(p):
    """Expand ~ and env vars in a path string."""
    return os.path.expanduser(os.path.expandvars(p)) if isinstance(p, str) else p


def find_config(explicit=None):
    """Resolve the config path: explicit > env > repo > XDG. May not exist."""
    candidates = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get("METEORDASH_CONFIG"):
        candidates.append(os.environ["METEORDASH_CONFIG"])
    candidates.append(Path(__file__).resolve().parent.parent / "config.toml")
    candidates.append(Path(expand("~/.config/meteor-dash/config.toml")))
    for c in candidates:
        if c and Path(c).is_file():
            return Path(c)
    return None


def load(explicit=None):
    path = find_config(explicit)
    user = {}
    if path:
        with open(path, "rb") as f:
            user = tomllib.load(f)
    cfg = _merge(DEFAULTS, user)
    cfg["_config_path"] = str(path) if path else None
    return Config(cfg)


class Config:
    """Thin attribute/threshold accessor over the merged dict."""
    def __init__(self, d):
        self._d = d

    def __getitem__(self, k):
        return self._d[k]

    def get(self, k, default=None):
        return self._d.get(k, default)

    def panel(self, name):
        return bool(self._d["panels"].get(name, False))

    def threshold(self, name):
        t = self._d["thresholds"].get(name, {})
        return t.get("warn"), t.get("crit")

    @property
    def path(self):
        return self._d.get("_config_path")
