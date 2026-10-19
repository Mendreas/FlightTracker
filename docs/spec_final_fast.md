# Especificação exacta — Aba "Final" e Análise Op. → FAST / Análise de Dados / Análise Diária

Fonte: `/home/claude/mendreas/flighttracker/dist/index.html` (FlightTracker v3.5). Esta especificação descreve, com fidelidade total ao JavaScript, os algoritmos a reimplementar em Python. Referências de linha são à versão actual do ficheiro.

---

## 0. Conceitos e funções base partilhadas

### 0.1 Linhas radar (rows) e campos usados

Cada ficheiro CSV (separador `;` ou `,`, cabeçalhos convertidos para minúsculas) produz linhas (`rows`) com os campos originais em minúsculas. Linhas sem `latitude`/`lat` são descartadas no parse. São anexados a cada linha:
- `_date` — data interna no formato `AAMMDD` (ex.: `260405`), obtida do nome do ficheiro (`parseFilename`, linha 1336): regex `(\d{6})_(\d{2}-\d{2})` ou `LPXX_AAAA-MM-DD_HH-HH`; se desconhecida fica `'??'` (ou é atribuída pelo utilizador).
- `_block` — bloco horário `HH-HH` (`00-04`, `04-08`, …, `20-24`).
- `_filename`.

Campos lidos pelas análises (`ESSENTIAL_COLS`, linha 1166): `csn, tod, latitude, lat, longitude, lon, modec, baroh, tas, tasa, iar, iara, roc, gspa, modes, modea, trknr`.

Funções auxiliares (citadas literalmente):

```js
function gv(r,...ks){for(const k of ks){if(r[k]!==undefined&&r[k]!=='')return r[k];}return '—';}
function getAlt(r){
  const raw=r.modec!==undefined&&r.modec!==''?r.modec:r.baroh!==undefined&&r.baroh!==''?r.baroh:null;
  if(raw===null)return '—';const v=parseFloat(raw);if(isNaN(v))return '—';
  return Math.round(v<600?v*100:v);          // valores <600 são FL → ×100 ; resultado em ft
}
function _iasFromRow(r){ const v=gv(r,'iar','iara','ias'); if(v==='—')return null;
  const n=parseFloat(String(v).replace(',','.')); return isNaN(n)?null:n; }
function _altFromRow(r){ const a=getAlt(r); if(a==='—')return NaN; return typeof a==='number'?a:parseFloat(a); }
```

**Tempo (pseudo-epoch)** — `rowEpoch` (linha 3279):
```js
function todSec(tod){ const p=String(tod||'').split(':'); if(p.length<3)return NaN;
  const h=+p[0],m=+p[1],sec=parseFloat(p[2]); return h*3600+m*60+sec; }
function rowEpoch(r){
  const t=todSec(r.tod);if(isNaN(t))return NaN;
  const dk=r._date&&r._date!=='??'?(parseInt(String(r._date).replace(/\D/g,''),10)||0):0;
  return dk*86400+t;      // NÃO é epoch Unix: é int(AAMMDD)*86400 + segundos do dia
}
```
Consequência: diferenças de tempo só são correctas dentro do mesmo dia (`_date` igual). `tod` tem formato `HH:MM:SS(.fff)`. `epochToHHMMSS(ep)` = `round(((ep % 86400)+86400)%86400)` formatado `HH:MM:SS`. `fmtTime(sec)` idem, com `floor`.

**Data formatada** — `fmtDate('260405')` → `'05/04/2026'` (`DD/MM/AAAA`); `'??'` → `'Data desconhecida'`.

### 0.2 Distâncias e geometria (NM)

```js
function distNM(lat1,lon1,lat2,lon2){            // haversine, R = 3440.065 NM
  const R=3440.065,dLat=(lat2-lat1)*Math.PI/180,dLon=(lon2-lon1)*Math.PI/180;
  const a=Math.sin(dLat/2)**2+Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLon/2)**2;
  return R*2*Math.asin(Math.sqrt(a));
}
function bearingDeg(lat1,lon1,lat2,lon2){        // rumo inicial verdadeiro 0..360
  const p1=_rad(lat1),p2=_rad(lat2),dl=_rad(lon2-lon1);
  const y=Math.sin(dl)*Math.cos(p2);
  const x=Math.cos(p1)*Math.sin(p2)-Math.sin(p1)*Math.cos(p2)*Math.cos(dl);
  return (_deg(Math.atan2(y,x))+360)%360;
}
// along = distância ao longo do eixo de aproximação (positivo = aeronave ainda antes da THR, a chegar)
// cross = desvio lateral assinado ao eixo
function approachCoords(lat,lon,thrLat,thrLon,landBrg){
  const d=distNM(thrLat,thrLon,lat,lon);
  if(d===0)return{along:0,cross:0};
  const br=bearingDeg(thrLat,thrLon,lat,lon);
  const app=(landBrg+180)%360;                   // direcção THR → exterior (recíproco do rumo de aterragem)
  let delta=br-app; while(delta>180)delta-=360; while(delta<=-180)delta+=360;
  const dr=_rad(delta);
  return{along:d*Math.cos(dr),cross:d*Math.sin(dr)};
}
```
`cross>0` significa que a aeronave está à direita quando se olha da THR para fora (= à esquerda do piloto que vem a aterrar). A tabela mostra o valor assinado tal como calculado.

### 0.3 Configuração de aeroportos / pistas (linha 3420)

```js
const AIRPORT_CONFIGS={
  LPPT:{name:'Lisboa (LPPT)',center:[38.7813,-9.1359],elev:374,rwys:{
    '02':{thr:{lat:38.766428,lon:-9.143903},brg:32.0,elev:357,name:'RWY 02'},
    '20':{thr:{lat:38.792331,lon:-9.130047},brg:212.0,elev:303,name:'RWY 20'},
  }},
  LPPR:{name:'Porto (LPPR)',center:[41.2481,-8.6814],elev:227,rwys:{
    '17':{thr:{lat:41.260681,lon:-8.684561},brg:171.0,elev:151,name:'RWY 17'},
    '35':{thr:{lat:41.233886,lon:-8.677536},brg:351.0,elev:227,name:'RWY 35'},
  }},
  LPFR:{name:'Faro (LPFR)',center:[37.0153,-7.9723],elev:24,rwys:{
    '10':{thr:{lat:37.017222,lon:-7.985614},brg:101.0,elev:24,name:'RWY 10'},
    '28':{thr:{lat:37.013450,lon:-7.959042},brg:281.0,elev:18,name:'RWY 28'},
  }},
  LPMA:{name:'Funchal (LPMA)',center:[32.6978,-16.7745],elev:191,rwys:{
    '05':{thr:{lat:32.689932,lon:-16.783751},brg:47.0,elev:146,name:'RWY 05'},
    '23':{thr:{lat:32.705841,lon:-16.765150},brg:227.0,elev:191,name:'RWY 23'},
  }},
};
```
`brg` = rumo verdadeiro de aterragem (graus), `elev` = elevação da THR em ft. Aeroporto activo por defeito: `LPPT`. Os pontos THR02/THR20 da base de pontos (linhas 2796-2797) têm exactamente as mesmas coordenadas.

### 0.4 Voos, "legs" e classificação ARR/DEP

