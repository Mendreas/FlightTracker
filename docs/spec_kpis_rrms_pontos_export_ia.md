# Especificação de algoritmos — Flight Track Viewer v3.5 (dist/index.html)
## Abas KPIs · Análise Op. (RRMS / ROT / Oper / Separação / Dados / Diária) · Pontos · Sequência · Exportações · Análise IA

Fonte: `/home/claude/mendreas/flighttracker/dist/index.html` (referências de linha indicadas entre parênteses).
Objectivo: reimplementação fiel em Python. Tudo o que está marcado **[BUG]** é comportamento real do JS que deve ser decidido (replicar ou corrigir) na reimplementação.

---

## 0. Primitivas comuns (usadas por todas as secções)

### 0.1 Estruturas de dados
- `flights` : dict `callsign → {rows:[...], color, visible}`. Cada `row` tem campos CSV em minúsculas: `tod` ("HH:MM:SS.sss"), `latitude`, `longitude`, `modec`, `baroh`, `iar`/`iara` (IAS), `tas`, `roc`, `csn`, e campos injectados `_date` (string **YYMMDD**, ou `'??'`), `_block` ("08-12"…), `_rwy` (opcional).
- `loadedFiles` : dict por ficheiro `{date (YYMMDD), block, airport, rows|null, _fsa}`.
- `selDaysSet`, `selBlocksSet` : Sets com dias (YYMMDD) e blocos seleccionados no painel esquerdo.
- `flightTypeFilter` : `'arr'|'dep'|'all'` (default **'arr'**, l.1189).
- `coordMode` : `'dec'|'geo'` (localStorage `ft.coordMode`, default `'dec'`).
- `activeAirport` : `'LPPT'|'LPPR'|'LPFR'|'LPMA'` (default `'LPPT'`).

### 0.2 Funções base
```js
function gv(r,...ks){for(const k of ks){if(r[k]!==undefined&&r[k]!=='')return r[k];}return '—';}   // l.1324
function getAlt(r){ // l.1325 — altitude em ft; valores <600 são FL (×100)
  const raw=r.modec!==undefined&&r.modec!==''?r.modec:r.baroh!==undefined&&r.baroh!==''?r.baroh:null;
  if(raw===null)return '—';const v=parseFloat(raw);if(isNaN(v))return '—';
  return Math.round(v<600?v*100:v);
}
function todSec(tod){ // l.3272 — "HH:MM:SS.s" → segundos do dia (float); NaN se <3 partes
  const s=String(tod||''),p=s.split(':'); if(p.length<3)return NaN;
  const h=+p[0],m=+p[1],sec=parseFloat(p[2]); if(isNaN(h)||isNaN(m)||isNaN(sec))return NaN;
  return h*3600+m*60+sec;
}
function rowEpoch(r){ // l.3279 — PSEUDO-epoch: int(YYMMDD)*86400 + segundos do dia. NÃO é epoch Unix.
  const t=todSec(r.tod);if(isNaN(t))return NaN;
  const dk=r._date&&r._date!=='??'?(parseInt(String(r._date).replace(/\D/g,''),10)||0):0;
  return dk*86400+t;
}
```
> Nota: `rowEpoch % 86400` dá sempre os segundos do dia correctos; diferenças entre dias distintos são **inválidas** (260415→260416 = 86400 s, mas 260430→260501 = 71×86400 s). Em Python, replicar exactamente (`int(date)*86400+sec`) ou converter para epoch real — escolha a tomar; todos os limiares abaixo assumem segundos.

- `epochToHHMMSS(ep)` (l.3524): `s=round(((ep%86400)+86400)%86400)` → `"HH:MM:SS"`; `'--:--:--'` se não finito.
- `fmtDate(d)` (l.1410): `'??'`/vazio → `'Data desconhecida'`; 6 chars YYMMDD → `"DD/MM/20YY"`; senão devolve tal qual.
- `distNM(lat1,lon1,lat2,lon2)` (l.3108): haversine, `R=3440.065` NM.
- `bearingDeg(lat1,lon1,lat2,lon2)` (l.3499): rumo inicial 0–360.
- `projectPoint(lat,lon,brg,dNM)` (l.3505): destino geodésico.
- `approachCoords(lat,lon,thrLat,thrLon,landBrg)` (l.3513): `d=distNM(THR,pt)`; `br=bearing(THR→pt)`; `app=(landBrg+180)%360`; `delta=br-app` normalizado a (−180,180]; `along=d·cos(delta)` (NM, positivo = ainda antes da THR), `cross=d·sin(delta)` (NM, positivo = direita olhando no sentido de aproximação).
- `toDMS(deg,type)` (l.1330): `DD°MM'SS.SS"N`.
- `_iasFromRow(r)` (l.3532): `gv(r,'iar','iara','ias')`, `'—'`→null, vírgula→ponto, parseFloat.
- `_altFromRow(r)` (l.3538): `getAlt` → NaN se `'—'`.
- `_fmtDur(s)` (l.6036): `"M:SS"` (`'—'` se não finito).
- `fmtN(v,d)` (l.3705): `'—'` se null/não finito; `d===0` → round; senão `toFixed(d)` com vírgula decimal. `fmtS(v)` = round ou `'—'`.
- `_firstEpoch(rows)` (l.6032): primeiro `rowEpoch` truthy; 0 se nenhum.

### 0.3 Classificação de voo (l.1422)
```js
function classifyFlight(rows){
  if(rows.length<2)return 'lvl';
  let firstA=null,lastA=null,minA=Infinity,maxA=-Infinity;
  for(const r of rows){ const a=getAlt(r);if(a==='—')continue; const v=+a;if(isNaN(v))continue;
    if(firstA===null)firstA=v;lastA=v; if(v<minA)minA=v;if(v>maxA)maxA=v; }
  if(firstA===null)return 'lvl';
  if(maxA-minA<500)return 'lvl';
  const d=lastA-firstA;
  if(d<-500)return 'arr'; if(d>500)return 'dep'; return 'lvl';
}
```
Rótulos: `arr`→"ARR", `dep`→"DEP", `lvl`→"NVL"/"LVL"/"Sobrevoos".

### 0.4 Legs (l.1448)
Uma *leg* = par único (callsign, `_date`). `getFlightLegs()` agrupa `f.rows` por `r._date||'??'`, cada leg `{csn,date,rows,color,_flight,firstEpoch}`; ordenação por `date` (string) e depois `firstEpoch`. `isLegVisible(leg)` = `leg._flight.visible && (flightTypeFilter==='all' || classifyFlight(leg.rows)===flightTypeFilter)`. `isFlightVisible(csn,f)` idem para o voo inteiro.

### 0.5 Operador / companhia a partir do callsign — há **quatro** regras diferentes na app
| Onde | Regra |
|---|---|
| KPIs "Top 10 operadores" (l.3867) | `csn.replace(/[^A-Za-z]/g,'').substring(0,3).toUpperCase() || '???'` — remove todos os não-letras e fica com as 3 primeiras letras (ex. `TAP1234`→`TAP`, `N123AB`→`NAB`). |
| Cumprimento IAS por operador, IA ctx, RRMS `comp`, Go-around/holding por companhia (l.6375, 10331, 8627) | `(csn.match(/^[A-Z]{2,3}/)||['?'])[0]` — 2–3 letras maiúsculas iniciais; `'?'`/`'???'` se não casar. (regex `i` em 6375, upper após). |
| Oper analysis (l.7220) | `_operPrefix = csn.replace(/\d.*/,'').substring(0,3).toUpperCase() || '???'` — corta a partir do 1º dígito, 3 primeiros chars. |
| Separação/Análise de Dados/Diária (l.7766) | `companyFromCallsign`: upper+trim; vazio→`'SEM CSN'`; `^([A-Z]{2,4})(?=\d)` (2–4 letras seguidas de dígito); senão `^([A-Z]{2,4})`; senão `s.slice(0,4)`. |

### 0.6 Aeroportos / pistas (l.3420)
```
LPPT center [38.7813,-9.1359] elev 374
  '02': thr {38.766428,-9.143903} brg 32.0 elev 357
  '20': thr {38.792331,-9.130047} brg 212.0 elev 303
LPPR center [41.2481,-8.6814] elev 227
  '17': thr {41.260681,-8.684561} brg 171.0 elev 151
  '35': thr {41.233886,-8.677536} brg 351.0 elev 227
LPFR center [37.0153,-7.9723] elev 24
  '10': thr {37.017222,-7.985614} brg 101.0 elev 24
  '28': thr {37.013450,-7.959042} brg 281.0 elev 18
LPMA center [32.6978,-16.7745] elev 191
  '05': thr {32.689932,-16.783751} brg 47.0 elev 146
  '23': thr {32.705841,-16.765150} brg 227.0 elev 191
```

### 0.7 Análise "Final" (`runFinalAnalysis`, l.3662) — pré-requisito de quase tudo
Controlos: `finRwy` (default `BOTH`), `finFaf` default **7** NM (3–15, passo 0.5), `finCorr` default **2** NM (0.5–5), `finAltThr` default **1000** ft (500–3000).
Para cada leg visível e cada pista → `analyzeFlightApproach(csn,leg,rwy,rid,fafNM,corrNM,altThrMax)` (l.3544):
1. Bounding box: existe ponto com `|lat−thr.lat|<0.6 && |lon−thr.lon|<0.6`; senão null.
2. `pts` = rows com lat/lon, epoch e alt válidos, com `along/cross` (approachCoords); ordenar por t; <3 → null.
3. Cruzamento THR: primeiro `i≥1` com `a.along>0 && b.along<=0.3` e `min(a.alt,b.alt) <= rwy.elev+altThrMax` e `|a.cross|<corrNM && |b.cross|<corrNM`. Interpolação `kT=a.along/(a.along−b.along)` → `tTHR, altTHR, iasTHR (se ambos), latTHR, lonTHR`.
4. FAF: retroceder de `thrIdx−1` até encontrar `a.along>fafNM && b.along<=fafNM`; `kF=(a.along−fafNM)/(a.along−b.along)` → `tFAF, altFAF, crossFAF, iasFAF, latFAF, lonFAF`. Sem FAF → null.
5. `ias4` = IAS interpolada no 1º segmento entre fafIdx..thrIdx com `a.along>4 && b.along<=4`.
6. `trackNM` = distância FAF→pts[fafIdx] + soma segmentos + pts[thrIdx−1]→THR.
7. `stab` = `aglFAF∈[800,5000] && (iasFAF==null || iasFAF∈[120,230]) && |crossFAF|<=1.0`, com `aglFAF=altFAF−rwy.elev`.
8. CDO: a partir do 1º ponto com `alt<=10000` antes da THR, procurar janelas onde `maxAlt−minAlt<=150`, `j−i>=2`, **`dur=(pts[j].t−a.t)/1000 >= 30`** e `a.alt>=rwy.elev+800` → `cdoLevelOffs++`, `cdoLevelSecs+=dur`. `cdo = cdoLevelOffs===0`. **[BUG]** `t` está em segundos; a divisão por 1000 faz com que `dur>=30` exija ≥30000 s → level-offs praticamente nunca detectados → `cdo` quase sempre true, `cdoLevelSecs` em "milésimos".
9. Devolve `{csn,rwy,epochTHR,epochFAF,tFAFstr,tTHRstr,date(fmtDate do 1º row),_dateRaw,altFAF,altTHR,iasFAF,ias4,iasTHR,crossFAF,trackNM,durS=tTHR−tFAF,stab,cdo,cdoLevelOffs,cdoLevelSecs,color,latFAF,lonFAF,latTHR,lonTHR}`.

Depois: ordenar por `epochTHR`; `idx=i+1`; `sepTimeS` = `epochTHR − epochTHR da aterragem anterior na mesma pista e no mesmo dia` (`_dateRaw` ou data UTC do epoch); null se primeira.

---

# A. Aba "KPIs" — `renderKpis()` (l.3842)

### Controlos
- Botão **⟳ Actualizar** → `renderKpis()`; **↓ CSV** → `exportKpisCsv()`; **📄 Relatório** → `openReport()`.
- Nota `kpiNote` (canto direito): se há resultados, lista `"<N> aproximações · <N> holdings · <N> go-arounds · <N> passagens STAR · <N> violações IAS"` (só partes existentes; aproximações vai para a frente); senão `"Corre Final e Velocidades STAR para mais métricas"`.
- Sem `flights` → painel vazio "Sem dados".
- Não há filtro próprio: usa **todas** as legs (`getFlightLegs()` sem `isLegVisible`) para o resumo/hora/operadores; mas os blocos avançados usam `isLegVisible` (ver cada um).

### Algoritmo (agregações base)
Para cada leg (todas, sem filtro de visibilidade):
- `cls=classifyFlight(leg.rows)`; `clsCnt[cls]++`.
- `firstT` = 1º `rowEpoch` válido; `minT/maxT` globais; `days.add(r._date)` se ≠'??'; `pts++` por row (amostras radar).
- `hr=floor(((firstT%86400)+86400)%86400/3600)`; `byHour[hr]++`, e `byHArr`/`byHDep` conforme cls (lvl não entra nas pilhas).
- `op` = regra KPIs (0.5, 1ª linha); `opCnt[op]++`.
- `total=arr+dep+lvl`; `peakHr=indexOf(max(byHour))` (primeira hora com o máximo); `topOp` = top 10 por contagem desc; `period="HH:MM:SS → HH:MM:SS"` (de minT/maxT); `spanH=(maxT−minT)/3600` se maxT>minT.

