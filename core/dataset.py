"""Excel à medida (Preferências → Construir relatório): uma linha por movimento com TODOS os campos
das quatro fontes (radar, NMIR, torre, OPDI) e os calculados; o utilizador escolhe colunas, filtros e contagens.

Campos: secção -> lista de (chave, rótulo, tipo, descrição). Tipos: txt, num, time (hora UTC), date, bool.
Ligação: radar↔torre pela ligação de db.ground_list (callsign+dia+hora); radar↔OPDI por Mode S ou callsign
(integrate._pair); NMIR por callsign+dia; torre↔OPDI por callsign+dia+hora (movimentos sem radar).
"""
from __future__ import annotations

import re
import time
from collections import Counter, defaultdict

from .filenames import date_label
from .geo import hhmmss, wtc_from_type
from . import integrate

FIELDS: dict[str, tuple[str, list[tuple[str, str, str, str]]]] = {
    "mov": ("Movimento (comum a todas as fontes)", [
        ("date", "Data", "date", "Dia do movimento"),
        ("csn", "Callsign", "txt", "Indicativo de chamada"),
        ("cls", "ARR/DEP", "txt", "ARR, DEP ou LVL (sobrevoo)"),
        ("src", "Fontes", "txt", "Letras das fontes que têm este movimento: R radar, N NMIR, T torre, O OPDI"),
        ("hour", "Hora (UTC)", "num", "Hora inteira do movimento (0–23), pela melhor fonte"),
        ("dow", "Dia da semana", "txt", "Seg … Dom"),
        ("t_mov", "Hora do movimento", "time", "ALDT/ATOT da torre, senão OPDI, senão radar"),
    ]),
    "calc": ("Calculados (melhor valor entre fontes)", [
        ("actype", "Tipo de aeronave", "txt", "Correção do utilizador > torre > NMIR > radar"),
        ("wtc", "WTC", "txt", "Esteira (L/M/H/J) do tipo escolhido"),
        ("adep", "ADEP", "txt", "Torre > NMIR > OPDI"),
        ("ades", "ADES", "txt", "Torre > NMIR > OPDI"),
        ("other_apt", "Outro aeroporto", "txt", "ADES numa partida, ADEP numa chegada"),
        ("operator", "Operador", "txt", "Operador (torre AO > NMIR)"),
        ("rwy", "Pista", "txt", "Pista (torre > OPDI)"),
        ("rot_s", "ROT (s)", "num", "Ocupação de pista: torre (ARR: RWY_VAC−ALDT; DEP: ATOT−RWY_ENT), senão OPDI (só ARR)"),
        ("taxi_s", "Taxi (s)", "num", "Torre: DEP ATOT−AOBT; ARR AIBT−RWY_VAC"),
        ("ga", "Borrego", "txt", "torre+radar / só torre / só radar / —"),
        ("otp_dev", "Desvio partida (min)", "num", "FSA/DEP − (CTOT ou ETOT); sem FSA/DEP: ATOT − (CTOT ou ETOT)"),
        ("otp_ok", "Pontual (≤15 min)", "bool", "Desvio de partida até 15 min"),
        ("slot", "Conformidade slot", "txt", "Within / Earlier / Later (NMIR, só voos regulados)"),
        ("atfm_delay", "Atraso ATFM (min)", "num", "NMIR > torre"),
    ]),
    "fast": ("Final e FAST (radar: aproximação, sequência AA/ADA/ADDA)", [
        ("f_rwy", "Final: pista", "txt", "Pista detetada pela análise da final"),
        ("f_t_faf", "Final: hora na FAF", "time", "7 NM da soleira"), ("f_t_thr", "Final: hora na soleira", "time", ""),
        ("f_ias_faf", "Final: IAS na FAF (kt)", "num", ""), ("f_ias4", "Final: IAS a 4 NM (kt)", "num", ""), ("f_ias_thr", "Final: IAS na soleira (kt)", "num", ""),
        ("f_alt_faf", "Final: alt. na FAF (ft)", "num", ""), ("f_alt_thr", "Final: alt. na soleira (ft)", "num", ""),
        ("f_dur", "Final: FAF→soleira (s)", "num", ""), ("f_track", "Final: distância voada (NM)", "num", ""),
        ("f_stab", "Final: estabilizada", "bool", ""), ("f_cdo", "Final: CDO", "bool", "Sem patamares na final"), ("f_level_offs", "Final: n.º patamares", "num", ""),
        ("f_seq", "FAST: sequência", "txt", "Chegada como seguinte do par: AA (sem DEP entre as duas chegadas), ADA (1 DEP), ADDA (2 DEP), AD…A (3+)"),
        ("f_sep_s", "FAST: separação à chegada anterior (s)", "num", "Entre soleiras, mesma pista, ≤ 600 s"),
        ("f_sep_nm", "FAST: separação à chegada anterior (NM)", "num", "A 140 kt"),
        ("f_lead", "FAST: chegada anterior", "txt", "Callsign da chegada que precede"),
        ("f_dep_cnt", "FAST: n.º DEP intercalados", "num", "Descolagens entre a chegada anterior e esta"),
        ("f_deps", "FAST: DEP intercalados", "txt", "Callsigns das descolagens intercaladas"),
        ("f_first_dep", "FAST: 1.ª DEP intercalada", "txt", ""), ("f_b_sec", "FAST: soleira − 1.ª DEP (s)", "num", "Tempo entre a 1.ª descolagem intercalada e a soleira desta chegada"),
        ("f_b_nm", "FAST: soleira − 1.ª DEP (NM)", "num", ""),
        ("f_next", "FAST: chegada seguinte", "txt", "Callsign da chegada que se segue (quando esta é a primeira do par)"),
        ("f_sep_next_s", "FAST: separação à chegada seguinte (s)", "num", ""),
        ("f_in_pair", "FAST: DEP entre as chegadas", "txt", "Para uma partida: as duas chegadas entre as quais descolou (anterior → seguinte)"),
        ("f_in_pair_seq", "FAST: sequência do par (DEP)", "txt", "Para uma partida: a sequência do par onde está intercalada"),
    ]),
    "radar": ("Radar (CNS)", [
        ("r_t_first", "Radar: 1.º plot", "time", "Hora do primeiro plot"),
        ("r_t_last", "Radar: último plot", "time", "Hora do último plot"),
        ("r_n", "Radar: n.º plots", "num", "Plots do movimento"),
        ("r_dur", "Radar: duração (s)", "num", "Último − primeiro plot"),
        ("r_alt_first", "Radar: alt. 1.º plot (ft)", "num", ""),
        ("r_alt_last", "Radar: alt. último plot (ft)", "num", ""),
        ("r_alt_min", "Radar: alt. mín. (ft)", "num", ""),
        ("r_alt_max", "Radar: alt. máx. (ft)", "num", ""),
        ("r_actype", "Radar: tipo", "txt", "Tipo atribuído ao movimento (NMIR/herança/prefixo)"),
        ("r_wtc", "Radar: WTC", "txt", ""),
        ("r_modes", "Radar: Mode S", "txt", "Endereço ICAO24"),
        ("r_blocks", "Radar: blocos", "txt", "Blocos horários dos ficheiros"),
        ("r_ga", "Radar: n.º borregos", "num", "Borregos detetados no perfil"),
        ("r_ga_t", "Radar: hora do borrego", "time", ""),
    ]),
    "nmir": ("NMIR (Network Manager)", [
        ("n_actype", "NMIR: tipo", "txt", ""), ("n_wtc", "NMIR: WTC", "txt", ""),
        ("n_adep", "NMIR: ADEP", "txt", ""), ("n_ades", "NMIR: ADES", "txt", ""),
        ("n_etot", "NMIR: ETOT", "time", "Descolagem estimada"), ("n_ctot", "NMIR: CTOT", "time", "Slot ATFM"),
        ("n_atot", "NMIR: ATOT", "time", "Descolagem real"), ("n_eta", "NMIR: ETA", "time", ""), ("n_ata", "NMIR: ATA", "time", ""),
        ("n_fsa_dep", "NMIR: FSA/DEP", "time", "First System Activation"), ("n_fsa_dev", "NMIR: FSA/DEP−ETOT (min)", "num", ""),
        ("n_lobt", "NMIR: LOBT", "time", "Off-block previsto"), ("n_atfm_delay", "NMIR: atraso ATFM (min)", "num", ""),
        ("n_mp_regulation", "NMIR: regulação", "txt", ""), ("n_dep_window", "NMIR: janela de partida", "txt", ""),
        ("n_dep_conformance", "NMIR: conformidade", "txt", "Within / Earlier / Later"),
        ("n_flttyp", "NMIR: FLTTYP", "txt", ""), ("n_diverted", "NMIR: desviado", "txt", ""),
        ("n_operator", "NMIR: operador", "txt", ""), ("n_flt_uid", "NMIR: FLT_UID", "txt", ""),
        ("n_src", "NMIR: origem do tipo", "txt", "nmir (mesmo dia) / fallback (outro dia) / prefix / —"),
    ]),
    "torre": ("Torre (A-SMGCS Lisboa)", [
        ("t_rwy", "Torre: pista", "txt", ""), ("t_actype", "Torre: tipo", "txt", ""), ("t_reg", "Torre: matrícula", "txt", ""),
        ("t_ao", "Torre: operador", "txt", ""), ("t_wtc", "Torre: WTC", "txt", ""),
        ("t_adep", "Torre: ADEP", "txt", ""), ("t_ades", "Torre: ADES", "txt", ""),
        ("t_sid", "Torre: SID", "txt", ""), ("t_star", "Torre: STAR", "txt", ""),
        ("t_stand_d", "Torre: stand partida", "txt", ""), ("t_stand_a", "Torre: stand chegada", "txt", ""), ("t_apron", "Torre: plataforma", "txt", ""),
        ("t_taxi_out", "Torre: rota taxi-out", "txt", ""), ("t_taxi_in", "Torre: rota taxi-in", "txt", ""),
        ("t_hp", "Torre: holding point", "txt", ""), ("t_ep", "Torre: ponto de entrada", "txt", ""),
        ("t_aobt", "Torre: AOBT", "time", "Off-block"), ("t_hp_time", "Torre: hora no HP", "time", ""),
        ("t_rwy_ent", "Torre: RWY_ENT", "time", "Entrada na pista"), ("t_atot", "Torre: ATOT", "time", "Descolagem"),
        ("t_aldt", "Torre: ALDT", "time", "Aterragem"), ("t_rwy_vac", "Torre: RWY_VAC", "time", "Pista livre"),
        ("t_aibt", "Torre: AIBT", "time", "In-block"), ("t_ctot", "Torre: CTOT", "time", ""),
        ("t_spd_vac", "Torre: vel. ao livrar (kt)", "num", ""), ("t_ga", "Torre: GA", "bool", "Go-around"), ("t_rto", "Torre: RTO", "bool", "Descolagem rejeitada"),
        ("t_atfm_delay", "Torre: atraso ATFM (min)", "num", ""), ("t_regulation", "Torre: regulação", "txt", ""),
        ("t_rot_s", "Torre: ROT (s)", "num", ""), ("t_taxi_s", "Torre: taxi (s)", "num", ""),
    ]),
    "opdi": ("OPDI (EUROCONTROL / ADS-B)", [
        ("o_id", "OPDI: id do voo", "txt", ""), ("o_icao24", "OPDI: ICAO24", "txt", ""), ("o_reg", "OPDI: matrícula", "txt", ""),
        ("o_typecode", "OPDI: tipo", "txt", ""), ("o_model", "OPDI: modelo", "txt", ""),
        ("o_adep", "OPDI: ADEP", "txt", ""), ("o_ades", "OPDI: ADES", "txt", ""),
        ("o_t_first", "OPDI: 1.º visto", "time", ""), ("o_t_last", "OPDI: último visto", "time", ""),
        ("o_t_rwy_in", "OPDI: entrada na pista", "time", ""), ("o_t_rwy_out", "OPDI: saída da pista", "time", ""),
        ("o_t_takeoff", "OPDI: descolagem", "time", ""), ("o_t_landing", "OPDI: aterragem", "time", ""),
        ("o_t_toc", "OPDI: TOC", "time", "Topo de subida"), ("o_t_tod", "OPDI: TOD", "time", "Topo de descida"),
        ("o_t_fx50", "OPDI: 1.ª passagem FL50", "time", ""), ("o_t_fx100", "OPDI: 1.ª passagem FL100", "time", ""),
        ("o_t_lx100", "OPDI: última passagem FL100", "time", ""), ("o_t_lx50", "OPDI: última passagem FL50", "time", ""),
        ("o_n_levels_low", "OPDI: patamares < FL100", "num", "Nivelamentos abaixo de FL100 (CDO)"),
        ("o_twy", "OPDI: taxiways", "txt", ""), ("o_rwy_ref", "OPDI: pista", "txt", ""),
        ("o_t_park_in", "OPDI: entrada no stand", "time", ""), ("o_t_park_out", "OPDI: saída do stand", "time", ""),
        ("o_rot", "OPDI: ROT (s)", "num", "Só chegadas"),
    ]),
}
FIELD_TYPE = {k: t for _, lst in FIELDS.values() for k, _, t, _ in lst}
FIELD_LABEL = {k: l for _, lst in FIELDS.values() for k, l, _, _ in lst}
OPS = {"=": "igual a", "!=": "diferente de", "in": "um de (a, b, c)", "contains": "contém", "starts": "começa por",
       ">": "maior que", ">=": "maior ou igual", "<": "menor que", "<=": "menor ou igual", "empty": "vazio", "notempty": "preenchido"}
