; Instalador Windows do FlightTracker (Inno Setup 6)
; Compilado no GitHub Actions: ISCC.exe /DAppVersion=4.0.0 installer\FlightTracker.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{7E2B1C44-6B1F-4E0C-9C3A-5A1D2F8E9B07}
AppName=FlightTracker
AppVersion={#AppVersion}
AppVerName=FlightTracker {#AppVersion}
AppPublisher=NAV Portugal - GOPLIS
AppPublisherURL=https://github.com/Mendreas/FlightTracker
DefaultDirName={localappdata}\Programs\FlightTracker
DefaultGroupName=FlightTracker
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=FlightTracker-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\FlightTracker.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\Portuguese.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\FlightTracker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\FlightTracker"; Filename: "{app}\FlightTracker.exe"
Name: "{group}\FlightTracker (no navegador)"; Filename: "{app}\FlightTracker.exe"; Parameters: "--browser"
Name: "{autodesktop}\FlightTracker"; Filename: "{app}\FlightTracker.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FlightTracker.exe"; Description: "{cm:LaunchProgram,FlightTracker}"; Flags: nowait postinstall skipifsilent

[InstallDelete]
; limpa ficheiros de versões anteriores (a base de dados em %LOCALAPPDATA%\FlightTracker não é tocada)
Type: filesandordirs; Name: "{app}\_internal"