- `flights[csn]` = `{rows, color, visible}`; as `rows` do callsign (de todos os ficheiros filtrados por dia/bloco no painel esquerdo) são **ordenadas apenas pela string `tod`** (`localeCompare`), ou seja, se o mesmo callsign existir em vários dias, as linhas ficam intercaladas por hora e não por data.
- **Leg** = par único (callsign, `_date`) — `getFlightLegs()` (linha 1448): agrupa as rows de cada callsign por `_date`; cada leg tem `csn, date, rows, color, _flight, firstEpoch`; lista ordenada por `date` e depois `firstEpoch`.
- `isLegVisible(leg)` = `leg._flight.visible && (flightTypeFilter==='all' || classifyFlight(leg.rows)===flightTypeFilter)`.
- Classificação (linha 1422):
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
- `_firstEpoch(rows)` = `rowEpoch` da primeira row com epoch "truthy" (≠0, ≠NaN), senão `0`. Como as rows estão ordenadas por `tod` (string), é a row com menor hora do dia, independentemente da data.
- Companhia a partir do callsign (linha 7766):
```js
function companyFromCallsign(csn){const s=String(csn||'').trim().toUpperCase();if(!s)return 'SEM CSN';
  const m=s.match(/^([A-Z]{2,4})(?=\d)/);if(m)return m[1];
  const m2=s.match(/^([A-Z]{2,4})/);return m2?m2[1]:s.slice(0,4);}
```

### 0.5 Formatação

- `fmtN(v,d)`: `null`/não finito → `'—'`; `d===0` → inteiro arredondado; senão `toFixed(d)` com vírgula decimal.
- `fmtS(v)`: `'—'` ou `Math.round(v)`.

---

## 1. Aba "Final" — detecção de aterragens e análise da final (FAF → THR)

### 1.1 Inputs / controlos (painel `panel-final`, linhas 595-627)

| id | Label | Tipo / Opções | Default | Limites |
|---|---|---|---|---|
| `finRwy` | Pista: | select `BOTH` ("Ambas (02+20)") ou uma pista (`02`, `20`, …) — opções geradas de `getActiveRwy()` | `BOTH` | — |
| `finFaf` | FAF: … NM | number | `7` | min 3, max 15, step 0.5 |
| `finCorr` | Corredor ± … NM | number | `2` | min 0.5, max 5, step 0.5 |
| `finAltThr` | Alt THR ≤ … ft (tooltip "Máxima altitude ao cruzar THR para considerar aterragem") | number | `1000` | min 500, max 3000, step 100 |
| botão | ▶ Analisar → `runFinalAnalysis()` | | | |
| botão | ↓ CSV → `exportFinalCsv()` | | | |
| botão `finOvBtn` | 🗺 Mostrar/Ocultar corredor (overlay no mapa) | | | |
| `finResultCount` | texto "N aterragem(ns) detectada(s)" | | | |
| `finSummary` | barra de KPIs | | | |
| `finResultTable` | tabela de resultados (ordenável por clique no cabeçalho) | | | |

Parse dos valores: `parseFloat(x)||default` — portanto um valor 0 ou inválido cai no default (7 / 2 / 1000).

Notas de execução automática:
- Após cada `applyFilter()` (painel esquerdo), `finalResults` é esvaziado e `_autoAnalyseAndAlert()` (linha 7402) força `finRwy='BOTH'` e corre `runFinalAnalysis()` automaticamente se `finalResults` estiver vazio.
- A aba Análise Op. (`ensureAnaTabData`) também corre `runFinalAnalysis()` se `finalResults` estiver vazio.
- `switchAirport()` limpa `finalResults`.

### 1.2 Algoritmo — `runFinalAnalysis()` (linha 3662)

1. Se não há voos → alerta "Sem dados. Aplica um filtro primeiro." e sai.
2. Ler `rwySel`, `fafNM`, `corrNM`, `altThrMax`. `rwys = rwySel==='BOTH' ? todas as pistas do aeroporto activo : [rwySel]`.
3. `finalResults=[]`.
4. Para **cada pista** `rid` em `rwys`, para **cada leg** em `getFlightLegs()` com `isLegVisible(leg)`: `ap = analyzeFlightApproach(leg.csn, leg, rwy, rid, fafNM, corrNM, altThrMax)`; se `ap` não for `null` → `finalResults.push(ap)`.
   - Nota: **não** há filtro por `classifyFlight==='arr'` aqui (apenas o filtro ARR/DEP/NVL da sidebar, se activo, via `isLegVisible`). O mesmo leg pode, em teoria, gerar um registo por pista se satisfizer ambas (não acontece na prática porque as THR são opostas, mas não há dedup).
5. Ordenar `finalResults` por `epochTHR` ascendente.
6. Atribuir `idx` (1..N) e **separação temporal face à aterragem anterior na mesma pista e mesmo dia**:
```js
const prevByRwyDay={};
const _dayKey=r=>{ if(r&&r._dateRaw&&r._dateRaw!=='??')return String(r._dateRaw);
  const d=new Date((r.epochTHR||0)*1000); return `${UTCFullYear}-${MM}-${DD}`; };
finalResults.forEach((r,i)=>{ r.idx=i+1;
  const prev=prevByRwyDay[`${r.rwy}|${_dayKey(r)}`];
  r.sepTimeS=prev!=null?r.epochTHR-prev:null;
  prevByRwyDay[`${r.rwy}|${_dayKey(r)}`]=r.epochTHR; });
```
   `sepTimeS` (s) é `null` para a primeira aterragem de cada (pista, dia). Não há limite máximo aqui (contrário aos pares FAST, ver §2).
7. Se o overlay estiver activo, redesenha-o; `renderFinalResults()`.

### 1.3 Algoritmo — `analyzeFlightApproach(csn, flight, rwy, rwyId, fafNM, corrNM, altThrMax)` (linha 3544)

Devolve `null` (não é aterragem nesta pista) ou um registo.

**Passo A — Sanidade de caixa (~36 NM):** existe pelo menos uma row com `|lat−thr.lat|<0.6` e `|lon−thr.lon|<0.6` (graus). Se não → `null`.

**Passo B — Construir pontos:** para cada row com `lat`,`lon` numéricos e ≠0, `t=rowEpoch(r)` válido e `alt=_altFromRow(r)` válido:
`{t, lat, lon, alt, along, cross, ias:_iasFromRow(r), row}` com `approachCoords(lat,lon,thr.lat,thr.lon,rwy.brg)`. Ordenar por `t`. Se `< 3` pontos → `null`.

**Passo C — Cruzamento da THR:**
```js
const altThrAbsMax=rwy.elev+altThrMax;          // ft MSL
let thrIdx=-1;
for(let i=1;i<pts.length;i++){
  const a=pts[i-1],b=pts[i];
  if(a.along>0&&b.along<=0.3){
    const loAlt=Math.min(a.alt,b.alt);
    if(loAlt<=altThrAbsMax&&Math.abs(a.cross)<corrNM&&Math.abs(b.cross)<corrNM){thrIdx=i;break;}
  }
}
if(thrIdx<0)return null;
```
- Primeiro par consecutivo (cronológico) em que `along` passa de `>0` para `≤0.3 NM`, com a menor das duas altitudes ≤ `elev_THR + altThrMax` e ambos os pontos dentro do corredor lateral (`|cross| < corrNM`).
- Não existe "raio" circular à THR: o critério é projecção no eixo (0.3 NM de tolerância) + corredor lateral + altitude.
- Interpolação linear ao ponto `along=0`:
```js
const pA=pts[thrIdx-1],pB=pts[thrIdx];
const kT=pA.along/(pA.along-pB.along);           // pode ser >1 (extrapolação) se pB.along>0
const tTHR=pA.t+kT*(pB.t-pA.t);
const altTHR=pA.alt+kT*(pB.alt-pA.alt);
const iasTHR=(pA.ias!=null&&pB.ias!=null)?pA.ias+kT*(pB.ias-pA.ias):null;
const latTHR=pA.lat+kT*(pB.lat-pA.lat),lonTHR=pA.lon+kT*(pB.lon-pA.lon);
```

