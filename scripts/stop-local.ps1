$root = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $root "tmp\local-worker.pids"

$ports = @(8000, 3000)
foreach ($port in $ports) {
  Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object {
      Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
      Write-Host "Stopped process $_ on port $port"
    }
}

if (Test-Path $pidFile) {
  Get-Content $pidFile |
    ForEach-Object {
      Stop-Process -Id ([int]$_) -Force -ErrorAction SilentlyContinue
      Write-Host "Stopped worker process $_"
    }
  Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like '*-m app.worker*' } |
  ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped worker process $($_.ProcessId)"
  }
