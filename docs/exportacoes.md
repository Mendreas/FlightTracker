# Exportações e relatórios do FlightTracker

Inventário completo do que se consegue extrair da aplicação: cada botão de Excel, CSV, PDF, PowerPoint ou relatório, a aba onde está, o que contém e que fontes de dados mistura.

## 1. Como ler este documento

A aplicação lê quatro fontes: **Radar** (CSV do CNS: trajetórias), **NMIR** (Excel do Network Manager: plano de voo, ETOT/CTOT/ATOT, FSA/DEP, atraso ATFM), **Torre** (export A-SMGCS de Lisboa: horas reais de pista e de stand, ROT, taxi, go-arounds) e **OPDI** (dados abertos EUROCONTROL/ADS-B: eventos de voo). Em cada exportação indica-se, com as letras **R / N / T / O**, que fontes entram e em que colunas se cruzam.

Formas de sair da aplicação:

- **Excel (.xlsx):** ficheiros com uma ou mais folhas, guardados onde escolher (janela de gravação) — ou na pasta de dados, quando a app corre no navegador/iPad.
- **CSV:** só na aba Tabela (separador `;`, abre no Excel).
- **Relatório imprimível:** página HTML que abre no navegador com botão "Imprimir / PDF"; para PDF usa-se Imprimir → Guardar como PDF.
- **PDF / Excel de modal:** qualquer cartão clicável abre um modal com os registos de origem; o modal tem sempre os botões ⬇ Excel e 📄 PDF (regra geral da app).
- **PowerPoint (.pptx):** só nas velocidades da aproximação.
- Outros: `points.json` (pontos personalizados), email de novidades (HTML / .eml), guia de utilização (PDF).

Todas as horas são UTC. Todas as exportações respeitam o filtro ativo (dias, blocos, aeroporto, ✈ Só ARR/DEP), exceto o Painel, que usa o período próprio.

## 2. Quadro-resumo