**Passo D — Cruzamento do FAF (distância `fafNM` ao longo do eixo):** pesquisa **para trás** a partir de `thrIdx-1`:
```js
let fafIdx=-1;
for(let i=thrIdx-1;i>=1;i--){ const a=pts[i-1],b=pts[i];
  if(a.along>fafNM&&b.along<=fafNM){fafIdx=i;break;} }
if(fafIdx<0)return null;                        // sem cruzamento do FAF → NÃO é contado como aterragem
const fA=pts[fafIdx-1],fB=pts[fafIdx];
const kF=(fA.along-fafNM)/(fA.along-fB.along);
const tFAF=fA.t+kF*(fB.t-fA.t);  const altFAF=fA.alt+kF*(fB.alt-fA.alt);
const crossFAF=fA.cross+kF*(fB.cross-fA.cross);
const iasFAF=(fA.ias!=null&&fB.ias!=null)?fA.ias+kF*(fB.ias-fA.ias):null;
const latFAF=…, lonFAF=…  (mesma interpolação)
```
- É o **último** cruzamento de `fafNM` antes da THR. Não há verificação de corredor no FAF. Um voo cujo track só começa dentro do FAF não é detectado.
- O "FAF" é um ponto virtual a `fafNM` NM da THR no prolongamento do eixo, **não** o fix publicado (PESEX/UPKAT a 11.3 NM). Default 7 NM.

**Passo E — IAS a 4 NM:** entre `fafIdx` e `thrIdx`, primeiro par `(a,b)=(pts[i-1],pts[i])` com `a.along>4 && b.along<=4`; se ambos têm IAS: `ias4 = a.ias + k*(b.ias-a.ias)` com `k=(a.along-4)/(a.along-b.along)`; senão `null`.

**Passo F — Track miles FAF→THR (NM):**
```
trackNM = distNM(FAF_interp, pts[fafIdx]) + Σ_{i=fafIdx}^{thrIdx-2} distNM(pts[i],pts[i+1]) + distNM(pts[thrIdx-1], THR_interp)
```

**Passo G — Estabilizada (proxy no FAF):**
```js
const aglFAF=altFAF-rwy.elev;
const stab=(aglFAF>=800&&aglFAF<=5000) && (iasFAF==null||(iasFAF>=120&&iasFAF<=230)) && (Math.abs(crossFAF)<=1.0);
```

**Passo H — CDO (patamares abaixo de FL100):** (calculado, não mostrado na tabela da aba Final; usado em KPIs)
```js
let cdoLevelOffs=0,cdoLevelSecs=0; let _startIdx=-1;
for(let i=0;i<thrIdx;i++){if(pts[i].alt<=10000){_startIdx=i;break;}}
if(_startIdx>=0){ let i=_startIdx;
  while(i<thrIdx-1){ const a=pts[i]; let j=i+1; let maxAlt=a.alt,minAlt=a.alt;
    while(j<=thrIdx&&pts[j].alt<=10000){ if(pts[j].alt>maxAlt)maxAlt=pts[j].alt; if(pts[j].alt<minAlt)minAlt=pts[j].alt;
      if((maxAlt-minAlt)>150)break; j++; }
    const dur=(pts[Math.min(j,thrIdx)].t-a.t)/1000;      // BUG: t está em segundos; /1000 torna dur quase sempre <30
    if(j-i>=2&&dur>=30&&(maxAlt-minAlt)<=150&&a.alt>=rwy.elev+800){cdoLevelOffs++;cdoLevelSecs+=dur;}
    i=Math.max(j,i+1); } }
const cdo=cdoLevelOffs===0;
```
Na prática (por causa do `/1000`) `cdo` é quase sempre `true`. Reproduzir tal qual se se quiser fidelidade; corrigir removendo `/1000` se se quiser o comportamento pretendido.

**Registo devolvido:**
```
{ csn, rwy:rwyId, epochTHR:tTHR, epochFAF:tFAF, tFAFstr:HH:MM:SS, tTHRstr:HH:MM:SS,
  date: fmtDate(primeira row._date) ou '' se '??', _dateRaw: primeira row._date,
  altFAF, altTHR, iasFAF, ias4, iasTHR, crossFAF, trackNM, durS: tTHR-tFAF,
  stab, cdo, cdoLevelOffs, cdoLevelSecs, color, latFAF, lonFAF, latTHR, lonTHR }
```
(`idx` e `sepTimeS` são adicionados depois em `runFinalAnalysis`.)

### 1.4 Outputs — `renderFinalResults()` (linha 3708)

`finResultCount`: `"${N} aterragem(ns) detectada(s)"`. Se N=0: mensagem "Nenhuma aterragem detectada nos parâmetros actuais".

**Barra de resumo (`finSummary`)** — médias simples, mínimo:
- `N aterragens`
- `Estabilizadas: stabCount (pct%)` — `pct = (stabCount/N*100).toFixed(0)`; cor verde se todas, laranja caso contrário
- `IAS@FAF méd: mean(iasFAF não nulos).toFixed(0) kt`
- `Tempo FAF→THR méd: mean(durS finitos).toFixed(0) s`
- `Sep. temporal méd: mean(sepTimeS não nulos).toFixed(0) s`
- `Sep. temporal mín: min(sepTimeS).toFixed(0) s`

**Tabela `finResultTable`** (ordem = `finalResults` ordenado por `epochTHR`; cabeçalhos clicáveis para ordenar):

| # | Coluna | Valor | Formato |
|---|---|---|---|
| 1 | `#` | `idx` | inteiro |
| 2 | RWY | `RWY ${rwy}` (badge azul 02 / roxo 20) | |
| 3 | Voo | `csn` (badge com cor do voo; clique abre modal do voo) | |
| 4 | Data | `date` ou `—` | DD/MM/AAAA |
| 5 | Hora FAF | `tFAFstr` | HH:MM:SS |
| 6 | Hora THR | `tTHRstr` | HH:MM:SS |
| 7 | FAF→THR (s) | `fmtS(durS)` | inteiro |
| 8 | Dist (NM) | `fmtN(trackNM,2)` | 2 dec, vírgula |
| 9 | ΔT ant (s) | `sepTimeS==null?'—':fmtS(sepTimeS)` | inteiro |
| 10 | Alt FAF (ft) | `fmtN(altFAF,0)` (ft MSL) | |
| 11 | IAS FAF | `fmtN(iasFAF,0)` | kt |
| 12 | IAS@4NM | `fmtN(ias4,0)` | kt |
| 13 | IAS THR | `fmtN(iasTHR,0)` | kt |
| 14 | Desvio eixo (NM) | `fmtN(crossFAF,2)` (tooltip "negativo=esquerda") | |
| 15 | Estab. | ✓ (verde) / ✗ (vermelho) | |

**CSV (`exportFinalCsv`)** — separador `;`, BOM UTF-8, CRLF, nome `final_lppt_AAAA-MM-DD.csv`:
```
Seq;RWY;Voo;Data;Hora_FAF;Hora_THR;Dur_FAF_THR_s;Dist_FAF_THR_NM;Sep_temporal_anterior_s;Alt_FAF_ft;IAS_FAF_kt;IAS_4NM_kt;IAS_THR_kt;Desvio_eixo_NM;Estabilizada
```
Valores: `idx; parseInt(rwy); csn; date; tFAFstr; tTHRstr; fmtS(durS); fmtN(trackNM,2); sepTimeS==null?'':fmtS; fmtN(altFAF,0); fmtN(iasFAF,0); fmtN(ias4,0); fmtN(iasTHR,0); fmtN(crossFAF,2); 'Sim'/'Nao'`. Campos com `;` são envolvidos em aspas.

