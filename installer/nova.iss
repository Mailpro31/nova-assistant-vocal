; ===========================================================================
;  Nova — script d'installation Inno Setup
;  Empaquette le dossier PyInstaller (dist\Nova\) en un installateur unique
;  Nova-Setup.exe : assistant d'installation, raccourcis menu Démarrer +
;  bureau, démarrage automatique (facultatif) et désinstallateur propre.
;
;  Prérequis : Inno Setup 6  (https://jrsoftware.org/isdl.php)
;  Compilation : ouvrir ce fichier dans Inno Setup puis « Build > Compile »,
;  ou en ligne de commande :  iscc installer\nova.iss
;  (build_installer.bat enchaîne PyInstaller + cette compilation.)
; ===========================================================================

#define MyAppName "Nova"
#define MyAppVersion "3.0"
#define MyAppPublisher "Nova"
#define MyAppExeName "Nova.exe"

[Setup]
AppId={{7F3B2A10-9C4D-4E5F-8A1B-NOVAVOCAL0001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; Installation par utilisateur : pas de droits administrateur requis.
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=Nova-Setup
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le bureau"; GroupDescription: "Raccourcis :"
Name: "autostart"; Description: "Lancer Nova au démarrage de Windows"; GroupDescription: "Options :"; Flags: unchecked

[Files]
; Tout le dossier produit par PyInstaller (build.bat -> dist\Nova\).
Source: "..\dist\Nova\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Désinstaller {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Démarrage automatique (case à cocher « autostart »). Retiré à la désinstallation.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "Nova"; ValueData: """{app}\{#MyAppExeName}"""; \
  Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer Nova"; \
  Flags: nowait postinstall skipifsilent
