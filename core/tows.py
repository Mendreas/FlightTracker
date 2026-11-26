"""Reboques (towing) de aeronaves: leitura do registo em Excel, emparelhamento com o radar de solo
(CNS, TGO) para encontrar o alvo rebocado e o veículo que o acompanhou (follow-me), e estatísticas.

O registo em Excel tem uma linha por reboque: data, hora de início/fim, stand de origem/destino, rota
(taxiways), cruzamento de pista (Sim/Não), categoria (M/H/L) e duração. As horas vêm do registo manual:
por defeito assume-se hora de Lisboa e confirma-se contra o radar ('auto'). Não há coordenadas dos stands,
por isso o emparelhamento usa o tempo e o movimento conjunto dos alvos (o follow-me segue o reboque a
poucas dezenas de metros)."""
from __future__ import annotations

import datetime as dt
import math
import unicodedata

from .geo import AIRPORTS

MOVING_KT = 1.5          # abaixo disto considera-se parado
MAX_TOW_KT = 45.0        # um reboque (ou follow-me) nunca passa disto
CLOSE_M = 120.0          # distância máxima entre reboque e acompanhante para contarem como "juntos"
WINDOW_TOL = (90.0, 150.0)   # folga antes do início / depois do fim (o Excel tem resolução de minuto)


# ----------------------------------------------------------------------------- tempo
def _last_sunday(year: int, month: int) -> dt.date:
    d = dt.date(year, month + 1, 1) - dt.timedelta(days=1) if month < 12 else dt.date(year, 12, 31)
    return d - dt.timedelta(days=(d.weekday() + 1) % 7)


def lisbon_offset_s(utc_epoch: float) -> int:
    """UTC→hora de Lisboa: +1 h entre o último domingo de março e o último de outubro (01:00 UTC)."""
    y = dt.datetime.fromtimestamp(utc_epoch, dt.timezone.utc).year
    s = dt.datetime.combine(_last_sunday(y, 3), dt.time(1), dt.timezone.utc).timestamp()
    e = dt.datetime.combine(_last_sunday(y, 10), dt.time(1), dt.timezone.utc).timestamp()
    return 3600 if s <= utc_epoch < e else 0


def day_epoch(date: str) -> float:
    return dt.datetime(2000 + int(date[:2]), int(date[2:4]), int(date[4:6]), tzinfo=dt.timezone.utc).timestamp()


def epoch_date(epoch: float) -> tuple[str, float]:
    d = dt.datetime.fromtimestamp(epoch, dt.timezone.utc)
    return d.strftime("%y%m%d"), epoch - day_epoch(d.strftime("%y%m%d"))


def to_utc(date: str, sec: float, tz: str) -> float:
    """Hora escrita no Excel (segundos desde as 00:00 da data) → epoch UTC. tz: 'lisboa' | 'utc'."""
    wall = day_epoch(date) + sec
    if tz == "utc":
        return wall
    guess = wall - 3600
    return guess if lisbon_offset_s(guess) == 3600 else wall


# ----------------------------------------------------------------------------- Excel
def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return "".join(c for c in s if c.isalnum())


def _sec(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, dt.datetime):
        return v.hour * 3600 + v.minute * 60 + v.second
    if isinstance(v, dt.time):
        return v.hour * 3600 + v.minute * 60 + v.second
    if isinstance(v, (int, float)):
        return (float(v) % 1.0) * 86400.0
    try:
        p = [float(x) for x in str(v).strip().split(":")]
        return p[0] * 3600 + (p[1] if len(p) > 1 else 0) * 60 + (p[2] if len(p) > 2 else 0)
    except (ValueError, IndexError):
        return None


def _date(v) -> str | None:
    if isinstance(v, (dt.datetime, dt.date)):
        return v.strftime("%y%m%d")
    s = str(v or "").strip()
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(s[:10], f).strftime("%y%m%d")
        except ValueError:
            pass
    return None


def _txt(v) -> str | None:
    s = str(v).strip() if v is not None else ""
    return s or None


