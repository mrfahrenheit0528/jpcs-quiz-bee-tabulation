param([Parameter(Mandatory=$true)][int]$InterfaceIndex,[Parameter(Mandatory=$true)][string]$Subnet,[Parameter(Mandatory=$true)][int]$Port)
$ErrorActionPreference='Stop'
$profile=Get-NetConnectionProfile -InterfaceIndex $InterfaceIndex
if ($profile.NetworkCategory -ne 'Private') { Set-NetConnectionProfile -InterfaceIndex $InterfaceIndex -NetworkCategory Private }
$alias=(Get-NetAdapter -InterfaceIndex $InterfaceIndex).Name
Get-NetFirewallRule -Group 'JPCS Quiz LAN' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -Name 'JPCS-Quiz-HTTP' -DisplayName 'JPCS Quiz HTTP' -Group 'JPCS Quiz LAN' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -RemoteAddress $Subnet -InterfaceAlias $alias -Profile Private | Out-Null
New-NetFirewallRule -Name 'JPCS-Quiz-mDNS' -DisplayName 'JPCS Quiz mDNS' -Group 'JPCS Quiz LAN' -Direction Inbound -Action Allow -Protocol UDP -LocalPort 5353 -RemoteAddress $Subnet -InterfaceAlias $alias -Profile Private | Out-Null