**Overlay no mapa (`drawFinalOverlay`)** — por pista: polígono do corredor (largura `±corrNM`, desde a THR até `fafNM+5` NM ao longo do recíproco do rumo), linha tracejada THR→(fafNM+5), marcador THR e marcador FAF a `fafNM` NM (projecção geodésica `projectPoint`).

**KPIs derivados noutras abas** (de `finalResults`): aba KPIs mostra Aterragens (e taxa `N/spanH` aterr./h), por pista 02/20, Estabilizadas, IAS@FAF méd., Tempo FAF→THR méd., Sep. temporal méd. e mín./máx. (`_landingRateBlock`: taxa rolling 60 min com passo 5 min, capacidade referência LPPT = 38 mov/h; histograma de `sepTimeS` com bins `[0,60,90,120,150,180,240,300,600,∞)`). Na aba Análise de Dados o cartão `mLand` "passagens THR detetadas" = `finalResults.length`.

### 1.5 "ESCALA DA FINAL — selecciona pontos de análise (12 NM → THR)"

Esta escala **não** pertence à aba Final: é a sub-aba "Violações por distância" da aba **Conformidade IAS (APP)** (`panel-iasapp`, linhas 748-774, código 4801-5253). Documenta-se por ser pedida.

**Controlos:**
| id | Label | Default |
|---|---|---|
| `appDistRwy02` / `appDistRwy20` | PISTA: RWY 02 / RWY 20 (exclusivo) | `02` (`_appDistRwy`) |
| `appDistBuffer` | BUFFER ± … kt | `4` (min 0, max 20, step 1; `parseInt(...||'4')`) |
| `appDistBtns` | botões da escala: 12.0, 11.5, …, 0.5, 0.0 NM (25 botões, passo 0.5) — todos seleccionados por defeito (`_appDistSelNm`) | todos |
| botões de segmento | RWY02: `PESEX→NETVO` (11.5–8.0), `NETVO→OKNIB` (7.5–4.0), `OKNIB→THR` (3.5–0.0); RWY20: `UPKAT→TOPVI`, `TOPVI→ROKOB`, `ROKOB→THR` — alternam em bloco | |
| ▶ Analisar → `computeAppDistViol()`; ↓ CSV → `exportAppDistCsv()` | | |
| no gráfico: `appDistChartComp` (companhia), `appDistChartBuf` (0,2,4,6,8,10,12 kt; default 4), `appDistTopFilter` (Todos / Top 5 ▲ acima / Top 5 ▼ abaixo) | | |

**Waypoints nomeados na escala** (linha 4807) — distâncias AIP LPPT AD 2.24.12; `scalePt` é o botão (0.5 NM) que o waypoint ocupa:
```
'02': PESEX nm 11.3 limit 180 scalePt 11.5 | NETVO 8.2/160/8.0 | OKNIB 4.2/160/4.0 | 'THR 02' 0.0/160/0.0
'20': UPKAT 11.3/180/11.5 | TOPVI 8.2/160/8.0 | ROKOB 3.96/160/4.0 | 'THR 20' 0.0/160/0.0
```
Perfil de limite para pontos sem nome (`getAppDistLimitAt(d)`): `d>=8.2 → 180`; `8.2>d>=4.0 → 160`; `d<4 → round(135 + (d/4)*(160-135))` (135 kt na THR).

**Algoritmo `_computeAppDistViol()`:**
1. `selNm` = pontos seleccionados, ordenados decrescente.
2. Para cada leg com `_flight.visible` (ignora filtro ARR/DEP da sidebar) e `classifyFlight(rows)==='arr'`, para a pista seleccionada:
   - `pts` = rows com lat/lon válidos e `rowEpoch>0`, projectadas (`approachCoords`), **filtradas** a `0 ≤ along ≤ 12` e `|cross| < 1.5` NM, ordenadas por `along` decrescente. Requer `≥3` pontos e o ponto mais próximo com `along ≤ 1.5` NM.
   - Para cada `nm` seleccionado: `analysisNm` = distância real do waypoint se o botão é nomeado (ex.: 11.3 para 11.5), senão `nm`; `lim` = limite do waypoint ou `getAppDistLimitAt(nm)`. Procurar o primeiro par `(a,b)` com `a.along>=analysisNm && b.along<=analysisNm`; `k=(a.along-analysisNm)/(a.along-b.along)` (0 se `range≤0.001`); `iasInterp = round(iasA + k*(iasB-iasA))` se ambos `>0`, senão o que existir (`>0`), senão `null`.
   - `dev = ias - lim`; `viol = |dev| > buffer` (acima **ou abaixo**).
   - O voo só entra nos resultados se tiver ≥1 violação; `avgDev = round(mean(dev não nulos))`.
   - Registo: `{csn, date, _dateRaw, tod (HH:MM:SS da 1.ª row), rwy, distData{nm→{ias,lim,dev,viol,analysisNm}}, avgDev, comp (regex ^[A-Z]{2,3})}`.
3. Tabela: colunas `CALLSIGN, DATA, HORA, PISTA, <um por ponto: nome do waypoint "(x.xx NM)" ou "k.k NM">, MÉD DEV.`; ordenação default por `|avgDev|` desc; célula vermelha se `dev>0` e viol, azul se `dev<0` e viol.
4. Gráfico SVG "Perfil de velocidade ao longo da final": X = pontos seleccionados (equidistantes), Y = kt; linha tracejada vermelha = perfil de limite; até 100 polilinhas de voos (vermelha se o ponto central tem `dev>0`, azul caso contrário, cinza se sem violação).
5. CSV `APP_violacoes_distancia.csv`: `Callsign;Data;Hora;Pista;<LABEL_k.kNM ou k.kNM>…;Med_Desvio_kt` (só a pista seleccionada).

---

## 2. Análise Op. → "Separação entre chegadas" (FAST)

### 2.1 Inputs / controlos (linhas 792-833)

| id | Label | Default / opções |
|---|---|---|
| `fastThreshold` | Separação THR: … s | `160` (min 30, max 300, step 10; `parseInt(...)||160`); `oninput` re-renderiza |
| `fastModeAll` | Todos | modo `'all'` (estado inicial do JS `_fastMode='all'`, embora o botão "< Abaixo" apareça pré-realçado no HTML) |
| `fastModeLt` | < Abaixo | `'lt'` — pares com `sep < thr` |
| `fastModeRange` | ↔ Entre limite e 240s | `'range'` — `thr ≤ sep ≤ 240` (240 fixo) |
| `fastInterBtn` | A/C intercalar (toggle) | `_fastIntercalOnly=false` — só pares com ≥1 DEP entre as duas aterragens |
| `fastRwy02Btn` / `fastRwy20Btn` | RWY02 / RWY20 (toggle; clicar na activa volta a `'all'`) | `_fastRwyFilter='all'` |
| `fastCount` | `"N par(es)" + " · com DEP intercalar" + " · RWY xx"` | |
| `fastTable` | lista (esquerda) | |
| `fastDetail` | detalhe do par seleccionado (direita) | |

Ao abrir a sub-aba: `ensureAnaTabData('fast')` → se `finalResults` vazio corre `runFinalAnalysis()`; depois `renderFastResults()`.

