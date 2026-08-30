[CmdletBinding()]
param(
    [string]$Model = "yolo11n.pt",
    [string]$PiUrl = "http://192.168.15.51:8080",
    [string]$Token = "",
    [string]$RiskLabels = "",
    [string]$RiskZone = "",
    [int]$ImageSize = 320,
    [double]$IntervalSeconds = 0.5,
    [double]$ReportIntervalSeconds = 0.5
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Ambiente virtual não encontrado. No projeto, execute: py -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -e `".[vision]`""
}
$env:CRYSENSE_PI_URL = $PiUrl.TrimEnd('/')
$env:CRYSENSE_VISION_MODEL = if (Test-Path -LiteralPath $Model) { (Resolve-Path -LiteralPath $Model).Path } else { $Model }
$env:CRYSENSE_VISION_TOKEN = $Token
$env:CRYSENSE_VISION_RISK_LABELS = $RiskLabels
$env:CRYSENSE_VISION_RISK_ZONE = $RiskZone
$env:CRYSENSE_VISION_IMAGE_SIZE = $ImageSize
$env:CRYSENSE_VISION_INTERVAL = $IntervalSeconds
$env:CRYSENSE_VISION_REPORT_INTERVAL = $ReportIntervalSeconds

& $python -m crysense.vision_service
