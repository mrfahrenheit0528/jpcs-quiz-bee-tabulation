param([ValidateRange(1024,65535)][int]$Port=5059, [string]$Interface='')
$ErrorActionPreference='Stop'
. "$PSScriptRoot\WindowsCommon.ps1"
$lan=Get-QuizLan @{QUIZ_INTERFACE=$Interface}
$profile=Get-NetConnectionProfile -InterfaceIndex $lan.index
if ($profile.NetworkCategory -ne 'Private') { throw 'The preview LAN must already be a trusted Private network.' }
$name="JPCS-Quiz-Preview-$Port"
$rule=Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue
if ($rule) { $rule | Remove-NetFirewallRule }
New-NetFirewallRule -Name $name -DisplayName "JPCS Quiz Preview ($Port)" -Group 'JPCS Quiz Preview' `
    -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -RemoteAddress $lan.subnet `
    -InterfaceAlias $lan.interface -Profile Private | Out-Null
New-Item (Join-Path $QuizRoot '.quiz') -ItemType Directory -Force | Out-Null
"Allowed TCP $Port on Private $($lan.interface) from $($lan.subnet). URL: http://$($lan.ip):$Port" |
    Set-Content (Join-Path $QuizRoot '.quiz\preview-firewall.log')
