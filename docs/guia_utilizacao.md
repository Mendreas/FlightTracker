# Guia de utilização do FlightTracker

NAV Portugal · GOPLIS · análise de trajetórias radar, dados da torre (A-SMGCS), NMIR e OPDI

Este guia foi escrito para quem nunca usou a aplicação e não precisa de ter conhecimentos de informática nem de análise de dados. Explica, passo a passo, o que a aplicação faz, como se instala, que ficheiros aceita, o que significa cada botão, cada aba e cada número que aparece no ecrã, e como se calculam os indicadores. O capítulo final lista todos os acrónimos e termos técnicos usados, com o respetivo significado. Sempre que aparecer um termo desconhecido, consulte esse capítulo.

Convenções usadas neste guia: os nomes de botões, abas e caixas aparecem a **negrito**; nomes de ficheiros e caminhos de pastas aparecem em `letra de máquina`; "clicar" significa clicar com o botão esquerdo do rato (ou tocar, no iPad).

## 1. O que é o FlightTracker

### 1.1 Para que serve

O FlightTracker é um programa para computador (Windows e macOS) que permite **ver e analisar o tráfego aéreo real** de um aeroporto a partir de registos que já existem na NAV, mas que estão espalhados por vários ficheiros e sistemas:

- as **trajetórias radar** (a posição de cada avião, segundo a segundo, exportada pelo CNS em ficheiros CSV);
- os **planos de voo** do Network Manager da EUROCONTROL (ficheiros Excel do NMIR), que dizem de onde vem e para onde vai cada voo, que tipo de avião é e a que horas devia descolar;
- o **export operacional da torre de Lisboa** (sistema A-SMGCS), que regista com precisão a hora de aterragem, de descolagem, a saída de pista usada, o stand, o percurso no solo e os go-arounds;
- os **dados abertos de desempenho da EUROCONTROL** (OPDI), obtidos a partir de ADS-B, que dão uma visão independente de cada voo.

A aplicação junta tudo isto numa base de dados local e responde a perguntas como: quantos movimentos houve ontem entre as 08:00 e as 12:00? Que separação houve entre aterragens consecutivas? Quantas aproximações foram feitas acima da velocidade publicada? Quanto tempo ocupa a pista cada aterragem? Quanto tempo de taxi adicional tiveram as partidas da placa 1? Como se compara este mês com o mesmo mês do ano passado? Os resultados são mostrados em mapas, tabelas e gráficos, e podem ser exportados para Excel, PDF, PowerPoint ou relatórios imprimíveis.

### 1.2 Como funciona, em termos simples

Pense na aplicação como um arquivo e uma calculadora:

1. **Importar:** indica-se uma pasta com ficheiros. A aplicação lê-os uma única vez e guarda o conteúdo, já organizado, numa **base de dados** no seu computador (um único ficheiro, chamado `flightplotter.duckdb`). Os ficheiros originais ficam onde estavam e nunca são alterados.
2. **Filtrar:** escolhe-se um ou mais dias e blocos horários num calendário. Como os dados já estão organizados, isto demora milissegundos, mesmo com meses de dados.
3. **Analisar:** cada aba (Mapa, Tabela, Final, KPIs…) mostra uma análise diferente sobre os voos escolhidos.
4. **Exportar:** qualquer tabela ou cartão pode ser guardado em Excel ou PDF.

A aplicação é composta por uma **janela** (a parte que vê) e por um **motor de dados** em Python que corre em segundo plano no mesmo computador. Os dois comunicam entre si internamente; não é enviado nada para a internet (exceto se usar a aba Análise IA, que envia um resumo ao fornecedor de IA que escolher).

### 1.3 Onde ficam os ficheiros da aplicação

É importante distinguir três locais no disco:

| O quê | Windows | macOS |
|---|---|---|
| **Programa instalado** (pode apagar-se e reinstalar-se sem perder nada) | `C:\Users\<o seu nome>\AppData\Local\Programs\FlightTracker` | `/Applications/FlightTracker.app` |
| **Base de dados, registo (log), relatórios gerados** — os seus dados | `C:\Users\<o seu nome>\AppData\Local\FlightTracker` | `~/Library/Application Support/FlightTracker` |
| **Ficheiros de origem** (CSV do radar, Excel NMIR…) | onde os tiver guardado (disco, rede, pen) | idem |

Dentro da pasta de dados encontra: `flightplotter.duckdb` (a base de dados), `app.log` (o registo de funcionamento, útil quando algo corre mal), a pasta `novidades` (emails gerados) e os relatórios/exportações criados pela aplicação. A forma mais rápida de chegar a esta pasta é clicar no ícone da base de dados (o pequeno "armário") na barra superior da aplicação. Em Windows pode também escrever `%LOCALAPPDATA%\FlightTracker` na barra de endereço do Explorador de Ficheiros.

A pasta `AppData` está normalmente escondida no Windows. Se não a vir, escreva o caminho diretamente na barra de endereço do Explorador, ou ative "Itens ocultos" no menu Ver.

## 2. Instalação e atualização

### 2.1 Windows

1. Abra a página de releases: https://github.com/Mendreas/FlightTracker/releases/latest
2. Em "Assets", clique em `FlightTracker-Setup.exe` para descarregar.
3. O Chrome ou o Edge podem avisar que o ficheiro "não é frequentemente transferido" ou "pode ser perigoso". Isto acontece porque o programa não tem assinatura digital comercial, não porque tenha algum problema. Na lista de transferências, clique nos três pontos (ou na seta) junto ao ficheiro e escolha **Manter** → **Manter mesmo assim**.
4. Execute o instalador. Não precisa de ser administrador: o programa instala-se na sua pasta de utilizador. Aceite as opções por omissão e, se quiser, marque "Criar atalho no ambiente de trabalho".
5. No fim, o FlightTracker abre automaticamente. Fica também no menu Iniciar com três atalhos: **FlightTracker** (normal), **FlightTracker (no navegador)** e **FlightTracker (acesso na rede local — iPad)** (ver capítulo 15).

Existe ainda uma versão **portátil** em zip (`FlightTracker-windows-portable.zip`): descompacta-se para qualquer pasta e executa-se `FlightTracker.exe` sem instalar. A base de dados fica na mesma pasta de dados indicada em 1.3.

### 2.2 macOS

1. Descarregue o ficheiro `.dmg` da mesma página de releases.
2. Abra-o e arraste o FlightTracker para a pasta Aplicações.
3. Na primeira abertura o macOS diz que o programa é de um "programador não identificado". Clique com o botão direito no ícone → **Abrir** → **Abrir**. Só é preciso fazer isto uma vez.

### 2.3 Atualizar para uma versão nova

Instale a versão nova por cima da antiga, exatamente como na primeira instalação. A base de dados, as preferências e as correções que registou não são tocadas. O número da versão aparece junto ao nome, no canto superior esquerdo da janela, e em **⚙ Preferências → Histórico de versões** pode ler o que mudou em cada versão.

### 2.4 Versão madura e versão de desenvolvimento

O programa tem dois ramos de desenvolvimento no GitHub: `main` (versão madura, a que os colegas recebem através da página de releases) e `dev` (versão em desenvolvimento, só para testes). A página de releases mostra sempre e só a versão madura.

## 3. Os ficheiros que a aplicação lê

### 3.1 Visão geral

A aplicação aceita quatro tipos de ficheiro. Pode importá-los todos de uma vez, misturados na mesma pasta ou em subpastas:

