"""Serves the single-page HUD on localhost, plus the JSON endpoints it polls.

Boot data is injected server-side so the page never flashes blank.
"""
from __future__ import annotations
import http.server
import json
import socketserver
import time
from pathlib import Path

from . import collect as C
from . import health as H
from .modules import movies as M
from .modules import vault as V
from .sampler import Sampler

WEB = Path(__file__).resolve().parent / "web" / "page.html"


def _public_cfg(cfg):
    """Config the page needs: enabled panels + titles + thresholds."""
    return {"panels": cfg["panels"], "title": cfg["server"]["title"],
            "thresholds": cfg["thresholds"]}


def slow_parts(cfg, data):
    """The expensive, slow-changing parts of the payload."""
    out = {"integrity": H.integrity(cfg, data) if cfg.panel("integrity") else None,
           "advisories": H.advisories(cfg, data) if cfg.panel("health") else None}
    if cfg.panel("vault"):
        out["vault"] = V.collect(cfg)
    if cfg.panel("movies"):
        out["movies"] = M.collect(cfg)
    return out


def snapshot(cfg, sampler=None):
    """Everything the page renders, in one payload (also used as boot data)."""
    if sampler:
        data, slow, history = sampler.read()
    else:                                 # one-shot (--check): two samples for rates
        C.collect(cfg)
        time.sleep(0.5)
        data = C.collect(cfg)
        slow, history = slow_parts(cfg, data), []
    return {"cfg": _public_cfg(cfg), "data": data, "history": history, **slow}


def make_handler(cfg, sampler):
    page_tpl = WEB.read_text()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, body, ctype, code=200):
            b = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            p = self.path.split("?")[0]
            if p == "/data":
                self._send(json.dumps(sampler.read()[0]), "application/json")
            elif p == "/health":
                slow = sampler.read()[1]
                self._send(json.dumps({"integrity": slow.get("integrity"),
                                       "advisories": slow.get("advisories")}),
                           "application/json")
            elif p == "/vault":
                self._send(json.dumps(V.collect(cfg)), "application/json")
            elif p == "/movies":
                self._send(json.dumps(M.collect(cfg)), "application/json")
            elif p == "/snapshot":
                self._send(json.dumps(snapshot(cfg, sampler)), "application/json")
            elif p == "/":
                boot = json.dumps(snapshot(cfg, sampler))
                self._send(page_tpl.replace("__BOOTJSON__", boot),
                           "text/html; charset=utf-8")
            else:
                self._send("not found", "text/plain", 404)

        def do_POST(self):
            p = self.path.split("?")[0]
            if p == "/movies/mark":
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length) if length else b"{}"
                try:
                    title = json.loads(body).get("title", "")
                except Exception:
                    title = ""
                ok = bool(title) and M.mark_watched(cfg, title)
                if ok:
                    sampler.refresh_slow()
                self._send(json.dumps({"ok": ok}), "application/json")
            else:
                self._send("not found", "text/plain", 404)

    return Handler


def serve(cfg):
    host, port = cfg["server"]["host"], cfg["server"]["port"]
    sampler = Sampler(cfg, slow_parts)
    sampler.start()
    socketserver.ThreadingTCPServer.daemon_threads = True
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer((host, port), make_handler(cfg, sampler)) as s:
        print(f"meteor-dash → http://{host}:{port}  (Ctrl+C to stop)")
        if cfg.path:
            print(f"config: {cfg.path}")
        else:
            print("config: (defaults — no config.toml found)")
        s.serve_forever()