### 2.2 Formação dos pares — `buildFastPairs()` (linha 5804)

```js
_fastPairs=[];
if(!finalResults||!finalResults.length)return;
const byKey={};
for(const r of finalResults){ const k=r.rwy+'|'+(r._dateRaw||r.date||''); (byKey[k]||=[]).push(r); }
for(const arr of Object.values(byKey)){
  arr.sort((a,b)=>(a.epochTHR||0)-(b.epochTHR||0));
  for(let i=1;i<arr.length;i++){
    const lead=arr[i-1],trail=arr[i];
    const sep=(trail.epochTHR||0)-(lead.epochTHR||0);
    if(sep<=0||sep>600)continue;          // ignora negativos/zero e >10 min
    _fastPairs.push({lead,trail,sep});
  }
}
_fastPairs.sort((a,b)=>(a.lead.epochTHR||0)-(b.lead.epochTHR||0));
```
- Pares = aterragens **consecutivas na mesma pista e no mesmo dia** (`_dateRaw`), ordenadas pela hora de cruzamento da THR. `sep` em segundos (float; `epochTHR` interpolado).
- Pares com `sep > 600 s` são descartados (diferente de `sepTimeS` da aba Final, que não tem limite).
- `lead` = precedente/líder, `trail` = seguidor.

### 2.3 Filtragem e enriquecimento — `renderFastResults()` (linha 5825)

1. `buildFastPairs()`; `thr = parseInt(fastThreshold)||160`.
2. Modo: `all` → todos; `lt` → `sep<thr`; `range` → `sep>=thr && sep<=240`.
3. **DEP epochs** (lista global, independente de pista/dia/visibilidade): para cada `flights[csn]` com `classifyFlight(rows)==='dep'`, `t=_firstEpoch(rows)`; se `t>0` finito, adicionar `{t, csn: rows[0].csn}`. Ordenar por `t`.
   - A "hora de descolagem" é a hora da **primeira row radar** do callsign (não há detecção de rotação nem de pista). Como `rowEpoch` inclui a data, um DEP só pode cair entre duas aterragens do mesmo dia.
   - Edge case: se um callsign DEP operar em vários dias no filtro, `flights[csn].rows` mistura dias ordenados por `tod`, e `_firstEpoch` devolve apenas **um** epoch (o da menor hora do dia) → só um DEP é contabilizado para esse callsign.
4. Se `_fastIntercalOnly`: manter só pares com `_pairHasIntercalDep`: existe `d` com `lead.epochTHR < d < trail.epochTHR` (estritos).
5. Se `_fastRwyFilter!=='all'`: `String(lead.rwy)===_fastRwyFilter`.
6. Enriquecimento de cada par:
```js
const t0=p.lead.epochTHR,t1=p.trail.epochTHR;
const depsIn=_depEpochs.filter(d=>d.t>t0&&d.t<t1);
const depCnt=depsIn.length;
const seq=depCnt===0?'AA':depCnt===1?'ADA':depCnt===2?'ADDA':'AD…A';   // 3+ DEP → 'AD…A' (reticências U+2026)
const firstDep=depsIn[0]||null;
let bNmAtDep='—';
if(firstDep&&p.trail.epochTHR&&p.trail.iasTHR){
  const secs=p.trail.epochTHR-firstDep.t;
  if(secs>0){const nmPerSec=(p.trail.iasTHR||140)/3600;bNmAtDep=(secs*nmPerSec).toFixed(1);}
}
```
   - **"Seg. no DEP" / "Posição do seguidor no DEP"** = distância estimada do seguidor à THR no instante do primeiro DEP = `(t_THR_seguidor − t_DEP) × IAS_THR_seguidor / 3600` NM (assume velocidade constante igual à IAS interpolada na THR; se `iasTHR` for `null`/0 o valor é `—`).
   - **IAS Líder / IAS Seg.** = `iasTHR` do líder / seguidor (IAS interpolada no cruzamento da THR, §1.3 C), arredondada.
7. Se `_fastPairs` vazio: "Sem dados — corre Final primeiro". Se a filtragem der 0: "Nenhum par encontrado com este filtro", `fastCount = "0 pares (de N total)"`.

**Tabela `fastTable`** (ordem = `lead.epochTHR` asc; clique na linha → `showFastDetail(i)`):

| Coluna | Valor |
|---|---|
| # | i+1 |
| Pista | `RWY ${lead.rwy}` |
| Data | `lead.date` (DD/MM/AAAA) |
| Líder | `lead.csn` (quadrado da cor) |
| Hora (THR) | `lead.tTHRstr` |
| IAS Líder | `round(lead.iasTHR)+'kt'` ou `—` |
| Seguidor | `trail.csn` |
| IAS Seg. | `round(trail.iasTHR)+'kt'` ou `—` |
| Sep. (s) | `round(sep)+'s'` — cor: `<120` vermelho, `<thr` laranja, senão verde |
| Seq. | `AA` (cinza) / `ADA` (laranja) / `ADDA`,`AD…A` (vermelho) |
| DEP | callsign do **primeiro** DEP intercalar (badge laranja) ou `—` |
| Seg. no DEP | `bNmAtDep + ' NM'` ou `—` |

`window._fastFilteredPairs = enrichedPairs` (usado por exportações).

### 2.4 Detalhe do par — `showFastDetail(idx)` (linha 5909)

- Recalcula a lista de DEP entre `t0` e `t1` (mesmo critério) → cartões "DEP csn HH:MM:SS Descolou entre as duas aterragens".
- **Diagrama SVG da final (360×500 px)**: eixo vertical de 0 (THR, em baixo, `thrY=svgH-28`) a 12 NM (topo, `topY=18`); `ptY(nm)=thrY-nm*scale`, `scale=(thrY-topY)/12`.
  - Waypoints desenhados (rótulos à esquerda, distância à direita) — **valores fixos no código, distintos dos da escala APP**: RWY02: `FAF/IF 11.3`, `OKNIE 7.0`, `NETVO 4.5`; RWY20: `UPKAT 11.0`, `TOPVI 8.0`, `ROKOB 5.0`.
  - Líder: círculo na THR (`y=thrY`), texto `csn` e `THR hh:mm:ss`.
  - Seguidor: círculo a `trailDistNM = sep × 140/3600` NM (**velocidade fixa 140 kt GS**, i.e. "distância aproximada do seguidor quando o líder cruzou a THR"), texto `round(sep)s • trailDistNM.toFixed(1)NM`; seta entre os dois.
  - DEPs: rectângulos laranja `DEP csn` colocados a `1.5 + i*0.5` NM (posição puramente ilustrativa).
- Cartões de texto: Líder (`Hora THR`, `IAS`, `Alt THR` = `round(altTHR) ft`), DEPs, Seguidor (`${round(sep)}s atrás da soleira`, mesmas três métricas, "Distância aprox. quando líder cruzou THR: `(sep*140/3600).toFixed(1)` NM"), aviso "N descolagem(ns) entre as duas aterragens". Cores por `sep`: `<120` vermelho, `<160` laranja (**160 fixo** aqui, não `thr`), senão verde.

### 2.5 Exportações da FAST

**CSV da aba (`exportAnaActiveCsv`, aba `fast`)** — `analise_fast_lppt_AAAA-MM-DD.csv`, usa `window._fastFilteredPairs` (pares visíveis após filtros):
```
N;Pista;Data;Lider;Hora_lider;IAS_lider_kt;Seguidor;Hora_seguidor;IAS_seguidor_kt;Separacao_s
i+1; parseInt(lead.rwy); lead.date; lead.csn; lead.tTHRstr; round(lead.iasTHR)|''; trail.csn; trail.tTHRstr; round(trail.iasTHR)|''; round(sep)
```