| Aba / sub-aba | Botão | Formato | Fontes | Conteúdo resumido |
|---|---|---|---|---|
| Tabela | ⬇ CSV | CSV | R | Todos os movimentos do filtro |
| Final | ⬇ Excel | Excel | R | Uma linha por aterragem detetada (FAF, THR, IAS, separação) |
| Final | 📄 Relatório | HTML/PDF | R | KPIs radar: aproximações, taxa de aterragem, separações, CDO, STAR |
| Vel. STAR | ⬇ Excel | Excel | R | Cumprimento por waypoint + lista de violações |
| Vel. APP | ⬇ Excel | Excel | R | Violações por voo e ponto (até 4 pontos) |
| Vel. APP (distância) | ⬇ Excel | Excel | R | IAS por milha da final, por voo |
| Vel. APP | ⬇ PPTX | PowerPoint | R | Histogramas de IAS por fix e pista, com glossário |
| Análise Op. → FAST | ⬇ Excel | Excel | R | Geral, black-list APP, pares FAST |
| Análise Op. → Dados | ⬇ Excel | Excel | R | Pares filtrados, top 10 críticos, movimentos, companhias |
| Análise Op. → Dados | 📄 Relatório | HTML/PDF | R | Síntese executiva FAST com gráficos |
| Análise Op. → Diária | ⬇ Excel | Excel | R | Indicadores, por dia, dia da semana, companhias, callsigns, dia×hora |
| Análise Op. → Diária | 📄 Relatório | HTML/PDF | R | Movimentos e críticos por dia, padrões semanais |
| Análise Op. → RRMS | ⬇ Excel | Excel | R | Passagens no ponto 2 400 m (ar/solo) |
| Análise Op. → RRMS | 📄 Relatório | HTML/PDF | R | Ar vs solo por hora e categoria |
| Análise Op. → ROT | ⬇ Excel | Excel | R + T | ROT por movimento com torre e radar lado a lado, taxiways |
| KPIs | ⬇ Excel | Excel | R | KPIs radar e movimentos por hora |
| KPIs | ⬇ Excel PRU | Excel | R + N + T + O | Indicadores PRU + taxi por stand + ASMA |
| KPIs | 📄 Relatório | HTML/PDF | R | KPIs radar |
| KPIs | 📄 Relatório mensal | HTML/PDF | R + N + T + O | Composto: PRU, Painel, Solo, KPIs radar, Cruzamento |
| KPIs | 🧩 Relatórios… | HTML/PDF | à escolha | Composto com as secções escolhidas (botões guardados) |
| Painel | ⬇ Excel | Excel | R + N + T + O | Série diária com todas as fontes + top 10 |
| Solo | ⬇ Excel | Excel | T (+ R) | Movimentos no solo + estatísticas ROT/taxi |
| Cruzamento | ⬇ Excel | Excel | R + N + T + O | Um registo por movimento com as 4 fontes lado a lado |
| Pontos → Passagens | ⬇ Excel | Excel | R | Passagens no ponto |
| Pontos → Sequência | ⬇ Excel | Excel | R | Sequência num ponto com distâncias à frente/atrás |
| Pontos → Personalizados | ↓ points.json | JSON | — | Pontos criados pelo utilizador |
| Análise IA | ⬇ Excel / 📄 | Excel / HTML | R (resumo) | Perguntas, respostas e gráficos da sessão |
| Caixa do voo | 📄 | HTML/PDF | R + N + T + O | Relatório de um voo com todas as fontes |
| Qualquer cartão | ⬇ Excel / 📄 PDF (modal) | Excel / HTML | depende do cartão | Registos de origem do valor |
| Preferências | ✉ / ⬇ HTML / 📋 | .eml / HTML | — | Email de novidades |
| Preferências | 📘 Guia | PDF | — | Guia de utilização |
| Preferências | 🧩 Construir relatório… → Excel | Excel | R + N + T + O | Uma linha por movimento com as colunas escolhidas de todas as fontes, filtros por campo e contagens; folhas Dados, Resumo, Por dia, Por <campo>, Parâmetros |
| Preferências | 🧩 Construir relatório… → secções | HTML/PDF | R + N + T + O (conforme as secções) | Relatório por secções com aeroporto e início/fim próprios; independente do filtro ativo |

## 3. Exportações por aba (detalhe)

### 3.1 Tabela — ⬇ CSV

Fontes: **R** (com tipo/WTC vindos do NMIR). Uma linha por movimento do filtro: Data, Callsign, Tipo, WTC, Classe (ARR/DEP/LVL), Início, Fim, Alt. inicial, Alt. final, Alt. máx., Plots, Blocos. É a lista "crua" de movimentos; serve para contagens e para cruzar com outras folhas por callsign + data.

### 3.2 Final — ⬇ Excel (folha "Final")

Fontes: **R**. Uma linha por aterragem detetada: Seq, RWY, Voo, Tipo, Data, Hora_FAF, Hora_THR, Dur_FAF_THR_s, Dist_FAF_THR_NM, Sep_temporal_anterior_s (soleira a soleira, mesma pista), Alt_FAF_ft, IAS_FAF_kt, IAS_4NM_kt, IAS_THR_kt, Desvio_eixo_NM, Estabilizada (Sim/Não). Com borrego, a aterragem é a real (último cruzamento da soleira).

### 3.3 Final — 📄 Relatório (KPIs radar)

Fontes: **R**. Secções: Resumo Operacional (movimentos, ARR/DEP/LVL, dias, pico), Análise de Aproximações (aterragens, estabilizadas, IAS@FAF, tempo FAF→THR), Taxa de aterragem (rolling 60 min, pico, % capacidade), Separação temporal entre aterragens consecutivas (mediana/mín/máx, bunching, histograma), CDO < FL100 pelo radar, Cumprimento de IAS em waypoints STAR (top 5 waypoints, top 10 operadores), Movimentos por hora e por dia. É o mesmo relatório do botão 📄 Relatório da aba KPIs.