DOW = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def catalog() -> dict:
    return {"sections": [{"key": k, "title": t, "fields": [{"key": f, "label": l, "type": ty, "descr": d} for f, l, ty, d in lst]} for k, (t, lst) in FIELDS.items()],
            "ops": OPS}


def _sod(t):
    return None if t is None else (t % 86400 if t > 86400 else t)


def build_rows(db, airport: str, dates: list[str]) -> list[dict]:
    """Uma linha por movimento (união radar ∪ torre ∪ OPDI) com todos os campos."""
    flights = [f for f in db.flights_list(airport, dates, [], "", "")]
    ground = db.ground_list(airport, dates)
    gextra = {g["gid"]: g for g in db.ground_get([g["gid"] for g in ground])} if ground else {}
    opdi = db.opdi_flights(airport, dates)
    nmir = {}
    for r in db.con.execute('SELECT csn, date, actype, wtc, adep, ades, etot, ctot, atot, eta, ata, atfm_delay, fsa_dep, fsa_dev, lobt, '
                            'mp_regulation, dep_window, dep_conformance, flttyp, diverted, "operator", flt_uid FROM nmir WHERE date IN (SELECT unnest(?::VARCHAR[]))', [dates]).fetchall():
        nmir[(r[0], r[1])] = dict(zip(("actype", "wtc", "adep", "ades", "etot", "ctot", "atot", "eta", "ata", "atfm_delay", "fsa_dep", "fsa_dev", "lobt",
                                       "mp_regulation", "dep_window", "dep_conformance", "flttyp", "diverted", "operator", "flt_uid"), r[2:]))
    corr = db.corrections(dates); overrides = db.type_overrides()
    from .analysis.ops import nmir_lookup
    from .analysis import final as finalmod, fast as fastmod
    # Final + FAST (só radar): aproximações e pares de chegadas consecutivas na mesma pista
    arrs = [f for f in flights if f["cls"] in ("arr", "dep")]
    try:
        final = finalmod.run_final(db, arrs, airport, "BOTH", 7.0, 2.0, 1000.0)
        pairs = fastmod.build_pairs(final, fastmod.dep_events(arrs))
    except Exception:  # noqa: BLE001 — sem análise da final não se perde o resto
        final, pairs = [], []
    fin_by = {r["flight_id"]: r for r in final}
    trail_by, lead_by, dep_in = {}, {}, {}
    for p in pairs:
        trail_by[p["trail"]["flight_id"]] = p; lead_by[p["lead"]["flight_id"]] = p
        for d in p["depsIn"]:
            dep_in.setdefault((d["csn"], p["lead"]["_dateRaw"]), p)
    for g in ground:
        g["cls"] = "dep" if g["mt"] == "DEPARTURE" else "arr"
    # OPDI ↔ radar: primeiro por Mode S + dia + classe, depois por callsign (integrate._pair)
    t_r = lambda f: f["t_first"] if f["cls"] == "dep" else f["t_last"]
    t_o = lambda o: (o.get("t_rwy_out") or o.get("t_takeoff") or o.get("t_first")) if o["cls"] == "dep" else (o.get("t_rwy_in") or o.get("t_landing") or o.get("t_last"))
    by_modes = defaultdict(list)
    for f in flights:
        if f.get("modes"): by_modes[(f["modes"].lower(), f["date"], f["cls"])].append(f)
    o_by_fid, used = {}, set()
    rest = []
    for o in opdi:
        cands = [f for f in by_modes.get(((o.get("icao24") or "").lower(), o["date"], o["cls"]), []) if f["flight_id"] not in used]
        if cands and t_o(o) is not None:
            f = min(cands, key=lambda f: abs(integrate._dt(t_o(o), t_r(f))))
            if abs(integrate._dt(t_o(o), t_r(f))) <= integrate.MATCH_WINDOW_S:
                o_by_fid[f["flight_id"]] = o; used.add(f["flight_id"]); continue
        rest.append(o)
    m = integrate._pair([f for f in flights if f["flight_id"] not in used], rest, t_r, t_o)
    for o in rest:
        fid = m.get(id(o))
        if fid: o_by_fid[fid] = o
    g_by_fid = {g["flight_id"]: g for g in ground if g.get("flight_id")}
    seen_o = {o["flight_id"] for o in o_by_fid.values()}
    go = integrate._pair([{"flight_id": g["gid"], "csn": g["csn"], "date": g["date"], "cls": g["cls"], "t_first": g.get("atot"), "t_last": g.get("aldt")} for g in ground if not g.get("flight_id")],
                         [o for o in opdi if o["flight_id"] not in seen_o], t_r, t_o)
    o_by_gid = {gid: o for o, gid in ((o, go.get(id(o))) for o in opdi) if gid}

    def new(csn, date, cls):
        r = {k: None for k in FIELD_TYPE}
        r.update(csn=csn, date=date, cls=cls, src="")
        return r

    def put_radar(r, f):
        r["src"] += "R"
        r["r_t_first"], r["r_t_last"], r["r_n"] = f["t_first"], f["t_last"], f["n"]
        r["r_dur"] = round(f["t_last"] - f["t_first"]) if f["t_last"] is not None and f["t_first"] is not None else None
        for k in ("alt_first", "alt_last", "alt_min", "alt_max", "actype", "wtc", "modes", "blocks", "ga", "ga_t"):
            r["r_" + k] = f.get(k)

    def put_fast(r, f):
        x = fin_by.get(f["flight_id"])
        if x:
            r["f_rwy"], r["f_t_faf"], r["f_t_thr"] = x["rwy"], x["epochFAF"], x["epochTHR"]
            r["f_ias_faf"], r["f_ias4"], r["f_ias_thr"], r["f_alt_faf"], r["f_alt_thr"] = x["iasFAF"], x["ias4"], x["iasTHR"], x["altFAF"], x["altTHR"]
            r["f_dur"], r["f_track"], r["f_stab"], r["f_cdo"], r["f_level_offs"] = x["durS"], x["trackNM"], x["stab"], x["cdo"], x["cdoLevelOffs"]
        p = trail_by.get(f["flight_id"])
        if p:
            r["f_seq"], r["f_sep_s"], r["f_sep_nm"], r["f_lead"], r["f_dep_cnt"] = p["seq"], p["sep"], p["sepNm"], p["lead"]["csn"], p["depCnt"]
            r["f_deps"] = " ".join(d["csn"] for d in p["depsIn"]) or None
            r["f_first_dep"], r["f_b_sec"], r["f_b_nm"] = p["firstDep"], p["bSecAtDep"], p["bNmAtDep"]
        p = lead_by.get(f["flight_id"])
        if p:
            r["f_next"], r["f_sep_next_s"] = p["trail"]["csn"], p["sep"]
        if f["cls"] == "dep":
            p = dep_in.get((f["csn"], f["date"]))
            if p:
                r["f_in_pair"] = f'{p["lead"]["csn"]} → {p["trail"]["csn"]}'; r["f_in_pair_seq"] = p["seq"]

    def put_nmir(r):
        n = nmir.get((r["csn"], r["date"]))
        if n:
            r["src"] += "N"
            for k, v in n.items(): r["n_" + k] = v
            r["n_src"] = "nmir"
        else:
            lk = nmir_lookup(db, r["csn"], r["date"])
            if lk.get("type") not in (None, "?"):
                r["n_actype"], r["n_wtc"], r["n_src"] = lk["type"], lk.get("wtc"), lk["source"]

    def put_ground(r, g):
        r["src"] += "T"; e = gextra.get(g["gid"], {})
        for k in ("rwy", "actype", "reg", "ao", "wtc", "adep", "ades", "sid", "star", "stand_d", "stand_a", "taxi_out", "taxi_in", "hp", "ep",
                  "aobt", "hp_time", "rwy_ent", "atot", "aldt", "rwy_vac", "aibt", "ctot", "spd_vac", "ga", "rto", "atfm_delay", "rot_s", "taxi_s"):
            r["t_" + k] = g.get(k)
        r["t_apron"], r["t_regulation"] = e.get("apron"), e.get("regulation")

    def put_opdi(r, o):
        r["src"] += "O"
        r["o_id"], r["o_icao24"], r["o_reg"], r["o_typecode"], r["o_model"] = o["flight_id"], o.get("icao24"), o.get("reg"), o.get("typecode"), o.get("model")
        r["o_adep"], r["o_ades"], r["o_twy"], r["o_rwy_ref"], r["o_n_levels_low"] = o.get("adep"), o.get("ades"), o.get("twy"), o.get("rwy_ref"), o.get("n_levels_low")
        for k in ("t_first", "t_last", "t_rwy_in", "t_rwy_out", "t_takeoff", "t_landing", "t_toc", "t_tod", "t_fx50", "t_fx100", "t_lx100", "t_lx50", "t_park_in", "t_park_out"):
            r["o_" + k] = o.get(k)
        if o["cls"] == "arr" and o.get("t_rwy_in") and o.get("t_rwy_out") and 0 < o["t_rwy_out"] - o["t_rwy_in"] < 600:
            r["o_rot"] = o["t_rwy_out"] - o["t_rwy_in"]

    def finish(r):
        c = corr.get((r["csn"], r["date"], r["cls"])) or {}
        r["actype"] = c.get("actype") or r["t_actype"] or r["n_actype"] or r["r_actype"]
        r["wtc"] = overrides.get(r["actype"]) or c.get("wtc") or (r["t_wtc"] if r["t_actype"] == r["actype"] else None) or wtc_from_type(r["actype"]) or r["r_wtc"]
        r["adep"] = r["t_adep"] or r["n_adep"] or r["o_adep"]
        r["ades"] = r["t_ades"] or r["n_ades"] or r["o_ades"]
        if c.get("apt"):
            if r["cls"] == "dep": r["ades"] = c["apt"]
            else: r["adep"] = c["apt"]
        r["other_apt"] = r["ades"] if r["cls"] == "dep" else r["adep"]
        r["operator"] = r["t_ao"] or r["n_operator"]
        r["rwy"] = r["t_rwy"] or r["o_rwy_ref"]
        r["rot_s"] = r["t_rot_s"] if r["t_rot_s"] is not None else r["o_rot"]
        r["taxi_s"] = r["t_taxi_s"]
        r["ga"] = ("torre+radar" if r["t_ga"] and r["r_ga"] else "só torre" if r["t_ga"] else "só radar" if r["r_ga"] else None)
        ref = r["n_ctot"] or r["n_etot"]
        if r["n_fsa_dev"] is not None: r["otp_dev"] = round(r["n_fsa_dev"], 1)
        elif r["n_fsa_dep"] and ref: r["otp_dev"] = round((r["n_fsa_dep"] - ref) / 60, 1)
        elif r["n_atot"] and ref: r["otp_dev"] = round((r["n_atot"] - ref) / 60, 1)
        r["otp_ok"] = (r["otp_dev"] <= 15) if r["otp_dev"] is not None else None
        r["slot"] = r["n_dep_conformance"]
        r["atfm_delay"] = r["n_atfm_delay"] if r["n_atfm_delay"] is not None else r["t_atfm_delay"]
        tm = (r["t_atot"] if r["cls"] == "dep" else r["t_aldt"]) or \
             ((r["o_t_rwy_out"] or r["o_t_takeoff"] or r["o_t_first"]) if r["cls"] == "dep" else (r["o_t_rwy_in"] or r["o_t_landing"] or r["o_t_last"])) or \
             (r["r_t_first"] if r["cls"] == "dep" else r["r_t_last"]) or r["r_t_first"]
        r["t_mov"] = tm
        r["hour"] = int(_sod(tm) // 3600) if tm is not None else None
        try:
            y, mo, d = int("20" + r["date"][:2]), int(r["date"][2:4]), int(r["date"][4:6])
            import datetime as _d; r["dow"] = DOW[_d.date(y, mo, d).weekday()]
        except Exception:  # noqa: BLE001
            r["dow"] = None

    rows = []
    for f in flights:
        r = new(f["csn"], f["date"], f["cls"]); put_radar(r, f); put_fast(r, f); put_nmir(r)
        g = g_by_fid.get(f["flight_id"])
        if g: put_ground(r, g)
        o = o_by_fid.get(f["flight_id"]) or (o_by_gid.get(g["gid"]) if g else None)
        if o: put_opdi(r, o)
        finish(r); rows.append(r)
    for g in ground:
        if g.get("flight_id") in g_by_fid: continue
        r = new(g["csn"], g["date"], g["cls"]); put_nmir(r); put_ground(r, g)
        o = o_by_gid.get(g["gid"])
        if o: put_opdi(r, o)
        finish(r); rows.append(r)
    done_o = {r["o_id"] for r in rows if r["o_id"]}
    for o in opdi:
        if o["flight_id"] in done_o: continue
        r = new(integrate._norm_csn(o.get("csn")), o["date"], o["cls"]); put_nmir(r); put_opdi(r, o); finish(r); rows.append(r)
    rows.sort(key=lambda r: (r["date"], _sod(r["t_mov"]) or 0))
    return rows


# ------------------------------------------------------------------ filtros
def _parse_val(ty: str, v: str):
    v = (v or "").strip()
    if ty == "time":
        m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", v)
        if m: return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3) or 0)
    if ty in ("num", "time"):
        try: return float(v.replace(",", "."))
        except ValueError: return None
    if ty == "bool":
        return v.lower() in ("1", "sim", "true", "s", "x", "✓")
    return v.upper()