def read_tows_excel(path: str) -> list[dict]:
    """Lê o Excel de reboques. Colunas reconhecidas pelo cabeçalho: Data, Início, Fim, Rasto, Schengen, De, Para,
    Rota, Cruzamento de pista, Duração registada (min), Observações."""
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    hdr = None
    for row in it:
        names = [_norm(c) for c in row]
        if "data" in names and any(n.startswith("inicio") for n in names):
            hdr = names
            break
    if hdr is None:
        raise RuntimeError("Não encontrei o cabeçalho (Data, Início, Fim, …) na primeira folha do Excel.")

    def col(*opts):
        for o in opts:
            for i, n in enumerate(hdr):
                if n == o or (len(o) > 4 and n.startswith(o)):
                    return i
        return None
    ix = {"data": col("data"), "t0": col("inicio"), "t1": col("fim"), "wtc": col("rasto", "categoria"), "sch": col("schengen"),
          "de": col("de"), "para": col("para"), "rota": col("rota"), "cruz": col("cruzamentodepista", "cruzamento"),
          "dur": col("duracaoregistada", "duracao"), "obs": col("observacoes")}
    if ix["data"] is None or ix["t0"] is None or ix["t1"] is None:
        raise RuntimeError("Faltam as colunas Data / Início / Fim.")
    out = []
    for n, row in enumerate(it, 1):
        g = lambda k: row[ix[k]] if ix[k] is not None and ix[k] < len(row) else None  # noqa: E731
        d, a, b = _date(g("data")), _sec(g("t0")), _sec(g("t1"))
        if not d or a is None or b is None:
            continue
        if b < a:
            b += 86400
        cr = _txt(g("cruz"))
        dur = g("dur")
        out.append({"date": d, "t0": a, "t1": b, "wtc": (_txt(g("wtc")) or "").upper() or None, "schengen": _txt(g("sch")),
                    "de": (_txt(g("de")) or "").upper() or None, "para": (_txt(g("para")) or "").upper() or None,
                    "rota": _txt(g("rota")), "cruz": cr, "dur_reg": float(dur) if isinstance(dur, (int, float)) else None,
                    "obs": _txt(g("obs"))})
    out.sort(key=lambda r: (r["date"], r["t0"]))
    for i, r in enumerate(out, 1):
        r["tid"] = i
    return out


def cruz_flag(v) -> bool | None:
    s = _norm(v)
    return True if s in ("sim", "s", "yes", "1") else False if s in ("nao", "n", "no", "0") else None


# ----------------------------------------------------------------------------- geometria
class _XY:
    def __init__(self, lat0: float, lon0: float):
        self.lat0, self.lon0 = lat0, lon0
        self.kx = 111320.0 * math.cos(math.radians(lat0))

    def __call__(self, lat, lon):
        return ((lon - self.lon0) * self.kx, (lat - self.lat0) * 110540.0)


def _interp(t, ts, vals, i0=0):
    """Interpolação linear em ts (crescente); devolve (valor, índice)."""
    n = len(ts)
    if t <= ts[0]:
        return vals[0], 0
    if t >= ts[-1]:
        return vals[-1], n - 1
    i = i0
    while i < n - 2 and ts[i + 1] < t:
        i += 1
    f = (t - ts[i]) / (ts[i + 1] - ts[i]) if ts[i + 1] > ts[i] else 0.0
    return vals[i] + (vals[i + 1] - vals[i]) * f, i


class Leg:
    """Percurso de um alvo do radar de solo (pode juntar vários troços do mesmo veículo)."""
    __slots__ = ("key", "csn", "modes", "t", "x", "y", "lat", "lon", "gs")

    def __init__(self, key, csn, modes):
        self.key, self.csn, self.modes = key, csn, modes
        self.t, self.x, self.y, self.lat, self.lon, self.gs = [], [], [], [], [], []

    @property
    def t0(self):
        return self.t[0]

    @property
    def t1(self):
        return self.t[-1]

    def add(self, t, x, y, lat, lon, gs):
        self.t.append(t); self.x.append(x); self.y.append(y); self.lat.append(lat); self.lon.append(lon); self.gs.append(gs or 0.0)

    def label(self) -> str:
        if self.csn and self.csn != "(SEM ID)":
            return self.csn
        k = str(self.key or "?")
        return "alvo " + (k.lstrip("#") if k.startswith("#") else k)

    def has_id(self) -> bool:
        return bool(self.csn) or bool(self.modes)


