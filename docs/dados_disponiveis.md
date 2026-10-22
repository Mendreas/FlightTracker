# Compilação de todos os dados disponíveis no FlightTracker

Dicionário de dados completo: todos os campos que a aplicação lê dos ficheiros de origem, campo a campo, mais todos os campos que a aplicação calcula a partir deles. É o complemento do documento "Exportações e relatórios" (que diz **onde** sair cada dado); este diz **o que existe**, de onde vem e com que outro dado se pode cruzar.

## 1. As quatro fontes, em resumo

| Fonte | Ficheiro de origem | O que é | Cobertura |
|---|---|---|---|
| **Radar (R)** | CSV do CNS (um por bloco horário, por aeroporto) | Plots brutos do radar/ADS-B (posição, altitude, velocidade), agregados pela app em "movimentos" (um ARR ou DEP por avião) | Todos os aeroportos com radar importado |
| **NMIR (N)** | Excel do Network Manager (Eurocontrol), ficheiro mensal tipo `LPPT_2026.xlsx` | Plano de voo e dados ATFM: tipo de avião, ADEP/ADES, ETOT/CTOT/ATOT, FSA/DEP, atraso ATFM, regulação, janela e conformidade de slot | Só tráfego IFR com plano de voo; todos os aeroportos |
| **Torre (T)** | Export A-SMGCS da torre de Lisboa (`ALL_LPPT_AAAA-MM-DD_*.csv`) | Horas reais de pista e de stand, rota no solo, ROT medido, go-around, rejeição de descolagem (RTO) | Só Lisboa (LPPT); só os dias com ficheiro importado |
| **OPDI (O)** | CSV de eventos do OPDI (dados abertos Eurocontrol/ADS-B), `opdi_LPPT_AAAAMMDD.csv` | Eventos de voo (entrada/saída de pista, descolagem/aterragem, TOC/TOD, travessias de nível) | Cobertura incompleta no solo; qualquer aeroporto |

Nas tabelas abaixo, a coluna **Fonte** usa R / N / T / O. Todas as horas armazenadas são UTC.

## 2. Radar — plots brutos (tabela interna `points`)

Um registo por plot (posição instantânea). É a matéria-prima de tudo o resto do radar.

| Campo | Tipo | Descrição |
|---|---|---|
| csn | texto | Indicativo de chamada (callsign) tal como veio no CSV |
| tod | texto | Hora do dia (HH:MM:SS,ms) tal como veio no CSV |
| tod_sec | número | A mesma hora, em segundos desde as 00:00 UTC (usada em todos os cálculos) |
| lat / lon | número | Posição (graus decimais) |
| alt | número (ft) | Altitude — Modo C ou altitude báric., a que vier |
| tas / ias | número (kt) | Velocidade verdadeira / indicada |
| roc | número (ft/min) | Taxa de subida/descida |
| gs | número (kt) | Velocidade em relação ao solo |
| modes | texto | Endereço Modo S (ICAO24) |
| modea | texto | Código do transponder (Modo A / squawk) |
| trknr | texto | Número de pista de radar (track number) |
| airport / date / block | texto | Aeroporto, dia (AAMMDD) e bloco horário do ficheiro de origem |

## 3. Radar — movimentos (tabela interna `flights`, derivada dos plots)

Um registo por movimento (um avião, uma perna ARR ou DEP). Construído agrupando plots do mesmo callsign e separando-os quando há um intervalo superior a 300 s (religados até 1200 s se a aeronave esteve sempre no ar antes e depois — caso do borrego/buraco de cobertura).

| Campo | Fonte | Descrição |
|---|---|---|
| csn | R | Callsign |
| cls | R (calc.) | Classificação do movimento: `arr`, `dep` ou `lvl` (sobrevoo), pela evolução da altitude |
| n | R | Número de plots do movimento |
| t_first / t_last | R | Hora (seg. do dia) do 1.º e do último plot |
| alt_first / alt_last | R | Altitude no 1.º e no último plot |
| alt_min / alt_max | R | Altitude mínima e máxima observadas |
| actype | R / N | Tipo de aeronave — do NMIR quando há correspondência, senão inferido |
| modes | R | Endereço Modo S do movimento |
| wtc | R / N | Categoria de esteira de turbulência (L/M/H/J) |
| blocks | R | Lista dos ficheiros/blocos horários de onde vêm os plots |
| **ga** | R (calc.) | Número de borregos (go-arounds) detetados no perfil radar deste movimento |
| **ga_t** | R (calc.) | Instante (seg. do dia) do primeiro borrego detetado |

