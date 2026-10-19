"""Análise IA — ligação a fornecedores de modelos e construção do contexto com os resultados das análises."""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from collections import Counter

from .geo import operator3

PROVIDERS = {
    "anthropic": {"name": "Claude (Anthropic)", "url": "https://api.anthropic.com/v1/messages", "type": "anthropic",
                  "models": [["claude-sonnet-4-5", "Claude Sonnet 4.5 (recomendado)"], ["claude-haiku-4-5", "Claude Haiku 4.5 (mais rápido)"],
                             ["claude-opus-4-5", "Claude Opus 4.5 (mais potente)"]]},
    "openai": {"name": "OpenAI (ChatGPT)", "url": "https://api.openai.com/v1/chat/completions", "type": "openai",
               "models": [["gpt-4o", "GPT-4o (recomendado)"], ["gpt-4o-mini", "GPT-4o mini (mais rápido)"], ["gpt-4-turbo", "GPT-4 Turbo"]]},
    "mistral": {"name": "Mistral AI", "url": "https://api.mistral.ai/v1/chat/completions", "type": "openai",
                "models": [["mistral-large-latest", "Mistral Large"], ["mistral-small-latest", "Mistral Small"], ["open-mixtral-8x22b", "Mixtral 8x22B"]]},
    "azure": {"name": "Azure OpenAI", "url": "", "type": "azure", "models": [["gpt-4o", "GPT-4o"], ["gpt-4", "GPT-4"], ["gpt-35-turbo", "GPT-3.5 Turbo"]]},
    "groq": {"name": "Groq (Llama)", "url": "https://api.groq.com/openai/v1/chat/completions", "type": "openai",
             "models": [["llama-3.3-70b-versatile", "Llama 3.3 70B"], ["llama-3.1-8b-instant", "Llama 3.1 8B"], ["mixtral-8x7b-32768", "Mixtral 8x7B"]]},
}

SYSTEM = ("Es um especialista em analise de dados de trafego aereo e radar. Responde SEMPRE em JSON valido, sem markdown, sem texto fora do JSON. "
          "Estrutura: {\"texto\":\"explicacao em portugues de Portugal sem asteriscos\",\"grafico\":{\"tipo\":\"bar|pie|line|doughnut\",\"titulo\":\"titulo\","
          "\"dados\":[{\"nome\":\"label\",\"valor\":numero}]}} O campo grafico e OPCIONAL. Os valores em valor devem ser SEMPRE numeros inteiros ou decimais, "
          "NUNCA strings. Para listas usa hifen (-).")


def ask(provider: str, key: str, model: str, question: str, context: str, azure_endpoint: str = "") -> dict:
    cfg = PROVIDERS.get(provider)
    if not cfg:
        raise ValueError("Fornecedor desconhecido")
    if not key:
        raise ValueError("Sem chave API — configura em Preferências.")
    user = context + "\nPERGUNTA: " + question
    if cfg["type"] == "anthropic":
        url = cfg["url"]
        headers = {"Content-Type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"}
        body = {"model": model, "max_tokens": 2048, "system": SYSTEM, "messages": [{"role": "user", "content": user}]}
    elif cfg["type"] == "azure":
        if not azure_endpoint:
            raise ValueError("Endpoint Azure em falta.")
        url = azure_endpoint.rstrip("/") + "?api-version=2024-02-01"
        headers = {"Content-Type": "application/json", "api-key": key}
        body = {"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}], "temperature": 0.2,
                "max_tokens": 2048, "response_format": {"type": "json_object"}}
    else:
        url = cfg["url"]
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
        body = {"model": model, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                "temperature": 0.2, "max_tokens": 2048, "response_format": {"type": "json_object"}}
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}") from e
    raw = data["content"][0]["text"] if cfg["type"] == "anthropic" else data["choices"][0]["message"]["content"]
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"texto": raw}
    return {"texto": parsed.get("texto") or "(sem resposta)", "grafico": parsed.get("grafico")}


