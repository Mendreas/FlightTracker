# FlightTracker 4.0

Análise de trajetórias radar (CSV do CNS) para os aeroportos LPPT, LPPR, LPFR e LPMA.
Versão 4 do FlightTracker: reescrita em Python/DuckDB (as versões 1–3 eram uma app HTML de ficheiro único) com um objetivo: **ler os dados muito mais depressa.**

## Como funciona

```
CSV do CNS ──(importa 1 vez)──►  base DuckDB local  ──(SQL, ms)──►  mapa / tabela / análises
```

* **Importar** (botão *Importar pasta…*): escolhe-se a pasta com os CSV (subpastas incluídas).
  Cada ficheiro é lido uma única vez e guardado tipado (números, tempos) na base
  `flightplotter.duckdb`. Ficheiros já importados são ignorados; alterados são substituídos.
* **Consultar**: dias, blocos horários, callsign e classe (chegada / partida / sobrevoo) são
  consultas SQL sobre a base — milissegundos, mesmo com meses de dados.
* **Movimentos**: um callsign no mesmo dia é separado em movimentos distintos quando há um
  intervalo sem plots superior a 300 s. Classificação pela variação de altitude (±500 ft).
* **NMIR**: a base já inclui 46 060 registos callsign→tipo de aeronave; novos Excel NMIR
  importam-se pelo botão *NMIR…*.

A base fica em `%LOCALAPPDATA%\FlightTracker\` (botão 🗄 abre a pasta). Aí fica também o `import.log` com os tempos de cada importação.

## Análises disponíveis

| Aba | Conteúdo |
|---|---|
| Mapa / Tabela | Trajetórias, pontos AIP, lista e tabela de movimentos, detalhe por voo (perfil 3°, violações, relatório imprimível) |
| Final | Deteção de aterragens (FAF virtual, corredor, Alt THR), métricas FAF→THR, separação temporal, corredor no mapa |
| Vel. STAR | Conformidade de IAS nos pontos STAR (CPA por raio), limites editáveis, por waypoint e por operador |
| Vel. APP | Violações por voo e pontos (PESEX/NETVO/OKNIB/THR02, UPKAT/TOPVI/ROKOB/THR20…), histogramas e PPTX; violações por distância na escala da final 12 NM→THR |
| Análise Op. | FAST (pares de chegadas, AA/ADA/ADDA/AD…A, detalhe da final), Análise de Dados (KPIs, 11 gráficos, timeline, tabelas, relatório), Análise Diária (dias/semana, callsigns comuns, relatório), RRMS (ponto 2400 m TWY U6/P), ROT |
| KPIs | Resumo operacional, aproximações, taxa de aterragem rolling 60 min, separações, CDO, IAS STAR, por hora/dia/operador, relatório |
| Pontos | Passagens num ponto com filtro de IAS, sequência num ponto (distância à frente/atrás), pontos personalizados (points.json) |
| Análise IA | Chat com Claude / OpenAI / Mistral / Azure / Groq sobre o resumo das análises (chave guardada localmente) |

Todas as abas exportam para Excel; os relatórios abrem no navegador (Imprimir → Guardar como PDF).
As especificações detalhadas dos algoritmos portados da app antiga estão em `docs/`.

## Correr em desenvolvimento (Windows)

1. Instalar Python 3.11 ou superior (marcar *Add Python to PATH*).
2. Na pasta do projeto: `python -m pip install -r requirements.txt`
3. `python app.py`

## Gerar o executável

* Localmente: duplo clique em `build_windows.bat` → pasta `dist\FlightTracker\` (correr o `FlightTracker.exe` lá dentro; para dar a um colega copia-se a pasta inteira)
* Automático: cada *push* para `main` gera o `.exe` no GitHub Actions
  (separador *Actions* → último run → *Artifacts* → `FlightTracker-windows`).

## Se o .exe não abrir noutro PC

A janela nativa usa o WebView2 do Windows via .NET. Se falhar (pasta dentro do OneDrive, DLL bloqueada, PC muito restrito),
a app **abre automaticamente no navegador predefinido** (Edge/Chrome) — tudo funciona igual. Também podes forçar esse modo
com `FlightTracker.exe --browser`. Recomendações para distribuir: copiar a pasta `FlightTracker` para fora do OneDrive
(ex.: `C:\FlightTracker`) e, se o Windows marcar o zip como "transferido da Internet", botão direito no zip → Propriedades → **Desbloquear** antes de extrair.

## Dados de teste

```
python tools/gerar_csv_teste.py csv_teste 30 40
```
cria 30 dias × 6 blocos de CSV sintéticos em `csv_teste/` para experimentar sem dados reais.

## Estrutura

```
app.py              janela (pywebview) + API chamada pelo JavaScript
core/db.py          DuckDB: importação, tabela de movimentos, consultas, cache de análises
core/geo.py         geometria (haversine, eixo de aproximação), pistas, limites de velocidade, WTC
core/analysis/      final.py (aterragens), fast.py (FAST/Dados/Diária), speeds.py (STAR/APP), ops.py (KPIs/RRMS/ROT/Pontos)
core/service.py     orquestração por sessão (filtro actual, resultados, exportações, relatórios, IA)
core/reports.py     Excel (openpyxl), PPTX (python-pptx), relatórios HTML imprimíveis
core/ia.py          fornecedores de IA e contexto enviado ao modelo
core/filenames.py   interpretação dos nomes LPPT_260415_04-08.csv / LPFR_2026-03-01_00-04.csv
ui/                 interface (HTML/CSS/JS) com Leaflet local
data/               pontos AIP, grupos de pontos, NMIR inicial
tools/              utilitários (gerador de CSV de teste)
```

## Formato dos CSV

Separador `;` ou `,`, cabeçalho na 1ª linha. Colunas reconhecidas (maiúsculas/minúsculas indiferente):
`CSN` (callsign), `TOD` (hh:mm:ss), `LATITUDE`/`LAT`, `LONGITUDE`/`LON`, `MODEC` ou `BAROH`
(altitude; valores < 600 são FL ×100), `TAS`, `IAR`/`IAS`, `ROC`, `GSPA`, `MODES`, `MODEA`, `TRKNR`.
A data e o bloco vêm do nome do ficheiro (ou da pasta); o bloco é confirmado pela hora mínima dos dados.
