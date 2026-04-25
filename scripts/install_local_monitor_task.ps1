# Instala o monitor de fontes geo-restritas como Task Scheduler do Windows.
#
# Por que: GitHub Actions runners (Azure US-West) recebem ConnectTimeout
# em servidores .gov.br como dadosabertos.almg.gov.br. Yamls com
# `geo_restricted: true` sao pulados em CI e coletados aqui localmente.
#
# Comportamento da tarefa:
# - Roda 1x/dia as 07:23 BRT (10 min depois do CI nas federais)
# - Executa: python -m monitoritcd.main run --only-geo-restricted
# - Usa pythonw.exe (sem janela)
# - Reinicia se falhar (5x, 5min interval)
# - Loga em local-monitor.log
#
# Uso (PowerShell elevado):
#   .\scripts\install_local_monitor_task.ps1
#
# Para remover:
#   schtasks /Delete /TN "MonitorITCD-LocalMonitor" /F
#
# Para rodar imediato:
#   schtasks /Run /TN "MonitorITCD-LocalMonitor"

[CmdletBinding()]
param(
    [string]$RepoPath = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$TaskName = "MonitorITCD-LocalMonitor",
    [string]$ScheduleTime = "07:23"
)

$ErrorActionPreference = "Stop"

$python = Join-Path $RepoPath ".venv\Scripts\pythonw.exe"
$logFile = Join-Path $RepoPath "local-monitor.log"

if (-not (Test-Path $python)) {
    Write-Error "Python venv nao encontrado: $python. Rode 'pip install -e .[dev]' primeiro."
    exit 1
}

$envFile = Join-Path $RepoPath ".env"
if (-not (Test-Path $envFile)) {
    Write-Warning ".env nao encontrado em $envFile."
    Write-Warning "Crie a partir de .env.example com FIREBASE_SERVICE_ACCOUNT_JSON, GEMINI_API_KEY etc."
}

# Wrapper que carrega .env e roda o monitor
$wrapperScript = @"
@echo off
cd /d "$RepoPath"
for /f "usebackq tokens=1,2 delims==" %%a in ("$envFile") do set %%a=%%b
"$python" -m monitoritcd.main run --only-geo-restricted >> "$logFile" 2>&1
"@

$wrapperPath = Join-Path $RepoPath "scripts\_run_local_monitor.bat"
$wrapperScript | Out-File -FilePath $wrapperPath -Encoding ASCII

$taskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>MonitorITCD - coleta diaria de fontes geo-restritas (ALMG e similares)</Description>
    <URI>\$TaskName</URI>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T${ScheduleTime}:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$env:USERNAME</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
    <RestartOnFailure>
      <Interval>PT5M</Interval>
      <Count>5</Count>
    </RestartOnFailure>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>cmd.exe</Command>
      <Arguments>/c "$wrapperPath"</Arguments>
      <WorkingDirectory>$RepoPath</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

$xmlPath = Join-Path $env:TEMP "monitoritcd-local-task.xml"
$taskXml | Out-File -FilePath $xmlPath -Encoding Unicode

schtasks /Query /TN $TaskName 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Removendo tarefa existente..."
    schtasks /Delete /TN $TaskName /F | Out-Null
}

Write-Host "Criando Task Scheduler '$TaskName' (diaria, $ScheduleTime BRT)..."
schtasks /Create /TN $TaskName /XML $xmlPath
Remove-Item $xmlPath -Force

Write-Host ""
Write-Host "Tarefa criada. Para rodar agora (testar):"
Write-Host "  schtasks /Run /TN $TaskName"
Write-Host ""
Write-Host "Logs:"
Write-Host "  $logFile"
Write-Host ""
Write-Host "Status:"
Write-Host "  schtasks /Query /TN $TaskName /V /FO LIST"
Write-Host ""
Write-Host "Remover:"
Write-Host "  schtasks /Delete /TN $TaskName /F"