### 3.4 Vel. STAR — ⬇ Excel

Fontes: **R** (limites do AIP configurados na app). Folhas: **Por waypoint** (Waypoint, Limite_kt, Passagens, Conformes, Violacoes, Cumprim_pct, IAS_med/max/min, Excesso_med/max) e **Violações** (N, Hora, Data, Voo, Tipo, Waypoint, IAS_kt, Limite, Excesso, CPA_NM).

### 3.5 Vel. APP — ⬇ Excel, ⬇ Excel (por distância) e ⬇ PPTX

Fontes: **R**.

- **Violações APP:** Hora, Data, Voo, Tipo, Pista e, para cada um de até 4 pontos da aproximação, PONTOn, IASn, LIMITEn, DESVIOn.
- **Violações por distância:** Callsign, Data, Hora, Pista, IAS interpolada em cada milha da escala 12 NM → THR (uma coluna por ponto da escala) e Med_Desvio_kt.
- **PowerPoint "IAS na final (APP)":** um diapositivo por fix e pista com histograma de IAS (verde conforme, amarelo abaixo, vermelho acima da tolerância), n, média, mediana, limite; diapositivo de glossário.

### 3.6 Análise Op. → Separação entre chegadas (FAST) — ⬇ Excel

Fontes: **R**. Folhas: **Geral** (Hora, Data, Voo, Tipo, Altitude, IAS, Latitude, Longitude — passagens analisadas), **BLACK-LIST** (voos com violações APP: pontos, IAS, limites, desvios) e **FAST** (Hora, Data, RWY, Líder (THR), IAS líder, Seguidor, IAS seguidor, Sep (s), A/C intercalar, Call_sign, Hora DEP).

### 3.7 Análise Op. → Análise de Dados — ⬇ Excel e 📄 Relatório

Fontes: **R**. Excel: **Pares filtrados** (Pista, Data, Hora A, callsign precedente e IAS, seguidor e IAS, Sep s, Sep NM, Seq. (AA/ADA/ADDA/AD…A), DEP, Hora DEP, Seguidor à THR no DEP (s e NM)), **Top 10 críticos**, **Movimentos ARR+DEP** (Tipo, Pista, Data, Hora, Callsign, Companhia), **Resumo por companhia** (movimentos, ARR, DEP, ocorrências críticas, taxa). Relatório: Filtros, Síntese executiva, Destaques, Indicadores principais, Distribuição de separações, Pares por hora, Comparação por pista, Sequências ARR/DEP, Movimentos por hora, Taxa de ocorrências críticas, Posição do seguidor no DEP, IAS do seguidor, Top 10 pares mais apertados, Resumo por hora, Companhias.

### 3.8 Análise Op. → Análise Diária — ⬇ Excel e 📄 Relatório

Fontes: **R**. Excel: **Indicadores** (dias, movimentos, aterragens, descolagens, pares, críticos…), **Resumo por dia** (Data, Dia sem., ARR, DEP, Movimentos, Pares, Críticos), **Dia da semana** (n.º dias, movimentos totais, média/dia, críticos, taxa, datas), **Companhias**, **Callsigns comuns** (callsign, n.º dias, dias, movimentos, companhia), **Por dia e hora**. Relatório: Movimentos por dia, Ocorrências críticas por dia, Pico horário por dia, médias por dia da semana, Resumo por dia, Companhias, Callsigns comuns, dia × hora, Metodologia.

### 3.9 Análise Op. → RRMS — ⬇ Excel e 📄 Relatório

Fontes: **R**. Excel **RRMS**: Callsign, WTC, Tipo_AC, RWY, Status (ar/solo no ponto 2 400 m), Data, Hora, Alt_ft, IAS_kt, Dist_NM. Relatório por pista: No ar vs Solo no ponto 2400 m, Estatísticas por categoria, Distribuição horária, Detalhe completo.

