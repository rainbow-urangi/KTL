param(
    [ValidateRange(0, 65535)][int]$Port = 8000,
    [string]$Python = ''
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
    $Python = Join-Path $projectRoot '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw 'Python 환경이 없습니다. 프로젝트 폴더에서 py -3.12 -m venv .venv 실행 후 requirements.txt를 설치하세요.'
}
& $Python -B -X utf8 (Join-Path $PSScriptRoot 'start_local.py') --port $Port
exit $LASTEXITCODE
