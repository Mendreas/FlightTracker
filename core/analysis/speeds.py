"""Velocidades STAR e APP — conformidade de IAS (algoritmos da app antiga, sem as limitações de UI)."""
from __future__ import annotations

import math
from collections import defaultdict

from ..geo import (AIRPORTS, APP_DIST_WAYPOINTS, APP_IAS_DEFAULTS, APP_MODES, APP_POINT_ORDER, app_dist_limit_at,
                   approach_coords, dist_nm, epoch, fmt_date, hhmmss, points_by_name, operator3)
from .final import T, LAT, LON, ALT, IAS, TOD


def nearest_pass(pts: list[tuple], lat: float, lon: float, radius: float):
    """CPA discreto: plot mais próximo dentro do raio. Devolve (d, plot) ou None."""
    coslat = max(math.cos(math.radians(lat)), 1e-6)
    dlat = (radius / 60) * 1.4; dlon = (radius / 60 / coslat) * 1.4
    best = None
    for p in pts:
        la, lo = p[LAT], p[LON]
        if not la or not lo:
            continue
        if abs(la - lat) > dlat or abs(lo - lon) > dlon:
            continue
        d = dist_nm(lat, lon, la, lo)
        if d <= radius and (best is None or d < best[0]):
            best = (d, p)
    return best


# ------------------------------------------------------------------ STAR
def run_star(db, flights: list[dict], limits: dict[str, int], radius: float = 1.0, tol: float = 0.0) -> dict:
    radius = max(0.1, radius); tol = max(0.0, tol)
    byname = points_by_name(db.user_points())
    per_wp = {}; missing = []
    for wp, lim in limits.items():
        p = byname.get(wp.upper())
        if not p:
            missing.append(wp); continue
        per_wp[wp] = {"wp": wp, "lat": p["lat"], "lon": p["lon"], "limit": lim, "total": 0, "compliant": 0, "violations": 0,
                      "iasSum": 0.0, "iasMax": 0, "iasMin": math.inf, "excessSum": 0.0, "excessMax": 0.0}
    arr = [f for f in flights if f["cls"] == "arr"]
    pts_all = db.points_bulk([f["flight_id"] for f in arr])
    viols = []
    for f in arr:
        pts = pts_all.get(f["flight_id"], [])
        for st in per_wp.values():
            best = nearest_pass(pts, st["lat"], st["lon"], radius)
            if not best or best[1][IAS] is None or best[1][IAS] <= 0:
                continue
            d, row = best; ias = row[IAS]
            st["total"] += 1; st["iasSum"] += ias; st["iasMax"] = max(st["iasMax"], ias); st["iasMin"] = min(st["iasMin"], ias)
            excess = ias - st["limit"]
            if excess <= tol:
                st["compliant"] += 1
            else:
                st["violations"] += 1; st["excessSum"] += excess; st["excessMax"] = max(st["excessMax"], excess)
                viols.append({"flight_id": f["flight_id"], "csn": f["csn"], "wp": st["wp"], "ias": ias, "limit": st["limit"], "excess": excess,
                              "tod": (row[TOD] or "")[:8], "date": fmt_date(f["date"]), "dateRaw": f["date"], "dCpa": d,
                              "epoch": epoch(f["date"], row[T]), "actype": f.get("actype")})
    viols.sort(key=lambda v: v["epoch"])
    for st in per_wp.values():
        if st["iasMin"] == math.inf: st["iasMin"] = None
    total = sum(s["total"] for s in per_wp.values()); comp = sum(s["compliant"] for s in per_wp.values())
    # por operador
    ops: dict[str, dict] = {}
    for f in arr:
        ops.setdefault(operator3(f["csn"]), {"op": operator3(f["csn"]), "arrFlights": 0, "violations": 0})["arrFlights"] += 1
    for v in viols:
        ops.setdefault(operator3(v["csn"]), {"op": operator3(v["csn"]), "arrFlights": 0, "violations": 0})["violations"] += 1
    for o in ops.values():
        o["rate"] = o["violations"] / o["arrFlights"] if o["arrFlights"] else 0
    op_rows = sorted(ops.values(), key=lambda o: (-o["violations"], -o["rate"], -o["arrFlights"]))[:10]
    per_wp_rows = sorted([s for s in per_wp.values() if s["total"]], key=lambda s: (-(s["violations"] / s["total"]), -s["total"]))
    return {"perWp": per_wp_rows, "violations": viols, "radius": radius, "tol": tol, "flightsTotal": len(flights),
            "flightsAnalysed": len(arr), "totalPasses": total, "totalComp": comp, "totalViol": len(viols), "missing": missing,
            "pct": (comp / total * 100) if total else None, "operators": op_rows}


