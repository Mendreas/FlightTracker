"""Análise Op. — FAST (separação entre chegadas), Análise de Dados e Análise Diária.

Nota: a categoria de sequência com 3+ descolagens é 'AD…A' (reticência Unicode) em todo o lado;
a versão antiga tinha uma inconsistência 'AD...A' que impedia estes pares de aparecer nos gráficos.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median

from ..geo import epoch, hhmmss, fmt_date, company, weekday, WD_SHORT, WD_LONG

SEQ_LABELS = ["AA", "ADA", "ADDA", "AD…A"]
HIST_BINS = [0, 60, 90, 120, 140, 165, 200, 240, float("inf")]
HIST_LABELS = ["0-60", "60-90", "90-120", "120-140", "140-165", "165-200", "200-240", ">240"]
DEP_BINS = [0, 3, 4, 5, 6, float("inf")]
DEP_LABELS = ["<3", "3-4", "4-5", "5-6", ">6"]
DEP_CLASSES = ["muito crítico", "crítico", "apertado", "normal", "confortável"]
IAS_BINS = [0, 140, 150, 160, 170, float("inf")]
IAS_LABELS = ["<140", "140-150", "150-160", "160-170", ">170"]


def _bin(v, bins):
    for i in range(len(bins) - 1):
        if bins[i] <= v < bins[i + 1]:
            return i
    return None


def dep_events(flights: list[dict]) -> list[dict]:
    """Descolagens = movimentos classificados DEP; hora = primeiro plot radar."""
    out = [{"t": epoch(f["date"], f["t_first"]), "csn": f["csn"], "date": f["date"], "flight_id": f["flight_id"]}
           for f in flights if f["cls"] == "dep" and f["t_first"] is not None]
    out.sort(key=lambda d: d["t"])
    return out


def build_pairs(final_results: list[dict], deps: list[dict]) -> list[dict]:
    """Pares de aterragens consecutivas na mesma pista e dia, 0 < sep ≤ 600 s, enriquecidos com DEP intercalar."""
    by_key: dict[str, list] = defaultdict(list)
    for r in final_results:
        by_key[f"{r['rwy']}|{r['_dateRaw']}"].append(r)
    pairs = []
    for arr in by_key.values():
        arr.sort(key=lambda r: r["epochTHR"])
        for i in range(1, len(arr)):
            lead, trail = arr[i - 1], arr[i]
            sep = trail["epochTHR"] - lead["epochTHR"]
            if sep <= 0 or sep > 600:
                continue
            pairs.append({"lead": lead, "trail": trail, "sep": sep})
    pairs.sort(key=lambda p: p["lead"]["epochTHR"])
    for idx, p in enumerate(pairs):
        t0, t1 = p["lead"]["epochTHR"], p["trail"]["epochTHR"]
        deps_in = [d for d in deps if t0 < d["t"] < t1]
        n = len(deps_in)
        p["id"] = idx
        p["depsIn"] = [{"csn": d["csn"], "t": d["t"], "tod": hhmmss(d["t"])} for d in deps_in]
        p["depCnt"] = n
        p["seq"] = "AA" if n == 0 else "ADA" if n == 1 else "ADDA" if n == 2 else "AD…A"
        ias_t = p["trail"]["iasTHR"]
        first = deps_in[0] if deps_in else None
        p["firstDep"] = first["csn"] if first else None
        p["firstDepTod"] = hhmmss(first["t"]) if first else None
        p["bSecAtDep"] = round(t1 - first["t"]) if first and ias_t and (t1 - first["t"]) > 0 else None
        p["bNmAtDep"] = round(p["bSecAtDep"] * ias_t / 3600, 2) if p["bSecAtDep"] is not None else None
        p["depDistances"] = [round((t1 - d["t"]) * (ias_t or 140) / 3600, 2) for d in deps_in if (t1 - d["t"]) > 0]
        p["sepNm"] = round(sep_nm(p["sep"]), 2)
    return pairs


def sep_nm(sep: float) -> float:
    return sep * 140 / 3600


def fast_view(pairs: list[dict], thr: int = 160, mode: str = "all", intercal_only: bool = False, rwy: str = "all") -> list[dict]:
    out = []
    for p in pairs:
        s = p["sep"]
        if mode == "lt" and not s < thr: continue
        if mode == "range" and not (thr <= s <= 240): continue
        if intercal_only and p["depCnt"] == 0: continue
        if rwy != "all" and str(p["lead"]["rwy"]) != rwy: continue
        out.append(_pair_row(p))
    return out


def _pair_row(p: dict) -> dict:
    L, Tr = p["lead"], p["trail"]
    return {"id": p["id"], "rwy": L["rwy"], "date": L["date"], "dateRaw": L["_dateRaw"],
            "lead": L["csn"], "leadFlight": L["flight_id"], "leadTod": L["tTHRstr"], "leadIas": L["iasTHR"], "leadAlt": L["altTHR"],
            "trail": Tr["csn"], "trailFlight": Tr["flight_id"], "trailTod": Tr["tTHRstr"], "trailIas": Tr["iasTHR"], "trailAlt": Tr["altTHR"],
            "sep": p["sep"], "sepNm": p["sepNm"], "seq": p["seq"], "depCnt": p["depCnt"], "deps": p["depsIn"],
            "firstDep": p["firstDep"], "firstDepTod": p["firstDepTod"], "bSecAtDep": p["bSecAtDep"], "bNmAtDep": p["bNmAtDep"],
            "depDistances": p["depDistances"], "tLead": L["epochTHR"] % 86400, "tTrail": Tr["epochTHR"] % 86400,
            "hour": L["tTHRstr"][:2]}


def movements(final_results: list[dict], deps: list[dict]) -> list[dict]:
    movs = [{"type": "ARR", "csn": r["csn"], "tod": r["tTHRstr"], "rwy": str(r["rwy"]), "date": r["_dateRaw"], "t": r["epochTHR"]}
            for r in final_results]
    movs += [{"type": "DEP", "csn": d["csn"], "tod": hhmmss(d["t"]), "rwy": "", "date": d["date"], "t": d["t"]} for d in deps]
    movs.sort(key=lambda m: m["t"])
    return movs


def company_summary(movs: list[dict], crit_pairs: list[dict]) -> list[dict]:
    comp: dict[str, dict] = {}
    for m in movs:
        c = company(m["csn"])
        e = comp.setdefault(c, {"company": c, "movements": 0, "arr": 0, "dep": 0, "critical": 0})
        e["movements"] += 1
        e["arr" if m["type"] == "ARR" else "dep"] += 1
    for p in crit_pairs:
        for c in {company(p["lead"]), company(p["trail"])}:
            e = comp.setdefault(c, {"company": c, "movements": 0, "arr": 0, "dep": 0, "critical": 0})
            e["critical"] += 1
    for e in comp.values():
        e["rate"] = e["critical"] / e["movements"] if e["movements"] else 0
    return sorted(comp.values(), key=lambda e: (-e["movements"], e["company"]))


def hour_summary(movs: list[dict]) -> dict:
    arr = Counter(m["tod"][:2] for m in movs if m["type"] == "ARR")
    dep = Counter(m["tod"][:2] for m in movs if m["type"] == "DEP")
    tot = Counter(m["tod"][:2] for m in movs)
    def peak(c):
        if not c: return None
        h = min(c, key=lambda k: (-c[k], k))
        return {"hour": h, "n": c[h]}
    return {"peakArr": peak(arr), "peakDep": peak(dep), "peakTotal": peak(tot),
            "byHour": {h: {"arr": arr.get(h, 0), "dep": dep.get(h, 0), "total": tot.get(h, 0)} for h in sorted(tot)}}


# ----------------------------------------------------------------- Análise de Dados
def data_analysis(pairs: list[dict], movs: list[dict], all_pairs_count: int, landings: int, files: int,
                  limit: int = 165, f_date: str = "all", f_hour: str = "all", f_rwy: str = "all",
                  f_tipo: str = "all", f_seq: str = "all", f_depnm: str = "all", f_crit: str = "all") -> dict:
    rows = [_pair_row(p) for p in pairs]
    def keep(r):
        if f_date != "all" and r["dateRaw"] != f_date: return False
        if f_hour != "all" and r["hour"] != f_hour: return False
        if f_rwy != "all" and str(r["rwy"]) != f_rwy: return False
        if f_tipo == "withDep" and r["depCnt"] == 0: return False
        if f_tipo == "noDep" and r["depCnt"] > 0: return False
        if f_seq != "all" and r["seq"] != f_seq: return False
        if f_depnm != "all":
            if r["depCnt"] == 0 or not any(d <= float(f_depnm) for d in r["depDistances"]): return False
        if f_crit == "crit" and not round(r["sep"]) < limit: return False
        return True
    frows = [r for r in rows if keep(r)]
    fmovs = [m for m in movs if (f_date == "all" or m["date"] == f_date) and (f_hour == "all" or m["tod"][:2] == f_hour)
             and (f_rwy == "all" or m["rwy"] == f_rwy)]
    crit = [r for r in frows if round(r["sep"]) < limit]
    seps = [round(r["sep"]) for r in frows]
    crit_hours = Counter(r["hour"] for r in crit)
    busy = Counter(r["hour"] for r in frows)
    rwys = Counter(str(r["rwy"]) for r in frows)
    hs = hour_summary(fmovs)
    def mode_lbl(c, fmt="{}h ({})"):
        if not c: return "—"
        k = min(c, key=lambda x: (-c[x], x))
        return fmt.format(k, c[k])
    kpis = {
        "pairs": len(frows), "crit": len(crit), "critDep": sum(1 for r in crit if r["depCnt"]), "critNoDep": sum(1 for r in crit if not r["depCnt"]),
        "min": min(seps) if seps else None, "avg": sum(seps) / len(seps) if seps else None, "median": median(seps) if seps else None,
        "critHour": mode_lbl(crit_hours), "busyHour": mode_lbl(busy), "mainRwy": mode_lbl(rwys, "RWY {} ({})"),
        "depTotal": sum(r["depCnt"] for r in frows), "movs": len(fmovs),
        "peakArr": hs["peakArr"], "peakDep": hs["peakDep"], "peakTotal": hs["peakTotal"],
        "files": files, "landings": landings, "allPairs": all_pairs_count, "movementRows": len(movs),
    }
    # gráficos
    hist = [0] * (len(HIST_BINS) - 1); hist_crit = [0] * (len(HIST_BINS) - 1)
    for r in frows:
        b = _bin(round(r["sep"]), HIST_BINS)
        if b is not None:
            hist[b] += 1
            if round(r["sep"]) < limit: hist_crit[b] += 1
    hist_red = [HIST_BINS[i + 1] <= limit or (HIST_BINS[i] < limit < HIST_BINS[i + 1]) for i in range(len(hist))]
    by_hour = {}
    for r in frows:
        e = by_hour.setdefault(r["hour"], {"total": 0, "crit": 0, "dep": 0})
        e["total"] += 1; e["crit"] += round(r["sep"]) < limit; e["dep"] += r["depCnt"] > 0
    by_rwy = {rw: {"total": sum(1 for r in frows if str(r["rwy"]) == rw), "crit": sum(1 for r in crit if str(r["rwy"]) == rw),
                   "dep": sum(1 for r in frows if str(r["rwy"]) == rw and r["depCnt"])} for rw in ["02", "20"]}
    by_seq = {s: {"total": sum(1 for r in frows if r["seq"] == s), "crit": sum(1 for r in crit if r["seq"] == s)} for s in SEQ_LABELS}
    comp = company_summary(fmovs, crit)
    dep_vals = [d for r in frows for d in r["depDistances"]]
    dep_hist = [0] * 5; dep_hist_crit = [0] * 5
    for r in frows:
        for d in r["depDistances"]:
            b = _bin(d, DEP_BINS)
            if b is not None:
                dep_hist[b] += 1
                if round(r["sep"]) < limit: dep_hist_crit[b] += 1
    ias_hist = [0] * 5; ias_hist_crit = [0] * 5
    for r in frows:
        if r["trailIas"] is not None:
            b = _bin(r["trailIas"], IAS_BINS)
            if b is not None:
                ias_hist[b] += 1
                if round(r["sep"]) < limit: ias_hist_crit[b] += 1
    # tabelas
    top10 = sorted(frows, key=lambda r: round(r["sep"]))[:10]
    arrivals_by_hour = Counter()
    seen = set()
    for r in rows:  # TODOS os pares (não filtrados), como na app antiga
        k = f"{r['lead']}|{r['leadTod']}|{r['rwy']}"
        if k not in seen:
            seen.add(k); arrivals_by_hour[r["hour"]] += 1
    hour_table = []
    for h in sorted(by_hour):
        hr = [r for r in frows if r["hour"] == h]
        hour_table.append({"hour": h, "arrivals": arrivals_by_hour.get(h, 0), "pairs": len(hr),
                           "crit": sum(1 for r in hr if round(r["sep"]) < limit), "dep": sum(r["depCnt"] for r in hr),
                           "minSep": min(round(r["sep"]) for r in hr), "avgSep": sum(round(r["sep"]) for r in hr) / len(hr)})
    timeline = [{"id": r["id"], "rwy": str(r["rwy"]), "tLead": r["tLead"], "tTrail": r["tTrail"], "lead": r["lead"], "trail": r["trail"],
                 "deps": [{"t": d["t"] % 86400, "csn": d["csn"]} for d in r["deps"]], "crit": round(r["sep"]) < limit} for r in frows]
    scatter = [{"id": r["id"], "sep": r["sep"], "nm": r["sepNm"], "dep": r["depCnt"] > 0, "crit": round(r["sep"]) < limit,
                "ias": r["trailIas"], "lead": r["lead"], "trail": r["trail"]} for r in frows]
    options = {"dates": sorted({r["dateRaw"] for r in rows}), "hours": sorted({r["hour"] for r in rows}),
               "rwys": sorted({str(r["rwy"]) for r in rows}), "seqs": [s for s in SEQ_LABELS if any(r["seq"] == s for r in rows)]}
    ctx = {"limit": limit, "kpis": kpis, "rows": frows, "crit": crit, "comp": comp, "by_rwy": by_rwy, "by_seq": by_seq,
           "filters": {"Limite crítico": f"{limit}s", "Data": fmt_date(f_date) if f_date != "all" else "Todas",
                       "Hora": f"{f_hour}h" if f_hour != "all" else "Todas", "Pista": f"RWY {f_rwy}" if f_rwy != "all" else "Todas",
                       "Tipo": {"all": "Tudo", "withDep": "Com DEP entre aterragens", "noDep": "Sem DEP no meio"}[f_tipo],
                       "Sequência": f_seq if f_seq != "all" else "Todas",
                       "Seguidor no DEP até": f"{f_depnm} NM" if f_depnm != "all" else "Qualquer distância",
                       "Mostrar": "Só abaixo do limite" if f_crit == "crit" else "Todos os pares precedente/seguidor"}}
    return {"kpis": kpis, "rows": frows, "options": options, "filters": ctx["filters"],
            "charts": {"hist": {"labels": HIST_LABELS, "total": hist, "crit": hist_crit, "red": hist_red},
                       "byHour": by_hour, "byRwy": by_rwy, "bySeq": by_seq, "movHour": hs["byHour"],
                       "companies": comp[:15], "topCritCompanies": sorted([c for c in comp if c["critical"]],
                                                                          key=lambda c: (-c["rate"], -c["critical"], -c["movements"]))[:10],
                       "depDist": {"labels": DEP_LABELS, "classes": DEP_CLASSES, "total": dep_hist, "crit": dep_hist_crit, "n": len(dep_vals)},
                       "scatter": scatter, "timeline": timeline, "ias": {"labels": IAS_LABELS, "total": ias_hist, "crit": ias_hist_crit}},
            "tables": {"top10": top10, "hour": hour_table, "companies": comp},
            "narrative": data_narrative(ctx)}


def data_narrative(ctx: dict) -> dict:
    k, limit = ctx["kpis"], ctx["limit"]
    pairs, crit = k["pairs"], k["crit"]
    rate = round(crit / pairs * 1000) / 10 if pairs else 0
    paras, insights = [], []
    skip = {"Todas", "Tudo", "Todos os pares precedente/seguidor", "Qualquer distância", ""}
    filt = "; ".join(f"{a}: {b}" for a, b in ctx["filters"].items() if b not in skip and a != "Limite crítico")
    paras.append(f"Este relatório analisa a separação entre chegadas consecutivas na LPPT, com limite crítico de {limit} segundos."
                 + (f" Filtros activos: {filt}." if filt else "")
                 + f" A amostra inclui {pairs} par(es) precedente/seguidor" + (f" e {k['movs']} movimentos ARR+DEP." if k["movs"] else "."))
    paras.append(f"Os dados provêm de {k['files']} ficheiro(s) CSV ({k['movementRows']} movimentos, {k['landings']} passagens THR, {k['allPairs']} pares na janela global).")
    if pairs:
        s = f"Foram identificados {crit} pares abaixo do limite ({rate}%)"
        if crit: s += f", dos quais {k['critDep']} com descolagem intercalada (DEP) e {k['critNoDep']} sem DEP"
        paras.append(s + ".")
        if rate >= 15: paras.append(f"A taxa de críticos ({rate}%) é elevada e sugere pressão operacional significativa na sequência de chegadas analisada.")
        elif rate > 0: paras.append(f"A taxa global de críticos ({rate}%) é moderada; convém cruzar com hora, pista e tipo de sequência para localizar concentrações.")
        else: paras.append(f"Não foram registados pares abaixo de {limit}s nos filtros seleccionados.")
        insights.append(f"{rate}% dos pares abaixo de {limit}s")
    if k["min"] is not None:
        paras.append(f"A menor separação observada foi {k['min']} s, com média de {k['avg']:.1f} s e mediana de {k['median']:.1f} s — indicadores úteis para avaliar o aperto típico vs casos extremos.")
        insights.append(f"Menor separação: {k['min']} s")
    if crit:
        paras.append(f"A hora com mais pares críticos foi {k['critHour']}, o que aponta para o período do dia com maior risco de sequências apertadas.")
        insights.append(f"Hora mais crítica: {k['critHour']}")
    if pairs:
        paras.append(f"A hora mais movimentada em pares precedente/seguidor foi {k['busyHour']} — nem sempre coincide com a hora mais crítica, o que pode indicar densidade vs aperto real.")
    if k["peakArr"]: paras.append(f"O pico de aterragens ocorreu à hora {k['peakArr']['hour']}h ({k['peakArr']['n']}).")
    if k["peakDep"]: paras.append(f"O pico de descolagens ocorreu à hora {k['peakDep']['hour']}h ({k['peakDep']['n']}), relevante para sequências ADA/ADDA com DEP intercalado.")
    br = ctx["by_rwy"]
    main = max(br, key=lambda r: br[r]["total"]) if any(v["total"] for v in br.values()) else None
    if main:
        v = br[main]; other = [r for r in br if r != main and br[r]["total"]]
        s = f"RWY {main} concentra {v['total']} pares ({v['crit']} críticos, {v['crit'] / v['total'] * 100:.1f}%)"
        if other:
            o = br[other[0]]; s += f"; RWY {other[0]} regista taxa de {o['crit'] / o['total'] * 100:.1f}%"
        paras.append(s + ".")
        insights.append(f"Pista principal: RWY {main}")
    bs = ctx["by_seq"]
    dom = max(bs, key=lambda q: bs[q]["total"]) if any(v["total"] for v in bs.values()) else None
    if dom:
        s = f"A sequência dominante é {dom} ({bs[dom]['total']} pares, {bs[dom]['crit']} críticos)"
        others = sorted([q for q in bs if q != dom and bs[q]["crit"]], key=lambda q: -bs[q]["crit"])
        if others: s += f"; {others[0]} destaca-se com {bs[others[0]]['crit']} ocorrências críticas"
        paras.append(s + ".")
        if dom == "AA": paras.append("Predominância de sequências AA (chegada seguida de chegada, sem DEP) indica fluxo principalmente de aterragens consecutivas.")
        elif dom == "ADA": paras.append("Sequências ADA frequentes indicam descolagens intercaladas entre chegadas — factor relevante na gestão de separação.")
    comp = ctx["comp"]
    if comp:
        top = comp[0]
        s = f"{top['company']} lidera em movimentos ({top['movements']} ARR+DEP"
        if top["critical"]: s += f", {top['critical']} ocorrências críticas ({top['rate'] * 100:.1f}%)"
        paras.append(s + ").")
        worst = max((c for c in comp if c["critical"]), key=lambda c: c["rate"], default=None)
        if worst and worst is not top:
            paras.append(f"{worst['company']} apresenta a maior taxa de críticos por movimento ({worst['rate'] * 100:.1f}%).")
    if ctx["rows"]:
        t = min(ctx["rows"], key=lambda r: r["sep"])
        s = f"O par mais apertado foi {t['lead']} → {t['trail']} ({round(t['sep'])} s, {t['sepNm']} NM) em {t['date']} às {t['leadTod']}"
        if t["firstDep"]: s += f", com DEP {t['firstDep']}"
        paras.append(s + ".")
    return {"paragraphs": paras, "insights": insights}


# ----------------------------------------------------------------- Análise Diária
def _block_hours(block: str) -> set[str]:
    try:
        a, b = block.split("-")
        return {f"{h:02d}" for h in range(int(a), int(b))}
    except ValueError:
        return set()


def daily_analysis(pairs: list[dict], movs: list[dict], dates: list[str], blocks: list[str], limit: int = 165) -> dict:
    dates_set = set(dates)
    hours = set().union(*[_block_hours(b) for b in blocks]) if blocks else None
    in_block = lambda h: hours is None or h in hours
    rows = [_pair_row(p) for p in pairs if p["lead"]["_dateRaw"] in dates_set and in_block(p["lead"]["tTHRstr"][:2])]
    fm = [m for m in movs if m["date"] in dates_set and in_block(m["tod"][:2])]
    crit = [r for r in rows if round(r["sep"]) < limit]
    stats = []
    for d in sorted(dates_set):
        dm = [m for m in fm if m["date"] == d]; dr = [r for r in rows if r["dateRaw"] == d]
        wd = weekday(d)
        hc = Counter(m["tod"][:2] for m in dm)
        peak = max(hc.items(), key=lambda x: (x[1], -int(x[0]))) if hc else None
        stats.append({"date": d, "label": f"{d[2:4]}-{d[4:6]} {WD_SHORT[wd]}", "dateFmt": fmt_date(d), "wd": wd, "wdName": WD_LONG[wd],
                      "arr": sum(1 for m in dm if m["type"] == "ARR"), "dep": sum(1 for m in dm if m["type"] == "DEP"),
                      "total": len(dm), "pairs": len(dr), "crit": sum(1 for r in dr if round(r["sep"]) < limit),
                      "peakHour": peak[0] if peak else None, "peakN": peak[1] if peak else 0,
                      "companies": Counter(company(m["csn"]) for m in dm).most_common(10)})
    hs = hour_summary(fm)
    # callsigns comuns
    cs_days: dict[str, set] = defaultdict(set); cs_movs = Counter()
    for m in fm:
        cs_days[m["csn"]].add(m["date"]); cs_movs[m["csn"]] += 1
    common = sorted([{"csn": c, "count": len(ds), "days": sorted(ds), "movements": cs_movs[c], "company": company(c)}
                     for c, ds in cs_days.items() if len(ds) > 1], key=lambda x: (-x["count"], x["csn"]))
    # por dia da semana
    wd_agg: dict[int, dict] = {}
    for s in stats:
        e = wd_agg.setdefault(s["wd"], {"wd": s["wd"], "name": WD_LONG[s["wd"]], "days": 0, "mov": 0, "arr": 0, "dep": 0, "pairs": 0, "crit": 0, "critDep": 0, "dates": []})
        e["days"] += 1; e["mov"] += s["total"]; e["arr"] += s["arr"]; e["dep"] += s["dep"]; e["pairs"] += s["pairs"]; e["crit"] += s["crit"]
        e["critDep"] += sum(1 for r in crit if r["dateRaw"] == s["date"] and r["depCnt"]); e["dates"].append(s["dateFmt"])
    for e in wd_agg.values():
        e["avgMov"] = round(e["mov"] / e["days"], 1); e["avgCrit"] = round(e["crit"] / e["days"], 1)
        e["rate"] = round(e["crit"] / e["pairs"] * 100, 1) if e["pairs"] else 0
    wd_rows = [wd_agg[w] for w in [1, 2, 3, 4, 5, 6, 0] if w in wd_agg]
    # por dia e hora
    hour_out = []
    for d in sorted(dates_set):
        for h in range(24):
            hh = f"{h:02d}"
            if not in_block(hh): continue
            dm = [m for m in fm if m["date"] == d and m["tod"][:2] == hh]; dr = [r for r in rows if r["dateRaw"] == d and r["hour"] == hh]
            if dm or dr:
                hour_out.append({"date": d, "dateFmt": fmt_date(d), "wd": WD_SHORT[weekday(d)], "hour": hh, "arr": sum(1 for m in dm if m["type"] == "ARR"),
                                 "dep": sum(1 for m in dm if m["type"] == "DEP"), "total": len(dm), "pairs": len(dr),
                                 "crit": sum(1 for r in dr if round(r["sep"]) < limit)})
    comp = company_summary(fm, crit)[:10]
    kpis = {"days": len(dates_set), "movs": len(fm), "arr": sum(1 for m in fm if m["type"] == "ARR"), "dep": sum(1 for m in fm if m["type"] == "DEP"),
            "pairs": len(rows), "crit": len(crit), "critDep": sum(1 for r in crit if r["depCnt"]),
            "peakArr": hs["peakArr"], "peakDep": hs["peakDep"], "common": len(common)}
    ctx = {"limit": limit, "kpis": kpis, "stats": stats, "wd": wd_rows, "comp": comp, "common": common, "blocks": blocks, "hourOut": hour_out}
    return {"kpis": kpis, "stats": stats, "weekday": wd_rows, "common": common[:80], "hourTable": hour_out, "companies": comp,
            "narrative": daily_narrative(ctx), "limit": limit}


def daily_narrative(ctx: dict) -> dict:
    k, limit, stats = ctx["kpis"], ctx["limit"], ctx["stats"]
    paras, insights = [], []
    dias = ", ".join(s["dateFmt"] for s in stats)
    blocos = ", ".join(ctx["blocks"]) if ctx["blocks"] else "todos"
    paras.append(f"Este relatório analisa {k['days']} dia(s) seleccionado(s) ({dias}), considerando os blocos horários {blocos}. "
                 f"O limite de separação crítica aplicado é {limit} segundos entre chegadas consecutivas.")
    avg = k["movs"] / k["days"] if k["days"] else 0
    paras.append(f"No período foram registados {k['movs']} movimentos ({k['arr']} aterragens e {k['dep']} descolagens), "
                 f"o que corresponde a uma média de {avg:.1f} movimentos por dia analisado.")
    insights.append(f"{k['movs']} movimentos ARR+DEP no período")
    rate = round(k["crit"] / k["pairs"] * 1000) / 10 if k["pairs"] else 0
    s = f"Foram identificados {k['pairs']} pares precedente/seguidor. Destes, {k['crit']} ({rate}%) ficaram abaixo do limite de {limit}s"
    s += f", incluindo {k['critDep']} com descolagem intercalada (DEP)." if k["critDep"] else ", sem DEP intercalado relevante."
    paras.append(s)
    if rate >= 15: paras.append(f"A taxa de críticos ({rate}%) é elevada face ao volume analisado e merece atenção operacional, sobretudo nas horas e dias com maior concentração de ocorrências.")
    elif rate > 0: paras.append(f"A taxa global de críticos ({rate}%) situa-se num patamar moderado; convém cruzar com os dias e horas de pico para identificar padrões localizados.")
    else: paras.append(f"Não foram registados pares abaixo do limite de {limit}s no período e filtros seleccionados.")
    if stats:
        top = max(stats, key=lambda s: s["total"]); low = min(stats, key=lambda s: s["total"])
        paras.append(f"O dia de maior volume operacional foi {top['dateFmt']} ({top['wdName']}), com {top['total']} movimentos ({top['arr']} ARR / {top['dep']} DEP) e {top['crit']} pares críticos.")
        insights.append(f"Pico diário: {top['dateFmt']} · {top['total']} mov.")
        if low is not top:
            paras.append(f"O dia de menor volume foi {low['dateFmt']} ({low['total']} movimentos), útil como referência de carga operacional mínima no conjunto analisado.")
        tc = max(stats, key=lambda s: s["crit"])
        if tc["crit"]:
            paras.append(f"O dia com mais ocorrências críticas foi {tc['dateFmt']} ({tc['crit']} pares abaixo do limite, {tc['crit'] / tc['pairs'] * 100:.1f}% dos {tc['pairs']} pares desse dia).")
            insights.append(f"Mais críticos: {tc['dateFmt']} · {tc['crit']} pares")
    if k["peakArr"]: paras.append(f"As aterragens concentram-se tipicamente na hora {k['peakArr']['hour']}h ({k['peakArr']['n']}), indicando o período do dia com maior pressão na sequência de chegadas.")
    if k["peakDep"]: paras.append(f"As descolagens atingem o máximo à hora {k['peakDep']['hour']}h ({k['peakDep']['n']}), o que pode influenciar a intercalação ARR/DEP e a formação de sequências ADA/ADDA.")
    comp = ctx["comp"]
    if comp:
        c0 = comp[0]
        paras.append(f"A companhia com mais movimentos no período foi {c0['company']} ({c0['movements']} movimentos"
                     + (f", {c0['critical']} ocorrências críticas associadas" if c0["critical"] else "") + ").")
        if len(comp) > 1:
            paras.append("Seguem-se " + ", ".join(f"{c['company']} ({c['movements']})" for c in comp[1:4]) + " entre as operadoras mais activas.")
    wd = ctx["wd"]
    if len(wd) >= 2:
        m = max(wd, key=lambda e: e["avgMov"]); c = max(wd, key=lambda e: e["avgCrit"]); r = max(wd, key=lambda e: e["rate"])
        paras.append(f"Comparando dias da semana (médias por dia para comparar de forma justa), {m['name']} regista a maior média de movimentos ({m['avgMov']}/dia em {m['days']} dia(s) analisado(s)).")
        paras.append(f"{c['name']} apresenta a maior média de pares críticos ({c['avgCrit']}/dia), com taxa de {r['rate']}% em {r['name']} — útil para comparar, por exemplo, terças vs quartas ao longo do mês.")
        insights.append(f"Dia da semana mais crítico (média): {c['name']}")
    if k["common"]:
        paras.append(f"Foram encontrados {k['common']} callsign(s) comuns a mais do que um dos dias seleccionados, o que facilita a comparação de padrões horários ou de sequência entre datas equivalentes.")
    elif k["days"] > 1:
        paras.append("Não há callsigns repetidos entre os dias seleccionados, pelo que a comparação deve focar-se em indicadores agregados (volume, críticos, hora) e não em voos individuais recorrentes.")
    ho = [h for h in ctx["hourOut"] if h["crit"]]
    if ho:
        h = max(ho, key=lambda x: x["crit"])
        paras.append(f"A hora com mais pares críticos no conjunto analisado foi {h['hour']}h do dia {h['dateFmt']} ({h['wd']}) ({h['crit']} críticos em {h['pairs']} pares).")
    return {"paragraphs": paras, "insights": insights}
