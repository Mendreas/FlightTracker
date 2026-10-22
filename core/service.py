"""Orquestração das análises para a sessão (estado do filtro actual e resultados em memória)."""
from __future__ import annotations

import csv
import json
import os
import tempfile
import time
import webbrowser

from . import ia, reports
from .analysis import fast as fastmod, final as finalmod, ops, speeds
from .db import Database
from .filenames import date_label
from .geo import AIRPORTS, LPPT_STAR_IAS_DEFAULTS, dist_nm, fmt_date


class Service:
    def __init__(self, db: Database):
        self.db = db
        self.airport = "LPPT"; self.dates: list[str] = []; self.blocks: list[str] = []; self.csn = ""; self.cls = ""
        self.flights: list[dict] = []
        self.all_flights: list[dict] = []
        self.reset_results()
        self.ia_history: list[dict] = []

    def reset_results(self):
        self.final = None; self.final_params = None; self.pairs = None; self.deps = None; self.movs = None
        self.star = None; self.app = None; self.app_dist = None; self.rrms = None; self.rot = None
        self.point_rows = None; self.point_name = None; self.seq = None
        self.ground = None; self.cross = None; self.pru = None

    # ------------------------------------------------------------- filtro
    def set_filter(self, dates, blocks, csn="", cls="", airport=None):
        """Carrega os movimentos de TODOS os aeroportos para os dias/blocos; o aeroporto activo só filtra a vista."""
        self.dates, self.blocks, self.csn, self.cls = list(dates), list(blocks), csn or "", cls or ""
        self.all_flights = self.db.flights_list(None, dates, blocks, csn, cls)
        airports = sorted({f["airport"] for f in self.all_flights})
        if airport:
            self.airport = airport
        elif self.airport not in airports and airports:
            self.airport = "LPPT" if "LPPT" in airports else airports[0]
        self.flights = [f for f in self.all_flights if f["airport"] == self.airport]
        self.airport_only_ids = None
        self.reset_results()
        return {"flights": self.all_flights, "airport": self.airport, "airports": airports}

    def set_airport(self, airport: str):
        self.airport = airport
        self.airport_only_ids = None
        self.flights = [f for f in self.all_flights if f["airport"] == airport]
        self.reset_results()
        return len(self.flights)

    def set_airport_only(self, on: bool) -> dict:
        """Retira da vista os voos que, segundo o NMIR/OPDI, têm origem e destino conhecidos e nenhum é o aeroporto activo.
        Voos sem informação mantêm-se."""
        base = [f for f in self.all_flights if f["airport"] == self.airport]
        if not on:
            self.airport_only_ids = None
            self.flights = base
            self.reset_results()
            return {"on": False, "n": len(self.flights), "n_nmir": None}
        r = self.db.airport_nmir(self.airport, self.dates)
        excl = set(r["exclude"])
        self.airport_only_ids = excl
        self.flights = [f for f in base if f["flight_id"] not in excl]
        self.reset_results()
        return {"on": True, "n": len(self.flights), "n_nmir": r["n_info"], "excluded": len(excl), "ids": sorted(excl)}

    def _by_id(self, fid: int) -> dict | None:
        return next((f for f in self.flights if f["flight_id"] == fid), None)

    # ------------------------------------------------------------- Final / FAST
    def run_final(self, rwy="BOTH", faf=7.0, corr=2.0, alt=1000.0):
        params = (rwy, float(faf), float(corr), float(alt))
        if self.final is None or self.final_params != params:
            self.final = finalmod.run_final(self.db, self.flights, self.airport, rwy, *params[1:])
            self.final_params = params
            self.deps = fastmod.dep_events(self.flights)
            self.pairs = fastmod.build_pairs(self.final, self.deps)
            self.movs = fastmod.movements(self.final, self.deps)
        return {"results": self.final, "summary": finalmod.final_summary(self.final), "params": params,
                "rwys": list(AIRPORTS.get(self.airport, AIRPORTS["LPPT"])["rwys"])}

    def ensure_final(self):
        if self.final is None:
            self.run_final()

    def fast(self, thr=160, mode="all", intercal=False, rwy="all"):
        self.ensure_final()
        rows = fastmod.fast_view(self.pairs, int(thr), mode, bool(intercal), rwy)
        return {"rows": rows, "total": len(self.pairs), "thr": int(thr)}

    def data_analysis(self, **f):
        self.ensure_final()
        files = self.db.con.execute("SELECT count(*) FROM files WHERE airport=? AND date IN (SELECT unnest(?::VARCHAR[]))",
                                    [self.airport, self.dates or ["__"]]).fetchone()[0]
        return fastmod.data_analysis(self.pairs, self.movs, len(self.pairs), len(self.final), files, **f)

    def daily(self, limit=165):
        self.ensure_final()
        return fastmod.daily_analysis(self.pairs, self.movs, self.dates, self.blocks, int(limit))

    # ------------------------------------------------------------- velocidades
    def star_limits(self) -> dict:
        raw = self.db.setting_get("ias_limits")
        return json.loads(raw) if raw else dict(LPPT_STAR_IAS_DEFAULTS)

    def star_limits_set(self, limits: dict):
        clean = {str(k).upper().strip(): int(v) for k, v in limits.items() if str(k).strip() and 80 <= int(v) <= 400}
        self.db.setting_set("ias_limits", json.dumps(clean)); self.star = None
        return clean

    def run_star(self, radius=1.0, tol=0.0):
        self.star = speeds.run_star(self.db, self.flights, self.star_limits(), float(radius), float(tol))
        return self.star

    def run_app(self, radius=1.0, tol=0.0):
        self.app = speeds.run_app(self.db, self.flights, self.airport, float(radius), float(tol))
        return self.app

    def run_app_dist(self, rwy="02", buffer=4, sel=None):
        self.app_dist = speeds.run_app_dist(self.db, self.flights, self.airport, str(rwy), int(buffer), sel)
        return self.app_dist

    # ------------------------------------------------------------- KPIs / RRMS / ROT
    def kpis(self):
        self.ensure_final()
        return ops.kpis(self.flights, self.final, self.star)

    def run_rrms(self):
        self.rrms = ops.run_rrms(self.db, self.flights)
        return self.rrms

    def run_rot(self):
        ground = self.db.ground_list(self.airport, self.dates) if self.dates else []
        self.rot = ops.run_rot(self.db, self.flights, self.airport, ground)
        return self.rot

    # ------------------------------------------------------------- pontos
    def points(self):
        return ops.all_points_for(self.db, self.airport)

    def _point(self, name: str) -> dict:
        p = next((p for p in self.points() if p["name"].upper() == name.upper()), None)
        if not p:
            raise ValueError(f"Ponto {name} não encontrado")
        return p

    def point_query(self, name, radius=1.0, op="any", v1=None, v2=None, tol=2.0):
        rows = ops.point_query(self.db, self.flights, self._point(name), float(radius))
        self.point_rows, self.point_name = rows, name
        v1 = float(v1) if v1 not in (None, "") else None; v2 = float(v2) if v2 not in (None, "") else None
        return {"rows": ops.ias_filter(rows, op, v1, v2, float(tol)), "total": len(rows)}

    def sequence(self, name, radius=1.0):
        self.seq = ops.sequence_query(self.db, self.flights, self._point(name), float(radius))
        return self.seq

    # ------------------------------------------------------------- detalhe de voo
    def flight_detail(self, fid: int) -> dict:
        f = self._by_id(fid)
        if f is None:
            cur = self.db.con.execute("SELECT * FROM flights WHERE flight_id=?", [fid])
            row = cur.fetchone()
            if row is None:
                raise ValueError("Movimento não encontrado")
            f = dict(zip([d[0] for d in cur.description], row))
        pts = self.db.flight_points(fid)
        cfg = AIRPORTS.get(f["airport"], AIRPORTS["LPPT"])
        # pista provável = THR mais próxima do último (ARR) ou primeiro (DEP) plot
        # chegada: o primeiro plot abaixo de 500 ft AGL (ainda antes da soleira); partida: o primeiro plot. O último plot de uma
        # chegada já está no fim da pista, perto da soleira oposta — dava a pista errada.
        elev = min(r["elev"] for r in cfg["rwys"].values())
        if f["cls"] == "dep":
            ref = pts[0] if pts else None
        else:
            ref = next((p for p in pts if p.get("alt") is not None and p["alt"] < elev + 500), pts[-1] if pts else None)
        rwy = min(cfg["rwys"], key=lambda r: dist_nm(ref["lat"], ref["lon"], *cfg["rwys"][r]["thr"])) if ref else None
        sources = self.db.flight_sources(f)
        if sources.get("tower") and sources["tower"].get("rwy") in cfg["rwys"]:
            rwy = sources["tower"]["rwy"]
        if rwy:
            thr = cfg["rwys"][rwy]["thr"]
            for p in pts:
                p["dist_thr"] = dist_nm(p["lat"], p["lon"], *thr)
        app_rec = next((r for r in (self.app or {}).get("records", []) if r["flight_id"] == fid), None)
        star_v = [v for v in (self.star or {}).get("violations", []) if v["flight_id"] == fid]
        fin = [r for r in (self.final or []) if r["flight_id"] == fid]
        return {"flight": {**f, "date_fmt": fmt_date(f["date"]), "rwy_guess": rwy}, "points": pts, "app": app_rec, "star": star_v, "final": fin,
                "tol": (self.app or {}).get("tol", 0), "sources": sources}

    # ------------------------------------------------------------- exportações
    def export_excel(self, path: str, kind: str, extra: dict | None = None):
        extra = extra or {}
        sheets = []
        if kind == "panel":
            d0, d1 = extra.get("d0"), extra.get("d1")
            rows = self.db.daily_series(self.airport, d0, d1)
            sheets.append(("Painel diário", ["DIA", "RADAR mov.", "RADAR ARR", "RADAR DEP", "RADAR blocos", "TORRE ARR", "TORRE DEP", "GO-AROUNDS", "ROT ARR (s)", "ROT DEP (s)", "TAXI-OUT (s)", "TAXI-IN (s)", "ATFM (min)", "ATFM voos", "NMIR DEP", "NMIR ARR", "PONT. n", "PONT. ok", "OPDI voos"],
                           [[fmt_date(r["date"]), r["n"], r["arr"], r["dep"], r["blocks"], r["g_arr"], r["g_dep"], r["ga"], r["rot_arr"] or "", r["rot_dep"] or "", r["taxi_out"] or "", r["taxi_in"] or "", r["atfm_min"] or "", r["atfm_n"], r["n_dep"], r["n_arr"], r["p_n"], r["p_ok"], r["o_n"]] for r in rows]))
            top = self.db.top_lists(self.airport, d0, d1)
            sheets.append(("Top 10", ["GRUPO", "CHAVE", "MOVIMENTOS"], [["Operador", k, n] for k, n in top["operators"]] + [["Tipo", k, n] for k, n in top["types"]] + [["Aeroporto", k, n] for k, n in top["airports"]]))
            return reports.write_excel(path, sheets)
        if kind == "pru":
            d = self.pru or self.pru_kpis()
            rows = []
            def add(sec, k, v, note=""):
                rows.append([sec, k, "" if v is None else (round(v, 2) if isinstance(v, float) else v), note])
            t = d.get("throughput") or {}
            for k in ("source", "n", "days", "per_day", "peak_hour_mov", "peak_roll60", "capacity", "util_peak", "hours_over_capacity", "ga", "ga_rate"):
                add("Throughput", k, t.get(k))
            x = d.get("taxi") or {}
            for kind2 in ("taxi_out", "taxi_in"):
                for k in ("n", "mean", "median", "p80", "max", "mean_min"):
                    add(kind2, k, (x.get(kind2) or {}).get(k), "segundos (mean_min em minutos)")
            a = d.get("asma") or {}
            for k in ("n", "ring_nm", "mean", "median", "p80", "max", "mean_min"):
                add("ASMA", k, a.get(k))
            f = d.get("atfm") or {}
            for k in ("n", "ok", "pct", "early", "n_fsa", "dev_mean", "dev_median", "dev_p80"):
                add("Pontualidade (NMIR, FSA/DEP)", k, (f.get("otp") or {}).get(k))
            for k in ("n", "within", "pct"):
                add("Conformidade slot ATFM", k, (f.get("slot") or {}).get(k))
            for src in ("atfm_nmir", "atfm_torre"):
                for k, v in (f.get(src) or {}).items():
                    if not isinstance(v, (list, dict)):
                        add(src, k, v)
            c = d.get("cdo") or {}
            for k in ("n", "cdo", "pct", "levels_mean"):
                add("CDO (OPDI)", k, c.get(k))
            sheets.append(("KPIs PRU", ["SECÇÃO", "INDICADOR", "VALOR", "NOTA"], rows))
            if x:
                sheets.append(("Taxi por stand", ["TIPO", "STAND", "N", "ADICIONAL MÉDIO (s)"], [[k, r["key"], r["n"], round(r["mean"])] for k in ("taxi_out", "taxi_in") for r in (x.get(k) or {}).get("by_stand", [])]))
            if a.get("worst"):
                sheets.append(("ASMA voos", ["DATA", "VOO", "RWY", "TRÂNSITO (s)", "ADICIONAL (s)"], [[fmt_date(r["date"]), r["csn"], r["rwy"], round(r["t"]), round(r["add"])] for r in a["worst"]]))
            return reports.write_excel(path, sheets)
        if kind == "cross":
            res = self.cross or self.crosscheck()
            hm = lambda t: time.strftime("%H:%M:%S", time.gmtime(t)) if t else ""
            cols = ["DATA", "VOO", "MOV", "FONTES", "DISCREPÂNCIAS",
                    "RADAR 1º plot", "RADAR último plot", "RADAR nº plots", "RADAR alt máx",
                    "NMIR tipo", "NMIR WTC", "NMIR ADEP", "NMIR ADES", "NMIR origem",
                    "TORRE tipo", "TORRE WTC", "TORRE matrícula", "TORRE operador", "TORRE RWY", "TORRE stand", "TORRE ADEP/ADES", "TORRE AOBT", "TORRE RWY_ENT", "TORRE ATOT", "TORRE ALDT", "TORRE RWY_VAC", "TORRE AIBT", "TORRE ROT (s)", "TORRE taxi (s)", "TORRE GA",
                    "OPDI id", "OPDI icao24", "OPDI matrícula", "OPDI tipo", "OPDI modelo", "OPDI ADEP", "OPDI ADES", "OPDI entrada pista", "OPDI saída pista", "OPDI ROT (s)", "OPDI TOC", "OPDI TOD", "OPDI último FL100", "OPDI último FL50", "OPDI 1º FL50", "OPDI 1º FL100", "OPDI patamares <FL100",
                    "Δt radar−torre (s)", "Δt OPDI−torre (s)", "ΔROT OPDI−torre (s)", "CORREÇÃO tipo", "CORREÇÃO WTC", "CORREÇÃO ADEP/ADES", "CORREÇÃO nota", "VERIFICADO"]
            data = [[fmt_date(r["date"]), r["csn"], r["cls"].upper(), r["src"], "; ".join(r["flags"]),
                     hm(r["r_t_first"]), hm(r["r_t_last"]), r["r_n"] or "", r["r_alt_max"] or "",
                     r["n_type"] or "", r["n_wtc"] or "", r["n_adep"] or "", r["n_ades"] or "", r["n_src"] or "",
                     r["t_type"] or "", r["t_wtc"] or "", r["t_reg"] or "", r["t_ao"] or "", r["t_rwy"] or "", r["t_stand"] or "", r["t_apt"] or "",
                     hm(r["t_aobt"]), hm(r["t_rwy_ent"]), hm(r["t_atot"]), hm(r["t_aldt"]), hm(r["t_rwy_vac"]), hm(r["t_aibt"]),
                     round(r["t_rot"]) if r["t_rot"] else "", round(r["t_taxi"]) if r["t_taxi"] else "", "GA" if r["t_ga"] else "",
                     r["o_id"] or "", r["o_icao24"] or "", r["o_reg"] or "", r["o_type"] or "", r["o_model"] or "", r["o_adep"] or "", r["o_ades"] or "",
                     hm(r["o_rwy_in"]), hm(r["o_rwy_out"]), round(r["o_rot"]) if r["o_rot"] else "", hm(r["o_toc"]), hm(r["o_tod"]), hm(r["o_lx100"]), hm(r["o_lx50"]), hm(r["o_fx50"]), hm(r["o_fx100"]), r["o_levels_low"] if r["o_levels_low"] is not None else "",
                     r["dt_radar_torre"] if r["dt_radar_torre"] is not None else "", r["dt_opdi_torre"] if r["dt_opdi_torre"] is not None else "", r["d_rot"] if r["d_rot"] is not None else "",
                     (r.get("corr") or {}).get("actype") or "", (r.get("corr") or {}).get("wtc") or "", (r.get("corr") or {}).get("apt") or "", (r.get("corr") or {}).get("note") or "", "sim" if (r.get("corr") or {}).get("verified") else ""] for r in res["rows"]]
            sheets.append(("Cruzamento", cols, data))
            sheets.append(("Discrepâncias", cols, [d for d, r in zip(data, res["rows"]) if r["n_flags"]]))
            c = res["coverage"]
            sheets.append(("Cobertura", ["INDICADOR", "VALOR"], [[k, v if v is not None else ""] for k, v in c.items()]))
            return reports.write_excel(path, sheets)
        if kind == "ground":
            rows = self.ground or self.db.ground_list(self.airport, self.dates)
            hm = lambda t: time.strftime("%H:%M:%S", time.gmtime(t)) if t else ""
            sheets.append(("Movimentos solo", ["DATA", "MOV", "VOO", "TIPO", "WTC", "RWY", "STAND", "TAXI", "HP/EP", "AOBT/AIBT", "RWY_ENT/ALDT", "ATOT/RWY_VAC", "TAXI (s)", "ROT (s)", "ADEP/ADES", "GA"],
                           [[fmt_date(r["date"]), "DEP" if r["mt"] == "DEPARTURE" else "ARR", r["csn"], r.get("actype") or "", r.get("wtc") or "", r.get("rwy") or "",
                             (r.get("stand_d") if r["mt"] == "DEPARTURE" else r.get("stand_a")) or "", (r.get("taxi_out") if r["mt"] == "DEPARTURE" else r.get("taxi_in")) or "",
                             (r.get("hp") if r["mt"] == "DEPARTURE" else r.get("ep")) or "",
                             hm(r["aobt"] if r["mt"] == "DEPARTURE" else r["aibt"]), hm(r["rwy_ent"] if r["mt"] == "DEPARTURE" else r["aldt"]), hm(r["atot"] if r["mt"] == "DEPARTURE" else r["rwy_vac"]),
                             round(r["taxi_s"]) if r.get("taxi_s") else "", round(r["rot_s"]) if r.get("rot_s") else "",
                             (r.get("ades") if r["mt"] == "DEPARTURE" else r.get("adep")) or "", "GA" if r.get("ga") else ""] for r in rows]))
            from . import ground as gmod
            st = gmod.ground_stats(rows) if rows else None
            if st:
                def sec(name, lst):
                    return [[name, x["key"], x["n"], round(x.get("median") or 0), round(x.get("mean") or 0), round(x.get("p10") or 0), round(x.get("p90") or 0), round(x.get("max") or 0)] for x in lst if x["n"]]
                sheets.append(("ROT e taxi", ["GRUPO", "CHAVE", "N", "MEDIANA (s)", "MÉDIA (s)", "P10", "P90", "MÁX"],
                               sec("ROT ARR por saída", st["rot_arr_by_ep"]) + sec("ROT ARR por WTC", st["rot_arr_by_wtc"]) + sec("ROT ARR por RWY", st["rot_arr_by_rwy"]) +
                               sec("ROT DEP por HP", st["rot_dep_by_hp"]) + sec("ROT DEP por WTC", st["rot_dep_by_wtc"]) + sec("ROT DEP por RWY", st["rot_dep_by_rwy"]) +
                               sec("Taxi-in por stand", st["taxi_in_by_stand"]) + sec("Taxi-out por stand", st["taxi_out_by_stand"])))
            return reports.write_excel(path, sheets)
        if kind == "operacional":
            self.ensure_final()
            geral = []
            for f in self.flights:
                for p in self.db.flight_points(f["flight_id"]):
                    geral.append([p["tod"][:12], fmt_date(f["date"]), f["csn"], f["cls"].upper(), p["alt"], p["ias"], round(p["lat"], 6), round(p["lon"], 6)])
            sheets.append(("Geral", ["HORA", "DATA", "VOO", "TIPO", "ALTITUDE", "IAS", "LATITUDE", "LONGITUDE"], geral))
            bl = []
            for r in (self.app or {}).get("records", []):
                row = [r["tod"], r["date"], r["csn"], int(r["rwy"])]
                for p in (r["points"] + [None] * 4)[:4]:
                    row += [p["point"], round(p["ias"]) if p["ias"] is not None else "", round(p["limit"]), f"{p['deviation']:+.0f}" if p["deviation"] is not None else ""] if p else ["", "", "", ""]
                bl.append(row)
            hb = ["HORA", "DATA", "VOO", "PISTA"] + [c for i in range(1, 5) for c in (f"PONTO{i}", f"IAS{i}", f"LIMITE{i}", f"DESVIO{i}")]
            sheets.append(("BLACK-LIST", hb, bl))
            rows = fastmod.fast_view(self.pairs, int(extra.get("thr", 160)), extra.get("mode", "all"), bool(extra.get("intercal")), extra.get("rwy", "all"))
            sheets.append(("FAST", ["HORA", "DATA", "RWY", "LIDER (THR)", "IAS LIDER", "SEGUIDOR", "IAS SEG.", "SEP (s)", "A/C INTERCALAR", "CALL_SIGN", "HORA DEP"],
                           [[r["leadTod"], r["date"], int(r["rwy"]), r["lead"], round(r["leadIas"]) if r["leadIas"] else "", r["trail"],
                             round(r["trailIas"]) if r["trailIas"] else "", round(r["sep"]), "Sim" if r["depCnt"] else "Nao", r["firstDep"] or "", r["firstDepTod"] or ""] for r in rows]))
        elif kind == "final":
            self.ensure_final()
            sheets.append(("Final", ["Seq", "RWY", "Voo", "Tipo", "Data", "Hora_FAF", "Hora_THR", "Dur_FAF_THR_s", "Dist_FAF_THR_NM", "Sep_temporal_anterior_s",
                                     "Alt_FAF_ft", "IAS_FAF_kt", "IAS_4NM_kt", "IAS_THR_kt", "Desvio_eixo_NM", "Estabilizada"],
                           [[r["idx"], int(r["rwy"]), r["csn"], r["actype"], r["date"], r["tFAFstr"], r["tTHRstr"], round(r["durS"]), round(r["trackNM"], 2),
                             round(r["sepTimeS"]) if r["sepTimeS"] is not None else "", round(r["altFAF"]), round(r["iasFAF"]) if r["iasFAF"] is not None else "",
                             round(r["ias4"]) if r["ias4"] is not None else "", round(r["iasTHR"]) if r["iasTHR"] is not None else "", round(r["crossFAF"], 2),
                             "Sim" if r["stab"] else "Nao"] for r in self.final]))
        elif kind == "dados":
            da = self.data_analysis(**extra)
            sheets.append(("Pares filtrados", ["Pista", "Data", "Hora A", "Callsign precedente", "IAS precedente", "Callsign seguidor", "IAS seguidor", "Sep. s", "Sep. NM", "Seq.", "DEP", "Hora DEP", "Seguidor à THR no DEP (s)", "Seguidor à THR no DEP (NM)"],
                           [[r["rwy"], r["date"], r["leadTod"], r["lead"], round(r["leadIas"]) if r["leadIas"] else None, r["trail"], round(r["trailIas"]) if r["trailIas"] else None,
                             round(r["sep"]), r["sepNm"], r["seq"], r["firstDep"], r["firstDepTod"], r["bSecAtDep"], r["bNmAtDep"]] for r in da["rows"]]))
            sheets.append(("Top 10 críticos", ["Pista", "Data", "Hora A", "Precedente", "Seguidor", "Seq.", "Sep. s", "Sep. NM", "DEP"],
                           [[r["rwy"], r["date"], r["leadTod"], r["lead"], r["trail"], r["seq"], round(r["sep"]), r["sepNm"], r["firstDep"]] for r in da["tables"]["top10"]]))
            sheets.append(("Movimentos ARR+DEP", ["Tipo", "Pista", "Data", "Hora", "Callsign", "Companhia"],
                           [[m["type"], m["rwy"], fmt_date(m["date"]), m["tod"], m["csn"], fastmod.company(m["csn"])] for m in self.movs]))
            sheets.append(("Resumo por companhia", ["Companhia", "Movimentos", "ARR", "DEP", "Ocorrências críticas", "Taxa"],
                           [[c["company"], c["movements"], c["arr"], c["dep"], c["critical"], round(c["rate"] * 100, 1)] for c in da["tables"]["companies"]]))
        elif kind == "diaria":
            dy = self.daily(int(extra.get("limit", 165)))
            k = dy["kpis"]
            sheets.append(("Indicadores", ["Indicador", "Valor"], [["Dias", k["days"]], ["Movimentos", k["movs"]], ["Aterragens", k["arr"]], ["Descolagens", k["dep"]], ["Pares", k["pairs"]],
                                                                  ["Abaixo do limite", k["crit"]], ["Críticos com DEP", k["critDep"]], ["Callsigns comuns", k["common"]]]))
            sheets.append(("Resumo por dia", ["Data", "Dia sem.", "ARR", "DEP", "Movimentos", "Pares", "Críticos"], [[s["dateFmt"], s["wdName"], s["arr"], s["dep"], s["total"], s["pairs"], s["crit"]] for s in dy["stats"]]))
            sheets.append(("Dia da semana", ["Dia", "Nº dias", "Mov. totais", "Méd mov/dia", "Críticos", "Méd crít/dia", "Taxa %", "Datas"], [[e["name"], e["days"], e["mov"], e["avgMov"], e["crit"], e["avgCrit"], e["rate"], ", ".join(e["dates"])] for e in dy["weekday"]]))
            sheets.append(("Companhias", ["Companhia", "Movimentos", "ARR", "DEP", "Críticos", "Taxa"], [[c["company"], c["movements"], c["arr"], c["dep"], c["critical"], round(c["rate"] * 100, 1)] for c in dy["companies"]]))
            sheets.append(("Callsigns comuns", ["Callsign", "Nº dias", "Dias", "Movimentos", "Companhia"], [[c["csn"], c["count"], ", ".join(fmt_date(d) for d in c["days"]), c["movements"], c["company"]] for c in dy["common"]]))
            sheets.append(("Por dia e hora", ["Data", "Dia", "Hora", "ARR", "DEP", "Movimentos", "Pares", "Críticos"], [[h["dateFmt"], h["wd"], h["hour"], h["arr"], h["dep"], h["total"], h["pairs"], h["crit"]] for h in dy["hourTable"]]))
        elif kind == "star":
            st = self.star or self.run_star()
            sheets.append(("Por waypoint", ["Waypoint", "Limite_kt", "Passagens", "Conformes", "Violacoes", "Cumprim_pct", "IAS_med", "IAS_max", "IAS_min", "Excesso_med", "Excesso_max"],
                           [[w["wp"], w["limit"], w["total"], w["compliant"], w["violations"], round(w["compliant"] / w["total"] * 100, 1), round(w["iasSum"] / w["total"]), w["iasMax"], w["iasMin"],
                             round(w["excessSum"] / w["violations"]) if w["violations"] else "", round(w["excessMax"]) if w["violations"] else ""] for w in st["perWp"]]))
            sheets.append(("Violações", ["N", "Hora", "Data", "Voo", "Tipo", "Waypoint", "IAS_kt", "Limite", "Excesso", "CPA_NM"],
                           [[i + 1, v["tod"], v["date"], v["csn"], v["actype"], v["wp"], round(v["ias"]), v["limit"], f"+{v['excess']:.0f}", round(v["dCpa"], 1)] for i, v in enumerate(st["violations"])]))
        elif kind == "app":
            ap = self.app or self.run_app()
            hb = ["Hora", "Data", "Voo", "Tipo", "Pista"] + [c for i in range(1, 5) for c in (f"PONTO{i}", f"IAS{i}", f"LIMITE{i}", f"DESVIO{i}")]
            rows = []
            for r in ap["records"]:
                row = [r["tod"], r["date"], r["csn"], r["actype"], int(r["rwy"])]
                for p in (r["points"] + [None] * 4)[:4]:
                    row += [p["point"], round(p["ias"]) if p["ias"] is not None else "", round(p["limit"]), f"{p['deviation']:+.0f}" if p["deviation"] is not None else ""] if p else ["", "", "", ""]
                rows.append(row)
            sheets.append(("Violações APP", hb, rows))
        elif kind == "appdist":
            ad = self.app_dist or self.run_app_dist()
            cols = ad["columns"]
            sheets.append(("Violações por distância", ["Callsign", "Data", "Hora", "Pista"] + [f"{c['label']}_{c['nm']:.1f}NM" for c in cols] + ["Med_Desvio_kt"],
                           [[r["csn"], r["date"], r["tod"], f"RWY{r['rwy']}"] + [r["dist"][f"{c['nm']:.1f}"]["ias"] for c in cols] + [r["avgDev"]] for r in ad["results"]]))
        elif kind == "rrms":
            rr = self.rrms or self.run_rrms()
            sheets.append(("RRMS", ["Callsign", "WTC", "Tipo_AC", "RWY", "Status", "Data", "Hora", "Alt_ft", "IAS_kt", "Dist_NM"],
                           [[h["csn"], h["cat"], h["acType"], h["rwy"], "No_ar" if h["airborne"] else "Solo", h["date"], h["tod"], h["altFt"], h["ias"], h["distNM"]] for h in rr["hits"]]))
        elif kind == "rot":
            rt = self.rot or self.run_rot()
            sheets.append(("ROT", ["N", "Mov", "Pista", "Data", "Voo", "Tipo", "Fonte", "ROT_s", "ROT_torre_s", "ROT_radar_s", "TWY_torre", "Hora_RWY_VAC_ou_RWY_ENT_torre", "Hora_ALDT_ou_ATOT_torre", "TWY_radar", "Hora_evento_radar", "Hora_THR_ou_1a_amostra_radar", "Hora_descolagem_radar", "Posicao_m_radar"],
                           [[i + 1, "ARR" if r.get("cls", "arr") == "arr" else "DEP", r["rwy"], r["date"], r["csn"], r["actype"], r.get("src", ""), r["rotS"], r.get("rotTower") or "", r.get("rotRadar") or "", r.get("twyTower") or "", r.get("tEventTowerStr") or "", r.get("tEventTower2Str") or "", r.get("twy") or "", r.get("tEventStr") or "", r.get("tTHRstr") or "", r.get("tOffStr", ""), r.get("exitM") or ""] for i, r in enumerate(rt["results"])]))
        elif kind == "pontos":
            rows = extra.get("rows", [])
            sheets.append(("Passagens", ["Hora", "Data", "Bloco", "Voo", "Tipo", "Dist_NM", "Altitude_ft", "IAS_kt", "ROC_fpm", "Latitude", "Longitude"],
                           [[r["tod"], r["date"], r["block"], r["csn"], r["cls"].upper(), r["d"], r["alt"], r["ias"], r["roc"], r["lat"], r["lon"]] for r in rows]))
        elif kind == "sequencia":
            rows = self.seq or []
            sheets.append(("Sequência", ["Seq", "Hora", "Data", "Bloco", "Voo", "Dist_CPA_NM", "AC_a_frente_NM", "AC_atras_NM", "Altitude_ft", "IAS_kt"],
                           [[i + 1, r["tod"], r["date"], r["block"], r["csn"], r["d"], r["antD"], r["segD"], r["alt"], r["ias"]] for i, r in enumerate(rows)]))
        elif kind == "kpis":
            k = self.kpis()
            rows = [["Movimentos", k["total"]], ["Chegadas (ARR)", k["arr"]], ["Partidas (DEP)", k["dep"]], ["Sobrevoos (LVL)", k["lvl"]], ["Período (UTC)", k["period"]]]
            sheets.append(("KPI", ["KPI", "Valor"], rows))
            sheets.append(("Por hora", ["Hora", "Total", "ARR", "DEP"], [[f"{h:02d}:00", k["byHour"][h], k["byArr"][h], k["byDep"][h]] for h in range(24)]))
        elif kind == "ia":
            rows = []
            for m in self.ia_history:
                rows.append(["Pergunta" if m["role"] == "user" else "Resposta IA", m["text"]])
                g = m.get("grafico")
                if g and g.get("dados"):
                    rows.append(["Gráfico", g.get("titulo", "")]); rows += [["Item", f"{d.get('nome')}: {d.get('valor')}"] for d in g["dados"]]
            sheets.append(("Análise IA", ["Tipo", "Conteúdo"], rows))
        else:
            raise ValueError("Exportação desconhecida: " + kind)
        if path.lower().endswith(".csv"):
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh, delimiter=";")
                for name, headers, rows in sheets:
                    w.writerow([name]); w.writerow(headers); w.writerows(rows); w.writerow([])
        else:
            reports.write_excel(path, sheets)
        return path

    def export_pptx(self, path: str):
        ap = self.app or self.run_app()
        caption = (f"Dias: {', '.join(date_label(d) for d in self.dates)} · Blocos: {', '.join(self.blocks) or 'todos'} · "
                   f"{len(self.flights)} movimento(s) ({ap['arrAnalysed']} ARR) · Raio CPA {ap['radius']:g} NM · tolerância ±{ap['tol']:g} kt")
        reports.write_pptx_ias_app(path, ap.get("histograms", []), caption, ap["tol"], self.airport)
        return path

    # ------------------------------------------------------------- relatórios HTML
    def report(self, kind: str, extra: dict | None = None) -> str:
        extra = extra or {}
        if kind == "voo":
            d = self.flight_detail(int(extra["flight_id"]))
            html = reports.report_flight(d["flight"], d["points"], d["app"], d["star"], d["tol"], d.get("sources"), d.get("final"))
        elif kind == "kpis":
            html = reports.report_kpis(self.kpis(), self.airport)
        elif kind == "dados":
            html = reports.report_data_analysis(self.data_analysis(**{k: v for k, v in extra.items()}), self.airport)
        elif kind == "diaria":
            html = reports.report_daily(self.daily(int(extra.get("limit", 165))), self.airport, self.blocks)
        elif kind == "rrms":
            rr = self.rrms or self.run_rrms()
            cat = extra.get("cat", "MH"); rwy = extra.get("rwy", "all")
            shown = [h for h in rr["hits"] if (cat == "all" or (cat == "MH" and h["cat"] in "MH") or h["cat"] == cat) and (rwy == "all" or h["rwy"] == rwy)]
            html = reports.report_rrms(rr, shown, cat, "Ambas" if rwy == "all" else f"RWY {rwy}")
        elif kind == "ia":
            html = reports.report_ia(self.ia_history, ia.PROVIDERS.get(self.ia_settings()["provider"], {}).get("name", ""))
        elif kind in ("mensal", "custom"):
            html = self.compose_report(extra)
        else:
            raise ValueError("Relatório desconhecido")
        out_dir = os.path.join(tempfile.gettempdir(), "flighttracker_relatorios"); os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"{kind}_{time.strftime('%Y%m%d_%H%M%S')}.html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)
        webbrowser.open("file://" + path.replace("\\", "/"))
        return path

    # ------------------------------------------------------------- IA
    def ia_settings(self) -> dict:
        raw = self.db.setting_get("ia_settings")
        s = json.loads(raw) if raw else {}
        s.setdefault("provider", "anthropic"); s.setdefault("keys", {}); s.setdefault("models", {}); s.setdefault("azure_endpoint", "")
        return s

    def ia_settings_set(self, provider=None, key=None, model=None, azure_endpoint=None):
        s = self.ia_settings()
        if provider: s["provider"] = provider
        if key is not None and key != "": s["keys"][s["provider"]] = key
        if model: s["models"][s["provider"]] = model
        if azure_endpoint is not None: s["azure_endpoint"] = azure_endpoint
        self.db.setting_set("ia_settings", json.dumps(s))
        return self.ia_public()

    def ia_public(self) -> dict:
        s = self.ia_settings(); p = s["provider"]
        return {"provider": p, "providers": {k: {"name": v["name"], "models": v["models"]} for k, v in ia.PROVIDERS.items()},
                "hasKey": bool(s["keys"].get(p)), "model": s["models"].get(p) or ia.PROVIDERS[p]["models"][0][0],
                "azure_endpoint": s["azure_endpoint"], "history": self.ia_history}

    def ia_ask(self, question: str) -> dict:
        s = self.ia_settings(); p = s["provider"]
        self.ensure_final()
        ctx = ia.build_context(self.flights, self.final, self.pairs, self.star, self.app, self.rot, self.seq, self.point_rows, self.point_name or "—")
        self.ia_history.append({"role": "user", "text": question})
        ans = ia.ask(p, s["keys"].get(p, ""), s["models"].get(p) or ia.PROVIDERS[p]["models"][0][0], question, ctx, s["azure_endpoint"])
        self.ia_history.append({"role": "ai", "text": ans["texto"], "grafico": ans.get("grafico")})
        return ans

    # ------------------------------------------------------------- Solo (ficheiro da torre)
    def ground_list(self):
        from . import ground as gmod
        rows = self.db.ground_list(self.airport, self.dates)
        try:
            af = gmod.airfield(self.airport)
        except Exception:  # noqa: BLE001 — aeroporto sem rede embebida
            af = None
        for r in rows:
            r["routable"] = bool(af) and bool(r.get("taxi_out") or r.get("taxi_in"))
        self.ground = rows
        return {"rows": rows, "summary": self.db.ground_summary(), "network": af is not None,
                "stats": gmod.ground_stats(rows) if rows else None}

    def ground_routes(self, gids: list[int]):
        from . import ground as gmod
        af = gmod.airfield(self.airport)
        out = {}
        for r in self.db.ground_get([int(g) for g in gids]):
            m = gmod.build_movement(r, af)
            if m:
                m["csn"] = r["csn"]; m["mt"] = r["mt"]; m["actype"] = r.get("actype"); m["rwy"] = r.get("rwy")
                m["stand"] = r.get("stand_d") if r["mt"] == "DEPARTURE" else r.get("stand_a")
                out[r["gid"]] = m
        return out

    def ground_network(self):
        from . import ground as gmod
        af = gmod.airfield(self.airport)
        ways = [{"type": w["type"], "ref": w.get("ref"), "pts": [af.nodes[n] for n in w["nodes"] if n in af.nodes]} for w in af.ways]
        return {"ways": ways, "stands": af.stands, "holding": af.holding, "thr": {k: v["thr"] for k, v in af.thr.items()}}

    def ground_raw(self, gid: int):
        return self.db.ground_raw(int(gid))

    # ------------------------------------------------------------- relatórios compostos (mensal / personalizados)
    REPORT_SECTIONS = {
        "pru": "KPIs PRU (throughput, taxi adicional, ASMA, pontualidade, ATFM, CDO)",
        "painel": "Evolução diária (movimentos, ROT, taxi, pontualidade, top 10)",
        "solo": "Ocupação de pista e taxi (A-SMGCS)",
        "kpis": "KPIs operacionais do radar (aproximações, separações, IAS STAR)",
        "dados": "Análise de dados (FAST, separações, narrativa)",
        "diaria": "Análise diária",
        "rrms": "RRMS",
        "cross": "Cruzamento de fontes (cobertura e discrepâncias)",
    }

    def compose_report(self, extra: dict) -> str:
        secs = extra.get("sections") or ["pru", "painel", "solo", "kpis", "cross"]
        title = extra.get("title") or f"Relatório mensal — {self.airport}"
        dates = sorted(self.dates)
        d0, d1 = (extra.get("d0") or (dates[0] if dates else None)), (extra.get("d1") or (dates[-1] if dates else None))
        sub = f"{self.airport} · {fmt_date(d0) if d0 else '?'} → {fmt_date(d1) if d1 else '?'} · {len(dates)} dia(s) no filtro"
        parts = []
        for s in secs:
            try:
                if s == "pru":
                    parts.append(reports.section_pru(self.pru or self.pru_kpis()))
                elif s == "painel" and d0 and d1:
                    pn = self.panel(d0, d1, extra.get("r0"), extra.get("r1"))
                    parts.append(reports.section_panel(pn))
                elif s == "solo":
                    g = self.ground_list()
                    parts.append(reports.section_ground(g.get("stats")))
                elif s == "kpis":
                    parts.append(reports.body_of(reports.report_kpis(self.kpis(), self.airport)))
                elif s == "dados":
                    parts.append(reports.body_of(reports.report_data_analysis(self.data_analysis(), self.airport)))
                elif s == "diaria":
                    parts.append(reports.body_of(reports.report_daily(self.daily(165), self.airport, self.blocks)))
                elif s == "rrms":
                    rr = self.rrms or self.run_rrms()
                    parts.append(reports.body_of(reports.report_rrms(rr, [h for h in rr["hits"] if h["cat"] in "MH"], "MH", "Ambas")))
                elif s == "cross":
                    cr = self.cross or self.crosscheck(); c = cr["coverage"]
                    parts.append("<h2>Cruzamento de fontes</h2>" + reports.kpi_grid([("Movimentos (união)", c["total"]), ("Radar", c["radar"]), ("Torre", c["torre"]), ("OPDI", c["opdi"]), ("Radar ∩ Torre", c["r_t"]), ("Torre ∩ OPDI", c["t_o"]), ("Com NMIR", c["nmir"]), ("Discrepâncias", c["with_flags"]), ("Só torre", c["only_torre"]), ("Só OPDI", c["only_opdi"])]) +
                                 reports.table(["Data", "Voo", "Mov.", "Fontes", "Discrepâncias"], [[fmt_date(r["date"]), r["csn"], r["cls"].upper(), r["src"], "; ".join(f for f in r["flags"] if not f.startswith("sem "))] for r in cr["rows"] if r["n_flags"]], limit=200))
            except Exception as e:  # noqa: BLE001 — uma secção falhada não impede o relatório
                parts.append(f"<h2>{reports.esc(self.REPORT_SECTIONS.get(s, s))}</h2><p class='note'>Sem dados: {reports.esc(str(e))}</p>")
        return reports.report_composed(title, sub, parts)

    def custom_report_run(self, extra: dict) -> str:
        """Relatório à medida com aeroporto e intervalo de datas escolhidos no momento (Preferências).
        Não altera o filtro activo da aplicação: guarda o estado, gera o relatório e repõe tudo no fim."""
        snap = (self.airport, self.dates, self.blocks, self.csn, self.cls, self.flights, self.all_flights,
                getattr(self, "airport_only_ids", None))
        try:
            airport = extra.get("airport") or self.airport
            dates = sorted(set(extra.get("dates") or []))
            if not dates:
                raise ValueError("Não há dias com dados radar nesse intervalo para esse aeroporto.")
            self.set_filter(dates, [], "", "", airport)
            rep = dict(extra); rep["d0"] = dates[0]; rep["d1"] = dates[-1]
            rep.setdefault("title", f"Relatório {airport} · {fmt_date(dates[0])} → {fmt_date(dates[-1])}")
            return self.report("custom", rep)
        finally:
            (self.airport, self.dates, self.blocks, self.csn, self.cls, self.flights, self.all_flights,
             self.airport_only_ids) = snap
            self.reset_results()

    # ------------------------------------------------------------- Excel à medida (Preferências)
    def dataset_catalog(self) -> dict:
        from . import dataset
        return dataset.catalog()

    def _dataset_rows(self, airport: str, dates: list[str]) -> list[dict]:
        from . import dataset
        key = (airport, tuple(sorted(set(dates))))
        cache = getattr(self, "_ds_cache", None)
        if cache and cache[0] == key:
            return cache[1]
        rows = dataset.build_rows(self.db, airport, sorted(set(dates)))
        self._ds_cache = (key, rows)
        return rows

    def dataset_preview(self, extra: dict) -> dict:
        """Nº de movimentos no período e após os filtros; valores mais frequentes de um campo (para ajudar a filtrar)."""
        from . import dataset
        dates = sorted(set(extra.get("dates") or []))
        if not dates:
            return {"total": 0, "n": 0, "values": []}
        rows = self._dataset_rows(extra.get("airport") or self.airport, dates)
        sel = dataset.apply_filters(rows, extra.get("filters") or [])
        out = {"total": len(rows), "n": len(sel), "values": []}
        fld = extra.get("field")
        if fld in dataset.FIELD_TYPE:
            from collections import Counter
            ty = dataset.FIELD_TYPE[fld]
            c = Counter(dataset._fmt(ty, r.get(fld)) for r in rows if r.get(fld) is not None)
            out["values"] = [[str(k), n] for k, n in c.most_common(40)]
        return out

    def dataset_excel(self, path: str, extra: dict) -> str:
        from . import dataset
        dates = sorted(set(extra.get("dates") or []))
        if not dates:
            raise ValueError("Não há dias com dados nesse intervalo para esse aeroporto.")
        airport = extra.get("airport") or self.airport
        rows = self._dataset_rows(airport, dates)
        sel = dataset.apply_filters(rows, extra.get("filters") or [])
        reports.write_excel(path, dataset.sheets(sel, extra.get("fields") or [], extra.get("filters") or [], extra.get("groups") or [], airport, dates, len(rows)))
        return path

    def custom_reports(self) -> list[dict]:
        raw = self.db.setting_get("custom_reports")
        return json.loads(raw) if raw else []

    def custom_reports_set(self, lst: list[dict]):
        self.db.setting_set("custom_reports", json.dumps(lst, ensure_ascii=False))
        return lst

    # ------------------------------------------------------------- KPIs PRU / painel diário
    def pru_kpis(self):
        from .analysis import pru
        ground = self.db.ground_list(self.airport, self.dates)
        opdi = self.db.opdi_flights(self.airport, self.dates)
        nmir_rows = self.db.nmir_departures(self.airport, self.dates)
        cap = self.db.setting_get(f"capacity_{self.airport}")
        res = pru.compute(self.db, self.airport, self.flights, ground, opdi, nmir_rows, int(cap) if cap else None, self.db.ground_reference(self.airport))
        self.pru = res
        return res

    def export_rows(self, path: str, title: str, headers: list[str], rows: list[list]):
        return reports.write_excel(path, [(title[:28] or "Dados", headers, rows)])

    def report_rows(self, title: str, headers: list[str], rows: list[list]) -> str:
        html = reports.wrap(title, f"{self.airport} · {len(rows)} registo(s) · {', '.join(fmt_date(d) for d in sorted(self.dates)[:3])}{'…' if len(self.dates) > 3 else ''}",
                            reports.table(headers, rows), landscape=len(headers) > 8)
        out_dir = os.path.join(tempfile.gettempdir(), "flighttracker_relatorios"); os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"dados_{time.strftime('%Y%m%d_%H%M%S')}.html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)
        webbrowser.open("file://" + path.replace("\\", "/"))
        return path

    def panel_details(self, key: str, d0: str, d1: str):
        """Dados de origem dos cartões do Painel."""
        dates = [r["date"] for r in self.db.daily_series(self.airport, d0, d1)]
        if key in ("ga", "atfm", "mov_torre"):
            if key == "ga":
                return self.db.go_arounds(self.airport, dates)
            rows = self.db.ground_list(self.airport, dates)
            if key == "atfm":
                return sorted([r for r in rows if r.get("atfm_delay")], key=lambda r: -r["atfm_delay"])
            return rows
        if key in ("otp", "slot"):
            from .analysis import pru
            f = pru.atfm_and_punctuality(self.db.nmir_departures(self.airport, dates), [])
            return f[key]["records"]
        if key == "mov_radar":
            return self.db.flights_list(self.airport, dates, [], "", "")
        if key.startswith("heat:"):          # heat:<dow>:<hora>:<all|arr|dep>[:<aeroporto>]
            parts = key.split(":")
            apt = parts[4] if len(parts) > 4 else self.airport
            return self.db.heatmap_rows(apt, d0, d1, int(parts[1]), int(parts[2]), parts[3])
        return []

    def set_capacity(self, airport: str, cap: int):
        self.db.setting_set(f"capacity_{airport}", str(int(cap)))
        return int(cap)

    def panel(self, d0: str, d1: str, r0: str | None = None, r1: str | None = None):
        """Série diária para o painel: período principal e, opcionalmente, período de referência."""
        main = self.db.daily_series(self.airport, d0, d1)
        ref = self.db.daily_series(self.airport, r0, r1) if r0 and r1 else []
        return {"main": main, "ref": ref, "top": self.db.top_lists(self.airport, d0, d1), "heat": self.db.heatmap(self.airport, d0, d1),
                "top_ref": self.db.top_lists(self.airport, r0, r1) if r0 and r1 else None, "airport": self.airport}

    # ------------------------------------------------------------- Cruzamento de fontes
    def crosscheck(self):
        from . import integrate
        from .analysis.ops import nmir_lookup
        ground = self.db.ground_list(self.airport, self.dates)
        opdi = self.db.opdi_flights(self.airport, self.dates)
        res = integrate.crosscheck(self.airport, self.flights, ground, opdi, lambda c, d: nmir_lookup(self.db, c, d), self.db.corrections(self.dates), self.db.type_overrides())
        self.cross = res
        res["summary"] = {"ground": self.db.ground_summary(), "opdi": self.db.opdi_summary()}
        return res

    def correction_set(self, csn, date, cls, actype=None, wtc=None, apt=None, note=None, verified=False):
        r = self.db.correction_set(csn, date, cls, actype, wtc, apt, note, verified, self.airport)
        # reflecte o tipo corrigido nos movimentos já carregados
        if actype:
            for f in self.all_flights:
                if f["csn"] == csn and f["date"] == date and f["cls"] == cls:
                    f["actype"] = r["actype"]; f["wtc"] = r["wtc"]
        self.cross = None
        return r

    def correction_delete(self, csn, date, cls):
        self.db.correction_delete(csn, date, cls); self.cross = None
        return True

    def type_wtc_set(self, actype, wtc, note=None):
        n = self.db.type_wtc_set(actype, wtc, note)
        for f in self.all_flights:
            if f.get("actype") == actype.strip().upper():
                f["wtc"] = wtc.strip().upper()
        self.cross = None; self.reset_results()
        return n

    def ia_context_preview(self) -> str:
        self.ensure_final()
        return ia.build_context(self.flights, self.final, self.pairs, self.star, self.app, self.rot, self.seq, self.point_rows, self.point_name or "—")
