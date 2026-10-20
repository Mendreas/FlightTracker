"""Movimentos no solo (LPPT): rede de taxiways/stands do OpenStreetMap embebida na app
e reconstrução do percurso stand ↔ pista a partir das sequências TAXI_OUT / TAXI_IN do
ficheiro operacional da torre (ALL_LPPT_*.csv), com interpolação temporal entre os
tempos conhecidos (AOBT, HP_TIME, RWY_ENT, ATOT / ALDT, RWY_VAC, AIBT)."""
from __future__ import annotations

import heapq
import json
import math
from functools import lru_cache

from core.db import resource_path
from core.geo import AIRPORTS, dist_nm

R_EARTH_M = 6371000.0


def _m(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    x = (lo2 - lo1) * math.cos((la1 + la2) / 2); y = la2 - la1
    return math.hypot(x, y) * R_EARTH_M


class Airfield:
    """Grafo da rede de circulação: nós (lat,lon) ligados por arestas com o nome do taxiway."""

    def __init__(self, airport="LPPT"):
        p = resource_path("data", f"{airport.lower()}_airfield.json")
        d = json.loads(p.read_text(encoding="utf-8"))
        self.airport = airport
        self.nodes: dict[int, tuple[float, float]] = {int(k): (v[0], v[1]) for k, v in d["nodes"].items()}
        self.stands: dict[str, tuple[float, float]] = {k: (v[0], v[1]) for k, v in d["stands"].items()}
        self.stand_lines = d.get("stand_lines", {})
        self.holding = {k: (v[0], v[1]) for k, v in d.get("holding", {}).items()}
        self.ways = d["ways"]
        self.adj: dict[int, list[tuple[int, float, str | None, str]]] = {}   # n -> [(m, metros, ref, type)]
        self.ref_nodes: dict[str, set[int]] = {}
        self.runway_nodes: set[int] = set()
        for w in self.ways:
            ref, typ = w.get("ref"), w["type"]
            ns = [n for n in w["nodes"] if n in self.nodes]
            for a, b in zip(ns, ns[1:]):
                L = _m(self.nodes[a], self.nodes[b])
                self.adj.setdefault(a, []).append((b, L, ref, typ))
                self.adj.setdefault(b, []).append((a, L, ref, typ))
            if typ == "runway":
                self.runway_nodes.update(ns)
            if ref:
                self.ref_nodes.setdefault(ref.upper(), set()).update(ns)
        self.thr = AIRPORTS[airport]["rwys"] if airport in AIRPORTS else {}

    # ------------------------------------------------------------------ helpers
    def nearest_node(self, pt, candidates=None) -> int:
        cand = candidates if candidates is not None else self.nodes.keys()
        return min(cand, key=lambda n: _m(self.nodes[n], pt))

    def junction(self, a: str, b: str) -> int | None:
        """Nó comum entre o taxiway a e o taxiway b (ou pista se b == 'RWY')."""
        sa = self.ref_nodes.get(a.upper(), set())
        sb = self.runway_nodes if b == "RWY" else self.ref_nodes.get(b.upper(), set())
        common = sa & sb
        if common:
            return next(iter(common))
        if not sa or not sb:
            return None
        # sem nó partilhado: o par de nós mais próximo
        best = min(((_m(self.nodes[x], self.nodes[y]), x) for x in sa for y in sb), default=None)
        return best[1] if best and best[0] < 80 else None

    def path(self, src: int, dst: int, prefer: str | None) -> list[int]:
        """Dijkstra; arestas fora do taxiway 'prefer' custam 6× (pista 25×) para seguir a sequência."""
        if src == dst:
            return [src]
        pref = prefer.upper() if prefer else None
        dist = {src: 0.0}; prev = {}; pq = [(0.0, src)]
        while pq:
            d, n = heapq.heappop(pq)
            if n == dst:
                break
            if d > dist.get(n, math.inf):
                continue
            for m, L, ref, typ in self.adj.get(n, []):
                w = L * (1.0 if (pref and ref and ref.upper() == pref) else 25.0 if typ == "runway" else 6.0)
                nd = d + w
                if nd < dist.get(m, math.inf):
                    dist[m] = nd; prev[m] = n; heapq.heappush(pq, (nd, m))
        if dst not in prev:
            return []
        out = [dst]
        while out[-1] != src:
            out.append(prev[out[-1]])
        return out[::-1]

    # ------------------------------------------------------------------ rotas
    def taxi_route(self, stand: str | None, seq: list[str], hp: str | None, kind: str):
        """Devolve (pontos [(lat,lon)], anchors {nome: índice}) do percurso no solo.
        kind='dep': stand → seq → HP → entrada na pista ; kind='arr': saída de pista (EP) → seq → stand."""
        seq = [s.upper() for s in seq if s and s.upper() != "RWY20" and s.upper() != "RWY02"]
        if kind == "arr":
            seq = seq[:]  # já vem na ordem de circulação (saída de pista → stand)
        pts: list[tuple[float, float]] = []
        anchors: dict[str, int] = {}
        node_seq: list[int] = []
        # pontos-chave: junções consecutivas
        chain = list(seq)
        if kind == "dep" and hp and (not chain or chain[-1] != hp.upper()):
            chain.append(hp.upper())
        if kind == "arr" and hp and (not chain or chain[0] != hp.upper()):
            chain.insert(0, hp.upper())
        chain = [c for c in chain if c in self.ref_nodes]
        if not chain:
            return [], {}
        if kind == "dep":
            start = self.nearest_node(self.stands[stand], self.ref_nodes[chain[0]]) if stand in self.stands else None
            targets = [self.junction(chain[i], chain[i + 1]) for i in range(len(chain) - 1)] + [self.junction(chain[-1], "RWY")]
            cur = start if start is not None else self.nearest_node(self.nodes[next(iter(self.ref_nodes[chain[0]]))], self.ref_nodes[chain[0]])
            if stand in self.stands:
                pts.append(self.stands[stand]); anchors["stand"] = 0
            node_seq.append(cur)
            for i, t in enumerate(targets):
                if t is None:
                    continue
                seg = self.path(cur, t, chain[i] if i < len(chain) else chain[-1])
                node_seq += seg[1:]; cur = t
                if i == len(targets) - 2 or (len(targets) == 1 and i == 0):
                    anchors["hp"] = len(pts) + len(node_seq) - 1
            pts += [self.nodes[n] for n in node_seq]
            anchors["rwy_ent"] = len(pts) - 1
            if "hp" not in anchors:
                anchors["hp"] = max(0, len(pts) - 2)
        else:
            entry = self.junction(chain[0], "RWY")
            targets = [self.junction(chain[i], chain[i + 1]) for i in range(len(chain) - 1)]
            end = self.nearest_node(self.stands[stand], self.ref_nodes[chain[-1]]) if stand in self.stands else None
            cur = entry if entry is not None else next(iter(self.ref_nodes[chain[0]]))
            node_seq.append(cur); anchors["rwy_vac"] = 0
            for i, t in enumerate(targets):
                if t is None:
                    continue
                seg = self.path(cur, t, chain[i]); node_seq += seg[1:]; cur = t
            if end is not None:
                seg = self.path(cur, end, chain[-1]); node_seq += seg[1:]
            pts = [self.nodes[n] for n in node_seq]
            if stand in self.stands:
                pts.append(self.stands[stand])
            anchors["stand"] = len(pts) - 1
        return pts, anchors

    def runway_segment(self, rwy: str, kind: str, exit_pt=None, frac_liftoff=0.45):
        """Troço de pista: dep = entrada → ponto de rotação (frac do comprimento);
        arr = soleira → ponto de saída (exit_pt)."""
        thr_from = (self.thr.get(rwy) or {}).get("thr"); thr_to = (self.thr.get(self._opposite(rwy)) or {}).get("thr")
        if not thr_from or not thr_to:
            return []
        if kind == "arr":
            if exit_pt is None:
                return [thr_from]
            # projeta a saída no eixo da pista
            L = _m(thr_from, thr_to)
            d = _m(thr_from, exit_pt)
            f = max(0.0, min(1.0, d / L))
            return [thr_from, (thr_from[0] + (thr_to[0] - thr_from[0]) * f, thr_from[1] + (thr_to[1] - thr_from[1]) * f)]
        return [(thr_from[0] + (thr_to[0] - thr_from[0]) * frac_liftoff, thr_from[1] + (thr_to[1] - thr_from[1]) * frac_liftoff)]

    @staticmethod
    def _opposite(rwy: str) -> str:
        n = int(rwy[:2]); s = rwy[2:]
        o = (n + 18 - 1) % 36 + 1
        return f"{o:02d}" + {"L": "R", "R": "L"}.get(s, s)


@lru_cache(maxsize=4)
def airfield(airport="LPPT") -> Airfield:
    return Airfield(airport)


def cumdist(pts) -> list[float]:
    out = [0.0]
    for a, b in zip(pts, pts[1:]):
        out.append(out[-1] + _m(a, b))
    return out


def build_movement(row: dict, af: Airfield) -> dict | None:
    """Percurso completo (solo + pista) com tempo em cada ponto, para animação.
    row: registo da tabela ground (tempos em epoch s ou None)."""
    kind = "dep" if row["mt"] == "DEPARTURE" else "arr"
    rwy = row.get("rwy") or ""
    seq = (row.get("taxi_out") if kind == "dep" else row.get("taxi_in") or "").split()
    stand = row.get("stand_d") if kind == "dep" else row.get("stand_a")
    pts, anchors = af.taxi_route(stand, seq, row.get("hp") if kind == "dep" else row.get("ep"), kind)
    if not pts:
        return None
    times: dict[int, float] = {}
    if kind == "dep":
        rw = af.runway_segment(rwy, "dep")
        i_ent = anchors.get("rwy_ent", len(pts) - 1)
        pts = pts + rw
        t_aobt, t_hp, t_ent, t_atot = row.get("aobt"), row.get("hp_time"), row.get("rwy_ent"), row.get("atot")
        if t_atot is None:
            return None
        if t_ent is None: t_ent = t_atot - 45
        if t_hp is None: t_hp = t_ent - 60
        if t_aobt is None: t_aobt = t_hp - 10 * 60
        times[anchors.get("stand", 0)] = t_aobt
        times[anchors.get("hp", i_ent)] = min(t_hp, t_ent)
        times[i_ent] = t_ent
        times[len(pts) - 1] = t_atot
    else:
        t_aldt, t_vac, t_aibt = row.get("aldt"), row.get("rwy_vac"), row.get("aibt")
        if t_aldt is None and t_vac is None:
            return None
        if t_vac is None: t_vac = t_aldt + 50
        if t_aldt is None: t_aldt = t_vac - 50
        if t_aibt is None: t_aibt = t_vac + 5 * 60
        rw = af.runway_segment(rwy, "arr", exit_pt=pts[0])
        off = len(rw)
        pts = rw + pts
        times[0] = t_aldt
        times[off] = t_vac
        times[len(pts) - 1] = t_aibt
    # interpolação por distância entre âncoras
    cd = cumdist(pts)
    keys = sorted(times)
    tt = [None] * len(pts)
    for k in keys:
        tt[k] = times[k]
    for a, b in zip(keys, keys[1:]):
        da, db = cd[a], cd[b]
        for i in range(a + 1, b):
            f = (cd[i] - da) / (db - da) if db > da else 0
            tt[i] = times[a] + (times[b] - times[a]) * f
    # garante monotonia
    for i in range(1, len(tt)):
        if tt[i] is None or tt[i] < tt[i - 1]:
            tt[i] = tt[i - 1]
    return {"kind": kind, "pts": [[round(p[0], 6), round(p[1], 6)] for p in pts], "t": [round(x, 1) for x in tt],
            "anchors": anchors, "len_m": round(cd[-1]), "t0": tt[0], "t1": tt[-1]}


def _pct(v, p):
    if not v:
        return None
    v = sorted(v); k = (len(v) - 1) * p
    f = int(k); c = min(f + 1, len(v) - 1)
    return v[f] + (v[c] - v[f]) * (k - f)


def _stats(vals):
    vals = [v for v in vals if v is not None and 0 < v < 1800]
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "mean": sum(vals) / len(vals), "median": _pct(vals, .5), "p10": _pct(vals, .1), "p90": _pct(vals, .9),
            "min": min(vals), "max": max(vals)}


