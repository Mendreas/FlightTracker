# Especificação — Abas "Velocidades STAR" e "Velocidades APP" (FlightTracker)

Fonte: `/home/claude/mendreas/flighttracker/dist/index.html` (linhas indicadas entre parênteses). Documento de referência para reimplementação fiel em Python. Todas as fórmulas, defaults, limiares e colunas são transcritos do JS original.

---

## 0. Primitivas comuns (usadas por ambas as abas)

### 0.1 Modelo de dados de entrada

- `flights` — dicionário `callsign → {rows, color, visible}`. Cada `row` tem, entre outras, as colunas CSV: `tod` (hora `HH:MM:SS[.fff]`), `latitude`, `longitude`, `modec` / `baroh` (altitude), `iar` / `iara` (IAS), `tas`, `roc`, e o campo interno `_date` (string `YYMMDD`, ou `'??'` se desconhecida).
- **Leg** (`getFlightLegs()`, l.1448): par único *(callsign, `_date`)*. Um callsign que opera 31 dias produz 31 legs. Estrutura: `{csn, date, rows, color, _flight, firstEpoch}`. Legs ordenadas por `date` (lexicográfica) e depois por `firstEpoch`.
- `isLegVisible(leg)` (l.1473): `leg._flight.visible` tem de ser true; se `flightTypeFilter!=='all'`, exige `classifyFlight(leg.rows)===flightTypeFilter`. **Default de `flightTypeFilter` é `'arr'`** (l.1189).

### 0.2 Funções auxiliares

```js
function gv(r,...ks){for(const k of ks){if(r[k]!==undefined&&r[k]!=='')return r[k];}return '—';}
function getAlt(r){
  const raw=r.modec!==undefined&&r.modec!==''?r.modec:r.baroh!==undefined&&r.baroh!==''?r.baroh:null;
  if(raw===null)return '—';const v=parseFloat(raw);if(isNaN(v))return '—';
  return Math.round(v<600?v*100:v);          // valores <600 são Flight Levels → ×100 ft
}
function _iasFromRow(r){                       // l.3532
  const v=gv(r,'iar','iara','ias');
  if(v==='—')return null;
  const n=parseFloat(String(v).replace(',','.'));
  return isNaN(n)?null:n;
}
function _altFromRow(r){const a=getAlt(r);if(a==='—')return NaN;return typeof a==='number'?a:parseFloat(a);}
function todSec(tod){ const p=String(tod||'').split(':'); if(p.length<3)return NaN;
  const h=+p[0],m=+p[1],sec=parseFloat(p[2]); if(isNaN(h)||isNaN(m)||isNaN(sec))return NaN; return h*3600+m*60+sec; }
function rowEpoch(r){                          // l.3279
  const t=todSec(r.tod);if(isNaN(t))return NaN;
  const dk=r._date&&r._date!=='??'?(parseInt(String(r._date).replace(/\D/g,''),10)||0):0;
  return dk*86400+t;                           // NB: "epoch" pseudo = YYMMDD*86400 + segundos do dia
}
function fmtDate(d){ if(!d||d==='??')return 'Data desconhecida'; if(d.length===6)return `${d.slice(4,6)}/${d.slice(2,4)}/20${d.slice(0,2)}`; return d; }  // YYMMDD → DD/MM/20YY
function fmtNM1(v){return v==null||isNaN(v)?'—':v.toFixed(1).replace('.',',');}
```

**Classificação ARR/DEP/LVL** (`classifyFlight`, l.1422):

1. `rows.length<2` → `'lvl'`.
2. Percorre rows; para cada altitude válida (`getAlt`), regista `firstA` (primeira), `lastA` (última), `minA`, `maxA`.
3. Sem altitudes → `'lvl'`. `maxA-minA<500` → `'lvl'`.
4. `d=lastA-firstA`; `d<-500` → `'arr'`; `d>500` → `'dep'`; senão `'lvl'`.

**Distância em NM (haversine)** (`distNM`, l.3108), R = 3440.065 NM:

```js
function distNM(lat1,lon1,lat2,lon2){
  const R=3440.065,dLat=(lat2-lat1)*Math.PI/180,dLon=(lon2-lon1)*Math.PI/180;
  const a=Math.sin(dLat/2)**2+Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLon/2)**2;
  return R*2*Math.asin(Math.sqrt(a));
}
```

**Azimute inicial** (`bearingDeg`, l.3499): fórmula standard `atan2(sin Δλ·cos φ2, cos φ1·sin φ2 − sin φ1·cos φ2·cos Δλ)`, normalizada a [0,360).

### 0.3 Geometria do eixo de aproximação (`approachCoords`, l.3513)

```js
// along = distance along approach axis (positive = aircraft still ahead of THR coming in)
// cross = signed lateral offset from centerline (positive = right looking along approach direction)
function approachCoords(lat,lon,thrLat,thrLon,landBrg){
  const d=distNM(thrLat,thrLon,lat,lon);
  if(d===0)return{along:0,cross:0};
  const br=bearingDeg(thrLat,thrLon,lat,lon);   // azimute da THR para a aeronave
  const app=(landBrg+180)%360;                   // direcção "recíproca" = de onde vem a aproximação
  let delta=br-app;
  while(delta>180)delta-=360;
  while(delta<=-180)delta+=360;
  const dr=_rad(delta);
  return{along:d*Math.cos(dr),cross:d*Math.sin(dr)};
}
```

Ou seja: `along = d·cos(Δ)`, `cross = d·sin(Δ)`, com `Δ = bearing(THR→aeronave) − (brg_pista+180)`. `along>0` = ainda antes da THR; `along<0` = já passou a THR.

**Configuração de pistas** (`AIRPORT_CONFIGS`, l.3420) — `brg` = rumo verdadeiro da pista, THR do AIP:

| ICAO | RWY | THR lat | THR lon | brg (°T) | elev THR (ft) |
|---|---|---|---|---|---|
| LPPT | 02 | 38.766428 | -9.143903 | 32.0 | 357 |
| LPPT | 20 | 38.792331 | -9.130047 | 212.0 | 303 |
| LPPR | 17 | 41.260681 | -8.684561 | 171.0 | 151 |
| LPPR | 35 | 41.233886 | -8.677536 | 351.0 | 227 |
| LPFR | 10 | 37.017222 | -7.985614 | 101.0 | 24 |
| LPFR | 28 | 37.013450 | -7.959042 | 281.0 | 18 |
| LPMA | 05 | 32.689932 | -16.783751 | 47.0 | 146 |
| LPMA | 23 | 32.705841 | -16.765150 | 227.0 | 191 |

`getActiveRwy()` devolve `AIRPORT_CONFIGS[activeAirport].rwys`. Nota importante (ver §2.3 Notas): o azimute geodésico real THR02→THR20 é ≈22.6°, mas o código usa `brg=32.0`/`212.0` (rumo magnético do AIP). Isto afecta `cross` na análise por distância (§2.3). Para reproduzir **fielmente**, usar os valores da tabela.

### 0.4 Pontos (waypoints) e grupos

`AIP_POINTS` (l.2742) — lista `{name,lat,lon,type:'aip',desc}`. `allPoints()` (l.2979) devolve os pontos AIP filtrados pelo aeroporto activo e pelo `pointMode` (modo da aba "Pontos"), mais os `userPoints` (pontos manuais do utilizador):

```js
function allPoints(){
  const names=activePointNames();   // pointMode==='ALL' ? POINT_GROUPS_ALL : POINT_GROUPS[pointMode]
  const aip=AIP_POINTS.filter(p=>{
    const n=String(p.name||'').toUpperCase();
    if((p.desc||'').includes(activeAirport)){ if(pointMode==='ALL')return true; return names.has(n); }
    if(activeAirport==='LPPT')return names.has(n);
    return false;
  });
  return [...aip,...userPoints];
}
```

`POINT_GROUPS` (l.2951):

