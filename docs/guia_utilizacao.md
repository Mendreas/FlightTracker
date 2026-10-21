# Guia de utilização do FlightTracker

NAV Portugal · GOPLIS · análise de trajetórias radar, dados da torre (A-SMGCS), NMIR e OPDI

Este guia descreve todas as funcionalidades da aplicação FlightTracker, aba a aba, os ficheiros que ela lê, os indicadores que calcula e a forma como os calcula. O último capítulo lista todos os acrónimos e termos usados na aplicação, com o respetivo significado.

## 1. O que é o FlightTracker

O FlightTracker é uma aplicação de secretária (Windows e macOS) que importa os ficheiros CSV de trajetórias radar exportados pelo CNS, os cruza com outras fontes (NMIR, export operacional da torre A-SMGCS e dados OPDI da EUROCONTROL) e calcula análises operacionais sobre os aeroportos portugueses (LPPT por omissão; também LPPR, LPFR e LPMA).

Os ficheiros são lidos uma única vez e guardados numa base de dados local (DuckDB). A partir daí, escolher dias, blocos horários, callsigns ou aeroportos é uma consulta instantânea — mesmo com meses de dados carregados. Os ficheiros de origem nunca são alterados.

### 1.1 Arquitetura, em poucas palavras

- **Janela nativa** (WebView2 no Windows, WebKit no macOS) com a interface em HTML.
- **Motor de dados** em Python, num processo separado, que fala com a interface por HTTP local (127.0.0.1). Se a janela nativa não abrir, a app corre no navegador predefinido.
- **Base de dados** DuckDB num único ficheiro: `%LOCALAPPDATA%\FlightTracker\flightplotter.duckdb` (Windows) ou `~/Library/Application Support/FlightTracker` (macOS). O registo de funcionamento fica em `app.log` na mesma pasta.
- **Modo rede local** (`--lan`): o motor responde a toda a rede local na porta 8765 e a app pode ser aberta no Safari de um iPad ou noutro PC (ver capítulo 14).

### 1.2 Instalação e atualização

