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
; Doit rester égal à core.APP_VERSION (test_v3 le vérifie) — c'est ce que
; l'updater intégré compare au tag de la release GitHub.
#define MyAppVersion "3.1.10"
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
; Mise à jour par-dessus une instance en cours (updater silencieux) : ferme
; proprement Nova.exe avant de copier, ne le relance pas via RestartManager
; (c'est l'entrée [Run] « Check: WizardSilent » qui s'en charge).
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le bureau"; GroupDescription: "Raccourcis :"
Name: "autostart"; Description: "Lancer Nova au démarrage de Windows"; GroupDescription: "Options :"; Flags: unchecked
; cochée par défaut : sans le modèle, la première dictée devrait attendre son
; téléchargement — on le fait pendant l'installation, où l'attente est attendue
Name: "preload"; Description: "Télécharger l'Intelligence privée maintenant (recommandé, ~500 Mo)"; GroupDescription: "Options :"

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
; Pré-télécharge le modèle de l'Intelligence privée (profil adapté à la machine)
; pour que la première dictée fonctionne immédiatement, même hors ligne.
Filename: "{app}\{#MyAppExeName}"; Parameters: "--preload-models"; \
  StatusMsg: "Téléchargement de l'Intelligence privée (quelques minutes)…"; \
  Flags: runhidden waituntilterminated; Tasks: preload
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer Nova"; \
  Flags: nowait postinstall skipifsilent
; Mise à jour silencieuse (updater intégré) : Nova a quitté avant l'installation,
; on le relance automatiquement à la fin — l'utilisateur ne perd pas son app.
; WorkingDir explicite : relancée par l'installateur, l'app doit démarrer dans
; SON dossier — sinon le serveur interne de l'interface répondait 404.
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Flags: nowait; Check: WizardSilent