def build_context(flights: list[dict], final_results: list[dict], pairs: list[dict], star: dict | None, app: dict | None,
                  rot: dict | None, seq: list[dict] | None, point_rows: list[dict] | None, point_name: str, fast_thr: int = 160) -> str:
    L = []
    cnt = Counter(f["cls"] for f in flights)
    L.append("DADOS CARREGADOS NO FLIGHTTRACKER:")
    L.append(f"Total aeronaves: {len(flights)} | ARR: {cnt.get('arr', 0)} | DEP: {cnt.get('dep', 0)} | NVL: {cnt.get('lvl', 0)}")
    if flights:
        L.append(f"Periodo: {min(f['tod_first'] for f in flights)[:5]}-{max(f['tod_last'] for f in flights)[:5]}")
    ops: dict[str, Counter] = {}
    for f in flights:
        ops.setdefault(operator3(f["csn"]), Counter())[f["cls"]] += 1
    L.append("Voos por operador (lista completa):")
    for op, c in sorted(ops.items(), key=lambda x: -sum(x[1].values())):
        L.append(f"  {op}: total={sum(c.values())} | ARR={c.get('arr', 0)} | DEP={c.get('dep', 0)} | NVL={c.get('lvl', 0)}")
    alts = [f["alt_max"] for f in flights if f["alt_max"] is not None]
    if alts:
        L.append(f"Altitude maxima por voo (ft): min={min(alts)} max={max(alts)} media={sum(alts) / len(alts):.0f}")
    if star:
        if star["totalViol"]:
            L.append(f"Violacoes IAS STAR: total={star['totalViol']} em {star['totalPasses']} passagens")
            top = sorted([w for w in star["perWp"] if w["violations"]], key=lambda w: -w["violations"])[:8]
            L.append("Waypoints STAR com mais violacoes: " + ", ".join(f"{w['wp']}({w['violations']}viol/{w['total']}pass)" for w in top))
            per_flight = Counter(v["csn"] for v in star["violations"])
            dist = Counter(min(n, 5) for n in per_flight.values())
            L.append(f"Distribuicao violacoes IAS STAR por voo: 1viol={dist.get(1, 0)} | 2viol={dist.get(2, 0)} | 3viol={dist.get(3, 0)} | 4viol={dist.get(4, 0)} | 5+viol={dist.get(5, 0)}")
            L.append("Top voos com mais violacoes STAR: " + ", ".join(f"{c}({n}x)" for c, n in per_flight.most_common(5)))
            comp = Counter(operator3(v["csn"]) for v in star["violations"])
            L.append("Top companhias com violacoes IAS STAR: " + ", ".join(f"{c}({n}viol)" for c, n in comp.most_common(8)))
        else:
            L.append(f"Violacoes IAS STAR: 0 em {star['totalPasses']} passagens")
    else:
        L.append("Violacoes IAS STAR: analise nao efectuada (usa aba Velocidades STAR)")
    if app and app.get("records"):
        recs = app["records"]; tol = app["tol"]
        L.append("=== VIOLAÇÕES IAS APP (Velocidades Aproximação) ===")
        L.append(f"Voos com violacoes: {len(recs)} de {app['arrAnalysed']} chegadas analisadas")
        pts = [p for r in recs for p in r["points"] if p["deviation"] is not None and abs(p["deviation"]) > 0]
        L.append(f"Total pontos violados: {len(pts)} | Desvio maximo: {max((abs(p['deviation']) for p in pts), default=0):.0f} kt")
        by_wp: dict[str, dict] = {}
        for r in recs:
            for p in r["points"]:
                if p["deviation"] is not None and abs(p["deviation"]) > 0:
                    e = by_wp.setdefault(p["point"], {"flights": set(), "pts": 0, "max": 0, "sum": 0})
                    e["flights"].add(r["csn"]); e["pts"] += 1; e["max"] = max(e["max"], abs(p["deviation"])); e["sum"] += abs(p["deviation"])
        L.append("Violacoes por waypoint APP (ordenado por numero de voos):")
        for wp, e in sorted(by_wp.items(), key=lambda x: -len(x[1]["flights"])):
            L.append(f"  {wp}: {len(e['flights'])} voos | {e['pts']} pontos violados | max={e['max']:.0f}kt | mediaExcesso={e['sum'] / e['pts']:.0f}kt")
        comp = Counter(r["company"] for r in recs)
        L.append("Top companhias: " + ", ".join(f"{c}({n}voos)" for c, n in comp.most_common(10)))
        rw = Counter(r["rwy"] for r in recs)
        L.append("Por pista: " + " | ".join(f"RWY{k}={v}" for k, v in sorted(rw.items())))
        d = Counter(min(r["violCount"], 5) for r in recs)
        L.append(f"Distribuicao por voo: 1pt={d.get(1, 0)} | 2pt={d.get(2, 0)} | 3pt={d.get(3, 0)} | 4pt={d.get(4, 0)} | 5+pt={d.get(5, 0)}")
    else:
        L.append("Violacoes IAS APP: analise nao efectuada (usa aba Velocidades APP para analisar)")
    if rot and rot["n"]:
        vals = [r["rotS"] for r in rot["results"]]
        L.append("=== ROT — TEMPO DE OCUPAÇÃO DE PISTA ===")
        L.append(f"Total registos: {rot['n']}")
        L.append(f"Média geral: {rot['mean']:.0f}s | Min: {min(vals)}s | Max: {max(vals)}s")
        for rw in sorted({r["rwy"] for r in rot["results"]}):
            v = [r["rotS"] for r in rot["results"] if r["rwy"] == rw]
            L.append(f"  RWY{rw}: {len(v)} registos | média={sum(v) / len(v):.0f} | min={min(v)} | max={max(v)}")
        bins = [(0, 30, "<30s"), (30, 45, "30-44s"), (45, 60, "45-59s"), (60, 90, "60-89s"), (90, 120, "90-119s"), (120, 10 ** 9, ">=120s")]
        L.append("Distribuicao: " + " | ".join(f"{lbl}={sum(1 for v in vals if a <= v < b)}" for a, b, lbl in bins))
    if seq:
        L.append("=== SEQUÊNCIA / PONTOS ===")
        L.append(f"Aeronaves na sequência: {len(seq)}")
        ad = [s["antD"] for s in seq if s["antD"] is not None]
        if ad: L.append(f"Distância ao anterior: min={min(ad)} max={max(ad)} média={sum(ad) / len(ad):.1f} NM")
        al = [s["alt"] for s in seq if s["alt"] is not None]
        if al: L.append(f"Altitude no ponto: min={min(al)} max={max(al)} média={sum(al) / len(al):.0f} ft")
    if pairs:
        seps = [p["sep"] for p in pairs]
        L.append("=== DADOS DE SEPARAÇÃO ENTRE CHEGADAS CONSECUTIVAS (FAST) ===")
        L.append("IMPORTANTE: os números abaixo espelham exactamente o que a aba FAST mostra.")
        L.append(f"Limiar configurado na aba FAST: {fast_thr}s (mostra pares com sep < {fast_thr}s)")
        L.append(f"Total de pares calculados (todos): {len(pairs)}")
        L.append(f"Separação: min={min(seps):.0f} | max={max(seps):.0f} | média={sum(seps) / len(seps):.0f}")
        rw = Counter(str(p["lead"]["rwy"]) for p in pairs)
        L.append("Por pista: " + " | ".join(f"RWY{k}={v}" for k, v in sorted(rw.items())))
        below = [p for p in pairs if p["sep"] < fast_thr]
        L.append(f"PARES COM sep < {fast_thr}s (= o que a aba FAST mostra sem filtro A/C intercalar): {len(below)}")
        L.append(f"  - Com descolagem intercalar (= aba FAST com filtro A/C INTERCALAR activo): {sum(1 for p in below if p['depCnt'])}")
        L.append(f"  - Sem descolagem intercalar: {sum(1 for p in below if not p['depCnt'])}")
        L.append(f"Todos os pares (sem filtro de limiar): com DEP={sum(1 for p in pairs if p['depCnt'])} | sem DEP={sum(1 for p in pairs if not p['depCnt'])}")
        bins = [(0, 30), (30, 60), (60, 90), (90, 120), (120, 150), (150, 180), (180, 210), (210, 240), (240, 270), (270, 300), (300, 360), (360, 10 ** 9)]
        L.append("Distribuicao por faixas: " + " | ".join(
            (f"<{b}s" if a == 0 else f">={a}s" if b >= 10 ** 9 else f"{a}-{b - 1}s") + f"={sum(1 for s in seps if a <= s < b)}" for a, b in bins))
        L.append(f"Detalhe dos pares abaixo de {fast_thr}s:")
        for i, p in enumerate(below[:50]):
            L.append(f"  {i + 1}. {p['lead']['csn']} → {p['trail']['csn']} | RWY{p['lead']['rwy']} | {p['lead']['tTHRstr']} | sep={p['sep']:.0f}s | {'COM' if p['depCnt'] else 'SEM'} DEP intercalar")
        if len(below) > 50:
            L.append(f"  ... ({len(below) - 50} pares adicionais omitidos)")
    elif final_results:
        L.append(f"Separacao entre chegadas (FAST): dados da aba Final disponiveis ({len(final_results)} chegadas) mas sem pares.")
    else:
        L.append("Separacao entre chegadas (FAST): sem dados.")
    if final_results:
        L.append("=== CHEGADAS ANALISADAS (ABA FINAL) ===")
        L.append(f"Total chegadas analisadas: {len(final_results)}")
        rw = Counter(r["rwy"] for r in final_results)
        L.append("Por pista: " + " | ".join(f"RWY{k}={v}" for k, v in sorted(rw.items())))
    by_day: dict[str, Counter] = {}
    for f in flights:
        by_day.setdefault(f["date"], Counter())[f["cls"]] += 1
    if by_day:
        L.append("=== TRÁFEGO POR DIA ===")
        L.append(f"Dias carregados: {len(by_day)}")
        for d in sorted(by_day):
            c = by_day[d]
            L.append(f"  {d[4:6]}/{d[2:4]}/20{d[:2]}: total={sum(c.values())} | ARR={c.get('arr', 0)} | DEP={c.get('dep', 0)} | NVL={c.get('lvl', 0)}")
        top = sorted(by_day.items(), key=lambda x: -sum(x[1].values()))[:3]
        L.append("Top 3 dias com mais trafego: " + ", ".join(f"{d[4:6]}/{d[2:4]}({sum(c.values())})" for d, c in top))
    if point_rows:
        L.append(f"=== ABA PONTOS — PASSAGENS NO RAIO ===")
        L.append(f"Ponto seleccionado: {point_name}")
        L.append(f"Total passagens: {len(point_rows)}")
        c = Counter(r["cls"] for r in point_rows)
        L.append(f"Por tipo: ARR={c.get('arr', 0)} | DEP={c.get('dep', 0)} | NVL={c.get('lvl', 0)}")
        L.append("Top operadores: " + ", ".join(f"{o}({n}x)" for o, n in Counter(operator3(r["csn"]) for r in point_rows).most_common(8)))
        ias = [r["ias"] for r in point_rows if r["ias"]]
        if ias: L.append(f"IAS no ponto: min={min(ias):.0f} max={max(ias):.0f} media={sum(ias) / len(ias):.0f} kt")
        al = [r["alt"] for r in point_rows if r["alt"] is not None]
        if al: L.append(f"Altitude no ponto: min={min(al)} max={max(al)} media={sum(al) / len(al):.0f} ft")
    return "\n".join(L)