def build_legs(rows, xy: _XY, gap_s: float = 120.0) -> list[Leg]:
    """rows: (k, t_epoch, lat, lon, gs, csn, modes) ordenado por k, t."""
    legs, cur, last_k, last_t = [], None, None, None
    for k, t, la, lo, gs, csn, ms in rows:
        if k != last_k or t - last_t > gap_s:
            cur = Leg(k, csn or None, ms)
            legs.append(cur)
        x, y = xy(la, lo)
        cur.add(t, x, y, la, lo, gs)
        last_k, last_t = k, t
    return legs


def _moving_time(leg: Leg, a: float, b: float) -> float:
    s = 0.0
    for i in range(1, len(leg.t)):
        if leg.t[i] < a or leg.t[i - 1] > b:
            continue
        dt_ = leg.t[i] - leg.t[i - 1]
        if dt_ <= 12 and (leg.gs[i] >= MOVING_KT or leg.gs[i - 1] >= MOVING_KT):
            s += dt_
    return s


def _slice(leg: Leg, a: float, b: float) -> Leg | None:
    idx = [i for i, t in enumerate(leg.t) if a <= t <= b]
    if len(idx) < 3:
        return None
    s = Leg(leg.key, leg.csn, leg.modes)
    for i in idx:
        s.add(leg.t[i], leg.x[i], leg.y[i], leg.lat[i], leg.lon[i], leg.gs[i])
    return s


def _trim_moving(leg: Leg) -> Leg:
    """Remove as pontas paradas (parqueado antes/depois), mantendo 1 ponto de margem."""
    mv = [i for i, g in enumerate(leg.gs) if g >= MOVING_KT]
    if not mv:
        return leg
    i0, i1 = max(0, mv[0] - 1), min(len(leg.t) - 1, mv[-1] + 1)
    s = Leg(leg.key, leg.csn, leg.modes)
    for i in range(i0, i1 + 1):
        s.add(leg.t[i], leg.x[i], leg.y[i], leg.lat[i], leg.lon[i], leg.gs[i])
    return s


def _stitch(subs: list[Leg]) -> list[Leg]:
    """Une troços que se seguem no tempo e no espaço (o radar de solo muda de nº de pista com frequência)."""
    subs = sorted(subs, key=lambda l: l.t0)
    out: list[Leg] = []
    for s in subs:
        done = False
        for o in out:
            if -3 <= s.t0 - o.t1 <= 40 and math.hypot(s.x[0] - o.x[-1], s.y[0] - o.y[-1]) <= 120:
                if (s.csn or o.csn) and s.csn and o.csn and s.csn != o.csn:
                    continue
                for i in range(len(s.t)):
                    if s.t[i] > o.t1:
                        o.add(s.t[i], s.x[i], s.y[i], s.lat[i], s.lon[i], s.gs[i])
                o.csn = o.csn or s.csn; o.modes = o.modes or s.modes
                done = True
                break
        if not done:
            c = Leg(s.key, s.csn, s.modes)
            for i in range(len(s.t)):
                c.add(s.t[i], s.x[i], s.y[i], s.lat[i], s.lon[i], s.gs[i])
            out.append(c)
    return out


def _comove(A: Leg, B: Leg) -> float:
    """Fração do tempo, em que ambos se movem em simultâneo, em que estão a menos de CLOSE_M um do outro."""
    t0, t1 = max(A.t0, B.t0), min(A.t1, B.t1)
    if t1 - t0 < 16:
        return 0.0
    n = close = 0
    t = t0
    ia = ib = 0
    while t <= t1:
        gA, ia = _interp(t, A.t, A.gs, ia)
        gB, ib = _interp(t, B.t, B.gs, ib)
        if gA >= MOVING_KT and gB >= MOVING_KT:
            xa, _ = _interp(t, A.t, A.x, ia); ya, _ = _interp(t, A.t, A.y, ia)
            xb, _ = _interp(t, B.t, B.x, ib); yb, _ = _interp(t, B.t, B.y, ib)
            n += 1
            if math.hypot(xa - xb, ya - yb) <= CLOSE_M:
                close += 1
        t += 2.0
    return close / n if n >= 8 else 0.0


def _path_len(leg: Leg) -> float:
    return sum(math.hypot(leg.x[i] - leg.x[i - 1], leg.y[i] - leg.y[i - 1]) for i in range(1, len(leg.t)))


