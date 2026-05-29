<#
  gerar-com-chave.ps1
  --------------------------------------------------------------
  Injeta a API Key do Claude (Anthropic) no FlightTracker,
  substituindo o placeholder __ANTHROPIC_API_KEY__ pelo valor real.

  O CODIGO-FONTE fica sempre com o placeholder (sem segredo).
  Este script gera um ficheiro NOVO (…-com-chave.html) que ja
  leva a chave embutida — esse e o que instalas/distribuis.

  IMPORTANTE: a substituicao e feita ao nivel dos BYTES (Latin-1,
  mapeamento 1:1) para NAO corromper a codificacao do HTML
  (acentos, emojis, Leaflet, BOM, etc.). O placeholder e a chave
  sao ASCII, por isso a troca e segura.

  AVISO: a chave fica VISIVEL no HTML gerado. Nao o publiques nem
  o deixes sincronizar para a cloud (OneDrive, etc.).

  ORIGEM DA CHAVE (por ordem de prioridade):
    1) Variavel de ambiente  ANTHROPIC_API_KEY
    2) Ficheiro local        chave.txt  (na mesma pasta; fora do git)

  USO (a partir da pasta FlightTracker):
    Set-Content -Path "chave.txt" -Value "sk-ant-..." -NoNewline
    powershell -ExecutionPolicy Bypass -File ".\gerar-com-chave.ps1"
#>

param(
  # Por defeito assume o build em dist\index.html
  [string]$Source = ".\dist\index.html",

  # Se nao indicado, gera "<nome>-com-chave.html" ao lado do original
  [string]$Output,

  # Caminho do ficheiro com a chave (opcao B)
  [string]$KeyFile = "chave.txt"
)

$ErrorActionPreference = "Stop"
$placeholder = "__ANTHROPIC_API_KEY__"

# 1) Obter a chave
$key = $env:ANTHROPIC_API_KEY
if ([string]::IsNullOrWhiteSpace($key)) {
  if (Test-Path $KeyFile) {
    $key = (Get-Content -Raw -Path $KeyFile).Trim()
  }
}
if ([string]::IsNullOrWhiteSpace($key)) {
  Write-Error "Sem chave. Define `$env:ANTHROPIC_API_KEY ou cria o ficheiro '$KeyFile' com a chave."
  exit 1
}
if ($key -notmatch '^sk-ant-') {
  Write-Warning "A chave nao comeca por 'sk-ant-'. Continua na mesma, mas confirma que esta correta."
}
if ($key -match '[^\x00-\x7F]') {
  Write-Error "A chave contem caracteres nao-ASCII. Verifica se copiaste a chave correta."
  exit 1
}

# 2) Ler o HTML como BYTES e tratar como Latin-1 (byte<->char 1:1)
if (-not (Test-Path $Source)) { Write-Error "Origem nao encontrada: $Source"; exit 1 }
$enc   = [System.Text.Encoding]::GetEncoding('iso-8859-1')
$bytes = [System.IO.File]::ReadAllBytes((Resolve-Path $Source))
$html  = $enc.GetString($bytes)

if ($html.IndexOf($placeholder) -lt 0) {
  Write-Error "Placeholder '$placeholder' nao encontrado em '$Source'. Ja foi substituido ou o ficheiro e diferente."
  exit 1
}

# 3) Substituir o placeholder pela chave real (ASCII -> seguro em Latin-1)
$html = $html.Replace($placeholder, $key)

# 4) Definir o destino
if ([string]::IsNullOrWhiteSpace($Output)) {
  $dir  = Split-Path -Parent (Resolve-Path $Source)
  $name = [IO.Path]::GetFileNameWithoutExtension($Source)
  $Output = Join-Path $dir ("$name-com-chave.html")
}

# 5) Escrever de volta os MESMOS bytes (preserva a codificacao original)
[System.IO.File]::WriteAllBytes($Output, $enc.GetBytes($html))

Write-Host "OK -> chave injetada em:" -ForegroundColor Green
Write-Host "   $Output"
Write-Host "Distribui/instala ESTE ficheiro. Mantem o original (com placeholder) no git." -ForegroundColor Yellow
