"""Background sampler: one collector thread instead of one per page request.

Fast telemetry is sampled every `interval` seconds and kept as a short history
(for the sparklines). Slow, expensive checks (health advisories, vault, movies)
are refreshed every `slow_every` seconds. Requests only read the cache.
"""
from __future__ import annotations
import threading
import time
from collections import deque

from . import collect as C


def _point(d):
    """The few numbers per sample that the history graphs need."""
    cpu, mem, io, net = d.get("cpu") or {}, d.get("memory") or {}, d.get("io") or {}, d.get("net") or {}
    return {
        "t": round(time.time()),
        "cpu": cpu.get("usage"), "cpu_temp": cpu.get("temp"),
        "mem": mem.get("pct"),
        "gpus": [{"temp": g.get("temp"), "util": g.get("util")} for g in d.get("gpus") or []],
        "rx": net.get("rx"), "tx": net.get("tx"),
        "rd": io.get("read"), "wr": io.get("write"),
    }


class Sampler(threading.Thread):
    def __init__(self, cfg, slow_fn, interval=2.0, keep=90, slow_every=30.0):
        super().__init__(daemon=True, name="meteordash-sampler")
        self.cfg, self.slow_fn = cfg, slow_fn
        self.interval, self.slow_every = interval, slow_every
        self.history = deque(maxlen=keep)
        self.lock = threading.Lock()
        self.data, self.slow, self._slow_t = None, {}, 0.0
        self._wake = threading.Event()
        self.step()                       # prime counters so rates exist soon

    def step(self):
        data = C.collect(self.cfg)
        with self.lock:
            self.data = data
            self.history.append(_point(data))
        if time.monotonic() - self._slow_t >= self.slow_every:
            slow = self.slow_fn(self.cfg, data)
            with self.lock:
                self.slow = slow
            self._slow_t = time.monotonic()

    def refresh_slow(self):
        """Force the slow checks on the next tick (e.g. after marking a movie)."""
        self._slow_t = 0.0
        self._wake.set()

    def run(self):
        while True:
            self._wake.wait(self.interval)
            self._wake.clear()
            try:
                self.step()
            except Exception as e:        # never let the thread die
                print("sampler:", e)

    def read(self):
        with self.lock:
            return self.data, dict(self.slow), list(self.history)
