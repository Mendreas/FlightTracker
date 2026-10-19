"""FlightTracker 4.0 — NAV Portugal / GOPLIS
Janela de ambiente de trabalho (pywebview) + backend Python/DuckDB.

Arrancar em desenvolvimento:  python app.py
Gerar .exe (Windows):          build_windows.bat
"""
from __future__ import annotations

import json
import logging
import subprocess
import os
import socket
import time
import urllib.request
import subprocess
import sys
import threading
import traceback
from pathlib import Path

from core.db import Database, resource_path
FOLDER_DIALOG, OPEN_DIALOG, SAVE_DIALOG = 1, 2, 3  # iguais aos do pywebview
from core.filenames import date_label
from core.httpapi import start_server
from core.service import Service

APP_NAME = "FlightTracker"
VERSION = "4.0.0"


def setup_logging(folder: Path):
    log = folder / "app.log"
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(threadName)s %(message)s",
                        handlers=[logging.FileHandler(log, encoding="utf-8")])
    logging.getLogger("pywebview").setLevel(logging.INFO)
    sys.excepthook = lambda t, v, tb: logging.error("Exceção não tratada", exc_info=(t, v, tb))
    threading.excepthook = lambda a: logging.error("Exceção em thread %s", a.thread.name, exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    return log


def data_dir() -> Path:
    """Pasta onde fica a base de dados: %LOCALAPPDATA%\\FlightTracker (Windows) ou ~/.flighttracker."""
    override = os.environ.get("FLIGHTPLOTTER_DATA")
    if override:
        p = Path(override)
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        p = base / "FlightTracker"
        old = base / "FlightPlotter"
        if not p.exists() and old.exists():   # migra a base criada pelas versões 2.x
            try:
                old.rename(p)
            except OSError:
                p = old
    else:
        p = Path.home() / ".flighttracker"
    p.mkdir(parents=True, exist_ok=True)
    return p


class Api:
    """Métodos chamados a partir do JavaScript via window.pywebview.api.<nome>(...)."""

    def __init__(self):
        self.window = None
        self._importing = False
        self._import_state = {"importing": False, "done": 0, "total": 0, "name": "", "result": None}
        self._lock = threading.RLock()
        self.init_error = None
        try:
            logging.info("A abrir base de dados em %s", data_dir())
            self.db = Database(data_dir() / "flightplotter.duckdb")
            self.svc = Service(self.db)
            logging.info("Base aberta: %s", self.db.summary())
        except Exception as e:  # noqa: BLE001
            logging.exception("Erro a abrir a base de dados")
            msg = str(e)
            if "lock" in msg.lower() or "being used" in msg.lower():
                msg = "A base de dados está aberta por outro programa — fecha o outro FlightTracker (Gestor de Tarefas → FlightTracker.exe) e volta a abrir. " + msg
            self.init_error = msg; self.db = None; self.svc = None

    # -------------------------------------------------------------- utilidades
    def _js(self, code: str):
        if self.window:
            try:
                self.window.evaluate_js(code)
            except Exception:  # noqa: BLE001
                pass

    def _safe(self, fn, *a, **kw):
        name = getattr(fn, "__name__", "?")
        if self.init_error and fn is not self._state_fn:
            return {"ok": False, "error": "Base de dados indisponível: " + self.init_error}
        t0 = time.time()
        try:
            with self._lock:
                r = {"ok": True, "data": fn(*a, **kw)}
            dt = time.time() - t0
            if dt > 0.5:
                logging.info("%s demorou %.1fs", name, dt)
            return r
        except Exception as e:  # noqa: BLE001
            logging.exception("Erro em %s", name)
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------ estado
    def _state_fn(self):
        if self.init_error:
            raise RuntimeError("Não foi possível abrir a base de dados (está outro FlightTracker aberto?). " + self.init_error)
        s = self.db.summary()
        s["version"] = VERSION
        s["importing"] = self._importing
        s["log_path"] = str(data_dir() / "app.log")
        return s

    def get_state(self):
        return self._safe(self._state_fn)

    def get_filters(self):
        def f():
            r = self.db.filters()
            for d in r["dates"]:
                d["label"] = date_label(d["date"])
            return r
        return self._safe(f)

    def get_points(self):
        def f():
            pts = json.loads(resource_path("data", "aip_points.json").read_text(encoding="utf-8"))
            grp = json.loads(resource_path("data", "point_groups.json").read_text(encoding="utf-8"))
            return {"points": pts, "groups": grp}
        return self._safe(f)

    # -------------------------------------------------------------- importação
    def choose_folder(self):
        if self.init_error:
            return {"ok": False, "error": "Base de dados indisponível: " + self.init_error}
        try:
            res = self.window.create_file_dialog(FOLDER_DIALOG)
            if res:
                return {"ok": True, "data": res[0] if isinstance(res, (list, tuple)) else res}
            return {"ok": True, "data": None}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def import_folder(self, folder: str | None = None):
        """Arranca a importação em thread; o progresso chega ao JS por onImportProgress/onImportDone."""
        if self.init_error:
            return {"ok": False, "error": "Base de dados indisponível: " + self.init_error}
        if self._importing:
            return {"ok": False, "error": "Já está uma importação a decorrer."}
        if not folder:
            folder = self.db.summary().get("last_folder")
        if not folder or not os.path.isdir(folder):
            return {"ok": False, "error": "Pasta inválida."}
        self._importing = True

        self._import_state = {"importing": True, "done": 0, "total": 0, "name": "A procurar ficheiros CSV…", "result": None}

        def progress(done, total, name):
            logging.info("importação %s/%s %s", done, total, name)
            self._import_state.update(done=done, total=total, name=name)

        def run():
            try:
                logging.info("Início da importação de %s", folder)
                res = self.db.import_folder(folder, progress, lock=self._lock)
                logging.info("Importação concluída: %s", res)
                self._import_state["result"] = {"ok": True, "data": res}
            except Exception as e:  # noqa: BLE001
                logging.exception("Erro na importação")
                self._import_state["result"] = {"ok": False, "error": str(e)}
            finally:
                self._importing = False
                self._import_state["importing"] = False

        threading.Thread(target=run, daemon=True).start()
        return {"ok": True, "data": folder}

    def import_status(self):
        """Estado da importação em curso (a interface consulta periodicamente)."""
        st = dict(self._import_state)
        if st["result"] is not None and not st["importing"]:
            self._import_state["result"] = None   # entregue uma vez
        return {"ok": True, "data": st}

    def remove_missing(self):
        return self._safe(self.db.remove_missing)

    def import_nmir(self):
        try:
            res = self.window.create_file_dialog(OPEN_DIALOG, allow_multiple=False,
                                                 file_types=("Excel NMIR (*.xlsx)", "Todos (*.*)"))
            if not res:
                return {"ok": True, "data": None}
            path = res[0] if isinstance(res, (list, tuple)) else res
            return self._safe(self.db.import_nmir_xlsx, path)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    # ---------------------------------------------------------------- consultas
    def get_flights(self, dates, blocks, csn="", cls="", airport=None):
        return self._safe(self.svc.set_filter, dates, blocks, csn or "", cls or "", airport)

    def set_airport(self, airport):
        return self._safe(self.svc.set_airport, airport)

    # ---------------------------------------------------------------- análises
    def run_final(self, rwy="BOTH", faf=7, corr=2, alt=1000):
        return self._safe(self.svc.run_final, rwy, faf, corr, alt)

    def fast(self, thr=160, mode="all", intercal=False, rwy="all"):
        return self._safe(self.svc.fast, thr, mode, intercal, rwy)

    def data_analysis(self, filters=None):
        return self._safe(self.svc.data_analysis, **(filters or {}))

    def daily(self, limit=165):
        return self._safe(self.svc.daily, limit)

    def star_limits(self):
        return self._safe(self.svc.star_limits)

    def star_limits_set(self, limits):
        return self._safe(self.svc.star_limits_set, limits)

    def star_limits_reset(self):
        return self._safe(lambda: self.svc.star_limits_set(dict(__import__("core.geo", fromlist=["x"]).LPPT_STAR_IAS_DEFAULTS)))

    def run_star(self, radius=1, tol=0):
        return self._safe(self.svc.run_star, radius, tol)

    def run_app(self, radius=1, tol=0):
        return self._safe(self.svc.run_app, radius, tol)

    def run_app_dist(self, rwy="02", buffer=4, sel=None):
        return self._safe(self.svc.run_app_dist, rwy, buffer, sel)

    def kpis(self):
        return self._safe(self.svc.kpis)

    def run_rrms(self):
        return self._safe(self.svc.run_rrms)

    def run_rot(self):
        return self._safe(self.svc.run_rot)

    def points_list(self):
        return self._safe(self.svc.points)

    def point_query(self, name, radius=1, op="any", v1=None, v2=None, tol=2):
        return self._safe(self.svc.point_query, name, radius, op, v1, v2, tol)

    def sequence(self, name, radius=1):
        return self._safe(self.svc.sequence, name, radius)

    def user_point_add(self, name, lat, lon, desc="Ponto manual"):
        return self._safe(lambda: (self.db.user_point_add(name, lat, lon, desc), self.svc.points())[1])

    def user_point_remove(self, name):
        return self._safe(lambda: (self.db.user_point_remove(name), self.svc.points())[1])

    def points_import(self):
        def f():
            res = self.window.create_file_dialog(OPEN_DIALOG, allow_multiple=False, file_types=("JSON (*.json)",))
            if not res: return None
            path = res[0] if isinstance(res, (list, tuple)) else res
            data = json.load(open(path, encoding="utf-8"))
            names = {p["name"].upper() for p in self.svc.points()}
            n = 0
            for p in data if isinstance(data, list) else []:
                try:
                    if p.get("name") and str(p["name"]).upper() not in names:
                        self.db.user_point_add(p["name"], float(p["lat"]), float(p["lon"]), p.get("desc") or "Ponto importado"); n += 1
                except (ValueError, TypeError, KeyError):
                    pass
            return {"imported": n, "points": self.svc.points()}
        return self._safe(f)

    def points_export(self):
        def f():
            res = self.window.create_file_dialog(SAVE_DIALOG, save_filename="points.json", file_types=("JSON (*.json)",))
            if not res: return None
            path = res[0] if isinstance(res, (list, tuple)) else res
            json.dump(self.db.user_points(), open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            return path
        return self._safe(f)

    def flight_detail(self, flight_id):
        return self._safe(self.svc.flight_detail, int(flight_id))

    def export(self, kind, extra=None, default_name=None, as_csv=False):
        def f():
            name = default_name or f"{kind}_{time.strftime('%Y-%m-%d')}.{'csv' if as_csv else 'xlsx'}"
            types = ("CSV (*.csv)",) if as_csv else ("Excel (*.xlsx)",)
            res = self.window.create_file_dialog(SAVE_DIALOG, save_filename=name, file_types=types)
            if not res: return None
            path = res[0] if isinstance(res, (list, tuple)) else res
            return self.svc.export_excel(path, kind, extra or {})
        return self._safe(f)

    def export_pptx(self):
        def f():
            res = self.window.create_file_dialog(SAVE_DIALOG, save_filename=f"ias_app_final_{time.strftime('%Y-%m-%d')}.pptx", file_types=("PowerPoint (*.pptx)",))
            if not res: return None
            path = res[0] if isinstance(res, (list, tuple)) else res
            return self.svc.export_pptx(path)
        return self._safe(f)

    def report(self, kind, extra=None):
        return self._safe(self.svc.report, kind, extra or {})

    def ia_settings(self):
        return self._safe(self.svc.ia_public)

    def ia_settings_set(self, provider=None, key=None, model=None, azure_endpoint=None):
        return self._safe(self.svc.ia_settings_set, provider, key, model, azure_endpoint)

    def ia_ask(self, question):
        return self._safe(self.svc.ia_ask, question)

    def ia_context(self):
        return self._safe(self.svc.ia_context_preview)

    def ia_clear(self):
        return self._safe(lambda: self.svc.ia_history.clear())

    def get_tracks(self, flight_ids, max_points=120000):
        return self._safe(self.db.tracks, flight_ids, int(max_points))

    def get_flight(self, flight_id):
        return self._safe(self.db.flight_points, int(flight_id))

    def get_stats(self, airport, dates, blocks):
        return self._safe(self.db.stats, airport or None, dates, blocks)

    def export_flights_csv(self, airport, dates, blocks, csn="", cls=""):
        try:
            res = self.window.create_file_dialog(SAVE_DIALOG, save_filename="movimentos.csv",
                                                 file_types=("CSV (*.csv)",))
            if not res:
                return {"ok": True, "data": None}
            path = res[0] if isinstance(res, (list, tuple)) else res
            rows = self.db.flights_list(airport, dates, blocks, csn or "", cls or "")
            import csv
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh, delimiter=";")
                w.writerow(["Data", "Aeroporto", "Callsign", "Tipo", "WTC", "Classe", "Início", "Fim",
                            "Alt início", "Alt fim", "Alt mín", "Alt máx", "Plots", "Blocos", "Mode S"])
                for r in rows:
                    w.writerow([date_label(r["date"]), r["airport"], r["csn"], r["actype"] or "", r["wtc"] or "",
                                r["cls"].upper(), r["tod_first"], r["tod_last"], r["alt_first"], r["alt_last"],
                                r["alt_min"], r["alt_max"], r["n"], r["blocks"], r["modes"] or ""])
            return {"ok": True, "data": path}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def open_data_folder(self):
        p = str(data_dir())
        try:
            if os.name == "nt":
                os.startfile(p)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", p])
            else:
                subprocess.Popen(["xdg-open", p])
            return {"ok": True, "data": p}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}


