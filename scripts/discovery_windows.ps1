. "$PSScriptRoot\WindowsCommon.ps1"
try { Add-Type -Path "$PSScriptRoot\DnsSd.cs" }
catch { Write-QuizNetwork @{status='error';message="DNS-SD companion failed to load: $($_.Exception.Message)"}; throw }
$saved=Get-Content (Join-Path $QuizRoot '.quiz\windows-config.json') -Raw | ConvertFrom-Json
$cfg=@{}
foreach($property in $saved.PSObject.Properties) { $cfg[$property.Name]=$property.Value }
$stop=Join-Path $QuizRoot '.quiz\discovery.stop'
$previous=''; $registration=$null; $state=@{}
try {
    while (!(Test-Path $stop)) {
        try {
            $lan=Get-QuizLan $cfg
            $key="$($lan.index)/$($lan.ip)/$($lan.subnet)"
            if ($key -ne $previous -or !$registration) {
                if ($registration) { $registration.Dispose(); $registration=$null }
                $state=@{ip=$lan.ip; interface=$lan.interface; status='starting'; message='Registering hostname and HTTP service.'}
                Write-QuizNetwork $state
                $registration=[QuizDnsSd]::new($cfg.QUIZ_HOSTNAME,$lan.ip,[ushort]$cfg.QUIZ_PORT,[uint32]$lan.index)
                $previous=$key
            }
            $state=@{ip=$lan.ip; interface=$lan.interface; status='ready'; message='Hostname and HTTP service advertised. Test from another device.'}
            $firewall=Get-Content (Join-Path $QuizRoot '.quiz\firewall.json') -Raw | ConvertFrom-Json
            if ($firewall.subnet -ne $lan.subnet) { $state.status='warning'; $state.message='LAN subnet changed. Run quiz start again to update the firewall rules.' }
        } catch {
            if ($registration) { $registration.Dispose(); $registration=$null }
            $state.status='error'; $state.message="Hostname collision or discovery failure; use direct IP. $($_.Exception.Message)"
        }
        Write-QuizNetwork $state
        for($i=0;$i -lt 10 -and !(Test-Path $stop);$i++) { Start-Sleep -Milliseconds 500 }
    }
} finally {
    if ($registration) { $registration.Dispose() }
    $state.status='stopped'; $state.message='Discovery stopped.'; Write-QuizNetwork $state
}
