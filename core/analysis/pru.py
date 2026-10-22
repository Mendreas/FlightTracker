"""KPIs de aeroporto no estilo PRU / EUROCONTROL (ansperformance.eu), calculados com as fontes da app:
   - Additional taxi-out / taxi-in time (ficheiro da torre): real − referência não-impedida (P20 por stand↔pista)
   - ASMA additional time (radar): tempo do anel de 40 NM à aterragem − referência não-impedida (P20 por pista × setor de entrada)
   - ATFM delay de aeroporto (torre e NMIR), pontualidade à partida OTP15 (NMIR), go-arounds (torre),
     throughput horário e utilização da capacidade declarada (radar), CDO (OPDI)."""
from __future__ import annotations

import math
from collections import defaultdict

from core.geo import AIRPORTS, dist_nm, bearing_deg

ASMA_NM = 40.0
DECLARED_CAPACITY = {"LPPT": 40, "LPPR": 20, "LPFR": 24, "LPMA": 12}   # mov./hora — editável em Preferências


def _p(v, q):
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    k = (len(v) - 1) * q; f = int(k); c = min(f + 1, len(v) - 1)
    return v[f] + (v[c] - v[f]) * (k - f)


def _stats(v):
    v = [x for x in v if x is not None]
    if not v:
        return {"n": 0}
    return {"n": len(v), "mean": sum(v) / len(v), "median": _p(v, .5), "p20": _p(v, .2), "p80": _p(v, .8), "max": max(v)}


