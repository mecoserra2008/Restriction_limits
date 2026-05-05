; Inno Setup script for a per-user installer (no admin rights required).
; Compile with the free "Inno Setup Compiler"
; (https://jrsoftware.org/isinfo.php).
;
; Outputs an installer .exe that:
;   * places RestrictionLimits.exe in %LOCALAPPDATA%\Programs\RestrictionLimits
;   * creates a Start-menu shortcut + a desktop icon
;   * does NOT require administrator privileges

#define MyAppName "Restriction Limits"
#define MyAppVersion "0.1.0"
#define MyAppExeName "RestrictionLimits.exe"

[Setup]
AppId={{B5C0E1D2-3F4A-4E0E-9E0F-1234567890AB}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\RestrictionLimits
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=RestrictionLimits-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "..\dist\RestrictionLimits.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
