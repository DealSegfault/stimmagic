# Windows : build et déploiement plug-and-play

Stimma est distribué sur Windows sous la forme d'un installateur NSIS `.exe`.
Cet installateur contient l'application Tauri et son backend Python portable :
le poste cible n'a besoin ni de Python, ni de Node.js, ni de Rust.

## Construire l'installateur en une commande

Depuis la racine du dépôt, dans PowerShell :

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\bin\build-windows-installer.ps1
```

On peut aussi double-cliquer sur
`infra\bin\build-windows-installer.cmd`. Le script :

1. détecte les prérequis de compilation ;
2. installe ceux qui manquent avec `winget` ;
3. synchronise les dépendances verrouillées ;
4. construit le backend Python portable, le watchdog et l'application ;
5. affiche le chemin et le SHA-256 de l'installateur final.

Le résultat se trouve dans :

```text
src-tauri\target\release\bundle\nsis\*.exe
```

Pour vérifier un poste sans rien installer ni compiler :

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\bin\build-windows-installer.ps1 -CheckOnly -NoInstall
```

Pour réutiliser des dépendances déjà synchronisées :

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\bin\build-windows-installer.ps1 -SkipDependencySync
```

## Installer et tester localement

Après le build, double-cliquez sur l'installateur ou exécutez :

```powershell
.\tools\stimma.ps1 app install
```

Le mode NSIS `currentUser` n'exige pas une installation système. Les données
de l'application restent séparées par canal et sandbox sous `%LOCALAPPDATA%` ;
voir [DATA_DIRECTORIES.md](DATA_DIRECTORIES.md).

Un build local n'est pas signé avec un certificat Authenticode et peut donc
déclencher SmartScreen. La signature minisign de l'updater utilisée par la CI
officielle est distincte de la réputation Authenticode de l'installateur ; une
distribution publique sans avertissement Windows nécessite un certificat de
signature de code.

## Développement local et outils GPU

Le build de l'installateur ne déploie aucun service cloud et n'engendre aucun
coût Modal. Le parcours Codex + ComfyUI + Modal est optionnel et séparé :

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\bin\bootstrap-local.ps1
```

Une fois le bootstrap local terminé, lancez explicitement l'assistant Modal
seulement si vous souhaitez déployer les outils GPU payants :

```powershell
$python = ".\infra\.runtime\ComfyUI\.venv\Scripts\python.exe"
& $python .\infra\bin\setup-interactive.py
```

Les identifiants restent gérés par Codex, Modal ou le répertoire de
configuration de l'utilisateur ; ils ne doivent jamais être ajoutés au dépôt.

Le raccourci de Bureau Windows lance PowerShell sans fenêtre de terminal,
arrête les arbres Stimma précédents avant un nouveau démarrage et ignore les
double-clics concurrents pendant qu'un lancement est déjà en cours. Une fois
le backend et le frontend prêts, il ouvre automatiquement
`http://127.0.0.1:9192/` dans le navigateur par défaut. Les logs de démarrage
restent disponibles dans `%LOCALAPPDATA%\Stimma\Logs`.
