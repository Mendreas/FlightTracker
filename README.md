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
| KPIs | KPIs PRU/EUROCONTROL (throughput e capacidade, taxi adicional, ASMA, pontualidade, ATFM, CDO, go-arounds), resumo operacional, aproximações, separações, IAS STAR; relatório mensal e relatórios à medida |
| Painel | Evolução diária de toda a base com referência (ano anterior…), comparação A/B, top 10, qualidade dos dados por dia |
| Solo | Movimentos no solo (ficheiro da torre / A-SMGCS) sobre a rede OSM de LPPT, replay ar + solo, ROT e taxi |
| Cruzamento | Radar × NMIR × torre × OPDI por movimento, discrepâncias, correções guardadas, Excel |
| Pontos | Passagens num ponto com filtro de IAS, sequência num ponto (distância à frente/atrás), pontos personalizados (points.json) |
| Análise IA | Chat com Claude / OpenAI / Mistral / Azure / Groq sobre o resumo das análises (chave guardada localmente) |

Todas as abas exportam para Excel; os relatórios abrem no navegador (Imprimir → Guardar como PDF).
As especificações detalhadas dos algoritmos portados da app antiga estão em `docs/`.

## Correr em desenvolvimento (Windows)

1. Instalar Python 3.11 ou superior (marcar *Add Python to PATH*).
2. Na pasta do projeto: `python -m pip install -r requirements.txt`
3. `python app.py`

## Ramos

* `main` — versão madura. Só aqui se geram o instalador e as releases que os colegas descarregam.
* `dev` — desenvolvimento. Cada *push* gera artefactos (Actions → *Artifacts*) para testar, sem mexer nas releases.
  Quando uma versão está pronta: subir `VERSION` em `app.py`, acrescentar ao `data/changelog.json`, e fundir `dev` em `main`.

## Instalar / distribuir

Cada *push* para `main` gera automaticamente (GitHub Actions → *Build Windows exe*):

| O quê | Onde |
|---|---|
| Instalador Windows (`FlightTracker-Setup.exe`, instala em `%LOCALAPPDATA%\Programs\FlightTracker`, sem direitos de administrador) | [Release *latest*](https://github.com/Mendreas/FlightTracker/releases/latest) — link fixo `releases/download/latest/FlightTracker-Setup.exe` |
| DMG macOS (`FlightTracker-macOS.dmg`) | idem — `releases/download/latest/FlightTracker-macOS.dmg` |
| Pasta portátil (zip, sem instalar) | idem — `FlightTracker-windows-portable.zip` |
| Release com o número da versão (`v4.0.0`, …) | [Releases](https://github.com/Mendreas/FlightTracker/releases) — fica o histórico |

A versão vem de `VERSION` em `app.py`; o histórico de alterações está em `data/changelog.json` e aparece na app em
**Preferências → Histórico de versões**, onde o botão **✉ Email de novidades** abre no Outlook um rascunho formatado
com as novidades e os links de download. Para lançar uma versão nova: atualizar `VERSION`, acrescentar a entrada no
`changelog.json` e fazer *push*.

Localmente: duplo clique em `build_windows.bat` → pasta `dist\FlightTracker\` (correr o `FlightTracker.exe` lá dentro).

## Se o .exe não abrir noutro PC

A janela nativa usa o WebView2 do Windows via .NET. Se falhar (pasta dentro do OneDrive, DLL bloqueada, PC muito restrito),
a app **abre automaticamente no navegador predefinido** (Edge/Chrome) — tudo funciona igual. Também podes forçar esse modo
com `FlightTracker.exe --browser`. Recomendações para distribuir: copiar a pasta `FlightTracker` para fora do OneDrive
(ex.: `C:\FlightTracker`) e, se o Windows marcar o zip como "transferido da Internet", botão direito no zip → Propriedades → **Desbloquear** antes de extrair.

## iPad / outros dispositivos

Correr `FlightTracker.exe --lan` (há um atalho no menu Iniciar). A app passa a responder na porta 8765 para toda a rede local; em Preferências aparece o endereço a abrir no Safari do iPad (mesma rede Wi-Fi). Importações e relatórios ficam no PC. Não há autenticação — só em rede interna.

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

## Guia de utilização

O texto do guia está em `docs/guia_utilizacao.md`. O PDF distribuído na app (`ui/Guia_FlightTracker.pdf`) é a versão formatada em Word pelo Paulo (capa NAV/GOPLIS); `python tools/build_guide.py` gera uma versão alternativa simples com reportlab quando não houver Word atualizado.