| Fonte | Tipo de ficheiro | O que contém | Para que serve na aplicação |
|---|---|---|---|
| Radar (CNS) | CSV, um por dia e por bloco de 4 horas, por aeroporto | Uma linha por "plot": callsign, código Mode S, hora, latitude, longitude, altitude, velocidade indicada (IAS), velocidade solo (GS), rumo, razão de subida | É a base de tudo: trajetórias no mapa, classificação em chegada/partida, Final, velocidades, FAST, KPIs radar |
| NMIR | Excel (.xlsx) exportado do portal NMIR da EUROCONTROL | Uma linha por voo com plano de voo: callsign, tipo de aeronave, aeródromo de partida (ADEP) e de destino (ADES), horas previstas e reais (LOBD, ETOT, CTOT, ATOT, ETA, ATA), atraso ATFM | Dá o tipo de avião e a categoria de esteira a cada movimento radar; diz se o voo é mesmo de/para o aeroporto; pontualidade e atraso ATFM |
| Torre (A-SMGCS) | CSV com nome do género `ALL_LPPT_2026-03-01_….csv` (132 colunas) | Um registo por movimento de pista em Lisboa: horas reais de off-block, descolagem, aterragem, on-block; entrada e saída de pista; ponto de espera; stand; taxiways percorridos; go-around; atraso ATFM | Aba Solo (percursos no solo, animação, ROT, tempos de taxi), KPIs PRU, Painel, Cruzamento |
| OPDI | CSV diário com nome do género `opdi_LPPT_20260301.csv` | Um registo por evento de cada voo captado por ADS-B: descolagem, aterragem, topo de subida/descida, cruzamentos de FL50/FL100, início de cada patamar | Origem/destino independente do NMIR; descida contínua (CDO); Cruzamento de fontes |

### 3.2 Como a aplicação reconhece cada ficheiro

A aplicação olha para o **conteúdo** (a primeira linha, com os nomes das colunas) para saber de que tipo é cada ficheiro:

- Ficheiro `.xlsx` → NMIR.
- CSV cuja primeira linha contém `flt_id` e `event_time` → OPDI.
- CSV cuja primeira linha contém `taxi_out` e `aldt` → torre.
- Qualquer outro CSV → radar.

Por isso, **para o NMIR, a torre e o OPDI o nome do ficheiro não tem importância**: pode ter o nome que tiver.

### 3.3 Os ficheiros do radar: o nome importa

Nos ficheiros do radar **o nome do ficheiro (ou da pasta) é essencial**, porque é nele que a aplicação vai buscar o **dia**, o **bloco horário** e, se existir, o **aeroporto** a que o ficheiro se refere. São reconhecidos três formatos de nome (os mesmos da versão anterior da aplicação):

| Formato | Exemplo | Como é lido |
|---|---|---|
| `AAAA_AAMMDD_HH-HH.csv` | `LPPT_260415_04-08.csv` | aeroporto LPPT, dia 15/04/2026, bloco 04–08 |
| `AAAA_AAAA-MM-DD_HH-HH.csv` | `LPFR_2026-03-01_00-04.csv` | aeroporto LPFR, dia 01/03/2026, bloco 00–04 |
| nome solto com data e bloco | `radar 2026-03-01 export 00-04.csv` | dia 01/03/2026, bloco 00–04 |

Regras práticas:

- Se o nome do ficheiro não tiver data e bloco, a aplicação tenta o nome da **pasta** onde ele está (e depois da pasta acima, e assim sucessivamente). Pode portanto ter uma pasta `LPPT_260415_04-08` com um ficheiro `export.csv` dentro.
- Se não encontrar data em lado nenhum, o ficheiro é importado com data "??" e não aparece no calendário — fica inutilizável. Renomeie-o e importe de novo.
- O **aeroporto** é lido das quatro letras `LPxx` que apareçam no nome (LPPT, LPPR, LPFR, LPMA). Se não aparecer nenhuma, a aplicação determina o aeroporto pela posição dos plots.
- O bloco horário tem de ser um dos seis blocos de 4 horas: 00-04, 04-08, 08-12, 12-16, 16-20, 20-24.
- Os CSV do radar podem vir com ou sem linha de cabeçalho; se não a tiverem, a aplicação assume a ordem de colunas habitual do CNS.

### 3.4 O que a aplicação faz com os plots do radar

Um ficheiro do radar tem dezenas de milhar de linhas; cada linha é uma posição de um avião num instante. A aplicação transforma essas linhas em **movimentos** (um movimento = um voo a chegar, a partir ou a sobrevoar), da seguinte forma:

1. Agrupa as linhas por **callsign** (o indicativo do voo, por exemplo TAP441) e por dia.
2. Se o mesmo callsign tiver um intervalo sem plots **superior a 5 minutos**, considera que são dois movimentos distintos (por exemplo o mesmo avião que aterra de manhã e descola à tarde).
3. Classifica cada movimento pela variação de altitude entre o primeiro e o último plot: **Chegada (ARR)** se desceu mais de 500 ft; **Partida (DEP)** se subiu mais de 500 ft; **Sobrevoo (LVL)** se variou menos de 500 ft (trânsito em nível, helicópteros, voos locais).
4. Procura o **tipo de aeronave** e a **categoria de turbulência de esteira (WTC)** no NMIR: primeiro o mesmo callsign no mesmo dia; se não existir, o registo mais recente desse callsign; se ainda não existir, o mesmo código Mode S. As correções que registar na aba Cruzamento (ver 12.4) prevalecem sobre tudo isto.
5. Guarda tudo na base de dados. Esta reconstrução acontece automaticamente no fim de cada importação.

**Todas as horas na aplicação são UTC** (hora universal), tal como nos ficheiros de origem. Em Portugal continental, no verão, a hora local é UTC+1; no inverno é igual a UTC.

### 3.5 Como obter cada ficheiro