**Folha Excel/CSV "FAST" do export operacional** (`_buildExportSheets`, linha 2671; `doExport` → CSV com secções `Geral`, `BLACK-LIST`, `FAST`; `doExportExcel` → xlsx com 3 folhas). Chama `renderFastResults()` e usa os pares **visíveis** (`_fastFilteredPairs`). Para cada par recalcula a lista de DEP (mesmo critério `classifyFlight==='dep'` + `_firstEpoch`, chave = nome do callsign em `flights`) e escolhe o **primeiro** com `t0<d.t<t1`:

| Coluna | Valor |
|---|---|
| HORA | `lead.tTHRstr` |
| DATA | `lead.date` (DD/MM/AAAA) |
| RWY | `parseInt(lead.rwy)` (2 ou 20) |
| LIDER (THR) | `lead.csn` |
| IAS LIDER | `round(lead.iasTHR)` ou `''` |
| SEGUIDOR | `trail.csn` |
| IAS SEG. | `round(trail.iasTHR)` ou `''` |
| SEP (s) | `round(sep)` |
| A/C INTERCALAR | `'Sim'` se existe DEP entre, senão `'Nao'` |
| CALL_SIGN | callsign do primeiro DEP intercalar ou `''` |
| HORA DEP | `epochToHHMMSS(depT)` ou `''` |

---

## 3. Análise Op. → "Análise de Dados" (`renderSepAnalysis` / `sep_renderAnalysis`)

Título do export: **"Análise LPPT - limite {limit}s"**.

### 3.1 Dados base — `sep_buildData()` (linha 7778)

Executado sempre que se abre a sub-aba (via `ensureAnaTabData('anaData')` → `runFinalAnalysis` se necessário → `buildFastPairs()` → `renderSepAnalysis()`). Usa **todos** os `_fastPairs` (sem os filtros da aba FAST).

**`sep_results`** — um registo por par:
```
horaA   = lead.tTHRstr                     pistaA = pista = String(lead.rwy)
csnA=callA = lead.csn                      csnB=callB = trail.csn
iasA    = round(lead.iasTHR) | null        iasB = round(trail.iasTHR) | null
horaB   = trail.tTHRstr
sepSec  = round(sep)           _sepSecNum = round(sep)
sepNm   = +(sep*(140/3600)).toFixed(2)     // distância do seguidor à THR quando o precedente cruzou a THR, a 140 kt fixos
depCsn  = primeiro DEP intercalar (csn) | ''     depHora = HH:MM:SS do primeiro DEP | ''
bSecAtDep = round(trail.epochTHR - firstDep.t) | null      (só se trail.iasTHR truthy e secs>0)
bNmAtDep  = +(bSecAtDep * trail.iasTHR/3600).toFixed(2) | null
seq=_seq  = 'AA' | 'ADA' | 'ADDA' | 'AD…A'   (U+2026)
data    = lead._dateRaw (AAMMDD) || lead.date
_hasDep = depCnt>0        _depCount = depCnt
_depDistances = [ +( (trail.epochTHR - d.t) * (trail.iasTHR||140)/3600 ).toFixed(2) para cada DEP intercalar com secs>0 ]
_viz = {A:{t:lead.epochTHR,csn}, B:{t:trail.epochTHR,csn}, deps:[{t,csn}…]}
_hasB = true      _id = índice sequencial
```
Nota: `_depDistances` usa fallback 140 kt quando `iasTHR` é nulo; `bNmAtDep` não (fica `null`).

**`sep_movementRows`** — movimentos:
- ARR: por cada `finalResults` → `{type:'ARR', callsign:csn, hora:tTHRstr, pista:rwy, data:_dateRaw, t:epochTHR, _isMovement:true}`.
- DEP: por cada `flights[csn]` com `classifyFlight==='dep'`, `t=_firstEpoch(rows)>0` → `{type:'DEP', callsign:rows[0].csn, hora:epochToHHMMSS(t), pista: rows[0]._rwy||'' (**sempre vazio** — `_rwy` nunca é definido), data: rows[0]._date, t}`.
- Ordenados por `t`. Campos `company`, `ias`, `fileName` não existem (ficam vazios nas tabelas; a companhia é inferida por `companyFromCallsign` no resumo por companhia).

### 3.2 Controlos / filtros (linhas 900-913)

| id | Label | Opções | Default |
|---|---|---|---|
| `sep_anaLimit` | Limite crítico | 240, 200, 165, 140, 120 | **165** |
| `anaData` | Data | Todas / datas (`AAMMDD`) presentes em `sep_results` | Todas |
| `sep_anaHour` | Hora | Todas / horas `HH` de `horaA` | Todas |
| `sep_anaPista` | Pista | Todas / RWY 02 / RWY 20 (repovoado com pistas presentes) | Todas |
| `sep_anaTipo` | Tipo | Tudo / `withDep` "Com DEP entre aterragens" / `noDep` "Sem DEP no meio" | Tudo |
| `sep_anaSeq` | Sequência | Todas / AA / ADA / ADDA / `AD...A` (HTML) — repovoado com valores presentes (`AD…A`) | Todas |
| `sep_anaDepNm` | Seguidor no DEP até | Qualquer / 3 / 4 / 5 / 6 NM | Qualquer |
| `sep_anaCrit` | Mostrar | Todos os pares / `crit` Só abaixo do limite | Todos |
| botões | Atualizar análise (`renderSepAnalysis`), Download análise (`sep_exportAnalysisExcel`), Relatório PDF | | |

**Pares filtrados** (`sep_anaFilteredRows`):
```js
if(!r._hasB) return false;
if(data!=='all' && r.data!==data) return false;
if(hour!=='all' && (r.horaA||'').slice(0,2)!==hour) return false;
if(pista!=='all' && r.pista!==pista) return false;
if(tipo==='withDep' && !r._hasDep) return false;
if(tipo==='noDep' && r._hasDep) return false;
if(seq!=='all' && (r._seq||'')!==seq) return false;
if(depNm!=='all'){ if(!r._hasDep) return false; if(!(r._depDistances||[]).some(nm=>Number(nm)<=depNmLimit)) return false; }
if(crit==='crit' && !(r._sepSecNum < limit)) return false;
```
**Movimentos filtrados** (`sep_anaFilteredMovements`): por `data`, `hour` (de `hora`), `pista` — nota: com pista ≠ Todas os DEP desaparecem (pista vazia).

**Definição de "par crítico"**: `r._sepSecNum < limit` (estritamente menor que o limite seleccionado; `_sepSecNum = round(sep)`).

### 3.3 Cartões de topo e KPIs (`sep_renderAnalysis`, linha 7851)

Cartões (`metric`): `mFiles` = nº de ficheiros carregados; `mRows` = `sep_movementRows.length` (rotulado "registos radar" mas é nº de movimentos); `mLand` = `finalResults.length` ("passagens THR detetadas"); `mPairs` = `sep_results.length`.

