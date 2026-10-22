/* FlightTracker 4 — ajuda contextual: um "?" junto a cada quadro, gráfico e conceito; ao passar o rato mostra a descrição.
   As entradas são procuradas pelo título do cartão/gráfico (correspondência exacta ou por início do título). */
'use strict';
const HELP = {
  // ---- conceitos gerais
  'FSA/DEP': 'First System Activation / DEP: hora em que o Network Manager recebeu a primeira mensagem de ativação do voo (DEP = mensagem de partida da torre, FSA = primeira posição radar). "FSA/DEP − ETOT/CTOT" é o desvio em minutos face à hora prevista ou ao slot.',
  'Movimentos': 'Número de movimentos (chegadas + partidas + sobrevoos) detetados no radar para os dias e blocos escolhidos. Um callsign no mesmo dia é separado em movimentos distintos quando há um intervalo sem plots superior a 5 min — excepto se a aeronave estava no ar antes e depois do intervalo e voltou em menos de 20 min (borrego, buraco de cobertura): continua a ser o mesmo movimento.',
  'Movimentos ARR+DEP': 'Chegadas e partidas detetadas no radar (sem sobrevoos).',
  'Chegadas (ARR)': 'Movimentos cuja altitude desce mais de 500 ft entre o primeiro e o último plot — classificação automática a partir do radar.',
  'Partidas (DEP)': 'Movimentos cuja altitude sobe mais de 500 ft entre o primeiro e o último plot.',
  'Sobrevoos (LVL)': 'Movimentos com variação de altitude inferior a 500 ft (trânsito em nível, helicópteros, voos locais).',
  'Chegadas': 'Chegadas (aterragens) no período.',
  'Partidas': 'Partidas (descolagens) no período.',
  'Dias de dados': 'Número de dias distintos com dados no filtro atual.',
  'Hora de pico': 'Hora UTC com mais movimentos (primeiro plot de cada movimento).',
  'Período (UTC)': 'Do primeiro ao último plot dos movimentos selecionados. Todas as horas da app são UTC.',
  'Amostras (radar)': 'Número total de plots radar (posições) dos movimentos selecionados.',
  'Ficheiros carregados': 'Ficheiros CSV do radar na base de dados que cobrem os dias selecionados.',
  'Resumo Operacional': 'Contagens globais do filtro atual, a partir do radar.',
  'Pista mais usada': 'Pista com mais aterragens detetadas pela análise da Final.',
  'Pistas': 'Distribuição das aterragens por pista.',
  'Dias selecionados': 'Dias escolhidos no calendário.',
  'Referência': 'Período de comparação: os mesmos indicadores calculados para outro intervalo de datas (ano anterior, período anterior ou personalizado). Aparece a cinzento nos gráficos.',
  'Variação': 'Diferença percentual da média diária de movimentos do período face à referência.',

  // ---- Final / aproximações
  'Análise de Aproximações': 'Aterragens detetadas na Final: o voo tem de passar pelo FAF virtual (7 NM por omissão), dentro do corredor lateral (±2 NM) e chegar à soleira abaixo da altitude limite. As métricas FAF→THR são interpoladas entre plots.',
  'Aterragens': 'Aterragens detetadas pela análise da Final (passagem no FAF virtual dentro do corredor e chegada à soleira).',
  'N.º aterragens': 'Aterragens detetadas pela análise da Final.',
  'Estabilizadas': 'Aproximações consideradas estabilizadas: dentro do corredor lateral, perfil vertical próximo de 3° e IAS no FAF dentro do intervalo esperado. Critérios configuráveis na aba Final.',
  'IAS@FAF méd': 'Velocidade indicada média no FAF virtual (interpolada), em nós.',
  'IAS@FAF méd.': 'Velocidade indicada média no FAF virtual (interpolada), em nós.',
  'Tempo FAF→THR méd': 'Tempo médio entre a passagem no FAF virtual e a soleira.',
  'Tempo FAF→THR méd.': 'Tempo médio entre a passagem no FAF virtual e a soleira.',
  'Sep. temporal méd': 'Separação temporal média entre aterragens consecutivas na mesma pista (soleira a soleira).',
  'Sep. temporal méd.': 'Separação temporal média entre aterragens consecutivas na mesma pista (soleira a soleira).',
  'Sep. temporal mín': 'Menor separação temporal entre duas aterragens consecutivas.',
  'Sep. temporal mín./máx.': 'Menor e maior separação temporal entre aterragens consecutivas.',
  'Separação temporal entre aterragens consecutivas': 'Intervalo de tempo entre passagens consecutivas na soleira da mesma pista. Mediana = valor central; mínimo e máximo; bunching = pares a menos de 90 s.',
  'Distribuição das separações': 'Histograma dos intervalos entre aterragens consecutivas.',
  'Mediana': 'Valor central: metade dos casos está abaixo, metade acima. Menos sensível a extremos do que a média.',
  'Média': 'Média aritmética — sensível a valores extremos.',
  'Mínimo': 'Menor valor observado.',
  'Máximo': 'Maior valor observado.',
  'P85': 'Percentil 85: 85 % dos valores são inferiores a este.',
  'P95': 'Percentil 95: 95 % dos valores são inferiores a este.',
  'Bunching': 'Pares de aterragens consecutivas com menos de 90 s entre si — aproximações muito comprimidas.',
  'Menor separação': 'Menor separação temporal observada entre dois voos consecutivos.',
  'Taxa de aterragem (rolling 60 min)': 'Número de aterragens em qualquer janela de 60 minutos, avaliada de 5 em 5 min; o pico é a janela mais carregada. % capacidade compara o pico com a capacidade de referência.',
  'Pico aterragens': 'Maior número de aterragens numa janela móvel de 60 min.',
  'Pico de aterragens': 'Maior número de aterragens numa janela móvel de 60 min.',
  'Pico de descolagens': 'Maior número de descolagens numa janela móvel de 60 min.',
  'Pico descolagens': 'Maior número de descolagens numa janela móvel de 60 min.',
  'Pico movimentos': 'Maior número de movimentos numa hora.',
  'Média período': 'Média de aterragens por hora ao longo do período analisado.',
  'CDO — Continuous Descent Operations (< FL100)': 'Descida contínua: proporção de chegadas sem patamares (segmentos em nível) abaixo de FL100, calculada a partir do radar. Um patamar é um troço com variação de altitude pequena durante vários plots.',
  'Taxa CDO': 'Percentagem de chegadas sem patamar abaixo de FL100.',
  'Level-offs méd./aprox.': 'Número médio de patamares (level-offs) por aproximação abaixo de FL100.',
  'Tempo nível méd.': 'Tempo médio passado em nível abaixo de FL100, por aproximação.',

  // ---- STAR / APP
  'Cumprimento de IAS em waypoints STAR (ARR)': 'Para cada chegada, a IAS no ponto de passagem mais próximo (CPA) de cada waypoint STAR, dentro do raio indicado, é comparada com a restrição publicada. Violação = IAS acima do limite.',
  'Raio CPA': 'Raio à volta do waypoint dentro do qual se procura o ponto de passagem mais próximo (closest point of approach).',
  'Passagens analisadas': 'Passagens de chegadas em waypoints STAR com IAS disponível.',
  'Passagens detectadas': 'Passagens detetadas dentro do raio definido.',
  'Violações': 'Passagens com IAS acima da restrição publicada.',
  'Taxa de cumprimento': 'Percentagem de passagens com IAS dentro da restrição.',
  'Voos ARR analisados': 'Chegadas com pelo menos uma passagem analisada.',
  'Voos com violações': 'Chegadas com pelo menos uma violação.',
  'Tolerância': 'Margem (kt) à volta do limite publicado dentro da qual não se considera violação.',
  'Conformes': 'Passagens dentro do limite (com tolerância).',
  'Abaixo do limite': 'Passagens com IAS abaixo do limite menos a tolerância.',
  'Cumprimento IAS por operador (top 10 pior)': 'Operadores (prefixo do callsign) ordenados por número de violações; "inc./voo" = violações por chegada.',
  'Waypoints sem coordenadas': 'Pontos com restrição definida mas sem coordenadas conhecidas — não são analisados.',
  '📈 Perfil de velocidade ao longo da final': 'IAS interpolada a cada milha náutica da soleira, por voo, comparada com a escala de limites da final (12 NM → THR).',
  'Estatísticas no ponto de referência (valores interpolados)': 'IAS e altitude no ponto escolhido, interpoladas entre os dois plots que o enquadram.',
  'IAS mín/méd/máx RWY 02': 'Velocidade indicada mínima, média e máxima das passagens na pista 02.',
  'IAS mín/méd/máx RWY 20': 'Velocidade indicada mínima, média e máxima das passagens na pista 20.',
  'Alt. mín/méd/máx RWY 02': 'Altitude mínima, média e máxima das passagens na pista 02.',
  'Alt. mín/méd/máx RWY 20': 'Altitude mínima, média e máxima das passagens na pista 20.',
  'RWY 02 — passagens': 'Passagens de chegadas na pista 02 no ponto analisado.',
  'RWY 20 — passagens': 'Passagens de chegadas na pista 20 no ponto analisado.',
  'Análise por pista': 'Resultados separados por pista de aterragem.',

  // ---- FAST / dados / diária
  'Pares': 'Pares de aterragens consecutivas na mesma pista (líder → seguidor) com separação entre 0 e 600 s.',
  'Pares analisados': 'Pares de aterragens consecutivas analisados.',
  'Pares globais': 'Todos os pares de aterragens consecutivas, antes de aplicar filtros.',
  'Passagens THR detetadas': 'Passagens na soleira detetadas pela análise da Final.',
  'Tipo de sequência': 'AA = duas chegadas seguidas sem partida entre elas; ADA = uma partida entre as duas chegadas; ADDA = duas partidas; AD…A = três ou mais partidas intercaladas.',
  'DEP entre chegadas': 'Partidas que descolaram entre as duas aterragens do par.',
  'IAS da aeronave seguidora': 'Velocidade indicada do seguidor no momento em que o líder cruza a soleira.',
  'Posição do seguidor no momento do DEP': 'Distância do seguidor à soleira no instante da descolagem intercalada.',
  'Separação vs distância do seguidor': 'Relação entre a separação temporal do par e a distância do seguidor quando o líder aterra.',
  'Críticos com DEP': 'Pares abaixo do limite de separação que tiveram uma partida intercalada.',
  'Críticos sem DEP': 'Pares abaixo do limite de separação sem partida intercalada.',
  'Hora mais crítica': 'Hora com mais pares abaixo do limite.',
  'Hora mais movimentada': 'Hora com mais movimentos.',
  'Ocorrências críticas por dia': 'Pares abaixo do limite de separação, por dia.',
  'Top 10 situações mais críticas': 'Os pares com menor separação temporal.',
  'Top 10 companhias por taxa de ocorrências críticas': 'Operadores com maior proporção de pares críticos face ao total de pares em que participam.',
  'Resumo por companhia': 'Movimentos e pares por operador (prefixo do callsign).',
  'Resumo por hora': 'Movimentos e pares críticos por hora do dia.',
  'Resumo por dia e hora': 'Tabela cruzada dia × hora.',
  'Movimentos por companhia (top 15)': 'Operadores com mais movimentos (prefixo do callsign).',
  'Companhias por dia (top 10)': 'Movimentos dos principais operadores, por dia.',
  'Padrões por dia da semana': 'Médias por dia da semana (segunda a domingo).',
  'Média de movimentos por dia da semana': 'Movimentos médios em cada dia da semana.',
  'Média de pares críticos por dia da semana': 'Pares abaixo do limite, em média, por dia da semana.',
  'Callsigns comuns aos dias': 'Callsigns que aparecem em todos os dias selecionados (voos regulares).',
  'Callsigns comuns entre dias': 'Callsigns presentes em mais do que um dia.',
  'Pico horário por dia': 'Hora de pico e número de movimentos nessa hora, por dia.',
  'Movimentos por hora (UTC)': 'Distribuição dos movimentos pelas 24 horas (UTC).',
  'Movimentos por hora': 'Distribuição dos movimentos por hora.',
  'Movimentos por dia': 'Movimentos por dia do período.',
  'Top 10 operadores (prefixo callsign)': 'Operadores identificados pelas três letras iniciais do callsign (TAP, RYR…).',

  // ---- RRMS / ROT
  'No ar vs Solo no ponto 2400m — por hora': 'Passagens de partidas no ponto a 2 400 m da soleira (TWY U6 / P): "no ar" quando já descolou (altitude ≥ 50 ft), "solo" quando ainda rola.',
  'Descolagens': 'Partidas analisadas no ponto de referência.',
  'ROT médio': 'Tempo médio de ocupação de pista.',
  'Saídas / entradas': 'Taxiway por onde a chegada saiu da pista (radar: junção da rede de taxiways mais próxima da última amostra na pista, do lado para onde virou; torre: campo EP) ou por onde a partida entrou (só a torre consegue: ponto de espera HP — o radar vê a partida já em corrida). A hora ao lado é a do evento (saída / entrada na pista).',
  'Posição na pista': 'Distância ao longo da pista, em metros desde a soleira. Chegadas: onde a última amostra radar ainda estava na pista (≈ saída usada). Partidas: 1.ª amostra radar na pista (já em corrida) → ponto de descolagem (100 ft sobre a pista).',
  'N.º movimentos': 'Chegadas e partidas com ROT calculável a partir do radar: chegada = do cruzamento da soleira à última amostra na pista; partida = da primeira amostra na pista (no solo) à descolagem (primeira amostra acima de 100 ft sobre a pista). Só é possível quando há plots na rolagem.',
  'Total': 'Total de registos analisados.',
  'Vel. na saída': 'Velocidade (kt) registada pelo A-SMGCS no momento em que a aeronave liberta a pista (RWY_VAC).',

  // ---- KPIs PRU
  'KPIs de aeroporto — estilo PRU / EUROCONTROL': 'Indicadores com as definições da Performance Review Unit (ansperformance.eu), para comparar com os painéis da EUROCONTROL. "Adicional" significa tempo real menos uma referência não-impedida (percentil 20 do grupo).',
  'Movimentos de pista': 'Chegadas + partidas reais na pista. Com ficheiro da torre usa ATOT/ALDT (movimentos de pista); sem torre usa o radar, que inclui tráfego de aeródromos vizinhos.',
  'Pico 60 min': 'Maior número de movimentos de pista em qualquer janela de 60 minutos (passos de 5 min). "Hora cheia" = maior contagem numa hora de relógio.',
  'Utilização no pico': 'Pico de 60 min dividido pela capacidade declarada da pista (movimentos/hora). Acima de 100 % a procura excedeu a capacidade declarada nessa hora. "h acima" = horas de relógio com mais movimentos do que a capacidade.',
  'Go-arounds': 'Aproximações abortadas. Torre: o A-SMGCS cria um registo ARRIVAL com GA=TRUE no instante do borrego (sem saída de pista nem stand) e outro registo para a aterragem real. Radar: ponto abaixo de 1 500 ft a menos de 4 NM da soleira, depois de descer ≥ 1 000 ft e seguido de subida ≥ 600 ft. O cartão mostra os da torre (e quantos o radar confirma); sem ficheiro da torre, os do radar. Taxa por 1 000 aterragens.',
  'Taxi-out adicional': 'Tempo de taxi-out real (off-block → descolagem) menos a referência não-impedida: percentil 20 dos tempos observados para o mesmo stand e pista (ou só pista, se houver poucos casos). Indicador PRU "additional taxi-out time".',
  'Taxi-in adicional': 'Tempo de taxi-in real (saída de pista → on-block) menos a referência não-impedida (percentil 20 por stand e pista). Indicador PRU "additional taxi-in time".',
  'ASMA adicional': 'ASMA = Arrival Sequencing and Metering Area. Tempo desde a entrada no anel à volta do aeroporto até à aterragem, menos a referência não-impedida (percentil 20 por pista e setor de entrada). O PRU usa 40 NM; aqui o anel é o maior coberto pelo radar (indicado no título). Mede atrasos de sequenciamento, vectoração e esperas.',
  'ASMA por setor de entrada': 'Tempo adicional médio por setor de 45° em que a chegada entrou no anel (N, NE, E…), com a referência não-impedida de cada setor.',
  'ASMA — chegadas com mais tempo adicional': 'Chegadas com mais tempo acima da referência do seu setor.',
  'Pontualidade partida (15 min)': 'Partidas que descolaram até 15 min depois da hora prevista (ETOT, ou CTOT quando regulada), segundo o NMIR. Aproximação ao indicador OTP15 da EUROCONTROL, que usa off-block em vez de descolagem.',
  'Pontualidade 15 min': 'Partidas que descolaram até 15 min depois do ETOT/CTOT (NMIR).',
  'Atraso ATFM (NMIR)': 'Minutos de atraso ATFM (regulações do Network Manager) atribuídos às partidas, segundo o NMIR; "regulados" = voos com CTOT.',
  'Atraso ATFM (torre)': 'Minutos de atraso ATFM registados no ficheiro da torre, por partida.',
  'Atraso ATFM por regulação (torre)': 'Minutos e voos por regulação ATFM.',
  'Desvio ATOT − (CTOT ou ETOT), min': 'Histograma da diferença entre a descolagem real e a hora prevista (ou o CTOT, quando regulada). Negativo = descolou antes.',
  'CDO (OPDI)': 'Chegadas sem nenhum patamar abaixo de FL100 segundo os eventos level-start do OPDI (ADS-B). Mede a descida contínua.',
  'Patamares abaixo de FL100 por chegada (OPDI)': 'Distribuição do número de patamares (level-offs) abaixo de FL100 por chegada.',
  'Movimentos por hora (média diária, chegadas + partidas)': 'Movimentos de pista por hora do dia, em média por dia do período.',
  'Taxi-out adicional por stand (média, s)': 'Stands com mais tempo adicional de taxi-out (média por partida).',
  'Taxi-in adicional por stand (média, s)': 'Stands com mais tempo adicional de taxi-in (média por chegada).',

  // ---- Painel
  'Movimentos por dia —': 'Movimentos de pista por dia (torre; radar quando não há torre), com média móvel de 7 dias (tracejado) e período de referência (cinzento).',
  'ROT mediano por dia (s)': 'ROT = Runway Occupancy Time (tempo de ocupação de pista). Chegadas: ALDT → RWY_VAC; partidas: RWY_ENT → ATOT. Mediana de cada dia; linha tracejada = alerta a 60 s.',
  'Taxi mediano por dia (min)': 'Mediana diária do taxi-out (off-block → descolagem) e do taxi-in (saída de pista → on-block).',
  'Atraso ATFM por dia (min, torre)': 'Soma dos minutos de atraso ATFM das partidas de cada dia.',
  'Pontualidade à partida por dia (%, NMIR)': 'Percentagem diária de partidas até 15 min depois do ETOT/CTOT; linha tracejada = meta de 80 %.',
  'Go-arounds por dia': 'Aproximações abortadas por dia (torre).',
  'Chegadas / partidas por dia': 'Chegadas e partidas por dia (torre; radar quando não há torre).',
  'Comparação A (período) vs B (referência)': 'Os mesmos indicadores nos dois períodos; Δ verde = melhorou, vermelho = piorou (para ROT, taxi, ATFM e go-arounds, menor é melhor).',
  'Top 10 operadores (radar)': 'Operadores com mais movimentos (prefixo do callsign), com o valor da referência ao lado.',
  'Top 10 tipos (radar)': 'Tipos de aeronave com mais movimentos.',
  'Top 10 aeroportos origem/destino (NMIR)': 'Aeroportos de origem/destino mais frequentes segundo o NMIR.',
  'Mapa de calor — hora × dia da semana': 'Número de movimentos por hora (UTC) e dia da semana, somados em todos os dias do período. Mais escuro = mais movimentos. Hora da descolagem (ATOT) e da aterragem (ALDT) da torre; nos dias sem ficheiro da torre, o radar. Clica numa célula para ver os voos.',
  'Qualidade / cobertura dos dados por dia': 'Para cada dia: blocos radar presentes (de 6), existência de dados da torre, NMIR e OPDI, e alertas automáticos (ROT, go-arounds, ATFM, pontualidade).',
  'ROT chegada': 'Tempo de ocupação de pista nas chegadas: da aterragem (ALDT) à saída da pista (RWY_VAC), medido pelo A-SMGCS.',
  'ROT partida': 'Tempo de ocupação de pista nas partidas: da entrada na pista (RWY_ENT) à descolagem (ATOT).',
  'Taxi-out': 'Tempo entre off-block (AOBT) e descolagem (ATOT).',
  'Taxi-in': 'Tempo entre a saída da pista (RWY_VAC) e on-block (AIBT).',

  // ---- Solo
  'ROT chegadas — distribuição (s)': 'Histograma do tempo de ocupação de pista nas chegadas.',
  'ROT partidas — distribuição (s)': 'Histograma do tempo de ocupação de pista nas partidas.',
  'ROT chegadas por saída de pista': 'ROT das chegadas agrupado pelo taxiway de saída (H1, H3, H4…): saídas mais afastadas da soleira dão ROT maior.',
  'ROT chegadas por WTC': 'ROT das chegadas por categoria de turbulência de esteira (L/M/H/J).',
  'ROT chegadas por pista': 'ROT das chegadas por pista.',
  'ROT partidas por ponto de espera': 'ROT das partidas agrupado pelo ponto de espera usado (M5, N2, U5, S4, P): entradas intermédias encurtam a corrida.',
  'ROT partidas por WTC': 'ROT das partidas por categoria de turbulência de esteira.',
  'ROT partidas por pista': 'ROT das partidas por pista.',
  'Taxi-in por stand (15 mais usados)': 'Mediana do taxi-in para os stands de chegada mais usados.',
  'Taxi-out por stand (15 mais usados)': 'Mediana do taxi-out para os stands de partida mais usados.',

  // ---- Cruzamento
  'Radar': 'Movimentos detetados no radar (CSV do CNS).',
  'Torre': 'Movimentos do export operacional da torre (A-SMGCS / CPPM).',
  'OPDI': 'Voos do Open Performance Data Initiative (EUROCONTROL, a partir de ADS-B da OpenSky).',
  'Radar ∩ Torre': 'Movimentos emparelhados entre radar e torre (mesmo callsign, dia e tipo de movimento, instante mais próximo).',
  'Radar ∩ OPDI': 'Movimentos emparelhados entre radar e OPDI.',
  'Torre ∩ OPDI': 'Movimentos emparelhados entre torre e OPDI.',
  'Nas 3': 'Movimentos presentes nas três fontes.',
  'Com NMIR': 'Movimentos com registo NMIR (tipo de aeronave, ADEP/ADES) nesse dia.',
  'Discrepâncias': 'Movimentos em que as fontes não concordam (tipo, WTC, ADEP/ADES, desvios de tempo) ou com go-around.',
  'Só radar': 'Movimentos que só o radar viu — tipicamente tráfego de aeródromos vizinhos ou sobrevoos classificados como chegada/partida.',
  'Só torre': 'Movimentos da torre sem correspondência no radar (fora dos blocos carregados, ou callsign diferente).',
  'Só OPDI': 'Voos OPDI sem correspondência nas outras fontes.',
  'Δt radar−torre': 'Mediana da diferença entre o primeiro plot radar e o ATOT (partidas) ou entre o último plot e o ALDT (chegadas). Mostra a consistência dos relógios e da cobertura.',
  'Δt OPDI−torre': 'Mediana da diferença entre o evento de pista do OPDI e o ATOT/ALDT da torre.',
};