def _cell(ty: str, v):
    if v is None: return None
    if ty == "time": return _sod(v)
    if ty == "bool": return bool(v)
    if ty == "num": return v
    if ty == "date": return v
    return str(v).upper()


def match(row: dict, flt: dict) -> bool:
    k, op, val = flt.get("field"), flt.get("op", "="), flt.get("value", "")
    ty = FIELD_TYPE.get(k, "txt"); v = _cell(ty, row.get(k))
    if op == "empty": return v is None or v == ""
    if op == "notempty": return v is not None and v != ""
    if ty == "date":
        d = (val or "").strip(); d = d.replace("-", "")[2:] if len(d) == 10 else d
        return {"=": v == d, "!=": v != d, ">": v > d, ">=": v >= d, "<": v < d, "<=": v <= d, "contains": d in (v or ""), "starts": (v or "").startswith(d),
                "in": v in [x.strip().replace("-", "")[2:] if len(x.strip()) == 10 else x.strip() for x in val.split(",")]}.get(op, False)
    if op == "in":
        vals = [_parse_val(ty, x) for x in val.split(",") if x.strip()]
        return v in vals
    p = _parse_val(ty, val)
    if v is None: return op == "!="
    if ty in ("num", "time"):
        if p is None: return False
        return {"=": v == p, "!=": v != p, ">": v > p, ">=": v >= p, "<": v < p, "<=": v <= p}.get(op, False)
    if ty == "bool":
        return (v == p) if op == "=" else (v != p)
    s = str(v)
    return {"=": s == p, "!=": s != p, "contains": p in s, "starts": s.startswith(p), ">": s > p, "<": s < p, ">=": s >= p, "<=": s <= p}.get(op, False)


