"""Health signals.

integrity() checks user-defined invariants, advisories() checks hardware and
system health. A failed probe reports an info note rather than crashing.
Thresholds are sourced in docs/HEALTH_SIGNALS.md.
"""
from __future__ import annotations
import glob
import json
import os
import shutil
import subprocess

from .collect import sh, read, _int
from .config import expand

ORDER = {"crit": 0, "warn": 1, "info": 2, "ok": 3}


def _sev_sort(items):
    items.sort(key=lambda c: ORDER.get(c["state"], 4))
    return items


def _summary(items):
    return {s: sum(1 for c in items if c["state"] == s)
            for s in ("ok", "warn", "crit", "info")}


def _uunit_active(unit):
    return sh("systemctl --user is-active " + unit) == "active"


def integrity(cfg, data=None):
    """User-defined 'must stay true' checks. Empty config = empty panel."""
    checks = []
    hcfg = cfg["health"]
    for unit in hcfg.get("watch_user_units", []):
        active = _uunit_active(unit)
        checks.append({"name": unit.replace(".service", ""),
                       "state": "ok" if active else "crit",
                       "detail": "active" if active else "service not running"})
    for name, path in (hcfg.get("watch_files", {}) or {}).items():
        ok = os.path.exists(expand(path))
        checks.append({"name": name, "state": "ok" if ok else "crit",
                       "detail": "present" if ok else "MISSING: " + path})
    _sev_sort(checks)
    return {"checks": checks, "summary": _summary(checks)}


def _derive_disk_device(mount):
    src = sh(f"findmnt -no SOURCE -T {mount}")
    if not src.startswith("/dev/"):
        return None
    # strip partition suffix: nvme0n1p4 -> nvme0n1 ; sda4 -> sda
    import re
    m = re.match(r"(/dev/nvme\d+n\d+)p\d+$", src)
    if m:
        return m.group(1)
    m = re.match(r"(/dev/[a-z]+)\d+$", src)
    if m:
        return m.group(1)
    return src


def _smart(cfg, out):
    if not cfg["health"].get("smart", True):
        return
    if not shutil.which("smartctl"):
        out.append({"name": "Disk SMART", "state": "info",
                    "detail": "install smartmontools for wear/error monitoring"})
        return
    for d in cfg["disks"]:
        dev = d.get("device") or _derive_disk_device(d.get("mount", "/"))
        if not dev:
            continue
        raw = sh(f"smartctl -j -H -A {dev}", timeout=5)
        try:
            j = json.loads(raw)
        except Exception:
            j = {}
        if not j or j.get("smartctl", {}).get("exit_status", 0) & 0x2:
            # bit 1 = device open failed (usually permission)
            out.append({"name": f"SMART {d.get('label', dev)}", "state": "info",
                        "detail": "needs root — see docs (sudoers/helper)"})
            continue
        warn, crit = cfg.threshold("nvme_wear")
        nl = j.get("nvme_smart_health_information_log")
        if nl:  # NVMe
            cw = nl.get("critical_warning", 0)
            used = nl.get("percentage_used", 0)
            media = nl.get("media_errors", 0)
            unsafe = nl.get("unsafe_shutdowns", 0)
            if cw:
                out.append({"name": f"SMART {d['label']}", "state": "crit",
                            "detail": f"critical_warning=0x{cw:x} — back up now"})
            elif media:
                out.append({"name": f"SMART {d['label']}", "state": "crit",
                            "detail": f"{media} media/integrity errors — back up"})
            else:
                st = "crit" if used >= crit else "warn" if used >= warn else "ok"
                out.append({"name": f"SSD wear {d['label']}", "state": st,
                            "detail": f"{used}% of rated endurance used"
                                      + (f", {unsafe} unsafe shutdowns" if unsafe > 50 else "")})
        else:  # SATA/ATA
            passed = j.get("smart_status", {}).get("passed")
            attrs = {a["name"]: a for a in
                     j.get("ata_smart_attributes", {}).get("table", [])}
            realloc = attrs.get("Reallocated_Sector_Ct", {}).get("raw", {}).get("value", 0)
            st = "ok" if passed else "crit"
            if realloc:
                st = "warn" if st == "ok" else st
            out.append({"name": f"SMART {d['label']}", "state": st,
                        "detail": "health OK" if passed and not realloc
                        else (f"{realloc} reallocated sectors" if passed
                              else "SMART overall FAILED — back up now")})