def runway_crossings(leg: Leg, airport: str, xy: _XY) -> int:
    """Nº de vezes que o percurso corta o eixo da pista (segmento entre as duas soleiras)."""
    rw = AIRPORTS.get(airport, {}).get("rwys", {})
    thr = [v["thr"] for v in rw.values()]
    if len(thr) != 2:
        return 0
    (ax, ay), (bx, by) = xy(*thr[0]), xy(*thr[1])
    n, inside_prev = 0, False
    for i in range(1, len(leg.t)):
        px, py, qx, qy = leg.x[i - 1], leg.y[i - 1], leg.x[i], leg.y[i]
        d1 = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
        d2 = (bx - ax) * (qy - ay) - (by - ay) * (qx - ax)
        if d1 == 0 and d2 == 0:
            continue
        if (d1 > 0) != (d2 > 0):
            d3 = (qx - px) * (ay - py) - (qy - py) * (ax - px)
            d4 = (qx - px) * (by - py) - (qy - py) * (bx - px)
            if (d3 > 0) != (d4 > 0):
                n += 1
    return n


# ----------------------------------------------------------------------------- emparelhamento
def match_one(legs: list[Leg], a: float, b: float, airport: str, xy: _XY) -> dict:
    """Procura, nos percursos do radar de solo, o reboque que decorreu em [a, b] (epoch UTC)."""
    dur = max(b - a, 60.0)
    lo, hi = a - WINDOW_TOL[0], b + WINDOW_TOL[1]
    subs = []
    for L in legs:
        if L.t1 < lo or L.t0 > hi:
            continue
        s = _slice(L, lo, hi)
        if s is None:
            continue
        s = _trim_moving(s)
        if sum(1 for g in s.gs if g > MAX_TOW_KT) > 2:     # aeronave a rolar/aterrar, não é um reboque
            continue
        subs.append(s)
    cands = []
    for s in _stitch(subs):
        mt = _moving_time(s, lo, hi)
        disp = math.hypot(s.x[-1] - s.x[0], s.y[-1] - s.y[0])
        if mt < 30 or max(disp, _path_len(s) * 0.5) < 80:
            continue
        s_in = _moving_time(s, a - 30, b + 90)
        cands.append((min(1.3, s_in / dur), s))
    res = {"status": "sem radar", "conf": None, "legs": [], "alts": 0}
    if not cands:
        return res
    cands.sort(key=lambda c: -c[0])
    cands = cands[:12]
    n = len(cands)
    C = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            C[i][j] = C[j][i] = _comove(cands[i][1], cands[j][1])
    groups, best = [], None
    for i in range(n):
        mem = [i] + sorted([j for j in range(n) if j != i and C[i][j] >= 0.6], key=lambda j: -C[i][j] * cands[j][0])[:2]
        cov = max(cands[m][0] for m in mem)
        score = cov * (1.0 + 0.3 * (min(len(mem), 2) - 1))
        g = {"mem": mem, "cov": cov, "score": score}
        groups.append(g)
        if best is None or score > best["score"]:
            best = g
    used = set(best["mem"])
    alts = [g for g in groups if not (set(g["mem"]) & used) and g["cov"] >= 0.5 and g["score"] >= 0.6 * best["score"]]
    # alternativas distintas entre si (um mesmo conjunto aparece uma vez por membro)
    alt_sets = {frozenset(g["mem"]) for g in alts}
    res["alts"] = len(alt_sets)
    mem = [cands[m][1] for m in best["mem"]]
    roles = _roles(mem)
    legs_out = []
    for leg, role in zip(mem, roles):
        legs_out.append({"role": role, "label": leg.label(), "csn": leg.csn, "modes": leg.modes, "leg": leg})
    cov = best["cov"]
    two = len(mem) >= 2
    if two and cov >= 0.7 and not alt_sets:
        conf = "alta"
    elif (two and cov >= 0.5) or (cov >= 0.7 and not alt_sets):
        conf = "média"
    else:
        conf = "baixa"
    res.update(status="ok", conf=conf, legs=legs_out, cov=round(min(cov, 1.0), 2), two=two)
    return res


