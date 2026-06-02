; tgecase_installer.iss
; Inno Setup script for TNE Case
; Pre-requisite: run build_installer.bat first so dist\TNECase\ already exists.

#define AppName      "TNE Case"
#define AppVersion   "1.0.0"
#define AppPublisher "TNE"
#define AppExeName   "TNECase.exe"
#define DistDir      "dist\TNECase"

[Setup]
AppId={{A3F2C1D4-8B56-4E9A-BC12-7D3E5F901234}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisherURL=https://tge.com
AppSupportURL=https://tge.com
AppUpdatesURL=https://tge.com
DefaultDirName={autopf}\TNECase
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=TNECase_Setup_{#AppVersion}
SetupIconFile=optimize\assets\logo.ico
Compression=lzma2/fast
SolidCompression=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
PrivilegesRequiredOverridesAllowed=dialog
; Creates a unique uninstall entry per version so upgrades work cleanly
AppMutex=TGECaseMutex

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "startmenuicon"; Description: "Create a Start Menu shortcut"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; Copy entire PyInstaller output folder
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: startmenuicon
Name: "{autodesktop}\{#AppName}";  Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; Offer to launch app right after install
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up log file written at runtime
Type: files; Name: "{app}\tgecase.log"

[Code]
// Check if a previous version is running before install/uninstall
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // nothing extra needed
  end;
end;
