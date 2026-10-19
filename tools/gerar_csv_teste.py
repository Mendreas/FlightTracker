"""Gera CSV sintéticos (formato semelhante ao do CNS) para testar o FlightTracker sem dados reais.

Uso:  python tools/gerar_csv_teste.py PASTA_DESTINO [dias] [voos_por_bloco]
Cria PASTA_DESTINO/LPPT_2604DD_HH-HH.csv para cada dia/bloco.
"""
import csv
import math
import random
import sys
from pathlib import Path

THR02 = (38.766428, -9.143903)
THR20 = (38.792331, -9.130047)
AIRLINES = ["TAP", "RYR", "EJU", "KLM", "AFR", "RZO", "THY", "BAW", "DLH", "IBE", "VLG", "TVF"]
TYPES = ["A320", "A20N", "B738", "A321", "A339", "E190"]


def dest(lat, lon, brg_deg, dist_nm):
    r = 3440.065
    b = math.radians(brg_deg)
    la1, lo1 = math.radians(lat), math.radians(lon)
    la2 = math.asin(math.sin(la1) * math.cos(dist_nm / r) + math.cos(la1) * math.sin(dist_nm / r) * math.cos(b))
    lo2 = lo1 + math.atan2(math.sin(b) * math.sin(dist_nm / r) * math.cos(la1),
                           math.cos(dist_nm / r) - math.sin(la1) * math.sin(la2))
    return math.degrees(la2), math.degrees(lo2)


def flight(csn, t0, kind, rwy):
    rows = []
    thr = THR02 if rwy == "02" else THR20
    final_brg = 21 if rwy == "02" else 201      # rumo da final
    if kind == "arr":
        # vem de 30 NM, sector lateral, intercepta a final a 12 NM
        d = 30.0
        lat, lon = dest(*thr, final_brg + 180 + random.choice([-50, 50]), d)
        alt, ias, gs = 9000, 250, 280
        t = t0
        while d > 0.3:
            brg_to = (math.degrees(math.atan2(
                math.sin(math.radians(thr[1] - lon)) * math.cos(math.radians(thr[0])),
                math.cos(math.radians(lat)) * math.sin(math.radians(thr[0])) -
                math.sin(math.radians(lat)) * math.cos(math.radians(thr[0])) * math.cos(math.radians(thr[1] - lon)))) + 360) % 360
            step_nm = gs / 3600 * 4
            lat, lon = dest(lat, lon, brg_to, step_nm)
            d -= step_nm
            if d < 12:
                ias = max(135, ias - 2.5); gs = ias + 10; alt = max(0, int(d * 318))
            elif d < 20:
                ias = max(200, ias - 1); gs = ias + 20; alt = max(3000, int(d * 318) + 500)
            rows.append((csn, t, lat, lon, alt, ias, gs, -700 if d < 12 else -1500))
            t += 4
    else:
        lat, lon = thr
        alt, ias, gs = 0, 140, 150
        t = t0
        d = 0
        hdg = final_brg
        while alt < 10000:
            step_nm = gs / 3600 * 4
            lat, lon = dest(lat, lon, hdg, step_nm)
            d += step_nm
            alt += 2500 / 60 * 4
            ias = min(250, ias + 1.5); gs = ias + 15
            if d > 5:
                hdg += 2  # vira para a saída
            rows.append((csn, t, lat, lon, int(alt), ias, gs, 2500))
            t += 4
    return rows


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "csv_teste")
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    per_block = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    out.mkdir(parents=True, exist_ok=True)
    random.seed(1)
    for day in range(1, days + 1):
        rwy = random.choice(["02", "20"])
        for bi, block in enumerate(["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]):
            rows = []
            for i in range(per_block):
                csn = f"{random.choice(AIRLINES)}{random.randint(10, 9999)}"
                t0 = bi * 4 * 3600 + random.randint(0, 4 * 3600 - 700)
                rows += flight(csn, t0, random.choice(["arr", "dep"]), rwy)
            rows.sort(key=lambda r: r[1])
            name = out / f"LPPT_2604{day:02d}_{block}.csv"
            with open(name, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh, delimiter=";")
                w.writerow(["TRKNR", "TOD", "CSN", "MODEA", "MODES", "LATITUDE", "LONGITUDE", "MODEC", "TAS", "IAR", "ROC", "GSPA"])
                for csn, t, lat, lon, alt, ias, gs, roc in rows:
                    tod = f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{t % 60:02d}"
                    modec = f"{alt / 100:.2f}" if alt >= 100 else "0.00"   # FL (×100 ft) como no CNS
                    w.writerow([random.randint(1000, 9999), tod, csn, "%04d" % random.randint(0, 7777),
                                "%06X" % random.randint(0x340000, 0x34FFFF), f"{lat:.6f}", f"{lon:.6f}",
                                modec, f"{ias + 10:.0f}", f"{ias:.0f}", f"{roc}", f"{gs:.0f}"])
    print(f"Gerados {days * 6} ficheiros em {out.resolve()}")


if __name__ == "__main__":
    main()
