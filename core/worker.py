"""Processo de trabalho: base de dados + servidor HTTP local. Corre separado da janela,
para que o Windows nunca marque a janela como "Não responde" enquanto o Python calcula.

Os diálogos de ficheiros usam tkinter (funciona sem janela principal). O Tk/Cocoa só pode ser
usado na thread principal do processo — os pedidos HTTP chegam numa thread por pedido (ver
core/httpapi.py), por isso o diálogo é pedido por uma fila e executado na thread principal
(o ciclo deste módulo), que espera o resultado. Sem isto, no macOS o diálogo nunca aparece
(o ícone salta na dock a pedir atenção, mas a janela não chega a desenhar-se)."""
from __future__ import annotations

import logging
import queue
import sys
import threading
import time
from pathlib import Path

FOLDER_DIALOG, OPEN_DIALOG, SAVE_DIALOG = 1, 2, 3

_dialog_queue: "queue.Queue[tuple]" = queue.Queue()


def _types(file_types):
    out = []
    for ft in file_types or ():
        # "Excel (*.xlsx)" -> ("Excel", "*.xlsx")
        name, _, pat = ft.partition("(")
        out.append((name.strip(), pat.rstrip(")").strip() or "*.*"))
    return out or [("Todos", "*.*")]


def _run_dialog(kind, allow_multiple, save_filename, file_types):
    """Corre SEMPRE na thread principal deste processo (ver _dialog_loop)."""
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
    try:
        if kind == FOLDER_DIALOG:
            p = filedialog.askdirectory(title="Escolhe a pasta com os CSV", parent=root)
        elif kind == OPEN_DIALOG:
            p = filedialog.askopenfilename(filetypes=_types(file_types), parent=root)
        else:
            ext = Path(save_filename).suffix
            p = filedialog.asksaveasfilename(initialfile=save_filename, defaultextension=ext, filetypes=_types(file_types), parent=root)
    finally:
        root.destroy()
    return [p] if p else None


def _dialog_loop(stop: threading.Event):
    """Corre na thread principal do processo: tira pedidos da fila e mostra o diálogo do Tk."""
    while not stop.is_set():
        try:
            kind, allow_multiple, save_filename, file_types, result_box, done = _dialog_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            result_box["result"] = _run_dialog(kind, allow_multiple, save_filename, file_types)
        except Exception as e:  # noqa: BLE001
            logging.exception("Diálogo de ficheiro falhou")
            result_box["error"] = str(e)
        finally:
            done.set()


class TkDialogs:
    """Substitui window.create_file_dialog do pywebview dentro do processo de trabalho.
    Pode ser chamado de qualquer thread (os pedidos HTTP chegam numa thread por pedido):
    põe o pedido na fila e espera que a thread principal (_dialog_loop) o processe."""

    def create_file_dialog(self, kind, allow_multiple=False, save_filename="", file_types=()):
        result_box: dict = {}
        done = threading.Event()
        _dialog_queue.put((kind, allow_multiple, save_filename, file_types, result_box, done))
        if not done.wait(600):
            return None
        if "error" in result_box:
            raise RuntimeError(result_box["error"])
        return result_box.get("result")

    def evaluate_js(self, code):  # sem janela neste processo; o progresso é consultado por polling
        pass


def run(port: int, data_dir: str, log_path: str, lan: bool = False):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s worker %(threadName)s %(message)s",
                        handlers=[logging.FileHandler(log_path, encoding="utf-8")])
    import os
    os.environ["FLIGHTPLOTTER_DATA"] = data_dir
    from app import Api
    from core.db import resource_path
    from core.httpapi import start_server
    api = Api()
    api.window = TkDialogs()
    start_server(api, resource_path("ui"), port, "0.0.0.0" if lan else "127.0.0.1")
    if lan:
        logging.info("acesso na rede local ATIVO: http://<IP deste PC>:%s/index.html", port)
    logging.info("worker pronto na porta %s", port)
    stop = threading.Event()
    _dialog_loop(stop)   # ocupa a thread principal deste processo até sair (os diálogos têm de correr aqui)


if __name__ == "__main__":
    run(int(sys.argv[1]), sys.argv[2], sys.argv[3], "--lan" in sys.argv)