Mini-KPIs (sobre `rows` filtrados, `critRows = rows.filter(sep<limit)`, `movs` filtrados):
| id | Valor |
|---|---|
| `sep_akPairs` | `rows.length` |
| `sep_akCrit` | `critRows.length` |
| `sep_akCritDep` | críticos com `_hasDep` |
| `sep_akCritNoDep` | críticos sem `_hasDep` |
| `sep_akMin` | `min(_sepSecNum).toFixed(1)+' s'` |
| `sep_akAvg` | média `.toFixed(1)+' s'` |
| `sep_akMedian` | mediana (`sep_median`: média dos dois centrais se par) |
| `sep_akHour` | hora (de `horaA`) com mais críticos: `"HHh (n)"` (empate → menor hora) |
| `sep_akBusyHour` | moda da hora de `horaA` em `rows`: `"HHh (n)"` |
| `sep_akMainRwy` | moda de `pista`: `"RWY xx (n)"` |
| `sep_akDepTotal` | `Σ _depCount` |
| `sep_akMovs` | `movs.length` |
| `sep_akPeakArr` / `PeakDep` / `PeakTotal` | hora com mais ARR / DEP / total em `sep_movementHourSummary(movs)` → `"HHh (n)"` |

`sep_anaStatus`: `"${rows.length} pares precedente/seguidor analisados · ${crit} abaixo de ${limit}s"`.

### 3.4 Gráficos (SVG; todos sobre `rows` filtrados)

1. **Distribuição das separações** (`sep_renderHist`): bins `[0,60,90,120,140,165,200,240,∞)`, rótulos `0-60, 60-90, 90-120, 120-140, 140-165, 165-200, 200-240, >240`; `v>=bins[i] && v<bins[i+1]`; barra vermelha se o bin está totalmente abaixo do limite ou contém o limite (`bins[i+1]<=limit || (bins[i]<limit && bins[i+1]>limit)`); tooltip: intervalo, pares, críticos no intervalo.
2. **Resumo por hora** (`sep_renderByHour`): barras agrupadas por `HH` de `horaA`: Total vs Críticos (+ `dep` = pares com DEP no tooltip, % crítico).
3. **Análise por pista** (`sep_renderRunway`): para `'02'` e `'20'` (fixo) barras horizontais `total`, `crit`, `dep` (pares com DEP).
4. **Tipo de sequência** (`sep_renderSeq`): categorias fixas `['AA','ADA','ADDA','AD...A']` (três pontos ASCII) — Total vs Críticos. **Edge case**: `_seq` é gerado com `'AD…'` (U+2026) pelo que a categoria `AD...A` nunca casa e pares com 3+ DEP não aparecem neste gráfico.
5. **Movimentos por hora** (`sep_renderMovementHour`): total ARR+DEP por `HH` de `hora` (só horas com movimentos).
6. **Movimentos por companhia**: top 15 de `sep_companySummary` por nº de movimentos.
7. **Top 10 companhias por taxa de ocorrências críticas**: companhias com `critical>0`, ordenadas por `rate` desc, depois `critical`, depois `movements`; valor = `rate×100` (1 dec).
8. **Posição do seguidor no momento do DEP** (`sep_renderDepDistance`): valores = todos os `_depDistances` (um por DEP); bins `[0,3,4,5,6,∞)` com rótulos `<3, 3-4, 4-5, 5-6, >6` NM e classes `muito crítico, crítico, apertado, normal, confortável`; barras `<3` e `3-4` a vermelho; tooltip inclui quantos pertencem a pares críticos.
9. **Separação vs distância do seguidor** (`sep_renderSepDistance`): scatter X = `sepSec`, Y = `sepNm` (= `sep×140/3600`, "distância do seguidor à THR quando o precedente cruzou a soleira" a 140 kt); botões `Todos (n)`, `< limit s (n)`, `≥ limit s (n)`; cor laranja se com DEP, accent se sem; contorno vermelho se crítico; linha vertical tracejada no `limit`; grelha a 3,4,5,6 NM; tooltip inclui `IAS do seguidor` = `iasB`.
10. **Timeline operacional** (`sep_renderTimeline`): eventos por par: `precedente` (t = `lead.epochTHR mod 86400`, azul `#0b5cad`, 16 px acima da faixa), `dep` intermédio (quadrado laranja `#f59e0b`, na faixa), `seguidor` (roxo `#7c3aed`, 16 px abaixo); contorno vermelho `#b91c1c` se par crítico; segmento entre A e B na faixa da pista (vermelho e espessura 4 se crítico, cinza 2 caso contrário). Faixas: `RWY 02` (y=150) e `RWY 20` (y=260). Zoom: `all` (dia completo, 900 px/h), `4` (1200 px/h), `2` (default, 1500 px/h), `1` (2000 px/h); hora foco `auto` = hora com mais eventos; etiquetas `crit` (default: só callsigns de pares críticos) / `none` / `all`. Legenda: "Precedente na THR", "DEP intermédio", "Seguidor na THR", "Par abaixo do limite". Clique → navega para a aba FAST e realça o par.
11. **IAS da aeronave seguidora** (`sep_renderIas`): bins de `iasB` `[0,140,150,160,170,∞)` rótulos `<140, 140-150, 150-160, 160-170, >170` — Total vs Críticos (pares sem `iasB` são ignorados).

### 3.5 Tabelas

**Top 10 situações mais críticas** (`sep_renderCriticalTable`): `rows` ordenados por `_sepSecNum` asc, 10 primeiros. Colunas: `Pista, Data, Hora A, Callsign A, Callsign B, Seq., Sep. s, Sep. NM, DEP (pill csn ou "Sem DEP"), Hora DEP, Seguidor no DEP (= bSecAtDep, em s)`.

**Resumo por hora** (`sep_renderHourTable`): por `HH` de `horaA` (ordenado): `Hora | Chegadas | Pares preced./seg. | < limite | Com DEP | Menor sep. | Média sep.` — `Chegadas` = nº de precedentes distintos (`csnA|horaA|pista`) nessa hora em **todos** os `sep_results` (não filtrados); `Com DEP` = `Σ _depCount`; `Menor`/`Média` com 1 decimal + ' s'.

**Resumo por companhia** (`sep_companySummary(movs, rows, limit)`): companhia = `companyFromCallsign(callsign)` dos movimentos filtrados; `movements, arr, dep`; `critical` = nº de pares críticos (de `rows`) em que a companhia é a do precedente **ou** do seguidor (contado uma vez por par e por companhia); `rate = critical/movements` (0 se sem movimentos); ordenado por `movements` desc depois nome. Colunas: `Companhia | Movimentos | ARR | DEP | Ocorrências críticas | Taxa por movimento (%.1f%)`.

### 3.6 Export "Download análise" (`sep_exportAnalysisExcel`) — ficheiro `analise_separacao_thr_lppt.xls` (HTML com tabelas)

- `<h2>Análise LPPT - limite {limit}s</h2>`
- **Pares filtrados**: `Pista | Data | Hora A | Callsign precedente | IAS precedente | Callsign seguidor | IAS seguidor | Sep. s | Sep. NM | Seq. | DEP | Hora DEP | Seguidor à THR no DEP (s) | Seguidor à THR no DEP (NM)` ← `pista, data, horaA, csnA, iasA, csnB, iasB, sepSec, sepNm, _seq, depCsn, depHora, bSecAtDep, bNmAtDep`.
- **Top 10 críticos**: `Pista | Data | Hora A | Precedente | Seguidor | Seq. | Sep. s | Sep. NM | DEP`.
- **Movimentos ARR+DEP**: `Tipo | Pista | Data | Hora | Callsign | Companhia | IAS | Ficheiro` (últimos 3 vazios).
- **Resumo por companhia**: `Companhia | Movimentos | ARR | DEP | Ocorrências críticas | Taxa`.

O modal "dados de origem" (clique em KPI/barra) exporta `.xls` com `Pista, Data, Hora THR, Precedente, IAS Prec., Seguidor, IAS Seg., Sep. s, Sep. NM, Seq., DEP, Hora DEP, Seg. DEP (NM)` ou, para movimentos, `Tipo, Pista, Data, Hora, Callsign`.