**Como se detecta o borrego (ga):** ponto baixo (< 1500 ft) a menos de 4 NM da soleira, depois de ter descido ≥ 1000 ft, seguido de uma subida ≥ 600 ft. Ver secção 7 para o cruzamento com a torre.

## 4. NMIR — plano de voo e ATFM

Um registo por callsign + dia. Todas as colunas tal como existem no Excel do Network Manager (só se grava a versão mais completa quando o mesmo voo aparece em mais do que um ficheiro).

| Campo | Coluna no Excel NMIR | Descrição |
|---|---|---|
| csn | Callsign / Call sign / CSN / Aircraft id | Indicativo de chamada |
| date | LOBD (ou EOBD/DOF/data) | Dia local do voo, convertido para AAMMDD |
| actype | Aircraft type | Tipo de aeronave (ICAO) |
| wtc | WTC / Wake | Categoria de esteira (preenchida a partir do tipo, se a coluna faltar) |
| adep | ADEP / Departure | Aeródromo de partida |
| ades | ADES / Destination | Aeródromo de destino |
| etot | ETOT | Hora estimada de descolagem |
| ctot | CTOT | Hora calculada (slot) de descolagem ATFM |
| atot | ATOT | Hora real de descolagem (reportada ao NM) |
| eta | ETA | Hora estimada de chegada |
| ata | ATA | Hora real de chegada |
| atfm_delay | ATFM Delay | Atraso ATFM atribuído (min) |
| **fsa_dep** | **FSA/DEP** | Hora da mensagem "First System Activation" de partida — referência real do Eurocontrol para pontualidade (ver secção 7) |
| fsa_dev | FSA/DEP-ETOT | Desvio FSA/DEP − ETOT (min), já calculado no próprio NMIR |
| lobt | LOBT | Hora local prevista de bloco (off-block) |
| mp_regulation | MP Regulation | Regulação ATFM que afetou o voo (se alguma) |
| dep_window | Departure Window | Janela de partida ATFM atribuída |
| dep_conformance | Departure Conformance | Resultado da conformidade com o slot: Within / Earlier / Later |
| flttyp | FLTTYP | Tipo de voo (IFR/VFR, regular/não regular, etc.) |
| diverted | Diverted | Indicação de desvio de destino |
| operator | Aircraft Operator | Companhia / operador |
| flt_uid | FLT_UID | Identificador único do voo no Network Manager |

## 5. Torre — movimentos A-SMGCS (tabela interna `ground`)

Um registo por movimento reportado pela torre de Lisboa. Guarda os campos principais tipados e a linha completa em JSON (`raw`) para relatórios à medida.

| Campo | Coluna no CSV da torre | Descrição |
|---|---|---|
| mt | MT | Tipo de movimento (ARR/DEP) |
| csn | CALLSIGN | Indicativo de chamada |
| rwy | RWY | Pista utilizada |
| actype | AC_TYPE | Tipo de aeronave |
| reg | REG | Matrícula |
| ao | AO | Operador/companhia |
| wtc | ICAO_WTC | Categoria de esteira (Heavy/Medium/Light/Super → H/M/L/J) |
| adep / ades | ADEP / ADES | Aeródromo de partida / destino |
| sid / star | SID / STAR | Procedimento de saída / chegada atribuído |
| stand_d / stand_a | STANDD / STANDA | Posição de estacionamento à partida / chegada |
| apron | APRON | Plataforma |
| taxi_out / taxi_in | TAXI_OUT / TAXI_IN | **Rota de táxi no solo** (sequência de taxiways), à saída / à entrada |
| hp / ep | HP / EP | Ponto de espera (holding point) / ponto de entrada em pista |
| aobt | AOBT | Hora real off-block (saída do stand) |
| hp_time | HP_TIME | Hora de chegada ao holding point |
| **rwy_ent** | RWY_ENT | Hora de entrada na pista (partida) — início do ROT de descolagem |
| atot | ATOT | Hora real de descolagem |
| aldt | ALDT | Hora real de aterragem (toque das rodas) |
| **rwy_vac** | RWY_VAC | Hora de saída/libertação da pista (chegada) — fim do ROT de aterragem |
| aibt | AIBT | Hora real in-block (chegada ao stand) |
| ctot | CTOT | Slot ATFM (cópia do valor usado pela torre) |
| spd_vac | SPD@RWY_VAC | Velocidade ao libertar a pista |
| **ga** | GA | Indicador de go-around reportado pela torre |
| rto | RTO | Indicador de rejeição de descolagem (rejected take-off) |
| atfm_delay | ATFM_DELAY | Atraso ATFM (cópia da torre) |
| regulation | REGULATION_NAME | Nome da regulação ATFM aplicada |
| raw | (linha completa) | Todas as colunas originais do CSV, guardadas em JSON — usadas nos relatórios/exportações "à medida" |

