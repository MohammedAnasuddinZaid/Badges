#!/usr/bin/env python3
"""Jarvis daemon - keeps the assistant alive on 127.0.0.1:21340."""

import hmac
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from jarvis import (  # noqa: E402
    BASE, VERSION, Jarvis, load_config, auto_update,
    tech_news, post_notification,
)

PORT = 21340
TOKEN_PATH = os.path.join(BASE, "token")
LOG_PATH = os.path.join(BASE, "logs", "daemon.log")

def log(line):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + line + "\n")
    except Exception:
        pass

def read_token():
    try:
        with open(TOKEN_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""

TOKEN = read_token()
LOCK = threading.Lock()
JARVIS = None


class Handler(BaseHTTPRequestHandler):
    server_version = "Jarvis/" + VERSION

    def log_message(self, fmt, *args):
        log("http " + (fmt % args))

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authed(self):
        supplied = self.headers.get("X-Jarvis-Token", "")
        if not supplied:
            qs = self.path.split("?", 1)
            if len(qs) == 2:
                from urllib.parse import parse_qs
                supplied = parse_qs(qs[1]).get("token", [""])[0]
        if not TOKEN:
            return False
        return hmac.compare_digest(supplied, TOKEN)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/health", "/"):
            self._send(200, {"ok": True, "name": "Jarvis", "version": VERSION})
            return
        if path == "/ask":
            self._handle_ask(None)
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/ask":
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(min(length, 20000)) if length else b""
            try:
                data = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                data = {}
            self._handle_ask(data)
            return
        self._send(404, {"error": "not found"})

    def _handle_ask(self, data):
        if not self._authed():
            self._send(401, {"error": "bad or missing token"})
            return
        if data is None:
            from urllib.parse import parse_qs, urlparse
            qs = parse_qs(urlparse(self.path).query)
            question = (qs.get("q") or [""])[0]
        else:
            question = data.get("q") or data.get("text") or ""
        question = str(question).strip()[:4000]
        if not question:
            self._send(400, {"error": "missing q"})
            return
        try:
            with LOCK:
                answer = JARVIS.ask(question)
            self._send(200, {"answer": answer, "tools": JARVIS.last_tools})
        except Exception as e:
            log("ask error: " + repr(e))
            self._send(500, {"error": str(e)[:400]})


def daily_news_loop():
    """Post a tech-news notification every morning around 08:00 (once a day)."""
    last_day = ""
    while True:
        try:
            now = time.localtime()
            today = time.strftime("%Y-%m-%d", now)
            if now.tm_hour == 8 and now.tm_min < 15 and today != last_day:
                text = tech_news(3, force=True)
                if not text.startswith("ERROR"):
                    lines = [ln.strip() for ln in text.splitlines()
                             if re.match(r"^\d+\.", ln.strip())][:3]
                    if lines:
                        post_notification("Jarvis · daily tech news",
                                          "\n".join(lines)[:900])
                last_day = today
        except Exception as e:
            log("news loop error: " + repr(e))
        time.sleep(60)


def main():
    global JARVIS
    os.makedirs(os.path.join(BASE, "logs"), exist_ok=True)
    auto_update()
    if not TOKEN:
        print("No token found. Run the installer first.", file=sys.stderr)
        return 1
    load_config()
    JARVIS = Jarvis(interactive=False)
    threading.Thread(target=daily_news_loop, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.daemon_threads = True
    log("daemon started pid=%d port=%d" % (os.getpid(), PORT))
    print("Jarvis daemon listening on http://127.0.0.1:%d" % PORT, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        log("daemon stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
