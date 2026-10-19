"""Processo de trabalho: base de dados + servidor HTTP local. Corre separado da janela,
para que o Windows nunca marque a janela como "Não responde" enquanto o Python calcula.

Os diálogos de ficheiros usam tkinter (funciona sem janela principal)."""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

FOLDER_DIALOG, OPEN_DIALOG, SAVE_DIALOG = 1, 2, 3


class TkDialogs:
    """Substitui window.create_file_dialog do pywebview dentro do processo de trabalho."""

    def _root(self):
        import tkinter as tk
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        return root

    @staticmethod
    def _types(file_types):
        out = []
        for ft in file_types or ():
            # "Excel (*.xlsx)" -> ("Excel", "*.xlsx")
            name, _, pat = ft.partition("(")
            out.append((name.strip(), pat.rstrip(")").strip() or "*.*"))
        return out or [("Todos", "*.*")]

    def create_file_dialog(self, kind, allow_multiple=False, save_filename="", file_types=()):
        from tkinter import filedialog
        root = self._root()
        try:
            if kind == FOLDER_DIALOG:
                p = filedialog.askdirectory(title="Escolhe a pasta com os CSV")
            elif kind == OPEN_DIALOG:
                p = filedialog.askopenfilename(filetypes=self._types(file_types))
            else:
                ext = Path(save_filename).suffix
                p = filedialog.asksaveasfilename(initialfile=save_filename, defaultextension=ext, filetypes=self._types(file_types))
        finally:
            root.destroy()
        return [p] if p else None

    def evaluate_js(self, code):  # sem janela neste processo; o progresso é consultado por polling
        pass


def run(port: int, data_dir: str, log_path: str):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s worker %(threadName)s %(message)s",
                        handlers=[logging.FileHandler(log_path, encoding="utf-8")])
    import os
    os.environ["FLIGHTPLOTTER_DATA"] = data_dir
    from app import Api
    from core.db import resource_path
    from core.httpapi import start_server
    api = Api()
    api.window = TkDialogs()
    start_server(api, resource_path("ui"), port)
    logging.info("worker pronto na porta %s", port)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    run(int(sys.argv[1]), sys.argv[2], sys.argv[3])
