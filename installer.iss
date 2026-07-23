; Inno Setup script for dcad -- turns the single dist\dcad.exe (built via
; `pyinstaller dcad.spec`) into a real double-click installer: a wizard
; that installs to Program Files, adds Start Menu/Desktop shortcuts, and
; registers an uninstaller in "Add or Remove Programs".
;
; Must run ON WINDOWS, after the PyInstaller build (dist\dcad.exe must
; already exist -- see README.md "Packaging as an executable").
;
; Build steps:
;   1. Install Inno Setup: https://jrsoftware.org/isdl.php (free)
;   2. pyinstaller dcad.spec        (produces dist\dcad.exe)
;   3. iscc installer.iss           (or open this file in the Inno Setup
;                                     IDE and click Compile)
; Output: installer_output\dcad-setup.exe -- that's the one file to hand
; to a user; running it is the whole "single click and install" experience.

#define MyAppName "dcad"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "dcad"
#define MyAppExeName "dcad.exe"

[Setup]
AppId={{B6E6C9C1-6B3B-4B7B-9B0B-6B7B6C9C1B6E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=dcad-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; No admin rights required -- installs per-user under Program Files by
; default via {autopf}; Inno elevates automatically only if needed.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
; Single-file EXE build from dcad.spec -- adjust the source path here if
; you instead used the folder-build alternative in dcad.spec (in that
; case use "dist\dcad\*" with Flags: recursesubdirs instead).
Source: "dist\dcad.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