# ------------------------------------------------------------------ APP (pontos)
def run_app(db, flights: list[dict], airport: str, radius: float = 1.0, tol: float = 0.0) -> dict:
    radius = max(0.1, radius); tol = max(0.0, tol)
    modes = APP_MODES.get(airport, [])
    byname = points_by_name(db.user_points())
    arr = [f for f in flights if f["cls"] == "arr"]
    if not modes:
        return {"records": [], "modes": [], "flightsTotal": len(flights), "arrAnalysed": len(arr), "radius": radius, "tol": tol,
                "message": "LPMA — Sem restrições de velocidade — O aeroporto da Madeira não tem restrições de velocidade definidas em AIP."}
    pts_all = db.points_bulk([f["flight_id"] for f in arr])
    records = []; samples: dict[str, list] = defaultdict(list)
    for mode in modes:
        order = APP_POINT_ORDER.get(mode, [])
        if len(order) < 2 or any(n.upper() not in byname for n in order):
            continue
        lims = APP_IAS_DEFAULTS.get(mode, {}); rwy = mode[-2:]
        for f in arr:
            pts = pts_all.get(f["flight_id"], [])
            data = []
            for name in order:
                p = byname[name.upper()]; lim = lims.get(name, 180)
                hit = nearest_pass(pts, p["lat"], p["lon"], radius)
                if hit and hit[1][IAS] is not None and hit[1][IAS] > 0:
                    d, row = hit; ias = row[IAS]
                    samples[f"{mode}|{name}"].append(ias)
                    data.append({"point": name, "ias": ias, "limit": lim, "deviation": ias - lim, "absDeviation": abs(ias - lim),
                                 "dCpa": d, "tod": (row[TOD] or "")[:8], "epoch": epoch(f["date"], row[T])})
                else:
                    data.append({"point": name, "ias": None, "limit": lim, "deviation": None, "absDeviation": None, "dCpa": None, "tod": "", "epoch": None})
            viol = [x for x in data if x["ias"] is not None and not x["point"].upper().startswith("THR") and x["absDeviation"] > tol]
            if not viol:
                continue
            detected = [x for x in data if x["ias"] is not None]
            first = min(detected, key=lambda x: x["epoch"])
            records.append({"flight_id": f["flight_id"], "csn": f["csn"], "rwy": rwy, "mode": mode, "detected": len(detected),
                            "date": fmt_date(f["date"]), "dateRaw": f["date"], "tod": first["tod"], "epoch": first["epoch"],
                            "violCount": len(viol), "maxAbsDeviation": max(x["absDeviation"] for x in viol), "points": data,
                            "actype": f.get("actype"), "company": operator3(f["csn"])})
    # deduplicação pista/dia
    groups: dict[str, list] = defaultdict(list)
    for r in records:
        groups[f"{r['csn']}|{r['dateRaw']}"].append(r)
    filtered = []
    for g in groups.values():
        if len(g) > 1:
            mx = max(r["detected"] for r in g)
            filtered += [r for r in g if not (r["detected"] == 1 and mx > 1)]
        else:
            filtered += g
    filtered.sort(key=lambda r: r["epoch"] or 0)
    # histogramas por ponto (todas as passagens, para gráficos/PPTX)
    hist = []
    for mode in modes:
        for name in APP_POINT_ORDER.get(mode, []):
            vals = samples.get(f"{mode}|{name}", [])
            lim = APP_IAS_DEFAULTS.get(mode, {}).get(name, 180)
            hist.append({"mode": mode, "rwy": mode[-2:], "point": name, "limit": lim, "samples": vals, **_hist_stats(vals, lim, tol)})
    return {"records": filtered, "modes": modes, "flightsTotal": len(flights), "arrAnalysed": len(arr), "radius": radius, "tol": tol,
            "histograms": hist}


