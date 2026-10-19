"""Geometria aeronáutica e configuração de aeroportos/pistas (valores iguais à app antiga)."""
from __future__ import annotations

import json
import math
from datetime import date
from functools import lru_cache

from .db import resource_path

R_NM = 3440.065

AIRPORTS = {
    "LPPT": {"name": "Lisboa (LPPT)", "center": (38.7813, -9.1359), "elev": 374, "rwys": {
        "02": {"thr": (38.766428, -9.143903), "brg": 32.0, "elev": 357},
        "20": {"thr": (38.792331, -9.130047), "brg": 212.0, "elev": 303}}},
    "LPPR": {"name": "Porto (LPPR)", "center": (41.2481, -8.6814), "elev": 227, "rwys": {
        "17": {"thr": (41.260681, -8.684561), "brg": 171.0, "elev": 151},
        "35": {"thr": (41.233886, -8.677536), "brg": 351.0, "elev": 227}}},
    "LPFR": {"name": "Faro (LPFR)", "center": (37.0153, -7.9723), "elev": 24, "rwys": {
        "10": {"thr": (37.017222, -7.985614), "brg": 101.0, "elev": 24},
        "28": {"thr": (37.013450, -7.959042), "brg": 281.0, "elev": 18}}},
    "LPMA": {"name": "Funchal (LPMA)", "center": (32.6978, -16.7745), "elev": 191, "rwys": {
        "05": {"thr": (32.689932, -16.783751), "brg": 47.0, "elev": 146},
        "23": {"thr": (32.705841, -16.765150), "brg": 227.0, "elev": 191}}},
}


def _fix_runway_bearings():
    """Rumo verdadeiro do eixo calculado entre as duas soleiras (a app antiga usava o rumo magnético do AIP,
    o que deslocava o eixo ~1,2 NM a 11 NM da THR e invalidava o critério de 'estabilizada')."""
    for apt in AIRPORTS.values():
        rws = list(apt["rwys"].items())
        if len(rws) == 2:
            (ra, a), (rb, b) = rws
            a["brg"] = bearing_deg(*a["thr"], *b["thr"])
            b["brg"] = bearing_deg(*b["thr"], *a["thr"])


def dist_nm(lat1, lon1, lat2, lon2) -> float:
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R_NM * 2 * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def project_point(lat, lon, brg, d_nm):
    b = math.radians(brg)
    la1, lo1 = math.radians(lat), math.radians(lon)
    ad = d_nm / R_NM
    la2 = math.asin(math.sin(la1) * math.cos(ad) + math.cos(la1) * math.sin(ad) * math.cos(b))
    lo2 = lo1 + math.atan2(math.sin(b) * math.sin(ad) * math.cos(la1), math.cos(ad) - math.sin(la1) * math.sin(la2))
    return math.degrees(la2), math.degrees(lo2)


def approach_coords(lat, lon, thr_lat, thr_lon, land_brg):
    """along (NM, >0 = ainda antes da THR), cross (NM, assinado) no eixo de aproximação."""
    d = dist_nm(thr_lat, thr_lon, lat, lon)
    if d == 0:
        return 0.0, 0.0
    br = bearing_deg(thr_lat, thr_lon, lat, lon)
    app = (land_brg + 180) % 360
    delta = br - app
    while delta > 180: delta -= 360
    while delta <= -180: delta += 360
    dr = math.radians(delta)
    return d * math.cos(dr), d * math.sin(dr)


def runway_coords_m(lat, lon, thr_lat, thr_lon, rwy_brg):
    """Como approach_coords mas em metros e no sentido da pista (along>0 = pista adentro)."""
    d = dist_nm(thr_lat, thr_lon, lat, lon) * 1852.0
    if d < 0.5:
        return 0.0, 0.0
    br = bearing_deg(thr_lat, thr_lon, lat, lon)
    delta = br - rwy_brg
    while delta > 180: delta -= 360
    while delta <= -180: delta += 360
    dr = math.radians(delta)
    return d * math.cos(dr), d * math.sin(dr)


_fix_runway_bearings()


def to_dms(deg: float, is_lat: bool) -> str:
    h = ("N" if deg >= 0 else "S") if is_lat else ("E" if deg >= 0 else "W")
    a = abs(deg)
    d = int(a); m = int((a - d) * 60); s = (a - d - m / 60) * 3600
    return f"{d:02d}°{m:02d}'{s:05.2f}\"{h}"


# ------------------------------------------------------------------ datas / tempo
def day_index(yymmdd: str) -> int:
    """Dias desde 2000-01-01 (calendário real) — para 'epoch' comparável entre dias."""
    if not yymmdd or len(yymmdd) != 6 or not yymmdd.isdigit():
        return 0
    try:
        return (date(2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])) - date(2000, 1, 1)).days
    except ValueError:
        return 0