def _roles(mem: list[Leg]) -> list[str]:
    """reboque / acompanhante (follow-me): o follow-me vai sempre à frente do reboque, em relação ao sentido de marcha."""
    if len(mem) == 1:
        return ["reboque"]
    # projecção da posição, no instante de maior velocidade conjunta, sobre o sentido de marcha
    t0 = max(m.t0 for m in mem); t1 = min(m.t1 for m in mem)
    if t1 <= t0:
        return ["alvo A" if i == 0 else "alvo B" for i in range(len(mem))]
    ref = mem[0]
    inside = [i for i in range(len(ref.t)) if t0 <= ref.t[i] <= t1]
    tm = ref.t[max(inside, key=lambda i: ref.gs[i])] if inside else (t0 + t1) / 2
    vx = ref.x[-1] - ref.x[0]; vy = ref.y[-1] - ref.y[0]
    # sentido instantâneo do alvo de referência em tm (mais fiável que o deslocamento total em percursos com curvas)
    i = min(range(len(ref.t)), key=lambda k: abs(ref.t[k] - tm))
    j0, j1 = max(0, i - 3), min(len(ref.t) - 1, i + 3)
    if math.hypot(ref.x[j1] - ref.x[j0], ref.y[j1] - ref.y[j0]) > 3:
        vx, vy = ref.x[j1] - ref.x[j0], ref.y[j1] - ref.y[j0]
    nrm = math.hypot(vx, vy) or 1.0
    proj = []
    for m in mem:
        x, _ = _interp(tm, m.t, m.x); y, _ = _interp(tm, m.t, m.y)
        proj.append((x * vx + y * vy) / nrm)
    order = sorted(range(len(mem)), key=lambda k: -proj[k])
    if proj[order[0]] - proj[order[-1]] < 5:       # lado a lado: não dá para saber quem vai à frente
        ids = [m.has_id() for m in mem]
        if sum(ids) == 1:
            return ["reboque" if i else "acompanhante" for i in ids]
        return ["alvo A" if k == 0 else "alvo B" if k == 1 else "alvo C" for k in range(len(mem))]
    roles = ["outro"] * len(mem)
    roles[order[0]] = "acompanhante"
    roles[order[-1]] = "reboque"
    return roles


# ----------------------------------------------------------------------------- obtenção dos dados
def _fetch_legs(db, airport: str, t_from: float, t_to: float, xy: _XY) -> list[Leg]:
    """Percursos do radar de solo (gradar) em [t_from, t_to] (epoch UTC); a tabela guarda o dia UTC e o segundo do dia."""
    rows = []
    day = day_epoch(epoch_date(t_from)[0])
    while day <= t_to:
        date = epoch_date(day)[0]
        a, b = max(0.0, t_from - day), min(86400.0, t_to - day)
        if b >= a:
            rows += [(k, day + t, la, lo, gs, csn, ms) for k, t, la, lo, gs, csn, ms in db.con.execute(
                """SELECT CASE WHEN csn IS NULL OR csn = '' THEN '#' || block || '/' || coalesce(CAST(trk AS VARCHAR), '?') ELSE csn END AS k,
                          t, lat, lon, gs, csn, modes
                   FROM gradar WHERE airport = ? AND date = ? AND t BETWEEN ? AND ? ORDER BY k, t""", [airport, date, a, b]).fetchall()]
        day += 86400
    rows.sort(key=lambda r: (r[0], r[1]))
    return build_legs(rows, xy)


def _centers():
    from .db import AIRPORT_CENTERS
    return AIRPORT_CENTERS


def match_tows(db, airport: str, tows: list[dict], tz: str = "auto", progress=None) -> tuple[list[dict], str]:
    """Emparelha cada reboque com o radar de solo. Devolve (resultados, fuso usado)."""
    lat0, lon0 = _centers().get(airport, (0.0, 0.0))
    xy = _XY(lat0, lon0)
    if tz == "auto":
        tz = _choose_tz(db, airport, tows, xy)
    out = {}
    by_day: dict[str, list[dict]] = {}
    for r in tows:
        by_day.setdefault(r["date"], []).append(r)
    done = 0
    for date, lst in sorted(by_day.items()):
        spans = [(to_utc(date, r["t0"], tz), to_utc(date, r["t1"] + 59, tz)) for r in lst]
        legs = _fetch_legs(db, airport, min(s[0] for s in spans) - 600, max(s[1] for s in spans) + 600, xy)
        for r, (a, b) in zip(lst, spans):
            m = match_one(legs, a, b, airport, xy)
            m["a"], m["b"] = a, b
            out[r["tid"]] = m
            done += 1
        if progress:
            progress(done, len(tows))
    res = []
    for r in tows:
        m = out[r["tid"]]
        res.append(_summarise(r, m, airport, xy))
    return res, tz


