; Instalador por usuario (sin permisos de administrador) — Inno Setup 6.
#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{6F1C3B5E-7A42-4C8E-9D55-A1B2C3D4E5F6}
AppName=AnimaLinux
AppVersion={#Version}
AppPublisher=Sergi122
AppPublisherURL=https://animalinux.web.app
DefaultDirName={localappdata}\Programs\AnimaLinux
DefaultGroupName=AnimaLinux
PrivilegesRequired=lowest
OutputDir=..\..\build
OutputBaseFilename=AnimaLinux-Setup-{#Version}
SetupIconFile=animalinux.ico
UninstallDisplayIcon={app}\AnimaLinux.exe
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
Source: "..\..\build\win-dist\AnimaLinux\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\AnimaLinux"; Filename: "{app}\AnimaLinux.exe"; Parameters: "--show"

[Registry]
; el arranque automático lo activa la propia app; aquí solo se limpia al desinstalar
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "AnimaLinux"; Flags: dontcreatekey uninsdeletevalue

[Run]
Filename: "{app}\AnimaLinux.exe"; Parameters: "--show"; Description: "Abrir AnimaLinux"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\AnimaLinux.exe"; Parameters: "--quit"; Flags: runhidden; RunOnceId: "QuitAnimaLinux"