def epoch(yymmdd: str, tod_sec: float) -> float:
    return day_index(yymmdd) * 86400.0 + tod_sec


def hhmmss(sec: float) -> str:
    if sec is None or not math.isfinite(sec):
        return "--:--:--"
    s = int(round(((sec % 86400) + 86400) % 86400))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def fmt_date(yymmdd: str) -> str:
    if not yymmdd or yymmdd == "??":
        return "Data desconhecida"
    if len(yymmdd) == 6:
        return f"{yymmdd[4:6]}/{yymmdd[2:4]}/20{yymmdd[0:2]}"
    return yymmdd


def weekday(yymmdd: str) -> int:
    """0=Domingo … 6=Sábado (como JS getDay)."""
    try:
        return (date(2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])).weekday() + 1) % 7
    except (ValueError, TypeError):
        return 0


WD_SHORT = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
WD_LONG = ["Domingo", "Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado"]


def company(csn: str) -> str:
    """companyFromCallsign da app antiga: 2-4 letras iniciais seguidas de dígito."""
    import re
    s = (csn or "").strip().upper()
    if not s:
        return "SEM CSN"
    m = re.match(r"^([A-Z]{2,4})(?=\d)", s)
    if m:
        return m.group(1)
    m = re.match(r"^([A-Z]{2,4})", s)
    return m.group(1) if m else s[:4]


def operator3(csn: str) -> str:
    """Regra ^[A-Z]{2,3} (IAS por operador, RRMS, IA)."""
    import re
    m = re.match(r"^([A-Z]{2,3})", (csn or "").upper())
    return m.group(1) if m else "???"


