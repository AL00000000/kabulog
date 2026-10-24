$ErrorActionPreference = 'Stop'
$taskPython = (& py -c 'import sys;print(sys.executable)').Trim()
$taskPythonw = Join-Path (Split-Path $taskPython) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $taskPythonw)) { throw 'pythonw.exe was not found.' }
$taskScript = Join-Path $PSScriptRoot 'watch_notify.py'
$taskUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $taskUser -LogonType Interactive -RunLevel Limited
$taskSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 8) -MultipleInstances IgnoreNew -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5)
foreach ($taskMode in @('daily','weekly')) {
    $taskTrigger = if ($taskMode -eq 'daily') { New-ScheduledTaskTrigger -Daily -At '17:10' } else { New-ScheduledTaskTrigger -Weekly -DaysOfWeek Wednesday -At '12:00' }
    # Explicit JST offset keeps the schedule stable if Windows timezone changes.
    $taskTrigger.StartBoundary = ([datetime]$taskTrigger.StartBoundary).ToString('yyyy-MM-ddTHH:mm:ss') + '+09:00'
    $taskAction = New-ScheduledTaskAction -Execute $taskPythonw -Argument ('"'+$taskScript+'" '+$taskMode) -WorkingDirectory $PSScriptRoot
    Register-ScheduledTask -TaskPath '\StockAutomation\' -TaskName ('kabulog-notes-'+$taskMode) -Action $taskAction -Trigger $taskTrigger -Settings $taskSettings -Principal $taskPrincipal -Description 'Kabulog watched stocks to Discord; daily close return / Wednesday open-to-open weekly return.' -Force | Out-Null
}
Write-Output 'Registered daily 17:10 JST and Wednesday 12:00 JST notifications.'