- **Radar:** export dos CSV pelo CNS, normalmente um ficheiro por aeroporto, dia e bloco de 4 horas.
- **NMIR:** no portal NMIR da EUROCONTROL, exportar para Excel a lista de voos do aeroporto para o período pretendido. As colunas usadas são: Callsign, Aircraft type (ou ICAO type), ADEP, ADES, LOBD, ETOT, CTOT, ATOT, ETA, ATA e o atraso ATFM; as outras são ignoradas. A aplicação traz já uma base NMIR inicial com cerca de 46 000 registos.
- **Torre:** export operacional do A-SMGCS da torre de Lisboa (um ficheiro por dia ou por mês).
- **OPDI:** ficheiros diários preparados pelo GOPLIS a partir dos dados abertos da EUROCONTROL (https://www.opdi.aero). Só existem para Lisboa e só a partir de 2026.

## 4. Importar dados

### 4.1 Importar uma pasta (o método normal)

1. Clique em **📂 Importar pasta…** na barra superior.
2. Escolha a pasta onde estão os ficheiros. A aplicação percorre essa pasta **e todas as subpastas**.
3. Aparece uma mensagem com o número de ficheiros encontrados e de quantos são novos. A importação arranca de imediato, em segundo plano. Uma barra de progresso discreta aparece por cima da barra superior; **pode continuar a usar a aplicação** enquanto importa.
4. No fim aparece a mensagem "importação concluída" e o calendário passa a mostrar os dias novos.

O que acontece com cada ficheiro:

- Ficheiro **novo** → é importado.
- Ficheiro **já importado antes** (mesmo caminho, mesmo tamanho, mesma data de modificação) → é ignorado. Pode importar a mesma pasta as vezes que quiser.
- Ficheiro **alterado** (tamanho ou data diferente) → o conteúdo antigo é apagado da base e substituído pelo novo.
- Ficheiros que não sejam `.csv` nem `.xlsx`, ou cujo nome comece por `.`, `~` ou `$` (ficheiros temporários do Excel) → são ignorados.

Se a pasta tiver vários ficheiros NMIR, todos são importados e os movimentos são reconstruídos **uma só vez** no fim (e não por cada ficheiro), para a importação ser rápida.

### 4.2 Botão ⟳ Atualizar

Repete a importação da **última pasta** que importou, procurando só os ficheiros novos ou alterados. É o botão a usar no dia a dia quando o CNS acrescenta os ficheiros de mais um dia à mesma pasta de rede.

### 4.3 Botão 📊 NMIR…

Importa **um único** ficheiro Excel do NMIR, escolhido numa janela de ficheiros. Serve quando se recebe um Excel novo sem o pôr na pasta dos CSV. Os registos são adicionados à base NMIR; um registo com o mesmo callsign e a mesma data substitui o anterior. Depois da importação, os movimentos radar já carregados são atualizados com os tipos de aeronave novos.

### 4.4 Botões 📥 Ficheiro da torre… e 📥 OPDI…

Nas abas **Solo** e **Cruzamento** existem botões para importar um único ficheiro da torre ou um único ficheiro OPDI. São equivalentes a pôr o ficheiro na pasta e usar Importar pasta.

### 4.5 Quanto tempo demora

Como referência: um dia completo de Lisboa (6 ficheiros do radar, cerca de 700 000 plots) demora alguns segundos; um mês demora alguns minutos; um ano com cerca de 2 000 ficheiros pode demorar 10 a 20 minutos. A mensagem de progresso indica o ficheiro atual e o total ("ficheiro 120 de 217"). Se a mensagem parecer parada muito tempo em "a reconstruir movimentos", é normal: é a fase final, única, que demora mais com bases grandes.

### 4.6 Remover ficheiros que já não existem

Em **⚙ Preferências → Base de dados → 🧹 Remover ficheiros que já não existem no disco** apagam-se da base os registos de ficheiros que entretanto foram apagados ou movidos. Útil para libertar espaço ou depois de reorganizar a pasta de rede.

## 5. A janela principal

### 5.1 Barra superior

Da esquerda para a direita:

- **Logótipo, nome e versão** — o número de versão instalada.
- **Contadores:** número de ficheiros, de plots (posições radar), de movimentos e tamanho da base de dados.
- **Aeroporto:** lista pendente com os aeroportos que têm dados. Ao mudar, o mapa centra-se nesse aeroporto e todas as análises passam a referir-se a ele; os dados dos outros aeroportos continuam carregados. Entre parênteses aparece o número de movimentos desse aeroporto no filtro atual.
- **✈ Só ARR/DEP:** botão que liga/desliga a exclusão dos voos que não são do aeroporto escolhido (explicado em 5.5).
- **📂 Importar pasta…**, **⟳ Atualizar**, **📊 NMIR…** — ver capítulo 4.
- **Ícone da base de dados** (armário): abre a pasta de dados no Explorador de Ficheiros (onde está a base, o `app.log` e os relatórios gerados).
- **Sol / lua:** alterna entre o tema claro (por omissão) e o tema escuro.
- **ⓘ:** abre a janela "Sobre", com a versão e os créditos.

Nos ecrãs mais estreitos a barra passa para duas linhas; nada se perde.

### 5.2 Painel esquerdo: filtro de datas

Tudo o que a aplicação mostra nas abas refere-se aos dias e blocos selecionados aqui.

1. **Mês disponível:** escolha o mês. Só aparecem meses com dados.
2. **Calendário:** cada dia com dados mostra um número pequeno por baixo (quantos ficheiros do radar tem; 6 = dia completo). Os dias sem dados aparecem a cinzento. Clique num dia para o selecionar (fica azul); clique noutro para selecionar vários. Os botões **Todos dias** e **Nenhum dia** selecionam/limpam o mês inteiro.
3. **Dias da semana:** clicar em "Seg", por exemplo, seleciona todas as segundas-feiras do mês. Útil para comparar dias úteis com fins de semana.
4. **Blocos horários:** os seis blocos de 4 horas (00–04, 04–08, 08–12, 12–16, 16–20, 20–24, UTC). Os blocos a verde estão selecionados. **Todos blocos** e **Nenhum bloco**.
5. **▶ Aplicar filtro:** carrega os movimentos dos dias e blocos escolhidos, para todos os aeroportos. O rodapé mostra "a calcular análises…" e depois "análises prontas": nesse momento todas as abas já têm os resultados calculados.

Dica: para ver um só dia completo, clique no dia e certifique-se de que os seis blocos estão a verde.

### 5.3 Painel esquerdo: lista de voos

Por baixo do filtro:

- **Caixa de pesquisa** (🔍 TAP, KLM, BAW…): escreva parte de um callsign para filtrar a lista e o mapa. "TAP" mostra todos os voos da TAP; "TAP441" só esse voo.
- **Todos / ▼ ARR / ▲ DEP / — Nível:** mostra só chegadas, só partidas ou só sobrevoos.
- **Lista:** cada voo tem uma bolinha com a sua cor no mapa, o callsign, uma etiqueta ARR/DEP/LVL, o tipo de aeronave (quando conhecido), o número de plots e o intervalo de tempo (primeiro → último plot). A caixa de verificação à direita mostra/esconde o voo no mapa. **Todos / Nenhum** marcam/desmarcam todas as caixas.
- **Clicar no callsign** seleciona o voo: no mapa a trajetória fica mais grossa, os outros voos ficam escondidos (ou a cinzento, se ativar **👁 Contexto**) e abre-se o painel de detalhe.

### 5.4 Painel de detalhe de um voo

Abre-se à direita sempre que clica num voo (na lista, no mapa ou em qualquer tabela das análises). Mostra:

- Callsign, data, classe (chegada/partida/sobrevoo), tipo de aeronave e categoria de esteira, código Mode S.
- Cartões com: número de plots, duração, soleira (pista) mais próxima no fim (chegadas) ou no início (partidas), IAS mínima/média/máxima, altitude mínima/máxima.
- Um gráfico do perfil (Altitude ou IAS ao longo da distância à soleira).
- Uma tabela com todos os plots: hora (TOD), altitude, IAS, velocidade solo (GS), razão de subida (ROC) e distância à soleira.
- O botão **📄** gera um relatório imprimível deste voo. **✕** fecha o painel; o mapa reajusta-se automaticamente.

### 5.5 Botão ✈ Só ARR/DEP: o que faz e as regras exatas

Os ficheiros do radar cobrem um raio grande à volta de cada aeroporto. Por isso, num dia de Lisboa aparecem também voos de Cascais, do Montijo, de Sintra, helicópteros e aviões a sobrevoar a área. Para contagens e indicadores do aeroporto, esses voos atrapalham. O botão **✈ Só ARR/DEP** retira-os, aplicando estas regras a cada movimento (são as mesmas para qualquer aeroporto escolhido):

1. Se o aeródromo de partida (ADEP) for o aeroporto escolhido → **fica**.
2. Se o aeródromo de destino (ADES) for o aeroporto escolhido → **fica**.
3. Se não se souber o ADEP → **fica**.
4. Se não se souber o ADES → **fica**.
5. Se ADEP e ADES forem ambos conhecidos e nenhum for o aeroporto escolhido → **sai**.

Ou seja, só é retirado um voo quando há **certeza** de que não é do aeroporto. Em caso de dúvida, fica. As fontes usadas para saber ADEP/ADES são:

- o **NMIR** (plano de voo);
- o **OPDI** (ADS-B);
- o **próprio radar**: uma chegada que termina a mais de 4 NM do aeroporto e abaixo de 3 000 ft, ou uma partida que começa nessas condições, aterrou/descolou noutro sítio (Cascais, Montijo, heliportos…). Um sobrevoo (LVL) é retirado a não ser que tenha descido a menos de 2 NM do aeroporto e abaixo de 1 500 ft (o que indica um toque-e-anda ou um go-around).

Se uma fonte disser que o voo é do aeroporto, o voo fica, mesmo que outra fonte diga o contrário. O facto de um voo não existir no NMIR não o retira: só os dados contam. O número de movimentos no seletor de aeroporto atualiza-se quando se liga o botão.

## 6. Aba Mapa

Mostra as trajetórias radar dos voos selecionados sobre um mapa.

- **Pontos AIP** (caixa de verificação): mostra os pontos publicados (waypoints das STAR, pontos da aproximação, FAF, soleiras THR, DME). A lista pendente ao lado escolhe o grupo de pontos (Todos os pontos, STAR, APP, …).
- **Cor por classe:** com a caixa marcada, as chegadas são azuis, as partidas laranja e os sobrevoos cinzentos (a legenda no canto inferior direito mostra as cores). Desmarcada, cada voo tem uma cor própria (a mesma da bolinha na lista).
- **Mapa de fundo:** Ruas (por omissão), OSM, Satélite ou sem fundo (só as trajetórias).
- **Navegar:** roda do rato para aproximar/afastar; arrastar para mover; botões + e −.
- **Passar o rato** sobre uma trajetória mostra o callsign, o tipo e a hora; **clicar** seleciona o voo e abre o painel de detalhe. **👁 Contexto** mantém os outros voos visíveis a cinzento enquanto um está selecionado.
- Se o mapa aparecer parcialmente em branco depois de fechar um painel ou redimensionar a janela, mude de aba e volte; a aplicação reajusta-o.

## 7. Aba Tabela

Lista todos os movimentos do filtro, um por linha, com as colunas: Data, Callsign, Tipo, WTC, Classe, Início, Fim, Alt ini, Alt fim, Alt máx, Plots, Blocos. Clique no cabeçalho de uma coluna para ordenar; clique numa linha para abrir o detalhe do voo. Os botões **⬇ Excel** e **⬇ CSV** guardam a tabela completa.

## 8. Aba Final: análise das aproximações

### 8.1 O que é

Esta aba olha para a última parte de cada chegada — a **aproximação final** — e mede como foi feita: a que velocidade, com que perfil, com que separação da aterragem anterior. É a base para avaliar estabilidade das aproximações e capacidade de pista.

### 8.2 Como se deteta uma aterragem

Um movimento é considerado aterragem numa pista quando a trajetória:

1. passa pelo **FAF virtual** — um ponto no eixo da pista a uma distância fixa da soleira (7 NM por omissão; não é o FAF publicado, é um ponto de referência da análise);
2. dentro do **corredor lateral** (± 2 NM do eixo, por omissão);
3. e chega à **soleira (THR)** abaixo de uma altitude máxima (**Alt THR ≤**, por omissão 1 000 ft).

O eixo da pista é calculado entre as coordenadas das duas soleiras. Os valores "no FAF" e "na THR" são **interpolados**: como o radar não regista exatamente nesses pontos, a aplicação calcula o valor entre os dois plots que os enquadram.

### 8.3 Parâmetros (botão ⚙)

- **Pista:** Ambas, ou só uma (02 / 20 em Lisboa).
- **FAF** (NM): distância do FAF virtual à soleira.
- **Corredor ±** (NM): meia-largura do corredor lateral.
- **Alt THR ≤** (ft): altitude máxima ao cruzar a soleira para contar como aterragem.
- Intervalo de IAS esperado no FAF e tolerância do perfil vertical (3°) para considerar uma aproximação **estabilizada**.

Depois de alterar, clique em **▶ Analisar** / **Atualizar análise**.

### 8.4 Cartões (clicáveis)

- **Aterragens:** quantas aterragens foram detetadas.
- **Estabilizadas:** quantas cumpriram os três critérios (lateral, vertical ~3°, IAS no FAF dentro do intervalo).
- **IAS@FAF méd.:** velocidade indicada média ao passar o FAF virtual, em nós.
- **Tempo FAF→THR méd.:** tempo médio entre o FAF virtual e a soleira.
- **Sep. temporal méd. / mín. / máx.:** intervalo entre aterragens consecutivas **na mesma pista**, medido de soleira a soleira.
- **Pistas / Pista mais usada.**

### 8.5 Gráficos e tabelas

- **Separação temporal entre aterragens consecutivas:** mediana, mínimo, máximo e **bunching** (número de pares a menos de 90 s — aproximações muito comprimidas). O histograma mostra a distribuição.
- **Taxa de aterragem (rolling 60 min):** quantas aterragens houve em qualquer janela de 60 minutos, avaliada de 5 em 5 minutos; o **pico** é a janela mais carregada e **% capacidade** compara-o com a capacidade de referência.
- **CDO (< FL100), a partir do radar:** percentagem de chegadas sem patamares abaixo de FL100, número médio de patamares e tempo em nível por aproximação. Um patamar (level-off) é um troço em que a altitude quase não varia durante vários plots.
- **Tabela de aterragens:** uma linha por aterragem com todos os valores (pista, hora na THR, IAS no FAF, tempo FAF→THR, separação da anterior, estabilizada sim/não). Clique numa linha para ver o voo.
- **⬇ Excel** e **📄 Relatório** (imprimível).

## 9. Abas Vel. STAR e Vel. APP: cumprimento de velocidades

### 9.1 Vel. STAR (velocidades nas chegadas padrão)

As STAR (rotas padrão de chegada) publicadas no AIP têm restrições de velocidade em certos waypoints (por exemplo "máx. 250 kt"). Esta aba verifica se as chegadas as cumpriram:

1. Para cada chegada e cada waypoint com restrição, procura-se o ponto da trajetória mais próximo do waypoint (**CPA**, closest point of approach), desde que esteja dentro do **Raio CPA** (NM).
2. A IAS nesse ponto é comparada com a restrição publicada. É **violação** se estiver acima do limite mais a **Tolerância** (kt).

Cartões: **Passagens analisadas**, **Violações**, **Taxa de cumprimento**, **Voos ARR analisados**, **Voos com violações**, e ainda **Conformes** / **Abaixo do limite**. Gráficos por waypoint e **Cumprimento IAS por operador (top 10 pior)** — operador = três primeiras letras do callsign; "inc./voo" = violações por chegada. **⚙ Gerir limites** permite editar as restrições de cada ponto (ficam guardadas). **⬇ PPTX** gera uma apresentação PowerPoint com os gráficos. **Waypoints sem coordenadas** lista pontos com restrição mas sem coordenadas, que não são analisados.

### 9.2 Vel. APP (velocidades na aproximação)

Dois modos, escolhidos pelos botões no topo:

- **Violações por voo e pontos:** o mesmo método da STAR, aplicado aos pontos da aproximação (IAF, FAF, …) com **Raio CPA** e **Tolerância ±**.
- **Violações por distância (escala da final 12 NM → THR):** em vez de pontos, usa uma escala de limites de velocidade por distância à soleira (por exemplo 220 kt a 12 NM, 180 kt a 8 NM, 160 kt a 4 NM). Para cada voo, a IAS é interpolada a cada milha náutica e comparada com o limite dessa distância, com um **Buffer ±**. O gráfico **Perfil de velocidade ao longo da final** desenha todos os voos sobre a escala.
- **Estatísticas no ponto de referência:** IAS e altitude mínima/média/máxima das passagens por pista (RWY 02 / RWY 20) no ponto escolhido, sempre interpoladas.

## 10. Aba Análise Op. (análise operacional)

Tem cinco sub-abas, escolhidas pelos botões no topo.

### 10.1 Separação entre chegadas (FAST)

Analisa os **pares de aterragens consecutivas na mesma pista** — o avião que aterra primeiro é o **líder**, o seguinte é o **seguidor** — com separação entre 0 e 600 s. Para cada par calcula:

- a **separação temporal** (soleira a soleira);
- o **tipo de sequência**: **AA** (duas chegadas seguidas, sem partida entre elas), **ADA** (uma partida descolou entre as duas), **ADDA** (duas partidas), **AD…A** (três ou mais);
- a **IAS do seguidor** no instante em que o líder cruza a soleira;
- a **distância do seguidor à soleira** no instante de cada descolagem intercalada.

Filtros: **Separação THR** e **Limite crítico** (240, 200, 165, 140, 120 s — um par abaixo deste limite é "crítico"); Data, Hora, Pista; Tipo (tudo / com DEP entre aterragens / sem DEP); Sequência; **Seguidor no DEP até** (NM); Mostrar (todos / só abaixo do limite); **Categoria rasto** (M + H, M, H, Todas). Os botões **↔ Entre limite e 240 s** e **A/C intercalar** são atalhos para os filtros mais usados.

Cartões: pares analisados, pares globais, passagens THR detetadas, críticos com DEP, críticos sem DEP, hora mais crítica, hora mais movimentada. Gráficos: separação vs distância do seguidor, ocorrências críticas por dia, top 10 situações mais críticas, top 10 companhias por taxa de ocorrências críticas. Ao clicar num par, o painel de detalhe mostra o líder e o seguidor com a sua final.

### 10.2 Análise de Dados

Um resumo "de contagem" do filtro atual: **Resumo Operacional** (movimentos, chegadas, partidas, sobrevoos, dias de dados, hora de pico, período UTC, amostras radar, ficheiros carregados), **Movimentos por hora (UTC)**, **Movimentos por dia**, **Movimentos por companhia (top 15)**, **Callsigns comuns aos dias** (voos regulares que aparecem em todos os dias selecionados) e a tabela cruzada **Resumo por dia e hora**. A lista pendente **Estatísticas** muda a tabela (Por pista, Ar/Solo, Por hora, Por categoria, Por tipo A/C, Por companhia, Top 10 callsigns).

### 10.3 Análise Diária

Uma linha por dia com movimentos, chegadas, partidas, pico horário e pares críticos; **Padrões por dia da semana** (média de movimentos e de pares críticos por dia da semana); **Companhias por dia (top 10)**. O botão **🔄 Actualizar análise diária** recalcula.

### 10.4 RRMS

Base para a análise de **Reduced Runway Minimum Separation**: olha para as partidas no ponto a **2 400 m da soleira** (ao nível das taxiways U6 / P em Lisboa) e verifica se, nesse ponto, o avião já estava **no ar** (altitude ≥ 50 ft) ou ainda **no solo**. Mostra a distribuição por hora e por pista (RWY02 / RWY20) e o total de descolagens analisadas.

### 10.5 ROT (a partir do radar)

Estimativa do tempo de ocupação de pista calculada só com o radar, para quando não existe ficheiro da torre. Quando existe ficheiro da torre, use a aba **Solo**, onde o ROT é medido diretamente pelo A-SMGCS e é muito mais exato.

## 11. Aba KPIs

### 11.1 KPIs de aeroporto no estilo PRU / EUROCONTROL

A **Performance Review Unit (PRU)** da EUROCONTROL publica indicadores de desempenho de todos os aeroportos europeus em https://ansperformance.eu. Esta secção calcula os mesmos indicadores, com as mesmas definições, para os dias selecionados, de forma a poderem comparar-se. Uma ideia-chave do PRU é o **tempo adicional**: tempo real menos um **tempo de referência "não-impedido"**, que é o **percentil 20 (P20)** dos tempos observados num grupo semelhante (por exemplo, mesmo stand e mesma pista). O P20 é o valor abaixo do qual estão os 20 % de casos mais rápidos — representa "o que o voo demoraria se nada o atrasasse".

Cartões (todos clicáveis):

- **Movimentos de pista:** chegadas + partidas reais. Com ficheiro da torre usa as horas ATOT/ALDT (exato); sem torre usa o radar, que pode incluir tráfego de aeródromos vizinhos.
- **Pico 60 min:** o maior número de movimentos em qualquer janela de 60 minutos (avaliada de 5 em 5 min). "Hora cheia" = maior contagem numa hora de relógio (08:00–09:00, etc.).
- **Utilização no pico:** pico de 60 min a dividir pela **capacidade declarada** da pista, em percentagem. Acima de 100 % a procura excedeu a capacidade. "h acima" = número de horas de relógio com mais movimentos do que a capacidade. A capacidade declarada edita-se no cartão **capacidade declarada (mov./h)** (40 por omissão para Lisboa) e fica guardada por aeroporto.
- **Go-arounds:** aproximações abortadas registadas pela torre (campo GA) e a taxa por 1 000 aterragens.
- **Taxi-out adicional:** taxi-out real (off-block → descolagem) menos a referência P20 para o mesmo stand e pista (ou só a pista, quando há poucos casos). Valor médio por partida, em minutos ou segundos.
- **Taxi-in adicional:** taxi-in real (saída de pista → on-block) menos a referência P20 por stand e pista.
- **ASMA adicional:** o ASMA é um anel à volta do aeroporto (40 NM no PRU). Mede-se o tempo desde que a chegada entra no anel até aterrar, e subtrai-se a referência P20 por pista e por **setor de entrada** (oito setores de 45°: N, NE, E, …). Como o radar do CNS não cobre 40 NM a toda a volta, a aplicação usa o maior anel coberto pelos dados (indicado no título; 13 NM para Lisboa). Este indicador mede atrasos de sequenciamento, vectoração e esperas.
- **Pontualidade partida (15 min):** percentagem de partidas que descolaram até 15 minutos depois da hora prevista (ETOT, ou CTOT quando o voo foi regulado), segundo o NMIR. É uma aproximação ao indicador OTP15 da EUROCONTROL (que usa a hora de off-block, não a de descolagem).
- **Atraso ATFM (NMIR):** minutos de atraso ATFM atribuídos às partidas pelo Network Manager; "regulados" = voos que receberam CTOT.
- **Atraso ATFM (torre):** o mesmo, mas registado no ficheiro da torre; inclui a tabela **por regulação**.
- **CDO (OPDI):** percentagem de chegadas sem nenhum patamar abaixo de FL100, segundo os eventos "level-start" do OPDI.

Gráficos: **Movimentos por hora (média diária)**, **Taxi-out / Taxi-in adicional por stand**, **ASMA por setor de entrada**, **ASMA — chegadas com mais tempo adicional**, **Desvio ATOT − (CTOT ou ETOT)** (histograma: negativo = descolou antes da hora prevista), **Patamares abaixo de FL100 por chegada**.

**⬇ Excel PRU** exporta todos os indicadores, cada um com a lista dos voos que lhe deram origem.

### 11.2 KPIs radar (sub-aba)

Indicadores calculados só com o radar: movimentos, pico de aterragens e de descolagens (janela móvel de 60 min), média do período, **Total** de passagens por waypoint, hora de pico, dias de dados.

### 11.3 Relatórios

- **📄 Relatório mensal:** num clique gera um relatório imprimível (abre no navegador; use Imprimir → Guardar como PDF) com: KPIs PRU, evolução diária (Painel), ROT e taxi (Solo), KPIs radar e cruzamento de fontes, para os dias do filtro.
- **🧩 Relatórios…:** relatórios à medida. Escolha as secções (KPIs PRU, Painel, Solo, KPIs radar, Análise de Dados, Análise Diária, RRMS, Cruzamento), dê um nome e **Guardar**: aparece um botão novo na barra da aba, que gera esse relatório sempre que precisar. Os botões ficam guardados na base de dados.

## 12. Abas Painel, Solo e Cruzamento

### 12.1 Painel

Ao contrário das outras abas, o Painel **não depende do filtro de dias**: mostra a evolução diária de **toda a base de dados** (ou de um período que escolher em **Período**).

- **Séries diárias:** movimentos por dia; chegadas/partidas por dia; ROT mediano (s); taxi mediano (min); atraso ATFM (min); pontualidade à partida (%); go-arounds. Cada gráfico tem a **média móvel de 7 dias** (linha tracejada) para suavizar o efeito do dia da semana. As linhas tracejadas horizontais são metas ou alertas (60 s no ROT; 80 % na pontualidade).
- **Referência:** escolha "período anterior (mesma duração)", "mesmo período do ano anterior" ou "personalizada": a referência aparece a cinzento em cada gráfico, e o cartão **Variação** mostra a diferença percentual da média diária de movimentos.
- **Comparação A (período) vs B (referência):** tabela com os mesmos indicadores nos dois períodos e a diferença Δ: verde = melhorou, vermelho = piorou (para ROT, taxi, ATFM e go-arounds, menor é melhor).
- **Top 10:** operadores (radar), tipos de aeronave (radar) e aeroportos de origem/destino (NMIR), com o valor da referência ao lado.
- **Qualidade / cobertura dos dados por dia:** para cada dia, quantos blocos radar existem (de 6), se há dados da torre, NMIR e OPDI, e alertas automáticos (ROT alto, muitos go-arounds, ATFM elevado, pontualidade baixa). Serve para perceber se um valor estranho se deve a dados em falta.
- **⬇ Excel** exporta todas as séries.

### 12.2 Solo (movimentos no solo em Lisboa)

Esta aba usa o ficheiro da torre (A-SMGCS) e só tem dados para Lisboa.

- **Mapa do aeroporto:** à direita, com a rede de **taxiways, pistas e 89 stands** de Lisboa, retirada do OpenStreetMap e embebida na aplicação (não precisa de internet). Fundo: OSM (por omissão), Satélite ou Sem fundo. **Nomes** liga/desliga as etiquetas dos taxiways e stands.
- **Tabela:** à esquerda, com um movimento por linha: hora, callsign, tipo, pista, stand, saída de pista (EP) ou ponto de espera (HP), ROT, taxi e o movimento radar correspondente quando existe. Clique numa linha para ver o percurso no mapa. O divisor entre tabela e mapa arrasta-se; duplo clique repõe a posição.
- **Percurso no solo:** para cada movimento, a aplicação reconstrói o caminho real stand ↔ pista a partir da sequência de taxiways registada (TAXI_OUT / TAXI_IN) e das horas reais (off-block, ponto de espera, entrada na pista, descolagem; aterragem, saída de pista, on-block), calculando o caminho mais curto na rede entre esses pontos.
- **Animação do dia:** o relógio (▶, velocidade 1× a 120×, barra de tempo) move todos os aviões ao longo do dia, com rasto. **Clicar num avião** no mapa seleciona-o na tabela sem parar o relógio.
- **Replay ar + solo:** com a caixa marcada, as trajetórias radar do mesmo dia animam-se no mesmo relógio: uma chegada aparece no ar, aterra e continua no percurso de solo até ao stand; uma partida faz o inverso.
- **ROT e taxi (A-SMGCS)** (botão): estatísticas de **ROT** (tempo de ocupação de pista) — chegadas: da aterragem (ALDT) à saída da pista (RWY_VAC); partidas: da entrada na pista (RWY_ENT) à descolagem (ATOT) — com distribuições, por saída de pista / ponto de espera, por categoria de esteira e por pista; **taxi-in/out por stand** (15 mais usados); **velocidade na saída** de pista. Todos os cartões são clicáveis. **⬇ Excel**.
- **📥 Ficheiro da torre…** importa um ficheiro individual.

### 12.3 Cruzamento de fontes

Mostra, **num só registo por movimento**, o que diz cada fonte: radar, NMIR, torre e OPDI. Serve para validar os dados e descobrir erros (um tipo de aeronave errado no NMIR, um voo que o radar não viu, relógios desfasados).

- **Emparelhamento:** dois registos de fontes diferentes são considerados o mesmo movimento quando têm o mesmo callsign, o mesmo dia, o mesmo tipo (chegada/partida) e instantes a menos de 20 minutos um do outro.
- **Cartões de cobertura** (clicáveis): Radar, Torre, OPDI (quantos movimentos cada fonte tem); Radar ∩ Torre, Radar ∩ OPDI, Torre ∩ OPDI (emparelhados); Nas 3; Com NMIR; Só radar, Só torre, Só OPDI; Discrepâncias; Δt radar−torre e Δt OPDI−torre (mediana da diferença de relógio entre as fontes).
- **Discrepâncias assinaladas:** TIPO ≠ (tipo de aeronave diferente entre fontes), WTC ≠, ADEP/ADES ≠, Δt (desvio de tempo grande), GA (go-around), e "sem radar / sem torre / sem OPDI".
- **Filtro:** Todos, Só discrepâncias, Sem radar, Sem torre, Sem OPDI, Nas 3 fontes; e pesquisa por callsign.
- **Clicar numa linha** abre o detalhe com todas as fontes lado a lado.
- **⬇ Excel:** folhas Cruzamento, Discrepâncias e Cobertura. **⟳ Cruzar fontes** recalcula depois de importar dados novos.

### 12.4 Registar correções

Quando sabe qual é o valor correto de uma discrepância, pode registá-lo:

1. Clique no ícone de lápis (✎) na primeira coluna da linha.
2. Preencha o tipo de aeronave correto, a WTC, o ADEP/ADES, ou marque apenas **Verificado**, e escreva uma nota se quiser.
3. **Guardar.**

A correção fica guardada na base de dados e aplica-se ao movimento radar e ao registo NMIR; os ficheiros de origem não são alterados e a correção sobrevive a novas importações. Se corrigir a **categoria de esteira de um tipo de aeronave** (por exemplo CL35 de L para M), a correção vale para **todos** os movimentos desse tipo, passados e futuros.

## 13. Aba Pontos

Analisa a passagem dos voos por um ponto à escolha.

- **Passagens num ponto:** escolha o **Ponto** (da lista AIP ou personalizado), o **Raio** (NM) e, opcionalmente, um filtro de **IAS** (<, ≤, = ±, ≥, >, entre … kt). **▶ Pesquisar** lista todos os voos que passaram dentro do raio, com a hora, a IAS, a altitude e a distância ao ponto; gráficos de distribuição.
- **Sequência:** para um ponto e uma **Dist. máx**, mostra os voos em sequência e a distância (e tempo) à frente e atrás de cada um — útil para ver o espaçamento numa STAR.
- **Pontos personalizados:** **+ Adicionar** cria um ponto com Nome (ex.: FF36), Lat e Lon em graus decimais e Descrição. Os pontos ficam na base de dados; **↓ points.json** exporta a lista para um ficheiro e **↑ points.json** importa (para partilhar com colegas).

## 14. Aba Análise IA

Envia um resumo (não os ficheiros) das análises do filtro atual a um modelo de linguagem e devolve uma interpretação escrita em português. Escreva a pergunta na caixa (ex.: "Quais as horas com mais pares abaixo de 160 s? Que companhias têm mais violações de IAS?") e clique **ENVIAR**. Antes de usar, configure em **⚙ Preferências → Análise IA** o fornecedor (Claude, OpenAI, Mistral, Azure, Groq), o modelo e a chave API; a chave fica guardada apenas na base de dados local deste computador. Esta é a única função da aplicação que envia dados para fora do computador.

## 15. Aceder a partir de um iPad ou de outro computador

A aplicação não se instala no iPad, mas pode ser **usada** a partir dele, como se fosse uma página web, desde que esteja aberta num PC da mesma rede:

1. No PC, abra o atalho **"FlightTracker (acesso na rede local — iPad)"** do menu Iniciar (é o mesmo programa, iniciado com a opção `--lan`). Na primeira vez, o Windows pergunta se permite o acesso à rede: clique **Permitir acesso**.
2. Na aplicação, abra **⚙ Preferências → Acesso a partir de outros dispositivos**. Aparece o endereço, por exemplo `http://192.168.1.23:8765`.
3. No iPad, ligado ao **mesmo Wi-Fi**, abra o Safari e escreva esse endereço. A aplicação aparece como no PC. Pode guardá-la no ecrã inicial (botão Partilhar → Adicionar ao ecrã principal) para ficar com um ícone.
4. O PC tem de ficar ligado, com a aplicação aberta. Tudo o que vê no iPad é calculado no PC; importações e relatórios também acontecem lá.

Não há palavra-passe: qualquer pessoa na mesma rede com o endereço pode usar a aplicação (só consulta; não altera os ficheiros de origem). Use apenas em rede interna. Se não abrir, verifique, por esta ordem: a aplicação foi iniciada com o atalho de rede local (e não o normal); PC e iPad estão na mesma rede (nas redes empresariais, o Wi-Fi de convidados costuma estar separado da rede dos PCs); a firewall do Windows permite o FlightTracker (Painel de Controlo → Firewall → Permitir uma aplicação).

## 16. Preferências (aba ⚙)

- **Análise IA — fornecedor e chave:** fornecedor, modelo, chave API, endpoint Azure (só para Azure). **Guardar.**
- **Base de dados:** caminho e tamanho; **🧹 Remover ficheiros que já não existem no disco**.
- **Acesso a partir de outros dispositivos:** o endereço a usar no iPad (capítulo 15).
- **Guia de utilização:** o botão **📘 Descarregar o guia de utilização (PDF)** abre este documento (no PC é copiado para a pasta de dados e aberto no leitor de PDF; no iPad abre num separador do Safari).
- **Histórico de versões:** as novidades de cada versão. **✉ Email de novidades** abre no Outlook um rascunho já escrito com as alterações e os links de download para Windows e macOS — só falta pôr os destinatários. **⬇ Guardar HTML** guarda o mesmo texto num ficheiro.
- **Sobre.**

## 17. Cartões clicáveis, modais e exportações

Regra geral da aplicação: **em qualquer aba ou sub-aba, qualquer cartão que mostre um valor calculado é clicável**. Ao clicar, abre-se uma janela (modal) com a lista dos voos ou registos que deram origem a esse valor — por exemplo, clicar em "Go-arounds: 3" mostra os três voos. Todas estas janelas têm os botões **⬇ Excel** e **📄 PDF**. O cursor muda para uma mão sobre os cartões clicáveis. Os cartões que são apenas parâmetros de entrada (Raio CPA, Tolerância, capacidade declarada) não têm dados de origem e por isso não abrem janela.

Cada cartão, gráfico e conceito tem ainda um pequeno **?** ao lado: passe o rato (ou toque) para ler a explicação; quando o cartão é clicável, a explicação inclui a indicação "Clica no cartão para ver os dados de origem".

Outras exportações: **⬇ Excel** e **⬇ CSV** nas tabelas; **⬇ Excel PRU** nos KPIs; **⬇ PPTX** nas velocidades; relatórios imprimíveis (**📄**) que abrem no navegador — para obter PDF use Imprimir → Guardar como PDF. Os ficheiros Excel são guardados na pasta de dados (ou onde escolher na janela de gravação) e a aplicação mostra o caminho numa mensagem.

## 18. Resolução de problemas

- **A janela não abre, ou abre em branco.** A aplicação precisa do componente WebView2 do Windows (vem com o Edge; já existe em todos os PCs atualizados). Use o atalho **FlightTracker (no navegador)**: a aplicação abre no navegador predefinido e funciona da mesma forma.
- **Onde está o registo (log)?** Em `C:\Users\<o seu nome>\AppData\Local\FlightTracker\app.log` (clique no ícone da base de dados na barra superior para abrir a pasta). Não está na pasta de instalação do programa. Ao reportar um problema, envie este ficheiro.
- **A importação parece parada.** Com muitos ficheiros é normal demorar; a fase final ("a reconstruir movimentos") pode demorar alguns minutos numa base grande. A aplicação continua utilizável entretanto. Se depois de 30 minutos nada mudar, feche e volte a abrir a aplicação e use ⟳ Atualizar: os ficheiros já importados não voltam a ser lidos.
- **Um dia não aparece no calendário.** O nome do ficheiro (ou da pasta) não tem a data e o bloco no formato esperado (ver 3.3). Renomeie e importe de novo.
- **Movimentos a mais no aeroporto (Cascais, Montijo, helicópteros).** Ligue **✈ Só ARR/DEP**.
- **Um voo tem tipo ou categoria de esteira errada.** Corrija na aba Cruzamento (✎) — fica guardado.
- **O mapa fica parcialmente em branco.** Mude de aba e volte, ou redimensione a janela.
- **Sem acesso a partir do iPad.** Ver o final do capítulo 15.
- **A base de dados ficou corrompida ou demasiado grande.** Feche a aplicação, apague (ou mude o nome de) `flightplotter.duckdb` na pasta de dados e volte a importar. As correções registadas perdem-se; as preferências também.
- **Erro inesperado.** A mensagem aparece numa caixa no fundo do ecrã; o detalhe fica no `app.log`.

## 19. Acrónimos e termos

| Acrónimo / termo | Significado |
|---|---|
| A-SMGCS | Advanced Surface Movement Guidance and Control System — sistema da torre que vigia e guia os movimentos no solo (aviões e viaturas) com radar de superfície e multilateração. É a origem do "ficheiro da torre". |
| AA / ADA / ADDA / AD…A | Tipos de sequência na análise FAST: duas chegadas seguidas; com uma, duas, ou três ou mais partidas intercaladas entre elas. |
| ADEP | Aerodrome of Departure — aeródromo de partida do voo (código ICAO de 4 letras). |
| ADES | Aerodrome of Destination — aeródromo de destino do voo. |
| ADS-B | Automatic Dependent Surveillance–Broadcast — o avião transmite a sua própria posição GPS; recetores no solo (como os da OpenSky) captam-na. Base dos dados OPDI. |
| AIBT | Actual In-Block Time — hora real em que o avião parou no stand (calços colocados). Fim do taxi-in. |
| AIP | Aeronautical Information Publication — publicação oficial de informação aeronáutica de cada país; de onde vêm os pontos (waypoints, FAF, soleiras) e as restrições de velocidade. |
| AIRAC | Aeronautical Information Regulation and Control — ciclo de 28 dias em que as alterações ao AIP entram em vigor. |
| ALDT | Actual Landing Time — hora real de aterragem (toque na pista). |
| AOBT | Actual Off-Block Time — hora real em que o avião saiu do stand (calços retirados). Início do taxi-out. |
| APP | Approach — a fase de aproximação ao aeroporto; na aplicação, a aba de velocidades na aproximação. |
| ARR | Arrival — chegada. |
| ASMA | Arrival Sequencing and Metering Area — anel (40 NM no PRU) à volta do aeroporto dentro do qual se mede o tempo adicional das chegadas (esperas, vectoração). |
| ATC | Air Traffic Control — controlo de tráfego aéreo. |
| ATFM | Air Traffic Flow Management — gestão de fluxos: quando há mais procura do que capacidade (num setor ou aeroporto), o Network Manager "regula" voos, atribuindo-lhes um CTOT e, portanto, um atraso ATFM. |
| ATOT | Actual Take-Off Time — hora real de descolagem. |
| Bloco horário | Cada um dos seis períodos de 4 horas em que os ficheiros do radar são divididos (00–04, 04–08, …, 20–24 UTC). |
| Bunching | "Agrupamento": pares de aterragens consecutivas com menos de 90 s entre si. |
| Callsign (csn) | Indicativo de chamada do voo (ex.: TAP441, RYR4PT). As três primeiras letras identificam o operador. |
| Capacidade declarada | Número de movimentos por hora que o aeroporto declara conseguir processar; usada na utilização no pico. |
| CDO | Continuous Descent Operations — descida contínua, sem patamares em nível; poupa combustível e ruído. Na aplicação é medida abaixo de FL100. |
| CNS | Communications, Navigation, Surveillance — área da NAV que exporta os CSV do radar. |
| CPA | Closest Point of Approach — o ponto da trajetória que passou mais perto de um waypoint. |
| CPPM | Designação interna do export operacional da torre (ficheiro A-SMGCS). |
| CSV | Comma-Separated Values — ficheiro de texto em que cada linha é um registo e os campos estão separados por vírgulas ou ponto-e-vírgula. Abre no Excel. |
| CTOT | Calculated Take-Off Time — hora de descolagem imposta pelo Network Manager a um voo regulado. |
| DEP | Departure — partida. |
| DME | Distance Measuring Equipment — rádio-ajuda que dá a distância; os pontos "DME" no mapa são posições de referência. |
| DuckDB | A base de dados usada pela aplicação: um único ficheiro no disco, muito rápido para análises. |
| EP | Exit Point — taxiway por onde a chegada saiu da pista (H1, H3, H4…). |
| ETA / ATA | Estimated / Actual Time of Arrival — hora prevista / real de chegada (NMIR). |
| ETOT | Estimated Take-Off Time — hora prevista de descolagem segundo o plano de voo. |
| EUROCONTROL | Organização europeia para a segurança da navegação aérea; gere o Network Manager e a PRU. |
| FAF | Final Approach Fix — ponto onde começa a aproximação final. O "FAF virtual" da aplicação é um ponto a distância fixa da soleira (7 NM por omissão) usado para detetar e medir aterragens. |
| FAST | Final Approach Spacing Tool — nome da análise de separação entre chegadas consecutivas. |
| FL | Flight Level — nível de voo: altitude em centenas de pés com pressão padrão (FL100 = 10 000 ft). |
| ft | Pés (feet); 1 ft = 0,3048 m. |
| GA | Go-around — aproximação abortada ("borrego"): o avião interrompe a aterragem e volta a subir. |
| GOPLIS | Gabinete de Operações de Lisboa (NAV Portugal). |
| GS | Ground Speed — velocidade em relação ao solo (IAS mais ou menos o vento). |
| H / M / L / J | Categorias de turbulência de esteira: Heavy (pesado), Medium (médio), Light (leve), Super (J, A380). |
| HP | Holding Point — ponto de espera antes de entrar na pista (M5, N2, U5, S4, P em Lisboa). |
| IAF | Initial Approach Fix — ponto inicial da aproximação. |
| IAS | Indicated Airspeed — velocidade indicada (a que o piloto lê), em nós; é a que as restrições publicadas usam. |
| ICAO | International Civil Aviation Organization; os códigos de aeródromo de 4 letras (LPPT) e de tipo de aeronave (A320, B738) são da ICAO. |
| icao24 | Endereço Mode S de 24 bits de cada aeronave, em hexadecimal (ex.: 4951C2). Identifica o avião, não o voo. |
| Interpolar | Calcular um valor entre dois registos conhecidos (ex.: a IAS exatamente a 7 NM, a partir dos plots a 7,2 e 6,8 NM). |
| kt | Nós (knots) — milhas náuticas por hora; 1 kt ≈ 1,85 km/h. |
| LAN | Local Area Network — rede local; o modo `--lan` da aplicação. |
| Level-off / patamar | Troço da descida em que a altitude fica constante durante vários plots. |
| LOBD | Last Off-Block Date — data de off-block no NMIR. |
| LPFR / LPMA / LPPR / LPPT | Códigos ICAO de Faro, Madeira, Porto e Lisboa. |
| LVL | Sobrevoo / voo em nível — classe de movimento radar sem chegada nem partida no aeroporto. |
| Média móvel de 7 dias | Média dos últimos 7 dias, calculada para cada dia; alisa as oscilações entre dias úteis e fins de semana. |
| Mediana / P20 / P85 / P95 | Percentis: valor abaixo do qual estão 50 % / 20 % / 85 % / 95 % dos casos. A mediana é menos sensível a valores extremos do que a média. |
| Mode S | Modo de transponder que inclui o endereço único da aeronave (icao24). |
| Movimento | Uma chegada, uma partida ou um sobrevoo detetado no radar. |
| MT | Movement Type — tipo de movimento no ficheiro da torre (A = chegada, D = partida). |
| NAV Portugal | Prestador de serviços de navegação aérea de Portugal. |
| NM | Milha náutica = 1 852 m. |
| NMIR | Network Manager Interactive Reporting — portal de relatórios do Network Manager da EUROCONTROL (planos de voo, tipos, ADEP/ADES, horas previstas e reais, atrasos). |
| Off-block / on-block | Saída do stand (início do taxi-out) / chegada ao stand (fim do taxi-in). |
| OPDI | Open Performance Data Initiative — dados abertos de desempenho da EUROCONTROL (voos e eventos a partir de ADS-B da OpenSky). |
| OpenSky | Rede de recetores ADS-B de acesso aberto, mantida por universidades. |
| OSM | OpenStreetMap — mapa colaborativo aberto; fonte do mapa de fundo e da rede de taxiways e stands. |
| OTP15 | On-Time Performance 15 min — percentagem de voos com atraso até 15 minutos. |
| Plot | Uma posição radar individual (uma linha do CSV): hora, lat/lon, altitude, velocidades. |
| PPTX | Ficheiro PowerPoint. |
| PRU | Performance Review Unit da EUROCONTROL — publica os indicadores de desempenho em ansperformance.eu. |
| Referência (período de) | Intervalo de comparação no Painel (ano anterior, período anterior, personalizado). |
| Referência não-impedida | Tempo que um voo demoraria sem atrasos; o PRU usa o percentil 20 dos tempos observados em situações semelhantes. |
| ROC | Rate of Climb — razão de subida (negativa na descida), em ft/min. |
| ROT | Runway Occupancy Time — tempo de ocupação de pista. Chegada: da aterragem à saída da pista; partida: da entrada na pista à descolagem. |
| RRMS | Reduced Runway Minimum Separation — separação mínima reduzida na pista; permite que uma partida comece antes de a chegada anterior libertar totalmente a pista, se estiver além de um ponto definido (2 400 m em Lisboa). |
| RWY | Runway — pista (02/20 em Lisboa: a mesma pista, usada num sentido ou no outro). |
| RWY_ENT / RWY_VAC | Hora de entrada na pista / de saída da pista, no ficheiro da torre. |
| SID / STAR | Standard Instrument Departure / Standard Terminal Arrival Route — rotas padrão publicadas de partida / chegada. |
| Soleira | Ver THR. |
| Stand (STANDD / STANDA) | Posição de estacionamento do avião, de partida / de chegada. |
| Taxi-in / Taxi-out | Tempo de rolagem da saída de pista ao stand / do stand à descolagem. |
| TAXI_IN / TAXI_OUT | Sequência de taxiways percorridos, registada no ficheiro da torre. |
| THR | Threshold — soleira: o início da parte utilizável da pista para aterragem. |
| TOC / TOD | Top of Climb / Top of Descent — fim da subida / início da descida (eventos OPDI). |
| TOD (na tabela de plots) | Time of Day — hora do plot. |
| Track | Rumo verdadeiro da trajetória, em graus. |
| TWY | Taxiway — caminho de circulação no solo. |
| UTC | Tempo Universal Coordenado — a hora usada em toda a aviação e em toda a aplicação. |
| Waypoint | Ponto de navegação com coordenadas e nome de 5 letras (ex.: NETVO, ODLIX). |
| WebView2 | Componente do Windows (motor do Edge) em que a janela da aplicação é desenhada. |
| WTC | Wake Turbulence Category — categoria de turbulência de esteira (L/M/H/J); determina as separações mínimas. |
| Δt | Diferença de tempo entre duas fontes para o mesmo evento (ex.: hora de aterragem no radar vs na torre). |