### 3.10 Análise Op. → ROT — ⬇ Excel

Fontes: **R + T** (cruzadas por callsign, data e tipo de movimento). Folha **ROT**, uma linha por movimento: N, Mov (ARR/DEP), Pista, Data, Voo, Tipo, **Fonte** (torre + radar / torre / radar), **ROT_s** (de referência: torre quando existe), ROT_torre_s, ROT_radar_s, TWY_torre (EP de saída ou HP de entrada), Hora_RWY_VAC_ou_RWY_ENT_torre, Hora_ALDT_ou_ATOT_torre, TWY_radar (saída identificada pela rede de taxiways), Hora_evento_radar, Hora_THR_ou_1ª_amostra_radar, Hora_descolagem_radar, Posição_m_radar. É a melhor folha para comparar a medida do A-SMGCS com a estimativa radar, movimento a movimento.

### 3.11 KPIs — ⬇ Excel (radar)

Fontes: **R**. Folhas **KPI** (KPI, Valor: movimentos, picos rolling 60 min, média do período, passagens por waypoint, hora de pico, dias) e **Por hora** (Hora, Total, ARR, DEP).

### 3.12 KPIs — ⬇ Excel PRU

Fontes: **R + N + T + O** (o Excel mais completo de indicadores). Folhas:

- **KPIs PRU** (Secção, Indicador, Valor, Nota): Throughput (fonte, movimentos, dias, por dia, pico hora cheia, pico 60 min, capacidade, utilização, horas acima, go-arounds e taxa — **T**, radar se não houver torre); Taxi adicional out/in (n, médias, referência não-impedida — **T**); ASMA (n, anel NM, média/mediana/P80/máx — **R**); Pontualidade (NMIR, FSA/DEP: n, ok, %, early, n_fsa, desvio médio/mediano/P80 — **N**); Conformidade slot ATFM (n, within, % — **N**); atraso ATFM NMIR e torre (regulados, atrasados, minutos, por partida — **N** e **T**); CDO (n, cdo, %, patamares médios — **O**).
- **Taxi por stand** (Tipo, Stand, N, Adicional médio (s)) — **T**.
- **ASMA voos** (Data, Voo, RWY, Trânsito (s), Adicional (s)) — **R**.

### 3.13 KPIs — 📄 Relatório mensal e 🧩 Relatórios à medida

Fontes: conforme as secções. Relatório composto, imprimível, com as secções (o "mensal" leva PRU, Painel, Solo, KPIs radar e Cruzamento; os botões à medida levam as que escolher):

- **KPIs PRU** (R+N+T+O): grelha de indicadores, Movimentos por hora (média diária), Taxi-out adicional por stand, ASMA por setor de entrada, Desvio FSA/DEP − CTOT/ETOT (histograma).
- **Evolução diária** (R+N+T+O): Movimentos por dia (com referência), ROT mediano por dia, Taxi mediano por dia, Pontualidade e atraso ATFM por dia, Mapa de calor hora × dia da semana, Top 10 (operadores, tipos, aeroportos).
- **Ocupação de pista e taxi (A-SMGCS)** (T): chegadas, partidas, go-arounds, ROT, ROT por saída de pista e por ponto de espera, distribuição.
- **KPIs operacionais do radar** (R): o relatório 3.3.
- **Análise de dados** (R), **Análise diária** (R), **RRMS** (R): os relatórios 3.7, 3.8, 3.9.
- **Cruzamento de fontes** (R+N+T+O): cobertura de cada fonte, emparelhamentos, discrepâncias.

### 3.14 Painel — ⬇ Excel