---

## 4. Análise Op. → "Análise Diária" (`renderSepDaily`, linha 9423)

Título do export: **"Análise Diária LPPT — limite {limit}s"** (`analise_diaria_lppt.xls`).

### 4.1 Inputs
- Dias e blocos seleccionados no **painel esquerdo** (`selDaysSet` — datas `AAMMDD`; `selBlocksSet` — blocos `HH-HH`). Botão "🔄 Actualizar análise diária".
- `limit` = valor de `sep_anaLimit` da aba Análise de Dados (default 165).
- Os dados `sep_results`/`sep_movementRows` são reconstruídos (`sep_buildData`).

### 4.2 Filtragem
```js
blockHours('08-12') → ['08','09','10','11']
activeHours = união das horas dos blocos seleccionados; inBlock(h) = !selectedBlocks.size || activeHours.has(h)
movs = sep_movementRows.filter(m => selectedDates.has(m.data) && inBlock(hora.slice(0,2)))
rows = sep_results.filter(r => r._hasB!==false && selectedDates.has(r.data) && inBlock(horaA.slice(0,2)))
arr = movs ARR; dep = movs DEP; crit = rows com _sepSecNum<limit; critDep = crit com _hasDep
```

### 4.3 Agregações
- **Por dia** (`stats`, ordem de data): `label = "MM-DD Dow"` (dia da semana abreviado `Dom..Sáb`, a partir de `AAMMDD` → `Date(2000+AA, MM-1, DD)`), `arr, dep, total, pairs, crit`.
- **Pico horário** global: `sep_movementHourSummary(movs)` → hora com mais ARR / mais DEP.
- **Callsigns comuns**: callsigns (dos movimentos) presentes em >1 dia seleccionado; `count` = nº de dias; ordenado por `count` desc, nome asc; tabela limitada a 80.
- **Por dia da semana** (`wdAgg`): agrupa `stats` por `wd`; `days, mov, arr, dep, pairs, crit, critDep`; `avgMov = mov/days`, `avgCrit = crit/days`, `rate = crit/pairs×100`; ordem Seg→Dom (`[1,2,3,4,5,6,0]`); destaques: dia com maior `avgMov`, maior `avgCrit`, maior `rate`; arredondamento a 1 decimal.
- **Por dia e hora** (`hourOut`): para cada data × hora `00..23` em bloco activo com movimentos ou pares: `arr, dep, total, pairs, crit`.
- **Companhias**: `sep_companySummary(movs,rows,limit)` top 10 por movimentos.

### 4.4 Outputs
KPIs: `dias selecionados, movimentos ARR+DEP, aterragens, descolagens, pares precedente/seguidor, pares abaixo do limite, críticos com DEP, pico de aterragens "HHh (n)", pico de descolagens, callsigns comuns aos dias`.

Gráficos: Movimentos por dia (ARR vs DEP agrupadas); Ocorrências críticas por dia; Pico horário por dia (máximo de movimentos numa hora, por dia); Companhias por dia (top 10); Média de movimentos por dia da semana; Média de pares críticos por dia da semana.

Tabelas: Padrões por dia da semana (`Dia da semana | Nº dias | Mov. totais | Méd mov/dia | Críticos totais | Méd crít/dia | Taxa crít. | Datas`); Callsigns comuns (`Callsign | Nº dias | Dias | Movimentos | Companhia`); Resumo por dia e hora (`Data | Hora | ARR | DEP | Movimentos | Pares | Críticos`).

Excel (`sep_exportDailyExcel`): secções Indicadores, Resumo por dia (`Data | Dia sem. | ARR | DEP | Movimentos | Pares | Críticos`), Padrões por dia da semana, Top companhias (`Companhia | Movimentos | ARR | DEP | Críticos | Taxa`), Callsigns comuns, Resumo por dia e hora (`Data | Dia sem. | Hora | ARR | DEP | Movimentos | Pares | Críticos`).

---

## 5. Resumo de constantes e defaults

| Constante | Valor | Onde |
|---|---|---|
| Tolerância de cruzamento THR (along) | `≤ 0.3 NM` | `analyzeFlightApproach` |
| Caixa de sanidade | `±0.6°` lat/lon | idem |
| FAF (distância virtual) | 7 NM (3–15) | `finFaf` |
| Corredor lateral | ±2 NM (0.5–5) | `finCorr` |
| Alt máx. na THR | elev_THR + 1000 ft (500–3000) | `finAltThr` |
| Estabilizada | AGL FAF 800–5000 ft, IAS FAF 120–230 kt (ou nula), |cross FAF| ≤ 1.0 NM | |
| IAS a 4 NM | along = 4 NM | |
| Par FAST válido | mesma pista + mesmo dia, `0 < sep ≤ 600 s` | `buildFastPairs` |
| Limiar FAST | 160 s (30–300); faixa superior fixa 240 s | `fastThreshold` |
| Cores sep. FAST | `<120` vermelho, `<thr` laranja, `≥thr` verde | |
| DEP intercalar | `classifyFlight==='dep'` e `t_lead_THR < t_first_row < t_trail_THR` | |
| Sequência | 0 DEP `AA`, 1 `ADA`, 2 `ADDA`, ≥3 `AD…A` | |
| Velocidade de referência | 140 kt (sepNm, diagrama); IAS THR do seguidor (Seg. no DEP) | |
| Limite crítico Análise de Dados/Diária | 165 s (240/200/165/140/120); crítico = `round(sep) < limit` | `sep_anaLimit` |
| Bins histograma separações | 0,60,90,120,140,165,200,240,∞ | |
| Bins posição no DEP | 0,3,4,5,6,∞ NM | |
| Bins IAS seguidor | 0,140,150,160,170,∞ kt | |
| Escala APP | 12.0 → 0.0 NM passo 0.5; buffer ±4 kt; corredor |cross|<1.5 NM; último ponto ≤1.5 NM | `_computeAppDistViol` |

## 6. Edge cases a reproduzir (ou corrigir conscientemente)

1. `rowEpoch` é pseudo-epoch (`int(AAMMDD)*86400 + s`); nunca subtrair tempos de dias diferentes.
2. `classifyFlight`, `_firstEpoch` e as listas de DEP operam sobre `flights[csn]` (todas as datas misturadas, ordenadas por `tod` string). Um callsign DEP repetido em vários dias gera um único evento DEP.
3. A detecção de aterragem exige cruzamento do FAF virtual (`fafNM`); sem ele o voo não conta, mesmo cruzando a THR.
4. A interpolação na THR pode extrapolar (`kT>1`) quando `0 < pB.along ≤ 0.3`.
5. `sepTimeS` (aba Final) não tem limite de 600 s; `_fastPairs` tem.
6. Bug `/1000` no CDO: `cdo` é quase sempre `true`.
7. `sep_movementRows` DEP têm `pista=''` → filtros por pista excluem DEPs; "Análise por pista" só considera `'02'`/`'20'`.
8. Categoria `AD...A` (ASCII) no gráfico/filtro de sequência nunca casa com `AD…A` (U+2026) gerado.
9. "Chegadas" no Resumo por hora conta precedentes distintos de **todos** os pares, não dos filtrados; a primeira aterragem do dia/pista nunca é "precedente" de ninguém se for a única.
10. O botão `< Abaixo` aparece realçado no HTML mas o estado inicial é `_fastMode='all'`.
11. Estado `finRwy` é forçado a `BOTH` na análise automática após `applyFilter`.