```js
APP_02:['PESEX','NETVO','OKNIB','THR02'],
APP_20:['UPKAT','TOPVI','ROKOB','THR20'],
STAR02:['ESUTI','INBOM','LAZET','LUVUP','PULPO','VATZI','XAMAX','CASLU','MAZUK','ERNIL','RELKU','ZEFFI','NEVUD','PESEX','GANSU','YETSI','ORTUG','ZACRA','INLIB','MIGTO','ULTIT'],
STAR20:['ESEBI','ESUTI','INBOM','LAZET','LUVUP','PULPO','VATZI','XAMAX','ITAVIT','DEKKI','ROMEP','EVPAP','FUSSI','ARNIT','UPKAT','PT813','PT811','PT818','EKLID','ROTBU','LERLI','FADEF','COCUN'],
LPMA_APP_05:['PILIM','MONEC','ABUSU','MA563','MA564','MA565','MA566','THR05'],
LPMA_APP_23:['PILIM','MONEC','MA410','MA561','MA562','THR23'],
LPPR_APP_17:['ADNOV','PR741','PR742','THR17','PR744','RETMO'],
LPPR_APP_35:['AKULU','PR541','PR542','THR35','PR544','RETMO'],
LPPR_STAR17:['ABLEG','VASIP','PR650','PR612','ADNOV'],
LPPR_STAR35:['ABLEG','AKULU','VASIP'],
LPFR_APP_10:['RUWIB','FR910','THR10','FR728','GIMAL'],
LPFR_APP_28:['GEBTI','FR928','THR28','FR710','GIMAL'],
```
(`POINT_GROUPS_ALL` = união sem duplicados de todos os grupos.)

**Caso limite crítico**: as duas análises IAS usam `allPoints()`, que depende de `pointMode`. Se o utilizador tiver seleccionado p.ex. `APP_02` na aba Pontos, os waypoints STAR não estarão em `allPoints()` e a análise STAR reporta-os como "sem coordenadas"; a análise APP ignora o modo `APP_20` (ponto em falta → `continue`). Em LPPT, `pointMode` é forçado a `'APP_02'` ao abrir a aba Pontos (l.2604) e também pela auto-análise ao carregar (l.7425). **Na reimplementação Python, recomenda-se resolver os nomes directamente em `AIP_POINTS` (sem filtro de modo), que é o comportamento pretendido quando `pointMode==='ALL'`.** Lookup é por nome em maiúsculas; em nomes duplicados em `AIP_POINTS` (GANSU, EXONA, ARNIT, DEKKI, ESEBI, EVPAP, FUSSI, ITAVIT, LUXUT, ROMEP, ADNOV, RETMO, ABLEG, VASIP, FUSUL), o mapa `wpByName` fica com a **última** ocorrência na lista.

#### Coordenadas dos waypoints usados nas análises de velocidades

**LPPT — STAR (limites IAS default)** — todos `desc` sem "LPPT"-tag ou com; coordenadas de `AIP_POINTS`:

| WP | lat | lon | desc |
|---|---|---|---|
| ESUTI | 37.859908 | -10.430214 | IAF LPPT |
| INBOM | 40.001919 | -8.302003 | IAF/DEP LPPT |
| LAZET | 38.923944 | -10.671011 | Holding LPPT |
| LUVUP | 37.720342 | -10.168589 | IAF LPPT |
| PULPO | 39.043769 | -7.651956 | Holding LPPT |
| VATZI | 37.597808 | -8.863081 | Holding LPPT |
| XAMAX | 40.031100 | -8.536206 | Holding LPPT |
| ESEBI | 39.403189 | -8.666467 | IAF LPPT (ATC req.) (duplicado "Waypoint ARR LPPT", mesmas coords) |
| UNPOT | 38.179342 | -10.000000 | Waypoint ARR LPPT |
| CASLU | 38.540014 | -9.809978 | STAR |
| NATID | 38.881672 | -9.547750 | STAR |
| RULOX | 38.900000 | -10.000000 | ARR |
| GANSU | 38.000000 | -9.817550 (1ª) / **-9.817500 (2ª, prevalece)** | STAR / ENR |
| EXONA | 38.904414 | -8.016667 | STAR/DEP |
| LUXUT | 37.999797 | -9.026939 | STAR |
| ODLIX | 38.678922 | -9.317083 | STAR |
| MAZUK | 38.593839 | -9.554028 | STAR |
| ERNIL | 38.498111 | -9.529731 | STAR |
| RELKU | 38.416922 | -9.460778 | STAR |
| ZEFFI | 38.362583 | -9.357719 | STAR |
| NEVUD | 38.567692 | -9.313608 | STAR |
| EKLID | 39.142372 | -9.263636 | STAR |
| ROTBU | 39.196375 | -9.159175 | STAR |
| LERLI | 39.215033 | -9.036011 | STAR |
| FADEF | 39.195472 | -8.913075 | STAR |
| COCUN | 39.026533 | -9.068600 | STAR |
| YETSI | 38.321531 | -8.895339 | STAR RWY02 |
| ORTUG | 38.403972 | -8.996081 | STAR RWY02 |
| ZACRA | 38.346553 | -9.106456 | STAR RWY02 |
| INLIB | 38.326622 | -9.236239 | STAR RWY02 |
| MIGTO | 38.347183 | -9.365861 | STAR RWY02 |
| ULTIT | 38.532278 | -9.204903 | STAR RWY02 |
| ITAVIT | 38.961519 | -8.562219 | STAR |
| DEKKI | 38.963058 | -8.695667 | STAR |
| ROMEP | 39.065364 | -8.720614 | STAR |
| EVPAP | 39.152403 | -8.794006 | STAR |
| FUSSI | 39.210842 | -8.904750 | STAR |
| ARNIT | 38.990722 | -8.959336 | STAR |
| PESEX | 38.592339 | -9.236858 | FAF RWY 02/20 LPPT |
| UPKAT | 38.966400 | -9.036681 | CIF/Holding LPPT |

**LPPT — APP** (com distâncias calculadas pelas fórmulas acima, `brg` do config):

| WP | lat | lon | desc | dist. geodésica à THR (NM) | `along` (NM) | `cross` (NM) | NM AIP (APP_DIST_WAYPOINTS) |
|---|---|---|---|---|---|---|---|
| PESEX | 38.592339 | -9.236858 | FAF RWY 02 | 11.32 | 11.17 | -1.84 | 11.3 |
| NETVO | 38.640000 | -9.211389 | STAR/APP RWY 02 | 8.22 | 8.11 | -1.34 | 8.2 |
| OKNIB | 38.702222 | -9.178611 | FAF interm RWY 02 | 4.18 | 4.13 | -0.66 | 4.2 |
| THR02 | 38.766428 | -9.143903 | Threshold RWY 02 | 0 | 0 | 0 | 0.0 |
| UPKAT | 38.966400 | -9.036681 | CIF/Holding (IF RWY 20) | 11.33 | 11.17 | -1.84 | 11.3 |
| TOPVI | 38.918611 | -9.062500 | STAR/APP RWY 20 | 8.21 | 8.10 | -1.34 | 8.2 |
| ROKOB | 38.853056 | -9.097500 | FAF interm RWY 20 | 3.95 | 3.90 | -0.64 | 3.96 |
| THR20 | 38.792331 | -9.130047 | Threshold RWY 20 | 0 | 0 | 0 | 0.0 |
| DME02 | 38.769361 | -9.143833 | GP/DME ILI (não usado nas análises) | 0.18 | | | |
| DME20 | 38.789167 | -9.130250 | GP/DME ILB (não usado) | 0.19 | | | |

(O `cross` ≈ −1.8 NM para PESEX/UPKAT é artefacto do `brg` 32/212 vs. azimute geodésico ≈22.6/202.6 — ver §2.3 Notas.)

**LPPR — APP** (IAS APP; não há análise "por distância" para LPPR):

| WP | lat | lon | desc | dist THR (NM) |
|---|---|---|---|---|
| ADNOV | 41.518244 | -8.753164 | IAF RWY 17 LPPR (prevalece sobre o FRA 41.518333/-8.753056) | 15.77 (THR17) |
| PR741 | 41.452894 | -8.735161 | IF RNP 17 | 11.76 |
| PR742 | 41.384278 | -8.717044 | FAF RNP Y 17 | 7.56 |
| THR17 | 41.260681 | -8.684561 | THR RWY 17 | 0 |
| AKULU | 40.984044 | -8.611819 | IAF RWY 35 | 15.29 (THR35) |
| PR541 | 41.061011 | -8.632356 | IF RNP 35 | 10.58 |
| PR542 | 41.093897 | -8.640931 | FAF RNP 35 | 8.57 |
| THR35 | 41.233886 | -8.677536 | THR RWY 35 | 0 |