def _hist_stats(vals: list[float], lim: float, tol: float) -> dict:
    if not vals:
        return {"n": 0, "mean": None, "median": None, "bins": [], "labels": []}
    s = sorted(vals); n = len(s)
    med = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    mn = max(40, math.floor((min(vals) - 12) / 5) * 5); mx = min(300, math.ceil((max(vals) + 12) / 5) * 5)
    if mx - mn < 35: mx = mn + 35
    nb = math.ceil((mx - mn) / 5)
    bins = [{"lo": mn + i * 5, "y": 0, "g": 0, "r": 0} for i in range(nb)]
    for v in vals:
        i = min(nb - 1, max(0, int((v - mn) // 5)))
        cls = "r" if v > lim + tol else "y" if v < lim - tol else "g"
        bins[i][cls] += 1
    return {"n": n, "mean": sum(vals) / n, "median": med, "bins": bins, "xmin": mn, "xmax": mx}


# ------------------------------------------------------------------ APP (por distância)
def run_app_dist(db, flights: list[dict], airport: str, rwy: str = "02", buffer: int = 4, sel_nm: list[float] | None = None) -> dict:
    cfg = AIRPORTS.get(airport, AIRPORTS["LPPT"])
    if rwy not in cfg["rwys"]:
        rwy = list(cfg["rwys"])[0]
    r = cfg["rwys"][rwy]; thr_lat, thr_lon = r["thr"]
    scale = [round(12.0 - 0.5 * i, 1) for i in range(25)]
    sel = sorted(set(sel_nm if sel_nm is not None else scale), reverse=True)
    named = {w["scalePt"]: w for w in APP_DIST_WAYPOINTS.get(rwy, [])}
    arr = [f for f in flights if f["cls"] == "arr"]
    pts_all = db.points_bulk([f["flight_id"] for f in arr])
    results = []; profiles = 0
    for f in arr:
        raw = pts_all.get(f["flight_id"], [])
        pts = []
        for p in raw:
            if p[LAT] is None or p[LON] is None: continue
            along, cross = approach_coords(p[LAT], p[LON], thr_lat, thr_lon, r["brg"])
            if 0 <= along <= 12.0 and abs(cross) < 1.5:
                pts.append((along, p[IAS] or 0))
        pts.sort(key=lambda x: -x[0])
        if len(pts) < 3 or pts[-1][0] > 1.5:
            continue
        dist_data = {}
        any_viol = False
        for nm in sel:
            w = named.get(nm)
            a_nm = w["nm"] if w else nm; lim = w["limit"] if w else app_dist_limit_at(nm)
            ias = None
            for i in range(len(pts) - 1):
                a, b = pts[i], pts[i + 1]
                if a[0] >= a_nm >= b[0]:
                    rng = a[0] - b[0]; k = (a[0] - a_nm) / rng if rng > 0.001 else 0
                    if a[1] > 0 and b[1] > 0: ias = round(a[1] + k * (b[1] - a[1]))
                    elif a[1] > 0: ias = a[1]
                    elif b[1] > 0: ias = b[1]
                    break
            dev = (ias - lim) if ias is not None else None
            viol = dev is not None and abs(dev) > buffer
            any_viol |= viol
            dist_data[f"{nm:.1f}"] = {"ias": ias, "lim": lim, "dev": dev, "viol": viol, "nm": a_nm, "name": w["name"] if w else None}
        profiles += 1
        if not any_viol:
            continue
        devs = [d["dev"] for d in dist_data.values() if d["dev"] is not None]
        results.append({"flight_id": f["flight_id"], "csn": f["csn"], "date": fmt_date(f["date"]), "dateRaw": f["date"],
                        "tod": hhmmss(f["t_first"]), "rwy": rwy, "dist": dist_data,
                        "avgDev": round(sum(devs) / len(devs)) if devs else None, "comp": operator3(f["csn"]), "actype": f.get("actype")})
    results.sort(key=lambda x: -abs(x["avgDev"] or 0))
    cols = [{"nm": nm, "label": (named[nm]["name"] if nm in named else f"{nm:.1f} NM"),
             "named": nm in named, "lim": named[nm]["limit"] if nm in named else app_dist_limit_at(nm),
             "profileLim": app_dist_limit_at(nm)} for nm in sel]
    return {"results": results, "columns": cols, "scale": scale, "rwy": rwy, "buffer": buffer,
            "arrAnalysed": len(arr), "profiles": profiles, "named": {f"{k:.1f}": v for k, v in named.items()}}