def _free_port() -> int:
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        return so.getsockname()[1]


def _wait_server(port: int, timeout: float = 60.0) -> bool:
    """Espera pelo motor de dados com uma ligação TCP direta (ignora o proxy do sistema)."""
    import http.client
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request("POST", "/api", body=b'{"method":"get_state","args":[]}', headers={"Content-Type": "application/json"})
            r = conn.getresponse(); r.read(); conn.close()
            if r.status == 200:
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.3)
    return False


def _spawn_worker(port: int, log: Path):
    """Lança o motor de dados como processo separado: o próprio .exe (ou python app.py) com --worker."""
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--worker", str(port), str(data_dir()), str(log)]
    else:
        cmd = [sys.executable, str(Path(__file__).resolve()), "--worker", str(port), str(data_dir()), str(log)]
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(cmd, creationflags=flags, cwd=str(Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent))


def main():
    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
    os.environ.setdefault("no_proxy", "127.0.0.1,localhost")
    log = setup_logging(data_dir())
    logging.info("=== FlightTracker %s a arrancar (python %s, frozen=%s) ===", VERSION, sys.version.split()[0], getattr(sys, "frozen", False))
    port = _free_port()
    proc = _spawn_worker(port, log)
    logging.info("Processo de dados iniciado (pid %s) na porta %s", proc.pid, port)
    url = f"http://127.0.0.1:{port}/index.html"
    ok = _wait_server(port, 60)
    if not ok:
        rc = proc.poll()
        logging.error("O processo de dados não respondeu a tempo (código de saída: %s)", rc)
        msg = (f"O motor de dados não arrancou (código {rc}). Consulta o ficheiro de registo:\n{log}")
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, "FlightTracker — erro ao arrancar", 0x10)
        except Exception:  # noqa: BLE001
            print(msg)
        if proc.poll() is None:
            proc.terminate()
        return
    use_browser = "--browser" in sys.argv or os.environ.get("FLIGHTPLOTTER_BROWSER") == "1"
    if not use_browser:
        try:
            import webview
            # WebView2 (Edge/Chromium): nunca passar pelo proxy da rede para o servidor local
            os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--proxy-bypass-list=127.0.0.1;localhost --proxy-server=direct://"
            window = webview.create_window(f"{APP_NAME} {VERSION} — NAV Portugal", url, width=1500, height=940, min_size=(1100, 700),
                                           background_color="#0b1220")
            logging.info("Janela criada; a iniciar webview")
            webview.start(debug="--debug" in sys.argv)
        except BaseException:  # noqa: BLE001 — pythonnet/WebView2 em falta, DLL bloqueada pelo OneDrive, etc.
            logging.exception("A janela nativa falhou — a abrir no navegador")
            use_browser = True
    if use_browser:
        _run_in_browser(url, port)
    if proc.poll() is None:
        proc.terminate()
    logging.info("Aplicação terminada")


def _run_in_browser(url: str, port: int):
    """Modo de recurso: interface no navegador predefinido; o processo fica vivo enquanto a página estiver aberta."""
    import webbrowser
    webbrowser.open(url)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, "O FlightTracker abriu no teu navegador (Edge/Chrome).\n\n"
                                         "Mantém esta janela aberta enquanto usares a aplicação; fecha-a para terminar.",
                                         "FlightTracker", 0x40)
    except Exception:  # noqa: BLE001 — não-Windows ou sem interface
        print(f"FlightTracker aberto em {url}. Ctrl+C para terminar.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    if len(sys.argv) >= 5 and sys.argv[1] == "--worker":
        from core import worker
        worker.run(int(sys.argv[2]), sys.argv[3], sys.argv[4])
    else:
        main()
