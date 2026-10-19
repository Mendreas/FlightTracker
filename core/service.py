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
        self.reset_results()
        return {"flights": self.all_flights, "airport": self.airport, "airports": airports}

    def set_airport(self, airport: str):
        self.airport = airport
        self.flights = [f for f in self.all_flights if f["airport"] == airport]
        self.reset_results()
        return len(self.flights)

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
        self.rot = ops.run_rot(self.db, self.flights, self.airport)
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
        ref = pts[-1] if f["cls"] != "dep" else pts[0]
        rwy = min(cfg["rwys"], key=lambda r: dist_nm(ref["lat"], ref["lon"], *cfg["rwys"][r]["thr"])) if pts else None
        if rwy:
            thr = cfg["rwys"][rwy]["thr"]
            for p in pts:
                p["dist_thr"] = dist_nm(p["lat"], p["lon"], *thr)
        app_rec = next((r for r in (self.app or {}).get("records", []) if r["flight_id"] == fid), None)
        star_v = [v for v in (self.star or {}).get("violations", []) if v["flight_id"] == fid]
        fin = [r for r in (self.final or []) if r["flight_id"] == fid]
        return {"flight": {**f, "date_fmt": fmt_date(f["date"]), "rwy_guess": rwy}, "points": pts, "app": app_rec, "star": star_v, "final": fin,
                "tol": (self.app or {}).get("tol", 0)}

    # ------------------------------------------------------------- exportações
    def export_excel(self, path: str, kind: str, extra: dict | None = None):
        extra = extra or {}
        sheets = []
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
            sheets.append(("ROT", ["N", "Pista", "Data", "Voo", "Tipo", "Hora_THR", "ROT_s", "Dist_saida_m"], [[i + 1, r["rwy"], r["date"], r["csn"], r["actype"], r["tTHRstr"], r["rotS"], r["exitM"]] for i, r in enumerate(rt["results"])]))
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
            html = reports.report_flight(d["flight"], d["points"], d["app"], d["star"], d["tol"])
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

    def ia_context_preview(self) -> str:
        self.ensure_final()
        return ia.build_context(self.flights, self.final, self.pairs, self.star, self.app, self.rot, self.seq, self.point_rows, self.point_name or "—")
