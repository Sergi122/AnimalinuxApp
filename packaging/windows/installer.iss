; Instalador de AnimaWin (AnimaLinux para Windows). Por usuario, sin permisos de administrador — Inno Setup 6.
#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{B7D2E4A1-3C58-4F69-8A17-5E9C0D4B2F63}
AppName=AnimaWin
AppVersion={#Version}
AppPublisher=Sergi122
AppPublisherURL=https://animalinux.web.app
DefaultDirName={localappdata}\Programs\AnimaWin
DefaultGroupName=AnimaWin
PrivilegesRequired=lowest
OutputDir=..\..\build
OutputBaseFilename=AnimaWin-Setup-{#Version}
SetupIconFile=animawin.ico
UninstallDisplayIcon={app}\AnimaWin.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
; cierra una instancia en marcha para poder actualizar los archivos
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\..\build\win-dist\AnimaWin\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\AnimaWin"; Filename: "{app}\AnimaWin.exe"; Parameters: "--show"

[Registry]
; el arranque automático lo activa la propia app; aquí solo se limpia al desinstalar
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "AnimaWin"; Flags: dontcreatekey uninsdeletevalue

[Run]
Filename: "{app}\AnimaWin.exe"; Parameters: "--show"; Description: "Abrir AnimaWin"; Flags: nowait postinstall skipifsilent

Filename: "{app}\AnimaWin.exe"; Parameters: "--daemon"; Flags: nowait runasoriginaluser; Check: WizardSilent

[UninstallRun]
Filename: "{app}\AnimaWin.exe"; Parameters: "--quit"; Flags: runhidden; RunOnceId: "QuitAnimaWin"
