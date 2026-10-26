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
# Firma opcional (Authenticode): si hay certificado, se firma el .exe de la
# app ANTES de empaquetarlo y luego el instalador. Variables de entorno:
#   ANIMAWIN_SIGN_PFX  ruta al .pfx   ANIMAWIN_SIGN_PASS  su contraseña
#   ANIMAWIN_SIGN_TS   servidor de sello de tiempo (por defecto DigiCert)
function Sign-File($path) {
    if (-not $env:ANIMAWIN_SIGN_PFX) { return }
    $signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match 'x64' } | Select-Object -Last 1
    if (-not $signtool) { Write-Warning 'Sin signtool (Windows SDK): no se firma'; return }
    $ts = if ($env:ANIMAWIN_SIGN_TS) { $env:ANIMAWIN_SIGN_TS } else { 'http://timestamp.digicert.com' }
    & $signtool.FullName sign /fd sha256 /tr $ts /td sha256 /f $env:ANIMAWIN_SIGN_PFX /p $env:ANIMAWIN_SIGN_PASS /d 'AnimaWin' $path
}
Get-ChildItem build\win-dist -Filter '*.exe' -Recurse | ForEach-Object { Sign-File $_.FullName }
& $iscc "/DVersion=$Version" 'packaging\windows\installer.iss'
Get-ChildItem build -Filter 'AnimaWin-Setup-*.exe' | ForEach-Object { Sign-File $_.FullName }
Get-ChildItem build -Filter 'AnimaWin-Setup-*.exe' | ForEach-Object { "{0}  {1} MB" -f $_.Name, [int]($_.Length / 1MB) }
