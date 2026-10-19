"""Interpretação dos nomes de ficheiro/pastas dos CSV de radar.

Formatos reconhecidos (iguais aos da versão anterior):
  1) LPPT_260415_04-08.csv            -> date=260415, block=04-08
  2) LPFR_2026-03-01_00-04.csv        -> date=260301, block=00-04
  3) ...2026-03-01...00-04...         -> variante solta
Se o nome não tiver data, tenta o nome da pasta onde o ficheiro está.
"""
import re
from pathlib import Path

_RE_AIRPORT = re.compile(r"\b(LP[A-Z]{2})\b", re.I)
_RE_1 = re.compile(r"(\d{6})_(\d{2}-\d{2})")
_RE_2 = re.compile(r"([A-Z]{4})_?(\d{4})-(\d{2})-(\d{2})_(\d{2}-\d{2})", re.I)
_RE_3 = re.compile(r"(\d{4})-(\d{2})-(\d{2}).*?(\d{2})-(\d{2})")

BLOCKS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]


def airport_from_name(name: str):
    m = _RE_AIRPORT.search(name or "")
    return m.group(1).upper() if m else None


def _parse_one(name: str):
    m = _RE_1.search(name)
    if m:
        return {"date": m.group(1), "block": m.group(2), "airport": airport_from_name(name)}
    m = _RE_2.search(name)
    if m:
        return {"date": m.group(2)[-2:] + m.group(3) + m.group(4), "block": m.group(5),
                "airport": m.group(1).upper()}
    m = _RE_3.search(name)
    if m:
        return {"date": m.group(1)[-2:] + m.group(2) + m.group(3),
                "block": f"{m.group(4)}-{m.group(5)}", "airport": airport_from_name(name)}
    return None


def parse_path(path: str):
    """Devolve dict(date, block, airport). date/block = '??' se desconhecidos."""
    p = Path(path)
    r = _parse_one(p.name)
    if r is None:
        # tenta as pastas, da mais próxima para a mais afastada
        for parent in p.parents:
            r = _parse_one(parent.name)
            if r:
                break
    if r is None:
        r = {"date": "??", "block": "??", "airport": None}
    if not r.get("airport"):
        r["airport"] = airport_from_name(str(p))   # None → detetado pela posição dos plots na importação
    return r


def block_from_hour(h: int) -> str:
    if h < 4: return "00-04"
    if h < 8: return "04-08"
    if h < 12: return "08-12"
    if h < 16: return "12-16"
    if h < 20: return "16-20"
    return "20-24"


def date_label(yymmdd: str) -> str:
    """260415 -> 15/04/2026"""
    if not yymmdd or len(yymmdd) != 6 or not yymmdd.isdigit():
        return yymmdd or "??"
    return f"{yymmdd[4:6]}/{yymmdd[2:4]}/20{yymmdd[0:2]}"
