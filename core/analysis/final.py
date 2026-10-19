"""Aba Final — deteção de aterragens e análise FAF→THR (algoritmo da app antiga).

Diferenças conscientes face à versão antiga:
  * tempos são 'epoch' reais entre dias (dias de calendário), não int(AAMMDD)*86400;
  * CDO: a duração dos patamares está em segundos (a versão antiga dividia por 1000 por engano).
"""
from __future__ import annotations

import json
import math

from ..geo import AIRPORTS, dist_nm, hhmmss, fmt_date

# índices do tuplo de points_bulk
T, LAT, LON, ALT, IAS, GS, ROC, TAS, TOD, BLOCK, MODEA = range(11)


def _interp(a, b, k):
    return a + k * (b - a)


def _k(a_along, b_along, target):
    """Factor de interpolação entre dois plots; 0 se os plots coincidem (evita divisão por zero)."""
    d = a_along - b_along
    return (a_along - target) / d if abs(d) > 1e-9 else 0.0


def analyze_flight_approach(flight: dict, pts_raw: list[tuple], ri: int, rwy_id: str, rwy: dict,
                            faf_nm: float, corr_nm: float, alt_thr_max: float) -> dict | None:
    """pts_raw: tuplos (epoch, lat, lon, alt, ias, along_1, cross_1, along_2, cross_2, …); ri = índice da pista (0,1,…)."""
    thr_lat, thr_lon = rwy["thr"]
    ia, ic = 5 + 2 * ri, 6 + 2 * ri
    # A — caixa de sanidade (~36 NM)
    if not any(abs(p[1] - thr_lat) < 0.6 and abs(p[2] - thr_lon) < 0.6 for p in pts_raw):
        return None
    # B — pontos válidos (já ordenados por tempo)
    pts = [{"t": p[0], "lat": p[1], "lon": p[2], "alt": p[3], "ias": p[4], "along": p[ia], "cross": p[ic]} for p in pts_raw if p[3] is not None]
    if len(pts) < 3:
        return None
    date = flight["date"]
    # C — cruzamento da THR
    alt_abs_max = rwy["elev"] + alt_thr_max
    thr_idx = -1
    for i in range(1, len(pts)):
        a, b = pts[i - 1], pts[i]
        if a["along"] > 0 and b["along"] <= 0.3:
            if min(a["alt"], b["alt"]) <= alt_abs_max and abs(a["cross"]) < corr_nm and abs(b["cross"]) < corr_nm:
                thr_idx = i
                break
    if thr_idx < 0:
        return None
    pa, pb = pts[thr_idx - 1], pts[thr_idx]
    kt = _k(pa["along"], pb["along"], 0.0)
    t_thr = _interp(pa["t"], pb["t"], kt)
    alt_thr = _interp(pa["alt"], pb["alt"], kt)
    ias_thr = _interp(pa["ias"], pb["ias"], kt) if pa["ias"] is not None and pb["ias"] is not None else None
    lat_thr, lon_thr = _interp(pa["lat"], pb["lat"], kt), _interp(pa["lon"], pb["lon"], kt)
    # D — FAF (último cruzamento antes da THR)
    faf_idx = -1
    for i in range(thr_idx - 1, 0, -1):
        a, b = pts[i - 1], pts[i]
        if a["along"] > faf_nm and b["along"] <= faf_nm:
            faf_idx = i
            break
    if faf_idx < 0:
        return None
    fa, fb = pts[faf_idx - 1], pts[faf_idx]
    kf = _k(fa["along"], fb["along"], faf_nm)
    t_faf = _interp(fa["t"], fb["t"], kf)
    alt_faf = _interp(fa["alt"], fb["alt"], kf)
    cross_faf = _interp(fa["cross"], fb["cross"], kf)
    ias_faf = _interp(fa["ias"], fb["ias"], kf) if fa["ias"] is not None and fb["ias"] is not None else None
    lat_faf, lon_faf = _interp(fa["lat"], fb["lat"], kf), _interp(fa["lon"], fb["lon"], kf)
    # E — IAS a 4 NM
    ias4 = None
    for i in range(faf_idx, thr_idx + 1):
        a, b = pts[i - 1], pts[i]
        if a["along"] > 4 and b["along"] <= 4:
            if a["ias"] is not None and b["ias"] is not None:
                ias4 = _interp(a["ias"], b["ias"], _k(a["along"], b["along"], 4.0))
            break
    # F — track miles FAF→THR
    track = dist_nm(lat_faf, lon_faf, pts[faf_idx]["lat"], pts[faf_idx]["lon"])
    for i in range(faf_idx, thr_idx - 1):
        track += dist_nm(pts[i]["lat"], pts[i]["lon"], pts[i + 1]["lat"], pts[i + 1]["lon"])
    track += dist_nm(pts[thr_idx - 1]["lat"], pts[thr_idx - 1]["lon"], lat_thr, lon_thr)
    # G — estabilizada (proxy no FAF)
    agl_faf = alt_faf - rwy["elev"]
    stab = (800 <= agl_faf <= 5000) and (ias_faf is None or 120 <= ias_faf <= 230) and abs(cross_faf) <= 1.0
    # H — CDO (patamares abaixo de FL100), duração em segundos
    level_offs, level_secs = 0, 0.0
    start = next((i for i in range(thr_idx) if pts[i]["alt"] <= 10000), -1)
    if start >= 0:
        i = start
        while i < thr_idx - 1:
            a = pts[i]; j = i + 1; mx = mn = a["alt"]
            while j <= thr_idx and pts[j]["alt"] <= 10000:
                mx = max(mx, pts[j]["alt"]); mn = min(mn, pts[j]["alt"])
                if mx - mn > 150:
                    break
                j += 1
            dur = pts[min(j, thr_idx)]["t"] - a["t"]
            if j - i >= 2 and dur >= 30 and (mx - mn) <= 150 and a["alt"] >= rwy["elev"] + 800:
                level_offs += 1; level_secs += dur
            i = max(j, i + 1)
    return {
        "flight_id": flight["flight_id"], "csn": flight["csn"], "rwy": rwy_id,
        "epochTHR": t_thr, "epochFAF": t_faf, "tTHRstr": hhmmss(t_thr), "tFAFstr": hhmmss(t_faf),
        "date": fmt_date(date), "_dateRaw": date, "actype": flight.get("actype"), "wtc": flight.get("wtc"),
        "altFAF": alt_faf, "altTHR": alt_thr, "iasFAF": ias_faf, "ias4": ias4, "iasTHR": ias_thr,
        "crossFAF": cross_faf, "trackNM": track, "durS": t_thr - t_faf, "stab": stab,
        "cdo": level_offs == 0, "cdoLevelOffs": level_offs, "cdoLevelSecs": level_secs,
        "latFAF": lat_faf, "lonFAF": lon_faf, "latTHR": lat_thr, "lonTHR": lon_thr,
    }