# ------------------------------------------------------------------ pontos AIP
@lru_cache(maxsize=1)
def aip_points() -> list[dict]:
    return json.loads(resource_path("data", "aip_points.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def point_groups() -> dict:
    return json.loads(resource_path("data", "point_groups.json").read_text(encoding="utf-8"))


def points_by_name(extra: list[dict] | None = None) -> dict[str, dict]:
    """Nome (maiúsculas) → ponto. Última ocorrência prevalece (como na app antiga)."""
    out = {}
    for p in aip_points():
        out[str(p["name"]).upper()] = p
    for p in extra or []:
        out[str(p["name"]).upper()] = p
    return out


def airport_points(airport: str, extra: list[dict] | None = None) -> list[dict]:
    """Pontos do aeroporto: com tag do ICAO em desc, ou (LPPT) os que pertencem a algum grupo."""
    groups = point_groups()
    all_names = set(n for g in groups.values() for n in g)
    out = []
    for p in aip_points():
        desc = p.get("desc", "") or ""
        if airport in desc:
            out.append(p)
        elif airport == "LPPT" and p["name"].upper() in all_names:
            out.append(p)
    return out + list(extra or [])


# ------------------------------------------------------------------ limites de velocidade
LPPT_STAR_IAS_DEFAULTS = {
    "ESUTI": 280, "INBOM": 280, "LAZET": 280, "LUVUP": 280, "PULPO": 280, "VATZI": 280, "XAMAX": 280, "ESEBI": 250,
    "UNPOT": 250, "CASLU": 230, "NATID": 230, "RULOX": 250, "GANSU": 250, "EXONA": 250, "LUXUT": 250, "ODLIX": 230,
    "MAZUK": 220, "ERNIL": 220, "RELKU": 220, "ZEFFI": 220, "NEVUD": 180,
    "EKLID": 220, "ROTBU": 220, "LERLI": 220, "FADEF": 220, "COCUN": 180,
    "YETSI": 230, "ORTUG": 220, "ZACRA": 220, "INLIB": 220, "MIGTO": 220, "ULTIT": 180,
    "ITAVIT": 230, "DEKKI": 220, "ROMEP": 220, "EVPAP": 220, "FUSSI": 220, "ARNIT": 180,
    "PESEX": 180, "UPKAT": 180,
}

APP_IAS_DEFAULTS = {
    "APP_02": {"PESEX": 180, "NETVO": 160, "OKNIB": 160, "THR02": 160},
    "APP_20": {"UPKAT": 180, "TOPVI": 160, "ROKOB": 160, "THR20": 160},
    "LPPR_APP_17": {"ADNOV": 180, "PR741": 180, "PR742": 180, "THR17": 180},
    "LPPR_APP_35": {"AKULU": 180, "PR541": 180, "PR542": 180, "THR35": 180},
    "LPFR_APP_10": {"RUWIB": 180, "FR910": 180, "THR10": 180},
    "LPFR_APP_28": {"GEBTI": 180, "FR928": 180, "THR28": 180},
}
APP_POINT_ORDER = {
    "APP_02": ["PESEX", "NETVO", "OKNIB", "THR02"],
    "APP_20": ["UPKAT", "TOPVI", "ROKOB", "THR20"],
    "LPPR_APP_17": ["ADNOV", "PR741", "PR742", "THR17"],
    "LPPR_APP_35": ["AKULU", "PR541", "PR542", "THR35"],
    "LPFR_APP_10": ["RUWIB", "FR910", "THR10"],
    "LPFR_APP_28": ["GEBTI", "FR928", "THR28"],
}
APP_MODES = {"LPPT": ["APP_02", "APP_20"], "LPPR": ["LPPR_APP_17", "LPPR_APP_35"], "LPFR": ["LPFR_APP_10", "LPFR_APP_28"]}

# escala da final (AIP LPPT AD 2.24.12)
APP_DIST_WAYPOINTS = {
    "02": [{"name": "PESEX", "nm": 11.3, "limit": 180, "scalePt": 11.5}, {"name": "NETVO", "nm": 8.2, "limit": 160, "scalePt": 8.0},
           {"name": "OKNIB", "nm": 4.2, "limit": 160, "scalePt": 4.0}, {"name": "THR 02", "nm": 0.0, "limit": 160, "scalePt": 0.0}],
    "20": [{"name": "UPKAT", "nm": 11.3, "limit": 180, "scalePt": 11.5}, {"name": "TOPVI", "nm": 8.2, "limit": 160, "scalePt": 8.0},
           {"name": "ROKOB", "nm": 3.96, "limit": 160, "scalePt": 4.0}, {"name": "THR 20", "nm": 0.0, "limit": 160, "scalePt": 0.0}],
}


def app_dist_limit_at(d: float) -> int:
    if d >= 8.2: return 180
    if d >= 4.0: return 160
    return int(round(135 + (d / 4.0) * (160 - 135)))


# RRMS (LPPT)
RRMS_POINTS = {
    "02": {"lat": 38 + 47 / 60 + 10.93 / 3600, "lon": -(9 + 7 / 60 + 59.65 / 3600), "label": "RWY 02 · TWY U6 · 2400m"},
    "20": {"lat": 38 + 46 / 60 + 20.54 / 3600, "lon": -(9 + 8 / 60 + 26.60 / 3600), "label": "RWY 20 · TWY P · 2400m"},
}
RRMS_RADIUS_NM = 0.40

WTC_H = set("A332 A333 A338 A339 A342 A343 A345 A346 A359 A35K A388 B744 B748 B762 B763 B764 B772 B773 B77L B77W B788 B789 B78X A306 A30B B742 B741 DC10 MD11 IL76".split())
WTC_L = set("C172 C182 C152 C208 C210 PA28 PA31 B06 R44 EC35 B350 PC12 TBM7 TBM8 TBM9 PC6T DA40 DA42 DA50 SR20 SR22 SR2T P28A AA5B M20T BE58 BE60 C337 P180".split())
PREFIX_TYPES = {"TAP": "A20N", "RYR": "B38M", "EJU": "A320", "EZY": "A320", "VLG": "A320", "IBE": "A320", "BAW": "B772", "DLH": "A321",
                "AFR": "A321", "KLM": "B738", "WZZ": "A320", "BEL": "A319", "SWR": "BCS3", "NAX": "A320", "THY": "A321", "UAE": "B77W", "QTR": "B773"}
HEAVY_PREFIX = {"BAW", "UAE", "QTR", "THY", "ANA", "JAL", "AAL", "UAL", "DAL", "FIN", "ELY", "TAM", "LAN", "GOL"}
MEDIUM_PREFIX = set("RYR EJU EZY VLG TAP IBE IBS AFR KLM DLH SWR TUI TOM WZZ WUK LOT CSA ROU BEL ETF NAX SAS AEE VKG ASL TVF TVS THY BTI AUI HYS RAM MSR RZO SXS ONT ONS".split())


def wtc_from_type(t: str | None) -> str:
    if not t: return "?"
    t = t.upper()
    if t in WTC_H: return "H"
    if t in WTC_L: return "L"
    return "M"


def wake_cat_heuristic(csn: str) -> str:
    import re
    pre = re.sub(r"\d.*", "", csn or "").upper()
    num = re.sub(r"\D", "", csn or "")
    if pre in HEAVY_PREFIX or (pre == "TAP" and num.isdigit() and 200 <= int(num) <= 499):
        return "H"
    if pre in MEDIUM_PREFIX:
        return "M"
    return "?"
