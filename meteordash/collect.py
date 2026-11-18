"""Vendor-generic hardware telemetry from sysfs, DRM and nvidia-smi.

CPU temp comes from known hwmon driver names, fans from any fan*_input,
the battery from any /sys/class/power_supply/BAT*.
"""
from __future__ import annotations
import glob
import os
import shutil
import json
import subprocess
import time

_prev_cpu = [0, 0]
_prev_core = {}
_prev_rate = {}
_prev_proc = {}
_CLK = os.sysconf("SC_CLK_TCK")
_PAGE = os.sysconf("SC_PAGE_SIZE")

CPU_HWMON = ("k10temp", "zenpower", "coretemp")   # AMD, AMD alt, Intel
CPU_TEMP_LABEL = {"k10temp": ("Tctl", "Tccd1"), "coretemp": ("Package id 0",)}  # preferred label per driver


def sh(cmd, timeout=2):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True,
                              text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""


def read(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return default


def _int(path, default=0):
    v = read(path)
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def hwmon_by_name(name):
    for p in glob.glob("/sys/class/hwmon/hwmon*"):
        if read(os.path.join(p, "name")) == name:
            return p
    return None


def _hwmon_temp(hw, prefer=()):
    """Return a temperature in °C from a hwmon dir, preferring labelled inputs."""
    if not hw:
        return None
    for lf in sorted(glob.glob(os.path.join(hw, "temp*_label"))):
        if read(lf) in prefer:
            inp = lf.replace("_label", "_input")
            if os.path.exists(inp):
                return round(_int(inp) / 1000)
    inp = os.path.join(hw, "temp1_input")
    return round(_int(inp) / 1000) if os.path.exists(inp) else None


def cpu_usage():
    global _prev_cpu
    try:
        vals = list(map(int, read("/proc/stat").splitlines()[0].split()[1:]))
        idle, total = vals[3] + vals[4], sum(vals)
        di, dt = idle - _prev_cpu[0], total - _prev_cpu[1]
        _prev_cpu = [idle, total]
        return 0 if dt <= 0 else round(100 * (1 - di / dt))
    except Exception:
        return 0


def cpu_cores():
    """Per-core load in %, from /proc/stat deltas (zeros on the first call)."""
    out = []
    for line in (read("/proc/stat") or "").splitlines()[1:]:
        if not line.startswith("cpu"):
            break
        p = line.split()
        vals = list(map(int, p[1:]))
        idle, total = vals[3] + vals[4], sum(vals)
        pi, pt = _prev_core.get(p[0], (idle, total))
        _prev_core[p[0]] = (idle, total)
        dt = total - pt
        out.append(0 if dt <= 0 else round(100 * (1 - (idle - pi) / dt)))
    return out


def _rate(key, value, now):
    """Bytes/s since the previous call for this key (None on the first call)."""
    prev = _prev_rate.get(key)
    _prev_rate[key] = (value, now)
    if not prev or now <= prev[1] or value < prev[0]:
        return None
    return round((value - prev[0]) / (now - prev[1]))


def cpu(cfg_hw):
    hw_name = cfg_hw.get("cpu_hwmon")
    hw = hwmon_by_name(hw_name) if hw_name else None
    if not hw:
        for n in CPU_HWMON:
            hw = hwmon_by_name(n)
            if hw:
                hw_name = n
                break
    freqs = [_int(f) for f in glob.glob(
        "/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq")]
    model = ""
    for line in (read("/proc/cpuinfo") or "").splitlines():
        if line.startswith("model name"):
            model = line.split(":", 1)[1].strip()
            break
    return {
        "temp": _hwmon_temp(hw, CPU_TEMP_LABEL.get(hw_name, ())),
        "usage": cpu_usage(),
        "ghz": round(max(freqs) / 1e6, 1) if freqs else None,
        "governor": read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor") or None,
        "cores": os.cpu_count(),
        "per_core": cpu_cores(),
        "model": model,
    }


def _nvidia():
    if not shutil.which("nvidia-smi"):
        return []
    q = ("nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,"
         "power.draw,memory.used,memory.total --format=csv,noheader,nounits")
    out = sh(q)
    gpus = []
    for line in out.splitlines():
        if "," not in line:
            continue
        try:
            name, t, u, p, mu, mt = [x.strip() for x in line.split(",")]
            gpus.append({
                "vendor": "nvidia", "name": name.replace("NVIDIA ", ""),
                "temp": round(float(t)), "util": round(float(u)),
                "watt": round(float(p)), "vram": round(float(mu)),
                "vram_total": round(float(mt)),
            })
        except ValueError:
            continue
    return gpus


def _amd():
    gpus = []
    for dev in glob.glob("/sys/class/drm/card*/device"):
        drv = os.path.join(dev, "driver")
        if not (os.path.islink(drv) and os.path.realpath(drv).endswith("amdgpu")):
            continue
        busy = _int(os.path.join(dev, "gpu_busy_percent"), -1)
        temp = None
        for hw in glob.glob(os.path.join(dev, "hwmon/hwmon*")):
            if read(os.path.join(hw, "name")) == "amdgpu":
                temp = _hwmon_temp(hw)
                break
        gpus.append({
            "vendor": "amd", "name": _read_drm_name(dev) or "Radeon",
            "temp": temp, "util": busy if busy >= 0 else None,
            "watt": None, "vram": None, "vram_total": None,
        })
    return gpus


def _read_drm_name(dev):
    # skip the PCI-id database; use the driver's marketing name if it exposes one
    return read(os.path.join(dev, "product_name"))


def gpus(cfg_hw):
    found = _nvidia() + _amd()
    return found


def fans(cfg_hw):
    names = set(cfg_hw.get("extra_fans", []))
    out = []
    seen = set()
    for hw in glob.glob("/sys/class/hwmon/hwmon*"):
        nm = read(os.path.join(hw, "name")) or ""
        for fi in sorted(glob.glob(os.path.join(hw, "fan*_input"))):
            rpm = _int(fi, -1)
            if rpm < 0:
                continue
            idx = os.path.basename(fi).replace("_input", "")
            label = read(fi.replace("_input", "_label")) or f"{nm}:{idx}"
            key = (nm, idx)
            if key in seen:
                continue
            seen.add(key)
            out.append({"label": label, "rpm": rpm})
    return out


def battery(cfg_hw):
    dev = cfg_hw.get("battery")
    bats = ([f"/sys/class/power_supply/{dev}"] if dev
            else sorted(glob.glob("/sys/class/power_supply/BAT*")))
    for b in bats:
        if not os.path.isdir(b):
            continue
        pct = read(os.path.join(b, "capacity"))
        if pct is None:
            continue
        # charge_* (µAh) or energy_* (µWh) depending on the platform
        full = _int(os.path.join(b, "charge_full")) or _int(os.path.join(b, "energy_full"))
        design = (_int(os.path.join(b, "charge_full_design"))
                  or _int(os.path.join(b, "energy_full_design")))
        return {
            "pct": pct,
            "status": read(os.path.join(b, "status")),
            "limit": read(os.path.join(b, "charge_control_end_threshold")),
            "health": round(100 * full / design) if full and design else None,
            # some firmwares always report 0: treat as unknown
            "cycles": (read(os.path.join(b, "cycle_count")) or "0").lstrip("0") or None,
            "device": os.path.basename(b),
        }
    return None


def memory():
    mi = {}
    for l in (read("/proc/meminfo") or "").splitlines():
        parts = l.split()
        if len(parts) >= 2:
            mi[parts[0].rstrip(":")] = int(parts[1])
    tot, avail = mi.get("MemTotal", 0), mi.get("MemAvailable", 0)
    swt, swf = mi.get("SwapTotal", 0), mi.get("SwapFree", 0)
    return {
        "used": round((tot - avail) / 1e6, 1), "total": round(tot / 1e6, 1),
        "pct": round(100 * (tot - avail) / tot) if tot else None,
        "swap_used": round((swt - swf) / 1e6, 1), "swap_total": round(swt / 1e6, 1),
    }


def disks(cfg_disks):
    out = []
    for d in cfg_disks:
        mount = d.get("mount", "/")
        try:
            s = os.statvfs(mount)
        except OSError:
            continue
        total = s.f_blocks * s.f_frsize
        free = s.f_bavail * s.f_frsize
        used = total - free
        out.append({
            "mount": mount, "label": d.get("label", mount),
            "total": total, "used": used, "free": free,
            "pct": round(100 * used / total) if total else None,
        })
    return out


def _is_vpn_iface(name):
    base = f"/sys/class/net/{name}"
    uevent = read(os.path.join(base, "uevent")) or ""
    return ("DEVTYPE=wireguard" in uevent
            or os.path.exists(os.path.join(base, "tun_flags"))
            or name.startswith(("nordlynx", "wg", "tun", "proton", "mullvad")))


def _route_dev(target="1.1.1.1"):
    try:
        return json.loads(sh("ip -j route get " + target) or "[]")[0].get("dev")
    except (ValueError, IndexError, AttributeError):
        return None


def net():
    """Throughput of physical links, plus whether a VPN is up *and* routing.

    A tunnel can be up while traffic still leaves through the physical link
    (empty policy-routing table, crashed daemon): that is reported as a leak.
    """
    now = time.monotonic()
    ifaces = {}
    for line in (read("/proc/net/dev") or "").splitlines()[2:]:
        name, _, rest = line.partition(":")
        name, f = name.strip(), rest.split()
        if name == "lo" or len(f) < 9:
            continue
        ifaces[name] = (int(f[0]), int(f[8]))
    phys = [n for n in ifaces if os.path.exists(f"/sys/class/net/{n}/device")]
    vpn = next((n for n in ifaces if _is_vpn_iface(n)), None)
    via = _route_dev()
    out = {
        "rx": _rate("net:rx", sum(ifaces[n][0] for n in phys), now),
        "tx": _rate("net:tx", sum(ifaces[n][1] for n in phys), now),
        "via": via,
        "vpn_iface": vpn,
        "vpn": bool(vpn and via == vpn),
        "vpn_leak": bool(vpn and via and via != vpn),
    }
    if vpn:
        out["vpn_rx"] = _rate("vpn:rx", ifaces[vpn][0], now)
        out["vpn_tx"] = _rate("vpn:tx", ifaces[vpn][1], now)
    return out


def disk_io():
    """Read/write bytes/s summed over whole physical disks."""
    now = time.monotonic()
    rd = wr = 0
    for line in (read("/proc/diskstats") or "").splitlines():
        f = line.split()
        if len(f) < 10 or not os.path.exists(f"/sys/block/{f[2]}/device"):
            continue
        rd += int(f[5]) * 512
        wr += int(f[9]) * 512
    return {"read": _rate("disk:r", rd, now), "write": _rate("disk:w", wr, now)}


def processes(n=6):
    """Top programs by CPU and by memory, grouped by name (like btop's list).

    CPU % is per core, as in top/btop: 200% = two cores fully busy.
    """
    global _prev_proc
    now = time.monotonic()
    prev_t = _prev_proc.get("_t")
    cur, groups = {"_t": now}, {}
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/stat") as fh:
                st = fh.read()
        except OSError:
            continue
        r = st.rfind(")")
        name, f = st[st.find("(") + 1:r], st[r + 2:].split()
        ticks, rss = int(f[11]) + int(f[12]), int(f[21]) * _PAGE
        if rss == 0:       # kernel threads
            continue
        cur[pid] = ticks
        g = groups.setdefault(name, {"name": name, "count": 0, "cpu": 0.0, "mem": 0})
        g["count"] += 1
        g["mem"] += rss
        if prev_t and pid in _prev_proc:
            g["cpu"] += (ticks - _prev_proc[pid]) / _CLK / (now - prev_t) * 100
    _prev_proc = cur
    rows = list(groups.values())
    for g in rows:
        g["cpu"] = round(g["cpu"], 1)
    top_cpu = sorted(rows, key=lambda g: -g["cpu"])[:n]
    top_mem = sorted(rows, key=lambda g: -g["mem"])[:n]
    return {"cpu": top_cpu if prev_t else [], "mem": top_mem}


def collect(cfg):
    hw = cfg["hardware"]
    return {
        "host": read("/proc/sys/kernel/hostname") or "host",
        "profile": (read("/sys/firmware/acpi/platform_profile") or "").capitalize() or None,
        "cpu": cpu(hw),
        "gpus": gpus(hw),
        "fans": fans(hw),
        "battery": battery(hw),
        "memory": memory(),
        "disks": disks(cfg["disks"]),
        "net": net(),
        "io": disk_io(),
        "procs": processes(),
    }
