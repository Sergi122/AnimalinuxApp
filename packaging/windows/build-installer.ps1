# Paso 2 (PowerShell, no MSYS2): empaqueta build\win-dist en AnimaWin-Setup-<version>.exe
# con Inno Setup 6 (se instala solo para el usuario si no está).
param([string]$Version = "0.0.0")
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..\..')
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $tmp = Join-Path $env:TEMP 'innosetup.exe'
    Invoke-WebRequest 'https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe' -OutFile $tmp -UseBasicParsing
    Start-Process $tmp -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CURRENTUSER' -Wait
    $iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
}
& $iscc "/DVersion=$Version" 'packaging\windows\installer.iss'
Get-ChildItem build -Filter 'AnimaWin-Setup-*.exe' | ForEach-Object { "{0}  {1} MB" -f $_.Name, [int]($_.Length / 1MB) }