### Saídas (ordem no ecrã)
**1. "Resumo Operacional"** — cartões `kpiCard(label, valor, sub)`:
| Cartão | Valor | Sub |
|---|---|---|
| Movimentos | `total` (pt-PT) | — |
| Chegadas (ARR) | `arr` | `(arr/total*100).toFixed(0)%` |
| Partidas (DEP) | `dep` | idem |
| Sobrevoos (LVL) | `lvl` | idem |
| Dias de dados | `days.size` | — |
| Hora de pico | `"HH:00"` de peakHr | `"<byHour[peakHr]> mov."` |
| Período (UTC) | `period` | — |
| Amostras (radar) | `pts` | — |
Se `days.size>1` nota: `"Contagem por (callsign, dia): <total> movimentos em <nº callsigns> callsigns distintos ao longo de <days> dias."`

**2. "Análise de Aproximações (LPPT)"** (só se `finalResults.length`):
- `hourlyRate = (finalResults.length/spanH).toFixed(1)+' aterr./h'` (se spanH finito).
- Cartões: `Aterragens` (N, sub=hourlyRate); `RWY 02` (count rwy '02'); `RWY 20`; `Estabilizadas` (`stab/N`, sub `%`); `IAS@FAF méd.` (média iasFAF não-null, 0 dec, " kt"); `Tempo FAF→THR méd.` (média durS, " s"); `Sep. temporal méd.` (média sepTimeS não-null, " s"); `Sep. temporal mín./máx.` (`"min / max s"`).

**3. "Taxa de aterragem (rolling 60 min)"** — `_landingRateBlock` (l.6312):
- `epochs` = epochTHR ordenados; `STEP=300 s`, `WIN=3600 s`; para `t` de `minT` até `maxT+STEP` passo STEP: `c = #epochs com e>t−WIN && e<=t`.
- Cartões: `Pico 60 min` = `max(c)+' aterr./h'`, sub `"<pct>% da capacidade LPPT (38)"` com `LPPT_CAPACITY=38`, `pct=(max/38*100).toFixed(0)`; `Média período` = `floor(N/spanH)` (spanH=max((maxT−minT)/3600, 1/60)), sub "média inteira (arred. por defeito)"; `Total` = `N aterragens`.
- Gráfico `_svgBars(vals, labels=hora UTC "HH" de cada bucket, {w:720,h:80,cls:'bar arr'})`. Nota: "Cada ponto: aterragens na hora anterior. Referência: capacidade declarada LPPT ≈ 38 mov/h."

