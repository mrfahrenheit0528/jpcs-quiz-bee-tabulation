$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$files=@(Join-Path $root 'quiz.ps1')+@(Get-ChildItem $PSScriptRoot -Filter '*.ps1' | ForEach-Object FullName)
foreach($file in $files) {
    $tokens=$null; $errors=$null
    [Management.Automation.Language.Parser]::ParseFile($file,[ref]$tokens,[ref]$errors) | Out-Null
    if($errors.Count) { throw ($errors | Out-String) }
    Write-Output "Parsed: $file"
}
Add-Type -Path (Join-Path $PSScriptRoot 'DnsSd.cs')
Write-Output 'Native DNS-SD P/Invoke C# compiled; Windows runtime calls not executed.'
. (Join-Path $PSScriptRoot 'WindowsCommon.ps1')
$cfg=Get-QuizConfig
if($cfg.QUIZ_HOSTNAME -ne 'jpcs-quiz.local' -or $cfg.QUIZ_PORT -ne '5000') { throw 'Unexpected config defaults.' }
Write-Output 'Default configuration parsed.'
# Exercise argument forwarding and subnet arithmetic without Windows host mutations.
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $root 'quiz.ps1'),[ref]$null,[ref]$null)
foreach($name in @('Invoke-QuizDocker','Invoke-QuizCompose')) {
    $definition=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$true)
    . ([scriptblock]::Create($definition.Extent.Text))
}
function global:docker.exe { $script:SeenArguments=@($args); $global:LASTEXITCODE=0 }
$compose=@('compose','-f','compose.yaml','-f','compose.windows.yaml')
Invoke-QuizCompose @('run','--rm','-v','C:\folder with spaces:/import:ro','app')
$expected=$compose+@('run','--rm','-v','C:\folder with spaces:/import:ro','app')
if(($script:SeenArguments -join '|') -ne ($expected -join '|')) { throw 'Docker arguments were not preserved.' }
function Get-NetAdapter { param([switch]$Physical) [pscustomobject]@{Status='Up';Name='Wi-Fi';ifIndex=7} }
function Get-NetIPInterface { param($InterfaceIndex,$AddressFamily) [pscustomobject]@{InterfaceMetric=10} }
function Get-NetIPAddress { param($InterfaceIndex,$AddressFamily) [pscustomobject]@{IPAddress='192.168.10.23';PrefixLength=24;AddressState='Preferred'} }
function Get-NetRoute { param($InterfaceIndex,$DestinationPrefix) [pscustomobject]@{DestinationPrefix='0.0.0.0/0'} }
$lan=Get-QuizLan $cfg
if($lan.ip -ne '192.168.10.23' -or $lan.subnet -ne '192.168.10.0/24' -or $lan.index -ne 7) { throw 'LAN/subnet calculation failed.' }
Write-Output 'Mocked Docker argument forwarding and LAN subnet selection passed.'
