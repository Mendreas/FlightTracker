"""Cruzamento das fontes: radar (CNS), NMIR, ficheiro da torre (A-SMGCS / CPPM) e OPDI.
Um registo por movimento, com o que cada fonte diz e sinalização das discrepâncias."""
from __future__ import annotations

import re
from collections import defaultdict

from core.geo import wtc_from_type

MATCH_WINDOW_S = 20 * 60     # janela para emparelhar movimentos da mesma matrícula/callsign no mesmo dia


def _norm_csn(c: str | None) -> str:
    return re.sub(r"\s+", "", (c or "").upper())


def _sod(t):
    """Segundos do dia: o radar já vem assim; a torre e o OPDI vêm em epoch (UTC)."""
    return None if t is None else (t % 86400 if t > 86400 else t)


def _dt(a, b):
    """Diferença a − b em segundos do dia, com volta à meia-noite (−43200 … 43200)."""
    d = (_sod(a) - _sod(b) + 43200) % 86400 - 43200
    return d


def _pair(radar: list[dict], others: list[dict], t_radar, t_other) -> dict:
    """Emparelha cada registo de 'others' com o movimento radar mais próximo no tempo (csn+data+classe), 1-para-1."""
    by_key = defaultdict(list)
    for f in radar:
        by_key[(_norm_csn(f["csn"]), f["date"], f["cls"])].append(f)
    used = set(); out = {}
    cands = []
    for o in others:
        key = (_norm_csn(o.get("csn")), o.get("date"), o.get("cls"))
        to = t_other(o)
        for f in by_key.get(key, []):
            tr = t_radar(f)
            if to is None or tr is None:
                dt = 10 ** 9
            else:
                dt = abs(_dt(to, tr))
            if dt <= MATCH_WINDOW_S or dt == 10 ** 9:
                cands.append((dt, id(o), o, f))
    for dt, _, o, f in sorted(cands, key=lambda x: x[0]):
        if id(o) in out or f["flight_id"] in used:
            continue
        out[id(o)] = f["flight_id"]; used.add(f["flight_id"])
    return out