def run_final(db, flights: list[dict], airport: str, rwy_sel: str = "BOTH",
              faf_nm: float = 7.0, corr_nm: float = 2.0, alt_thr_max: float = 1000.0) -> list[dict]:
    """Corre a análise da final sobre a lista de movimentos (resultados em cache por movimento)."""
    cfg = AIRPORTS.get(airport, AIRPORTS["LPPT"])
    rwys = list(cfg["rwys"].keys()) if rwy_sel == "BOTH" else [rwy_sel]
    pkey = f"final|{faf_nm}|{corr_nm}|{alt_thr_max}|{','.join(rwys)}"
    keys = {f["flight_id"]: f"{pkey}|{f['flight_id']}" for f in flights}
    cached = db.cache_get(keys.values())
    results: list[dict] = []
    todo = [f for f in flights if keys[f["flight_id"]] not in cached]
    for f in flights:
        k = keys[f["flight_id"]]
        if k in cached:
            results.extend(json.loads(cached[k]))
    if todo:
        rw = {rid: cfg["rwys"][rid] for rid in rwys}
        pts = db.points_with_approach([f["flight_id"] for f in todo], rw)
        new_items = []
        for f in todo:
            recs = []
            p = pts.get(f["flight_id"], [])
            if len(p) >= 3:
                for ri, rid in enumerate(rwys):
                    r = analyze_flight_approach(f, p, ri, rid, cfg["rwys"][rid], faf_nm, corr_nm, alt_thr_max)
                    if r:
                        recs.append(r)
            results.extend(recs)
            new_items.append((keys[f["flight_id"]], f["flight_id"], json.dumps(recs)))
        db.cache_put(new_items)
    results.sort(key=lambda r: r["epochTHR"])
    prev = {}
    for i, r in enumerate(results):
        r["idx"] = i + 1
        key = f"{r['rwy']}|{r['_dateRaw']}"
        r["sepTimeS"] = (r["epochTHR"] - prev[key]) if key in prev else None
        prev[key] = r["epochTHR"]
    return results


def final_summary(results: list[dict]) -> dict:
    n = len(results)
    def mean(vals):
        vals = [v for v in vals if v is not None and math.isfinite(v)]
        return sum(vals) / len(vals) if vals else None
    seps = [r["sepTimeS"] for r in results if r["sepTimeS"] is not None]
    return {
        "n": n, "stab": sum(1 for r in results if r["stab"]),
        "iasFAF": mean(r["iasFAF"] for r in results), "durS": mean(r["durS"] for r in results),
        "sepMean": mean(seps), "sepMin": min(seps) if seps else None, "sepMax": max(seps) if seps else None,
        "byRwy": {k: sum(1 for r in results if r["rwy"] == k) for k in sorted(set(r["rwy"] for r in results))},
    }