**LPFR — APP**:

| WP | lat | lon | desc | dist THR (NM) |
|---|---|---|---|---|
| RUWIB | 37.057083 | -8.269222 | IF ILS/RNP 10 | 13.80 (THR10) |
| FR910 | 37.043778 | -8.174000 | FAP ILS RWY 10 | 9.17 |
| THR10 | 37.017222 | -7.985614 | THR RWY 10 | 0 |
| GEBTI | 36.972778 | -7.675306 | IF ILS/RNP 28 | 13.82 (THR28) |
| FR928 | 36.986472 | -7.770333 | FAP ILS RWY 28 | 9.19 |
| THR28 | 37.013450 | -7.959042 | THR RWY 28 | 0 |

**LPMA**: sem análise de velocidades (mensagem "LPMA — Sem restrições de velocidade").

### 0.5 Detecção de passagem num waypoint (comum às duas abas, "CPA por raio")

Não há interpolação: a passagem é o **ponto de radar mais próximo do waypoint dentro do raio** (CPA discreto). `findNearestPassInRadius` (l.4353):

```js
function findNearestPassInRadius(rows,pt,radius){
  const coslat=Math.max(Math.cos(pt.lat*Math.PI/180),1e-6);
  const dLat=(radius/60)*1.4,dLon=(radius/60/coslat)*1.4;   // bounding box rápido (1 NM = 1/60°), factor 1.4
  let best=null;
  for(const r of rows){
    const la=+r.latitude,lo=+r.longitude;
    if(!la||!lo||isNaN(la)||isNaN(lo))continue;              // NB: lat/lon == 0 também é rejeitado
    if(Math.abs(la-pt.lat)>dLat||Math.abs(lo-pt.lon)>dLon)continue;
    const d=distNM(pt.lat,pt.lon,la,lo);
    if(d<=radius&&(best===null||d<best.d)){ const ias=_iasFromRow(r); best={d,row:r,ias}; }
  }
  return best;   // {d, row, ias} ou null
}
```

- Empates em `d`: fica o **primeiro** encontrado (comparação estrita `<`).
- A IAS "no ponto" é a IAS da linha do CPA (sem interpolação). Se `ias==null` ou `ias<=0`, a passagem **não conta** (nem como passagem nem como violação).
- Apenas uma passagem por (leg, waypoint) — mesmo que o voo passe duas vezes (holding), só o CPA global.

---

## 1. Aba "Velocidades STAR" — Conformidade IAS (STAR)

Painel `#panel-ias` (HTML l.645–696). Tab: `⚡ Velocidades STAR` (`switchTab('ias')`). Ao abrir a aba: `if(!iasLimits)loadIasLimits(); renderIasManage();` (l.2616). `loadIasLimits()` também é chamado no arranque (l.6554). A análise STAR é **auto-executada** depois do carregamento de dados (`_autoAnalyseAndAlert`, l.7447) se `iasResults` ainda for null.

### 1.1 Controlos

| id | Tipo | Label | Default | min/max/step | Função |
|---|---|---|---|---|---|
| `iasRadius` | number | "Raio CPA:" … "NM" | **1** | 0.1 / 10 / 0.1 | raio de detecção da passagem |
| `iasTolerance` | number | "Tolerância +" … "kt" (title: "Margem acima do limite antes de considerar violação") | **0** | 0 / 30 / 1 | margem só para cima |
| botão | "▶ Analisar" | | | | `runIasCompliance()` |
| botão | "↓ CSV" | | | | `exportIasCsv()` |
| botão `iasManageBtn` | "⚙ Gerir limites" / "⚙ Fechar gestão" | | | | `toggleIasManage()` — abre/fecha `#iasManagePanel` |
| `iasCount` | span | estado/progresso ("A analisar IAS STAR... i/N (w/W)") e resumo final "`N passagens · V violações`" | | | |

**Painel de gestão de limites** (`#iasManagePanel`): título "Restrições IAS publicadas (LPPT STAR, 2025-26) — edita os valores, adiciona ou remove waypoints. Guardado no browser."
- Botões: "↻ Repor defaults" (`resetIasDefaults` — pede `confirm('Repor os limites default das STAR de LPPT? Serão descartadas todas as alterações.')`), "↓ JSON" (`exportIasLimits` → ficheiro `ias_limits_YYYY-MM-DD.json`, JSON pretty 2 espaços do objecto `iasLimits`), "↑ JSON" (`importIasLimits` — lê JSON objecto; aceita só entradas com `parseInt(v)` entre 80 e 400, chave → maiúsculas; **substitui** todo o `iasLimits`; se nenhuma válida → alert "Nenhuma restrição válida no ficheiro."; sucesso → alert "Importadas N restrições.").
- Lista `#iasLimitsList`: uma linha por waypoint, **ordenada alfabeticamente** (`localeCompare`): nome (a laranja `#f59e0b` com "⚠" e title "Sem coordenadas — não será analisado" se o nome não estiver em `allPoints()`), input number `min=80 max=400 step=1` com `onchange=updateIasLimit(wp,val)` (se `parseInt` inválido ou fora de [80,400] → re-render, valor descartado), "kt", e "✖" (`removeIasLimit` com `confirm('Remover restrição para WP?')`).
- Adicionar: `iasNewWp` (texto, uppercase, placeholder "WAYPOINT"), `iasNewVal` (number, placeholder "IAS máx", HTML min=100 max=400 mas a validação JS é **80..400**), botão "+ Adicionar" (`addIasLimit`: `wp=trim().toUpperCase()`; se vazio ou valor inválido → alert "Waypoint e IAS válida são obrigatórios."). Pode sobrescrever um existente.

### 1.2 Estrutura `iasLimits` e persistência

```js
const LPPT_STAR_IAS_DEFAULTS={
  // IAFs
  ESUTI:280,INBOM:280,LAZET:280,LUVUP:280,PULPO:280,VATZI:280,XAMAX:280,ESEBI:250,
  // Transição
  UNPOT:250,CASLU:230,NATID:230,RULOX:250,GANSU:250,EXONA:250,LUXUT:250,ODLIX:230,
  // Norte → RWY 02 / RWY 20
  MAZUK:220,ERNIL:220,RELKU:220,ZEFFI:220,NEVUD:180,
  EKLID:220,ROTBU:220,LERLI:220,FADEF:220,COCUN:180,
  // Sul → RWY 02
  YETSI:230,ORTUG:220,ZACRA:220,INLIB:220,MIGTO:220,ULTIT:180,
  // Sul → RWY 20
  ITAVIT:230,DEKKI:220,ROMEP:220,EVPAP:220,FUSSI:220,ARNIT:180,
  // FAF/Clearance limits
  PESEX:180,UPKAT:180
};
```
(42 waypoints; unidade kt; são **IAS máxima** ao passar no waypoint.)

- `iasLimits` é um objecto plano `{WAYPOINT: kt}`. Não há noção de pista nem de grupo STAR02/STAR20 — é uma lista única, aplicada a **todas** as chegadas do aeroporto activo (os defaults são só de LPPT, mas a análise corre para qualquer aeroporto com os nomes que existirem em `allPoints()`).
- Persistência: `localStorage['ft.iasLimits']` = `JSON.stringify(iasLimits)`. `loadIasLimits()`: se existir a chave, `JSON.parse`; senão cópia dos defaults. Toda a edição (`updateIasLimit`, `removeIasLimit`, `addIasLimit`, import, reset) chama `saveIasLimits()`.
- Na reimplementação Python: ficheiro JSON equivalente (ex.: `ias_limits.json` no perfil do utilizador).

### 1.3 Algoritmo (`runIasCompliance`, l.4119)

Entradas: `flights`, `iasLimits`, `radius = max(0.1, parseFloat(iasRadius)||1)`, `tol = max(0, parseFloat(iasTolerance)||0)`, `pts=allPoints()`.

