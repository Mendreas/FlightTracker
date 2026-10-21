"""Camada de dados do FlightTracker — DuckDB.

Ideia central:
  * Importar: cada CSV do CNS é lido UMA vez (DuckDB, multi-thread) e guardado
    em formato colunar/tipado na base `flightplotter.duckdb`.
  * Consultar: filtros, voos e trajetórias são SQL sobre essa base (milissegundos).

Tabelas:
  files   -> um registo por CSV importado (caminho, tamanho, mtime, data, bloco, aeroporto)
  points  -> todos os plots (tipados: lat/lon DOUBLE, alt INTEGER, tod_sec DOUBLE…)
  flights -> um registo por movimento (date+airport+csn, separado em pernas quando
             há buracos > GAP_SPLIT_S), com classificação ARR/DEP/LVL e tipo (NMIR)
  nmir    -> callsign+data -> tipo de aeronave / WTC
"""
from __future__ import annotations

import logging
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Iterable

import duckdb

from .filenames import parse_path, block_from_hour

AIRPORT_CENTERS = {"LPPT": (38.7813, -9.1359), "LPPR": (41.2481, -8.6814), "LPFR": (37.0153, -7.9723), "LPMA": (32.6978, -16.7745)}
NEAREST_AIRPORT_SQL = ("CASE " + " ".join(
    f"WHEN d_{k} = least({', '.join(f'd_{a}' for a in AIRPORT_CENTERS)}) THEN '{k}'" for k in AIRPORT_CENTERS) + " END")

GAP_SPLIT_S = 300          # buraco de tempo que separa dois movimentos do mesmo callsign
MIN_POINTS_FLIGHT = 3      # movimentos com menos plots são ignorados

# nome normalizado -> candidatos nos cabeçalhos dos CSV (minúsculas)
COLUMN_CANDIDATES = {
    "csn":   ["csn", "callsign", "call_sign", "acid"],
    "tod":   ["tod", "time", "hora", "timestamp"],
    "lat":   ["latitude", "lat"],
    "lon":   ["longitude", "lon", "long"],
    "modec": ["modec", "mode_c", "fl"],
    "baroh": ["baroh", "baro", "altitude", "alt"],
    "tas":   ["tas", "tasa"],
    "ias":   ["iar", "iara", "ias"],
    "roc":   ["roc", "vs", "vz"],
    "gs":    ["gspa", "gs", "groundspeed"],
    "modes": ["modes", "mode_s", "address", "icao24"],
    "modea": ["modea", "mode_a", "squawk", "ssr"],
    "trknr": ["trknr", "track", "trk"],
}


