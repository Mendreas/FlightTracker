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

import os
import sys
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


class Database:
    def __init__(self, db_path: str | os.PathLike):
        self.path = str(db_path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(self.path)
        self.con.execute("PRAGMA threads=%d" % max(2, (os.cpu_count() or 4)))
        self._init_schema()

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
            csn VARCHAR, date VARCHAR, actype VARCHAR, wtc VARCHAR)""")
        c.execute("CREATE TABLE IF NOT EXISTS meta(key VARCHAR PRIMARY KEY, value VARCHAR)")
        c.execute("CREATE TABLE IF NOT EXISTS analysis_cache(key VARCHAR PRIMARY KEY, flight_id INTEGER, value VARCHAR, created TIMESTAMP DEFAULT current_timestamp)")
        c.execute("CREATE TABLE IF NOT EXISTS user_points(name VARCHAR PRIMARY KEY, lat DOUBLE, lon DOUBLE, descr VARCHAR)")
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
                c.execute("INSERT INTO nmir SELECT csn, date, actype, wtc FROM read_csv(?, header=true, all_varchar=true)",
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
                if fn.lower().endswith(".csv") and not fn.startswith((".", "~")):
                    out.append(os.path.join(root, fn))
        out.sort()
        return out

    def _known_files(self) -> dict[str, tuple[int, float]]:
        return {p: (s, m) for p, s, m in self.con.execute("SELECT path, size, mtime FROM files").fetchall()}

    def pending_files(self, folder: str) -> tuple[list[str], int]:
        """Devolve (ficheiros novos/alterados, total encontrado)."""
        known = self._known_files()
        todo = []
        allf = self.scan_folder(folder)
        for p in allf:
            st = os.stat(p)
            k = known.get(p)
            if k is None or k[0] != st.st_size or abs(k[1] - st.st_mtime) > 1:
                todo.append(p)
        return todo, len(allf)

    @staticmethod
    def _read_header(path: str):
        """Lê só a 1ª linha: devolve (colunas_minúsculas, encoding)."""
        raw = open(path, "rb").readline()
        enc = "utf-8"
        try:
            line = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            line, enc = raw.decode("latin-1"), "latin-1"
        line = line.rstrip("\r\n")
        sep = ";" if line.count(";") >= line.count(",") else ","
        cols, seen = [], set()
        for c in line.split(sep):
            c = c.strip().strip('"').lower() or "col"
            base, k = c, 1
            while c in seen:            # cabeçalhos repetidos -> col, col_2, ...
                k += 1; c = f"{base}_{k}"
            seen.add(c); cols.append(c)
        return cols, enc, sep

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
                cols, enc, sep = self._read_header(p)
                groups.setdefault((tuple(cols), enc, sep), []).append(p)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{os.path.basename(p)}: {e}")
        c = self.con
        total_rows = 0
        for (cols, enc, sep), plist in groups.items():
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
                        FROM read_csv(?, delim=?, header=true, columns=?, auto_detect=false, ignore_errors=true,
                                      null_padding=true, filename=true, encoding=?) r
                        JOIN pending t ON t.path = r.filename
                    ) WHERE {where}""", [plist, sep, coltypes, enc])
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
        with guard():
            todo, total_found = self.pending_files(folder)
        self._log(f"== importar {folder}: {len(todo)} novos de {total_found} (scan {time.time()-t0:.1f}s)")
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
        if todo:
            if progress:
                progress(done, len(todo), "a construir tabela de movimentos…")
            t_r = time.time()
            with guard():
                self.rebuild_flights()
            self._log(f"rebuild_flights {time.time()-t_r:.1f}s")
        with guard():
            self.con.execute("INSERT OR REPLACE INTO meta VALUES ('last_folder', ?)", [folder])
        self._log(f"== fim: {rows} linhas, {len(err_list)} erros, total {time.time()-t0:.1f}s")
        return {"found": total_found, "new": len(todo), "imported": len(todo) - len(err_list), "errors": len(err_list),
                "rows": rows, "ms": int((time.time() - t0) * 1000), "error_list": err_list[:20]}

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
            self.con.execute(
                "INSERT OR REPLACE INTO analysis_cache(key, flight_id, value) "
                "SELECT * FROM (SELECT unnest(?::VARCHAR[]) k, unnest(?::INTEGER[]) f, unnest(?::VARCHAR[]) v)", [keys, fids, vals])

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

    def import_nmir_xlsx(self, path: str) -> int:
        """Importa um Excel NMIR (EUROCONTROL) com openpyxl: precisa de colunas com callsign e tipo
        (data e WTC opcionais). Devolve o nº de registos novos."""
        from openpyxl import load_workbook
        from datetime import date, datetime
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
            i_date = find("date", "data", "dof")
            i_wtc = find("wtc", "wake")
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
                        s2 = "".join(ch for ch in str(v) if ch.isdigit())
                        if len(s2) == 8:      # yyyymmdd
                            d = s2[2:]
                        elif len(s2) == 6:
                            d = s2
                wtc = row[i_wtc] if i_wtc is not None and i_wtc < len(row) else None
                rows_out.append((str(csn).strip().upper(), d, str(typ).strip().upper(),
                                 str(wtc).strip().upper() if wtc else None))
        if not rows_out:
            raise RuntimeError("Excel sem colunas reconhecidas (callsign / aircraft type).")
        before = self.con.execute("SELECT count(*) FROM nmir").fetchone()[0]
        self.con.executemany("INSERT INTO nmir VALUES (?,?,?,?)", rows_out)
        self.con.execute("CREATE OR REPLACE TABLE nmir AS SELECT DISTINCT * FROM nmir")
        self.rebuild_flights()
        return self.con.execute("SELECT count(*) FROM nmir").fetchone()[0] - before

    def close(self):
        self.con.close()
