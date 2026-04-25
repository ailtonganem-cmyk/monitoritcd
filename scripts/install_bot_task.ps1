# Instala o polling worker do bot como Task Scheduler do Windows.
# Roda como o usuario logado, na inicializacao do sistema, com restart on failure.
#
# Uso (PowerShell elevado):
#   .\scripts\install_bot_task.ps1
#
# Para remover:
#   schtasks /Delete /TN "MonitorITCD-Bot" /F

[CmdletBinding()]
param(
    [string]$RepoPath = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$TaskName = "MonitorITCD-Bot"
)

$ErrorActionPreference = "Stop"

$python = Join-Path $RepoPath ".venv\Scripts\pythonw.exe"
$module = "monitoritcd.bot.poller"
$logFile = Join-Path $RepoPath "bot.log"

if (-not (Test-Path $python)) {
    Write-Error "Python venv nao encontrado: $python. Rode 'pip install -e .[dev]' primeiro."
    exit 1
}

# Carrega env vars do .env (se existir)
$envFile = Join-Path $RepoPath ".env"
if (-not (Test-Path $envFile)) {
    Write-Warning ".env nao encontrado em $envFile. Bot vai falhar sem secrets."
    Write-Warning "Crie .env baseado em .env.example antes de iniciar a tarefa."
}

# XML da tarefa - mais flexivel que schtasks /Create direto
$taskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>MonitorITCD - polling worker do bot Telegram</Description>
    <URI>\$TaskName</URI>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
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
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure>
      <Interval>PT5M</Interval>
      <Count>10</Count>
    </RestartOnFailure>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$python</Command>
      <Arguments>-m $module</Arguments>
      <WorkingDirectory>$RepoPath</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

# Cria a tarefa
$xmlPath = Join-Path $env:TEMP "monitoritcd-bot-task.xml"
$taskXml | Out-File -FilePath $xmlPath -Encoding Unicode

# Remove se ja existe
schtasks /Query /TN $TaskName 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Removendo tarefa existente..."
    schtasks /Delete /TN $TaskName /F | Out-Null
}

Write-Host "Criando Task Scheduler '$TaskName'..."
schtasks /Create /TN $TaskName /XML $xmlPath
Remove-Item $xmlPath -Force

Write-Host ""
Write-Host "Tarefa criada. Para iniciar agora:"
Write-Host "  schtasks /Run /TN $TaskName"
Write-Host ""
Write-Host "Para ver status:"
Write-Host "  schtasks /Query /TN $TaskName /V /FO LIST"
Write-Host ""
Write-Host "Para parar:"
Write-Host "  schtasks /End /TN $TaskName"
Write-Host ""
Write-Host "Para remover:"
Write-Host "  schtasks /Delete /TN $TaskName /F"
