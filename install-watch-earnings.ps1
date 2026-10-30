$ErrorActionPreference = 'Stop'
$taskPython = (& py -c 'import sys;print(sys.executable)').Trim()
$taskPythonw = Join-Path (Split-Path $taskPython) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $taskPythonw)) { throw 'pythonw.exe not found' }
$taskRoot = $PSScriptRoot
$taskScript = Join-Path $taskRoot 'watch_earnings.py'
$taskUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $taskUser -LogonType Interactive -RunLevel Limited
$taskSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -MultipleInstances IgnoreNew -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5)
$taskTriggers = @('07:00','12:00') | ForEach-Object {
    $taskTrigger = New-ScheduledTaskTrigger -Daily -At $_
    $taskTrigger.StartBoundary = ([datetime]$taskTrigger.StartBoundary).ToString('yyyy-MM-ddTHH:mm:ss') + '+09:00'
    $taskTrigger
}
$taskAction = New-ScheduledTaskAction -Execute $taskPythonw -Argument ('"'+$taskScript+'"') -WorkingDirectory $taskRoot
Register-ScheduledTask -TaskPath '\StockAutomation\' -TaskName 'kabulog-notes-earnings' -Action $taskAction -Trigger $taskTriggers -Settings $taskSettings -Principal $taskPrincipal -Description 'Kabulog public watchlist earnings reminders: 7 days and 1 day before; checks 07:00 and 12:00 JST.' -Force | Out-Null
Write-Output 'Registered earnings checks at 07:00 and 12:00 JST.'