def resource_path(*parts) -> Path:
    """Caminho para ficheiros empacotados (funciona em dev e no .exe do PyInstaller)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base.joinpath(*parts)


# Ordem das colunas nos CSV do CNS (usada quando o ficheiro vem sem linha de cabeçalho)
CNS_DEFAULT_COLUMNS = ("latitude", "longitude", "tod", "trknr", "modes", "modea", "csn", "modec", "x", "y", "baroh",
                       "vx", "vy", "roc", "ts", "tas", "gspadd", "iar", "mac", "gspa", "tasa", "iara", "maca", "rectime")


class Database:
    def __init__(self, db_path: str | os.PathLike):
        self.path = str(db_path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._main = duckdb.connect(self.path)
        self._main.execute("PRAGMA threads=%d" % max(2, (os.cpu_count() or 4)))
        self._main.execute("SET enable_progress_bar=false")
        self._tls = threading.local()
        self._init_schema()

    @property
    def con(self):
        """Ligação principal; uma thread que chamou use_own_connection() usa um cursor próprio
        (o DuckDB serve leituras e escritas concorrentes de cursores diferentes — a importação
        deixa de bloquear as consultas da interface)."""
        return getattr(self._tls, "con", None) or self._main

    def use_own_connection(self):
        self._tls.con = self._main.cursor()

    def release_own_connection(self):
        c = getattr(self._tls, "con", None)
        if c is not None:
            try: c.close()
            except Exception: pass
            self._tls.con = None

    # ------------------------------------------------------------------ schema
    def _init_schema(self):
        c = self.con
        c.execute("""
        CREATE TABLE IF NOT EXISTS files(
            file_id INTEGER PRIMARY KEY,
            path VARCHAR UNIQUE, name VARCHAR, size BIGINT, mtime DOUBLE,
            airport VARCHAR, date VARCHAR, block VARCHAR,
            n_rows INTEGER, imported_at TIMESTAMP DEFAULT current_timestamp)""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS points(
            file_id INTEGER, airport VARCHAR, date VARCHAR, block VARCHAR,
            csn VARCHAR, tod VARCHAR, tod_sec DOUBLE,
            lat DOUBLE, lon DOUBLE, alt INTEGER,
            tas DOUBLE, ias DOUBLE, roc DOUBLE, gs DOUBLE,
            modes VARCHAR, modea VARCHAR, trknr VARCHAR)""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS flights(
            flight_id INTEGER, airport VARCHAR, date VARCHAR, csn VARCHAR, leg INTEGER,
            n INTEGER, t_first DOUBLE, t_last DOUBLE, tod_first VARCHAR, tod_last VARCHAR,
            alt_first INTEGER, alt_last INTEGER, alt_min INTEGER, alt_max INTEGER,
            cls VARCHAR, modes VARCHAR, actype VARCHAR, wtc VARCHAR, blocks VARCHAR)""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS nmir(
            csn VARCHAR, date VARCHAR, actype VARCHAR, wtc VARCHAR, adep VARCHAR, ades VARCHAR)""")
        for col in ("adep", "ades"):   # bases criadas por versões anteriores
            c.execute(f"ALTER TABLE nmir ADD COLUMN IF NOT EXISTS {col} VARCHAR")
        for col in ("etot", "ctot", "atot", "eta", "ata", "atfm_delay"):
            c.execute(f"ALTER TABLE nmir ADD COLUMN IF NOT EXISTS {col} DOUBLE")
        c.execute("CREATE TABLE IF NOT EXISTS meta(key VARCHAR PRIMARY KEY, value VARCHAR)")
        c.execute("CREATE TABLE IF NOT EXISTS analysis_cache(key VARCHAR PRIMARY KEY, flight_id INTEGER, value VARCHAR, created TIMESTAMP DEFAULT current_timestamp)")
        c.execute("CREATE TABLE IF NOT EXISTS user_points(name VARCHAR PRIMARY KEY, lat DOUBLE, lon DOUBLE, descr VARCHAR)")
        c.execute("CREATE TABLE IF NOT EXISTS aux_files(path VARCHAR PRIMARY KEY, kind VARCHAR, size BIGINT, mtime DOUBLE, rows INTEGER, imported TIMESTAMP DEFAULT current_timestamp)")
        c.execute("CREATE TABLE IF NOT EXISTS type_overrides(actype VARCHAR PRIMARY KEY, wtc VARCHAR, note VARCHAR, ts TIMESTAMP DEFAULT current_timestamp)")
        c.execute("""
        CREATE TABLE IF NOT EXISTS corrections(
            csn VARCHAR, date VARCHAR, cls VARCHAR, actype VARCHAR, wtc VARCHAR, apt VARCHAR, note VARCHAR,
            verified BOOLEAN, ts TIMESTAMP DEFAULT current_timestamp, PRIMARY KEY (csn, date, cls))""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS opdi_events(
            flight_id VARCHAR, icao24 VARCHAR, csn VARCHAR, adep VARCHAR, ades VARCHAR, adep_p VARCHAR, ades_p VARCHAR,
            typecode VARCHAR, model VARCHAR, registration VARCHAR, type VARCHAR, t DOUBLE, lat DOUBLE, lon DOUBLE, alt DOUBLE,
            info_ref VARCHAR, at_apt BOOLEAN, airport VARCHAR, src VARCHAR)""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS ground(
            gid INTEGER, airport VARCHAR, date VARCHAR, mt VARCHAR, csn VARCHAR, rwy VARCHAR,
            actype VARCHAR, reg VARCHAR, ao VARCHAR, wtc VARCHAR, adep VARCHAR, ades VARCHAR, sid VARCHAR, star VARCHAR,
            stand_d VARCHAR, stand_a VARCHAR, apron VARCHAR, taxi_out VARCHAR, taxi_in VARCHAR, hp VARCHAR, ep VARCHAR,
            aobt DOUBLE, hp_time DOUBLE, rwy_ent DOUBLE, atot DOUBLE, aldt DOUBLE, rwy_vac DOUBLE, aibt DOUBLE, ctot DOUBLE,
            spd_vac DOUBLE, ga BOOLEAN, rto BOOLEAN, atfm_delay DOUBLE, regulation VARCHAR, src VARCHAR, raw JSON)""")
        if c.execute("SELECT count(*) FROM files").fetchone()[0] and not c.execute("SELECT value FROM meta WHERE key='airports_geo_v1'").fetchone():
            try:
                n = self.fix_airports()
                c.execute("INSERT OR REPLACE INTO meta VALUES ('airports_geo_v1', ?)", [str(n)])
                self._log(f"aeroportos redetetados pela posição: {n} ficheiro(s) alterado(s)")
            except Exception as e:  # noqa: BLE001 — nunca impedir o arranque por causa desta manutenção
                self._log(f"fix_airports falhou: {e}")
        if c.execute("SELECT count(*) FROM nmir").fetchone()[0] == 0:
            seed = resource_path("data", "nmir_seed.csv")
            if seed.exists():
                c.execute("INSERT INTO nmir SELECT csn, date, actype, wtc, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL FROM read_csv(?, header=true, all_varchar=true)",
                          [str(seed)])

    def fix_airports(self) -> int:
        """Redeteta o aeroporto de cada ficheiro pela posição média dos plots (ficheiros sem ICAO no nome)."""
        from .filenames import airport_from_name
        c = self.con
        rows = c.execute("SELECT file_id, path, airport FROM files").fetchall()
        todo = [fid for fid, path, apt in rows if not airport_from_name(path)]
        if not todo:
            return 0
        dist_cols = ", ".join(f"abs(la-({v[0]}))+abs(lo-({v[1]})) AS d_{k}" for k, v in AIRPORT_CENTERS.items())
        c.execute(f"""
            CREATE OR REPLACE TEMP TABLE fix AS
            SELECT g.file_id, f.airport AS old, g.apt
            FROM (SELECT file_id, {NEAREST_AIRPORT_SQL} AS apt FROM (
                    SELECT file_id, {dist_cols} FROM (
                        SELECT file_id, avg(lat) la, avg(lon) lo FROM points
                        WHERE file_id IN (SELECT unnest(?::INTEGER[])) GROUP BY file_id))) g
            JOIN files f USING (file_id)
            WHERE f.airport IS DISTINCT FROM g.apt""", [todo])
        n = c.execute("SELECT count(*) FROM fix").fetchone()[0]
        if n:
            c.execute("UPDATE files SET airport = x.apt FROM fix x WHERE x.file_id = files.file_id")
            c.execute("UPDATE points SET airport = x.apt FROM fix x WHERE x.file_id = points.file_id")
            self.rebuild_flights()
        return n

    # ------------------------------------------------------------------ import
    @staticmethod
    def scan_folder(folder: str) -> list[str]:
        out = []
        for root, _dirs, files in os.walk(folder):
            for fn in files:
                if fn.lower().endswith((".csv", ".xlsx")) and not fn.startswith((".", "~", "$")):
                    out.append(os.path.join(root, fn))
        out.sort()
        return out

    @staticmethod
    def classify_file(path: str) -> str:
        """'radar' (CSV do CNS), 'opdi' (flight events), 'ground' (export da torre), 'nmir' (Excel) — pela 1ª linha."""
        low = path.lower()
        if low.endswith(".xlsx"):
            return "nmir"
        try:
            hdr = open(path, "rb").readline().decode("utf-8-sig", "replace").lower()
        except OSError:
            return "radar"
        if "flt_id" in hdr and "event_time" in hdr:
            return "opdi"
        if "taxi_out" in hdr and "aldt" in hdr:
            return "ground"
        return "radar"

    def _known_aux(self) -> dict[str, tuple[int, float]]:
        return {p: (s, m) for p, s, m in self.con.execute("SELECT path, size, mtime FROM aux_files").fetchall()}

    def import_aux(self, path: str, kind: str) -> int:
        """Importa um ficheiro NMIR / OPDI / torre e regista-o em aux_files."""
        if kind == "nmir":
            n = self.import_nmir_xlsx(path, rebuild=False)   # a tabela de movimentos é reconstruída uma só vez no fim
        elif kind == "opdi":
            n = self.import_opdi(path)["rows"]
        else:
            n = self.import_ground(path)["rows"]
        st = os.stat(path)
        self.con.execute("INSERT OR REPLACE INTO aux_files VALUES (?,?,?,?,?,current_timestamp)", [path, kind, st.st_size, st.st_mtime, n])
        return n

    def _known_files(self) -> dict[str, tuple[int, float]]:
        return {p: (s, m) for p, s, m in self.con.execute("SELECT path, size, mtime FROM files").fetchall()}

    def pending_files(self, folder: str) -> tuple[list[str], int, list[tuple[str, str]]]:
        """Devolve (CSV radar novos/alterados, total encontrado, outros ficheiros novos [(path, kind)])."""
        known = self._known_files(); known_aux = self._known_aux()
        todo, aux = [], []
        allf = self.scan_folder(folder)
        for p in allf:
            st = os.stat(p)
            kind = self.classify_file(p)
            if kind == "radar":
                k = known.get(p)
                if k is None or k[0] != st.st_size or abs(k[1] - st.st_mtime) > 1:
                    todo.append(p)
            else:
                k = known_aux.get(p)
                if k is None or k[0] != st.st_size or abs(k[1] - st.st_mtime) > 1:
                    aux.append((p, kind))
        return todo, len(allf), aux

    @staticmethod
    def _read_header(path: str):
        """Lê só a 1ª linha: devolve (colunas_minúsculas, encoding, separador, tem_cabeçalho).
        Alguns CSV do CNS vêm sem linha de cabeçalho (a 1ª linha já é um plot): nesse caso
        assume-se a ordem de colunas habitual do CNS."""
        raw = open(path, "rb").readline()
        enc = "utf-8"
        try:
            line = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            line, enc = raw.decode("latin-1"), "latin-1"
        line = line.rstrip("\r\n")
        sep = ";" if line.count(";") >= line.count(",") else ","
        fields = [f.strip().strip('"') for f in line.split(sep)]
        try:
            float(fields[0].replace(",", "."))
            is_data = True
        except (ValueError, IndexError):
            is_data = False
        if is_data:
            if len(fields) == len(CNS_DEFAULT_COLUMNS):
                return list(CNS_DEFAULT_COLUMNS), enc, sep, False
            raise RuntimeError(f"sem cabeçalho e com {len(fields)} colunas (esperava {len(CNS_DEFAULT_COLUMNS)})")
        cols, seen = [], set()
        for c in line.split(sep):
            c = c.strip().strip('"').lower() or "col"
            base, k = c, 1
            while c in seen:            # cabeçalhos repetidos -> col, col_2, ...
                k += 1; c = f"{base}_{k}"
            seen.add(c); cols.append(c)
        return cols, enc, sep, True

    @staticmethod
    def _pick(cols: list[str], key: str):
        for cand in COLUMN_CANDIDATES[key]:
            if cand in cols:
                return cand
        return None

    def _build_select(self, cols: list[str]) -> tuple[str, str]:
        """Devolve (SELECT interno, SELECT externo, WHERE) para um grupo de ficheiros com o mesmo cabeçalho."""
        pick = {k: self._pick(cols, k) for k in COLUMN_CANDIDATES}
        if not (pick["lat"] and pick["lon"] and pick["csn"] and pick["tod"]):
            raise RuntimeError("faltam colunas (csn/tod/latitude/longitude). Cabeçalhos: " + ", ".join(cols[:12]))

        def q(k):
            c = pick[k]
            return f'trim(r."{c}")' if c else "NULL"

        def num(k):
            return f"TRY_CAST(replace({q(k)}, ',', '.') AS DOUBLE)"

        tod = q("tod")
        tod_sec = (f"TRY_CAST(split_part({tod}, ':', 1) AS INTEGER)*3600 + "
                   f"TRY_CAST(split_part({tod}, ':', 2) AS INTEGER)*60 + "
                   f"TRY_CAST(replace(split_part({tod}, ':', 3), ',', '.') AS DOUBLE)")
        # 1ª fase: cada expressão calculada UMA vez; 2ª fase (select) só deriva
        inner = f"""t.file_id, t.airport, t.date, t.block,
               upper({q('csn')}) AS csn, {tod} AS tod, {tod_sec} AS tod_sec,
               {num('lat')} AS lat, {num('lon')} AS lon,
               COALESCE({num('modec')}, {num('baroh')}) AS alt_raw,
               {num('tas')} AS tas, {num('ias')} AS ias, {num('roc')} AS roc, {num('gs')} AS gs,
               {q('modes')} AS modes, {q('modea')} AS modea, {q('trknr')} AS trknr"""
        select = """file_id, airport, date,
               CASE WHEN tod_sec IS NULL THEN block
                    WHEN tod_sec < 14400 THEN '00-04' WHEN tod_sec < 28800 THEN '04-08'
                    WHEN tod_sec < 43200 THEN '08-12' WHEN tod_sec < 57600 THEN '12-16'
                    WHEN tod_sec < 72000 THEN '16-20' ELSE '20-24' END,
               csn, tod, tod_sec, lat, lon,
               CAST(round(CASE WHEN alt_raw < 600 THEN alt_raw*100 ELSE alt_raw END) AS INTEGER),
               tas, ias, roc, gs, modes, modea, trknr"""
        where = "lat IS NOT NULL AND lon IS NOT NULL AND csn IS NOT NULL AND csn <> ''"
        return inner, select, where
        return select, where

    def _log(self, msg: str):
        try:
            with open(Path(self.path).with_name("import.log"), "a", encoding="utf-8") as fh:
                fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
        except Exception:  # noqa: BLE001
            pass

    def _import_batch(self, paths: list[str]) -> tuple[int, list[str]]:
        """Importa vários CSV de uma vez (agrupados por cabeçalho). Devolve (linhas, erros)."""
        t_batch = time.time()
        mb = sum(os.path.getsize(p) for p in paths) / 1048576
        errors = []
        groups: dict[tuple, list[tuple[str, str]]] = {}
        for p in paths:
            try:
                cols, enc, sep, has_header = self._read_header(p)
                groups.setdefault((tuple(cols), enc, sep, has_header), []).append(p)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{os.path.basename(p)}: {e}")
        c = self.con
        total_rows = 0
        for (cols, enc, sep, has_header), plist in groups.items():
            coltypes = {c: "VARCHAR" for c in cols}
            try:
                inner, select, where = self._build_select(list(cols))
            except Exception as e:  # noqa: BLE001
                errors.extend(f"{os.path.basename(p)}: {e}" for p in plist)
                continue
            # remove versões anteriores e prepara metadados por ficheiro
            c.execute("DELETE FROM points WHERE file_id IN (SELECT file_id FROM files WHERE path IN (SELECT unnest(?::VARCHAR[])))", [plist])
            c.execute("DELETE FROM files WHERE path IN (SELECT unnest(?::VARCHAR[]))", [plist])
            next_id = c.execute("SELECT coalesce(max(file_id),0)+1 FROM files").fetchone()[0]
            c.execute("CREATE OR REPLACE TEMP TABLE pending(file_id INTEGER, path VARCHAR, name VARCHAR, size BIGINT, mtime DOUBLE, airport VARCHAR, date VARCHAR, block VARCHAR)")
            rows = []
            for i, p in enumerate(plist):
                st = os.stat(p); m = parse_path(p)
                rows.append((next_id + i, p, os.path.basename(p), st.st_size, st.st_mtime, m["airport"], m["date"], m["block"]))
            c.executemany("INSERT INTO pending VALUES (?,?,?,?,?,?,?,?)", rows)
            try:
                c.execute(f"""
                    INSERT INTO points
                    SELECT {select} FROM (
                        SELECT {inner}
                        FROM read_csv(?, delim=?, header=?, columns=?, auto_detect=false, ignore_errors=true,
                                      null_padding=true, filename=true, encoding=?) r
                        JOIN pending t ON t.path = r.filename
                    ) WHERE {where}""", [plist, sep, has_header, coltypes, enc])
            except Exception as e:  # noqa: BLE001
                errors.extend(f"{os.path.basename(p)}: {e}" for p in plist)
                continue
            # bloco real pela hora mínima dos dados; contagens por ficheiro
            c.execute("""
                CREATE OR REPLACE TEMP TABLE pstat AS
                SELECT file_id, count(*) n, min(tod_sec) tmin FROM points
                WHERE file_id IN (SELECT file_id FROM pending) GROUP BY file_id""")
            # aeroporto pela posição média dos plots quando o nome não o indica
            c.execute("CREATE OR REPLACE TEMP TABLE pgeo AS SELECT file_id, avg(lat) la, avg(lon) lo FROM points WHERE file_id IN (SELECT file_id FROM pending) GROUP BY file_id")
            dist_cols = ", ".join(f"abs(la-({v[0]}))+abs(lo-({v[1]})) AS d_{k}" for k, v in AIRPORT_CENTERS.items())
            c.execute(f"""
                UPDATE pending SET airport = g.apt FROM (SELECT file_id, {NEAREST_AIRPORT_SQL} AS apt FROM (SELECT file_id, {dist_cols} FROM pgeo)) g
                WHERE g.file_id = pending.file_id AND pending.airport IS NULL""")
            c.execute("UPDATE pending SET airport = 'LPPT' WHERE airport IS NULL")
            c.execute("UPDATE points SET airport = t.airport FROM pending t WHERE t.file_id = points.file_id AND points.airport IS DISTINCT FROM t.airport")
            c.execute("""
                UPDATE pending SET block = CASE
                    WHEN s.tmin IS NULL THEN pending.block
                    WHEN s.tmin < 4*3600 THEN '00-04' WHEN s.tmin < 8*3600 THEN '04-08'
                    WHEN s.tmin < 12*3600 THEN '08-12' WHEN s.tmin < 16*3600 THEN '12-16'
                    WHEN s.tmin < 20*3600 THEN '16-20' ELSE '20-24' END
                FROM pstat s WHERE s.file_id = pending.file_id""")
            c.execute("""
                INSERT INTO files(file_id,path,name,size,mtime,airport,date,block,n_rows)
                SELECT p.file_id, p.path, p.name, p.size, p.mtime, p.airport, p.date, p.block, coalesce(s.n,0)
                FROM pending p LEFT JOIN pstat s USING(file_id)""")
            total_rows += c.execute("SELECT coalesce(sum(n),0) FROM pstat").fetchone()[0]
        self._log(f"lote de {len(paths)} ficheiros ({mb:.1f} MB) -> {int(total_rows)} linhas em {time.time()-t_batch:.1f}s"
                  + (f" | erros: {len(errors)}" if errors else ""))
        return int(total_rows), errors

    def import_file(self, path: str) -> int:
        rows, errs = self._import_batch([path])
        if errs:
            raise RuntimeError(errs[0])
        self.rebuild_flights()
        return rows

    def import_folder(self, folder: str, progress: Callable[[int, int, str], None] | None = None,
                      batch_size: int = 24, lock=None) -> dict:
        """lock: opcional; se dado, é tomado apenas durante cada lote (a app continua utilizável entre lotes)."""
        import contextlib
        guard = (lambda: lock) if lock is not None else contextlib.nullcontext
        t0 = time.time()
        self.use_own_connection()
        try:
            return self._import_folder(folder, progress, batch_size, guard, t0)
        finally:
            self.release_own_connection()

    def _import_folder(self, folder, progress, batch_size, guard, t0) -> dict:
        with guard():
            todo, total_found, aux = self.pending_files(folder)
        self._log(f"== importar {folder}: {len(todo)} CSV radar novos + {len(aux)} NMIR/OPDI/torre, de {total_found} (scan {time.time()-t0:.1f}s)")
        aux_done = {"nmir": 0, "opdi": 0, "ground": 0}
        aux_errs: list[str] = []
        for i, (p, kind) in enumerate(aux):
            if progress:
                progress(i, len(aux), f"{ {'nmir': 'NMIR', 'opdi': 'OPDI', 'ground': 'torre'}[kind] }: {os.path.basename(p)}")
            t_a = time.time()
            try:
                with guard():
                    n_a = self.import_aux(p, kind); aux_done[kind] += n_a
                self._log(f"aux {kind} {os.path.basename(p)}: {n_a} registos em {time.time()-t_a:.1f}s")
            except Exception as e:  # noqa: BLE001
                aux_errs.append(f"{os.path.basename(p)}: {e}")
                self._log(f"aux {kind} {p}: ERRO {e}")
        if progress and todo:
            mb = sum(os.path.getsize(p) for p in todo) / 1048576
            progress(0, len(todo), f"{len(todo)} ficheiro(s) novos, {mb:,.0f} MB — a ler…")
        done = rows = 0
        err_list: list[str] = []
        for i in range(0, len(todo), batch_size):
            chunk = todo[i:i + batch_size]
            with guard():
                r, errs = self._import_batch(chunk)
            rows += r; err_list += errs
            done += len(chunk)
            if progress:
                progress(done, len(todo), os.path.basename(chunk[-1]))
        if todo or aux_done["nmir"]:
            if progress:
                progress(done, len(todo), "a construir tabela de movimentos…")
            t_r = time.time()
            with guard():
                self.rebuild_flights()
            self._log(f"rebuild_flights {time.time()-t_r:.1f}s")
        with guard():
            self.con.execute("INSERT OR REPLACE INTO meta VALUES ('last_folder', ?)", [folder])
        err_list = aux_errs + err_list
        self._log(f"== fim: {rows} linhas, {len(err_list)} erros, total {time.time()-t0:.1f}s")
        return {"found": total_found, "new": len(todo) + len(aux), "imported": len(todo) - len(err_list) + len(aux) - len(aux_errs), "errors": len(err_list),
                "rows": rows, "ms": int((time.time() - t0) * 1000), "error_list": err_list[:20], "aux": aux_done, "aux_files": len(aux)}

    def remove_missing(self) -> int:
        """Apaga da base os ficheiros que já não existem no disco."""
        gone = [p for (p,) in self.con.execute("SELECT path FROM files").fetchall() if not os.path.exists(p)]
        for p in gone:
            fid = self.con.execute("SELECT file_id FROM files WHERE path=?", [p]).fetchone()[0]
            self.con.execute("DELETE FROM points WHERE file_id=?", [fid])
            self.con.execute("DELETE FROM files WHERE file_id=?", [fid])
        if gone:
            self.rebuild_flights()
        return len(gone)

    # ----------------------------------------------------------------- flights
    def rebuild_flights(self):
        """Reconstrói a tabela de movimentos a partir de points (rápido: window functions)."""
        self.con.execute("DELETE FROM flights")
        self.con.execute("DELETE FROM analysis_cache")
        self.con.execute(f"""
        INSERT INTO flights
        WITH ordered AS (
            SELECT airport, date, csn, tod, tod_sec, alt, modes, block,
                   tod_sec - lag(tod_sec) OVER (PARTITION BY airport, date, csn ORDER BY tod_sec) AS gap
            FROM points WHERE tod_sec IS NOT NULL
        ), legs AS (
            SELECT *, sum(CASE WHEN gap IS NULL OR gap > {GAP_SPLIT_S} THEN 1 ELSE 0 END)
                      OVER (PARTITION BY airport, date, csn ORDER BY tod_sec ROWS UNBOUNDED PRECEDING) AS leg
            FROM ordered
        ), agg AS (
            SELECT airport, date, csn, leg,
                   count(*) AS n, min(tod_sec) AS t_first, max(tod_sec) AS t_last,
                   arg_min(tod, tod_sec) AS tod_first, arg_max(tod, tod_sec) AS tod_last,
                   arg_min(alt, tod_sec) FILTER (WHERE alt IS NOT NULL) AS alt_first,
                   arg_max(alt, tod_sec) FILTER (WHERE alt IS NOT NULL) AS alt_last,
                   min(alt) AS alt_min, max(alt) AS alt_max,
                   mode(modes) AS modes,
                   string_agg(DISTINCT block, ',' ORDER BY block) AS blocks
            FROM legs GROUP BY airport, date, csn, leg
        )
        SELECT row_number() OVER (ORDER BY a.date, a.airport, a.t_first, a.csn) AS flight_id,
               a.airport, a.date, a.csn, a.leg, a.n, a.t_first, a.t_last, a.tod_first, a.tod_last,
               a.alt_first, a.alt_last, a.alt_min, a.alt_max,
               CASE WHEN a.alt_first IS NULL OR a.alt_max - a.alt_min < 500 THEN 'lvl'
                    WHEN a.alt_last - a.alt_first < -500 THEN 'arr'
                    WHEN a.alt_last - a.alt_first >  500 THEN 'dep'
                    ELSE 'lvl' END AS cls,
               a.modes, nm.actype, nm.wtc, a.blocks
        FROM agg a
        LEFT JOIN (SELECT csn, date, any_value(actype) actype, any_value(wtc) wtc FROM nmir GROUP BY csn, date) nm
               ON nm.csn = a.csn AND nm.date = a.date
        WHERE a.n >= {MIN_POINTS_FLIGHT}
        """)
        # Sem NMIR nesse dia: 2) tipo mais recente do mesmo callsign; 3) mesmo endereço Mode S (= mesma aeronave)
        self.con.execute("""
        UPDATE flights SET actype = nm.actype, wtc = nm.wtc
        FROM (SELECT csn, arg_max(actype, date) actype, arg_max(wtc, date) wtc FROM nmir WHERE actype IS NOT NULL GROUP BY csn) nm
        WHERE flights.actype IS NULL AND nm.csn = flights.csn""")
        self.con.execute("""
        UPDATE flights SET actype = m.actype, wtc = m.wtc
        FROM (SELECT modes, any_value(actype) actype, any_value(wtc) wtc FROM flights
              WHERE actype IS NOT NULL AND modes IS NOT NULL AND modes <> '' GROUP BY modes) m
        WHERE flights.actype IS NULL AND flights.modes IS NOT NULL AND flights.modes <> '' AND m.modes = flights.modes""")
        self.apply_type_overrides()

    # ----------------------------------------------------------------- queries
    def summary(self) -> dict:
        c = self.con
        files, rows = c.execute("SELECT count(*), coalesce(sum(n_rows),0) FROM files").fetchone()
        flights = c.execute("SELECT count(*) FROM flights").fetchone()[0]
        nmir = c.execute("SELECT count(*) FROM nmir").fetchone()[0]
        last = c.execute("SELECT value FROM meta WHERE key='last_folder'").fetchone()
        size = os.path.getsize(self.path) if os.path.exists(self.path) else 0
        return {"files": files, "rows": int(rows), "flights": flights, "nmir": nmir,
                "last_folder": last[0] if last else None, "db_bytes": size, "db_path": self.path}

    def filters(self) -> dict:
        c = self.con
        airports = [r[0] for r in c.execute("SELECT DISTINCT airport FROM files ORDER BY 1").fetchall()]
        dates = [{"date": d, "airport": a, "files": n, "rows": int(r), "blocks": b} for d, a, n, r, b in c.execute(
            "SELECT date, airport, count(*), sum(n_rows), string_agg(DISTINCT block, ',' ORDER BY block) "
            "FROM files GROUP BY date, airport ORDER BY date, airport").fetchall()]
        blocks = [r[0] for r in c.execute("SELECT DISTINCT block FROM files ORDER BY 1").fetchall()]
        return {"airports": airports, "dates": dates, "blocks": blocks}

    def flights_list(self, airport: str | None, dates: Iterable[str], blocks: Iterable[str],
                     csn: str = "", cls: str = "") -> list[dict]:
        """airport=None → todos os aeroportos."""
        dates = list(dates) or ["__none__"]
        blocks = list(blocks)
        params: list = [dates]
        where = ["date IN (SELECT unnest(?::VARCHAR[]))"]
        if airport:
            where.insert(0, "airport = ?"); params.insert(0, airport)
        if blocks:
            # o movimento é mostrado se tocar em pelo menos um dos blocos seleccionados
            where.append("EXISTS (SELECT 1 FROM unnest(string_split(blocks, ',')) AS u(b) "
                         "WHERE b IN (SELECT unnest(?::VARCHAR[])))")
            params.append(blocks)
        if csn:
            where.append("csn ILIKE ?")
            params.append(f"%{csn}%")
        if cls:
            where.append("cls = ?")
            params.append(cls)
        rows = self.con.execute(f"""
            SELECT flight_id, airport, date, csn, leg, n, tod_first, tod_last, t_first, t_last,
                   alt_first, alt_last, alt_min, alt_max, cls, modes, actype, wtc, blocks
            FROM flights WHERE {' AND '.join(where)}
            ORDER BY date, airport, t_first""", params).fetchall()
        keys = ["flight_id", "airport", "date", "csn", "leg", "n", "tod_first", "tod_last", "t_first", "t_last",
                "alt_first", "alt_last", "alt_min", "alt_max", "cls", "modes", "actype", "wtc", "blocks"]
        return [dict(zip(keys, r)) for r in rows]

    def tracks(self, flight_ids: Iterable[int], max_points: int = 120_000) -> dict:
        """Trajetórias dos movimentos pedidos. Reduz amostragem se exceder max_points."""
        ids = list(flight_ids)
        if not ids:
            return {"tracks": {}, "step": 1, "points": 0}
        total = self.con.execute(
            "SELECT coalesce(sum(n),0) FROM flights WHERE flight_id IN (SELECT unnest(?::INTEGER[]))", [ids]).fetchone()[0]
        step = max(1, int(total // max_points) + (1 if total % max_points else 0)) if total > max_points else 1
        rows = self.con.execute(f"""
            WITH sel AS (SELECT * FROM flights WHERE flight_id IN (SELECT unnest(?::INTEGER[])))
            SELECT s.flight_id, p.tod, p.tod_sec, p.lat, p.lon, p.alt, p.ias, p.gs, p.roc, p.tas
            FROM sel s JOIN points p
              ON p.airport = s.airport AND p.date = s.date AND p.csn = s.csn
             AND p.tod_sec BETWEEN s.t_first AND s.t_last
            QUALIFY (row_number() OVER (PARTITION BY s.flight_id ORDER BY p.tod_sec) - 1) % {step} = 0
            ORDER BY s.flight_id, p.tod_sec""", [ids]).fetchall()
        out: dict[int, list] = {}
        r5 = lambda v: None if v is None else round(v, 5)
        r0 = lambda v: None if v is None else round(v)
        for fid, tod, ts, lat, lon, alt, ias, gs, roc, tas in rows:
            out.setdefault(fid, []).append([r5(lat), r5(lon), alt, tod, r0(ias), r0(gs), r0(roc), r0(tas), ts])
        return {"tracks": out, "step": step, "points": len(rows)}

    def flight_points(self, flight_id: int) -> list[dict]:
        rows = self.con.execute("""
            SELECT p.tod, p.tod_sec, p.lat, p.lon, p.alt, p.ias, p.tas, p.gs, p.roc, p.modea, p.modes, p.trknr, p.block
            FROM flights s JOIN points p
              ON p.airport = s.airport AND p.date = s.date AND p.csn = s.csn
             AND p.tod_sec BETWEEN s.t_first AND s.t_last
            WHERE s.flight_id = ? ORDER BY p.tod_sec""", [flight_id]).fetchall()
        keys = ["tod", "tod_sec", "lat", "lon", "alt", "ias", "tas", "gs", "roc", "modea", "modes", "trknr", "block"]
        return [dict(zip(keys, r)) for r in rows]

    def points_bulk(self, flight_ids: Iterable[int]) -> dict[int, list[tuple]]:
        """Todos os plots dos movimentos pedidos, ordenados por tempo.
        Tuplo: (tod_sec, lat, lon, alt, ias, gs, roc, tas, tod, block, modea)."""
        ids = list(flight_ids)
        if not ids:
            return {}
        rows = self.con.execute("""
            WITH sel AS (SELECT * FROM flights WHERE flight_id IN (SELECT unnest(?::INTEGER[])))
            SELECT s.flight_id, p.tod_sec, p.lat, p.lon, p.alt, p.ias, p.gs, p.roc, p.tas, p.tod, p.block, p.modea
            FROM sel s JOIN points p
              ON p.airport = s.airport AND p.date = s.date AND p.csn = s.csn
             AND p.tod_sec BETWEEN s.t_first AND s.t_last
            WHERE p.tod_sec IS NOT NULL
            ORDER BY s.flight_id, p.tod_sec""", [ids]).fetchall()
        out: dict[int, list] = {}
        for r in rows:
            out.setdefault(r[0], []).append(r[1:])
        return out

    def points_with_approach(self, flight_ids: Iterable[int], rwys: dict) -> dict[int, list[tuple]]:
        """Plots + coordenadas no eixo de aproximação (along/cross em NM) calculadas em SQL para cada pista.
        rwys: {rid: {"thr": (lat, lon), "brg": deg}}. Tuplo: (epoch_s, lat, lon, alt, ias, along_r1, cross_r1, along_r2, cross_r2, ...)."""
        ids = list(flight_ids)
        if not ids:
            return {}
        cols = []
        for rid, r in rwys.items():
            tl, tn, brg = r["thr"][0], r["thr"][1], r["brg"]
            d = (f"3440.065*2*asin(sqrt(pow(sin(radians(p.lat-({tl}))/2),2)+cos(radians({tl}))*cos(radians(p.lat))"
                 f"*pow(sin(radians(p.lon-({tn}))/2),2)))")
            br = (f"(degrees(atan2(sin(radians(p.lon-({tn})))*cos(radians(p.lat)),"
                  f"cos(radians({tl}))*sin(radians(p.lat))-sin(radians({tl}))*cos(radians(p.lat))*cos(radians(p.lon-({tn})))))+360)%360")
            delta = f"((({br})-({(brg + 180) % 360})+540)%360-180)"
            cols.append(f"{d}*cos(radians({delta})) AS along_{rid}, {d}*sin(radians({delta})) AS cross_{rid}")
        rows = self.con.execute(f"""
            WITH sel AS (SELECT * FROM flights WHERE flight_id IN (SELECT unnest(?::INTEGER[])))
            SELECT s.flight_id,
                   (CASE WHEN s.date ~ '^[0-9]{{6}}$' THEN date_diff('day', DATE '2000-01-01', try_strptime(s.date, '%y%m%d')::DATE) ELSE 0 END)*86400 + p.tod_sec AS ep,
                   p.lat, p.lon, p.alt, p.ias, {', '.join(cols)}
            FROM sel s JOIN points p
              ON p.airport = s.airport AND p.date = s.date AND p.csn = s.csn
             AND p.tod_sec BETWEEN s.t_first AND s.t_last
            WHERE p.tod_sec IS NOT NULL AND p.lat IS NOT NULL AND p.lon IS NOT NULL AND p.lat <> 0 AND p.lon <> 0
            ORDER BY s.flight_id, p.tod_sec""", [ids]).fetchall()
        out: dict[int, list] = {}
        for r in rows:
            out.setdefault(r[0], []).append(r[1:])
        return out

    def cache_get(self, keys: Iterable[str]) -> dict[str, str]:
        keys = list(keys)
        if not keys:
            return {}
        return dict(self.con.execute("SELECT key, value FROM analysis_cache WHERE key IN (SELECT unnest(?::VARCHAR[]))", [keys]).fetchall())

    def cache_put(self, items: list[tuple[str, int, str]]):
        if items:
            keys = [i[0] for i in items]; fids = [i[1] for i in items]; vals = [i[2] for i in items]
            try:
                self.con.execute(
                    "INSERT OR REPLACE INTO analysis_cache(key, flight_id, value) "
                    "SELECT * FROM (SELECT unnest(?::VARCHAR[]) k, unnest(?::INTEGER[]) f, unnest(?::VARCHAR[]) v)", [keys, fids, vals])
            except Exception as e:  # conflito com uma importação a decorrer: a cache é só uma otimização
                logging.warning("cache_put ignorado: %s", e)

    def cache_clear(self):
        self.con.execute("DELETE FROM analysis_cache")

    def user_points(self) -> list[dict]:
        return [{"name": n, "lat": la, "lon": lo, "desc": d or "Ponto manual", "type": "user"}
                for n, la, lo, d in self.con.execute("SELECT name, lat, lon, descr FROM user_points ORDER BY name").fetchall()]

    def user_point_add(self, name: str, lat: float, lon: float, desc: str = "Ponto manual"):
        self.con.execute("INSERT OR REPLACE INTO user_points VALUES (?,?,?,?)", [name.upper().strip(), float(lat), float(lon), desc])

    def user_point_remove(self, name: str):
        self.con.execute("DELETE FROM user_points WHERE name=?", [name.upper().strip()])

    def setting_get(self, key: str, default=None):
        r = self.con.execute("SELECT value FROM meta WHERE key=?", [key]).fetchone()
        return r[0] if r else default

    def setting_set(self, key: str, value: str):
        self.con.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", [key, value])

    def stats(self, airport: str | None, dates: Iterable[str], blocks: Iterable[str]) -> dict:
        dates = list(dates) or ["__none__"]
        r = self.con.execute(f"""
            SELECT count(*), sum(CASE WHEN cls='arr' THEN 1 ELSE 0 END),
                   sum(CASE WHEN cls='dep' THEN 1 ELSE 0 END), sum(CASE WHEN cls='lvl' THEN 1 ELSE 0 END),
                   coalesce(sum(n),0), count(DISTINCT csn)
            FROM flights WHERE {'airport=? AND ' if airport else ''}date IN (SELECT unnest(?::VARCHAR[]))""",
            ([airport] if airport else []) + [dates]).fetchone()
        return {"flights": r[0], "arr": r[1] or 0, "dep": r[2] or 0, "lvl": r[3] or 0, "points": int(r[4]), "csn": r[5]}

    def import_nmir_xlsx(self, path: str, rebuild: bool = True) -> int:
        """Importa um Excel NMIR (EUROCONTROL) com openpyxl: precisa de colunas com callsign e tipo
        (data e WTC opcionais). Devolve o nº de registos novos."""
        from openpyxl import load_workbook
        from datetime import date, datetime, timezone
        from .geo import wtc_from_type
        wb = load_workbook(path, read_only=True, data_only=True)
        rows_out = []
        for ws in wb.worksheets:
            it = ws.iter_rows(values_only=True)
            header = None
            for row in it:
                if row and any(isinstance(v, str) and v.strip() for v in row):
                    header = [str(v).strip().lower() if v is not None else "" for v in row]
                    break
            if not header:
                continue

            def find(*cands):
                for cnd in cands:
                    for i, h in enumerate(header):
                        if cnd in h:
                            return i
                return None
            i_csn = find("callsign", "call sign", "csn", "aircraft id")
            i_type = find("aircraft type", "actype", "ac type", "type")
            i_date = find("lobd", "eobd", "date", "data", "dof", "lobt", "eobt")   # LOBD = dia do voo (NMIR)
            i_wtc = find("wtc", "wake")
            i_adep = find("adep", "departure"); i_ades = find("ades", "destination")
            if i_ades is not None and "diverted" in header[i_ades]:
                i_ades = next((i for i, h in enumerate(header) if h == "ades"), i_ades)
            exact = lambda name: next((i for i, h in enumerate(header) if h == name), None)
            i_etot, i_ctot, i_atot, i_eta, i_ata = exact("etot"), exact("ctot"), exact("atot"), exact("eta"), exact("ata")
            i_dly = find("atfm delay", "atfm_delay")
            def ts(i):
                if i is None or i >= len(row) or row[i] in (None, ""):
                    return None
                v = row[i]
                if isinstance(v, (datetime, date)):
                    return v.replace(tzinfo=timezone.utc).timestamp() if isinstance(v, datetime) else None
                try:
                    return datetime.strptime(str(v).strip()[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
                except ValueError:
                    try:
                        return datetime.strptime(str(v).strip()[:16], "%d/%m/%Y %H:%M").replace(tzinfo=timezone.utc).timestamp()
                    except ValueError:
                        return None
            if i_csn is None or i_type is None:
                continue
            for row in it:
                if not row or i_csn >= len(row) or i_type >= len(row):
                    continue
                csn, typ = row[i_csn], row[i_type]
                if not csn or not typ:
                    continue
                d = None
                if i_date is not None and i_date < len(row) and row[i_date] is not None:
                    v = row[i_date]
                    if isinstance(v, (datetime, date)):
                        d = v.strftime("%y%m%d")
                    else:
                        sv = str(v).strip()
                        m = re.match(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", sv)      # dd/mm/yyyy
                        if m:
                            d = f"{int(m.group(3)) % 100:02d}{int(m.group(2)):02d}{int(m.group(1)):02d}"
                        else:
                            s2 = "".join(ch for ch in sv if ch.isdigit())
                            if len(s2) >= 8 and s2[:2] == "20":      # yyyymmdd[hhmm]
                                d = s2[2:8]
                            elif len(s2) == 6:
                                d = s2
                wtc = row[i_wtc] if i_wtc is not None and i_wtc < len(row) else None
                typ_s = str(typ).strip().upper()
                cell = lambda i: (str(row[i]).strip().upper() or None) if i is not None and i < len(row) and row[i] else None
                dly = None
                if i_dly is not None and i_dly < len(row) and row[i_dly] not in (None, ""):
                    try: dly = float(str(row[i_dly]).replace(",", "."))
                    except ValueError: dly = None
                rows_out.append((str(csn).strip().upper(), d, typ_s,
                                 str(wtc).strip().upper() if wtc else (wtc_from_type(typ_s) or None), cell(i_adep), cell(i_ades),
                                 ts(i_etot), ts(i_ctot), ts(i_atot), ts(i_eta), ts(i_ata), dly))
        if not rows_out:
            raise RuntimeError("Excel sem colunas reconhecidas (callsign / aircraft type).")
        before = self.con.execute("SELECT count(*) FROM (SELECT DISTINCT csn, date FROM nmir)").fetchone()[0]
        cols = list(zip(*rows_out))
        self.con.execute("INSERT INTO nmir SELECT * FROM (SELECT unnest(?::VARCHAR[]), unnest(?::VARCHAR[]), unnest(?::VARCHAR[]), unnest(?::VARCHAR[]), unnest(?::VARCHAR[]), unnest(?::VARCHAR[]), "
                         "unnest(?::DOUBLE[]), unnest(?::DOUBLE[]), unnest(?::DOUBLE[]), unnest(?::DOUBLE[]), unnest(?::DOUBLE[]), unnest(?::DOUBLE[]))",
                         [list(c) for c in cols])
        # a mesma (csn, data) pode já existir sem ADEP/ADES (base inicial): fica a versão mais completa
        self.con.execute("""CREATE OR REPLACE TABLE nmir AS
            SELECT csn, date, arg_max(actype, coalesce(adep,'')||coalesce(ades,'')) actype,
                   arg_max(wtc, coalesce(adep,'')||coalesce(ades,'')) wtc, max(adep) adep, max(ades) ades,
                   max(etot) etot, max(ctot) ctot, max(atot) atot, max(eta) eta, max(ata) ata, max(atfm_delay) atfm_delay
            FROM nmir GROUP BY csn, date""")
        if rebuild:
            self.rebuild_flights()
        return max(0, self.con.execute("SELECT count(*) FROM (SELECT DISTINCT csn, date FROM nmir)").fetchone()[0] - before)

    # ----------------------------------------------------------------- solo (ficheiro da torre)
    def import_ground(self, path: str, airport: str = "LPPT") -> dict:
        """Importa o export operacional da torre (ALL_LPPT_AAAA-MM-DD_..csv, separador ';').
        Guarda os campos principais tipados e a linha completa em JSON (raw) para relatórios à medida."""
        c = self.con
        hdr = open(path, "rb").readline().decode("utf-8-sig", "replace")
        if "TAXI_OUT" not in hdr.upper() or "ALDT" not in hdr.upper():
            raise RuntimeError("Este ficheiro não parece ser o export da torre (faltam colunas TAXI_OUT / ALDT).")
        sep = ";" if hdr.count(";") >= hdr.count(",") else ","
        cols = [h.strip().strip('"') for h in hdr.rstrip("\r\n").split(sep)]
        up = {h.upper(): h for h in cols}
        def col(name, cast="VARCHAR"):
            h = up.get(name.upper())
            if h is None:
                return "NULL"
            q = f'r."{h}"'
            if cast == "TS":
                return f"epoch(try_strptime(nullif(trim({q}),''), '%Y-%m-%d %H:%M:%S'))"
            if cast == "NUM":
                return f"TRY_CAST(replace(nullif(trim({q}),''), ',', '.') AS DOUBLE)"
            if cast == "BOOL":
                return f"(upper(trim({q})) = 'TRUE')"
            return f"nullif(trim({q}),'')"
        src = os.path.basename(path)
        c.execute("DELETE FROM ground WHERE src = ?", [src])
        next_id = c.execute("SELECT coalesce(max(gid),0)+1 FROM ground").fetchone()[0]
        c.execute(f"""
        INSERT INTO ground
        SELECT {next_id} + row_number() OVER () - 1, ?, strftime(TRY_CAST({col('DATE')} AS DATE), '%y%m%d'), upper({col('MT')}),
               upper({col('CALLSIGN')}), {col('RWY')}, {col('AC_TYPE')}, {col('REG')}, {col('AO')},
               CASE upper({col('ICAO_WTC')}) WHEN 'HEAVY' THEN 'H' WHEN 'MEDIUM' THEN 'M' WHEN 'LIGHT' THEN 'L' WHEN 'SUPER' THEN 'J' ELSE {col('ICAO_WTC')} END,
               {col('ADEP')}, {col('ADES')}, {col('SID')}, {col('STAR')},
               {col('STANDD')}, {col('STANDA')}, {col('APRON')}, {col('TAXI_OUT')}, {col('TAXI_IN')}, {col('HP')}, {col('EP')},
               {col('AOBT','TS')}, {col('HP_TIME','TS')}, {col('RWY_ENT','TS')}, {col('ATOT','TS')}, {col('ALDT','TS')}, {col('RWY_VAC','TS')}, {col('AIBT','TS')}, {col('CTOT','TS')},
               {col('SPD@RWY_VAC','NUM')}, {col('GA','BOOL')}, {col('RTO','BOOL')}, {col('ATFM_DELAY','NUM')}, {col('REGULATION_NAME')}, ?, to_json(r)
        FROM read_csv(?, delim=?, header=true, all_varchar=true, ignore_errors=true, null_padding=true) r
        WHERE {col('CALLSIGN')} IS NOT NULL""", [airport, src, path, sep])
        n = c.execute("SELECT count(*) FROM ground WHERE src=?", [src]).fetchone()[0]
        d0, d1 = c.execute("SELECT min(date), max(date) FROM ground WHERE src=?", [src]).fetchone()
        self._log(f"ground: {src} -> {n} movimentos ({d0}..{d1})")
        return {"rows": n, "from": d0, "to": d1}

    # ----------------------------------------------------------------- OPDI (EUROCONTROL / OpenSky)
    def import_opdi(self, path: str, airport: str = "LPPT") -> dict:
        """Importa um CSV de flight events do OPDI (opdi_LPPT_AAAAMMDD.csv)."""
        hdr = open(path, "rb").readline().decode("utf-8-sig", "replace").lower()
        if "event_time" not in hdr or "flt_id" not in hdr:
            raise RuntimeError("Este ficheiro não parece ser um CSV de eventos OPDI (faltam flt_id / event_time).")
        src = os.path.basename(path)
        c = self.con
        c.execute("DELETE FROM opdi_events WHERE src = ?", [src])
        at_col = next((h for h in hdr.rstrip("\r\n").split(",") if h.startswith("at_")), None)
        at_expr = f'(lower(trim(r."{at_col}")) = \'true\')' if at_col else "NULL"
        c.execute(f"""
        INSERT INTO opdi_events
        SELECT r.flight_id, lower(trim(r.icao24)), upper(trim(r.flt_id)), nullif(upper(trim(r.adep)),''), nullif(upper(trim(r.ades)),''),
               nullif(upper(trim(r.adep_p)),''), nullif(upper(trim(r.ades_p)),''), nullif(upper(trim(r.typecode)),''), nullif(trim(r.model),''),
               nullif(upper(trim(r.registration)),''), trim(r.type),
               epoch(try_strptime(trim(r.event_time), '%Y-%m-%d %H:%M:%S')), TRY_CAST(r.latitude AS DOUBLE), TRY_CAST(r.longitude AS DOUBLE), TRY_CAST(r.altitude AS DOUBLE),
               nullif(nullif(trim(r.info_ref),''),'nan'), {at_expr}, ?, ?
        FROM read_csv(?, header=true, all_varchar=true, ignore_errors=true, null_padding=true) r""", [airport, src, path])
        n = c.execute("SELECT count(*) FROM opdi_events WHERE src=?", [src]).fetchone()[0]
        nf = c.execute("SELECT count(DISTINCT flight_id) FROM opdi_events WHERE src=?", [src]).fetchone()[0]
        self._log(f"opdi: {src} -> {n} eventos, {nf} voos")
        return {"rows": n, "flights": nf}

    def opdi_summary(self) -> dict:
        r = self.con.execute("SELECT count(*), count(DISTINCT flight_id), strftime(to_timestamp(min(t)), '%y%m%d'), strftime(to_timestamp(max(t)), '%y%m%d') FROM opdi_events").fetchone()
        return {"events": r[0], "flights": r[1], "from": r[2], "to": r[3]}

    def opdi_flights(self, airport: str, dates: list[str]) -> list[dict]:
        """Um registo por voo OPDI com ligação ao aeroporto (ADEP ou ADES) e marcos: entrada/saída de pista no
        aeroporto, descolagem/aterragem, TOC/TOD, cruzamentos FL50/FL100, nº de patamares abaixo FL100."""
        if not dates:
            return []
        cur = self.con.execute("""
        WITH e AS (SELECT * FROM opdi_events WHERE airport = ? AND (adep = ? OR ades = ?)),
        f AS (SELECT flight_id, any_value(icao24) icao24, any_value(csn) csn, any_value(adep) adep, any_value(ades) ades,
                     any_value(typecode) typecode, any_value(registration) reg, any_value(model) model,
                     min(t) FILTER (type='first_seen') t_first, max(t) FILTER (type='last_seen') t_last,
                     min(t) FILTER (type='entry-runway' AND at_apt) t_rwy_in, max(t) FILTER (type='exit-runway' AND at_apt) t_rwy_out,
                     any_value(info_ref) FILTER (type IN ('exit-runway','entry-runway') AND at_apt) rwy_ref,
                     min(t) FILTER (type='take-off') t_takeoff, max(t) FILTER (type='landing') t_landing,
                     min(t) FILTER (type='top-of-climb') t_toc, max(t) FILTER (type='top-of-descent') t_tod,
                     min(t) FILTER (type='first-xing-fl50') t_fx50, min(t) FILTER (type='first-xing-fl100') t_fx100,
                     max(t) FILTER (type='last-xing-fl100') t_lx100, max(t) FILTER (type='last-xing-fl50') t_lx50,
                     count(*) FILTER (type='level-start' AND alt < 10000 AND alt > 1500) n_levels_low,
                     string_agg(DISTINCT info_ref, ' ') FILTER (type IN ('entry-taxiway','exit-taxiway') AND at_apt AND info_ref IS NOT NULL) twy,
                     min(t) FILTER (type='entry-parking_position' AND at_apt) t_park_in, max(t) FILTER (type='exit-parking_position' AND at_apt) t_park_out
              FROM e GROUP BY flight_id)
        SELECT *, CASE WHEN ades = ? THEN 'arr' ELSE 'dep' END cls,
               strftime(to_timestamp(coalesce(CASE WHEN ades = ? THEN coalesce(t_rwy_in, t_last, t_landing) ELSE coalesce(t_rwy_out, t_takeoff, t_first) END, t_first)), '%y%m%d') date
        FROM f
        WHERE strftime(to_timestamp(coalesce(CASE WHEN ades = ? THEN coalesce(t_rwy_in, t_last, t_landing) ELSE coalesce(t_rwy_out, t_takeoff, t_first) END, t_first)), '%y%m%d')
              IN (SELECT unnest(?::VARCHAR[]))""", [airport, airport, airport, airport, airport, airport, dates])
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]

    # ----------------------------------------------------------------- correções (cruzamento)
    def correction_set(self, csn: str, date: str, cls: str, actype=None, wtc=None, apt=None, note=None, verified=False, airport=None) -> dict:
        from .geo import wtc_from_type
        actype = (actype or "").strip().upper() or None
        wtc = (wtc or "").strip().upper() or (wtc_from_type(actype) if actype else None)
        apt = (apt or "").strip().upper() or None
        self.con.execute("INSERT OR REPLACE INTO corrections VALUES (?,?,?,?,?,?,?,?,current_timestamp)",
                         [csn, date, cls, actype, wtc, apt, note, bool(verified)])
        if actype:
            # propaga: movimento radar + NMIR desse dia (sobrevive a reconstruções da tabela de movimentos)
            self.con.execute("UPDATE flights SET actype=?, wtc=? WHERE csn=? AND date=? AND cls=?" + (" AND airport=?" if airport else ""),
                             [actype, wtc, csn, date, cls] + ([airport] if airport else []))
            old = self.con.execute("SELECT adep, ades FROM nmir WHERE csn=? AND date=? LIMIT 1", [csn, date]).fetchone()
            self.con.execute("DELETE FROM nmir WHERE csn=? AND date=?", [csn, date])
            self.con.execute("INSERT INTO nmir (csn, date, actype, wtc, adep, ades) VALUES (?,?,?,?,?,?)", [csn, date, actype, wtc, old[0] if old else None, old[1] if old else None])
        if apt:
            field = "adep" if cls == "arr" else "ades"
            if self.con.execute("SELECT 1 FROM nmir WHERE csn=? AND date=?", [csn, date]).fetchone():
                self.con.execute(f"UPDATE nmir SET {field}=? WHERE csn=? AND date=?", [apt, csn, date])
        self.cache_clear()
        return self.correction_get(csn, date, cls)

    def type_wtc_set(self, actype: str, wtc: str, note: str | None = None) -> int:
        """WTC corrigida para um tipo de aeronave: vale para todos os movimentos, presentes e futuros."""
        actype = actype.strip().upper(); wtc = wtc.strip().upper()
        self.con.execute("INSERT OR REPLACE INTO type_overrides VALUES (?,?,?,current_timestamp)", [actype, wtc, note])
        self.con.execute("UPDATE nmir SET wtc=? WHERE actype=?", [wtc, actype])
        n = self.con.execute("SELECT count(*) FROM flights WHERE actype=? AND coalesce(wtc,'') <> ?", [actype, wtc]).fetchone()[0]
        self.con.execute("UPDATE flights SET wtc=? WHERE actype=?", [wtc, actype])
        self.cache_clear()
        return n

    def type_overrides(self) -> dict:
        return {a: w for a, w in self.con.execute("SELECT actype, wtc FROM type_overrides").fetchall()}

    def apply_type_overrides(self):
        self.con.execute("UPDATE flights SET wtc = o.wtc FROM type_overrides o WHERE flights.actype = o.actype")
        self.con.execute("UPDATE nmir SET wtc = o.wtc FROM type_overrides o WHERE nmir.actype = o.actype")

    def correction_delete(self, csn: str, date: str, cls: str):
        self.con.execute("DELETE FROM corrections WHERE csn=? AND date=? AND cls=?", [csn, date, cls])

    def correction_get(self, csn, date, cls):
        r = self.con.execute("SELECT actype, wtc, apt, note, verified, ts FROM corrections WHERE csn=? AND date=? AND cls=?", [csn, date, cls]).fetchone()
        return {"actype": r[0], "wtc": r[1], "apt": r[2], "note": r[3], "verified": r[4], "ts": str(r[5])} if r else None

    def corrections(self, dates: list[str]) -> dict:
        if not dates:
            return {}
        out = {}
        for csn, date, cls, actype, wtc, apt, note, verified, ts in self.con.execute(
                "SELECT csn, date, cls, actype, wtc, apt, note, verified, ts FROM corrections WHERE date IN (SELECT unnest(?::VARCHAR[]))", [dates]).fetchall():
            out[(csn, date, cls)] = {"actype": actype, "wtc": wtc, "apt": apt, "note": note, "verified": verified, "ts": str(ts)}
        return out

    # ----------------------------------------------------------------- painel diário / qualidade de dados
    def daily_series(self, airport: str, d0: str, d1: str) -> list[dict]:
        """Uma linha por dia (yymmdd) entre d0 e d1 com os indicadores de todas as fontes."""
        q = """
        WITH days AS (SELECT DISTINCT date FROM (SELECT date FROM flights WHERE airport=? UNION ALL SELECT date FROM ground WHERE airport=? UNION ALL SELECT date FROM nmir WHERE adep=? OR ades=?) WHERE date BETWEEN ? AND ?),
        r AS (SELECT f.date, count(*) FILTER (cls='arr') arr, count(*) FILTER (cls='dep') dep, count(*) FILTER (cls='lvl') lvl, count(*) n,
                     any_value(b.blocks) blocks
              FROM flights f LEFT JOIN (SELECT date, count(DISTINCT block) blocks FROM files WHERE airport=? GROUP BY date) b USING(date)
              WHERE f.airport=? GROUP BY f.date),
        g AS (SELECT date, count(*) FILTER (mt='DEPARTURE') g_dep, count(*) FILTER (mt<>'DEPARTURE') g_arr, count(*) FILTER (ga) ga,
                     median(rwy_vac - aldt) FILTER (mt<>'DEPARTURE' AND rwy_vac>aldt AND rwy_vac-aldt<1800) rot_arr,
                     median(atot - rwy_ent) FILTER (mt='DEPARTURE' AND atot>rwy_ent AND atot-rwy_ent<1800) rot_dep,
                     median(atot - aobt) FILTER (mt='DEPARTURE' AND atot>aobt AND atot-aobt<7200) taxi_out,
                     median(aibt - rwy_vac) FILTER (mt<>'DEPARTURE' AND aibt>rwy_vac AND aibt-rwy_vac<7200) taxi_in,
                     sum(atfm_delay) atfm_min, count(*) FILTER (atfm_delay>0) atfm_n
              FROM ground WHERE airport=? GROUP BY date),
        n AS (SELECT date, count(*) FILTER (adep=?) n_dep, count(*) FILTER (ades=?) n_arr,
                     count(*) FILTER (adep=? AND atot IS NOT NULL AND etot IS NOT NULL) p_n,
                     count(*) FILTER (adep=? AND atot IS NOT NULL AND etot IS NOT NULL AND atot - coalesce(ctot, etot) <= 900) p_ok,
                     sum(atfm_delay) FILTER (adep=?) n_atfm
              FROM nmir WHERE adep=? OR ades=? GROUP BY date),
        o AS (SELECT strftime(to_timestamp(min(t)), '%y%m%d') date, count(DISTINCT flight_id) o_n FROM opdi_events WHERE airport=? GROUP BY flight_id)
        SELECT d.date, coalesce(r.arr,0) arr, coalesce(r.dep,0) dep, coalesce(r.lvl,0) lvl, coalesce(r.n,0) n, coalesce(r.blocks,0) blocks,
               coalesce(g.g_dep,0) g_dep, coalesce(g.g_arr,0) g_arr, coalesce(g.ga,0) ga, g.rot_arr, g.rot_dep, g.taxi_out, g.taxi_in, g.atfm_min, coalesce(g.atfm_n,0) atfm_n,
               coalesce(n.n_dep,0) n_dep, coalesce(n.n_arr,0) n_arr, coalesce(n.p_n,0) p_n, coalesce(n.p_ok,0) p_ok, n.n_atfm,
               (SELECT count(*) FROM o WHERE o.date = d.date) o_n
        FROM days d LEFT JOIN r USING(date) LEFT JOIN g USING(date) LEFT JOIN n USING(date) ORDER BY d.date"""
        a = airport
        cur = self.con.execute(q, [a, a, a, a, d0, d1, a, a, a, a, a, a, a, a, a, a, a])
        names = [c[0] for c in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]

    def nmir_departures(self, airport: str, dates: list[str]) -> list[dict]:
        if not dates:
            return []
        cur = self.con.execute("SELECT csn, date, actype, wtc, adep, ades, etot, ctot, atot, eta, ata, atfm_delay FROM nmir WHERE adep=? AND date IN (SELECT unnest(?::VARCHAR[]))", [airport, dates])
        names = [c[0] for c in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]

    def ground_reference(self, airport: str) -> list[dict]:
        """Toda a população da torre (para referências não-impedidas), só os campos necessários."""
        cur = self.con.execute("""SELECT mt, rwy, stand_d, stand_a, atot, aldt,
                                         CASE WHEN mt='DEPARTURE' THEN atot - aobt ELSE aibt - rwy_vac END taxi_s
                                  FROM ground WHERE airport=?""", [airport])
        names = [c[0] for c in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]

    def top_lists(self, airport: str, d0: str, d1: str) -> dict:
        ops = self.con.execute("""SELECT regexp_extract(csn, '^[A-Z]{3}') op, count(*) n FROM flights WHERE airport=? AND date BETWEEN ? AND ? AND cls IN ('arr','dep')
                                  AND regexp_matches(csn, '^[A-Z]{3}[0-9]') GROUP BY 1 ORDER BY 2 DESC LIMIT 10""", [airport, d0, d1]).fetchall()
        typ = self.con.execute("SELECT coalesce(actype,'?') t, count(*) n FROM flights WHERE airport=? AND date BETWEEN ? AND ? AND cls IN ('arr','dep') GROUP BY 1 ORDER BY 2 DESC LIMIT 10", [airport, d0, d1]).fetchall()
        apts = self.con.execute("""SELECT apt, count(*) n FROM (SELECT CASE WHEN adep=? THEN ades ELSE adep END apt FROM nmir WHERE (adep=? OR ades=?) AND date BETWEEN ? AND ?)
                                   WHERE apt IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 10""", [airport, airport, airport, d0, d1]).fetchall()
        return {"operators": [list(r) for r in ops], "types": [list(r) for r in typ], "airports": [list(r) for r in apts]}

    def ground_summary(self) -> dict:
        r = self.con.execute("SELECT count(*), min(date), max(date), count(DISTINCT date) FROM ground").fetchone()
        return {"rows": r[0], "from": r[1], "to": r[2], "days": r[3]}

    def ground_dates(self) -> list[str]:
        return [d for (d,) in self.con.execute("SELECT DISTINCT date FROM ground ORDER BY 1").fetchall()]

    def ground_list(self, airport: str, dates: list[str]) -> list[dict]:
        """Movimentos no solo das datas, com o movimento radar mais próximo no tempo (flight_id), quando existe."""
        if not dates:
            return []
        cols = ["gid", "date", "mt", "csn", "rwy", "actype", "reg", "ao", "wtc", "adep", "ades", "sid", "star", "stand_d", "stand_a",
                "taxi_out", "taxi_in", "hp", "ep", "aobt", "hp_time", "rwy_ent", "atot", "aldt", "rwy_vac", "aibt", "ctot", "spd_vac", "ga", "rto", "atfm_delay"]
        rows = self.con.execute(f"""
        WITH g AS (SELECT {', '.join(cols)}, CASE WHEN mt='DEPARTURE' THEN atot ELSE aldt END AS t_ref
                   FROM ground WHERE airport=? AND date IN (SELECT unnest(?::VARCHAR[]))),
        m AS (SELECT g.gid, f.flight_id, abs(f.t_first - g.t_ref) AS dt_dep, abs(f.t_last - g.t_ref) AS dt_arr,
                     row_number() OVER (PARTITION BY g.gid ORDER BY CASE WHEN g.mt='DEPARTURE' THEN abs(f.t_first - g.t_ref) ELSE abs(f.t_last - g.t_ref) END) rn
              FROM g JOIN flights f ON f.csn = g.csn AND f.date = g.date AND f.airport = ?
                                   AND f.cls = CASE WHEN g.mt='DEPARTURE' THEN 'dep' ELSE 'arr' END
              WHERE g.t_ref IS NOT NULL)
        SELECT g.*, m.flight_id FROM g LEFT JOIN m ON m.gid = g.gid AND m.rn = 1
        ORDER BY g.t_ref""", [airport, dates, airport]).fetchall()
        names = cols + ["t_ref", "flight_id"]
        out = []
        for r in rows:
            d = dict(zip(names, r))
            d["taxi_s"] = (d["atot"] - d["aobt"]) if d["mt"] == "DEPARTURE" and d["atot"] and d["aobt"] else \
                          (d["aibt"] - d["rwy_vac"]) if d["mt"] != "DEPARTURE" and d["aibt"] and d["rwy_vac"] else None
            d["rot_s"] = (d["atot"] - d["rwy_ent"]) if d["mt"] == "DEPARTURE" and d["atot"] and d["rwy_ent"] else \
                         (d["rwy_vac"] - d["aldt"]) if d["mt"] != "DEPARTURE" and d["rwy_vac"] and d["aldt"] else None
            out.append(d)
        return out

    def ground_get(self, gids: list[int]) -> list[dict]:
        if not gids:
            return []
        cur = self.con.execute("SELECT * EXCLUDE (raw) FROM ground WHERE gid IN (SELECT unnest(?::INTEGER[]))", [gids])
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]

    def ground_raw(self, gid: int) -> dict | None:
        r = self.con.execute("SELECT raw FROM ground WHERE gid=?", [gid]).fetchone()
        return json.loads(r[0]) if r and r[0] else None

    def airport_nmir(self, airport: str, dates: list[str]) -> dict:
        """'Só ARR/DEP': devolve os flight_id a EXCLUIR — movimentos cuja origem E destino são conhecidos
        (NMIR ou OPDI) e nenhum deles é o aeroporto. Voos sem informação ficam (não se retira o que não se sabe).
        n_info = registos NMIR/OPDI com ADEP/ADES conhecidos nessas datas (0 → não há com que filtrar)."""
        if not dates:
            return {"exclude": [], "n_info": 0}
        from .geo import AIRPORTS
        ctr = AIRPORTS.get(airport, {}).get("center", (38.7813, -9.1359))
        n = self.con.execute("""SELECT count(*) FROM nmir WHERE date IN (SELECT unnest(?::VARCHAR[])) AND adep IS NOT NULL AND ades IS NOT NULL""", [dates]).fetchone()[0]
        n += self.con.execute("""SELECT count(DISTINCT flight_id) FROM opdi_events WHERE airport=? AND adep IS NOT NULL AND ades IS NOT NULL
                                 AND strftime(to_timestamp(t), '%y%m%d') IN (SELECT unnest(?::VARCHAR[]))""", [airport, dates]).fetchone()[0]
        exclude = [r[0] for r in self.con.execute("""
            WITH other AS (
                SELECT csn, date FROM nmir WHERE date IN (SELECT unnest(?::VARCHAR[])) AND adep IS NOT NULL AND ades IS NOT NULL AND adep <> ? AND ades <> ?
                UNION
                SELECT csn, strftime(to_timestamp(min(t)), '%y%m%d') date FROM opdi_events
                WHERE airport=? AND adep IS NOT NULL AND ades IS NOT NULL AND adep <> ? AND ades <> ?
                      AND coalesce(adep_p,'') <> ? AND coalesce(ades_p,'') <> ?
                GROUP BY flight_id, csn),
            at_apt AS (   -- qualquer fonte que diga que é do aeroporto prevalece
                SELECT csn, date FROM nmir WHERE date IN (SELECT unnest(?::VARCHAR[])) AND (adep = ? OR ades = ?)
                UNION SELECT csn, date FROM ground WHERE airport = ? AND date IN (SELECT unnest(?::VARCHAR[]))
                UNION SELECT csn, strftime(to_timestamp(min(t)), '%y%m%d') FROM opdi_events WHERE airport=? AND (adep = ? OR ades = ?) GROUP BY flight_id, csn),
            sel AS (SELECT flight_id, airport, date, csn, t_first, t_last, cls, alt_first, alt_last, alt_min FROM flights
                    WHERE airport = ? AND date IN (SELECT unnest(?::VARCHAR[]))),
            geo AS (   -- o próprio radar: chegada que termina baixa e longe do aeroporto / partida que começa baixa e longe = não é deste aeroporto
                SELECT s.flight_id,
                       2*3440.065*asin(sqrt(pow(sin(radians(arg_min(p.lat,p.tod_sec)-{lat})/2),2)+cos(radians(arg_min(p.lat,p.tod_sec)))*cos(radians({lat}))*pow(sin(radians(arg_min(p.lon,p.tod_sec)-({lon}))/2),2))) d_first,
                       2*3440.065*asin(sqrt(pow(sin(radians(arg_max(p.lat,p.tod_sec)-{lat})/2),2)+cos(radians(arg_max(p.lat,p.tod_sec)))*cos(radians({lat}))*pow(sin(radians(arg_max(p.lon,p.tod_sec)-({lon}))/2),2))) d_last,
                       min(2*3440.065*asin(sqrt(pow(sin(radians(p.lat-{lat})/2),2)+cos(radians(p.lat))*cos(radians({lat}))*pow(sin(radians(p.lon-({lon}))/2),2)))) d_min,
                       any_value(s.cls) cls, any_value(s.alt_first) alt_first, any_value(s.alt_last) alt_last, any_value(s.alt_min) alt_min
                FROM sel s JOIN points p ON p.airport=s.airport AND p.date=s.date AND p.csn=s.csn AND p.tod_sec BETWEEN s.t_first AND s.t_last
                GROUP BY s.flight_id),
            geo_other AS (SELECT flight_id FROM geo WHERE (cls='arr' AND d_last > {rad} AND coalesce(alt_last, 0) < 3000) OR (cls='dep' AND d_first > {rad} AND coalesce(alt_first, 0) < 3000)
                              -- sobrevoo: nunca aterrou nem descolou aqui, excepto se desceu até perto da pista (circuitos / toque-e-arranque)
                              OR (cls='lvl' AND NOT (d_min <= 2 AND coalesce(alt_min, 9999) < 1500)))
            SELECT DISTINCT f.flight_id FROM sel f
            LEFT JOIN other o ON o.csn = f.csn AND o.date = f.date
            LEFT JOIN geo_other g ON g.flight_id = f.flight_id
            LEFT JOIN at_apt a ON a.csn = f.csn AND a.date = f.date
            WHERE (o.csn IS NOT NULL OR g.flight_id IS NOT NULL) AND a.csn IS NULL""".format(lat=ctr[0], lon=ctr[1], rad=4.0),
            [dates, airport, airport, airport, airport, airport, airport, airport, dates, airport, airport, airport, dates, airport, airport, airport, airport, dates]).fetchall()]
        return {"exclude": exclude, "n_info": int(n) + 1}   # +1: o radar conta sempre como fonte

    def close(self):
        self.con.close()
