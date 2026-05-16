$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backendPython = Join-Path $root "backend\.venv\Scripts\python.exe"

if (!(Test-Path $backendPython)) {
  throw "Backend venv not found. Run: python -m venv backend\.venv; backend\.venv\Scripts\python.exe -m pip install -e '.\backend[dev]'"
}

$ports = @(8000, 3000)
foreach ($port in $ports) {
  Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
}
Start-Sleep -Milliseconds 500

$backend = Start-Process `
  -FilePath $backendPython `
  -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") `
  -WorkingDirectory (Join-Path $root "backend") `
  -WindowStyle Hidden `
  -PassThru

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$frontendOutLog = Join-Path $root "frontend\dev.$stamp.out.log"
$frontendErrLog = Join-Path $root "frontend\dev.$stamp.err.log"

$frontend = Start-Process `
  -FilePath "npm.cmd" `
  -ArgumentList @("run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000") `
  -WorkingDirectory (Join-Path $root "frontend") `
  -WindowStyle Hidden `
  -RedirectStandardOutput $frontendOutLog `
  -RedirectStandardError $frontendErrLog `
  -PassThru

Write-Host "Backend PID: $($backend.Id)  http://127.0.0.1:8000"
Write-Host "Frontend PID: $($frontend.Id) http://localhost:3000"
Write-Host "Frontend logs: $frontendOutLog ; $frontendErrLog"
