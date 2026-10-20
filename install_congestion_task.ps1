# Existing Windows scheduler integration; only this task/config entry is changed.
$ErrorActionPreference = 'Stop'
$taskId = 'callcenter-congestion'
$automationDir = 'C:\Users\yt\automation'
$pythonPath = 'C:\Users\yt\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$pythonWindowlessPath = Join-Path (Split-Path $pythonPath) 'pythonw.exe'
$configPath = Join-Path $automationDir 'tasks.json'
$projectDir = $PSScriptRoot
foreach ($requiredPath in @($pythonPath, $pythonWindowlessPath, $configPath, (Join-Path $automationDir 'run_task.py'), (Join-Path $projectDir 'fetch_congestion.py'))) {
    if (!(Test-Path -LiteralPath $requiredPath)) { throw "Missing: $requiredPath" }
}
if ((Get-TimeZone).Id -ne 'Tokyo Standard Time') { throw 'Scheduler requires Japan time on this PC' }
$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$entry = [pscustomobject]@{
    cwd = $projectDir.Replace('\', '/')
    python = $pythonPath.Replace('\', '/')
    steps = ,@('fetch_congestion.py')
    add = @('docs/data_congestion')
    commit = 'Record call-center congestion guidance for {date}'
    timeout = 600
    schedule = '00:00,12:00 daily JST'
}
$config | Add-Member -NotePropertyName $taskId -NotePropertyValue $entry -Force
$configText = $config | ConvertTo-Json -Depth 20
# Verify serialization of the nested argument array before writing.
$check = $configText | ConvertFrom-Json
if ($check.$taskId.steps[0][0] -ne 'fetch_congestion.py') { throw 'Invalid step arguments' }
Copy-Item -LiteralPath $configPath -Destination ($configPath + '.bak-congestion-' + (Get-Date -Format 'yyyyMMddHHmmss'))
[IO.File]::WriteAllText($configPath, $configText + "`n", [Text.UTF8Encoding]::new($false))
$action = New-ScheduledTaskAction -Execute $pythonWindowlessPath -Argument ('"' + (Join-Path $automationDir 'run_task.py') + '" ' + $taskId) -WorkingDirectory $automationDir
$triggers = @((New-ScheduledTaskTrigger -Daily -At '00:00'), (New-ScheduledTaskTrigger -Daily -At '12:00'))
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskId -TaskPath '\StockAutomation\' -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Description '証券各社の混雑目安を毎日0時・12時に観測し、内容比較履歴をGitHub Pagesへ公開' -Force
Get-ScheduledTaskInfo -TaskName $taskId -TaskPath '\StockAutomation\'
