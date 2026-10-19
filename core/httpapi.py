"""Servidor HTTP local (127.0.0.1, porta aleatória) que serve a interface e expõe a API.

A ponte JavaScript↔Python do pywebview bloqueia a janela com respostas grandes (trajetórias de um dia
inteiro são dezenas de MB), por isso a interface fala com o Python por HTTP na mesma máquina.
"""
from __future__ import annotations

import json
import logging
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def start_server(api, ui_dir: Path, port: int = 0) -> int:
    """Arranca o servidor numa thread e devolve a porta."""
    ui_dir = Path(ui_dir).resolve()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # silencioso; erros vão para o logging
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            rel = "index.html" if path in ("/", "") else path.lstrip("/")
            f = (ui_dir / rel).resolve()
            if ui_dir not in f.parents or not f.is_file():
                self._send(404, b"not found", "text/plain"); return
            ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            self._send(200, f.read_bytes(), ctype)

        def do_POST(self):
            if self.path != "/api":
                self._send(404, b"not found", "text/plain"); return
            try:
                n = int(self.headers.get("Content-Length", "0"))
                req = json.loads(self.rfile.read(n) or b"{}")
                method, args = req.get("method", ""), req.get("args", [])
                fn = getattr(api, method, None)
                if not method or method.startswith("_") or not callable(fn):
                    res = {"ok": False, "error": f"Método desconhecido: {method}"}
                else:
                    res = fn(*args)
                body = json.dumps(res, default=str, ensure_ascii=False).encode("utf-8")
            except Exception as e:  # noqa: BLE001
                logging.exception("Erro no pedido HTTP")
                body = json.dumps({"ok": False, "error": str(e)}).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")

    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, name="http-api", daemon=True).start()
    logging.info("Servidor local em http://127.0.0.1:%s", srv.server_address[1])
    return srv.server_address[1]