def additional_taxi(ground: list[dict], ref_rows: list[dict] | None = None) -> dict:
    """ref_rows: população para a referência não-impedida (por omissão, os próprios registos)."""
    ref_rows = ref_rows or ground
    def refs(rows, kind):
        g = defaultdict(list)
        for r in rows:
            if r["mt"] != kind or r.get("taxi_s") is None or not (30 < r["taxi_s"] < 7200):
                continue
            stand = r.get("stand_d") if kind == "DEPARTURE" else r.get("stand_a")
            g[(stand or "?", r.get("rwy") or "?")].append(r["taxi_s"])
        by_pair = {k: _p(v, .2) for k, v in g.items() if len(v) >= 5}
        by_rwy = defaultdict(list)
        for (s, rw), v in g.items():
            by_rwy[rw] += v
        by_rwy = {k: _p(v, .2) for k, v in by_rwy.items() if v}
        allv = [x for v in g.values() for x in v]
        return by_pair, by_rwy, _p(allv, .2)
    out = {}
    for kind, key in (("DEPARTURE", "taxi_out"), ("ARRIVAL", "taxi_in")):
        by_pair, by_rwy, glob = refs(ref_rows, kind)
        add = []; per_stand = defaultdict(list); per_hour = defaultdict(list); recs = []
        for r in ground:
            if r["mt"] != kind or r.get("taxi_s") is None or not (30 < r["taxi_s"] < 7200):
                continue
            stand = (r.get("stand_d") if kind == "DEPARTURE" else r.get("stand_a")) or "?"
            ref = by_pair.get((stand, r.get("rwy") or "?")) or by_rwy.get(r.get("rwy") or "?") or glob
            if ref is None:
                continue
            a = max(0.0, r["taxi_s"] - ref)
            add.append(a); per_stand[stand].append(a)
            recs.append({"date": r.get("date"), "csn": r.get("csn"), "flight_id": r.get("flight_id"), "actype": r.get("actype"), "stand": stand, "rwy": r.get("rwy"),
                         "route": r.get("taxi_out") if kind == "DEPARTURE" else r.get("taxi_in"), "taxi_s": round(r["taxi_s"]), "ref_s": round(ref), "add_s": round(a)})
            t = r.get("atot") if kind == "DEPARTURE" else r.get("aldt")
            if t:
                per_hour[int((t % 86400) // 3600)].append(a)
        st = _stats(add)
        out[key] = {**st, "mean_min": st["mean"] / 60 if st.get("mean") is not None else None, "records": sorted(recs, key=lambda x: -x["add_s"]),
                    "by_stand": sorted(({"key": k, "n": len(v), "mean": sum(v) / len(v)} for k, v in per_stand.items() if len(v) >= 3), key=lambda x: -x["mean"])[:12],
                    "by_hour": [sum(per_hour[h]) / len(per_hour[h]) if per_hour.get(h) else None for h in range(24)],
                    "n_refs": len(by_pair)}
    return out


def asma(db, flights: list[dict], airport: str) -> dict:
    """ASMA additional time: para cada chegada, tempo desde a 1ª entrada no anel de 40 NM até ao último plot
    (≈ aterragem) menos a referência não-impedida (P20) do grupo pista × setor de entrada (8 setores)."""
    arr = [f for f in flights if f["cls"] == "arr"]
    if not arr or airport not in AIRPORTS:
        return {"n": 0}
    c = AIRPORTS[airport]["center"]
    ids = [f["flight_id"] for f in arr]
    # raio do anel: 40 NM (PRU) se a cobertura radar chegar lá; senão o maior raio coberto por ≥80 % das chegadas
    cov = db.con.execute(f"""
        WITH sel AS (SELECT flight_id, airport, date, csn, t_first, t_last FROM flights WHERE flight_id IN (SELECT unnest(?::INTEGER[]))),
        pts AS (SELECT s.flight_id, 2*3440.065*asin(sqrt(pow(sin(radians(p.lat-{c[0]})/2),2) + cos(radians(p.lat))*cos(radians({c[0]}))*pow(sin(radians(p.lon-({c[1]}))/2),2))) AS d
                FROM sel s JOIN points p ON p.airport=s.airport AND p.date=s.date AND p.csn=s.csn AND p.tod_sec BETWEEN s.t_first AND s.t_last)
        SELECT quantile_cont(mx, 0.2) FROM (SELECT flight_id, max(d) mx FROM pts GROUP BY 1)""", [ids]).fetchone()[0]
    ring = min(ASMA_NM, math.floor(cov)) if cov else ASMA_NM
    if ring < 5:
        return {"n": 0, "note": "cobertura radar insuficiente para um anel de aproximação"}
    rows = db.con.execute(f"""
        WITH sel AS (SELECT flight_id, airport, date, csn, t_first, t_last FROM flights WHERE flight_id IN (SELECT unnest(?::INTEGER[]))),
        pts AS (SELECT s.flight_id, p.tod_sec, p.lat, p.lon,
                       2*3440.065*asin(sqrt(pow(sin(radians(p.lat-{c[0]})/2),2) + cos(radians(p.lat))*cos(radians({c[0]}))*pow(sin(radians(p.lon-({c[1]}))/2),2))) AS d
                FROM sel s JOIN points p ON p.airport=s.airport AND p.date=s.date AND p.csn=s.csn AND p.tod_sec BETWEEN s.t_first AND s.t_last)
        SELECT flight_id, min(tod_sec) FILTER (d <= {ring}) t_in, arg_min(lat, tod_sec) FILTER (d <= {ring}) lat_in, arg_min(lon, tod_sec) FILTER (d <= {ring}) lon_in,
               min(d) d_min, max(d) d_max, max(tod_sec) t_end, arg_max(lat, tod_sec) lat_end, arg_max(lon, tod_sec) lon_end,
               arg_min(lat, d) lat_c, arg_min(lon, d) lon_c
        FROM pts GROUP BY flight_id""", [ids]).fetchall()
    rwys = AIRPORTS[airport]["rwys"]
    by_f = {f["flight_id"]: f for f in arr}
    recs = []
    for fid, t_in, lat_in, lon_in, d_min, d_max, t_end, lat_end, lon_end, lat_c, lon_c in rows:
        if t_in is None or d_max is None or d_max < ring - 0.5 or d_min > 3:   # precisa de entrar no anel vindo de fora e chegar perto da pista
            continue
        brg = bearing_deg(c[0], c[1], lat_in, lon_in)
        sector = int(((brg + 22.5) % 360) // 45)
        f = by_f[fid]
        # pista pelo rumo do troço final (ponto mais próximo do ARP → último plot) comparado com o rumo de cada pista
        trk = bearing_deg(lat_c, lon_c, lat_end, lon_end) if (lat_c, lon_c) != (lat_end, lon_end) else None
        rwy = min(rwys, key=lambda k: abs((trk - rwys[k]["brg"] + 180) % 360 - 180)) if (rwys and trk is not None) else "?"
        recs.append({"flight_id": fid, "csn": f["csn"], "t": t_end - t_in, "sector": sector, "rwy": rwy, "hour": int((t_end % 86400) // 3600), "date": f["date"]})
    if not recs:
        return {"n": 0, "note": "nenhuma chegada com trajetória desde 40 NM"}
    groups = defaultdict(list)
    for r in recs:
        groups[(r["rwy"], r["sector"])].append(r["t"])
    ref = {k: _p(v, .2) for k, v in groups.items() if len(v) >= 5}
    glob = _p([r["t"] for r in recs], .2)
    add = []; per_sector = defaultdict(list); per_hour = defaultdict(list); worst = []
    for r in recs:
        rf = ref.get((r["rwy"], r["sector"])) or glob
        r["add"] = max(0.0, r["t"] - rf); add.append(r["add"]); per_sector[r["sector"]].append(r["add"]); per_hour[r["hour"]].append(r["add"])
    names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    st = _stats(add)
    return {**st, "mean_min": st["mean"] / 60, "ring_nm": ring, "transit": _stats([r["t"] for r in recs]),
            "by_sector": [{"key": names[s], "n": len(v), "mean": sum(v) / len(v), "ref": ref.get(next((k for k in ref if k[1] == s), None))} for s, v in sorted(per_sector.items())],
            "by_hour": [sum(per_hour[h]) / len(per_hour[h]) if per_hour.get(h) else None for h in range(24)],
            "worst": sorted(recs, key=lambda r: -r["add"])[:15],
            "records": [{"date": r["date"], "csn": r["csn"], "flight_id": r["flight_id"], "rwy": r["rwy"], "sector": names[r["sector"]], "t": round(r["t"]), "add": round(r["add"])} for r in sorted(recs, key=lambda r: -r["add"])]}


def atfm_and_punctuality(nmir_rows: list[dict], ground: list[dict]) -> dict:
    deps = [r for r in nmir_rows if r.get("atot") and r.get("etot")]
    dev = [(r["atot"] - (r.get("ctot") or r["etot"])) / 60 for r in deps]
    otp_recs = sorted(({"date": r["date"], "csn": r["csn"], "actype": r.get("actype"), "ades": r.get("ades"), "etot": r.get("etot"), "ctot": r.get("ctot"), "atot": r["atot"],
                        "dev_min": round(d, 1), "ok": d <= 15} for r, d in zip(deps, dev)), key=lambda x: -x["dev_min"])
    atfm_n_recs = sorted(({"date": r["date"], "csn": r["csn"], "actype": r.get("actype"), "ades": r.get("ades"), "etot": r.get("etot"), "ctot": r.get("ctot"), "atfm_delay": r["atfm_delay"]}
                          for r in nmir_rows if r.get("atfm_delay")), key=lambda x: -x["atfm_delay"])
    otp = sum(1 for d in dev if d <= 15)
    early = sum(1 for d in dev if d < -5)
    regulated = [r for r in nmir_rows if r.get("ctot")]
    dly_n = [r["atfm_delay"] for r in nmir_rows if r.get("atfm_delay")]
    g_dep = [r for r in ground if r["mt"] == "DEPARTURE"]
    dly_g = [r["atfm_delay"] for r in g_dep if r.get("atfm_delay")]
    regs = defaultdict(lambda: [0, 0.0])
    for r in g_dep:
        if r.get("atfm_delay"):
            k = r.get("regulation") or "?"; regs[k][0] += 1; regs[k][1] += r["atfm_delay"]
    atfm_g_recs = sorted(({"date": r.get("date"), "csn": r.get("csn"), "flight_id": r.get("flight_id"), "actype": r.get("actype"), "ades": r.get("ades"), "ctot": r.get("ctot"), "atot": r.get("atot"),
                           "atfm_delay": r["atfm_delay"], "regulation": r.get("regulation")} for r in g_dep if r.get("atfm_delay")), key=lambda x: -x["atfm_delay"])
    return {"otp": {"n": len(dev), "ok": otp, "pct": otp / len(dev) * 100 if dev else None, "early": early,
                    "dev_mean": sum(dev) / len(dev) if dev else None, "dev_median": _p(dev, .5), "dev_p80": _p(dev, .8),
                    "hist": _hist(dev, [-15, -5, 0, 5, 15, 30, 60, 120]), "records": otp_recs},
            "atfm_nmir": {"regulated": len(regulated), "delayed": len(dly_n), "minutes": sum(dly_n), "per_dep": sum(dly_n) / len(nmir_rows) if nmir_rows else None,
                          "mean_delayed": sum(dly_n) / len(dly_n) if dly_n else None, "n_dep": len(nmir_rows), "records": atfm_n_recs},
            "atfm_torre": {"delayed": len(dly_g), "minutes": sum(dly_g), "per_dep": sum(dly_g) / len(g_dep) if g_dep else None, "n_dep": len(g_dep),
                           "by_regulation": sorted(({"key": k, "n": v[0], "minutes": v[1]} for k, v in regs.items()), key=lambda x: -x["minutes"])[:12], "records": atfm_g_recs}}


def _hist(vals, edges):
    counts = [0] * (len(edges) + 1)
    for v in vals:
        i = 0
        while i < len(edges) and v >= edges[i]:
            i += 1
        counts[i] += 1
    labels = [f"<{edges[0]}"] + [f"{a}…{b}" for a, b in zip(edges, edges[1:])] + [f">{edges[-1]}"]
    return {"labels": labels, "counts": counts}


def throughput(flights: list[dict], ground: list[dict], capacity: int, ga_list: list[dict] | None = None) -> dict:
    """Movimentos de pista por hora. Com ficheiro da torre usa ATOT/ALDT (movimentos reais de pista);
    sem torre usa o radar (chegadas/partidas detetadas, que incluem tráfego de aeródromos vizinhos)."""
    src = "torre" if ground else "radar"
    if ground:
        mov = [{"date": g["date"], "cls": "dep" if g["mt"] == "DEPARTURE" else "arr", "t_first": g.get("atot") or 0, "t_last": g.get("aldt") or 0, "wtc": g.get("wtc"),
                "csn": g.get("csn"), "flight_id": g.get("flight_id"), "actype": g.get("actype"), "rwy": g.get("rwy"), "stand": g.get("stand_d") if g["mt"] == "DEPARTURE" else g.get("stand_a")}
               for g in ground if (g.get("atot") if g["mt"] == "DEPARTURE" else g.get("aldt"))]
    else:
        mov = [{**f, "stand": None, "rwy": None} for f in flights if f["cls"] in ("arr", "dep")]
    for m in mov:
        m["t"] = m["t_first"] if m["cls"] == "dep" else m["t_last"]
    days = sorted({f["date"] for f in mov})
    per = defaultdict(lambda: [0, 0])
    for f in mov:
        t = f["t_first"] if f["cls"] == "dep" else f["t_last"]
        per[(f["date"], int((t % 86400) // 3600))][0 if f["cls"] == "arr" else 1] += 1
    hourly = [sum(v) for v in per.values()]
    by_hour = [[0, 0] for _ in range(24)]
    for (d, h), v in per.items():
        by_hour[h][0] += v[0]; by_hour[h][1] += v[1]
    nd = max(1, len(days))
    avg_hour = [[a / nd, b / nd] for a, b in by_hour]
    # rolling 60 min (passos de 5 min) com todas as fontes radar
    peak_roll = 0; peak_when = None
    for d in days:
        ts = sorted((f["t_first"] if f["cls"] == "dep" else f["t_last"]) % 86400 for f in mov if f["date"] == d)
        j = 0
        for i, t in enumerate(ts):
            while ts[j] < t - 3600:
                j += 1
            if i - j + 1 > peak_roll:
                peak_roll = i - j + 1; peak_when = (d, t)
    peak_rows = []
    if peak_when:
        d, t = peak_when
        peak_rows = [m for m in mov if m["date"] == d and t - 3600 < (m["t"] % 86400) <= t]
    # go-arounds: torre (registos GA=TRUE) e, nos dias sem torre, os detetados no radar; ga_list vem de db.go_arounds
    ga = sum(1 for r in (ga_list or []) if r["src"] != "só radar") if ground else len(ga_list or [])
    n_arr_g = sum(1 for r in ground if r["mt"] != "DEPARTURE")
    hours_over = sum(1 for v in hourly if v > capacity)
    return {"source": src, "n": len(mov), "days": len(days), "per_day": len(mov) / nd, "peak_hour_mov": max(hourly) if hourly else 0,
            "peak_roll60": peak_roll, "peak_when": peak_when, "capacity": capacity, "util_peak": (peak_roll / capacity * 100) if capacity else None,
            "hours_over_capacity": hours_over, "hours_total": len(hourly), "avg_by_hour": avg_hour,
            "wtc": _wtc_mix(mov), "ga": ga, "ga_rate": (ga / n_arr_g * 1000) if n_arr_g else None, "n_arr_torre": n_arr_g,
            "records": sorted(mov, key=lambda m: (m["date"], m["t"])), "peak_records": sorted(peak_rows, key=lambda m: m["t"]),
            "ga_records": ga_list or [], "ga_radar": sum(1 for r in (ga_list or []) if r["src"] != "só torre" and r["src"] != "sem radar"),
            "ga_only_radar": sum(1 for r in (ga_list or []) if r["src"] == "só radar")}


def _wtc_mix(mov):
    from collections import Counter
    c = Counter((f.get("wtc") or "?") for f in mov)
    tot = sum(c.values()) or 1
    return {k: {"n": v, "pct": v / tot * 100} for k, v in sorted(c.items())}


def cdo(opdi: list[dict]) -> dict:
    arr = [o for o in opdi if o.get("cls") == "arr" and o.get("t_tod")]
    if not arr:
        return {"n": 0}
    lv = [o.get("n_levels_low") or 0 for o in arr]
    full = sum(1 for x in lv if x == 0)
    return {"n": len(arr), "cdo": full, "pct": full / len(arr) * 100, "levels_mean": sum(lv) / len(lv),
            "hist": _hist(lv, [1, 2, 3, 4]),
            "records": sorted(({"date": o.get("date"), "csn": o.get("csn"), "typecode": o.get("typecode"), "adep": o.get("adep"), "t_tod": o.get("t_tod"), "n_levels_low": o.get("n_levels_low") or 0, "cdo": (o.get("n_levels_low") or 0) == 0} for o in arr), key=lambda x: -x["n_levels_low"])}


def compute(db, airport: str, flights: list[dict], ground: list[dict], opdi: list[dict], nmir_rows: list[dict], capacity: int | None = None,
            ref_ground: list[dict] | None = None) -> dict:
    cap = capacity or DECLARED_CAPACITY.get(airport, 40)
    out = {"airport": airport, "capacity": cap,
           "taxi": additional_taxi(ground, ref_ground) if ground else None,
           "asma": asma(db, flights, airport) if flights else None,
           "atfm": atfm_and_punctuality(nmir_rows, ground),
           "throughput": throughput(flights, ground, cap, db.go_arounds(airport, sorted({f["date"] for f in flights} | {g["date"] for g in ground}))) if (flights or ground) else None,
           "cdo": cdo(opdi) if opdi else None,
           "sources": {"radar": len(flights), "torre": len(ground), "opdi": len(opdi), "nmir": len(nmir_rows)}}
    # dados de origem de cada cartão (drill-down), separados para não pesar o resto
    t, x, a, f, c = out["throughput"], out["taxi"], out["asma"], out["atfm"], out["cdo"]
    out["details"] = {
        "mov": (t or {}).pop("records", []), "peak": (t or {}).pop("peak_records", []), "ga": (t or {}).pop("ga_records", []),
        "taxi_out": (x or {}).get("taxi_out", {}).pop("records", []) if x else [], "taxi_in": (x or {}).get("taxi_in", {}).pop("records", []) if x else [],
        "asma": (a or {}).pop("records", []) if a else [],
        "otp": f["otp"].pop("records", []), "atfm_nmir": f["atfm_nmir"].pop("records", []), "atfm_torre": f["atfm_torre"].pop("records", []),
        "cdo": (c or {}).pop("records", []) if c else []}
    return out