def _choose_tz(db, airport: str, tows: list[dict], xy: _XY) -> str:
    """Escolhe entre hora de Lisboa e UTC pelo que casa melhor com o radar (amostra de reboques)."""
    if not tows:
        return "lisboa"
    step = max(1, len(tows) // 30)
    sample = tows[::step][:30]
    score = {}
    for tz in ("lisboa", "utc"):
        s = 0.0
        for r in sample:
            a, b = to_utc(r["date"], r["t0"], tz), to_utc(r["date"], r["t1"] + 59, tz)
            legs = _fetch_legs(db, airport, a - 600, b + 600, xy)
            m = match_one(legs, a, b, airport, xy)
            if m["status"] == "ok":
                s += m["cov"] * (1.5 if m["two"] else 1.0)
        score[tz] = s
    # em empate (sem radar / hora igual no inverno) vale a hora de Lisboa
    return "utc" if score["utc"] > score["lisboa"] * 1.05 else "lisboa"


def _summarise(r: dict, m: dict, airport: str, xy: _XY) -> dict:
    """Linha final: dados do Excel + o que se encontrou no radar (geometria incluída, comprimida)."""
    row = dict(r)
    row.update(status=m["status"], conf=m["conf"], alts=m.get("alts", 0), utc0=m["a"], utc1=m["b"])
    row.update(rb=None, fm=None, rb_modes=None, fm_modes=None, real_t0=None, real_t1=None, real_dur=None, dist_m=None,
               vmax=None, cruz_radar=None, n_cruz_radar=None, tracks=[])
    if m["status"] != "ok":
        return row
    legs = m["legs"]
    for e in legs:
        L = e["leg"]
        step = 2 if len(L.t) > 400 else 1
        row["tracks"].append({"role": e["role"], "label": e["label"], "t": [round(x, 1) for x in L.t[::step]],
                              "pts": [[round(a, 5), round(b, 5)] for a, b in zip(L.lat[::step], L.lon[::step])],
                              "gs": [round(g, 1) for g in L.gs[::step]]})
        if e["role"] == "reboque" and row["rb"] is None:
            row["rb"], row["rb_modes"] = e["label"], e["modes"]
        elif e["role"] == "acompanhante" and row["fm"] is None:
            row["fm"], row["fm_modes"] = e["label"], e["modes"]
    tow = next((e["leg"] for e in legs if e["role"] == "reboque"), legs[0]["leg"])
    if row["rb"] is None:
        row["rb"], row["rb_modes"] = legs[0]["label"], legs[0]["modes"]
    mv = [i for i, g in enumerate(tow.gs) if g >= MOVING_KT]
    row["real_t0"], row["real_t1"] = tow.t[mv[0]] if mv else tow.t0, tow.t[mv[-1]] if mv else tow.t1
    row["real_dur"] = round(row["real_t1"] - row["real_t0"])
    row["dist_m"] = round(_path_len(tow))
    row["vmax"] = round(max(tow.gs), 1)
    n = runway_crossings(tow, airport, xy)
    row["n_cruz_radar"], row["cruz_radar"] = n, n > 0
    row["cov"] = m.get("cov")
    return row


# ----------------------------------------------------------------------------- estatísticas
def _pct(vals: list[float], p: float):
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * p
    f, c = int(math.floor(k)), int(math.ceil(k))
    return s[f] + (s[c] - s[f]) * (k - f)


def dur_min(r: dict) -> float | None:
    if r.get("dur_reg") is not None:
        return float(r["dur_reg"])
    return (r["t1"] - r["t0"]) / 60.0 if r.get("t1") is not None else None


def _agg(rows: list[dict]) -> dict:
    d = [x for x in (dur_min(r) for r in rows) if x is not None]
    cz = [cruz_flag(r.get("cruz")) for r in rows]
    return {"n": len(rows), "media": sum(d) / len(d) if d else None, "mediana": _pct(d, .5), "min": min(d) if d else None,
            "max": max(d) if d else None, "p90": _pct(d, .9), "total_h": sum(d) / 60.0 if d else 0.0,
            "cruz_sim": sum(1 for c in cz if c is True), "cruz_nao": sum(1 for c in cz if c is False), "cruz_nd": sum(1 for c in cz if c is None)}


def tow_stats(rows: list[dict]) -> dict:
    """Estatísticas dos reboques (rows = linhas do Excel, com ou sem os campos do radar)."""
    def group(keyf):
        g: dict = {}
        for r in rows:
            g.setdefault(keyf(r) or "(vazio)", []).append(r)
        return {k: _agg(v) for k, v in g.items()}
    hour = lambda r: f"{int(r['t0'] // 3600) % 24:02d}h"  # noqa: E731
    month = lambda r: f"20{r['date'][:2]}-{r['date'][2:4]}"  # noqa: E731
    pair = lambda r: f"{r.get('de') or '?'} → {r.get('para') or '?'}"  # noqa: E731
    matched = [r for r in rows if r.get("status") == "ok"]
    both = [r for r in matched if r.get("fm")]
    diffs = [r["real_dur"] / 60.0 - dur_min(r) for r in matched if r.get("real_dur") is not None and dur_min(r) is not None]
    agree = [r for r in matched if r.get("cruz_radar") is not None and cruz_flag(r.get("cruz")) is not None]
    return {"global": _agg(rows), "com_cruz": _agg([r for r in rows if cruz_flag(r.get("cruz")) is True]),
            "sem_cruz": _agg([r for r in rows if cruz_flag(r.get("cruz")) is False]),
            "por_dia": group(lambda r: r["date"]), "por_mes": group(month), "por_hora": group(hour), "por_wtc": group(lambda r: r.get("wtc")),
            "por_schengen": group(lambda r: r.get("schengen")), "por_origem": group(lambda r: r.get("de")), "por_destino": group(lambda r: r.get("para")),
            "por_rota": group(lambda r: r.get("rota")), "por_par": group(pair),
            "radar": {"n": len(rows), "identificados": len(matched), "com_acompanhante": len(both),
                      "conf_alta": sum(1 for r in matched if r.get("conf") == "alta"),
                      "dif_media_min": sum(diffs) / len(diffs) if diffs else None,
                      "cruz_concordam": sum(1 for r in agree if r["cruz_radar"] == cruz_flag(r["cruz"])), "cruz_comparados": len(agree)}}


# ----------------------------------------------------------------------------- exportação (Excel)
def _hm(sec) -> str:
    return "" if sec is None else f"{int(sec // 3600) % 24:02d}:{int(sec % 3600 // 60):02d}"


def _hms_utc(epoch) -> str:
    return "" if epoch is None else dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime("%H:%M:%S")


def _fd(date: str) -> str:
    return f"{date[4:6]}/{date[2:4]}/20{date[:2]}"


def _r1(v):
    return None if v is None else round(v, 1)


def _agg_row(k, a):
    n = a["n"]
    return [k, n, _r1(a["media"]), _r1(a["mediana"]), _r1(a["min"]), _r1(a["max"]), _r1(a["p90"]), _r1(a["total_h"]),
            a["cruz_sim"], round(100.0 * a["cruz_sim"] / n, 1) if n else None]


AGG_HEAD = ["N.º reboques", "Duração média (min)", "Mediana (min)", "Mínima (min)", "Máxima (min)", "P90 (min)", "Tempo total (h)",
            "Com cruzamento de pista", "% com cruzamento"]


def export_sheets(rows: list[dict], tz_used: str, airport: str, with_radar: bool = True) -> list[tuple[str, list[str], list[list]]]:
    st = tow_stats(rows)
    g, rd = st["global"], st["radar"]
    dates = sorted({r["date"] for r in rows})
    tzn = {"lisboa": "hora de Lisboa", "utc": "UTC"}.get(tz_used, tz_used)
    resumo = [["Aeroporto", airport], ["Período", f"{_fd(dates[0])} → {_fd(dates[-1])}" if dates else "—"], ["Dias com reboques", len(dates)],
              ["Horas do Excel interpretadas como", tzn], [None, None],
              ["N.º de reboques", g["n"]], ["Duração média (min)", _r1(g["media"])], ["Duração mediana (min)", _r1(g["mediana"])],
              ["Duração mínima (min)", _r1(g["min"])], ["Duração máxima (min)", _r1(g["max"])], ["Duração P90 (min)", _r1(g["p90"])],
              ["Tempo total em reboque (h)", _r1(g["total_h"])], ["Reboques por dia (média)", round(g["n"] / len(dates), 1) if dates else None], [None, None],
              ["Reboques com cruzamento de pista", g["cruz_sim"]], ["Reboques sem cruzamento de pista", g["cruz_nao"]],
              ["Cruzamento não registado", g["cruz_nd"]],
              ["% com cruzamento de pista", round(100.0 * g["cruz_sim"] / g["n"], 1) if g["n"] else None],
              ["Duração média com cruzamento (min)", _r1(st["com_cruz"]["media"])], ["Duração média sem cruzamento (min)", _r1(st["sem_cruz"]["media"])],
              ["Duração máxima com cruzamento (min)", _r1(st["com_cruz"]["max"])], ["Duração máxima sem cruzamento (min)", _r1(st["sem_cruz"]["max"])]]
    if with_radar:
        resumo += [[None, None], ["Identificados no radar de solo", rd["identificados"]],
                   ["% identificados no radar", round(100.0 * rd["identificados"] / rd["n"], 1) if rd["n"] else None],
                   ["Com veículo acompanhante identificado", rd["com_acompanhante"]], ["Identificações de confiança alta", rd["conf_alta"]],
                   ["Duração radar − Excel, média (min)", _r1(rd["dif_media_min"])],
                   ["Cruzamento de pista: radar concorda com o Excel", f"{rd['cruz_concordam']} de {rd['cruz_comparados']}"]]
    sheets = [("Resumo", ["Indicador", "Valor"], resumo)]

    def grp(name, key, label, order=None, limit=None):
        d = st[key]
        keys = sorted(d, key=order or (lambda k: (-d[k]["n"], str(k))))
        if limit:
            keys = keys[:limit]
        sheets.append((name, [label] + AGG_HEAD, [_agg_row(_fd(k) if key == "por_dia" else k, d[k]) for k in keys]))
    grp("Por dia", "por_dia", "Dia", order=lambda k: k)
    grp("Por mês", "por_mes", "Mês", order=lambda k: k)
    grp("Por hora", "por_hora", "Hora de início (hora do Excel)", order=lambda k: k)
    grp("Por categoria", "por_wtc", "Rasto (categoria M/H/L)")
    grp("Por Schengen", "por_schengen", "Schengen")
    grp("Por origem", "por_origem", "Stand/zona de origem")
    grp("Por destino", "por_destino", "Stand/zona de destino")
    grp("Origem-destino", "por_par", "Origem → destino")
    grp("Por rota", "por_rota", "Rota (taxiways)")
    head = ["Data", "Início (Excel)", "Fim (Excel)", "Rasto", "Schengen", "De", "Para", "Rota", "Cruzamento (Excel)", "Duração registada (min)",
            "Duração calculada (min)", "Observações"]
    if with_radar:
        head += ["Radar: estado", "Confiança", "Reboque (alvo)", "Acompanhante (follow-me)", "Início radar (UTC)", "Fim radar (UTC)", "Duração radar (s)",
                 "Distância (m)", "Vel. máx (kt)", "Cruzou pista (radar)", "N.º cruzamentos (radar)", "Alternativas"]
    det = []
    for r in rows:
        line = [_fd(r["date"]), _hm(r["t0"]), _hm(r["t1"]), r.get("wtc"), r.get("schengen"), r.get("de"), r.get("para"), r.get("rota"), r.get("cruz"),
                r.get("dur_reg"), round((r["t1"] - r["t0"]) / 60.0, 1), r.get("obs")]
        if with_radar:
            line += [r.get("status"), r.get("conf"), r.get("rb"), r.get("fm"), _hms_utc(r.get("real_t0")), _hms_utc(r.get("real_t1")), r.get("real_dur"),
                     r.get("dist_m"), r.get("vmax"), None if r.get("cruz_radar") is None else ("Sim" if r["cruz_radar"] else "Não"),
                     r.get("n_cruz_radar"), r.get("alts") if r.get("status") == "ok" else None]
        det.append(line)
    sheets.append(("Detalhe", head, det))
    return sheets