const HELP_KEYS = Object.keys(HELP).sort((a, b) => b.length - a.length);
function helpFor(title) {
  if (!title) return null;
  const t = String(title).trim();
  if (HELP[t]) return HELP[t];
  for (const k of HELP_KEYS) if (t.startsWith(k)) return HELP[k];
  return null;
}
/* devolve o HTML do "?" (ou '' se não houver ajuda para este título) */
function helpIcon(title) {
  const h = helpFor(title);
  return h ? `<span class="hq" data-h="${h.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')}" tabindex="0">?</span>` : '';
}
// tooltip única, posicionada junto ao "?"
document.addEventListener('DOMContentLoaded', () => {
  const tip = document.createElement('div'); tip.id = 'helpTip'; tip.className = 'help-tip hidden'; document.body.appendChild(tip);
  const show = el => {
    const clk = el.closest('.kcard.clk');
    tip.innerHTML = ''; tip.appendChild(document.createTextNode(el.dataset.h));
    if (clk) { const m = document.createElement('div'); m.className = 'help-clk'; m.textContent = '↗ Clica no cartão para ver os dados de origem'; tip.appendChild(m); }
    tip.classList.remove('hidden');
    const r = el.getBoundingClientRect(); const w = Math.min(360, window.innerWidth - 24);
    tip.style.maxWidth = w + 'px';
    let x = r.left + r.width / 2 - w / 2; x = Math.max(12, Math.min(x, window.innerWidth - w - 12));
    tip.style.left = x + 'px';
    const th = tip.offsetHeight; const below = r.bottom + 8 + th < window.innerHeight;
    tip.style.top = (below ? r.bottom + 8 : r.top - th - 8) + 'px';
  };
  document.addEventListener('mouseover', e => { const el = e.target.closest('.hq'); if (el) show(el); });
  document.addEventListener('mouseout', e => { if (e.target.closest('.hq')) tip.classList.add('hidden'); });
  document.addEventListener('focusin', e => { const el = e.target.closest('.hq'); if (el) show(el); });
  document.addEventListener('focusout', e => { if (e.target.closest('.hq')) tip.classList.add('hidden'); });
  document.addEventListener('click', e => { const el = e.target.closest('.hq'); if (el) { e.stopPropagation(); e.preventDefault(); tip.classList.contains('hidden') ? show(el) : tip.classList.add('hidden'); } }, true);
});
window.HELP = HELP; window.helpIcon = helpIcon; window.helpFor = helpFor;