def ground_stats(rows: list[dict]) -> dict:
    """Tempos de ocupação de pista (ROT) e de taxi a partir dos tempos reais do A-SMGCS."""
    arr = [r for r in rows if r["mt"] != "DEPARTURE"]; dep = [r for r in rows if r["mt"] == "DEPARTURE"]
    def by(key, rows_, field):
        g = {}
        for r in rows_:
            k = r.get(key) or "?"
            g.setdefault(k, []).append(r.get(field))
        return sorted(({"key": k, **_stats(v)} for k, v in g.items()), key=lambda x: -x["n"])
    def hist(vals, edges):
        vals = [v for v in vals if v is not None]
        counts = [0] * (len(edges) + 1)
        for v in vals:
            i = 0
            while i < len(edges) and v >= edges[i]:
                i += 1
            counts[i] += 1
        labels = [f"<{edges[0]}"] + [f"{a}-{b}" for a, b in zip(edges, edges[1:])] + [f">{edges[-1]}"]
        return {"labels": labels, "counts": counts}
    return {
        "n_arr": len(arr), "n_dep": len(dep), "ga": sum(1 for r in rows if r.get("ga")),
        "rot_arr": _stats([r["rot_s"] for r in arr]), "rot_dep": _stats([r["rot_s"] for r in dep]),
        "taxi_in": _stats([r["taxi_s"] for r in arr]), "taxi_out": _stats([r["taxi_s"] for r in dep]),
        "rot_arr_by_ep": by("ep", arr, "rot_s"), "rot_arr_by_wtc": by("wtc", arr, "rot_s"), "rot_arr_by_rwy": by("rwy", arr, "rot_s"),
        "rot_dep_by_hp": by("hp", dep, "rot_s"), "rot_dep_by_wtc": by("wtc", dep, "rot_s"), "rot_dep_by_rwy": by("rwy", dep, "rot_s"),
        "taxi_in_by_stand": by("stand_a", arr, "taxi_s")[:15], "taxi_out_by_stand": by("stand_d", dep, "taxi_s")[:15],
        "rot_arr_hist": hist([r["rot_s"] for r in arr], [30, 40, 50, 60, 70, 80, 90, 120]),
        "rot_dep_hist": hist([r["rot_s"] for r in dep], [20, 30, 40, 50, 60, 70, 80, 120]),
        "spd_vac": _stats([r.get("spd_vac") for r in arr if r.get("spd_vac")]),
    }