**ROT medido pela torre** (ver secção 7): ARR = `rwy_vac − aldt`; DEP = `atot − rwy_ent`.

## 6. OPDI — eventos de voo (tabela interna `opdi_events`)

Um registo por evento (não por voo — um voo gera vários eventos ao longo da rota). A app agrega estes eventos por `flight_id` para obter um registo por voo (ver `opdi_flights`).

| Campo | Descrição |
|---|---|
| flight_id | Identificador do voo no OPDI |
| icao24 | Endereço Modo S (igual ao `modes` do radar — é a chave de cruzamento R↔O) |
| csn | Callsign |
| adep / ades | Aeródromo de partida / destino (ICAO) |
| adep_p / ades_p | Partida/destino previstos (plano) |
| typecode | Tipo de aeronave (ICAO) |
| model | Modelo/designação comercial |
| registration | Matrícula |
| type | Tipo de evento — ver lista abaixo |
| t | Instante do evento (epoch UTC) |
| lat / lon / alt | Posição e altitude no momento do evento |
| info_ref | Referência adicional do evento (ex.: nome da pista ou taxiway) |
| at_apt | Indica se o evento ocorreu no aeroporto em análise |

**Tipos de evento (`type`) usados pela app:** `first_seen`, `last_seen`, `entry-runway`, `exit-runway`, `take-off`, `landing`, `top-of-climb`, `top-of-descent`, `first-xing-fl50`, `first-xing-fl100`, `last-xing-fl100`, `last-xing-fl50`, `level-start` (nivelamento abaixo de FL100, usado para contar CDO), `entry-taxiway`, `exit-taxiway`, `entry-parking_position`, `exit-parking_position`.

## 7. Dados calculados pela app (não vêm de nenhum ficheiro)

Estes campos não existem em nenhuma fonte — são calculados pela app ao cruzar as fontes acima. É aqui que está a maior parte do valor do cruzamento R/N/T/O.

