$ErrorActionPreference = 'Stop'
$QuizRoot = Split-Path $PSScriptRoot -Parent
function Get-QuizConfig {
    $cfg = @{ QUIZ_HOSTNAME='jpcs-quiz.local'; QUIZ_PORT='5000'; QUIZ_INTERFACE=''; QUIZ_VOLUME='jpcs-quiz-data' }
    $path = Join-Path $QuizRoot 'quiz.env'
    if (Test-Path $path) {
        foreach ($line in Get-Content $path) {
            $line=$line.Trim()
            if (!$line -or $line.StartsWith('#')) { continue }
            $parts=$line.Split(@('='),2)
            if ($parts.Count -ne 2 -or !$cfg.ContainsKey($parts[0])) { throw "Invalid quiz.env line: $line" }
            $cfg[$parts[0]]=$parts[1].Trim()
        }
    }
    foreach ($key in @($cfg.Keys)) {
        $value=[Environment]::GetEnvironmentVariable($key)
        if ($null -ne $value) { $cfg[$key]=$value }
    }
    if ($cfg.QUIZ_HOSTNAME -notmatch '^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.local$') { throw 'Invalid .local hostname.' }
    if ($cfg.QUIZ_PORT -notmatch '^\d+$' -or [int]$cfg.QUIZ_PORT -lt 1024 -or [int]$cfg.QUIZ_PORT -gt 65535) { throw 'Port must be 1024..65535.' }
    if ($cfg.QUIZ_VOLUME -notmatch '^[a-zA-Z0-9][a-zA-Z0-9_.-]*$') { throw 'Invalid volume name.' }
    return $cfg
}
function Get-QuizLan($cfg) {
    $adapters = @(Get-NetAdapter -Physical | Where-Object { $_.Status -eq 'Up' -and (!$cfg.QUIZ_INTERFACE -or $_.Name -eq $cfg.QUIZ_INTERFACE) })
    $items = @()
    foreach ($adapter in $adapters) {
        $metric = (Get-NetIPInterface -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4).InterfaceMetric
        foreach ($addr in @(Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.AddressState -eq 'Preferred' })) {
            $bytes=[Net.IPAddress]::Parse($addr.IPAddress).GetAddressBytes()
            $remaining=[int]$addr.PrefixLength
            for($i=0;$i -lt 4;$i++) { $bits=[Math]::Min(8,[Math]::Max(0,$remaining)); $bytes[$i]=$bytes[$i] -band (256-[Math]::Pow(2,8-$bits)); $remaining-=8 }
            $subnet=([Net.IPAddress]::new($bytes)).ToString()+'/'+$addr.PrefixLength
            $gateway = @(Get-NetRoute -InterfaceIndex $adapter.ifIndex -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue)
            $items += [pscustomobject]@{ interface=$adapter.Name; index=$adapter.ifIndex; ip=$addr.IPAddress; subnet=$subnet; metric=($(if($gateway.Count){0}else{10000})+$metric) }
        }
    }
    $lan=$items | Sort-Object metric | Select-Object -First 1
    if (!$lan) { throw 'No active physical LAN IPv4 interface. Join the event router or set QUIZ_INTERFACE.' }
    return $lan
}
function Write-QuizNetwork($state) {
    $state.updated_at=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $file=Join-Path $QuizRoot '.quiz\network.json'
    $temp=$file+'.tmp'
    [IO.File]::WriteAllText($temp,($state | ConvertTo-Json),[Text.UTF8Encoding]::new($false))
    Move-Item -Force $temp $file
}