- **Windows:** descarregar `FlightTracker-Setup.exe` da página de releases do GitHub (https://github.com/Mendreas/FlightTracker/releases/latest) e executar. Não precisa de direitos de administrador (instala em `%LOCALAPPDATA%\Programs\FlightTracker`). Existe também uma versão portátil em zip.
- **macOS:** descarregar o `.dmg`, arrastar o FlightTracker para Aplicações. Na primeira abertura, clicar com o botão direito → Abrir (a app não está assinada pela Apple).
- **Atualizar:** instalar a versão nova por cima. A base de dados não é tocada.
- O Chrome/Edge podem bloquear o download por o executável não estar assinado: em Transferências escolher "Manter" / "Manter mesmo assim".
- Os colegas que instalam a partir de releases recebem sempre a versão madura (ramo `main`). As versões em desenvolvimento (ramo `dev`) produzem apenas artefactos de teste no GitHub Actions.

## 2. Ficheiros que a aplicação lê

A importação faz-se com o botão **📂 Importar pasta…** (barra superior). A app percorre a pasta e todas as subpastas e reconhece cada ficheiro **pelo conteúdo** — o nome do ficheiro não tem importância. Numa única importação podem estar misturados os quatro tipos de ficheiro.

| Fonte | Formato | Como é reconhecido | O que fornece |
|---|---|---|---|
| Radar (CNS) | CSV, um por dia e bloco de 4 h | Colunas de plots radar (callsign, Mode S, tempo, lat/lon, altitude, IAS, GS, track…) | Trajetórias completas, classificação ARR/DEP/LVL, todas as análises de voo |
| NMIR | Excel (.xlsx) | Colunas Callsign / Aircraft type / ADEP / ADES / LOBD / ETOT / CTOT / ATOT… | Tipo de aeronave, WTC, origem/destino, horas previstas e reais, atraso ATFM |
| Torre (A-SMGCS / CPPM) | CSV `ALL_LPPT_AAAA-MM-DD_…` (132 colunas) | Colunas MT, CALLSIGN, RWY, ALDT, ATOT, AOBT, AIBT, RWY_ENT, RWY_VAC, HP, EP, STANDD/STANDA, TAXI_OUT/TAXI_IN, GA, ATFM_DELAY | Movimentos de pista e de solo, ROT, taxi, go-arounds, atraso ATFM |
| OPDI | CSV diário `opdi_LPPT_AAAAMMDD.csv` | Colunas flight_id, icao24, ADEP/ADES, eventos (take-off, landing, TOC/TOD, level-start, cruzamentos FL50/FL100) | Cobertura ADS-B, origem/destino, patamares abaixo de FL100 (CDO) |

- Ficheiros já importados são ignorados; ficheiros alterados são substituídos.
- O botão **⟳ Atualizar** procura só os ficheiros novos na última pasta importada.
- A importação corre em segundo plano com uma barra de progresso discreta; a app continua utilizável. Com muitos ficheiros NMIR na pasta, os movimentos são reconstruídos uma só vez no fim.
- **📊 NMIR…** importa um único Excel NMIR; **📥 Ficheiro da torre…** e **📥 OPDI…** (aba Solo / Cruzamento) importam ficheiros individuais dessas fontes.

### 2.1 Como o radar é transformado em movimentos

- Os plots são agrupados por callsign e dia. Um intervalo sem plots superior a 5 minutos separa o mesmo callsign em movimentos distintos.
- **Chegada (ARR):** a altitude desce mais de 500 ft entre o primeiro e o último plot. **Partida (DEP):** sobe mais de 500 ft. **Sobrevoo (LVL):** variação inferior a 500 ft (trânsito em nível, helicópteros, voos locais).
- Cada movimento recebe o tipo de aeronave e a WTC do NMIR (mesmo callsign no mesmo dia; se não existir, o registo mais recente do mesmo callsign; depois o mesmo código Mode S). As correções registadas na aba Cruzamento e as correções ao nível do tipo (ver 10.3) sobrepõem-se a tudo isto.
- Todas as horas da aplicação são **UTC**.

## 3. A janela principal

### 3.1 Barra superior

- Contadores globais: ficheiros, plots, movimentos e tamanho da base.
- **Aeroporto:** muda a vista (mapa, análises) para o aeroporto escolhido sem perder os dados dos outros; mostra o número de movimentos do filtro atual.
- **✈ Só ARR/DEP:** retira os movimentos que de certeza não têm origem nem destino no aeroporto escolhido (ver 3.4).
- **📂 Importar pasta…**, **⟳ Atualizar**, **📊 NMIR…**.
- O ícone da base de dados (à direita na barra superior) abre a pasta da base; o ícone sol/lua alterna entre tema claro (por omissão) e escuro; o ícone "i" abre a janela Sobre.

### 3.2 Painel esquerdo — filtro de datas

- **Mês disponível:** meses com dados. O calendário mostra cada dia com o número de ficheiros carregados.
- **Dias da semana** e **Blocos horários** (00–04, 04–08, 08–12, 12–16, 16–20, 20–24) permitem selecionar rapidamente; botões Todos dias / Nenhum dia / Todos blocos / Nenhum bloco.
- **▶ Aplicar filtro** carrega os movimentos dos dias e blocos escolhidos (todos os aeroportos). As análises são pré-calculadas em segundo plano; a mensagem "análises prontas" aparece no rodapé.
- **Pesquisa de callsign** (TAP, KLM, BAW…) e filtros **Todos / ▼ ARR / ▲ DEP / — Nível**.
- **Lista de voos:** cada linha mostra callsign, classe, tipo, n.º de plots e intervalo de tempo. A caixa de verificação mostra/esconde o voo no mapa; clicar no callsign seleciona o voo, abre o painel de detalhe e mostra só esse voo. Botões Todos / Nenhum.

### 3.3 Painel de detalhe de um voo

Abre ao clicar num voo em qualquer aba. Mostra callsign, data, classe, tipo/WTC, Mode S, n.º de plots, duração, soleira mais próxima, IAS mín/méd/máx, altitude, e um gráfico do perfil. Fecha-se no botão de fechar (✕) do canto; o mapa é redesenhado automaticamente.

### 3.4 Botão ✈ Só ARR/DEP — regras

Serve para eliminar os voos cuja origem **e** destino não são o aeroporto escolhido. As regras são as mesmas para qualquer aeroporto:

1. Se ADEP for o aeroporto escolhido → fica.
2. Se ADES for o aeroporto escolhido → fica.
3. Se não se souber o ADEP → fica.
4. Se não se souber o ADES → fica.
5. ADEP e ADES conhecidos e nenhum é o aeroporto → sai.

As fontes de conhecimento são o NMIR, o OPDI e o próprio radar: uma chegada que termina a mais de 4 NM do aeroporto e abaixo de 3 000 ft, ou uma partida que começa nessas condições, tem origem/destino noutro local (Cascais, Sintra, Montijo, helicópteros…); um sobrevoo (LVL) é retirado a não ser que tenha descido a menos de 2 NM e abaixo de 1 500 ft. Qualquer fonte que diga que o voo é do aeroporto prevalece. O facto de um voo estar ou não no NMIR não influencia, só os dados.

## 4. Aba Mapa

- Mapa Leaflet com as trajetórias do filtro atual, coloridas por classe (Chegada / Partida / Sobrevoo) ou por outra propriedade (Cor por classe).
- **Mapa de fundo:** Ruas (por omissão), satélite, claro/escuro, ou sem fundo.
- **Pontos AIP:** waypoints, FAF, soleiras (THR), DME, IAF — por grupo (Todos os pontos, STAR, APP…).
- Clicar numa trajetória seleciona o voo (fica mais grosso, abre o painel de detalhe). O botão **👁 Contexto** mostra também os outros voos a cinzento.
- A legenda no canto inferior direito indica as cores.

## 5. Aba Tabela

Lista de todos os movimentos do filtro com callsign, data, classe, tipo, WTC, Mode S, n.º de plots, primeiro/último plot, altitude e IAS. Ordenável por coluna; filtro de texto; **⬇ Excel** e **⬇ CSV** exportam a tabela.

## 6. Aba Final

Análise das aproximações finais a cada pista.

### 6.1 Deteção de aterragens

Um voo é considerado aterragem numa pista quando passa pelo **FAF virtual** (7 NM da soleira por omissão), dentro do **corredor lateral** (±2 NM do eixo) e chega à soleira abaixo da **altitude limite THR**. O eixo é calculado entre as duas soleiras da pista. As métricas FAF→THR são interpoladas entre plots.

### 6.2 Parâmetros (⚙)

Distância do FAF, largura do corredor, altitude máxima na THR, intervalo de IAS esperado no FAF, tolerância do perfil vertical (3°).

### 6.3 Cartões e gráficos

- Aterragens, Estabilizadas, IAS@FAF média, Tempo FAF→THR médio, Separação temporal média/mín./máx., Pistas, Pista mais usada.
- **Separação temporal entre aterragens consecutivas** (mesma pista, soleira a soleira): mediana, mínimo, máximo e **bunching** (pares a menos de 90 s).
- **Taxa de aterragem (rolling 60 min):** aterragens em qualquer janela de 60 min, avaliada de 5 em 5 min; pico e % da capacidade.
- **CDO (< FL100)** a partir do radar: proporção de chegadas sem patamares abaixo de FL100, patamares por aproximação, tempo em nível.
- Tabela de aterragens com todos os valores por voo; **⬇ Excel**, **📄 Relatório**.

## 7. Abas Vel. STAR e Vel. APP

### 7.1 Vel. STAR

Para cada chegada, a IAS no ponto de passagem mais próximo (**CPA**) de cada waypoint STAR, dentro do **raio CPA**, é comparada com a restrição de velocidade publicada. Violação = IAS acima do limite mais a **tolerância**. Cartões: passagens analisadas, violações, taxa de cumprimento, voos analisados, voos com violações; gráficos por waypoint e por operador (top 10 pior); **⚙ Gerir limites** edita as restrições por ponto; **⬇ PPTX** gera uma apresentação.

### 7.2 Vel. APP

- **Violações por voo e pontos:** o mesmo método para os pontos da aproximação (IAF, FAF…).
- **Violações por distância (escala da final 12 NM → THR):** IAS interpolada a cada milha náutica da soleira, por voo, comparada com a escala de limites da final. Perfil de velocidade ao longo da final.
- **Estatísticas no ponto de referência:** IAS e altitude mín/méd/máx por pista (02/20) no ponto escolhido, valores interpolados.

## 8. Aba Análise Op. (análise operacional)

### 8.1 Separação entre chegadas (FAST)

Pares de aterragens consecutivas na mesma pista (líder → seguidor) com separação entre 0 e 600 s.

- **Tipo de sequência:** AA (duas chegadas seguidas), ADA (uma partida entre elas), ADDA (duas partidas), AD…A (três ou mais).
- Para cada par: separação temporal, IAS do seguidor quando o líder cruza a soleira, distância do seguidor à soleira no instante da descolagem intercalada.
- Cartões: pares analisados, pares globais, passagens THR, críticos com/sem DEP, hora mais crítica, hora mais movimentada. Gráfico separação vs distância; top 10 situações mais críticas; top 10 companhias por taxa de ocorrências críticas. Botões **↔ Entre limite e 240 s** e **A/C intercalar** filtram os pares.

### 8.2 Análise de Dados

Resumo operacional (movimentos, ARR/DEP/LVL, dias, hora de pico, período, amostras, ficheiros), movimentos por hora e por dia, movimentos por companhia (top 15), callsigns comuns aos dias, tabela cruzada dia × hora.

### 8.3 Análise Diária

Por dia: movimentos, chegadas, partidas, pico horário, pares críticos; padrões por dia da semana; companhias por dia (top 10).

### 8.4 RRMS

Passagens de partidas no ponto a 2 400 m da soleira (TWY U6 / P): "no ar" quando já descolou (altitude ≥ 50 ft), "solo" quando ainda rola; distribuição por hora. Base da análise de Reduced Runway Minimum Separation.

### 8.5 ROT

Estimativa de ocupação de pista a partir do radar (quando não há ficheiro da torre). Com ficheiro da torre, usar a aba Solo, que tem o ROT medido pelo A-SMGCS.

## 9. Aba KPIs

### 9.1 KPIs de aeroporto — estilo PRU / EUROCONTROL

Indicadores com as definições da Performance Review Unit (ansperformance.eu), para comparar com os painéis da EUROCONTROL. "Adicional" significa tempo real menos uma referência não-impedida (percentil 20 do grupo).

- **Movimentos de pista:** chegadas + partidas reais na pista. Com ficheiro da torre usa ATOT/ALDT; sem torre usa o radar.
- **Pico 60 min** e **Utilização no pico:** maior número de movimentos em qualquer janela de 60 min (passos de 5 min), dividido pela **capacidade declarada** (editável no cartão; 40 mov./h por omissão para LPPT). "h acima" = horas de relógio com mais movimentos do que a capacidade.
- **Go-arounds:** aproximações abortadas registadas pela torre (campo GA) e taxa por 1 000 aterragens.
- **Taxi-out adicional:** taxi-out real (AOBT → ATOT) menos o percentil 20 dos tempos observados para o mesmo stand e pista (só pista se houver poucos casos). Indicador PRU "additional taxi-out time".
- **Taxi-in adicional:** taxi-in real (RWY_VAC → AIBT) menos a referência por stand e pista.
- **ASMA adicional:** tempo desde a entrada no anel à volta do aeroporto até à aterragem, menos a referência (P20 por pista e setor de entrada de 45°). O PRU usa 40 NM; aqui o anel é o maior coberto pelo radar (indicado no título — 13 NM para os dados de LPPT). Mede sequenciamento, vectoração e esperas.
- **Pontualidade partida (15 min):** partidas que descolaram até 15 min depois do ETOT (ou CTOT quando regulada), segundo o NMIR. Aproximação ao OTP15 da EUROCONTROL (que usa off-block).
- **Atraso ATFM (NMIR)** e **Atraso ATFM (torre):** minutos de atraso ATFM por partida; por regulação (torre); histograma ATOT − (CTOT ou ETOT).
- **CDO (OPDI):** chegadas sem patamar abaixo de FL100 segundo os eventos level-start do OPDI.
- Gráficos: movimentos por hora (média diária), taxi adicional por stand, ASMA por setor, chegadas com mais tempo ASMA adicional.
- **⬇ Excel PRU** exporta todos os KPIs com os registos de origem.

### 9.2 KPIs radar (sub-aba)

Movimentos, pico de aterragens/descolagens (rolling 60 min), média do período, passagens por waypoint, hora de pico, dias de dados.

### 9.3 Relatórios

- **📄 Relatório mensal:** num clique, um relatório imprimível com KPIs PRU, evolução diária (Painel), ROT/taxi (Solo), KPIs radar e cruzamento de fontes.
- **🧩 Relatórios…:** relatórios à medida — escolhe as secções (pru, painel, solo, kpis, dados, diária, rrms, cross), dá um nome e fica guardado como botão na barra da aba.

## 10. Abas Painel, Solo e Cruzamento

### 10.1 Painel

Evolução diária de **toda a base de dados** (não depende do filtro de dias): movimentos, chegadas/partidas, ROT mediano, taxi mediano, atraso ATFM, pontualidade, go-arounds — com média móvel de 7 dias (tracejado) e **período de referência** (ano anterior, período anterior ou personalizado, a cinzento). **Comparação A vs B** com Δ (verde = melhorou; para ROT, taxi, ATFM e go-arounds menor é melhor). Top 10 operadores, tipos e aeroportos origem/destino (NMIR). **Qualidade / cobertura dos dados por dia:** blocos radar presentes (de 6), existência de torre/NMIR/OPDI, alertas (ROT, go-arounds, ATFM, pontualidade).

### 10.2 Solo (LPPT)

Movimentos no solo a partir do export da torre (A-SMGCS).

- **Rede de taxiways, pistas e 89 stands** de LPPT (OpenStreetMap) embebida na app — não precisa de internet. Fundo OSM por omissão.
- **Tabela à esquerda, mapa à direita**, com divisor arrastável (duplo clique repõe). Clicar num avião no mapa seleciona-o na tabela sem mexer no relógio.
- **Percurso de cada voo** reconstruído a partir da sequência TAXI_OUT / TAXI_IN e dos tempos reais (AOBT, HP, RWY_ENT, ATOT; ALDT, RWY_VAC, AIBT), sobre a rede real (caminho mais curto com preferência por taxiways).
- **Animação do dia** com relógio, velocidade e rasto; **replay ar + solo** mostra também as trajetórias radar do dia no mesmo relógio: a chegada passa do radar para o percurso no solo ao aterrar, a partida o inverso.
- **ROT e taxi (A-SMGCS):** ROT chegadas (ALDT → RWY_VAC) e partidas (RWY_ENT → ATOT), distribuições, por saída de pista / ponto de espera, por WTC e por pista; taxi-in/out por stand (15 mais usados); velocidade na saída. **⬇ Excel**.
- Cada linha da tabela tem o movimento radar correspondente (quando existe), taxi e ROT.

### 10.3 Cruzamento

Um registo por movimento com o que dizem o **radar**, o **NMIR**, a **torre** e o **OPDI**.

- Emparelhamento por callsign, dia e tipo de movimento, no instante mais próximo (até 20 min).
- Cartões de cobertura: Radar, Torre, OPDI, Radar ∩ Torre, Radar ∩ OPDI, Torre ∩ OPDI, Nas 3, Com NMIR, Só radar / Só torre / Só OPDI, Discrepâncias, Δt radar−torre, Δt OPDI−torre.
- **Discrepâncias** sinalizadas: tipo ≠, WTC ≠, ADEP/ADES ≠, desvio de tempo, go-around, fonte em falta.
- Clicar numa linha abre o **detalhe** do movimento com todas as fontes lado a lado. O ícone de lápis (✎, primeira coluna) abre a **correção**: registar o tipo/aeroporto correto ou marcar como verificado, com nota. A correção fica na base de dados e aplica-se ao movimento radar e ao NMIR; os ficheiros de origem não são alterados.
- **Correção ao nível do tipo:** ao corrigir a WTC de um tipo (ex.: CL35 → M), a correção vale para todos os movimentos desse tipo, passados e futuros.
- **⬇ Excel** com folhas Cruzamento, Discrepâncias e Cobertura; **⟳ Cruzar fontes** recalcula.

## 11. Aba Pontos

- **Passagens num ponto:** passagens de voos num ponto (AIP ou personalizado) com filtro de IAS e distância; tabela e gráficos.
- **Sequência:** distância à frente/atrás entre voos consecutivos num ponto.
- **Pontos personalizados:** criar/editar pontos próprios (nome, lat/lon); ↑/↓ points.json importa/exporta a lista.

## 12. Aba Análise IA

Envia um resumo das análises do filtro atual a um modelo de linguagem (Claude, OpenAI, Mistral, Azure, Groq) e devolve uma interpretação em texto. O fornecedor, o modelo e a chave API configuram-se em ⚙ Preferências; a chave fica apenas na base de dados local.

## 13. Cartões clicáveis, modais e exportações

**Regra geral da aplicação:** em qualquer aba ou sub-aba, qualquer cartão que mostre um valor calculado é clicável e abre um modal com a lista dos voos/registos que deram origem a esse valor. Todos os modais têm os botões **⬇ Excel** e **📄 PDF**. Os cartões que são apenas parâmetros (Raio CPA, Tolerância, capacidade declarada) não têm dados de origem e por isso não abrem modal.

Outras exportações: Excel e CSV nas tabelas; Excel PRU; PPTX nas velocidades; relatórios HTML imprimíveis (📄) que abrem no navegador para imprimir/guardar em PDF; **⬇ Guardar HTML** nas novidades.

## 14. Aceder a partir de um iPad (ou outro PC)

A aplicação não corre no iPad, mas pode ser **usada** a partir dele enquanto estiver aberta num PC da mesma rede:

1. No PC, abrir o atalho **"FlightTracker (acesso na rede local — iPad)"** do menu Iniciar (ou correr `FlightTracker.exe --lan`).
2. Abrir ⚙ Preferências → "Acesso a partir de outros dispositivos": aparece o endereço, por exemplo `http://192.168.1.23:8765`.
3. No iPad, ligado ao **mesmo Wi-Fi**, abrir esse endereço no Safari. (Pode guardar-se no ecrã inicial: Partilhar → Adicionar ao ecrã principal.)
4. Tudo o que se vê no iPad é calculado no PC; importações e relatórios acontecem no PC.

Não há autenticação — usar apenas em rede interna. Se não abrir: confirmar que o PC e o iPad estão na mesma rede, que a firewall do Windows permite o FlightTracker na porta 8765 (aceitar o pedido na primeira execução), e que a app foi iniciada com `--lan`.

## 15. Preferências (⚙)

- **Análise IA:** fornecedor, modelo, chave API, endpoint Azure.
- **Base de dados:** localização e tamanho; **🧹 Remover ficheiros que já não existem no disco**.
- **Acesso a partir de outros dispositivos:** endereço em modo rede local.
- **Guia de utilização (PDF):** este documento.
- **Histórico de versões:** novidades de cada versão; **✉ Email de novidades** abre no Outlook um rascunho com as alterações e links de download (Windows e macOS); **⬇ Guardar HTML**.
- **Sobre.**

## 16. Resolução de problemas

- **A janela não abre:** a app corre no navegador predefinido; o atalho "FlightTracker (no navegador)" faz o mesmo. Verificar `app.log` na pasta da base de dados (ícone da base, na barra superior).
- **Importação lenta:** normal com milhares de ficheiros; a app continua utilizável. Vários NMIR na mesma pasta são tratados numa só reconstrução.
- **Mapa fica em branco ou mal desenhado:** redimensionar a janela ou mudar de aba e voltar.
- **Voo com tipo/WTC errado:** corrigir na aba Cruzamento (✎) — fica guardado.
- **Movimentos a mais no aeroporto:** usar ✈ Só ARR/DEP.
- **Base corrompida ou demasiado grande:** fechar a app e apagar `flightplotter.duckdb` na pasta da base; voltar a importar.

## 17. Acrónimos e termos

| Acrónimo / termo | Significado |
|---|---|
| A-SMGCS | Advanced Surface Movement Guidance and Control System — sistema de vigilância e guiamento de movimentos no solo; origem do ficheiro da torre. |
| AA / ADA / ADDA / AD…A | Tipos de sequência FAST: duas chegadas seguidas; com uma, duas, ou três ou mais partidas intercaladas. |
| ADEP | Aerodrome of Departure — aeródromo de partida (código ICAO). |
| ADES | Aerodrome of Destination — aeródromo de destino (código ICAO). |
| ADS-B | Automatic Dependent Surveillance–Broadcast — difusão automática de posição pela aeronave; base dos dados OPDI/OpenSky. |
| AIBT | Actual In-Block Time — hora real de chegada ao stand (calços). |
| AIP | Aeronautical Information Publication — publicação de informação aeronáutica; origem dos pontos (waypoints, FAF, THR). |
| AIRAC | Aeronautical Information Regulation and Control — ciclo de 28 dias de publicação aeronáutica. |
| ALDT | Actual Landing Time — hora real de aterragem. |
| AOBT | Actual Off-Block Time — hora real de saída do stand (retirada de calços). |
| APP | Approach — aproximação; aba de velocidades na aproximação. |
| ARR | Arrival — chegada. |
| ASMA | Arrival Sequencing and Metering Area — área (anel de 40 NM no PRU) à volta do aeroporto onde se mede o tempo adicional de chegada. |
| ATC | Air Traffic Control — controlo de tráfego aéreo. |
| ATFM | Air Traffic Flow Management — gestão de fluxos de tráfego aéreo (regulações, CTOT, atrasos). |
| ATOT | Actual Take-Off Time — hora real de descolagem. |
| Bunching | Pares de aterragens consecutivas com menos de 90 s entre si. |
| Callsign (csn) | Indicativo de chamada do voo (ex.: TAP441). |
| Capacidade declarada | Número de movimentos por hora que o aeroporto declara poder processar; usada na utilização no pico. |
| CDO | Continuous Descent Operations — descida contínua sem patamares (aqui medida abaixo de FL100). |
| CNS | Communications, Navigation, Surveillance — departamento que exporta os CSV radar. |
| CPA | Closest Point of Approach — ponto da trajetória mais próximo de um waypoint. |
| CPPM | Designação interna do export operacional da torre (ficheiro A-SMGCS). |
| CSV | Comma-Separated Values — ficheiro de texto tabular. |
| CTOT | Calculated Take-Off Time — hora de descolagem atribuída pelo Network Manager a um voo regulado. |
| DEP | Departure — partida. |
| DME | Distance Measuring Equipment — equipamento de medição de distância; pontos DME no mapa. |
| DuckDB | Base de dados analítica embebida onde a app guarda os dados importados. |
| EP | Exit Point — taxiway de saída de pista na chegada (H1, H3, H4…). |
| ETA / ATA | Estimated / Actual Time of Arrival — hora prevista / real de chegada. |
| ETOT | Estimated Take-Off Time — hora prevista de descolagem (plano de voo). |
| EUROCONTROL | Organização europeia para a segurança da navegação aérea; Network Manager e PRU. |
| FAF | Final Approach Fix — ponto de início da aproximação final; o "FAF virtual" é um ponto a distância fixa da soleira usado na deteção. |
| FAST | Final Approach Spacing Tool / análise de separação entre chegadas consecutivas. |
| FL | Flight Level — nível de voo (FL100 = 10 000 ft, pressão padrão). |
| ft | Pés (feet). |
| GA | Go-around — aproximação abortada / borrego. |
| GOPLIS | Gabinete de Operações de Lisboa (NAV Portugal). |
| GS | Ground Speed — velocidade em relação ao solo. |
| H / M / L / J | Categorias de turbulência de esteira: Heavy, Medium, Light, Super (J). |
| HP | Holding Point — ponto de espera antes da pista (M5, N2, U5, S4, P). |
| IAF | Initial Approach Fix — ponto inicial da aproximação. |
| IAS | Indicated Airspeed — velocidade indicada, em nós. |
| ICAO | International Civil Aviation Organization; códigos de aeródromo de 4 letras (LPPT). |
| icao24 | Endereço Mode S de 24 bits da aeronave (hexadecimal). |
| kt | Nós (knots) — milhas náuticas por hora. |
| LAN | Local Area Network — rede local; modo `--lan`. |
| Level-off / patamar | Troço em nível durante a descida (altitude quase constante durante vários plots). |
| LOBD | Last Off-Block Date — data de off-block (NMIR). |
| LPFR / LPMA / LPPR / LPPT | Códigos ICAO de Faro, Madeira, Porto e Lisboa. |
| LVL | Sobrevoo / voo em nível (classe de movimento radar). |
| Mediana / P20 / P85 / P95 | Percentis: valor abaixo do qual estão 50 % / 20 % / 85 % / 95 % dos casos. |
| Mode S | Modo de transponder com endereço único da aeronave (24 bits). |
| MT | Movement Type — tipo de movimento no ficheiro da torre (A/D). |
| NAV Portugal | Prestador de serviços de navegação aérea de Portugal. |
| NM | Milha náutica (1 852 m). |
| NMIR | Network Manager Interactive Reporting — relatórios do Network Manager da EUROCONTROL (planos de voo, tipos, ADEP/ADES, ETOT/CTOT/ATOT). |
| Off-block / on-block | Saída do stand (início do taxi-out) / chegada ao stand (fim do taxi-in). |
| OPDI | Open Performance Data Initiative — dados abertos de desempenho da EUROCONTROL (voos e eventos a partir de ADS-B OpenSky). |
| OpenSky | Rede de recetores ADS-B de acesso aberto. |
| OSM | OpenStreetMap — mapa aberto; fonte da rede de taxiways e stands. |
| OTP15 | On-Time Performance 15 min — pontualidade a 15 minutos (indicador EUROCONTROL). |
| P20 | Percentil 20 — referência "não-impedida" usada pelo PRU para os tempos adicionais. |
| Plot | Posição radar individual (um registo do CSV). |
| PPTX | Ficheiro PowerPoint. |
| PRU | Performance Review Unit da EUROCONTROL (ansperformance.eu). |
| Referência (período) | Intervalo de comparação no Painel (ano anterior, período anterior, personalizado). |
| ROT | Runway Occupancy Time — tempo de ocupação de pista (chegada: ALDT → RWY_VAC; partida: RWY_ENT → ATOT). |
| RRMS | Reduced Runway Minimum Separation — separação mínima reduzida na pista; análise no ponto a 2 400 m. |
| RWY | Runway — pista (02/20 em LPPT). |
| RWY_ENT / RWY_VAC | Entrada na pista / saída da pista (hora, no ficheiro da torre). |
| SID / STAR | Standard Instrument Departure / Standard Terminal Arrival Route — rotas padrão de partida / chegada. |
| Stand (STANDD / STANDA) | Posição de estacionamento de partida / chegada. |
| Taxi-in / Taxi-out | Tempo de rolagem da saída de pista ao stand / do stand à descolagem. |
| TAXI_IN / TAXI_OUT | Sequência de taxiways percorridos (ficheiro da torre). |
| THR | Threshold — soleira da pista. |
| TOC / TOD | Top of Climb / Top of Descent — fim da subida / início da descida (eventos OPDI). |
| Track | Rumo verdadeiro da trajetória, em graus. |
| TWY | Taxiway — caminho de circulação. |
| UTC | Tempo Universal Coordenado — todas as horas da app. |
| WebView2 | Componente do Windows (motor Edge) que mostra a interface da app. |
| WTC | Wake Turbulence Category — categoria de turbulência de esteira (L/M/H/J). |
| Δt | Diferença de tempo entre duas fontes para o mesmo evento. |