| Dado calculado | Fontes cruzadas | Como é calculado |
|---|---|---|
| **Classificação ARR/DEP/LVL** | R | Evolução da altitude ao longo do movimento |
| **Borrego confirmado** (`db.go_arounds`) | R + T | Cruza o `ga` do radar (secção 3) com o `GA=TRUE` da torre (secção 5), por callsign + dia + proximidade horária; classifica cada caso como "torre+radar" (confirmado nas duas fontes), "só torre", "só radar" ou "sem radar" |
| **ROT torre** | T | ARR: `rwy_vac − aldt`; DEP: `atot − rwy_ent` — valor **autoritativo** quando existe |
| **ROT radar** | R | ARR: tempo entre cruzar a soleira e cruzar a marca CAT1 no solo (estimado pela posição); DEP: tempo entre a marca CAT1 e libertar a pista/ficar aerotransportado. Serve de comparação; não vê a entrada em pista de uma partida (o avião só é visível já a rolar) |
| **Taxiway de saída/entrada de pista** | R (+ T) | Identifica o ponto da rede de rolamento (OSM da pista) mais próximo do ponto onde a aeronave sai/entra na pista; cruzado com `taxi_out`/`taxi_in` da torre quando disponível |
| **Pista provável** | R (+ T) | Estimada pela posição/rumo no radar; substituída pelo valor da torre (`rwy`) quando há correspondência |
| **Pontualidade (FSA/DEP)** | N | Desvio = `fsa_dep − coalesce(ctot, etot)`; é a referência Eurocontrol (preferida a ATOT−ETOT, que a app usa só quando não há FSA/DEP) |
| **Conformidade de slot ATFM** | N | Classificação Within / Earlier / Later a partir de `dep_conformance`; agregada por regulação (`mp_regulation`) |
| **Atraso ATFM / throughput** | N (+ T) | Agregações diárias de `atfm_delay`, `regulation` |
| **Mapa de calor hora × dia da semana** | R (e T, por aeroporto) | Contagem de movimentos por combinação hora/dia da semana |
| **Final e FAST** | R | Por chegada: hora/IAS/altitude na FAF e na soleira, estabilizada, CDO; par com a chegada anterior na mesma pista (≤ 600 s): separação (s/NM), n.º de partidas intercaladas → sequência **AA / ADA / ADDA / AD…A** |
| **Separação ar / RRMS** | R | Distância/tempo entre movimentos sucessivos no ponto de 2 400 m e noutros pontos de referência |
| **Violações de velocidade (STAR/APP)** | R | Comparação da IAS/TAS de cada plot com os limites definidos por waypoint/fix |
| **Fontes do voo (`flight_sources`)** | R + N + T + O | Para um movimento, procura e devolve em conjunto o registo NMIR (com herança de tipo), o melhor registo de torre (+ todos os da torre nesse dia), e o registo OPDI — é o que a caixa de detalhe do voo mostra |

## 8. Como extrair estes dados: Preferências → 🧩 Construir relatório…

Todos os campos das secções 2 a 7 podem sair num único Excel, uma linha por movimento, em **Preferências → 🧩 Construir relatório… → Excel com os dados que escolher**: escolhe-se o aeroporto e o período, marcam-se as colunas (as secções da janela correspondem às secções deste documento: Movimento, Calculados, Radar, NMIR, Torre, OPDI), acrescentam-se filtros (ex.: ADES igual a EGLL; Tipo de aeronave um de A320, A321; ROT maior que 60) e contagens por campo (por tipo, por aeroporto, por hora, …). O ficheiro traz as folhas Dados, Resumo, Por dia, uma folha por contagem e Parâmetros.

## 9. Onde cada par de fontes se cruza (chave de ligação)

| Par | Chave de cruzamento | Observações |
|---|---|---|
| Radar ↔ NMIR | callsign + dia | NMIR só tem tráfego IFR com plano de voo |
| Radar ↔ Torre | callsign + dia + proximidade horária (±30 min) | A hora da torre é um instante absoluto (epoch); a do radar é segundos do dia — a app converte antes de comparar |
| Radar ↔ OPDI | `modes` (Mode S) = `icao24`, + dia | OPDI tem fraca cobertura no solo |
| NMIR ↔ Torre | callsign + dia | Junta plano de voo/ATFM aos tempos reais de pista/stand |
| Torre ↔ OPDI | callsign + dia | Ambas só existem para Lisboa; cobertura combinada ainda assim incompleta no solo |
| Todas (R+N+T+O) | callsign + dia (+ Mode S quando disponível) | Usado no Cruzamento, no Painel, no Excel PRU, no relatório mensal e na caixa de detalhe do voo |

## 10. Limitações a ter presentes

- **Torre e OPDI só existem para Lisboa (LPPT)** e apenas nos dias com ficheiro importado; nos outros aeroportos e dias, só há Radar (+ NMIR se o tráfego for IFR).
- **NMIR só cobre tráfego IFR** com plano de voo — sobrevoos VFR ou tráfego sem plano não aparecem.
- **O radar não vê a entrada em pista de uma descolagem** (o avião já está a rolar quando entra no campo do radar de superfície) — por isso o ROT de DEP é sempre mais fiável pela torre.
- **FSA/DEP só existe quando a coluna vem no Excel NMIR**; quando falta, a app usa ATOT−ETOT/CTOT como alternativa (menos preciso, mas disponível).
- **Um borrego só é "confirmado"** quando aparece simultaneamente no radar e na torre; um caso "só radar" pode ser um falso positivo do algoritmo, um "só torre" pode ser um evento fora do alcance do radar nesse troço.
