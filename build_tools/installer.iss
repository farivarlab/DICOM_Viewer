#ifndef AppVersion
  #error AppVersion must be supplied by the build script
#endif
#ifndef ProjectRoot
  #error ProjectRoot must be supplied by the build script
#endif
#define Payload ProjectRoot + "\dist\Lumen-" + AppVersion + "-portable-win64"

[Setup]
AppId={{6B4D7316-9954-49B3-84B7-363913BF6EE8}
AppName=Lumen DICOM Viewer
AppVersion={#AppVersion}
AppVerName=Lumen DICOM Viewer {#AppVersion}
; Without this, Setup.exe's file properties show no version.
VersionInfoVersion={#AppVersion}
AppPublisherURL=https://github.com/farivarlab/DICOM_Viewer
AppSupportURL=https://github.com/farivarlab/DICOM_Viewer/issues
AppUpdatesURL=https://github.com/farivarlab/DICOM_Viewer/releases
DefaultDirName={localappdata}\Programs\Lumen
DefaultGroupName=Lumen DICOM Viewer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#ProjectRoot}\dist
OutputBaseFilename=Lumen-{#AppVersion}-Setup-win64
SetupIconFile={#ProjectRoot}\build\release_materials\lumen.ico
UninstallDisplayIcon={app}\Lumen.exe
LicenseFile={#ProjectRoot}\LICENSE
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
Uninstallable=yes
UninstallDisplayName=Lumen DICOM Viewer

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#Payload}\*"; DestDir: "{app}"; Excludes: "\.lumen-settings.ini,\.lumen-annotations\*,\.cache\*"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Versions before 0.4.1 installed an editable logo.svg; the logo is now built in.
Type: files; Name: "{app}\logo.svg"

[Icons]
Name: "{group}\Lumen DICOM Viewer"; Filename: "{app}\Lumen.exe"; WorkingDir: "{app}"
Name: "{group}\Uninstall Lumen"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Lumen DICOM Viewer"; Filename: "{app}\Lumen.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Lumen.exe"; Description: "Open Lumen DICOM Viewer"; Flags: nowait postinstall skipifsilent unchecked

[UninstallDelete]
Type: files; Name: "{app}\.lumen-settings.ini"
Type: files; Name: "{app}\.cache\icons\app*.ico"
Type: dirifempty; Name: "{app}\.cache\icons"
Type: dirifempty; Name: "{app}\.cache"
Type: dirifempty; Name: "{app}"