1. Se não há voos → alert "Sem dados carregados."
2. `wpByName[name.toUpperCase()] = pt` para todos os pontos de `allPoints()` (última ocorrência vence).
3. Para cada `(wp, limit)` em `iasLimits`: se `wpByName[wp.toUpperCase()]` não existe → `missing.push(wp)`; senão criar `perWp[wp]={wp,lat,lon,limit,total:0,compliant:0,violations:0,iasSum:0,iasMax:0,iasMin:Infinity,excessSum:0,excessMax:0}` e pré-calcular a bounding box: `_dLat=(radius/60)*1.4`, `_dLon=(radius/60/max(cos(lat),1e-6))*1.4`.
4. Para cada leg de `getFlightLegs()` (ordem data/hora):
   - `if(!isLegVisible(leg)) continue;` → `flightsTotal++`.
   - `if(classifyFlight(leg.rows)!=='arr') continue;` → `flightsAnalysed++`.
   - `rowStep = max(1, ceil(rows.length/12000))` (**sub-amostragem**: legs com >12 000 linhas são varridas de `rowStep` em `rowStep`; `MAX_ROWS_PER_LEG_SCAN=12000`).
   - Para cada waypoint `stat` de `perWpList` (ordem de inserção = ordem das chaves de `iasLimits`):
     - Percorrer `rows` com passo `rowStep`; ignorar lat/lon inválidos ou `0`; rejeitar fora da bounding box; `d=distNM(stat.lat,stat.lon,la,lo)`; manter `best` com `d<=radius` e menor `d` (igual ao §0.5, mas inline e com `rowStep`).
     - **Orçamento de tempo**: se `performance.now()-legStart > 180 ms` (`LEG_TIME_BUDGET_MS`) após processar um waypoint → `legTimedOut=true; break` (os restantes waypoints dessa leg **não são analisados**; a leg entra em `skippedLegs`). Em Python isto não deve ser replicado (é um workaround de UI); documentar como opcional.
     - Se `best && best.ias!=null && best.ias>0`:
       - `stat.total++; stat.iasSum+=ias; iasMax=max; iasMin=min;`
       - `excess = ias - limit`
       - `if(excess<=tol) stat.compliant++` (conforme)
       - senão: `stat.violations++; stat.excessSum+=excess; excessMax=max(excessMax,excess);` e `violations.push({csn, wp, ias, limit, excess, tod: String(row.tod).substring(0,8), date: fmtDate(row._date) ou '', dCpa: best.d, color, _epoch: rowEpoch(row)})`.
5. `violations.sort((a,b)=>(a._epoch||0)-(b._epoch||0))` — ordem cronológica.
6. `totalPasses = Σ perWp.total`, `totalComp = Σ perWp.compliant`, `totalViol = violations.length`.
7. `iasResults = {perWp, violations, radius, tol, flightsTotal, flightsAnalysed, totalPasses, totalComp, totalViol, missing, skippedLegs, generatedAt}`.

**Definição de violação STAR**: `IAS_CPA − limite > tolerância` (só por cima; IAS abaixo do limite é sempre conforme). Com `tol=0`, uma IAS exactamente igual ao limite é conforme.

### 1.4 Saídas

**Barra de resumo (`#iasSummary`)**:
- "Voos ARR analisados: `flightsAnalysed`/`flightsTotal`"
- "Passagens detectadas: `totalPasses`"
- "Conformes: `totalComp`" (verde `ias-ok`)
- "Violações: `totalViol`" (vermelho `ias-bad`)
- "Taxa de cumprimento: `pct`" onde `pct = totalComp/totalPasses*100`, formatada `toFixed(1)` com vírgula decimal + "%", ou "—" se `totalPasses==0`; classe: `pct>=95` → verde; `85<=pct<95` → neutro; `<85` → vermelho.
- "Raio R NM · Tol +T kt"
- Se `missing.length`: "⚠ N waypoints sem coordenadas" (title = lista).
- Se `skippedLegs.length`: "⚠ N leg(s) limitados por performance" (title = até 20 callsigns únicos).
- `#iasCount`: "`totalPasses` passagens · `totalViol` violações".

**Tabela "Por waypoint" (`#iasPerWpTable`)** — só waypoints com `total>0`; ordenação default: **taxa de violação desc** (`violations/total`), desempate `total` desc. Colunas:

| Coluna | Valor |
|---|---|
| Waypoint | nome (monospace, cor accent) |
| Limite (kt) | `limit` |
| Passagens | `total` |
| Conformes | `compliant` (verde) |
| Violações | `violations` (vermelho se >0) |
| % Cumprim. | `compliant/total*100`, 1 decimal com vírgula, `%`; verde ≥95, vermelho <85 |
| IAS méd. | `iasSum/total`, `toFixed(0)` |
| IAS máx. | `iasMax` ou "—" se 0 |
| IAS mín. | `iasMin` ou "—" se Infinity |
| Excesso méd. | `'+'+ (excessSum/violations).toFixed(0)` ou "—" se sem violações |
| Excesso máx. | `'+'+excessMax.toFixed(0)` ou "—" |

Vazio: "Nenhuma passagem detectada nos waypoints configurados" (colspan 11). Cabeçalhos clicáveis (`activateSortable`): sort genérico por texto da célula — numérico se o texto inteiro casa `/^-?[\d]+([.,]\d+)?(\s*(kt|ft|nm|s|%|NM))?$/i` (vírgula → ponto), senão string lowercase; 1.º clique asc, 2.º desc.

**Tabela "Violações" (`#iasViolTable`)** — ordem cronológica; máx. **3000 linhas** no ecrã (`MAX_VIOL_ROWS_UI`; se excedido mostra aviso "⚠️ Tabela IAS limitada a 3.000 linhas (N omitidas no ecrã). O CSV inclui todas."). Colunas:

| # | Hora (`tod` 8 chars) | Data (`DD/MM/YYYY`) | Voo (quadrado de cor + callsign clicável → `openFlightModal`) | Waypoint | IAS (kt) (vermelho) | Limite | Excesso (`'+'+excess.toFixed(0)`, vermelho) | CPA (NM) (`fmtNM1(dCpa)` — 1 decimal, vírgula) |

Vazio: "✓ Sem violações" (verde, colspan 9). Sortable.

**Exportação CSV (`exportIasCsv`)** — ficheiro `ias_compliance_lppt_YYYY-MM-DD.csv`, UTF-8 com BOM, separador `;`, CRLF:

```
Resumo IAS Compliance LPPT
Gerado;<toLocaleString pt-PT>
Raio CPA (NM);<radius com vírgula>
Tolerância (kt);<tol>
Voos ARR analisados;<flightsAnalysed>/<flightsTotal>
Passagens;<totalPasses>
Conformes;<totalComp>
Violações;<totalViol>
Taxa cumprimento (%);<pct 1 dec com vírgula ou vazio>

Por waypoint
Waypoint;Limite_kt;Passagens;Conformes;Violacoes;Cumprim_pct;IAS_med;IAS_max;IAS_min;Excesso_med;Excesso_max
<linhas: só total>0, ordenadas por violations DESC (nota: ordenação diferente da tabela UI); IAS_max vazio se 0; IAS_min vazio se Infinity; Excesso_med = (excessSum/violations).toFixed(0) ou vazio; Excesso_max = excessMax (número cru, sem '+') ou vazio>

Violações
N;Hora;Data;Voo;Waypoint;IAS_kt;Limite;Excesso;CPA_NM
<i+1;tod;date;csn;wp;ias;limit;'+'+excess.toFixed(0);fmtNM1(dCpa)>
```

**Gráficos**: a aba STAR não tem gráficos próprios.

**Consumidores secundários de `iasResults`** (para completude):
- KPIs (`_iasKpiBlock`, l.5425): cartões "Passagens analisadas" (sub: "N voos ARR"), "Conformes" (sub "Raio R NM · Tol +T kt"), "Violações", "Taxa de cumprimento" (mesmas classes de cor), e "Top 5 waypoints com mais violações" (filtro `total>0 && violations>0`, sort `violations` desc, 5 primeiros; linha: `wp`, "lim L kt", `violations`, "(p% de total)" com p = violations/total*100 1 decimal).
- "Cumprimento IAS por operador (top 10 pior)" (`_operatorComplianceBlock`, l.6369): operador = `^[A-Z]{2,3}` do callsign (maiúsculas) ou `'???'`; `violations` por operador (contagem de linhas de `violations`), `arrFlights` = legs visíveis ARR por operador; `rate=violations/arrFlights`; sort violations desc, rate desc, arrFlights desc; 10 primeiros; colunas Operador / Voos ARR / Violações / Inc./voo (`rate*100` 1 decimal + %; verde ≤10%, vermelho ≥50%).
- Alertas (l.7477): "`N` violação(ões) IAS STAR em `M` voo(s)" (M = callsigns únicos).
- Modal do voo (l.7137): secção "⚡ Velocidades STAR" com Hora / Data / Waypoint / IAS / Lim. / Excesso (`+excess.toFixed(0)kt`) para as violações desse callsign.

