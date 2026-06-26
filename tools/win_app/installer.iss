; OCR Adjudicator — Windows installer (Inno Setup 6).
;
; Compiled by tools/build_win_app.ps1, which passes:
;   /DAppDir=<staged app folder>   (OCRAdjudicator.exe + runtime + site\)
;   /DOutDir=<output folder>       (where Setup.exe is written)
;   /DBootstrapper=<path>          (optional MicrosoftEdgeWebView2Setup.exe)
;
; Produces a single OCR-Adjudicator-Setup.exe a collaborator double-clicks: it installs the
; self-contained app, makes Start-menu / desktop shortcuts, and installs the WebView2 runtime
; only if it is missing. Per-user install by default (no admin required).

#define MyAppName "OCR Adjudicator"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "p-aldighieri"
#define MyAppExeName "OCRAdjudicator.exe"

#ifndef AppDir
  #define AppDir "..\..\dist-win\app"
#endif
#ifndef OutDir
  #define OutDir "..\..\dist-win"
#endif

[Setup]
AppId={{05370F6E-20B9-4CA5-86B5-C31F6045764F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\OCR Adjudicator
DisableProgramGroupPage=yes
DisableDirPage=auto
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
OutputDir={#OutDir}
OutputBaseFilename=OCR-Adjudicator-Setup
SetupIconFile={#AppDir}\app.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Per-user by default so no admin prompt; user may choose all-users in the dialog.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#AppDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
#ifdef Bootstrapper
Source: "{#Bootstrapper}"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: WebView2Missing
#endif

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
#ifdef Bootstrapper
Filename: "{tmp}\MicrosoftEdgeWebView2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installing Microsoft WebView2 runtime…"; Check: WebView2Missing; Flags: waituntilterminated
#endif
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
function WebView2Missing: Boolean;
var v: String;
begin
  Result := True;
  // Evergreen WebView2 Runtime client GUID; present (machine or per-user) => already installed.
  if RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v) and (v <> '') and (v <> '0.0.0.0') then
    Result := False;
  if Result and RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v) and (v <> '') and (v <> '0.0.0.0') then
    Result := False;
end;