**4. "Separação temporal entre aterragens consecutivas"** — `_sepHistogramBlock` (l.6342), só se ≥3 `sepTimeS` válidos:
- bins `[0,60,90,120,150,180,240,300,600,∞)`, labels `['<60s','60-90','90-120','120-150','150-180','180-240','240-300','300-600','>600']` (intervalo `[a,b)`).
- Cartões: `Média` (`_fmtDur`, sub "sensível a extremos"), `Mediana` (`sorted[floor(n/2)]`, sub "valor central (50%)"), `Mínimo`, `Máximo`, `Bunching` (`"<n> <90s"`, n=#sep<90, sub "aproximações muito comprimidas").
- Gráfico `_svgBars(counts,binLbl,{w:520,h:160,cls:'bar arr'})`.

**5. "CDO — Continuous Descent Operations (< FL100)"** — `_cdoBlock` (l.6405): sobre `finalResults` com `cdoLevelOffs!=null`: `Taxa CDO` = `%cdo` (classe ok ≥70, bad <40), sub `"<cdoCount>/<n> aprox."`; `Level-offs méd./aprox.` (1 dec); `Tempo nível méd.` (`_fmtDur(média cdoLevelSecs)`). (Ver [BUG] CDO em 0.7.)

**6. "Holdings (tempo em espera)"** — `_holdingsKpiBlock` (l.6424), se `holdingsResults.length`: `Total esperas`, `Tempo acumulado` (`round(Σ durS/60)+' min'`), `Duração média` (`_fmtDur(tot/n)`), `Voos afectados` (callsigns distintos); lista "Top fixes por tempo acumulado" (top 5 por Σ durS por `fix||'(sem fix)'`, barra relativa ao 1º, `"<min> min"`).

**7. "Go-Arounds"** — `_goAroundKpiBlock` (l.6443), se `goAroundResults.length`: `Total`; `Taxa` = `total/arrCount*100` (1 dec, vírgula) com sub `"de <arrCount> chegadas"` onde `arrCount` = legs visíveis classificadas `arr`; `Aterraram depois` (`landed/total`, eventuallyLanded); `Não aterraram`. Gráfico por hora UTC `_svgBars(byHour, '00'..'23', {w:720,h:60,cls:'bar ga'})` com `byHour[new Date(g.epochMin).getUTCHours()]` **[BUG]** `epochMin` em segundos pseudo-epoch tratado como ms → hora errada.

**8. "Cumprimento de IAS em waypoints STAR (ARR)"** — `_iasKpiBlock` (l.5425), se `iasResults`: `Passagens analisadas` (totalPasses, sub `"<flightsAnalysed> voos ARR"`); `Conformes` (totalComp, sub `"Raio <radius> NM · Tol +<tol> kt"`); `Violações` (totalViol); `Taxa de cumprimento` (`totalComp/totalPasses*100`, 1 dec, ok ≥95, bad <85). "Top 5 waypoints com mais violações": perWp com total>0 && violations>0, desc por violations, 5 → `WP | lim <limit> kt | <viol> | (<viol/total%> de <total>)`. Rodapé: `"Actualizado: HH:MM:SS. Para recalcular, vai ao separador Velocidades STAR e clica Analisar."`

**9. "Cumprimento IAS por operador (top 10 pior)"** — `_operatorComplianceBlock` (l.6369), se `iasResults` (cache em `iasResults._opBlockHtml`):
- `opStats[op]` = `{arrFlights, violations}`; violations de `iasResults.violations` por `extractOp(csn)` (regex `^([A-Z]{2,3})` i → upper, `'???'`); arrFlights de legs visíveis `arr`.
- Filtra `arrFlights>0||violations>0`; `rate=violations/arrFlights` (0 se arrFlights=0); ordena `violations desc, rate desc, arrFlights desc`; top 10.
- Tabela colunas: **Operador | Voos ARR | Violações | Inc./voo** (`rate*100` 1 dec, vírgula; classe ok ≤10%, bad ≥50%). Nota: "Ordenado por nº de violações (descendente). Indicador: violações por voo ARR no filtro activo."

**10. "Movimentos por hora (UTC)"** — `_hourlyBars(byHour,byHArr,byHDep)` (l.3826): 24 colunas, barras empilhadas ARR (vermelho #f87171, em baixo) + DEP (verde #22d3a0) normalizadas pelo `max(total)`; etiqueta do total em cima; legenda ARR/DEP. (LVL contribui para o total mas não para as barras.)

**11. "Movimentos por dia (N dias)"** — `_dayComparisonBlock` (l.6464), só se ≥2 dias: por leg **visível** com date≠'??': `{arr,dep,lvl,tot}` por dia; ordena por data; barra horizontal por dia com 3 segmentos (ARR verde #22d3a0, DEP laranja #f59e0b, LVL índigo #6366f1) largura `x/max(tot)*100%`; etiqueta `fmtDate(d)` e `tot`.

**12. "Top 10 operadores (prefixo callsign)"** — `topOp`: linhas `OP | barra (n/maxOp) | n`.

(No ecrã, a ordem real é: Resumo → Aproximações → Taxa aterragem → Sep histograma → CDO → Holdings → Go-Arounds → IAS STAR → IAS por operador → Movimentos por hora → Movimentos por dia → Top 10 operadores.)

**Não existem** na aba KPIs os blocos "Pico horário por dia", "Média de movimentos por dia da semana", "Companhias por dia", "Resumo por companhia", "Indicadores principais", "Destaques", "Factores operacionais" — esses pertencem à **Análise de Dados / Análise Diária** (secção B.4/B.5) e aos seus relatórios PDF.

### `exportKpisCsv()` (l.3957) — CSV `;`, BOM, `kpis_lppt_<YYYY-MM-DD>.csv`
```
KPI;Valor
Movimentos;<total>
Chegadas (ARR);<arr>
Partidas (DEP);<dep>
Sobrevoos (LVL);<lvl>
Período (UTC);<HH:MM:SS - HH:MM:SS>
(linha vazia)
Hora;Total;ARR;DEP
HH:00;<tot>;<arr>;<dep>   ×24
[se finalResults:]
(linha vazia)
Aproximações;Valor
Aterragens;N
RWY 02;n
RWY 20;n
Estabilizadas;n
IAS FAF méd. (kt);<1 dec>
Tempo FAF-THR méd. (s);<1 dec>
Sep. temporal méd. (s);<1 dec>
```
(Aqui a contagem é sobre todas as legs, igual ao ecrã.)

### `openReport()` (l.6502) — "Relatório Operacional — LPPT"
Abre janela nova com `<h1>Relatório Operacional — LPPT</h1>`, linha `"Gerado em <now pt-PT> · Dados: <nº callsigns> voos"`, **o innerHTML completo do painel KPIs** (`#kpiContent`, exige ter corrido "Actualizar"), rodapé `"Flight Tracker — Relatório automático. Dados baseados em track radar."`, CSS de impressão claro (azul #1e3a8a), e `window.print()` após 500 ms.

---

# B. Análise Op. → sub-abas

Barra de sub-abas (l.783): **Separação entre chegadas** (`fast`), **Análise de Dados** (`anaData`), **Análise Diária** (`anaDaily`), **RRMS** (`rrms`); botão **↓ CSV** (`exportAnaActiveCsv`). As sub-abas Holdings/GA/ROT/Oper estão escondidas ("kept hidden for compat") mas os cálculos continuam a correr para alertas e IA.
`ensureAnaTabData(tab)` (l.5723): `fast/anaData/anaDaily` correm `runFinalAnalysis()` se `finalResults` vazio; `anaData`→`buildFastPairs()+renderSepAnalysis()`; `anaDaily`→`buildFastPairs()+renderSepDaily()`; `rrms`→`renderRRMS()`.

## B.1 RRMS — `renderRRMS()` (l.8530)

### Constantes (l.8303)
```js
const RRMS_POINTS = {
  '02': { lat: 38+47/60+10.93/3600, lon: -(9+7/60+59.65/3600), label:'RWY 02 · TWY U6 · 2400m' },  // 38.786369°, -9.133236°
  '20': { lat: 38+46/60+20.54/3600, lon: -(9+8/60+26.60/3600), label:'RWY 20 · TWY P · 2400m'  }   // 38.772372°, -9.140722°
};
const RRMS_RADIUS_NM = 0.40;      // tolerância de detecção (≈740 m)
const RRMS_MIN_ALT_FT = -9999;    // sem filtro de altitude (mostra airborne E solo)
```
Os pontos são "2400 m da THR deslocada": RWY 02 → TWY U6 `38°47′10.93″N 009°07′59.65″W`; RWY 20 → TWY P `38°46′20.54″N 009°08′26.60″W`. Só existem para LPPT (não depende de `activeAirport`).

### Controlos (todos re-renderizam via `renderRRMS()`)
- `rrmsWakeSel` "Categoria rasto": `MH` (default, M+H), `M`, `H`, `all`.
- `rrmsStatGrp` "Estatísticas no ponto": `rwy` (default), `gnd`, `hour`, `cat`, `actype`, `comp`, `top10csn`.
- `rrmsChartMetric`: `alt` (default) | `ias`; `rrmsChartRwy`: `all` (default) | `02` | `20`.
- `rrmsRwyFilter` (tabela de detalhe, e também usado pelo gráfico ar/solo e pela tabela de estatísticas): `all` | `02` | `20`.
- Ordenação da tabela: `rrmsSort(col)` (toggle direcção), estado `window._rrmsSort` (default 0 = Callsign), `_rrmsSortDir` (1).
- Botões **⬇ CSV** (`rrmsExportCsv`) e **📄 PDF** (`rrmsExportPdf`).

### Algoritmo de detecção de passagens
Para cada `(csn, fl)` em `flights` com ≥2 rows; agrupar rows por `_date`; para cada (callsign, data) = leg:
1. Se `leg_date!=='??' && selDaysSet.size>0 && !selDaysSet.has(leg_date)` → ignora.
2. `_dbgTotal++`. `cls=classifyFlight(leg_rows)`; **se `'arr'` → ignora** (RRMS analisa DEP e LVL; ignora o filtro ARR/DEP da sidebar).
3. `cat=RRMS_WAKE.cat(csn)` (heurística por prefixo, ver abaixo). `rows` = rows com lat/lon numéricos, ordenadas por `rowEpoch`; <2 → ignora. `_dbgFiltered++`.
4. **Atribuição de pista pelo sentido de movimento**: `fR`=primeiras 5 rows, `lR`=últimas 5; `latF`/`latL` = médias das latitudes; `latL>latF+0.001` → `['02']`; `latF>latL+0.001` → `['20']`; senão nenhuma (→ `_dbgNoClose++`, ignora).
5. Para a pista: `pt=RRMS_POINTS[rwy]`. **Distância perpendicular ao segmento** (em graus, plano): para cada par consecutivo A,B: `dlat=laB−laA, dlon=loB−loA; dot=dlat·(pt.lat−laA)+dlon·(pt.lon−loA); len2=dlat²+dlon²` (ignora se `<1e-12`); `k=clamp(dot/len2,0,1)`; `d=distNM(laA+k·dlat, loA+k·dlon, pt)`. Guarda o mínimo `(bestDist,bestK,bestI)`.
6. Se `bestI<0 || bestDist>0.40` → `_dbgNoClose++`, ignora.
7. Interpolação linear com `k=bestK` entre `rA=rows[bestI]` e `rB=rows[bestI+1]`:
   - `altFt = round(aA + k·(aB−aA))` se ambos válidos (`getAlt` ≠ `'—'`), senão o que existir, senão null. Se null ou `< RRMS_MIN_ALT_FT` → `_dbgLowAlt++`, ignora (nunca acontece com −9999 salvo null).
   - `iasA=+(rA.iar||rA.iara||0)`, idem B; `ias = round(iasA+k·(iasB−iasA))` se ambos ≠0, senão `iasA||iasB||null`.
   - `tI = rowEpoch(rA)+k·(rowEpoch(rB)−rowEpoch(rA))`; `tod = "HH:MM:SS"` de `round(tI%86400)`.
   - `NMIR_LOOKUP(csn, leg_date)` → `{type, wtc, source}`; `cat` final = `wtc` se ≠'?' senão a heurística.
   - **`airborne = altFt!==null && altFt>=50`** (limiar 50 ft, "LPPT QFE") — é assim que se decide "No ar vs Solo no ponto 2400 m".
   - `hit={_isRRMS:true,csn,rwy,cat,cls,acType,airborne,_typeSource,distNM:bestDist.toFixed(3),altFt,ias,tod,t:tI,date:rrmsFormatDate(leg_date),_dateRaw,epoch:tI,comp:(csn.match(/^[A-Z]{2,3}/)||['?'])[0]}`.
8. `hits.all/hits['02']/hits['20']` ordenados por `epoch`.
9. Filtro de categoria `filterFn`: `M`→cat==='M'; `H`→'H'; `MH`→M ou H; `all`→tudo. `shown=hits.all.filter`, `shown02`, `shown20`. `window._rrmsLastShown=shown`.

`rrmsFormatDate(YYMMDD)` → `"DD/MMM/YYYY"` com meses `JAN FEV MAR ABR MAI JUN JUL AGO SET OUT NOV DEZ`.

**Categoria de turbulência de esteira (WTC)**:
- `nmir_wtc(icaoType)` (l.8318): listas `H` (A332,A333,A338,A339,A342,A343,A345,A346,A359,A35K,A388,B744,B748,B762,B763,B764,B772,B773,B77L,B77W,B788,B789,B78X,A306,A30B,B742,B741,DC10,MD11,IL76) e `L` (C172,C182,C152,C208,C210,PA28,PA31,B06,R44,EC35,B350,PC12,TBM7,TBM8,TBM9,PC6T,DA40,DA42,DA50,SR20,SR22,SR2T,P28A,AA5B,M20T,BE58,BE60,C337,P180); vazio→`'?'`; senão `'M'`.
- `NMIR_LOOKUP(csn,dateYYMMDD)` (l.8332): chave `"CSN|YYMMDD"` em `NMIR_DATA` (blob l.8314, valor `"TYPE:WTC"`) → `{type,wtc:parts[1]||nmir_wtc(type),source:'nmir'}`; senão `NMIR_FALLBACK[csn]` (blob l.8315) → `source:'fallback'`; senão prefixo (`csn.replace(/[0-9].*/,'')`) em `prefixTypes={TAP:'A20N',RYR:'B38M',EJU:'A320',EZY:'A320',VLG:'A320',IBE:'A320',BAW:'B772',DLH:'A321',AFR:'A321',KLM:'B738',WZZ:'A320',BEL:'A319',SWR:'BCS3',NAX:'A320',THY:'A321',UAE:'B77W',QTR:'B773'}` → `source:'prefix'`; senão `{type:'?',wtc:'?',source:'unknown'}`.
- `RRMS_WAKE.cat(csn)` (l.8359, fallback): `isH`: prefixo (`replace(/\d.*/,'')`, upper) em `['BAW','UAE','QTR','THY','ANA','JAL','AAL','UAL','DAL','FIN','ELY','TAM','LAN','GOL']`, ou `TAP` com nº de voo (dígitos) entre 200 e 499; `isM`: prefixo em `['RYR','EJU','EZY','VLG','TAP','IBE','IBS','AFR','KLM','DLH','SWR','TUI','TOM','WZZ','WUK','LOT','CSA','ROU','BEL','ETF','NAX','SAS','AEE','VKG','ASL','TVF','TVS','THY','BTI','AUI','HYS','RAM','MSR','RZO','SXS','ONT','ONS']`; `cat`: H → M → `'?'`.

### Saídas
**Cabeçalho**: "RRMS — Reduced Runway Separation Minima · Pontos 2400m das THR deslocadas · RWY 02 TWY U6 · RWY 20 TWY P · apenas aeronaves DEP no ar".

**Cartões KPI** (6, clicáveis → modal com linhas de origem):
| Label | Valor | Sub |
|---|---|---|
| RWY 02 — passagens | `shown02.length` | `"<nAir> no ar · <nGnd> no solo"` |
| RWY 20 — passagens | idem | idem |
| Alt. mín/méd/máx RWY 02 | `"min / avg / max ft"` (`rrmsStats`) ou `'—'` | "mínima / média / máxima" |
| Alt. mín/méd/máx RWY 20 | idem | |
| IAS mín/méd/máx RWY 02 | `"min / avg / max kt"` | |
| IAS mín/méd/máx RWY 20 | idem | |
`rrmsStats(rows)` (l.9096): alts = `altFt` não-null e **>0**; ias = `ias` truthy e >0; avg = `round(mean)`.

**Tabela "Estatísticas no ponto de referência (valores interpolados)"** — colunas `Grupo | N | Alt. mín (ft) | Alt. méd (ft) | Alt. máx (ft) | IAS mín (kt) | IAS méd (kt) | IAS máx (kt)`; `filtered = shown` filtrado por `rrmsRwyFilter`. Grupos por `rrmsStatGrp`:
- `rwy`: `'RWY 02'`, `'RWY 20'`.
- `hour`: `"HHh"` de `tod[0:2]`.
- `gnd`: `'✈ No ar (alt ≥ 50ft)'` (airborne) / `'⊙ No solo (alt < 50ft)'`.
- `cat`: `'M (Medium)'`, `'H (Heavy)'`, `'? (Desconhecido)'`.
- `actype`: por `acType||'Desconhecido'`, ordenado por N desc.
- `top10csn`: por callsign, N desc, 10 → label `"CSN  (TIPO)  [CAT]"`.
- `comp` (default do else): por `comp`, N desc, 12.
`statsFor(arr)`: null se sem alts>0 (linha omitida). Grupos vazios omitidos.

**Gráfico "Evolução temporal no ponto (por hora)"** (SVG 760×220): fonte = `shown`/`shown02`/`shown20` conforme `rrmsChartRwy`; por hora `tod[0:2]` recolhe valores `altFt` ou `ias` (>0); percentis por interpolação linear (`idx=(p/100)(n−1)`): `p0,p25,p50,p75,p100` arredondados; desenha banda Q1–Q3, linhas mín (vermelho tracejado), máx (laranja tracejado), Q1/Q3 (azul ténue), mediana (azul 2.5px) com pontos; tooltip `"HHh | n= | mín= | Q1= | med= | Q3= | máx="`; eixo Y de `min(p0)` a `max(p100)`, 5 ticks.

**Gráfico "No ar vs Solo no ponto 2400m — por hora"** (SVG 760×160, barras empilhadas verde #16a34a = ar, laranja #f59e0b = solo): fonte por `rrmsRwyFilter`; resumo: `"Total: <air> no ar (<pct>%) · <gnd> no solo (<100-pct>%)"` + `"✓ Todas as aeronaves já estavam no ar ao passar o ponto"` se gnd=0, `"⚠ Nenhuma aeronave estava no ar ao passar o ponto"` se air=0, senão `"⚠ <gnd> aeronave(s) passaram o ponto ainda no solo"`. `pctAir=round(air/total*100)`.

**"RWY 02/20 — distribuição horária (N passagens)"**: barras horizontais por hora (`tod[0:2]`), largura `count/max`.

**Tabela "Detalhe das passagens (N registos)"** — colunas `Callsign | WTC | Tipo A/C | RWY | Status | Data | Hora | Alt. (ft) | IAS (kt) | Dist. (NM)`; filtro `rrmsRwyFilter`; sort por índice de coluna com vectores `[csn,cat,acType,rwy,airborne?0:1,date,tod,altFt||0,ias||0,+distNM]` (numéricos por subtração, strings `localeCompare`); cor da alt: `<500` vermelho, `<1000` laranja, senão verde; Status "▲ No ar" / "⚫ Solo".

**Rodapé debug**: `"RRMS · DEP independente do filtro ARR/DEP · Datas: <dias> · Blocos: <blocos> · Analisados: <_dbgTotal> · Detectados: <shown.length>"`.

**`rrmsExportCsv()`** (l.8395): `RRMS_passagens.csv`, `;`, BOM, colunas `Callsign;WTC;Tipo_AC;RWY;Status;Data;Hora;Alt_ft;IAS_kt;Dist_NM` com Status `No_ar`/`Solo`; linhas = `_rrmsLastShown` (sem filtro de pista).

**`rrmsExportPdf()`** (l.8403) — janela de impressão "RRMS — Relatório de Estatísticas":
- `shown` = `_rrmsLastShown` filtrado por `rrmsRwyFilter`; `d02`, `d20`.
- Cabeçalho: Data (now), "Filtros activos: Categoria = <cat> · Pista = Ambas|RWY xx · Total passagens mostradas: N"; lista de pontos de referência (coordenadas DMS acima); parágrafo **Metodologia** (verbatim): *"Para cada aeronave DEP, o algoritmo determina a pista pela direcção de movimento (latitude crescente→RWY02, decrescente→RWY20), encontra o par de amostras radar consecutivas com menor distância perpendicular ao ponto de referência (raio máx: 0.40 NM) e interpola linearmente a altitude e IAS no instante exacto de passagem."*
- Por pista com dados: `<h2>RWY xx (N passagens) · Ponto TWY U6|P</h2>` + `narrative` + `<h3>No ar vs Solo no ponto 2400m</h3>` (`airGroundChart`: resumo + SVG barras empilhadas por hora) + `<h3>Estatísticas por categoria</h3>` (tabela `Categoria | N | Alt. mín | Alt. méd | Alt. máx | IAS mín | IAS méd | IAS máx` com linhas `Total`, `M (Medium)`, `H (Heavy)`; linha omitida se sem alts) + `<h3>Distribuição horária</h3>` (SVG barras horizontais) + `<h3>Detalhe completo</h3>` (tabela 10 colunas; **[BUG]** a linha de detalhe omite a célula Status, ficando desalinhada).
- `narrative(rows,rwy)` (l.8440) templates verbatim:
  - `"Na RWY <rwy>, foram registadas <N> passagens no ponto de referência 2400m da THR deslocada (valores obtidos por interpolação linear entre amostras radar consecutivas)."`
  - `"A altitude interpolada variou entre <minA> ft e <maxA> ft, com média de <avgA> ft. "` + (`avgA<500` ? `"A maioria das aeronaves ainda se encontrava a baixa altitude no ponto de referência."` : `"A maioria das aeronaves já se encontrava a altitude positiva, confirmando que estavam no ar ao passar o ponto."`)
  - `"A IAS interpolada variou entre <minI> kt e <maxI> kt, com média de <avgI> kt."`
  - `"Distribuição por categoria: M (Medium) — <n> (<pct>%) · H (Heavy) — <n> (<pct>%) · ? — <n> (<pct>%)."`
  - `"Hora de pico: <HH>h com <n> passagens."`
  - `"Estado no ponto 2400m: <nAir> aeronaves no ar (<pAir>%) · <nGnd> no solo (<100-pAir>%)."` + (nGnd===0 ? `" Todas estavam airborne ao passar o ponto — condição favorável para RRMS."` : `" ⚠ Algumas aeronaves ainda estavam em rolagem ao passar o ponto — analisar casos individuais."`)
  - `"Aeronaves M: alt méd=<avgA>ft, IAS méd=<avgI>kt."` / `"Aeronaves H: alt méd=…"` (se existirem).
  - `airGroundChart` resumo: `"✓ Todas as aeronaves (<tot>) já estavam no ar ao passar o ponto 2400m."` ou `"⚠ <gnd> aeronave(s) passaram o ponto ainda no solo (<pctGnd>%). <air> (<pctAir>%) estavam no ar."`

### Modal de dados RRMS (`sep_openDataModal`, l.9137)
Colunas `Callsign | WTC | Tipo A/C | RWY | Status | Data | Hora | Alt. (ft) | IAS (kt) | Dist. (NM)`, hint "Dados RRMS — passagens no ponto 2400m da THR (valores interpolados)."; botões "Exportar estes dados" (`.xls` HTML — para RRMS usa cabeçalhos genéricos de pares, pouco útil) e "PDF" (imprime a tabela do modal).

## B.2 ROT (Runway Occupancy Time) — `detectROT()` (l.6146) / `renderRotResults()` (l.6214)
Corre automaticamente em `_autoAnalyseAndAlert` (sem UI própria visível; alimenta alertas, IA e Oper).
```js
const MAX_ALONG=4300,MAX_CROSS=220,MIN_ALONG=-60,CROSS_DET=380;  // metros
```
`runwayCoords(lat,lon,thrLat,thrLon,rwyBrg)` = como `approachCoords` mas em **metros** e com `delta=br−rwyBrg` (eixo no sentido de aterragem; `along>0` = depois da THR, pista adentro); `d<0.5 m` → (0,0).
Para cada `csn` em `flights` (não legs!) com `classifyFlight==='arr'`:
- `pts`={t,lat,lon,_date} ordenados; <3 → `noPts++`.
- Para cada pista do aeroporto activo, para `i=1..`: `rc0`,`rc1`; precisa `rc0.along<0 && rc1.along>=0` (transição antes→depois da THR), `|cross|<=380 m` em ambos, `Δt<=60 s`. `frac=−rc0.along/(rc1.along−rc0.along)`; `epochTHR=t0+frac·Δt`. Chave `csn|date|rwy` já vista → continua.
- `lastOnRwy` = último `pts[j]` (j≥i, `t<=epochTHR+300`) com `along∈[−60,4300] && |cross|<=220`. Sem → `noOnRwy++`.
- `rotS=round(lastOnRwy.t−epochTHR)`; fora de `[20,300]` → `tooShort++`.
- Regista `{rwy,csn,date(DD/MM/YYYY se 8 dígitos, senão raw YYMMDD),tTHRstr,epochTHR,rotS,exitM:round(along do lastOnRwy),_epoch}`; `break` (1 por voo/pista).
- Sem nenhum → `noCross++`. Ordena por epoch.
**ROT = tempo entre o cruzamento (interpolado) da THR e a última amostra radar ainda dentro do rectângulo da pista (−60…4300 m ao longo, ±220 m lateral) nos 300 s seguintes.** Não usa altitude nem velocidade.
`renderRotResults`: KPIs `N.º aterragens`, `ROT médio` (0 dec), `P85`/`P95` (= `vals[min(floor(n·0.85), n−1)]`), `Máximo`; tabela `N | Pista | Data | Voo | Hora THR | ROT (s) | Dist. saída (m)` (cor ≤45 verde, ≤60 amarelo, senão vermelho); diagnóstico `"ARR processados: … · sem pontos · THR não detectada · sem pista · ROT inválido · calculados"`. Filtro `_rotRwyFilter` ('all'|'02'|'20'). `exportRotCsv`: `N;Pista;Data;Voo;Hora_THR;ROT_s;Dist_saida_m` → `analise_rot_lppt_<date>.csv`.

## B.3 "Oper" — `runOperAnalysis()` (l.7221) / `renderOperResults()` (l.7267)
Tabela por **operador** (`_operPrefix`, regra 0.5 linha 3). **Nunca é chamada** na v3.5 (código morto; elementos `anaOperTable/anaOperKpi` não existem). Lógica, para fidelidade:
- Por `csn` em `flights`: `arr/dep/lvl` por `classifyFlight`.
- `rotSum/rotN` de `rotResults` por operador; `gaCount` de `goAroundResults`; `starViols` = nº de `iasResults.violations`; `appViols` = Σ pontos com `!/^THR/ && |deviation|>tol` de `iasAppResults.records`.
- `rotAvg=round(rotSum/rotN)` ou null; `medViols=(starViols+appViols)/(arr+dep+lvl)`.
- KPIs: `Operadores` (nº), `Maior volume ARR` (`"OP (n)"`), `Mais Go-Arounds`.
- Colunas: `Operador | ARR | DEP | LVL | ROT méd | GA | Viols STAR | Viols APP | Méd Viols`; sort default `arr` desc (`_operSort={col:'arr',dir:-1}`), clique alterna.
- `exportOperCsv`: cabeçalho `Operador,ARR,DEP,LVL,ROT méd (s),Go-Arounds,Viols STAR,Viols APP,Méd Viols` (vírgulas) → `operadores.csv`.
"Posição do seguidor no DEP" **não** pertence ao Oper — é um gráfico da Análise de Dados (B.4).

## B.4 "Separação entre chegadas" (FAST) — `buildFastPairs` (l.5804) / `renderFastResults` (l.5825)
### Controlos
- `fastThreshold` "Separação THR" default **160** s (30–300, passo 10), `oninput` re-render.
- Modo `_fastMode`: `all` ("Todos"), `lt` ("< Abaixo", botão toggled por defeito no HTML mas variável JS inicia em `'all'`), `range` ("Entre limite e 240s").
- `fastInterBtn` "A/C intercalar" (`_fastIntercalOnly`), `RWY02`/`RWY20` (`_fastRwyFilter`, toggle; 'all' se repetido).

### Algoritmo
- `buildFastPairs`: agrupa `finalResults` por `rwy|_dateRaw`; ordena por epochTHR; pares consecutivos `(lead,trail)` com `sep=trail.epochTHR−lead.epochTHR`; **descarta `sep<=0 || sep>600`**; ordena por `lead.epochTHR`.
- Filtro modo: `lt` → `sep<thr`; `range` → `thr<=sep<=240`.
- `depEpochs` = `_firstEpoch(f.rows)` de todos os voos (`flights`, sem filtro de visibilidade) com `classifyFlight==='dep'`; `_pairHasIntercalDep` = existe `d` com `t0<d<t1`.
- Filtro pista: `lead.rwy===_fastRwyFilter`.
- Enriquecimento: `depsIn` (DEPs entre t0 e t1, com csn), `depCnt`, `seq = 0→'AA', 1→'ADA', 2→'ADDA', ≥3→'AD…A'`; `firstDep`; `bNmAtDep = ((trail.epochTHR−firstDep.t) · (trail.iasTHR||140)/3600).toFixed(1)` se `trail.iasTHR` truthy e secs>0 (distância estimada do seguidor à THR no instante do 1º DEP, assumindo IAS constante na THR).

### Saídas
Tabela `# | Pista | Data | Líder | Hora (THR) | IAS Líder | Seguidor | IAS Seg. | Sep. (s) | Seq. | DEP | Seg. no DEP` (cor sep: `<120` vermelho, `<thr` laranja, senão verde). `window._fastFilteredPairs`.
Detalhe (`showFastDetail`): SVG vertical da final (12 NM, waypoints RWY02 `FAF/IF 11.3, OKNIE 7.0, NETVO 4.5`; RWY20 `UPKAT 11.0, TOPVI 8.0, ROKOB 5.0`), seguidor a `sep·140/3600` NM; DEPs colocados a 1.5+0.5i NM; painel com Hora THR/IAS/Alt THR de ambos; `"Distância aprox. quando líder cruzou THR: <sep·140/3600> NM"`; `"⚠ N descolagem(ns) entre as duas aterragens"`.
`exportAnaActiveCsv` (fast): `N;Pista;Data;Lider;Hora_lider;IAS_lider_kt;Seguidor;Hora_seguidor;IAS_seguidor_kt;Separacao_s` → `analise_fast_lppt_<date>.csv` (pares visíveis). Outras abas: holdings `N;Inicio;Data;Voo;Fix;Dist_fix_NM;Duracao_s;Voltas;Alt_min_ft;Alt_max_ft;Caixa_NM;Lat;Lon`; go-arounds `N;Hora;Data;Voo;Alt_min_ft;AGL_min_ft;IAS_kt;Subida_ft;Duracao_s;Aterrou;HoraTHR;Lat;Lon`.

## B.5 "Análise de Dados" — `sep_buildData` (l.7778) / `sep_renderAnalysis` (l.7851)
### Dados
`sep_results` (um por par de `_fastPairs`, **todos**, sem filtro de modo/pista):
`{horaA:lead.tTHRstr, pista:lead.rwy, csnA, csnB, iasA:round(lead.iasTHR), iasB, sepSec:round(sep), sepNm:+(sep·140/3600).toFixed(2), depCsn:firstDep.csn, depHora, bSecAtDep:round(secs), bNmAtDep:+(secs·(trail.iasTHR||140)/3600).toFixed(2) [só se trail.iasTHR truthy], seq/_seq, data:lead._dateRaw, _hasDep, _depCount, _id, _depDistances:[(trail.epochTHR−d.t)·ias/3600 para cada DEP, 2 dec], _viz:{A:{t,csn},B:{t,csn},deps:[{t,csn}]}, _hasB:true, _sepSecNum:round(sep)}`.
`sep_movementRows`: ARR de `finalResults` (`{type:'ARR',callsign,hora:tTHRstr,pista:rwy,data:_dateRaw,t:epochTHR}`) + DEP de `flights` classificados dep (`{type:'DEP',callsign,hora:HHMMSS(_firstEpoch),pista:rows[0]._rwy||'',data:rows[0]._date,t}`), ordenados por `t`. (Sem `company`, `ias`, `fileName` — ficam vazios nas tabelas.)

### Controlos (toolbar `sep-ad-wrap`)
`sep_anaLimit` "Limite crítico": 240/200/**165**(default)/140/120 s · `anaData` Data (Todas + datas de `sep_results`) · `sep_anaHour` Hora · `sep_anaPista` Pista (all/02/20) · `sep_anaTipo` (`all`, `withDep` "Com DEP entre aterragens", `noDep`) · `sep_anaSeq` (all/AA/ADA/ADDA/AD...A) · `sep_anaDepNm` "Seguidor no DEP até" (all/3/4/5/6 NM) · `sep_anaCrit` "Mostrar" (`all`, `crit` "Só abaixo do limite") · botões "Atualizar análise", "Download análise" (xls), "Relatório PDF".
`sep_anaFilteredRows()` (l.9259): `_hasB`; data; hora (`horaA[0:2]`); pista; tipo; seq (`_seq===seq` — nota: a opção `AD...A` nunca casa com `'AD…A'` gerado com reticência Unicode **[BUG]**); depNm: exige `_hasDep` e algum `_depDistances<=limite`; crit: `_sepSecNum<limit`.
`sep_anaFilteredMovements()`: por data/hora/pista.

### KPIs (mini-cards, clicáveis)
`pares precedente/seguidor analisados`=rows; `pares abaixo do limite`=`_sepSecNum<limit`; `abaixo do limite com DEP`/`sem DEP`; `menor separação` (1 dec " s"); `média`; `mediana` (`sep_median`: par→média dos dois centrais); `hora mais crítica` = `"HHh (n)"` hora com mais críticos (desemp. por hora asc); `hora mais movimentada` = `sep_modeBy(horaA[0:2])` `"HHh (n)"`; `pista mais usada` `"RWY xx (n)"`; `DEP entre chegadas` = Σ `_depCount`; `movimentos ARR+DEP` = movs; `pico de aterragens/descolagens/movimentos` = `"HHh (n)"` via `sep_movementHourSummary`. Cards superiores: `mFiles` (nº ficheiros carregados), `mRows` (nº de `sep_movementRows` — rotulado "registos radar"), `mLand` (`finalResults.length`), `mPairs` (`sep_results.length`). Status: `"<n> pares precedente/seguidor analisados · <c> abaixo de <limit>s"`.

### Gráficos (todos SVG, com modal de origem por barra)
1. **Distribuição das separações** (`sep_renderHist`): bins `[0,60,90,120,140,165,200,240,∞)`, labels `0-60,60-90,90-120,120-140,140-165,165-200,200-240,>240`; barra vermelha se `bins[i+1]<=limit || (bins[i]<limit && bins[i+1]>limit)`.
2. **Resumo por hora** (`sep_renderByHour`): barras agrupadas Total (azul) / Críticos (vermelho) por `horaA[0:2]`.
3. **Análise por pista** (`sep_renderRunway`/`sep_stackInfoBars`): para RWY 02 e 20 três barras: total, crit, DEP (pares com DEP).
4. **Tipo de sequência** (`sep_renderSeq`): ordem `AA,ADA,ADDA,AD...A`; Total/Críticos (`AD...A` nunca casa, ver [BUG]).
5. **Movimentos por hora** (`sep_renderMovementHour`): total ARR+DEP por hora `hora[0:2]` (só horas com dados).
6. **Movimentos por companhia** (`sep_renderCompanyMoves`): top 15 por `movements` de `sep_companySummary`.
7. **Top 10 companhias por taxa de ocorrências críticas** (`sep_renderCompanyInfractions`): `critical>0`, ordena `rate desc, critical desc, movements desc`, 10; valor `rate*100` 1 dec.
8. **Posição do seguidor no momento do DEP** (`sep_renderDepDistance`): valores = todos `_depDistances` dos rows; bins `[0,3,4,5,6,∞)`, labels `<3,3-4,4-5,5-6,>6` NM, nomes `muito crítico, crítico, apertado, normal, confortável`; vermelho para `<3` e `3-4`.
9. **Separação vs distância do seguidor** (`sep_renderSepDistance`): scatter x=`sepSec`, y=`sepNm`; botões `Todos / < limit / ≥ limit` (`sep_sepDistFilter`); laranja=com DEP, verde=sem; contorno vermelho se crítico; linha vertical no limite; grelha 3/4/5/6 NM.
10. **Timeline operacional** (`sep_renderTimeline`): eventos `precedente` (azul #0b5cad, y−16), `dep` (quadrado laranja), `seguidor` (roxo #7c3aed, y+16) nas lanes RWY 02 (y=150) / RWY 20 (y=260); zoom `all/4/2(default)/1` h; hora foco `auto` (= hora com mais eventos) ou fixa; etiquetas `crit(default)/none/all`; px/h 900/1200/1500/2000; segmentos lead→trail vermelhos (4px) se crítico. Clique → navega para a sub-aba FAST e destaca.
11. **IAS da aeronave seguidora** (`sep_renderIas`): bins `[0,140,150,160,170,∞)` sobre `iasB`, Total/Críticos.

### Tabelas
- **Top 10 situações mais críticas**: ordena `_sepSecNum` asc, 10; colunas `Pista | Data | Hora A | Callsign A | Callsign B | Seq. | Sep. s | Sep. NM | DEP | Hora DEP | Seguidor no DEP` (último = `bSecAtDep`).
- **Resumo por hora** (`sep_renderHourTable`): `Hora | Chegadas | Pares preced./seg. | < limite | Com DEP | Menor sep. | Média sep.`; `Chegadas` = nº distinto de `csnA|horaA|pista` em **todo** `sep_results` nessa hora (não filtrado); `Com DEP` = Σ `_depCount||1`.
- **Resumo por companhia** (`sep_renderCompanyTable`): `Companhia | Movimentos | ARR | DEP | Ocorrências críticas | Taxa por movimento`. `sep_companySummary(movs,pairs,limit)` (l.8273): por companhia (`companyFromCallsign`) conta movimentos ARR/DEP de `movs`; para cada par crítico incrementa `critical` nas companhias **distintas** de `csnA` e `csnB`; `rate=critical/movements` (0 se sem movimentos); ordena `movements desc, company asc`.

### Exportações da Análise de Dados
- **"Download análise"** `sep_exportAnalysisExcel()` (l.9702): ficheiro `analise_separacao_thr_lppt.xls` (HTML com MIME Excel, BOM). Secções: `<h2>Análise LPPT - limite Ns</h2>`; **Pares filtrados** (`Pista | Data | Hora A | Callsign precedente | IAS precedente | Callsign seguidor | IAS seguidor | Sep. s | Sep. NM | Seq. | DEP | Hora DEP | Seguidor à THR no DEP (s) | Seguidor à THR no DEP (NM)`); **Top 10 críticos** (`Pista | Data | Hora A | Precedente | Seguidor | Seq. | Sep. s | Sep. NM | DEP`); **Movimentos ARR+DEP** (`Tipo | Pista | Data | Hora | Callsign | Companhia | IAS | Ficheiro`); **Resumo por companhia** (`Companhia | Movimentos | ARR | DEP | Ocorrências críticas | Taxa`).
- **"Relatório PDF"** `sep_exportAnalysisPdf()` → `sep_buildAnalysisReportHtml(ctx)` (l.9773), A4 landscape, `print()` após 700 ms. Estrutura: `<h1>Relatório de Análise de Dados</h1>`, sub "Flight Track Viewer · Separação entre chegadas · LPPT · <data>"; tabela de filtros (8 pares de `sep_reportActiveFilters`: Limite crítico, Data, Hora, Pista, Tipo, Sequência, Seguidor no DEP até, Mostrar); **Síntese executiva** (parágrafos); **Destaques** (insights); **Indicadores principais** (15 kpiRows, grelha 4 col); secções de gráficos com texto interpretativo: *Distribuição de separações*, *Pares por hora*, *Comparação por pista*, *Sequências ARR/DEP*, *Movimentos por hora*, page-break + `<h2>Companhias aéreas</h2>` (*Volume por companhia*, *Taxa de ocorrências críticas*), page-break + `<h2>Factores operacionais</h2>` (*Posição do seguidor no DEP*, *Separação vs distância do seguidor*, *IAS do seguidor*), page-break + `<h2>Anexos tabulares</h2>` (`sep_compactRowsTable`: *Top 10 pares mais apertados* [Pista, Data, Hora, Precedente, Seguidor, Seq., Sep. s, Sep. NM, DEP], *Resumo por hora* [Hora, Chegadas, Pares, Críticos, DEP, Menor sep., Média sep.] máx 24, *Companhias* [Companhia, Movimentos, ARR, DEP, Críticos, Taxa] máx 15); nota final.
  Textos interpretativos verbatim: "Histograma de pares por intervalo de separação (segundos). Barras a vermelho intersectam o limite de Ns — concentração à esquerda indica sequências mais apertadas." · "Total de pares precedente/seguidor vs críticos por hora UTC. A hora <h> concentra o maior número de críticos." · "Volume, críticos e DEP intercalado por RWY 02 e RWY 20 — permite comparar pressão operacional entre cabeceiras." · "Tipos de sequência (AA, ADA, ADDA, AD...A): AA sem DEP intercalado; ADA/ADDA com uma ou mais descolagens entre chegadas." · "Perfil horário de movimentos ARR+DEP nos filtros activos — complementa a análise de pares com a carga operacional global." · "Top 15 operadores por movimentos no período filtrado; <top> lidera com <n> movimentos." · "Companhias com maior taxa de críticos por movimento (mínimo de ocorrências relevantes) — útil para identificar operadores com sequências mais apertadas." · "Distância do seguidor à THR no momento da descolagem intercalada. Valores baixos (<3–4 NM) indicam DEP mais apertado e maior risco de sequência crítica." · "Cada ponto representa um par: eixo X = separação (s), eixo Y = distância NM do seguidor. Linha vertical = limite Ns. Pontos abaixo da linha são críticos." · "Distribuição de pares por classe de IAS do seguidor na THR — velocidades mais altas podem reduzir margem de recuperação em sequências apertadas." · rodapé "Relatório gerado automaticamente a partir dos dados carregados no Flight Track Viewer. A timeline interactiva e o detalhe completo de pares estão disponíveis na aplicação e na exportação Excel."

**Narrativa `sep_buildAnalysisNarrative(ctx)` (l.9720)** — `critRate=round(crit/pairs*1000)/10`; parágrafos (verbatim, na ordem; `insights` entre parênteses):
1. `"Este relatório analisa a separação entre chegadas consecutivas na LPPT, com limite crítico de <limit> segundos.[ Filtros activos: <k: v; …>.] A amostra inclui <pairs> par(es) precedente/seguidor[ e <movs> movimentos ARR+DEP]."` (filtros excluídos se valor ∈ {Todas, Tudo, "Todos os pares precedente/seguidor", "Qualquer distância"} ou vazio)
2. `"Os dados provêm de <files> ficheiro(s) CSV (<radarRows> registos radar, <landings> passagens THR, <allPairs> pares na janela global)."`
3. (se pairs) `"Foram identificados <crit> pares abaixo do limite (<critRate>%)[, dos quais <critDep> com descolagem intercalada (DEP) e <critNoDep> sem DEP]."`
   - `critRate>=15`: `"A taxa de críticos (<r>%) é elevada e sugere pressão operacional significativa na sequência de chegadas analisada."`
   - `>0`: `"A taxa global de críticos (<r>%) é moderada; convém cruzar com hora, pista e tipo de sequência para localizar concentrações."`
   - `0`: `"Não foram registados pares abaixo de <limit>s nos filtros seleccionados."` (insight `"<r>% dos pares abaixo de <limit>s"`)
4. (se minSep) `"A menor separação observada foi <min> s[, com média de <avg> s e mediana de <med> s] — indicadores úteis para avaliar o aperto típico vs casos extremos."` (insight `"Menor separação: <min> s"`)
5. `"A hora com mais pares críticos foi <HHh (n)>, o que aponta para o período do dia com maior risco de sequências apertadas."` (insight `"Hora mais crítica: …"`)
6. `"A hora mais movimentada em pares precedente/seguidor foi <…> — nem sempre coincide com a hora mais crítica, o que pode indicar densidade vs aperto real."`
7. `"O pico de aterragens ocorreu à hora <…>."` · `"O pico de descolagens ocorreu à hora <…>, relevante para sequências ADA/ADDA com DEP intercalado."`
8. `"<RWY vol> concentra <total> pares (<crit> críticos, <rate>%)[; <RWY> regista taxa de <rate>%]."` (insight `"Pista principal: RWY xx"`)
9. `"A sequência dominante é <seq> (<total> pares, <crit> críticos)[; <seq2> destaca-se com <n> ocorrências críticas]."` + (`AA`: `"Predominância de sequências AA (chegada seguida de chegada, sem DEP) indica fluxo principalmente de aterragens consecutivas."` / `ADA`: `"Sequências ADA frequentes indicam descolagens intercaladas entre chegadas — factor relevante na gestão de separação."`)
10. `"<top.company> lidera em movimentos (<n> ARR+DEP[, <crit> ocorrências críticas (<rate>)])."` · `"<worst> apresenta a maior taxa de críticos por movimento (<rate>)."` (se ≠ top)
11. `"O par mais apertado foi <A> → <B> (<sep> s, <nm> NM) em <data> às <hora>[, com DEP <csn>]."`

## B.6 "Análise Diária" — `renderSepDaily` (l.9423) / `sep_renderDailyContentGlobal` (l.9437)
Usa `selDaysSet`/`selBlocksSet` do painel esquerdo; limite = `sep_anaLimit` (165). `inBlock(h)` = sem blocos seleccionados ou hora dentro de algum bloco `"HH-HH"` (`[s,e)`). `movs`/`rows` filtrados por data e hora. Botões: "🔄 Actualizar análise diária", "⬇ Excel" (`sep_exportDailyExcel`), "📄 Relatório PDF".
- **KPIs** (10): dias selecionados; movimentos ARR+DEP; aterragens; descolagens; pares precedente/seguidor; pares abaixo do limite; críticos com DEP; pico de aterragens `"HHh (n)"`; pico de descolagens; callsigns comuns aos dias (callsigns presentes em >1 dia).
- Por dia `stats`: `{label:"MM-DD Dow", date, wd, wdName, arr, dep, total, pairs, crit}`; `parseYMD` aceita YYMMDD/YYYYMMDD/`YYYY-MM-DD`; `WD_SHORT=['Dom','Seg','Ter','Qua','Qui','Sex','Sáb']`, `WD_LONG=['Domingo',…,'Sábado']`.
- **Gráficos**: *Movimentos por dia* (agrupado ARR azul / DEP vermelho); *Ocorrências críticas por dia*; *Pico horário por dia* ("Hora com mais movimentos em cada dia selecionado", valor = total da hora pico, tooltip `Hora pico`); *Companhias por dia* (top 10 por movimentos, "Companhia inferida pelo prefixo do callsign").
- **Padrões por dia da semana** (`wdAgg`): por `wd` soma `days, mov, arr, dep, pairs, crit, critDep`; `avgMov=mov/days`, `avgCrit=crit/days`, `rate=crit/pairs*100`; ordem Seg→Dom (`[1,2,3,4,5,6,0]`); `r1` = 1 decimal. Destaques: "Mais movimentos (média/dia)", "Mais críticos (média/dia)", "Maior taxa de críticos". Gráficos *Média de movimentos por dia da semana* ("Total de movimentos ÷ nº de dias desse dia da semana.") e *Média de pares críticos por dia da semana* ("Pares abaixo do limite (Ns) ÷ nº de dias."). Tabela `Dia da semana | Nº dias | Mov. totais | Méd mov/dia | Críticos totais | Méd crít/dia | Taxa crít. | Datas`.
- **Voos/callsigns comuns entre dias selecionados**: `Callsign | Nº dias | Dias | Movimentos | Companhia` (máx 80, ordenado count desc, csn asc).
- **Resumo por dia e hora**: `Data | Hora | ARR | DEP | Movimentos | Pares | Críticos` (só horas com dados e dentro dos blocos).
- **Excel diário** (`analise_diaria_lppt.xls`): `<h2>Análise Diária LPPT — limite Ns</h2>`, Dias seleccionados, Blocos horários; tabelas *Indicadores* (Indicador|Valor), *Resumo por dia* (Data, Dia sem., ARR, DEP, Movimentos, Pares, Críticos), *Padrões por dia da semana* (8 col), *Top companhias* (Companhia, Movimentos, ARR, DEP, Críticos, Taxa), *Callsigns comuns entre dias*, *Resumo por dia e hora* (Data, Dia sem., Hora, ARR, DEP, Movimentos, Pares, Críticos).
- **PDF diário** (`sep_buildDailyReportHtml`, l.10011): `<h1>Relatório de Análise Diária</h1>`, filtros (Período, Limite crítico, Blocos horários, Dias analisados), Síntese executiva, Destaques, Indicadores principais, gráficos *Movimentos por dia* ("Comparação de aterragens (ARR) e descolagens (DEP) por dia seleccionado. O dia <d> destaca-se com <n> movimentos (média global: <avg>/dia)."), *Ocorrências críticas por dia*, *Pico horário por dia* ("Hora com maior volume de movimentos (ARR+DEP) em cada dia — indica o período de maior densidade operacional diária."), *Companhias por dia*; page-break *Padrões por dia da semana* (texto "Agrupamento por dia da semana com médias por dia (comparação justa quando há diferente número de segundas, terças, etc.). <dia> regista a maior média de críticos (<n>/dia).") com os 2 gráficos e tabela `Dia | Nº dias | Mov. totais | Méd mov/dia | Críticos | Méd crít/dia | Taxa % | Datas` (12); page-break *Anexos tabulares*: Resumo por dia (30), Companhias (10), Callsigns comuns (20), Resumo por dia e hora (amostra) (40).
  **Narrativa `sep_buildDailyNarrative`** (l.9933), verbatim:
  1. `"Este relatório analisa <n> dia(s) seleccionado(s) (<dias>), considerando os blocos horários <blocos>. O limite de separação crítica aplicado é <limit> segundos entre chegadas consecutivas."`
  2. `"No período foram registados <movs> movimentos (<arr> aterragens e <dep> descolagens), o que corresponde a uma média de <avgMov> movimentos por dia analisado."` (insight `"<movs> movimentos ARR+DEP no período"`)
  3. `"Foram identificados <pairs> pares precedente/seguidor. Destes, <crit> (<rate>%) ficaram abaixo do limite de <limit>s[, incluindo <critDep> com descolagem intercalada (DEP)| sem DEP intercalado relevante]."` + (≥15: `"A taxa de críticos (<r>%) é elevada face ao volume analisado e merece atenção operacional, sobretudo nas horas e dias com maior concentração de ocorrências."`; >0: `"A taxa global de críticos (<r>%) situa-se num patamar moderado; convém cruzar com os dias e horas de pico para identificar padrões localizados."`; 0: `"Não foram registados pares abaixo do limite de <limit>s no período e filtros seleccionados."`)
  4. `"O dia de maior volume operacional foi <data>[ (<dia semana>)], com <total> movimentos (<arr> ARR / <dep> DEP) e <crit> pares críticos."` (insight `"Pico diário: <data> · <n> mov."`) · `"O dia de menor volume foi <data> (<n> movimentos), útil como referência de carga operacional mínima no conjunto analisado."`
  5. `"O dia com mais ocorrências críticas foi <data> (<crit> pares abaixo do limite, <rate>% dos <pairs> pares desse dia)."` (insight `"Mais críticos: <data> · <n> pares"`)
  6. `"As aterragens concentram-se tipicamente na hora <HHh (n)>, indicando o período do dia com maior pressão na sequência de chegadas."` · `"As descolagens atingem o máximo à hora <…>, o que pode influenciar a intercalação ARR/DEP e a formação de sequências ADA/ADDA."`
  7. `"A companhia com mais movimentos no período foi <c> (<n> movimentos[, <k> ocorrências críticas associadas])."` · `"Seguem-se <c2 (n)>, <c3 (n)>, <c4 (n)> entre as operadoras mais activas."`
  8. (≥2 dias da semana) `"Comparando dias da semana (médias por dia para comparar de forma justa), <dia> regista a maior média de movimentos (<avg>/dia em <k> dia(s) analisado(s))."` · `"<dia> apresenta a maior média de pares críticos (<avg>/dia)[, com taxa de <rate>% em <dia>] — útil para comparar, por exemplo, terças vs quartas ao longo do mês."` (insight `"Dia da semana mais crítico (média): <dia>"`)
  9. `"Foram encontrados <n> callsign(s) comuns a mais do que um dos dias seleccionados, o que facilita a comparação de padrões horários ou de sequência entre datas equivalentes."` ou (n>1 dias) `"Não há callsigns repetidos entre os dias seleccionados, pelo que a comparação deve focar-se em indicadores agregados (volume, críticos, hora) e não em voos individuais recorrentes."`
  10. `"A hora com mais pares críticos no conjunto analisado foi <HH>h do dia <data>[ (<dow>)] (<crit> críticos em <pairs> pares)."`

## B.7 Holdings e Go-Arounds (escondidos; alimentam KPIs/alertas/IA)
**`detectHoldings()`** (l.5469): `arptR=max(10, anaArptRadius||30)` NM (elemento não existe → 30); `MIN_TURN=270°, MAX_BOX=12 NM, MIN_DUR=90 s`. Por leg visível com ≥8 pontos e algum ponto a ≤30 NM do centro do aeroporto: calcula `_db` (variação de rumo entre segmentos consecutivos, normalizada); janela deslizante a partir de `i`: acumula `sumTurn`, bounding box; pára se diagonal da box `>12 NM`; se `|sumTurn|>=270 && dur>=90` (**[BUG]** `dur=(t−startT)/1000` com t em segundos → exige 90000 s → holdings praticamente nunca detectados) estende enquanto se mantém na box e não há 6 pontos seguidos com `|_db|<3°`; regista `{startStr,endStr,durS,turns=|sumTurn|/360,cLat,cLon,boxNM,fix(ponto mais próximo do centro se ≤8 NM),fixD,altMin,altMax,_track}`.
**`detectGoArounds()`** (l.5568): `MIN_ALT=3000, MIN_CLIMB=800` (ft), `MAX_ALT_THR=3500` (não usado); legs visíveis `arr` com ≥8 pts com alt, ≥6 dentro de 30 NM; mínimo local `near[i].alt<=3000` com `near[i−3].alt−alt>=300` e `max(alt i+1..i+3)−alt>=800`; extensão da subida até cair 500 ft abaixo do máximo; `maxClimb−alt>=800`; **skip se existe aterragem (finalResults) para `csn|date` com `|t−epochTHR|<120000`** ([BUG] unidades: 120000 s ≈ 33 h → qualquer voo com aterragem detectada nesse dia nunca é GA); regista `{tMinStr,epochMin,altMin,aglMin=alt−elev,iasMin,altMaxAfter,climb,lat,lon,eventuallyLanded,landedAt,climbEndStr,durSinceMin=(tEnd−tMin)/1000}` ([BUG] /1000).

---

# C. Abas "Pontos" e "Sequência"

### C.1 Base de dados de pontos
- `AIP_POINTS` (constante, ~l.2700–2945): `{name, lat, lon, type:'aip', desc}`; `desc` contém o ICAO (`'... LPMA'`, `'... LPPR'`, `'... LPFR'`) para pontos desses aeroportos; pontos LPPT não têm tag.
- `userPoints` (`type:'user'`), `selectedPoint`, `ptQueryResults`, `iasFilter={op:'any',v1:NaN,v2:NaN,tol:2}`, `seqResults`, `pointMode='ALL'` (l.2947).
- `POINT_GROUPS` (l.2951): `APP_02=[PESEX,NETVO,OKNIB,THR02]`, `APP_20=[UPKAT,TOPVI,ROKOB,THR20]`, `STAR02=[ESUTI,INBOM,LAZET,LUVUP,PULPO,VATZI,XAMAX,CASLU,MAZUK,ERNIL,RELKU,ZEFFI,NEVUD,PESEX,GANSU,YETSI,ORTUG,ZACRA,INLIB,MIGTO,ULTIT]`, `STAR20=[ESEBI,ESUTI,INBOM,LAZET,LUVUP,PULPO,VATZI,XAMAX,ITAVIT,DEKKI,ROMEP,EVPAP,FUSSI,ARNIT,UPKAT,PT813,PT811,PT818,EKLID,ROTBU,LERLI,FADEF,COCUN]`, `LPMA_APP_05=[PILIM,MONEC,ABUSU,MA563,MA564,MA565,MA566,THR05]`, `LPMA_APP_23=[PILIM,MONEC,MA410,MA561,MA562,THR23]`, `LPPR_APP_17=[ADNOV,PR741,PR742,THR17,PR744,RETMO]`, `LPPR_APP_35=[AKULU,PR541,PR542,THR35,PR544,RETMO]`, `LPPR_STAR17=[ABLEG,VASIP,PR650,PR612,ADNOV]`, `LPPR_STAR35=[ABLEG,AKULU,VASIP]`, `LPFR_APP_10=[RUWIB,FR910,THR10,FR728,GIMAL]`, `LPFR_APP_28=[GEBTI,FR928,THR28,FR710,GIMAL]`. `POINT_GROUPS_ALL` = união.
- `allPoints()` (l.2979): nomes activos = `POINT_GROUPS_ALL` se `pointMode==='ALL'` senão o grupo. Para cada AIP point: se `desc` contém `activeAirport` → incluído se modo ALL, senão se nome ∈ activos; senão (sem tag) incluído só se `activeAirport==='LPPT'` e nome ∈ activos. Devolve `[...aip, ...userPoints]`.
- Botões de modo (`buildPointModeButtons`): LPPT `APP 02, APP 20, STAR 02, STAR 20, TODAS`; LPMA `APP 05, APP 23, TODAS`; LPPR `APP 17, APP 35, STAR 17, STAR 35, TODAS`; LPFR `APP 10, APP 28, TODAS`.
- Ao abrir a aba Pontos em LPPT com modo ALL: `setPointMode('APP_02')` e auto-selecciona o 1º ponto do APP_02 (PESEX) se nenhum (l.2604).
- `addManualPoint()`: nome upper, lat/lon decimais, `|lat|<=90`, `|lon|<=180`, nome único; `desc:'Ponto manual'`. `removePoint(name)` só user points.
- `exportPointsJSON()` → `points.json` = `JSON.stringify(userPoints,null,2)`. `importPointsJSON(file)` (l.3045): array de `{name,lat,lon,desc?}`; ignora sem `name` ou lat/lon NaN ou nome já existente em `allPoints()`; adiciona `{name,lat:+lat,lon:+lon,type:'user',desc:desc||'Ponto importado'}`; alerta `"<n> ponto(s) importado(s)."`.
- `renderPointList()` (l.3062): filtro `ptSearch` (substring case-insensitive em `name` ou `desc`); contador `(<nº allPoints>)`; item mostra nome, badge AIP/Manual, desc, coordenadas DMS; clique selecciona.

### C.2 Pesquisa de passagens — `queryPoint()` (l.3168) / `renderPtResults` (l.3194)
**Controlos**: `ptRadius` "Raio" default **1** NM (0.1–50, passo 0.1); botão **▶ Pesquisar**; **↓ CSV**; filtro IAS: `iasOp` ∈ `any`(Qualquer)/`lt`(<)/`le`(≤)/`eq`(= ±)/`ge`(≥)/`gt`(>)/`between`(entre); `iasV1`, `iasV2` (só between), `iasTol` default **2** (só eq); **✕ Limpar**.
**Algoritmo**:
- `radius=parseFloat(ptRadius)||1`. Bounding box: `maxDegLat=(radius/60)·1.2`, `maxDegLon=(radius/60/cos(lat))·1.2`.
- Para cada voo **visível** (`isFlightVisible`) e **cada row** com lat/lon válidos dentro da box: `d=distNM(pt,row)`; se `d<=radius` → regista `{csn, d:d.toFixed(2), tod:tod[0:12], date:fmtDate(_date) ou '', block, alt:getAlt, ias:gv(r,'iar','iara'), roc:gv(r,'roc'), tipo:'ARR'|'DEP'|'NVL', lat:5dec, lon:5dec, color}`. **Uma linha por amostra radar** (não por voo) — um voo lento no raio gera várias linhas.
- Ordena por `date` (string, dd/mm/yyyy — ordenação lexicográfica) e depois `tod`.
- Filtro IAS (`passesIasFilter`, l.3153): inactivo se `op==='any'` ou `v1` NaN ou (between e `v2` NaN); IAS não numérica → falha. `lt: n<v1; le: n<=v1; eq: |n−v1|<=tol; ge: n>=v1; gt: n>v1; between: min(v1,v2)<=n<=max(v1,v2)`. Label: `"< v1 kt"`, `"≤ v1 kt"`, `"= v1 ± tol kt"`, `"≥ v1 kt"`, `"> v1 kt"`, `"v1–v2 kt"`.
- Desenha círculo no mapa (laranja, `radius·1852` m).
**Saídas**: contador `"<N> passagem(ns) no raio de <r> NM"` e `"<n> com IAS <label>"`; tabela `Hora | Data | Bloco | Voo | Tipo | Dist (NM) | Alt (ft) | IAS | ROC | Lat | Lon` (Lat/Lon em DMS se `coordMode==='geo'`; ROC verde >0 / vermelho <0); vazio: `"Nenhuma passagem com IAS <label>"` ou `"Nenhum voo encontrado neste raio"`.
**`exportPtResult()`** (l.3233): CSV `;` BOM `Hora;Data;Bloco;Voo;Tipo;Dist_NM;Altitude_ft;IAS_kt;ROC_fpm;Latitude_dec|Latitude_geo;Longitude_dec|Longitude_geo`, linhas filtradas pelo IAS; nome `passagens_<PONTO>[_IAS_<op><v1> | _IAS_<min>-<max>]_<YYYY-MM-DD>.csv`.

### C.3 Sequência — `querySequence()` (l.3317) / `renderSeqResults` (l.3370)
**Controlos**: `seqPointSel` (todos os `allPoints()` ordenados por nome, label `"NAME · desc (manual)"`; pré-selecciona `selectedPoint`), `seqRadius` "Dist. máx" default **1** NM, **▶ Pesquisar**, **↓ CSV**. `SEQ_MAX_NEIGHBOR_NM=20`.
**Algoritmo**:
- Para cada voo visível: **CPA** = row com menor `distNM` ao ponto entre as que estão `<=radius` (bounding box ×1.2). **Uma linha por aeronave.** Regista `{csn,dNum,tod,date,_dateRaw,_epoch:rowEpoch(row),block,alt,ias,lat,lon,color}`.
- Ordena por `_epoch` (ordem de passagem no ponto).
- Para cada `i`: `antD` = distância espacial entre a posição CPA desta aeronave e a posição **interpolada no tempo** (`flightPosAt(flights[prev.csn], tCur)`, interpolação linear lat/lon entre amostras; null se `tCur` fora do intervalo do voo) da aeronave anterior na sequência (`seqResults[i−1]`) no instante `tCur`; `segD` idem para a seguinte (`seqResults[i+1]`). Null se não calculável.
- Círculo verde no mapa.
**Saídas**: contador `"<N> aeronave(s) ≤ <r> NM · <PONTO>"`; tabela `# | Hora | Data | Bloco | Voo | Dist CPA (NM) | AC à frente (NM) | AC atrás (NM) | Alt (ft) | IAS`; vizinhos: `'—'` se null, `">20"` se >20 NM, senão 1 dec com vírgula (`fmtSeqNeighbor`).
**`exportSeqResult()`**: `Seq;Hora;Data;Bloco;Voo;Dist_CPA_NM;AC_a_frente_NM;AC_atras_NM;Altitude_ft;IAS_kt` → `sequencia_<PONTO>_<date>.csv` (vizinhos `''` se null, `">20"`, ou 1 dec vírgula).

### C.4 Auto-execução (l.7423)
Após cada `applyFilter`, em LPPT: `setPointMode('APP_02')`, selecciona **PESEX**, corre `queryPoint()`; na Sequência selecciona PESEX e corre `querySequence()`.

---

# D. Exportações

## D.1 "Exportar CSV / Excel" (Preferências → modal `exportModal`) — `_buildExportSheets()` (l.2639)
Três folhas fixas (ordem `Geral`, `BLACK-LIST`, `FAST`):
- **Geral**: `HORA | DATA | VOO | TIPO | ALTITUDE | IAS | LATITUDE | LONGITUDE`. Fonte: todas as rows de voos **visíveis**, ordenadas por `tod` (string); HORA `tod[0:12]`, DATA `fmtDate(_date)` ou vazio, TIPO `ARR/DEP/NVL` (classifyFlight do voo), ALTITUDE `getAlt`, IAS `gv(r,'iar','iara')`, LAT/LON DMS se `coordMode==='geo'` senão 6 decimais.
- **BLACK-LIST**: `HORA | DATA | VOO | PISTA | PONTO1 | IAS1 | LIMITE1 | DESVIO1 | … | PONTO4 | IAS4 | LIMITE4 | DESVIO4`. Fonte: `iasAppResults.records` na ordem das linhas actualmente visíveis na tabela `#iasAppViolBody` (`data-idx`, deduplicadas); se nenhuma linha no DOM → todos os records. PISTA `parseInt(rwy)`; IAS/LIMITE arredondados; DESVIO com sinal `+/-`; pad a 4 pontos.
- **FAST**: `HORA | DATA | RWY | LIDER (THR) | IAS LIDER | SEGUIDOR | IAS SEG. | SEP (s) | A/C INTERCALAR | CALL_SIGN | HORA DEP`. Fonte: `renderFastResults()` e depois `window._fastFilteredPairs` (filtro activo da sub-aba FAST); `depEvents` = `_firstEpoch` dos voos DEP; primeiro DEP com `t0<t<t1` → `'Sim'`, csn, `epochToHHMMSS`; senão `'Nao'`, `''`, `''`.
- `doExport()`: CSV único `;` com as 3 secções separadas por linha vazia e nome da secção; aspas se `[;"\r\n]`; `export_operacional_<date>.csv`.
- `doExportExcel()`: carrega `xlsx@0.18.5` (`_ensureXlsxLib`), `XLSX.utils.book_new()` + `aoa_to_sheet` por folha + `book_append_sheet(wb,ws,name)`; `XLSX.write(bookType:'xlsx')` → `export_operacional_<date>.xlsx`.

## D.2 PPTX — `exportIasAppChartsPptx()` (l.5334), com `pptxgenjs@3.12.0`
Pré-requisito: `openIasAppCharts()` (aba Velocidades APP → "Análise (gráficos)") que preenche `_lastIasAppChartExport={caption,radius,tol,arrLegs,charts:[{samples,limit,tol,title,rwy}…]}` — um chart por ponto de `POINT_GROUPS.APP_02` (PESEX,NETVO,OKNIB,THR02) e `APP_20` (UPKAT,TOPVI,ROKOB,THR20), com `samples` = IAS ao CPA (raio `iasAppRadius`, default 1 NM) de todas as legs ARR visíveis (dedupe pista/dia: se o mesmo `csn|date` aparece em ambas as pistas e numa só passa por 1 ponto e noutra por ≥2, descarta a de 1 ponto); limites `APP_IAS_DEFAULTS` (`APP_02:{PESEX:180,NETVO:160,OKNIB:160,THR02:160}`, `APP_20:{UPKAT:180,TOPVI:160,ROKOB:160,THR20:160}`).
Layout `LAYOUT_16x9`:
- **Slide 1**: texto `'IAS na final (APP) — LPPT'` (x0.4,y0.22,fs20,cor 0284C7,bold); `caption` (x0.4,y0.62,w9.2,h2.05,fs9,cor 334155,valign top) = `"<Ano(s): …> · Dias: … · Blocos: … · N ficheiro(s) no filtro · N movimento(s) visível(is) (N ARR) · Raio CPA r NM · tolerância ±t kt (tabela de violações usa o mesmo ±)"`; `'Glossário'` (y2.78,fs12,bold); `iasAppChartsGlossaryPlain(tol)` (y2.98,w9.2,h2.5,fs7.5) — 8 linhas verbatim (l.4784): "n — Número de passagens com IAS válida ao CPA neste fix (após deduplicação pista/dia)." / "Média — Soma das IAS dividida por n." / "Mediana — Valor que divide a distribuição ao meio (metade das observações abaixo, metade acima)." / "Limite (linha tracejada no gráfico) — Velocidade máxima publicada (AIP) para o fix." / "Tolerância (±t kt) — Igual ao campo da aba Velocidades APP; cada observação classifica-se face a limite ± tolerância." / "Cores nas barras — Verde: IAS entre limite−tol e limite+tol (conforme). Amarelo: abaixo de limite−tol. Vermelho: acima de limite+tol." / "" / "Legenda: verde = conforme · amarelo = abaixo do limite (com tolerância) · vermelho = acima do limite (com tolerância) · linha tracejada = limite publicado."
- **Um slide por chart (8)**: título `"<fix> · RWY <rwy>"` (x0.35,y0.2,fs16,cor 0f172a,bold); imagem PNG (`svgToPngDataUrl`, SVG 960×400 rasterizado a 1920×800, fundo #f8fafc) em x0.35,y0.55,w9.3,h4.35.
- Histograma `iasAppHistogramSvg` (l.4696): eixo X IAS de `max(40, floor((min−12)/5)·5)` a `min(300, ceil((max+12)/5)·5)` (mín. 35 kt de largura), bins de 5 kt, empilhado amarelo (abaixo de `limite−tol`) / verde (conforme) / vermelho (acima de `limite+tol`), linha vermelha tracejada no limite, meta `"n=N · média X kt · mediana Y kt · limite L kt · tolerância ±t kt"`, 5 ticks.
- Ficheiro `ias_app_final_<date>.pptx`. Existe também `exportIasAppChartsPng()` (cabeçalho + 8 histogramas 800×230 empilhados num PNG).

## D.3 Relatório por voo — `_exportFlightPDF(csn,color)` (l.6944) (botão "📄 PDF" no modal do voo)
- `rows` = rows do voo no **dia mais recente** (se vários `_date`); `dateStr=fmtDate`.
- Stats: `Pontos` (nº rows), `Alt máx/mín` (getAlt), `IAS máx` e `IAS méd` (round; valores >0), `Início`/`Fim` (`tod[0:8]` da 1ª/última row).
- APP: `appRec = iasAppResults.records.find(csn)`; `appPoints` = pontos com ias; `appViols` = `!/^THR/ && |deviation|>tol`. STAR: `iasResults.violations.filter(csn)`.
- Gráfico: PNG do canvas `#fmProfileChart` (`_drawProfileChart`, l.7311: IAS linha ciano + área, altitude linha verde tracejada, gates 10/7/5/4 NM com IAS anotada; pontos = rows a ≤20 NM da THR da pista do appRec ou da pista cuja THR está em média mais perto das últimas 30 rows).
- Documento A4 portrait `Relatório <csn>`: cabeçalho `<csn>` + `"Relatório de Voo · Flight Track Viewer v3.5 · NAV Portugal · <data>"` + badge `"✔ Sem violações"` ou `"⚠ N viol. APP M viol. STAR"`; grelha 8 stats (Data, Pontos, Alt máx, Alt mín, IAS máx, IAS méd, Início, Fim); bloco narrativo `_buildFlightAnalysis`; `<h2>Perfil IAS / Altitude</h2>` + imagem; tabela APP `Pista | Waypoint | IAS | Limite | Desvio | Avaliação` ("⚠ Acima"/"▼ Abaixo"/"✔ OK"); tabela STAR `Hora | Data | Waypoint | IAS | Limite | Excesso`; `"Sem dados de violações registados para este voo."` se nada; rodapé; `print()`.
- **Narrativa `_buildFlightAnalysis`** (l.7052) verbatim: `"<csn> — análise de velocidades para <data>."` · `"Velocidade máxima registada: <max> kt. Média: <med> kt."` · `"Na fase de aproximação, foram avaliados <n> ponto(s): <lista>."` (**[BUG]** usa `x.name` que não existe nos pontos → lista vazia) · `"⚠ <n> ponto(s) acima do limite: <NAME> (<ias>kt, lim. <lim>kt, +<dev>kt); …"` · `"▼ <n> ponto(s) abaixo do limite: …"` · `"Desvio máximo: <point> com <±dev>kt (lim. <lim>kt)."` · `"✔ Todos os pontos de aproximação dentro do limite (tolerância ±<tol>kt)."` · `"Sem dados de velocidade de aproximação disponíveis."` · `"Na fase STAR: <n> violação(es) em <k> waypoint(s) — <wps>. Excesso máximo: +<max>kt."` · `"✔ Sem violações de velocidade na fase STAR."` · `"Conclusão: Voo sem violações de velocidade detectadas."` ou `"Conclusão: Registadas <n> violação(es). Recomenda-se revisão do perfil de desaceleração."`

## D.4 Outros relatórios
- l.6502–6541: `openReport()` = Relatório Operacional dos KPIs (ver A).
- l.10865–10990: `iaExportar(fmt)` = exportação da conversa IA (ver E.5) — é daí que vêm `tipo`/`textoHtml` (l.10932, 10966).
- Modal de dados (`sep_openDataModal`): "Exportar estes dados" (`.xls` HTML: movimentos `Tipo,Pista,Data,Hora,Callsign` ou pares 13 colunas) e "PDF" (tabela do modal).

---

# E. Análise IA

## E.1 `IA_PROVIDERS` (l.10154)
| key | name | url | type | models `[id, label]` |
|---|---|---|---|---|
| anthropic | Claude (Anthropic) | `https://api.anthropic.com/v1/messages` | anthropic | `claude-sonnet-4-5` "Claude Sonnet 4.5 (recomendado)", `claude-haiku-4-5` "Claude Haiku 4.5 (mais rápido)", `claude-opus-4-5` "Claude Opus 4.5 (mais potente)" |
| openai | OpenAI (ChatGPT) | `https://api.openai.com/v1/chat/completions` | openai | `gpt-4o` "(recomendado)", `gpt-4o-mini` "(mais rápido)", `gpt-4-turbo` |
| mistral | Mistral AI | `https://api.mistral.ai/v1/chat/completions` | openai | `mistral-large-latest`, `mistral-small-latest`, `open-mixtral-8x22b` |
| azure | Azure OpenAI | `''` (endpoint do utilizador) | azure | `gpt-4o`, `gpt-4`, `gpt-35-turbo` |
| groq | Groq (Llama) | `https://api.groq.com/openai/v1/chat/completions` | openai | `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `mixtral-8x7b-32768` |

Persistência (localStorage): `ia_provider` (default `'anthropic'`), `ia_key_<prov>`, `ia_model_<prov>` (default = 1º modelo), `ia_azure_endpoint`. Chave "baked" `_IA_BAKED_KEY='__ANTHROPIC_API_KEY__'` (substituída no build; usada se não começar por `__` e não houver chave guardada para anthropic).

**Pedidos** (l.10714):
- anthropic: POST, headers `Content-Type: application/json`, `x-api-key`, `anthropic-version: 2023-06-01`, `anthropic-dangerous-direct-browser-access: true`; body `{model, max_tokens:2048, system:SYSTEM, messages:[{role:'user', content: ctx+'\nPERGUNTA: '+q}]}`; resposta `data.content[0].text`.
- azure: URL `<endpoint sem / final>?api-version=2024-02-01`, header `api-key`; body `{messages:[{system},{user}], temperature:0.2, max_tokens:2048, response_format:{type:'json_object'}}`; resposta `choices[0].message.content`.
- openai-compatível (openai/mistral/groq): header `Authorization: Bearer <key>`; body `{model, messages:[system,user], temperature:0.2, max_tokens:2048, response_format:{type:'json_object'}}`.
- **Sem streaming; sem histórico enviado** — cada pergunta envia apenas `SYSTEM` + contexto completo + `"PERGUNTA: <q>"`.

## E.2 System prompt (verbatim, l.10708)
```
Es um especialista em analise de dados de trafego aereo e radar. Responde SEMPRE em JSON valido, sem markdown, sem texto fora do JSON. Estrutura: {"texto":"explicacao em portugues de Portugal sem asteriscos","grafico":{"tipo":"bar|pie|line|doughnut","titulo":"titulo","dados":[{"nome":"label","valor":numero}]}} O campo grafico e OPCIONAL. Os valores em valor devem ser SEMPRE numeros inteiros ou decimais, NUNCA strings. Para listas usa hifen (-).
```

## E.3 Contexto enviado — `_iaBuildCtx()` (l.10319)
Texto plano com secções (todas sobre `flights` **sem** filtro de visibilidade, contagem por callsign e não por leg):
1. `DADOS CARREGADOS NO FLIGHTTRACKER:` / `Total aeronaves: T | ARR: a | DEP: d | NVL: n` / `Periodo: HH:MM-HH:MM` (min/max de `tod[0:5]`, só se `>'00:00'`).
2. `Voos por operador (lista completa):` linhas `  PRE: total= | ARR= | DEP= | NVL=` (prefixo `^[A-Z]{2,3}`, ordenado total desc).
3. `Altitude (FL/100ft): min= max= media=` (de `r.modeC||r.baroH||r.alt` **[BUG]** campos com maiúsculas não existem → normalmente vazio), `Velocidade (TAS/kt): …` (`r.tas||r.ias||r.gspA`), `ROC (ft/min): …` (1 dec).
4. IAS STAR (se `iasResults.totalViol>0`): `Violacoes IAS STAR: total=V em P passagens`; `Waypoints STAR com mais violacoes: WP(vviol/ppass), …` (top 8 por `e[1].viol` **[BUG]** campo é `violations`, logo nunca aparece); `Distribuicao violacoes IAS STAR por voo: 1viol=… | 2viol=… | 3viol= | 4viol= | 5+viol=`; `Top voos com mais violacoes STAR: CSN(nx), …` (5); `Top companhias com violacoes IAS STAR: PRE(nviol), …` (8). Se `iasResults` null: `Violacoes IAS STAR: analise nao efectuada (usa aba Velocidades STAR)`.
5. IAS APP (se `iasAppResults.records`): `=== VIOLAÇÕES IAS APP (Velocidades Aproximação) ===`; `Voos com violacoes: N de A chegadas analisadas`; `Total pontos violados: V | Desvio maximo: D kt`; `Violacoes por waypoint APP (ordenado por numero de voos):` linhas `  WP: v voos | p pontos violados | max=Xkt | mediaExcesso=Ykt` (conta qualquer `|deviation|>0`, inclui THR); `Top companhias: PRE(vvoos/ppts/maxXkt), …` (10); `Por pista: RWY02=n | RWY20=m`; `Distribuicao por voo: 1pt= | 2pt= | 3pt= | 4pt= | 5+pt=`. Senão `Violacoes IAS APP: analise nao efectuada (usa aba Velocidades APP para analisar)`.
6. `=== HOLDINGS DETECTADOS ===` Total; `Duração: min=Xs | max=Ys | média=Zs`; `Por fix: FIX(nx), …`; `Por companhia: PRE(nx/Mmin), …` (8); `Lista: CSN(data start-end/durs/fix:FIX), …`.
7. `=== GO-AROUNDS DETECTADOS ===` Total; `Por companhia`; `Lista: CSN(data hora alt=Xft climb=Yft), …`.
8. `=== ROT — TEMPO DE OCUPAÇÃO DE PISTA ===` `Total registos`; `Média geral: Xs | Min: Ys | Max: Zs`; `  RWYxx: n registos | média= | min= | max=`; `Distribuicao: <30s= | 30-44s= | 45-59s= | 60-89s= | 90-119s= | >=120s=`.
9. `=== SEQUÊNCIA / PONTOS ===` `Aeronaves na sequência: N`; `Distância ao anterior: min/max/média NM` (de `antD`); `Altitude no ponto: min/max/média ft`.
10. FAST (se `_fastPairs`): `=== DADOS DE SEPARAÇÃO ENTRE CHEGADAS CONSECUTIVAS (FAST) ===` / `IMPORTANTE: os números abaixo espelham exactamente o que a aba FAST mostra.` / `Limiar configurado na aba FAST: Ts (mostra pares com sep < Ts)` / `Total de pares calculados (todos): N` / `Separação: min= | max= | média=` / `Por pista: RWY02=n | RWY20=m` / `PARES COM sep < Ts (= o que a aba FAST mostra sem filtro A/C intercalar): n` / `  - Com descolagem intercalar (= aba FAST com filtro A/C INTERCALAR activo): n` / `  - Sem descolagem intercalar: n` / `Todos os pares (sem filtro de limiar):` com/sem DEP / `Distribuicao por faixas: <30s= | 30-59s= | 60-89s= | 90-119s= | 120-149s= | 150-179s= | 180-209s= | 210-239s= | 240-269s= | 270-299s= | 300-359s= | >=360s=` / `Detalhe dos pares abaixo de Ts:` até 50 linhas `  i. A → B | RWYxx | HH:MM:SS | sep=Ns | COM/SEM DEP intercalar` + `  ... (k pares adicionais omitidos)`. Senão: `Separacao entre chegadas (FAST): dados da aba Final disponiveis (N chegadas) mas pares nao foram calculados. O utilizador deve ir a aba Analise Op. > FAST.` ou `Separacao entre chegadas (FAST): sem dados. Vai a aba Final e clica Analisar, depois Analise Op. > FAST.`
11. `=== CHEGADAS ANALISADAS (ABA FINAL) ===` `Total chegadas analisadas: N` / `Por pista: RWY02=n | RWY20=m`.
12. `=== TRÁFEGO POR DIA ===` `Dias carregados: N`; por dia `  DD/MM/AAAA: total= | ARR= | DEP= | NVL=` (data formatada só se 8 dígitos; com YYMMDD sai raw); `Top 3 dias com mais trafego: d(n), …`.
13. `=== ABA PONTOS — PASSAGENS NO RAIO DE rNM ===` `Ponto seleccionado: NAME` / `Total passagens: N` / `Por tipo: ARR= | DEP= | NVL=` / `Top operadores: PRE(nx), …` (8) / (se >1 dia) `Por dia: d=n | …` e `Top 3 dias com mais passagens` / `IAS no ponto: min/max/media kt` / `Altitude no ponto: min/max/media ft`.

## E.4 Chat UI (`iaPerguntar`, `_iaAddMsg`, `_iaRenderChart`)
- Selector de modelo na barra (`iaModelSel`), badge estado `"<provider> · <model>"` ou `"Sem chave — configura nas Preferências"`, botões HTML/XLS/DOC, input + ENVIAR (Enter envia).
- Fluxo: valida pergunta e dados; adiciona bolha "◈ TU"; bolha IA `"⏳ A analisar..."` (não gravada); `fetch`; `JSON.parse(raw.replace(/```json|```/g,'').trim())`; mostra `parsed.texto` (ou `'(sem resposta)'`); grava `{role:'ai',text,grafico,graficoImg,graficoSvg}` em `_iaHistory`; se `grafico.dados` renderiza SVG (bar/line/pie/doughnut; aliases `_iaTipoMap`: histograma/barras/colunas→bar, linha(s)→line, circular/pizza→pie, rosca/anel→doughnut; 10 cores; W460×H200); erro → `"⚠ Erro: <msg>"` com bolha vermelha.
- `_iaHistory` é só local (export); não é reenviado ao modelo.

## E.5 Exportação da conversa — `iaExportar(fmt)` (l.10865)
- `html`: documento `"⚙ Análise IA — Flight Track Viewer"`, meta `"Exportado em: <stamp> · Fornecedor: <nome>"`; por mensagem: `▶ Pergunta` (caixa azul) / `◈ <provider>` (caixa verde, `- ` → `•`), gráfico: `<img>` se `graficoImg` + tabela `Item | Valor`; ficheiro `IA_analise_<stamp>.html`.
- `excel`: HTML-Excel, folha "Análise IA", tabela `Tipo | Conteúdo` (`Pergunta`/`Resposta IA`), gráfico como `"Gráfico: <titulo>"` + linhas `Item | Valor`; `IA_analise_<stamp>.xls`.
- `word`: HTML-Word (`application/msword`), mesmo conteúdo com `.pergunta-box`/`.ia-box` (`textoHtml` = linhas com `- `→`•`), gráfico `<img>` (380pt) ou tabela; `IA_analise_<stamp>.doc`.
(Linhas ~10901–10970 são precisamente estes geradores HTML/Word: `tipo` em 10932 é "Pergunta"/"Resposta IA"; `textoHtml` em 10966 é o texto da resposta com bullets.)

## E.6 Auto-análise e alertas — `_autoAnalyseAndAlert()` (l.7402) / `_computeAlerts()` (l.7458)
Disparado após cada `applyFilter()` (l.2251), com 400 ms de atraso:
0. `buildFinRwyOptions()`; força `finRwy='BOTH'`.
1. `runFinalAnalysis()` se `finalResults` vazio.
2. `detectROT()` (uma vez por sessão, `_anaTabLoaded.rot`) + `_computeAlerts()`.
3. LPPT: modo APP_02, selecciona PESEX, `queryPoint()`, `querySequence()`.
4. `runIasCompliance()` se `iasResults` null.
5. IAS APP **não** corre automaticamente (só ao abrir a aba).
6. `detectHoldings()` e `detectGoArounds()` (uma vez cada) com `_computeAlerts()` após cada.

**Alertas** (`_alerts`, painel `#alertsPanel`, cada um `{icon,color,msg,detail}` com botão × e "dispensar todos"):
| Condição | icon/cor | msg | detail |
|---|---|---|---|
| `rotResults` com `rotS>55` (`ROT_THR=55`) | ⏱ #f59e0b | `"<n> ROT[s] acima de 55s"` | 3 primeiros `"CSN (Xs)"` + `…` |
| `goAroundResults.length>0` | 🚨 #f87171 | `"<n> go-around[s]"` | 3 callsigns |
| holdings com `durS>300` | ◎ #a78bfa | `"<n> holding[s] acima de 5 min"` | `"CSN (Mmin)"` ×3 |
| `iasResults.violations.length>0` | ⚡ #fbbf24 | `"<n> violação(ões) IAS STAR em <k> voo(s)"` | '' |
| records APP com ponto `!/^THR/ && |deviation|>tol` | 🛬 #f87171 | `"<n> voo(s) com violações IAS na aproximação"` | 3 callsigns |

---

## F. Análise IAS STAR (resumo, porque alimenta KPIs/IA/alertas) — `runIasCompliance()` (l.4119)
- Limites default `LPPT_STAR_IAS_DEFAULTS` (l.4002): IAFs 280 (ESUTI,INBOM,LAZET,LUVUP,PULPO,VATZI,XAMAX), ESEBI 250; transição UNPOT 250, CASLU 230, NATID 230, RULOX 250, GANSU 250, EXONA 250, LUXUT 250, ODLIX 230; norte MAZUK/ERNIL/RELKU/ZEFFI 220, NEVUD 180, EKLID/ROTBU/LERLI/FADEF 220, COCUN 180; sul 02 YETSI 230, ORTUG/ZACRA/INLIB/MIGTO 220, ULTIT 180; sul 20 ITAVIT 230, DEKKI/ROMEP/EVPAP/FUSSI 220, ARNIT 180; PESEX 180, UPKAT 180. Editáveis (localStorage `ft.iasLimits`, 80–400 kt).
- Controlos: `iasRadius` default 1 NM (0.1–10), `iasTolerance` default 0 kt (0–30).
- Por leg visível `arr`, por waypoint com coordenadas em `allPoints()`: CPA (menor `distNM<=radius`, bounding box ×1.4, amostragem `rowStep=ceil(rows/12000)`, orçamento 180 ms por leg → leg "limitado"); se `ias>0`: `excess=ias−limit`; `excess<=tol` conforme, senão violação `{csn,wp,ias,limit,excess,tod,date,dCpa}`.
- `iasResults={perWp{wp,limit,total,compliant,violations,iasSum,iasMax,iasMin,excessSum,excessMax},violations,radius,tol,flightsTotal,flightsAnalysed,totalPasses,totalComp,totalViol,missing,skippedLegs,generatedAt}`.
- CSV `ias_compliance_lppt_<date>.csv`: resumo + `Waypoint;Limite_kt;Passagens;Conformes;Violacoes;Cumprim_pct;IAS_med;IAS_max;IAS_min;Excesso_med;Excesso_max` + `N;Hora;Data;Voo;Waypoint;IAS_kt;Limite;Excesso;CPA_NM`.

## G. Lista consolidada de [BUG]s de unidade/campo a decidir na reimplementação
1. `rowEpoch` pseudo-epoch (int(YYMMDD)·86400+s) — diferenças entre dias não são reais.
2. CDO: `dur=(Δt)/1000` com Δt em s → level-offs nunca detectados.
3. Holdings: `dur=(Δt)/1000` vs `MIN_DUR=90` → holdings nunca detectados.
4. Go-arounds: `|t−epochTHR|<120000` (s) → qualquer leg com aterragem detectada é excluída; `durSinceMin=/1000`; KPI por hora usa `new Date(epochMin)` sem ×1000.
5. Análise de Dados: opção/ordem `'AD...A'` nunca casa com `'AD…A'` (reticência Unicode).
6. `_iaBuildCtx`: campos `modeC/baroH/alt/gspA` inexistentes → estatísticas Alt/TAS vazias; `e[1].viol` vs `violations` → "Waypoints STAR com mais violacoes" nunca aparece.
7. `_buildFlightAnalysis`: `x.name` inexistente (é `x.point`) → listas de pontos vazias na narrativa.
8. RRMS PDF tabela de detalhe omite a célula Status.
9. `detectROT`: data só formatada se 8 dígitos; `_date` é YYMMDD → data sai em bruto.
10. `runOperAnalysis` nunca é invocado (código morto).