### 1.5 Notas e casos limite (STAR)

- **Só chegadas** (`classifyFlight==='arr'`) e só legs visíveis pelo filtro lateral (datas/blocos + tipo de voo; se o filtro de tipo for `'dep'`, `flightsAnalysed` será 0).
- `flightsTotal` conta legs visíveis de qualquer tipo; `flightsAnalysed` só ARR.
- Waypoints em `iasLimits` sem coordenadas em `allPoints()` → ignorados e reportados em `missing`.
- Lat/lon exactamente `0` são tratados como inválidos (`!la||!lo`).
- Passagem = CPA discreto dentro do raio; sem interpolação temporal nem espacial; IAS da linha do CPA.
- Uma só passagem por (leg, waypoint); o resultado por waypoint não distingue pista nem STAR (02 vs 20).
- Linhas com IAS inválida/≤0 no CPA → o waypoint não conta como passagem, mesmo que outras linhas dentro do raio tenham IAS válida (o CPA é escolhido **só pela distância**).
- `rowStep` (sub-amostragem >12 000 linhas por leg) e o orçamento de 180 ms por leg são optimizações de UI; a implementação Python deve, por omissão, varrer todas as linhas (indicar nas notas que o resultado pode diferir marginalmente do HTML em legs muito pesadas).
- `tod` é truncado a 8 caracteres (`HH:MM:SS`).

---

## 2. Aba "Velocidades APP" — Conformidade IAS (APP)

Painel `#panel-iasapp` (HTML l.697–775). Tab: `🛬 Velocidades APP` (`switchTab('iasapp')`). Ao abrir: `if(!iasAppResults) setTimeout(runIasAppCompliance,200); buildIasAppRwyButtons(); renderIasAppResults();` (l.2617). Não é auto-executada no carregamento (l.7451, comentário "evita crash").

Tem **duas sub-abas** (`switchIasAppSubTab`): `iasAppSubBtn1` "Violações por voo e pontos" (default, `on`) e `iasAppSubBtn2` "Violações por distância". Os controlos do cabeçalho (raio/tolerância/Analisar/gráficos/CSV) pertencem à sub-aba 1; a sub-aba 2 tem os seus próprios controlos.

### 2.1 Sub-aba 1 — "Violações por voo e pontos" (`runIasAppCompliance`, l.4369)

#### 2.1.1 Controlos

| id | Tipo | Label | Default | min/max/step |
|---|---|---|---|---|
| `iasAppRwyBtns` | botões | "Todas" / "RWY 02" / "RWY 20" (ou 17/35, 10/28) | **Todas** (`iasAppRwyFilter='ALL'`) | — filtro **de visualização**; a análise corre sempre para todas as pistas |
| `iasAppRadius` | number | "Raio CPA:" … "NM" | **1** | 0.1/10/0.1 |
| `iasAppTolerance` | number | "Tolerância +" … "kt" (UI mostra "+", mas a análise é **±**) | **0** | 0/30/1 |
| botão | "▶ Analisar" → `runIasAppCompliance()` | | | |
| botão `iasAppChartsBtn` | "📊 Análise (gráficos)" → `openIasAppCharts()` | | | |
| botão | "↓ CSV" → `exportIasAppCsv()` | | | |
| `iasAppCount` | span: "`N` voo(s) com violações[ (RWY xx)]" | | | |

Texto vazio: "Clica Analisar para ver violações IAS nas aproximações" / "Analisa automaticamente ambas as pistas — não é necessário seleccionar modo na aba Pontos". LPMA: "LPMA — Sem restrições de velocidade — O aeroporto da Madeira não tem restrições de velocidade definidas em AIP por falta de rotinas operacionais."

#### 2.1.2 Perfis de limites por modo/pista (`APP_IAS_DEFAULTS`, l.4025; `APP_POINT_ORDER`, l.4034)

```js
const APP_IAS_DEFAULTS={
  APP_02:{PESEX:180,NETVO:160,OKNIB:160,THR02:160},
  APP_20:{UPKAT:180,TOPVI:160,ROKOB:160,THR20:160},
  LPPR_APP_17:{ADNOV:180,PR741:180,PR742:180,THR17:180},
  LPPR_APP_35:{AKULU:180,PR541:180,PR542:180,THR35:180},
  LPFR_APP_10:{RUWIB:180,FR910:180,THR10:180},
  LPFR_APP_28:{GEBTI:180,FR928:180,THR28:180},
};
const APP_POINT_ORDER={   // ordem de passagem na aproximação
  APP_02:['PESEX','NETVO','OKNIB','THR02'],
  APP_20:['UPKAT','TOPVI','ROKOB','THR20'],
  LPPR_APP_17:['ADNOV','PR741','PR742','THR17'],
  LPPR_APP_35:['AKULU','PR541','PR542','THR35'],
  LPFR_APP_10:['RUWIB','FR910','THR10'],
  LPFR_APP_28:['GEBTI','FR928','THR28'],
};
getAppModesForAirport: LPPT→['APP_02','APP_20']; LPPR→['LPPR_APP_17','LPPR_APP_35']; LPFR→['LPFR_APP_10','LPFR_APP_28']; outros (LPMA)→[].
getRwyFromMode(mode): últimos dígitos do nome ('APP_02'→'02', 'LPPR_APP_17'→'17').
```

- **Estes limites são constantes (hardcoded); não existe UI de edição nem persistência para os limites APP.** Só os limites STAR são editáveis. Limite em falta → `180` (fallback `lims[pName]||180`).
- Não existem "waypoint toggles" na sub-aba 1 — todos os pontos do `APP_POINT_ORDER` do modo são sempre analisados. (Os toggles de pontos existem só na sub-aba 2, ver §2.3.)

#### 2.1.3 Algoritmo

Entradas: `radius=max(0.1, parseFloat(iasAppRadius)||1)`, `tol=max(0, parseFloat(iasAppTolerance)||0)`, `pointByName` a partir de `allPoints()` (nome maiúsculas), `legs=getFlightLegs()`.

1. Se sem voos → alert "Sem dados carregados." Se `modes` vazio (LPMA) → render mensagem e sair.
2. Contagens: para cada leg visível: `flightsTotal++`; se ARR `arrAnalysed++`.
3. Para cada `mode` em `modes`:
   - `pointOrder = APP_POINT_ORDER[mode] || POINT_GROUPS[mode] || []`; se `<2` pontos → `continue`.
   - Se **algum** ponto não existir em `pointByName` → o modo inteiro é ignorado (`continue`).
   - `lims=APP_IAS_DEFAULTS[mode]||{}`, `rwy=getRwyFromMode(mode)`.
   - Para cada leg visível e ARR:
     - Para cada `pName` em `pointOrder`: `hit=findNearestPassInRadius(leg.rows, pt, radius)` (§0.5); `lim=lims[pName]||180`.
       - Se `hit && hit.ias!=null && hit.ias>0`: `dev=hit.ias-lim; absDev=|dev|`; `ptsData.push({point,ias,limit,deviation:dev,absDeviation:absDev,dCpa:hit.d,tod,date,_epoch})`.
       - Senão: `ptsData.push({point,ias:null,limit:lim,deviation:null,absDeviation:null,dCpa:null,tod:'',date:'',_epoch:NaN})` (o ponto mantém a posição na lista).
     - **Violações**: `viol = ptsData.filter(x => x.ias!=null && !/^THR/i.test(x.point) && |x.deviation| > tol)` — **bilateral (±tol)** e **os pontos THRxx nunca contam como violação** (aparecem no detalhe mas são informativos).
     - Se `viol.length===0` → leg não entra nos resultados (só voos com ≥1 violação).
     - `detected = nº pontos com ias!=null`; `first` = ponto com menor `_epoch` finito → `date/tod/_epoch` do registo.
     - `records.push({csn,color,rwy,mode,detected,date,tod,_epoch,violCount:viol.length,maxAbsDeviation:max(viol.absDeviation),points:ptsData})`.
