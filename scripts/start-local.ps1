$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backendPython = Join-Path $root "backend\.venv\Scripts\python.exe"
$tmpDir = Join-Path $root "tmp"
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
$pidFile = Join-Path $tmpDir "local-worker.pids"
Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue

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

$workerPids = @()
try {
  if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker compose up -d redis 2>$null | Out-Null
    Start-Sleep -Seconds 1
  }
  & $backendPython -c "from redis import Redis; from app.core.config import get_settings; Redis.from_url(get_settings().redis_url).ping()" `
    2>$null | Out-Null
  $workerCount = if ($env:UPTUBE_WORKER_COUNT) { [int]$env:UPTUBE_WORKER_COUNT } else { 2 }
  for ($i = 0; $i -lt $workerCount; $i++) {
    $worker = Start-Process `
      -FilePath $backendPython `
      -ArgumentList @("-m", "app.worker") `
      -WorkingDirectory (Join-Path $root "backend") `
      -WindowStyle Hidden `
      -PassThru
    $workerPids += $worker.Id
  }
} catch {
  Write-Host "Redis worker not started; API will use local background tasks."
}

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
if ($workerPids.Count -gt 0) {
  $workerPids | Set-Content -Path $pidFile
  Write-Host "Worker PIDs: $($workerPids -join ', ')"
}
Write-Host "Frontend PID: $($frontend.Id) http://localhost:3000"
Write-Host "Frontend logs: $frontendOutLog ; $frontendErrLog"
