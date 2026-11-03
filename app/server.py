"""Локальный HTTP-сервер: отдаёт интерфейс и JSON API. Только 127.0.0.1 + токен сессии."""
import json
import mimetypes
import os
import secrets
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import catalog
import engine
import hw

DONATE_URL = "https://dalink.to/olegche"
UI_DIR = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "ui")
TOKEN = secrets.token_urlsafe(24)

_hw_cache = {}
_updates = {"t": 0.0, "data": None}
UPDATES_TTL = 3600
last_ping = {"t": 0.0}
quit_event = threading.Event()   # страница просит закрыть программу (после полного удаления)


def get_hw(refresh=False):
    if refresh or "hw" not in _hw_cache:
        _hw_cache["hw"] = hw.detect()
    return _hw_cache["hw"]


def build_state(refresh=False):
    engine.wake()
    eng = engine.status()
    paths = engine.paths()
    info = dict(get_hw(refresh), disk_free_gb=paths["models"]["free_gb"])
    return {
        "hw": info,
        "engine": eng,
        "paths": paths,
        "installed": engine.models(),
        "models": catalog.recommend(info, eng["installed"],
                                    None if paths["same_drive"] else paths["engine"]["free_gb"]),
        "demo": engine.DEMO,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalAI"
    # HTTP/1.1: поток чата идёт chunked — WebView2/антивирус не ждут конца соединения, чтобы показать ответ.
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    # --- утилиты ---
    def _send(self, code, body=b"", ctype="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode())

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _guard(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            self.close_connection = True  # тело запроса не прочитано — соединение не переиспользуем
            self._send(403, b"forbidden", "text/plain")
            return False
        if self.path.startswith("/api/") and self.headers.get("X-Token") != TOKEN:
            self.close_connection = True
            self._json({"error": "forbidden"}, 403)
            return False
        return True

    # --- маршруты ---
    def do_GET(self):
        if not self._guard():
            return
        path, _, query = self.path.partition("?")
        if path == "/api/state":
            return self._json(build_state("refresh" in query))
        if path == "/api/model":
            name = urllib.parse.parse_qs(query).get("name", [""])[0]
            info = engine.model_info(name)
            return self._json(info or {"error": "not_found"}, 200 if info else 404)
        if path == "/api/updates":
            # Сеть (GitHub, реестр Ollama) — не чаще раза в час, если не попросили явно.
            if "force" in query or not _updates["data"] or time.time() - _updates["t"] > UPDATES_TTL:
                _updates["data"], _updates["t"] = engine.check_updates(), time.time()
            return self._json(_updates["data"])
        if path == "/api/job":
            return self._json(engine.current_job())
        if path == "/api/uninstall":
            return self._json(engine.uninstall_info())
        if path == "/api/ping":
            last_ping["t"] = time.time()
            return self._json({"ok": True})
        rel = "index.html" if path == "/" else path.lstrip("/")
        full = os.path.normpath(os.path.join(UI_DIR, rel))
        if not full.startswith(UI_DIR) or not os.path.isfile(full):
            return self._send(404, b"not found", "text/plain")
        data = open(full, "rb").read()
        if rel == "index.html":
            data = data.replace(b"__TOKEN__", TOKEN.encode())
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        self._send(200, data, ctype + ("; charset=utf-8" if ctype.startswith("text/") or ctype.endswith("javascript") else ""))

    def do_POST(self):
        if not self._guard():
            return
        data = self._body()
        if self.path == "/api/setup":
            model = data.get("model", "")
            if model not in catalog.BY_ID:
                return self._json({"error": "unknown_model"}, 400)
            return self._json({"started": engine.start_setup(model)})
        if self.path == "/api/update":
            model = data.get("model")
            if model and model not in {m["id"] for m in engine.models()}:
                return self._json({"error": "unknown_model"}, 400)
            _updates["data"] = None
            return self._json({"started": engine.start_update(model)})
        if self.path in ("/api/paths/check", "/api/paths"):
            kind = data.get("kind")
            if kind not in ("engine", "models"):
                return self._json({"error": "bad_kind"}, 400)
            chk = engine.check_dir(kind, data.get("path", ""))
            if self.path == "/api/paths/check" or not chk["ok"]:
                return self._json(chk)
            if chk["same"]:
                return self._json({"ok": True, "job": False})
            if kind == "engine":
                ok = engine.set_engine_dir(chk["path"])
                return self._json({"ok": ok, "job": ok and engine.status()["installed"], **({} if ok else {"error": "busy"})})
            move = bool(data.get("move"))
            ok = engine.set_models_dir(chk["path"], move)
            return self._json({"ok": ok, "job": ok and move, **({} if ok else {"error": "busy"})})
        if self.path == "/api/cancel":
            engine.cancel()
            return self._json({"ok": True})
        if self.path == "/api/delete":
            return self._json({"ok": engine.delete_model(data.get("model", ""))})
        if self.path == "/api/uninstall":
            return self._json({"started": engine.start_uninstall(data.get("parts") or [])})
        if self.path == "/api/quit":
            if not engine.DEMO:
                quit_event.set()
            return self._json({"ok": not engine.DEMO})
        if self.path == "/api/help":
            webbrowser.open(DONATE_URL)
            return self._json({"ok": True})
        if self.path == "/api/chat":
            return self._chat(data)
        self._send(404, b"not found", "text/plain")

    def _chat(self, data):
        model = data.get("model", "")
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def chunk(b):
            self.wfile.write(b"%x\r\n%s\r\n" % (len(b), b))
            self.wfile.flush()

        def emit(obj):
            chunk(json.dumps(obj, ensure_ascii=False).encode() + b"\n")

        try:
            self._chat_stream(data, model, chunk, emit)
            chunk(b"")  # конец chunked-ответа
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True

    def _chat_stream(self, data, model, chunk, emit):
        try:
            if engine.DEMO:
                emit({"status": "loading"})
                time.sleep(1.5)
                if data.get("think"):
                    for w in "Пользователь спрашивает… Подумаю, как ответить коротко. / Thinking it over…".split(" "):
                        emit({"message": {"content": "", "thinking": w + " "}})
                        time.sleep(0.12)
                text = "Это демо-режим: ответ имитирован. / Demo mode: this reply is simulated. **Markdown** works:\n\n```python\nprint('hello')\n```"
                for i in range(0, len(text), 4):
                    emit({"message": {"content": text[i:i + 4]}})
                    time.sleep(0.03)
                return emit({"done": True, "eval_count": len(text) // 4, "eval_duration": int(len(text) / 4 * 0.03e9)})
            # Первый вопрос после запуска ждёт загрузки модели в память (иногда десятки секунд) — сообщаем сразу.
            if not engine.loaded(model):
                emit({"status": "loading"})
            if not engine.ensure_running():
                return emit({"error": "engine_not_running"})
            caps = engine.caps(model)
            messages = data.get("messages", [])
            if "vision" not in caps:
                messages = [{k: v for k, v in m.items() if k != "images"} for m in messages]
            body = {"model": model, "messages": messages, "stream": True}
            if "think" in caps:
                body["think"] = bool(data.get("think"))
            req = urllib.request.Request(engine.BASE + "/api/chat", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=600) as resp:
                for line in resp:
                    chunk(line)
        except OSError as e:
            if isinstance(e, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
                raise
            emit({"error": str(e)})
        except Exception as e:  # noqa: BLE001
            emit({"error": str(e)})


class Server(ThreadingHTTPServer):
    # Без SO_REUSEADDR: на Windows с ним сервер молча садится на занятый порт рядом с чужим.
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


# Постоянный порт: localStorage (чаты, тема, модель) привязан к origin вместе с портом.
DEFAULT_PORT = 28765


def start():
    env = os.environ.get("LOCALAI_PORT")
    try:
        srv = Server(("127.0.0.1", int(env) if env else DEFAULT_PORT), Handler)
    except OSError:   # порт занят (второй экземпляр или чужая программа) — любой свободный
        if env:
            raise
        srv = Server(("127.0.0.1", 0), Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    threading.Thread(target=get_hw, daemon=True).start()
    threading.Thread(target=engine.wake, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"