def apply_filters(rows: list[dict], filters: list[dict]) -> list[dict]:
    flts = [f for f in (filters or []) if f.get("field") in FIELD_TYPE]
    return [r for r in rows if all(match(r, f) for f in flts)]


# ------------------------------------------------------------------ Excel
def _fmt(ty: str, v):
    if v is None: return None
    if v in ("arr", "dep", "lvl"): return v.upper()
    if ty == "time": return hhmmss(_sod(v))
    if ty == "date": return date_label(v)
    if ty == "bool": return "sim" if v else "não"
    if ty == "num" and isinstance(v, float): return round(v, 1)
    return v


def sheets(rows: list[dict], fields: list[str], filters: list[dict], groups: list[str], airport: str, dates: list[str], all_n: int) -> list:
    fields = [f for f in fields if f in FIELD_TYPE] or ["date", "csn", "cls", "src"]
    out = [("Dados", [FIELD_LABEL[f] for f in fields], [[_fmt(FIELD_TYPE[f], r.get(f)) for f in fields] for r in rows])]
    # Resumo
    n_arr = sum(1 for r in rows if r["cls"] == "arr"); n_dep = sum(1 for r in rows if r["cls"] == "dep"); n_lvl = len(rows) - n_arr - n_dep
    res = [["Movimentos (após filtros)", len(rows)], ["Chegadas (ARR)", n_arr], ["Partidas (DEP)", n_dep], ["Sobrevoos (LVL)", n_lvl],
           ["Movimentos no período (sem filtros)", all_n], ["Dias", len(dates)], ["Média por dia", round(len(rows) / len(dates), 1) if dates else 0]]
    for lab, key in (("Com radar", "R"), ("Com NMIR", "N"), ("Com torre", "T"), ("Com OPDI", "O")):
        res.append([lab, sum(1 for r in rows if key in r["src"])])
    res.append(["Borregos (torre+radar / só torre / só radar)", f"{sum(1 for r in rows if r['ga']=='torre+radar')} / {sum(1 for r in rows if r['ga']=='só torre')} / {sum(1 for r in rows if r['ga']=='só radar')}"])
    seqs = Counter(r["f_seq"] for r in rows if r.get("f_seq"))
    if seqs: res.append(["Pares de chegadas FAST: AA / ADA / ADDA / AD…A", " / ".join(str(seqs.get(k, 0)) for k in ("AA", "ADA", "ADDA", "AD…A"))])
    rots = [r["rot_s"] for r in rows if r["rot_s"] is not None]
    if rots: res.append(["ROT médio (s) / n", f"{sum(rots)/len(rots):.0f} / {len(rots)}"])
    otp = [r["otp_ok"] for r in rows if r["otp_ok"] is not None]
    if otp: res.append(["Pontualidade ≤15 min", f"{100*sum(otp)/len(otp):.1f}% ({sum(otp)}/{len(otp)})"])
    out.append(("Resumo", ["Indicador", "Valor"], res))
    # Por dia
    byd = defaultdict(lambda: [0, 0, 0])
    for r in rows: byd[r["date"]][0 if r["cls"] == "arr" else 1 if r["cls"] == "dep" else 2] += 1
    out.append(("Por dia", ["Data", "Dia da semana", "ARR", "DEP", "LVL", "Total"],
                [[date_label(d), DOW[__import__("datetime").date(int("20" + d[:2]), int(d[2:4]), int(d[4:6])).weekday()], *v, sum(v)] for d, v in sorted(byd.items())]))
    # Contagens pedidas
    for gk in [g for g in (groups or []) if g in FIELD_TYPE]:
        ty = FIELD_TYPE[gk]; cnt = defaultdict(lambda: [0, 0, 0])
        for r in rows:
            key = _fmt(ty, r.get(gk)); key = "(vazio)" if key is None else key
            cnt[key][0 if r["cls"] == "arr" else 1 if r["cls"] == "dep" else 2] += 1
        lines = sorted(cnt.items(), key=lambda kv: -sum(kv[1]))
        out.append((re.sub(r"[\[\]:*?/\\]", " ", f"Por {FIELD_LABEL[gk]}")[:31], [FIELD_LABEL[gk], "ARR", "DEP", "LVL", "Total", "%"],
                    [[k, *v, sum(v), round(100 * sum(v) / len(rows), 1) if rows else 0] for k, v in lines]))
    # Parâmetros
    par = [["Aeroporto", airport], ["Período", f"{date_label(dates[0])} → {date_label(dates[-1])}" if dates else "—"], ["Dias com dados", len(dates)],
           ["Gerado em", time.strftime("%Y-%m-%d %H:%M")], ["Colunas", ", ".join(FIELD_LABEL[f] for f in fields)]]
    for f in (filters or []):
        if f.get("field") in FIELD_TYPE:
            par.append(["Filtro", f"{FIELD_LABEL[f['field']]} {OPS.get(f.get('op', '='), f.get('op'))} {f.get('value', '')}".strip()])
    for g in (groups or []):
        if g in FIELD_TYPE: par.append(["Contagem por", FIELD_LABEL[g]])
    out.append(("Parâmetros", ["Parâmetro", "Valor"], par))
    return out