def crosscheck(airport: str, flights: list[dict], ground: list[dict], opdi: list[dict], nmir_lookup, corrections: dict | None = None, type_overrides: dict | None = None) -> dict:
    """flights: movimentos radar (do filtro, aeroporto activo); ground: registos da torre; opdi: voos OPDI;
    nmir_lookup(csn, date) -> dict(type, wtc, adep, ades, source)."""
    flights = [f for f in flights if f["cls"] in ("arr", "dep")]
    for g in ground:
        g["cls"] = "dep" if g["mt"] == "DEPARTURE" else "arr"
    g_map = _pair(flights, ground, lambda f: f["t_first"] if f["cls"] == "dep" else f["t_last"],
                  lambda g: g.get("atot") if g["cls"] == "dep" else g.get("aldt"))
    o_map = _pair(flights, opdi, lambda f: f["t_first"] if f["cls"] == "dep" else f["t_last"],
                  lambda o: (o.get("t_rwy_out") or o.get("t_takeoff") or o.get("t_first")) if o["cls"] == "dep" else (o.get("t_rwy_in") or o.get("t_last")))
    g_by_fid = {fid: g for g, fid in ((g, g_map.get(id(g))) for g in ground) if fid}
    o_by_fid = {fid: o for o, fid in ((o, o_map.get(id(o))) for o in opdi) if fid}
    # torre ↔ OPDI directamente (para movimentos sem radar)
    go_map = _pair([{"flight_id": g["gid"], "csn": g["csn"], "date": g["date"], "cls": g["cls"],
                     "t_first": g.get("atot"), "t_last": g.get("aldt")} for g in ground], opdi,
                   lambda f: f["t_first"] if f["cls"] == "dep" else f["t_last"],
                   lambda o: (o.get("t_rwy_out") or o.get("t_takeoff") or o.get("t_first")) if o["cls"] == "dep" else (o.get("t_rwy_in") or o.get("t_last")))
    o_by_gid = {gid: o for o, gid in ((o, go_map.get(id(o))) for o in opdi) if gid}

    rows = []
    def base(csn, date, cls):
        return {"csn": csn, "date": date, "cls": cls, "src": "", "flags": [],
                "flight_id": None, "r_t_first": None, "r_t_last": None, "r_n": None, "r_alt_max": None, "r_actype": None,
                "n_type": None, "n_wtc": None, "n_adep": None, "n_ades": None, "n_src": None,
                "gid": None, "t_type": None, "t_wtc": None, "t_reg": None, "t_ao": None, "t_rwy": None, "t_stand": None, "t_apt": None,
                "t_aobt": None, "t_rwy_ent": None, "t_atot": None, "t_aldt": None, "t_rwy_vac": None, "t_aibt": None, "t_rot": None, "t_taxi": None, "t_ga": None,
                "o_id": None, "o_icao24": None, "o_reg": None, "o_type": None, "o_model": None, "o_adep": None, "o_ades": None,
                "o_rwy_in": None, "o_rwy_out": None, "o_rot": None, "o_tod": None, "o_toc": None, "o_lx100": None, "o_lx50": None, "o_fx50": None, "o_fx100": None, "o_levels_low": None,
                "dt_radar_torre": None, "dt_opdi_torre": None, "d_rot": None}

    def fill_nmir(r):
        n = nmir_lookup(r["csn"], r["date"]) if nmir_lookup else None
        if n and n.get("type") not in (None, "?"):
            r["n_type"], r["n_wtc"], r["n_adep"], r["n_ades"], r["n_src"] = n.get("type"), n.get("wtc"), n.get("adep"), n.get("ades"), n.get("source")
            r["src"] += "N"

    def fill_ground(r, g):
        r["gid"] = g["gid"]; r["src"] += "T"
        r["t_type"], r["t_wtc"], r["t_reg"], r["t_ao"], r["t_rwy"] = g.get("actype"), g.get("wtc"), g.get("reg"), g.get("ao"), g.get("rwy")
        r["t_stand"] = g.get("stand_d") if g["cls"] == "dep" else g.get("stand_a")
        r["t_apt"] = g.get("ades") if g["cls"] == "dep" else g.get("adep")   # o outro aeroporto
        for k in ("aobt", "rwy_ent", "atot", "aldt", "rwy_vac", "aibt"):
            r["t_" + k] = g.get(k)
        r["t_rot"], r["t_taxi"], r["t_ga"] = g.get("rot_s"), g.get("taxi_s"), g.get("ga")

    def fill_opdi(r, o):
        r["o_id"] = o["flight_id"]; r["src"] += "O"
        r["o_icao24"], r["o_reg"], r["o_type"], r["o_model"], r["o_adep"], r["o_ades"] = o.get("icao24"), o.get("reg"), o.get("typecode"), o.get("model"), o.get("adep"), o.get("ades")
        r["o_rwy_in"], r["o_rwy_out"] = o.get("t_rwy_in"), o.get("t_rwy_out")
        # nas partidas os eventos de pista do OPDI marcam só o instante da rotação (sem recetores ADS-B no solo);
        # o ROT OPDI só faz sentido nas chegadas (entrada no polígono da pista = toque → saída)
        if o["cls"] == "arr" and o.get("t_rwy_in") and o.get("t_rwy_out") and 0 < o["t_rwy_out"] - o["t_rwy_in"] < 600:
            r["o_rot"] = o["t_rwy_out"] - o["t_rwy_in"]
        r["o_tod"], r["o_toc"], r["o_lx100"], r["o_lx50"], r["o_fx50"], r["o_fx100"], r["o_levels_low"] = \
            o.get("t_tod"), o.get("t_toc"), o.get("t_lx100"), o.get("t_lx50"), o.get("t_fx50"), o.get("t_fx100"), o.get("n_levels_low")

    def finish(r):
        n_type_exact = r["n_type"] if r["n_src"] == "nmir" else None      # o tipo "herdado" de outro dia não conta como discrepância
        types = {x for x in (n_type_exact, r["t_type"], r["o_type"]) if x}
        if len(types) > 1:
            r["flags"].append("TIPO ≠ (" + " / ".join(sorted(types)) + ")")
        ov = (type_overrides or {})
        if any(t and t in ov for t in (r["n_type"], r["t_type"], r["o_type"])):
            wtcs = set()      # WTC fixada para este tipo pelo utilizador
        else:
            wtcs = {x for x in ((r["n_wtc"] if r["n_src"] == "nmir" else None), r["t_wtc"], (wtc_from_type(r["o_type"]) if r["o_type"] else None)) if x}
        if len(wtcs) > 1:
            r["flags"].append("WTC ≠")
        other_n = r["n_adep"] if r["cls"] == "arr" else r["n_ades"]
        other_o = r["o_adep"] if r["cls"] == "arr" else r["o_ades"]
        apts = {x for x in (other_n, r["t_apt"], other_o) if x}
        if len(apts) > 1:
            r["flags"].append("ADEP/ADES ≠ (" + " / ".join(sorted(apts)) + ")")
        if r["flight_id"] and r["gid"]:
            tt = r["t_atot"] if r["cls"] == "dep" else r["t_aldt"]
            tr = r["r_t_first"] if r["cls"] == "dep" else r["r_t_last"]
            if tt and tr:
                r["dt_radar_torre"] = round(_dt(tr, tt))
                if abs(r["dt_radar_torre"]) > 300:
                    r["flags"].append("Δt radar/torre > 5 min")
        if r["gid"] and r["o_id"]:
            tt = r["t_atot"] if r["cls"] == "dep" else r["t_aldt"]
            to = r["o_rwy_out"] if r["cls"] == "dep" else r["o_rwy_in"]
            if tt and to:
                r["dt_opdi_torre"] = round(to - tt)
                if abs(r["dt_opdi_torre"]) > 120:
                    r["flags"].append("Δt OPDI/torre > 2 min")
            if r["t_rot"] and r["o_rot"]:
                r["d_rot"] = round(r["o_rot"] - r["t_rot"])
        corr = (corrections or {}).get((r["csn"], r["date"], r["cls"]))
        r["corr"] = corr
        if corr:
            if corr.get("actype") or corr.get("verified"):
                r["flags"] = [f for f in r["flags"] if not (f.startswith("TIPO") or f.startswith("WTC"))]
            if corr.get("apt") or corr.get("verified"):
                r["flags"] = [f for f in r["flags"] if not f.startswith("ADEP")]
            if corr.get("verified"):
                r["flags"] = [f for f in r["flags"] if f.startswith("sem ")]
        if r["t_ga"]:
            r["flags"].append("GA (torre)")
        if "R" not in r["src"]:
            r["flags"].append("sem radar")
        if "T" not in r["src"] and ground:
            r["flags"].append("sem torre")
        if "O" not in r["src"] and opdi:
            r["flags"].append("sem OPDI")
        if "N" not in r["src"]:
            r["flags"].append("sem NMIR")
        r["n_flags"] = len([f for f in r["flags"] if not f.startswith("sem ")])
        if corr:
            r["flags"].append("✓ corrigido" if (corr.get("actype") or corr.get("apt")) else "✓ verificado")
        r["t_sort"] = r["r_t_first"] or r["t_atot"] or r["t_aldt"] or r["o_rwy_in"] or r["o_rwy_out"] or 0

    for f in flights:
        r = base(f["csn"], f["date"], f["cls"])
        r["flight_id"] = f["flight_id"]; r["src"] = "R"
        r["r_t_first"], r["r_t_last"], r["r_n"], r["r_alt_max"], r["r_actype"] = f["t_first"], f["t_last"], f["n"], f.get("alt_max"), f.get("actype")
        fill_nmir(r)
        g = g_by_fid.get(f["flight_id"])
        if g:
            fill_ground(r, g)
            o = o_by_fid.get(f["flight_id"]) or o_by_gid.get(g["gid"])
        else:
            o = o_by_fid.get(f["flight_id"])
        if o:
            fill_opdi(r, o)
        finish(r); rows.append(r)
    matched_g = set(g_by_fid.keys())
    for g in ground:
        if g_map.get(id(g)) in matched_g and g_map.get(id(g)):
            continue
        r = base(g["csn"], g["date"], g["cls"])
        fill_nmir(r); fill_ground(r, g)
        o = o_by_gid.get(g["gid"])
        if o:
            fill_opdi(r, o)
        finish(r); rows.append(r)
    seen_o = {r["o_id"] for r in rows if r["o_id"]}
    for o in opdi:
        if o["flight_id"] in seen_o:
            continue
        r = base(_norm_csn(o.get("csn")), o["date"], o["cls"])
        fill_nmir(r); fill_opdi(r, o)
        finish(r); rows.append(r)
    rows.sort(key=lambda r: (r["date"], r["t_sort"]))

    cov = {"radar": len(flights), "torre": len(ground), "opdi": len(opdi), "total": len(rows),
           "r_t": sum(1 for r in rows if "R" in r["src"] and "T" in r["src"]),
           "r_o": sum(1 for r in rows if "R" in r["src"] and "O" in r["src"]),
           "t_o": sum(1 for r in rows if "T" in r["src"] and "O" in r["src"]),
           "all3": sum(1 for r in rows if "R" in r["src"] and "T" in r["src"] and "O" in r["src"]),
           "nmir": sum(1 for r in rows if "N" in r["src"]),
           "with_flags": sum(1 for r in rows if r["n_flags"]),
           "corrected": sum(1 for r in rows if r.get("corr")),
           "type_mismatch": sum(1 for r in rows if any(f.startswith("TIPO") for f in r["flags"])),
           "apt_mismatch": sum(1 for r in rows if any(f.startswith("ADEP") for f in r["flags"])),
           "only_radar": sum(1 for r in rows if r["src"].replace("N", "") == "R"),
           "only_torre": sum(1 for r in rows if r["src"].replace("N", "") == "T"),
           "only_opdi": sum(1 for r in rows if r["src"].replace("N", "") == "O")}
    dts = [r["dt_radar_torre"] for r in rows if r["dt_radar_torre"] is not None]
    dto = [r["dt_opdi_torre"] for r in rows if r["dt_opdi_torre"] is not None]
    drot = [r["d_rot"] for r in rows if r["d_rot"] is not None]
    med = lambda v: sorted(v)[len(v) // 2] if v else None
    cov["dt_radar_torre_med"] = med(dts); cov["dt_opdi_torre_med"] = med(dto); cov["d_rot_med"] = med(drot); cov["n_rot_both"] = len(drot)
    return {"rows": rows, "coverage": cov}