4. **Deduplicação pista/dia** (l.4420): agrupar `records` por chave `csn+'|'+date`. Para grupos com >1 registo (o mesmo voo apanhado em várias pistas): `maxDet=max(detected)`; descartar os registos com `detected===1 && maxDet>1` ("passagem incidental" por um único ponto). Grupos de 1 ficam. Nota: se ambos tiverem `detected>=2` ou ambos `detected==1`, ficam os dois.
5. `filtered.sort((a,b)=>(a._epoch||0)-(b._epoch||0))`.
6. `iasAppResults={radius,tol,records:filtered,flightsTotal,arrAnalysed,generatedAt}`; `iasAppSelectedSet=new Set(filtered.length?[0]:[])` (o 1.º registo fica pré-seleccionado); `iasAppSortKey='time'; iasAppSortDir='asc'`.

**Definição de violação APP (sub-aba 1)**: `|IAS_CPA − limite| > tolerância`, em pontos não-THR. Acima **ou abaixo** do limite conta.

#### 2.1.4 Saídas

**Barra de resumo (`#iasAppSummary`)**: "Pistas: `RWY 02 + RWY 20`" (ou "RWY xx" se filtrado), "Voos ARR analisados: `arrAnalysed`/`flightsTotal`", "Raio: R NM", "Tolerância: ±T kt", "Actualizado: HH:MM:SS".

**Filtro de pista** (`iasAppRwyFilter`): `'ALL'` ou `'02'`/`'20'`… — filtra `records` por `r.rwy` apenas na visualização/contagem.

**Tabela "Violações por voo (ordem temporal)" (`#iasAppViolTable`)** — linhas clicáveis (toggle selecção multi, `iasAppSelectedSet`; linha seleccionada com fundo `rgba(0,200,255,.08)`). Colunas:

| # (posição após sort) | Hora | Data | Voo (cor + callsign clicável → modal do voo) | Pista ("RWY xx") | Violações (`violCount`, vermelho) | Desvio máx (`Math.round(maxAbsDeviation)` + " kt", vermelho) |

Ordenação programática (`getIasAppSortedRecords`, `toggleIasAppSort`): chaves `'time'` (`_epoch`), `'viol'` (`violCount`), `'max'` (`maxAbsDeviation`); default `time asc`; ao mudar de chave começa em `desc`; mesma chave alterna. Também é aplicado `activateSortable` genérico aos cabeçalhos (sort por texto). Vazio: "✓ Sem violações" (colspan 7).

**Tabela "Detalhe do voo seleccionado" (`#iasAppDetailTable`)** — uma linha por registo seleccionado (índices ordenados asc). Colunas: `Hora | Data | Voo | Pista | PONTO1 | IAS1 | LIMITE | DESVIO | PONTO2 | IAS2 | LIMITE | DESVIO | PONTO3 | IAS3 | LIMITE | DESVIO | PONTO4 | IAS4 | LIMITE | DESVIO` (sempre 4 slots; LPFR com 3 pontos → 4.º slot "—"). `ias`=`Math.round` ou "—"; `lim`=`Math.round(limit)`; `dev`=`(+|-)Math.round(deviation)` ou "—"; classe `ias-bad` se `absDeviation>tol` (**inclui THR** aqui, visualmente). Sem selecção: "Selecciona um voo na tabela de violações".

**CSV (`exportIasAppCsv`)** — ficheiro `ias_app_02_20_YYYY-MM-DD.csv`, BOM, `;`, CRLF; exporta **todos** os `records` (ignora o filtro de pista):

```
Pistas;APP 02 + APP 20           (texto fixo, mesmo para LPPR/LPFR)
Raio CPA (NM);<radius>
Tolerância (kt);±<tol>
Voos ARR analisados;<arrAnalysed>/<flightsTotal>

Hora;Data;Voo;Pista;PONTO1;IAS1;LIMITE1;DESVIO1;PONTO2;IAS2;LIMITE2;DESVIO2;PONTO3;IAS3;LIMITE3;DESVIO3;PONTO4;IAS4;LIMITE4;DESVIO4
<tod;date;csn;parseInt(rwy) (ex. 2, 20);ponto;round(ias) ou '';round(lim);'+N'/'-N' ou ''...>
```

**Excel geral (folha "BLACK-LIST", `_buildExportSheets`, l.2655)**: cabeçalho `HORA,DATA,VOO,PISTA,PONTO1,IAS1,LIMITE1,DESVIO1,…,PONTO4,IAS4,LIMITE4,DESVIO4`; linhas = registos **na ordem/filtro actualmente mostrado** na tabela de violações (lê `data-idx` do DOM; se vazio, todos os records); mesmos formatos que o CSV. (Texto da ajuda: "A secção BLACK-LIST usa os voos seleccionados em Velocidades APP".)

**Consumidores secundários**: alertas ("`N` voo(s) com violações IAS na aproximação", 3 primeiros callsigns); modal do voo (secção "⚡ Velocidades APP": Pista / Waypoint / IAS / Limite / Desvio por ponto detectado, linha a vermelho se `|dev|>tol`).

#### 2.1.5 Gráficos "Análise (gráficos)" (`openIasAppCharts`, l.5255; amostras `collectIasAppChartSamples`, l.4605)

Modal `#iasAppChartModal` "📊 Análise visual — IAS na final (APP)". **Só LPPT** (modos hardcoded `APP_02`/`APP_20`, 4 pontos cada, `POINT_GROUPS[mode].slice(0,4)`).

Recolha de amostras: mesmo algoritmo da sub-aba 1 (raio/tolerância lidos dos inputs), mas **inclui todos os voos com ≥1 ponto detectado** (não só com violações); aplica a mesma deduplicação pista/dia; `buckets['APP_02|PESEX']=[ias,…]` com todas as IAS válidas (>0) por modo|ponto.

Subtítulo: `getIasAppChartsFilterCaption()` → "Ano(s): … · Dias: … · Blocos: … · N ficheiro(s) no filtro · M movimento(s) visível(is) (A ARR) · Raio CPA R NM · tolerância ±T kt (tabela de violações usa o mesmo ±)".

Um **histograma SVG por ponto** (8 cartões: RWY 02 — PESEX, NETVO, OKNIB, THR02; RWY 20 — UPKAT, TOPVI, ROKOB, THR20), 760×220 (`iasAppHistogramSvg`):
- Eixo X: `mn=max(40, floor((min−12)/5)*5)`, `mx=min(300, ceil((max+12)/5)*5)`; se `mx−mn<35` → `mx=mn+35`. Bins de **5 kt**; `nBins=ceil((mx−mn)/5)`; índice `floor((v−mn)/5)` clampado.
- Classificação de cada amostra (`_iasClassifySample`): `ias>limit+tol` → 'r' (vermelho `#ef4444`, "Acima do limite"); `ias<limit−tol` → 'y' (amarelo `#eab308`, "Abaixo do limite"); senão 'g' (accent, "Conforme"). Barras empilhadas por bin na ordem **amarelo, verde, vermelho** (de baixo para cima); altura proporcional ao máximo do total por bin.
- Linha vertical tracejada `#b91c1c` no `limit` (só se dentro de [mn,mx]).
- 5 ticks no eixo X (k/4 do span, arredondados).
- Meta: `n=N · média X kt (toFixed(0)) · mediana M kt · limite L kt · tolerância ±T kt`. Mediana: elemento central (ímpar) ou média dos dois centrais (par).
- Sem amostras: texto "Sem amostras com IAS ao CPA neste fix".
- Rodapé: "Inclui todas as passagens detectadas (não só violações). ARR nos dados actuais: N."
- Glossário (texto fixo, ver `iasAppChartsGlossaryBlock`).

Exportações do modal:
- **PPTX** (`exportIasAppChartsPptx`, PptxGenJS 16:9): slide 0 com título "IAS na final (APP) — LPPT", caption e glossário; um slide por gráfico (SVG 960×400 rasterizado a 1920×800 PNG), título "`PONTO · RWY xx`". Ficheiro `ias_app_final_YYYY-MM-DD.pptx`.
- **PNG único** (`exportIasAppChartsPng`): cabeçalho "IAS APP — Final" + caption, seguido dos 8 histogramas (800×230 → 1600×460) empilhados verticalmente com gap 24 px e margem 40 px, fundo `#e2e8f0`. Ficheiro `ias_app_final_YYYY-MM-DD.png`.

