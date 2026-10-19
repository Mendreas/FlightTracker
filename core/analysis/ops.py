"""KPIs, RRMS, ROT, Pontos e Sequência."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from ..geo import (AIRPORTS, RRMS_POINTS, RRMS_RADIUS_NM, PREFIX_TYPES, dist_nm, epoch, fmt_date, hhmmss, points_by_name,
                   airport_points, runway_coords_m, wake_cat_heuristic, wtc_from_type, operator3, to_dms)
from .final import T, LAT, LON, ALT, IAS, GS, ROC, TAS, TOD, BLOCK

MONTHS_PT = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]


def rrms_date(yymmdd: str) -> str:
    try:
        return f"{yymmdd[4:6]}/{MONTHS_PT[int(yymmdd[2:4]) - 1]}/20{yymmdd[0:2]}"
    except (ValueError, IndexError, TypeError):
        return yymmdd


# ------------------------------------------------------------------ KPIs
def kpis(flights: list[dict], final_results: list[dict], star: dict | None) -> dict:
    cnt = Counter(f["cls"] for f in flights)
    by_hour = [0] * 24; by_arr = [0] * 24; by_dep = [0] * 24
    days = set(); pts = 0; min_t = math.inf; max_t = -math.inf; ops = Counter()
    for f in flights:
        t = epoch(f["date"], f["t_first"]); t2 = epoch(f["date"], f["t_last"])
        min_t = min(min_t, t); max_t = max(max_t, t2)
        if f["date"] != "??": days.add(f["date"])
        pts += f["n"]
        h = int((f["t_first"] % 86400) // 3600)
        by_hour[h] += 1
        if f["cls"] == "arr": by_arr[h] += 1
        elif f["cls"] == "dep": by_dep[h] += 1
        ops[(re.sub(r"[^A-Za-z]", "", f["csn"])[:3].upper() or "???")] += 1
    total = len(flights)
    peak = by_hour.index(max(by_hour)) if total else 0
    span_h = (max_t - min_t) / 3600 if total and max_t > min_t else None
    out = {"total": total, "arr": cnt.get("arr", 0), "dep": cnt.get("dep", 0), "lvl": cnt.get("lvl", 0), "days": len(days),
           "peakHour": peak, "peakN": by_hour[peak] if total else 0, "pts": pts,
           "period": f"{hhmmss(min_t)} → {hhmmss(max_t)}" if total else "—", "callsigns": len({f["csn"] for f in flights}),
           "byHour": by_hour, "byArr": by_arr, "byDep": by_dep, "topOps": ops.most_common(10)}
    if final_results:
        n = len(final_results)
        seps = sorted(r["sepTimeS"] for r in final_results if r["sepTimeS"] is not None)
        ias_faf = [r["iasFAF"] for r in final_results if r["iasFAF"] is not None]
        out["approach"] = {"n": n, "rate": (n / span_h) if span_h else None,
                           "byRwy": Counter(r["rwy"] for r in final_results), "stab": sum(1 for r in final_results if r["stab"]),
                           "iasFAF": sum(ias_faf) / len(ias_faf) if ias_faf else None,
                           "durS": sum(r["durS"] for r in final_results) / n, "sepMean": sum(seps) / len(seps) if seps else None,
                           "sepMin": seps[0] if seps else None, "sepMax": seps[-1] if seps else None}
        # taxa rolling 60 min
        ep = sorted(r["epochTHR"] for r in final_results)
        series = []; labels = []
        t = ep[0]
        while t <= ep[-1] + 300:
            series.append(sum(1 for e in ep if t - 3600 < e <= t)); labels.append(hhmmss(t)[:2]); t += 300
        sp = max((ep[-1] - ep[0]) / 3600, 1 / 60)
        out["landingRate"] = {"peak": max(series), "capacity": 38, "pct": max(series) / 38 * 100, "avg": math.floor(n / sp),
                              "series": series, "labels": labels}
        if len(seps) >= 3:
            bins = [0, 60, 90, 120, 150, 180, 240, 300, 600, math.inf]
            counts = [sum(1 for s in seps if bins[i] <= s < bins[i + 1]) for i in range(len(bins) - 1)]
            out["sepHist"] = {"labels": ["<60s", "60-90", "90-120", "120-150", "150-180", "180-240", "240-300", "300-600", ">600"],
                              "counts": counts, "mean": sum(seps) / len(seps), "median": seps[len(seps) // 2], "min": seps[0], "max": seps[-1],
                              "bunching": sum(1 for s in seps if s < 90)}
        cdo = [r for r in final_results if r.get("cdoLevelOffs") is not None]
        if cdo:
            out["cdo"] = {"pct": sum(1 for r in cdo if r["cdo"]) / len(cdo) * 100, "n": len(cdo), "count": sum(1 for r in cdo if r["cdo"]),
                          "levelOffs": sum(r["cdoLevelOffs"] for r in cdo) / len(cdo), "levelSecs": sum(r["cdoLevelSecs"] for r in cdo) / len(cdo)}
    if star:
        out["star"] = {"passes": star["totalPasses"], "flights": star["flightsAnalysed"], "comp": star["totalComp"], "viol": star["totalViol"],
                       "pct": star["pct"], "radius": star["radius"], "tol": star["tol"],
                       "top5": sorted([w for w in star["perWp"] if w["violations"]], key=lambda w: -w["violations"])[:5],
                       "operators": star["operators"]}
    # movimentos por dia
    by_day: dict[str, dict] = {}
    for f in flights:
        if f["date"] == "??": continue
        e = by_day.setdefault(f["date"], {"date": f["date"], "label": fmt_date(f["date"]), "arr": 0, "dep": 0, "lvl": 0, "tot": 0})
        e[f["cls"]] += 1; e["tot"] += 1
    out["byDay"] = [by_day[d] for d in sorted(by_day)]
    return out


# ------------------------------------------------------------------ RRMS
def nmir_lookup(db, csn: str, date: str) -> dict:
    r = db.con.execute("SELECT actype, wtc FROM nmir WHERE csn=? AND date=? LIMIT 1", [csn, date]).fetchone()
    if r:
        return {"type": r[0], "wtc": r[1] or wtc_from_type(r[0]), "source": "nmir"}
    r = db.con.execute("SELECT actype, wtc FROM nmir WHERE csn=? ORDER BY date DESC LIMIT 1", [csn]).fetchone()
    if r:
        return {"type": r[0], "wtc": r[1] or wtc_from_type(r[0]), "source": "fallback"}
    pre = re.sub(r"[0-9].*", "", csn or "").upper()
    if pre in PREFIX_TYPES:
        return {"type": PREFIX_TYPES[pre], "wtc": wtc_from_type(PREFIX_TYPES[pre]), "source": "prefix"}
    return {"type": "?", "wtc": "?", "source": "unknown"}


def run_rrms(db, flights: list[dict]) -> dict:
    """Passagens no ponto 2400 m (TWY U6 / TWY P) de DEP e sobrevoos — só LPPT."""
    cands = [f for f in flights if f["cls"] != "arr" and f["n"] >= 2]
    pts_all = db.points_bulk([f["flight_id"] for f in cands])
    hits = []; dbg = {"total": len(cands), "filtered": 0, "noClose": 0}
    for f in cands:
        rows = [p for p in pts_all.get(f["flight_id"], []) if p[LAT] is not None and p[LON] is not None]
        if len(rows) < 2:
            continue
        dbg["filtered"] += 1
        fr, lr = rows[:5], rows[-5:]
        lat_f = sum(p[LAT] for p in fr) / len(fr); lat_l = sum(p[LAT] for p in lr) / len(lr)
        if lat_l > lat_f + 0.001: rwy = "02"
        elif lat_f > lat_l + 0.001: rwy = "20"
        else:
            dbg["noClose"] += 1; continue
        pt = RRMS_POINTS[rwy]
        best = (math.inf, 0.0, -1)
        for i in range(len(rows) - 1):
            a, b = rows[i], rows[i + 1]
            dlat, dlon = b[LAT] - a[LAT], b[LON] - a[LON]
            len2 = dlat * dlat + dlon * dlon
            if len2 < 1e-12: continue
            k = max(0.0, min(1.0, (dlat * (pt["lat"] - a[LAT]) + dlon * (pt["lon"] - a[LON])) / len2))
            d = dist_nm(a[LAT] + k * dlat, a[LON] + k * dlon, pt["lat"], pt["lon"])
            if d < best[0]: best = (d, k, i)
        if best[2] < 0 or best[0] > RRMS_RADIUS_NM:
            dbg["noClose"] += 1; continue
        d, k, i = best; a, b = rows[i], rows[i + 1]
        alt = round(a[ALT] + k * (b[ALT] - a[ALT])) if a[ALT] is not None and b[ALT] is not None else (a[ALT] if a[ALT] is not None else b[ALT])
        if alt is None:
            continue
        ia, ib = a[IAS] or 0, b[IAS] or 0
        ias = round(ia + k * (ib - ia)) if ia and ib else (ia or ib or None)
        t = a[T] + k * (b[T] - a[T])
        nm = nmir_lookup(db, f["csn"], f["date"])
        cat = nm["wtc"] if nm["wtc"] != "?" else wake_cat_heuristic(f["csn"])
        hits.append({"flight_id": f["flight_id"], "csn": f["csn"], "rwy": rwy, "cat": cat, "cls": f["cls"], "acType": nm["type"],
                     "airborne": alt >= 50, "distNM": round(d, 3), "altFt": alt, "ias": ias, "tod": hhmmss(t), "hour": hhmmss(t)[:2],
                     "date": rrms_date(f["date"]), "dateRaw": f["date"], "epoch": epoch(f["date"], t), "comp": operator3(f["csn"])})
    hits.sort(key=lambda h: h["epoch"])
    return {"hits": hits, "dbg": dbg, "points": {k: {**v, "dms": f"{to_dms(v['lat'], True)} {to_dms(v['lon'], False)}"} for k, v in RRMS_POINTS.items()}}


def rrms_stats(rows: list[dict]) -> dict | None:
    alts = [h["altFt"] for h in rows if h["altFt"] is not None and h["altFt"] > 0]
    ias = [h["ias"] for h in rows if h["ias"]]
    if not alts:
        return None
    return {"n": len(rows), "altMin": min(alts), "altAvg": round(sum(alts) / len(alts)), "altMax": max(alts),
            "iasMin": min(ias) if ias else None, "iasAvg": round(sum(ias) / len(ias)) if ias else None, "iasMax": max(ias) if ias else None}


# ------------------------------------------------------------------ ROT
def run_rot(db, flights: list[dict], airport: str) -> dict:
    cfg = AIRPORTS.get(airport, AIRPORTS["LPPT"])
    arr = [f for f in flights if f["cls"] == "arr"]
    pts_all = db.points_bulk([f["flight_id"] for f in arr])
    res = []; dbg = Counter()
    for f in arr:
        pts = [p for p in pts_all.get(f["flight_id"], []) if p[LAT] is not None and p[LON] is not None]
        if len(pts) < 3:
            dbg["noPts"] += 1; continue
        found = False
        for rid, r in cfg["rwys"].items():
            thr = r["thr"]
            rc = [runway_coords_m(p[LAT], p[LON], thr[0], thr[1], r["brg"]) for p in pts]
            for i in range(1, len(pts)):
                (a0, c0), (a1, c1) = rc[i - 1], rc[i]
                if a0 < 0 <= a1 and abs(c0) <= 380 and abs(c1) <= 380 and pts[i][T] - pts[i - 1][T] <= 60:
                    frac = -a0 / (a1 - a0) if abs(a1 - a0) > 1e-9 else 0.0
                    t_thr = pts[i - 1][T] + frac * (pts[i][T] - pts[i - 1][T])
                    last = None
                    for j in range(i, len(pts)):
                        if pts[j][T] > t_thr + 300: break
                        if -60 <= rc[j][0] <= 4300 and abs(rc[j][1]) <= 220: last = j
                    if last is None:
                        dbg["noOnRwy"] += 1; found = True; break
                    rot = round(pts[last][T] - t_thr)
                    if not 20 <= rot <= 300:
                        dbg["tooShort"] += 1; found = True; break
                    res.append({"flight_id": f["flight_id"], "rwy": rid, "csn": f["csn"], "date": fmt_date(f["date"]), "dateRaw": f["date"],
                                "tTHRstr": hhmmss(t_thr), "epoch": epoch(f["date"], t_thr), "rotS": rot, "exitM": round(rc[last][0]),
                                "actype": f.get("actype"), "op": operator3(f["csn"])})
                    found = True; break
            if found: break
        if not found: dbg["noCross"] += 1
    res.sort(key=lambda x: x["epoch"])
    vals = sorted(x["rotS"] for x in res)
    n = len(vals)
    return {"results": res, "dbg": dict(dbg), "n": n, "mean": sum(vals) / n if n else None,
            "p85": vals[min(int(n * 0.85), n - 1)] if n else None, "p95": vals[min(int(n * 0.95), n - 1)] if n else None,
            "max": vals[-1] if n else None, "processed": len(arr)}


# ------------------------------------------------------------------ Pontos / Sequência
def point_query(db, flights: list[dict], point: dict, radius: float = 1.0) -> list[dict]:
    """Uma linha por plot dentro do raio (como na app antiga)."""
    pts_all = db.points_bulk([f["flight_id"] for f in flights])
    lat, lon = point["lat"], point["lon"]
    coslat = max(math.cos(math.radians(lat)), 1e-6)
    dlat = (radius / 60) * 1.2; dlon = (radius / 60 / coslat) * 1.2
    out = []
    for f in flights:
        for p in pts_all.get(f["flight_id"], []):
            if p[LAT] is None or p[LON] is None or abs(p[LAT] - lat) > dlat or abs(p[LON] - lon) > dlon:
                continue
            d = dist_nm(lat, lon, p[LAT], p[LON])
            if d <= radius:
                out.append({"flight_id": f["flight_id"], "csn": f["csn"], "d": round(d, 2), "tod": (p[TOD] or "")[:12], "tod_sec": p[T],
                            "date": fmt_date(f["date"]), "dateRaw": f["date"], "block": p[BLOCK], "alt": p[ALT], "ias": p[IAS], "roc": p[ROC],
                            "cls": f["cls"], "lat": round(p[LAT], 5), "lon": round(p[LON], 5), "actype": f.get("actype")})
    out.sort(key=lambda r: (r["dateRaw"], r["tod_sec"]))
    return out


def ias_filter(rows: list[dict], op: str, v1, v2=None, tol: float = 2.0) -> list[dict]:
    if op == "any" or v1 is None or (op == "between" and v2 is None):
        return rows
    def ok(n):
        if n is None: return False
        return {"lt": n < v1, "le": n <= v1, "eq": abs(n - v1) <= tol, "ge": n >= v1, "gt": n > v1,
                "between": min(v1, v2) <= n <= max(v1, v2)}.get(op, True)
    return [r for r in rows if ok(r["ias"])]


def sequence_query(db, flights: list[dict], point: dict, radius: float = 1.0) -> list[dict]:
    """Uma linha por aeronave (CPA), com distância à anterior/seguinte interpolada no tempo."""
    pts_all = db.points_bulk([f["flight_id"] for f in flights])
    lat, lon = point["lat"], point["lon"]
    coslat = max(math.cos(math.radians(lat)), 1e-6)
    dlat = (radius / 60) * 1.2; dlon = (radius / 60 / coslat) * 1.2
    seq = []
    for f in flights:
        best = None
        for p in pts_all.get(f["flight_id"], []):
            if p[LAT] is None or p[LON] is None or abs(p[LAT] - lat) > dlat or abs(p[LON] - lon) > dlon: continue
            d = dist_nm(lat, lon, p[LAT], p[LON])
            if d <= radius and (best is None or d < best[0]): best = (d, p)
        if best:
            d, p = best
            seq.append({"flight_id": f["flight_id"], "csn": f["csn"], "d": round(d, 2), "tod": (p[TOD] or "")[:8], "date": fmt_date(f["date"]),
                        "dateRaw": f["date"], "epoch": epoch(f["date"], p[T]), "block": p[BLOCK], "alt": p[ALT], "ias": p[IAS],
                        "lat": p[LAT], "lon": p[LON], "cls": f["cls"], "actype": f.get("actype")})
    seq.sort(key=lambda r: r["epoch"])

    def pos_at(fid, date, t):
        pts = pts_all.get(fid, [])
        tt = t - epoch(date, 0)
        for i in range(1, len(pts)):
            if pts[i - 1][T] <= tt <= pts[i][T]:
                k = (tt - pts[i - 1][T]) / (pts[i][T] - pts[i - 1][T]) if pts[i][T] > pts[i - 1][T] else 0
                return pts[i - 1][LAT] + k * (pts[i][LAT] - pts[i - 1][LAT]), pts[i - 1][LON] + k * (pts[i][LON] - pts[i - 1][LON])
        return None
    for i, r in enumerate(seq):
        r["antD"] = r["segD"] = None
        if i > 0:
            pp = pos_at(seq[i - 1]["flight_id"], seq[i - 1]["dateRaw"], r["epoch"])
            if pp: r["antD"] = round(dist_nm(r["lat"], r["lon"], *pp), 1)
        if i < len(seq) - 1:
            pp = pos_at(seq[i + 1]["flight_id"], seq[i + 1]["dateRaw"], r["epoch"])
            if pp: r["segD"] = round(dist_nm(r["lat"], r["lon"], *pp), 1)
    return seq


def all_points_for(db, airport: str) -> list[dict]:
    return airport_points(airport, db.user_points())