Fontes: **R + N + T + O** (uma coluna por fonte, por dia). Folha **Painel diário**: Dia, RADAR mov./ARR/DEP/blocos (de 6), TORRE ARR/DEP, GO-AROUNDS, ROT ARR (s), ROT DEP (s), TAXI-OUT (s), TAXI-IN (s), ATFM (min) e voos (torre), NMIR DEP/ARR, PONT. n / ok (pontualidade FSA/DEP), OPDI voos. Folha **Top 10**: Grupo (Operador / Tipo / Aeroporto), Chave, Movimentos. É a folha certa para ver, dia a dia, que fontes existem e como os números de cada uma se comparam (ex.: movimentos radar vs torre).

### 3.15 Solo — ⬇ Excel

Fontes: **T** (com ligação ao movimento radar quando existe). Folha **Movimentos solo**: Data, Mov, Voo, Tipo, WTC, RWY, Stand, Taxi (sequência de taxiways), HP/EP, AOBT/AIBT, RWY_ENT/ALDT, ATOT/RWY_VAC, Taxi (s), ROT (s), ADEP/ADES, GA. Folha **ROT e taxi** (Grupo, Chave, N, Mediana, Média, P10, P90, Máx): ROT por saída de pista, por ponto de espera, por WTC, por pista; taxi por stand.

### 3.16 Cruzamento — ⬇ Excel

Fontes: **R + N + T + O** — a exportação mais "misturada": uma linha por movimento com todas as fontes lado a lado. Folhas: **Cruzamento**, **Discrepâncias** (só as linhas com sinalizações) e **Cobertura** (indicadores). Colunas: Data, Voo, Mov, Fontes (R/N/T/O presentes), Discrepâncias (TIPO≠, WTC≠, ADEP/ADES≠, Δt, GA, sem X); RADAR 1.º plot, último plot, n.º plots, alt. máx.; NMIR tipo, WTC, ADEP, ADES, origem (próprio dia / herdado); TORRE tipo, WTC, matrícula, operador, RWY, stand, ADEP/ADES, AOBT, RWY_ENT, ATOT, ALDT, RWY_VAC, AIBT, ROT (s), taxi (s), GA; OPDI id, icao24, matrícula, tipo, modelo, ADEP, ADES, entrada/saída de pista, ROT (s), TOC, TOD, último FL100, último FL50, 1.º FL50, 1.º FL100, patamares < FL100; correção registada / verificado / nota.

### 3.17 Pontos — ⬇ Excel (Passagens e Sequência) e points.json

Fontes: **R**. **Passagens** (Hora, Data, Bloco, Voo, Tipo, Dist_NM, Altitude_ft, IAS_kt, ROC_fpm, Latitude, Longitude) e **Sequência** (Seq, Hora, Data, Bloco, Voo, Dist_CPA_NM, AC_a_frente_NM, AC_atras_NM, Altitude_ft, IAS_kt). **↓ points.json** exporta os pontos personalizados (nome, lat, lon, descrição) para partilhar; **↑ points.json** importa.

### 3.18 Análise IA — ⬇ Excel e 📄

Fontes: **R** (resumo das análises enviado ao modelo). Excel com Pergunta / Resposta IA / Gráfico / Item; relatório com o histórico da sessão e os gráficos.

### 3.19 Caixa do voo — 📄 Relatório de voo

Fontes: **R + N + T + O** para um único movimento. Resumo de velocidades (APP e STAR, violações, conclusão), Final (pista, THR, FAF, IAS no FAF, estabilizada), secção **Fontes de dados** com Radar (CNS), NMIR (ADEP/ADES, ETOT/CTOT/ATOT, FSA/DEP e desvio, janela/conformidade do slot, regulação, ATFM…), Torre (stand, HP/EP, AOBT, RWY_ENT, ATOT, ALDT, RWY_VAC, AIBT, ROT, taxi, rota no solo, GA…) e OPDI (matrícula, icao24, pista, descolagem/aterragem, TOC/TOD, patamares), perfil IAS/altitude, tabelas de velocidades e todos os plots.

### 3.20 Modais dos cartões — ⬇ Excel e 📄 PDF