### 2.2 Sub-aba 2 — "Violações por distância" (`_computeAppDistViol`, l.4986; `renderAppDistResults`, l.5072)

**Só LPPT** (pistas `02`/`20` hardcoded; `APP_DIST_WAYPOINTS` só tem 02 e 20).

#### 2.2.1 Controlos

| id | Tipo | Label | Default |
|---|---|---|---|
| `appDistRwy02` / `appDistRwy20` | botões "PISTA: RWY 02 / RWY 20" (exclusivos) | `_appDistRwy='02'` | A análise corre só para a pista escolhida (`rwys=[_appDistRwy]`; existe caminho `'all'` no código mas sem botão). Mudar de pista re-renderiza se já houver dados **mas não recalcula** (os resultados são filtrados por `r.rwy===_appDistRwy`, logo ficam vazios até novo "Analisar"). |
| `appDistBuffer` | number "BUFFER ±" … "kt" | **4** (min 0, max 20, step 1) | `buffer=parseInt(value||'4')` |
| botão "▶ Analisar" | `computeAppDistViol()` (mostra "A calcular...", corre após 50 ms) | | |
| botão "↓ CSV" | `exportAppDistCsv()` | | |
| `appDistCount` | "N voo(s) com violações" | | |
| `appDistBtns` | **ESCALA DA FINAL — selecciona pontos de análise (12 NM → THR)**: 25 botões toggle de 12.0 a 0.0 NM em passos de 0.5 | **todos seleccionados** (`_appDistSelNm` = {0.0, 0.5, …, 12.0}) | |
| barras de segmento | 3 botões coloridos sob a escala: RWY02 `PESEX→NETVO` (11.5→8.0, azul), `NETVO→OKNIB` (7.5→4.0, âmbar), `OKNIB→THR` (3.5→0.0, vermelho); RWY20 `UPKAT→TOPVI`, `TOPVI→ROKOB`, `ROKOB→THR` (mesmos intervalos) | | Clique: se todos os passos do intervalo estão ON → desliga todos; senão liga todos. O botão 12.0 não pertence a nenhum segmento (spacer). |
| (no gráfico) `appDistChartComp` | select companhia ("Todas" + prefixos ICAO ordenados por nº de voos desc) | Todas | re-render |
| (no gráfico) `appDistChartBuf` | select buffer do gráfico: 0, ±2, ±4, ±6, ±8, ±10, ±12 kt | 4 | só afecta a cor das linhas do gráfico |
| (no gráfico) `appDistTopFilter` | select "Todos" / "Top 5 ▲ acima" / "Top 5 ▼ abaixo" | all | afecta tabela **e** gráfico |
| botão "↺ zoom" | repõe zoom/pan do gráfico | | |

**Botões da escala com nome** (`_APP_SCALE_MAP`): os waypoints ocupam o botão de 0.5 NM mais próximo ("diff ≤ 0.2 NM rule"):

```js
const APP_DIST_WAYPOINTS = {   // distâncias AIP LPPT AD 2.24.12
  '02': [ {name:'PESEX', nm:11.3, limit:180, scalePt:11.5},
          {name:'NETVO', nm:8.2,  limit:160, scalePt:8.0},
          {name:'OKNIB', nm:4.2,  limit:160, scalePt:4.0},
          {name:'THR 02',nm:0.0,  limit:160, scalePt:0.0} ],
  '20': [ {name:'UPKAT', nm:11.3, limit:180, scalePt:11.5},
          {name:'TOPVI', nm:8.2,  limit:160, scalePt:8.0},
          {name:'ROKOB', nm:3.96, limit:160, scalePt:4.0},
          {name:'THR 20',nm:0.0,  limit:160, scalePt:0.0} ],
};
APP_DIST_MAX=12.0; APP_DIST_STEP=0.5;
```
`_APP_SCALE_MAP[scalePt.toFixed(1)] = {label:'PESEX/UPKAT' (nomes únicos unidos por '/'), isNamed:true, wps:{'02':{name,actualNm,limit},'20':{…}}}`. Botões com nome: label = nome do WP da pista activa, negrito, min-width 56 px, title "`NOME — actualNm.toFixed(2) NM — lim L kt`"; os outros: label `nm.toFixed(1)`, title "`x.x NM da THR`". Botões ON: fundo accent/texto branco; OFF com nome: borda e texto accent; OFF sem nome: borda `#d7dce3`, texto `#374151`.

#### 2.2.2 Perfil de limite por distância (`getAppDistLimitAt`, l.4963)

```js
function getAppDistLimitAt(distFromThr, rwy){
  // FAF (11.3 NM): 180 kt — até TOPVI/NETVO (8.2 NM)
  // 8.2 NM: 160 kt — até 4.0 NM
  // 4.0 NM → THR: decréscimo linear de 160 kt para 135 kt
  const FAF = 11.3, TV = 8.2, FLAT_END = 4.0, THR_SPD = 135;
  if(distFromThr >= TV)  return 180;
  if(distFromThr >= FLAT_END) return 160;
  const k = distFromThr / FLAT_END;
  return Math.round(THR_SPD + k * (160 - THR_SPD));   // 135..160
}
```
Simétrico para 02 e 20 (o parâmetro `rwy` é ignorado). Valores nos 25 passos: 12.0→180, 11.5→180, 11.0→180, 10.5→180, 10.0→180, 9.5→180, 9.0→180, 8.5→180, 8.0→160 (≥TV? 8.0<8.2 → **160**), 7.5→160, 7.0→160, 6.5→160, 6.0→160, 5.5→160, 5.0→160, 4.5→160, 4.0→160, 3.5→157, 3.0→154, 2.5→151, 2.0→148, 1.5→144, 1.0→141, 0.5→138, 0.0→135.

