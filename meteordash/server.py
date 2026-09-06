"""Serves the single-page HUD on localhost, plus the JSON endpoints it polls.

Boot data is injected server-side so the page never flashes blank.
"""
from __future__ import annotations
import http.server
import json
import socketserver
from pathlib import Path

from . import collect as C
from . import health as H
from .modules import movies as M
from .modules import vault as V

WEB = Path(__file__).resolve().parent / "web" / "page.html"


def _public_cfg(cfg):
    """Config the page needs: enabled panels + titles + thresholds."""
    return {"panels": cfg["panels"], "title": cfg["server"]["title"],
            "thresholds": cfg["thresholds"]}


def snapshot(cfg):
    """Everything the page renders, in one payload (also used as boot data)."""
    data = C.collect(cfg)
    payload = {"cfg": _public_cfg(cfg), "data": data,
               "integrity": H.integrity(cfg, data) if cfg.panel("integrity") else None,
               "advisories": H.advisories(cfg, data) if cfg.panel("health") else None}
    if cfg.panel("vault"):
        payload["vault"] = V.collect(cfg)
    if cfg.panel("movies"):
        payload["movies"] = M.collect(cfg)
    return payload


def make_handler(cfg):
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
                self._send(json.dumps(C.collect(cfg)), "application/json")
            elif p == "/health":
                data = C.collect(cfg)
                self._send(json.dumps({
                    "integrity": H.integrity(cfg, data),
                    "advisories": H.advisories(cfg, data)}), "application/json")
            elif p == "/vault":
                self._send(json.dumps(V.collect(cfg)), "application/json")
            elif p == "/movies":
                self._send(json.dumps(M.collect(cfg)), "application/json")
            elif p == "/snapshot":
                self._send(json.dumps(snapshot(cfg)), "application/json")
            elif p == "/":
                boot = json.dumps(snapshot(cfg))
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
                self._send(json.dumps({"ok": ok}), "application/json")
            else:
                self._send("not found", "text/plain", 404)

    return Handler


def serve(cfg):
    host, port = cfg["server"]["host"], cfg["server"]["port"]
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((host, port), make_handler(cfg)) as s:
        print(f"meteor-dash → http://{host}:{port}  (Ctrl+C to stop)")
        if cfg.path:
            print(f"config: {cfg.path}")
        else:
            print("config: (defaults — no config.toml found)")
        s.serve_forever()
