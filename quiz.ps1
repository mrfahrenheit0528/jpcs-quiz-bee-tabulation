param([ValidateSet('start','stop','status','doctor','logs','backup')][string]$Command='status')
. "$PSScriptRoot\scripts\WindowsCommon.ps1"
Set-Location $PSScriptRoot
$cfg=Get-QuizConfig
foreach($key in $cfg.Keys) { [Environment]::SetEnvironmentVariable($key,$cfg[$key]) }
$compose=@('compose','-f','compose.yaml','-f','compose.windows.yaml')
function Invoke-QuizDocker {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments)
    & docker.exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker failed: $($Arguments -join ' ')" }
}
function Invoke-QuizCompose {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments)
    Invoke-QuizDocker ($compose+$Arguments)
}
function Stop-Discovery {
    $stop=Join-Path $PSScriptRoot '.quiz\discovery.stop'
    New-Item $stop -ItemType File -Force | Out-Null
    for($i=0;$i -lt 12;$i++) {
        $task=Get-ScheduledTask -TaskName 'JPCS Quiz Discovery' -ErrorAction SilentlyContinue
        if (!$task -or $task.State -ne 'Running') { break }
        Start-Sleep -Seconds 1
    }
    Get-ScheduledTask -TaskName 'JPCS Quiz Discovery' -ErrorAction SilentlyContinue | Stop-ScheduledTask -ErrorAction SilentlyContinue
}
try {
    if (!(Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Install Docker Desktop with Compose and start its Linux engine first.' }
    Invoke-QuizDocker @('compose','version') | Out-Null
    Invoke-QuizDocker @('info','--format','{{.OSType}}') | ForEach-Object { if ($_ -ne 'linux') { throw 'Switch Docker Desktop to Linux containers.' } }
    $endpoint=Invoke-QuizDocker @('context','inspect','--format','{{.Endpoints.docker.Host}}')
    if($Command -eq 'start' -and (!$endpoint.StartsWith('npipe://') -or $env:DOCKER_HOST -match '^(tcp|ssh):')) { throw 'Windows launcher requires the local Docker Desktop context.' }
    New-Item '.quiz' -ItemType Directory -Force | Out-Null
    switch($Command) {
        'stop' { Stop-Discovery; Invoke-QuizCompose @('stop'); break }
        'logs' { Invoke-QuizCompose @('logs','--tail','100','-f'); break }
        'backup' {
            New-Item 'backups' -ItemType Directory -Force | Out-Null
            $stamp=Get-Date -Format 'yyyyMMddTHHmmss'; $name="jpcs-quiz-backup-$stamp"; $file="quiz-$stamp.db"
            try {
                Invoke-QuizCompose @('run','--name',$name,'--no-deps','app','python','-m','website.manage','backup',"/data/backups/$file")
                Invoke-QuizDocker @('cp',"${name}:/data/backups/$file","backups\$file")
                Invoke-QuizDocker @('cp',"${name}:/data/session.key","backups\quiz-$stamp.session.key")
                Write-Host "Backup and session secret saved in backups\quiz-$stamp.*"
            } finally { & docker.exe rm -f $name | Out-Null }
            break
        }
        { $_ -in 'status','doctor' } {
            Invoke-QuizCompose @('ps')
            Get-ScheduledTask -TaskName 'JPCS Quiz Discovery' -ErrorAction SilentlyContinue | Format-Table TaskName,State
            $lan=Get-QuizLan $cfg
            foreach ($address in @('127.0.0.1',$lan.ip,$cfg.QUIZ_HOSTNAME)) {
                $url="http://${address}:$($cfg.QUIZ_PORT)/healthz"
                try { Write-Host "$url $((Invoke-WebRequest -UseBasicParsing $url -TimeoutSec 4).StatusCode)" } catch { Write-Host "$url $($_.Exception.Message)" }
            }
            if($Command -eq 'doctor') {
                Get-ScheduledTaskInfo -TaskName 'JPCS Quiz Discovery' -ErrorAction SilentlyContinue | Format-List LastRunTime,LastTaskResult
                Get-NetTCPConnection -LocalPort $cfg.QUIZ_PORT -State Listen -ErrorAction SilentlyContinue | Format-Table LocalAddress,LocalPort,OwningProcess
                Get-NetFirewallRule -Group 'JPCS Quiz LAN' -ErrorAction SilentlyContinue | Format-Table DisplayName,Enabled,Profile
                Get-Content '.quiz\network.json' -ErrorAction SilentlyContinue
                Write-Host 'Test the direct IP from another device first, then hostname. Local checks do not prove LAN reachability. Check router isolation if IP fails and multicast if only hostname fails.'
            }
            break
        }
        'start' {
            $lan=Get-QuizLan $cfg
            $existing=Invoke-QuizCompose @('ps','-q','app')
            $currentPort=$null
            if($existing) { $entries=(Invoke-QuizDocker @('inspect','--format','{{json .Config.Env}}',$existing)) | ConvertFrom-Json; $currentPort=($entries | Where-Object { $_ -like 'QUIZ_PORT=*' }) -replace '^QUIZ_PORT=','' }
            if ((!$existing -or $currentPort -ne $cfg.QUIZ_PORT) -and (Get-NetTCPConnection -LocalPort $cfg.QUIZ_PORT -State Listen -ErrorAction SilentlyContinue)) { throw "Port $($cfg.QUIZ_PORT) already belongs to another process." }
            $paths=@('Dockerfile','requirements.txt','main.py')+@(Get-ChildItem 'website' -Recurse -File | Where-Object { $_.FullName -notmatch '__pycache__' } | Sort-Object FullName | ForEach-Object FullName)
            $fingerprint=($paths | ForEach-Object { (Get-FileHash $_ -Algorithm SHA256).Hash }) -join ''
            $old=if(Test-Path '.quiz\image.sha256'){Get-Content '.quiz\image.sha256' -Raw}else{''}
            $image=Invoke-QuizDocker @('image','ls','-q','jpcs-quiz:local')
            if(!$image -or $old -ne $fingerprint) { Invoke-QuizCompose @('build'); [IO.File]::WriteAllText((Join-Path $PSScriptRoot '.quiz\image.sha256'),$fingerprint) }
            if(!$existing) { Invoke-QuizCompose @('run','--rm','--no-deps','-v',"${PSScriptRoot}\instance:/import:ro",'app','python','-m','website.manage','import','/import/database.db') }
            $desired=@{subnet=$lan.subnet; interface=$lan.interface; port=$cfg.QUIZ_PORT}
            $oldFirewall=if(Test-Path '.quiz\firewall.json'){Get-Content '.quiz\firewall.json' -Raw | ConvertFrom-Json}else{$null}
            $profile=Get-NetConnectionProfile -InterfaceIndex $lan.index
            if(!$oldFirewall -or $oldFirewall.subnet -ne $lan.subnet -or $oldFirewall.interface -ne $lan.interface -or $oldFirewall.port -ne $cfg.QUIZ_PORT -or $profile.NetworkCategory -ne 'Private' -or !(Get-NetFirewallRule -Name 'JPCS-Quiz-HTTP' -ErrorAction SilentlyContinue)) {
                Write-Host 'Configuring the selected event LAN as Private and adding scoped JPCS firewall rules (administrator elevation).'
                $script=Join-Path $PSScriptRoot 'scripts\setup_windows.ps1'
                $args="-NoProfile -ExecutionPolicy Bypass -File `"$script`" -InterfaceIndex $($lan.index) -Subnet $($lan.subnet) -Port $($cfg.QUIZ_PORT)"
                $process=Start-Process powershell.exe -Verb RunAs -ArgumentList $args -Wait -PassThru
                if($process.ExitCode -ne 0) { throw 'Administrator host setup failed.' }
                $desired | ConvertTo-Json | Set-Content '.quiz\firewall.json'
            }
            Invoke-QuizCompose @('up','-d','--no-build','--wait','--wait-timeout','90')
            Stop-Discovery
            $cfg | ConvertTo-Json | Set-Content '.quiz\windows-config.json'
            Remove-Item '.quiz\discovery.stop' -ErrorAction SilentlyContinue
            # No triggers: start manually each event; survives terminal closure, never starts at boot.
            $action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\scripts\discovery_windows.ps1`"" -WorkingDirectory $PSScriptRoot
            $settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
            $principal=New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
            Register-ScheduledTask -TaskName 'JPCS Quiz Discovery' -Action $action -Settings $settings -Principal $principal -Force | Out-Null
            $started=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
            Start-ScheduledTask -TaskName 'JPCS Quiz Discovery'
            $discovery='Discovery has not reported readiness; run quiz.ps1 doctor.'
            for($i=0;$i -lt 24;$i++) {
                try {
                    $state=Get-Content '.quiz\network.json' -Raw | ConvertFrom-Json
                    if($state.updated_at -ge $started -and $state.status -in @('ready','error','warning')) { $discovery=$state.message; break }
                } catch {}
                Start-Sleep -Milliseconds 500
            }
            Write-Host "HTTP server is healthy. Discovery: $discovery"
            Write-Host "Hostname: http://$($cfg.QUIZ_HOSTNAME):$($cfg.QUIZ_PORT)"
            Write-Host "Direct IP: http://$($lan.ip):$($cfg.QUIZ_PORT)"
            Write-Host 'Run quiz.ps1 doctor to inspect discovery. Terminal can close; run start again after reboot.'
            break
        }
    }
} catch { Write-Error $_; exit 1 }