**Mas** para os 4 botões "com nome" (11.5, 8.0, 4.0, 0.0) o limite usado é o `limit` de `APP_DIST_WAYPOINTS` (180/160/160/**160** na THR — não 135) e a distância de análise é `actualNm` (11.3/8.2/4.2 ou 3.96/0.0) em vez do valor do botão. (Existe também `getAppDistLimit`, l.4954, obsoleta e não usada.)

#### 2.2.3 Algoritmo

1. `buffer=parseInt(appDistBuffer||'4')`; `selNm = Array.from(_appDistSelNm).sort(desc)` (12.0→0.0); se vazio → "Selecciona pelo menos um ponto na escala."
2. `rwyCfg=getActiveRwy()`, `rwys=[_appDistRwy]`.
3. Para cada leg: **visibilidade** = `leg._flight.visible` apenas (respeita filtro de datas/blocos mas **ignora** o filtro ARR/DEP da sidebar); `_dbgTotal++`; `if(classifyFlight(leg.rows)!=='arr') continue`.
4. Para cada `rwyId` em `rwys`, `rwy=rwyCfg[rwyId]`:
   - Projectar todas as linhas: filtro `lat/lon` numéricos (`!isNaN`; aqui `0` é aceite) e `rowEpoch(r)>0`; `ac=approachCoords(lat,lon,rwy.thr.lat,rwy.thr.lon,rwy.brg)`; `{along,cross,ias:_iasFromRow(r),alt,t,r}`.
   - **Corredor**: manter só `along>=0 && along<=12.0 && |cross|<1.5` NM.
   - Ordenar por `along` **desc** (mais longe primeiro).
   - Se `<3` pontos → `continue`. Se o ponto mais próximo tiver `along>1.5` (não chegou perto da THR) → `continue`.
   - Para cada `nm` em `selNm`:
     - `scE=_APP_SCALE_MAP[nm.toFixed(1)]`; `analysisNm = scE&&scE.wps[rwyId] ? actualNm : nm`; `lim = scE&&scE.wps[rwyId] ? scE.wps[rwyId].limit : getAppDistLimitAt(nm,rwyId)`.
     - **Interpolação linear da IAS em `along`**: procurar o primeiro par consecutivo `(a=pts[i], b=pts[i+1])` com `a.along>=analysisNm && b.along<=analysisNm`;
       `range=a.along-b.along; k = range>0.001 ? (a.along-analysisNm)/range : 0; iasA=a.ias||0; iasB=b.ias||0;`
       `if(iasA>0&&iasB>0) iasInterp=Math.round(iasA+k*(iasB-iasA)); else if(iasA>0) iasInterp=iasA; else if(iasB>0) iasInterp=iasB;` (senão `null`). `break` no primeiro par.
     - `dev = iasInterp!=null ? iasInterp-lim : null`; `viol = dev!=null && |dev|>buffer`; `distData[nm.toFixed(1)]={ias,lim,dev,viol,analysisNm}`.
   - `_dbgProfiles++`. Se nenhum `viol` → `continue` (só voos com ≥1 violação).
   - `avgDev = Math.round(média dos dev não-nulos)` (ou null).
   - `firstRow` = linha com menor `rowEpoch>0` → `date=fmtDate(_date)`, `tod` 8 chars.
   - `results.push({csn,date,_dateRaw,tod,rwy:rwyId,distData,avgDev,comp:(csn.match(/^[A-Z]{2,3}/)||['?'])[0]})`.
5. `_appDistData={results,selNm,buffer,_dbgTotal,_dbgProfiles}`; `appDistCount="N voo(s) com violações"`.

**Definição de violação por distância**: `|IAS_interp(d) − limite(d)| > buffer` (bilateral), em qualquer ponto da escala seleccionado, **incluindo** a THR (0.0 NM, limite 160).

#### 2.2.4 Saídas

**Sem resultados**: "Sem violações encontradas com os filtros actuais." + debug "Sem violações encontradas · Pista: RWY02 · Buffer: ±4kt · Voos ARR analisados: N · Perfis construídos: M".

**Gráfico "📈 Perfil de velocidade ao longo da final"** (`buildAppDistChart`, SVG 760×220, pad l48 r16 t20 b46, zoom roda/pan arrasto):
- Dados: `res` (já filtrado por pista e Top-5) → filtrar por companhia; recalcular `viol` por ponto com o buffer do select do gráfico (`selBuf2`); aplicar Top-5 (acima: `avgDev>0` sort desc; abaixo: `avgDev<0` sort asc; 5 primeiros).
- Eixo X: posições equidistantes para cada `nm` de `selNm` (12→0 da esquerda para a direita); labels: nome do WP (rotacionado −35°, negrito) nos pontos com nome, número inteiro nos `nm` inteiros, nada nos .5 sem nome.
- Eixo Y (kt): `rawMin/rawMax` de todas as IAS dos voos + limites `getAppDistLimitAt(nm)`; `pad5=max(5,(rawMax-rawMin)*0.12)`; `yMin=max(80, round((rawMin-pad5)/5)*5)`; `yMax=min(320, round((rawMax+pad5)/5)*5)`; `nY=min(6, round((yMax-yMin)/10))` linhas de grelha.
- Linha de limite: polyline tracejada vermelha `#dc2626` com `getAppDistLimitAt(nm)` em cada `nm` (**nota**: no gráfico a THR aparece a 135 kt, embora a tabela use 160 nos pontos com nome).
- Até **100** voos (`filtered.slice(0,100)`), cada um uma polyline (pontos com `ias` válida; ≥2 pontos): cor `#b91c1c` se tem violação e o `dev` no ponto **central** da escala (`xs[floor(n/2)]`) é >0, `#2563eb` se tem violação e esse dev ≤0, `#94a3b8` sem violação; opacidade 0.55/0.20, espessura 2/1. Clique na linha → modal de dados.
- Label "kt" no canto; contador "N voo(s)".

**Tabela "Violações por distância — N voo(s) · buffer ±Bkt" ("Azul = abaixo do limite · Vermelho = acima do limite")**:
- Colunas: `CALLSIGN | DATA | HORA | PISTA | <uma por nm seleccionado: "NOME (x.xx NM)" para pontos com nome, "x.x NM" para os outros> | MÉD DEV.`
- Células de distância: `ias` interpolada; "—" se null; cor `#b91c1c` se `viol && dev>0`, `#0b5cad` se `viol && dev<=0`, `#6b7280` se não-violação; negrito se violação; title "Lim: L kt Dev: ±D kt".
- MÉD DEV.: `(+|-)avgDev+'kt'` (vermelho >0, azul <0, cinza 0, "—" null).
- Ordenação default: `|avgDev|` desc. Clique no cabeçalho (`appDistSort(ci)`): mesma coluna alterna sentido; nova coluna asc. Valores de sort: csn/date/tod/'RWY'+rwy como string (`localeCompare`), colunas de distância `ias||0`, `avgDev||0` numéricas.
- Filtros aplicados: `r.rwy===_appDistRwy`; `appDistTopFilter` (top5above: `avgDev>0` desc; top5below: `avgDev<0` asc; 5 primeiros).
- Clique na linha → modal "APP · CSN · RWYxx · data" com tabela `Ponto | Dist. (NM) | IAS (kt) | Limite (kt) | Desvio (kt) | Violação` (uma linha por `nm`; Violação: "⬆ ACIMA" / "⬇ ABAIXO" / "✓ OK"); modal tem "Exportar estes dados" e "PDF" (janela de impressão).

**CSV (`exportAppDistCsv`)** — ficheiro `APP_violacoes_distancia.csv`, BOM, `;`, CRLF; linhas = `results` filtrados por `r.rwy===_appDistRwy` (sem Top-5, sem ordenação especial):
```
Callsign;Data;Hora;Pista;<por nm: LABEL_x.xNM (ex. PESEX/UPKAT_11.5NM) ou x.xNM>;Med_Desvio_kt
<csn;date;tod;'RWY02';ias ou '';avgDev ou ''>
```
(Nota: o label dos pontos com nome no CSV é o label combinado `PESEX/UPKAT`, `NETVO/TOPVI`, `OKNIB/ROKOB`, `THR 02/THR 20` — não o da pista.)

### 2.3 Notas e casos limite (APP)

- **Pista de um voo (sub-aba 1)**: não há determinação explícita da pista; o voo é testado contra ambos os modos e cada modo gera o seu próprio registo se tiver violação; a deduplicação só remove registos com 1 único ponto detectado quando outra pista tem ≥2.
- **THR na sub-aba 1**: nunca violação (regex `/^THR/i`), mas aparece no detalhe e nos histogramas com limite 160 (LPPT) / 180 (LPPR/LPFR).
- **Tolerância**: UI diz "Tolerância +" mas a lógica é `|dev|>tol` (bilateral). O resumo mostra "±".
- **Raio 1 NM nos pontos APP**: com `cross≈−1.8 NM` para PESEX/UPKAT calculado pelo eixo (`brg` 32/212), isso não afecta a sub-aba 1 (que usa distância geodésica ao ponto), mas na sub-aba 2 a condição `|cross|<1.5` com o `brg` configurado exclui pontos reais do eixo ILS a mais de ≈9.2 NM da THR (1.5/sin(9.4°)) **se o rumo verdadeiro real for ≈22.6°**. Comportamento a replicar tal e qual (usar `brg` da tabela) — assinalar ao utilizador como possível melhoria (rumo verdadeiro 22.6°/202.6° para LPPT; 168.8°/348.8° LPPR; 100.1°/280.1° LPFR).
- Interpolação por distância usa `a.ias||0` — IAS 0/inválida num dos extremos faz cair no valor do outro extremo (sem interpolação); ambos inválidos → `null` (célula "—", não é violação).
- Linhas com `rowEpoch<=0` são excluídas da projecção (data `'??'` dá `dk=0`, mas `tod>0` ainda passa; apenas `tod=00:00:00` sem data falha).
- A sub-aba 2 ignora o filtro ARR/DEP mas usa sempre `classifyFlight==='arr'`.
- `avgDev` é a média dos desvios de **todos** os pontos seleccionados com IAS (não só os violadores).
- A pista RWY20 ROKOB é analisada a 3.96 NM (botão 4.0); OKNIB a 4.2 NM (botão 4.0); PESEX/UPKAT a 11.3 (botão 11.5); NETVO/TOPVI a 8.2 (botão 8.0).
- `_appDistSelNm` não é persistido; `iasAppRwyFilter`, selecções e resultados são repostos ao mudar de aeroporto/filtro (l.2213, 2348, 3475).
- Modal de dados e gráfico limitam-se a 100 linhas no SVG; a tabela não tem limite.
- Companhia (`comp`) = `^[A-Z]{2,3}` do callsign (case-sensitive, maiúsculas) ou `'?'`.
