param(
    [string]$PiHost = "crysense"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Release = "/home/crysense/crysense-release-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

Write-Host "Enviando release para $PiHost`:$Release"
& ssh $PiHost "mkdir -p '$Release'"
if ($LASTEXITCODE -ne 0) { throw "Não foi possível criar a pasta remota." }

foreach ($item in @("src", "deploy", "models")) {
    & scp -r (Join-Path $ProjectRoot $item) "${PiHost}:$Release/"
    if ($LASTEXITCODE -ne 0) { throw "Falha ao copiar $item." }
}
foreach ($item in @("pyproject.toml", ".env.example", "README.md")) {
    & scp (Join-Path $ProjectRoot $item) "${PiHost}:$Release/"
    if ($LASTEXITCODE -ne 0) { throw "Falha ao copiar $item." }
}

Write-Host "Instalando no Raspberry (o sudo pode pedir a senha do Raspberry)..."
& ssh -t $PiHost "sudo bash '$Release/deploy/install_pi.sh'"
if ($LASTEXITCODE -ne 0) { throw "O envio terminou, mas a instalação no Raspberry falhou." }

Write-Host "Concluído. Se o instalador solicitar reinicialização, execute: ssh $PiHost 'sudo reboot'. Depois abra http://IP_DO_RASPBERRY:8080 no celular conectado à mesma rede Wi-Fi."