Fontes: as do cartão. Qualquer cartão com valor abre a lista dos registos que o originaram; os botões exportam exatamente essa lista (com as colunas visíveis). Exemplos úteis para cruzar fontes: **Go-arounds** (torre + radar: hora do borrego, aterragem real, confirmação radar), **Pontualidade** e **Conformidade do slot** (NMIR com FSA/DEP), **Movimentos de pista** (torre ou radar), **Taxi adicional** (torre), **ASMA** (radar), **CDO (OPDI)**, células do **Mapa de calor** (torre ou radar por dia), cartões de **cobertura do Cruzamento** (Radar ∩ Torre, Só OPDI, Δt…).

### 3.21 Preferências — relatório à medida, email de novidades e guia

**🧩 Construir relatório…** — janela com aeroporto, data de início e de fim próprios (o filtro das outras abas não é alterado) e dois modos:

- **Excel com os dados que escolher** — a exportação mais flexível da app: uma linha por movimento da união radar ∪ torre ∪ OPDI (NMIR ligado por callsign+dia), com as colunas marcadas nas secções Movimento, Calculados, Final/FAST (sequência AA/ADA/ADDA, separações, DEP intercalados), Radar, NMIR, Torre e OPDI (o catálogo completo de campos está no documento "Dados disponíveis"), **filtros** por qualquer campo (igual a, diferente de, um de, contém, começa por, >, ≥, <, ≤, vazio, preenchido; horas em HH:MM) e **contagens** por campo. Folhas: *Dados* (colunas escolhidas), *Resumo* (movimentos, ARR/DEP/LVL, com radar/NMIR/torre/OPDI, borregos, ROT médio, pontualidade), *Por dia* (ARR/DEP/total por data), *Por <campo>* (uma por contagem pedida: valor, ARR, DEP, LVL, total, %), *Parâmetros* (aeroporto, período, colunas, filtros, contagens, data de geração).
- **Relatório por secções** — as secções do relatório mensal (ver 3.13), título opcional, HTML → PDF.

**✉ Email de novidades** (.eml para Outlook instalado), **📋 Copiar** (Outlook na web) e **⬇ Guardar HTML**: alterações da versão e links de download. **📘 Guia de utilização (PDF)**: manual completo.

## 4. Onde se misturam as fontes

| Cruzamento | Onde | Como é feito |
|---|---|---|
| Radar ↔ NMIR | Tipo/WTC de cada movimento; Cruzamento; Painel; caixa do voo | Mesmo callsign e dia (senão registo mais recente do callsign; senão mesmo Mode S); correções da aba Cruzamento prevalecem |
| Radar ↔ Torre | ROT (Análise Op.), Solo (coluna radar), Go-arounds, Cruzamento, Painel, caixa do voo, relatório de voo | Mesmo callsign, dia e tipo de movimento, instante mais próximo (ATOT ↔ 1.º plot; ALDT ↔ último plot), até 30 min; movimentos com borrego ligam a ARR |
| Radar ↔ OPDI | Cruzamento, Só ARR/DEP (ADEP/ADES), caixa do voo | Callsign e dia; evento de pista do OPDI ↔ ATOT/ALDT |
| Torre ↔ OPDI | Cruzamento (Δt OPDI−torre, ROT OPDI vs torre) | Callsign, dia, instante de pista |
| NMIR ↔ Torre | KPIs PRU (atraso ATFM NMIR vs torre, CTOT), Painel | Por dia e callsign |
| Todas | Excel do Cruzamento; Excel do Painel; relatório mensal; relatório de voo | Lado a lado, uma linha por movimento (Cruzamento) ou por dia (Painel) |

Limites a ter presentes: a torre e o OPDI só existem para Lisboa; o OPDI tem pouca cobertura no solo; o radar vê as partidas já em corrida (ROT de partida só pela torre); o NMIR só tem voos com plano de voo IFR; sem ficheiro da torre, os movimentos de pista e os go-arounds vêm do radar.