def _disk_usage(cfg, data, out):
    warn, crit = cfg.threshold("disk_pct")
    for d in (data or {}).get("disks", []):
        p = d.get("pct")
        if p is None:
            continue
        st = "crit" if p >= crit else "warn" if p >= warn else "ok"
        if st != "ok":
            free_gb = d["free"] / 1e9
            out.append({"name": f"Disk {d['label']}", "state": st,
                        "detail": f"{p}% full · {free_gb:.0f} GB free"})


def _thermal(cfg, data, out):
    if not cfg["health"].get("thermal", True):
        return
    d = data or {}
    cpu = d.get("cpu", {})
    ct = cpu.get("temp")
    warn, crit = cfg.threshold("cpu_temp")
    if ct is not None and ct >= warn:
        out.append({"name": "CPU thermal", "state": "crit" if ct >= crit else "warn",
                    "detail": f"{ct}°C — {'throttling likely' if ct >= crit else 'running hot'}"})
    # fan stall while hot = cooling failure
    fans = d.get("fans", [])
    if ct is not None and ct >= warn and fans and all(f["rpm"] == 0 for f in fans):
        out.append({"name": "Cooling", "state": "crit",
                    "detail": f"fans at 0 RPM while CPU {ct}°C — check fan"})
    for g in d.get("gpus", []):
        gt = g.get("temp")
        gw, gc = cfg.threshold("gpu_temp")
        if gt is not None and gt >= gw:
            out.append({"name": f"{g['name']} thermal",
                        "state": "crit" if gt >= gc else "warn",
                        "detail": f"{gt}°C"})


def _battery(cfg, data, out):
    if not cfg["health"].get("battery_wear", True):
        return
    b = (data or {}).get("battery")
    if not b or b.get("health") is None:
        return
    warn, crit = cfg.threshold("battery_health")
    h = b["health"]
    st = "crit" if h <= crit else "warn" if h <= warn else "ok"
    if st != "ok":
        cyc = f", {b['cycles']} cycles" if b.get("cycles") else ""
        out.append({"name": "Battery wear", "state": st,
                    "detail": f"{h}% of design capacity{cyc}"})


def _failed_units(cfg, out):
    if not cfg["health"].get("failed_units", True):
        return
    n = sh("systemctl --failed --no-legend")
    lines = [l for l in n.splitlines() if l.strip()]
    if lines:
        names = ", ".join(l.split()[0] for l in lines[:4])
        out.append({"name": "Failed units", "state": "warn",
                    "detail": f"{len(lines)} failed: {names}"})


def _updates(cfg, out):
    if not cfg["health"].get("pending_updates", True):
        return
    if shutil.which("checkupdates"):  # Arch (pacman-contrib)
        u = sh("checkupdates", timeout=8)
        lines = [l for l in u.splitlines() if l.strip()]
        if lines:
            kernel = any("linux" in l.split()[0] for l in lines)
            out.append({"name": "Updates", "state": "warn" if kernel else "info",
                        "detail": f"{len(lines)} pending"
                                  + (" (incl. kernel — reboot after)" if kernel else "")})


def _memory(cfg, data, out):
    if not cfg["health"].get("memory_pressure", True):
        return
    m = (data or {}).get("memory", {})
    swt, swu = m.get("swap_total", 0), m.get("swap_used", 0)
    if swt and swu / swt > 0.5:
        out.append({"name": "Swap pressure", "state": "warn",
                    "detail": f"{swu:.1f}/{swt:.1f} GB swap in use"})
    psi = read("/proc/pressure/memory") or ""
    for line in psi.splitlines():
        if line.startswith("some"):
            for tok in line.split():
                if tok.startswith("avg10="):
                    try:
                        if float(tok[6:]) > 10:
                            out.append({"name": "Memory stall", "state": "warn",
                                        "detail": f"PSI some avg10 {tok[6:]}%"})
                    except ValueError:
                        pass


def _load(cfg, data, out):
    if not cfg["health"].get("load", True):
        return
    try:
        la = float(read("/proc/loadavg").split()[0])
    except Exception:
        return
    cores = (data or {}).get("cpu", {}).get("cores") or os.cpu_count() or 1
    if la > 2 * cores:
        out.append({"name": "Load average", "state": "warn",
                    "detail": f"{la:.1f} on {cores} cores — heavily loaded"})


def advisories(cfg, data=None):
    out = []
    _smart(cfg, out)
    _disk_usage(cfg, data, out)
    _thermal(cfg, data, out)
    _battery(cfg, data, out)
    _failed_units(cfg, out)
    _updates(cfg, out)
    _memory(cfg, data, out)
    _load(cfg, data, out)
    if not out:
        out.append({"name": "All clear", "state": "ok",
                    "detail": "no health advisories"})
    _sev_sort(out)
    return {"items": out, "summary": _summary(out)}
