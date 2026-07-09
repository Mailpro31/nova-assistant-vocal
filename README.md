# Nova

**Assistant vocal Windows** au design « bleu nuit » façon macOS : mot d'éveil,
compréhension du langage naturel, domotique, médias, fichiers, vision d'écran,
multi-IA — le tout **offline-first** et respectueux de la vie privée.

Nova transcrit en local (faster-whisper), n'envoie aux fournisseurs d'IA que ce
que vous demandez explicitement, et chiffre toutes les clés avec DPAPI. Aucune
donnée personnelle n'est stockée en clair.

![version](https://img.shields.io/badge/version-2.14-0A84FF) ![Windows](https://img.shields.io/badge/Windows-10%2F11-2B517E) ![Python](https://img.shields.io/badge/Python-3.11%E2%80%933.13-3FA9FF)

---

## Installation (depuis les sources)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Compiler un exécutable autonome : `build.bat` (PyInstaller → dossier
portable `dist\Nova\`).

### Créer un installateur `.exe` complet

Pour un vrai assistant d'installation (raccourcis menu Démarrer / bureau,
démarrage automatique facultatif, désinstallateur) :

1. Prépare l'environnement une fois :
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt pyinstaller
   ```
2. Installe **[Inno Setup 6](https://jrsoftware.org/isdl.php)** (gratuit).
3. Lance **`build_installer.bat`** : il enchaîne PyInstaller puis Inno Setup et
   produit **`dist\Nova-Setup.exe`** — le fichier unique à distribuer.

> **WebView2** : le dock et l'onboarding web utilisent le runtime *Microsoft
> Edge WebView2*, préinstallé sur Windows 10/11 à jour. Sur un PC sans lui,
> [téléchargez l'« Evergreen Bootstrapper »](https://developer.microsoft.com/microsoft-edge/webview2/).
> Sans WebView2, Nova bascule automatiquement sur la pastille tkinter.

**Externe, facultatif** : [FFmpeg](https://ffmpeg.org) dans le PATH (flux IPTV),
[Ollama](https://ollama.com) (IA 100 % locale).

---

## Déclencheurs

| Déclencheur | Effet |
|---|---|
| **« Nova, ouvre YouTube »** d'une traite | Mot d'éveil + commande : exécution directe |
| **« Nova »** seul (écoute continue) | Ouvre l'écoute (Whisper local ou Porcupine) |
| **`Ctrl + Alt + Espace`** | Commande vocale |
| **`Ctrl + Alt + N`** | Note vocale |
| **`Ctrl + Alt + D`** | Dictée : le texte s'écrit au curseur pendant que vous parlez |
| **« Stop » / « tais-toi »** | Coupe la voix de Nova en cours |
| **« Merci » / « c'est tout »** | Met fin à la conversation |

Après une réponse, vous pouvez **enchaîner sans redire « Nova »** (conversation
continue). La **pilule flottante** (5 états) montre l'écoute, la transcription en
direct, la réflexion, le succès ou l'erreur.

---

## Ce que Nova comprend

**Voix & voix de synthèse** — Whisper local ou cloud Groq (opt-in), voix
neuronale Edge ou SAPI hors ligne, choix du micro, bip d'accusé, double
applaudissement.

**Applications & web** — ouvre ~90 sites et applis (« ouvre Chrome », « lance VS
Code », « ouvre lemonde.fr »), recherche web parlée, images, itinéraires.

**Médias** — « mets du jazz », playlists Spotify/YouTube attitrées, contrôle
média, volume système et **par application**, YouTube Data (recherche + choix
vocal, résumé de vidéo, tendances), IPTV.

**Minuteurs & rappels** — « minuteur de 10 minutes », « rappelle-moi le sport à
15 h 30 » (heure fixe, quotidien possible), ajout/retrait de temps.

**Maison (Home Assistant)** — lumières, couleurs, luminosité, prises, scènes,
thermostat, verrou, alarme, aspirateur, capteurs.

**PC** — veille / arrêt (avec confirmation) / redémarrage, luminosité écran,
« ferme Chrome », corbeille, batterie/CPU/RAM, scan antivirus Defender,
désinstallation de programmes.

**Fichiers** — tri par catégorie ou par date, recherche, création de dossier,
mosaïque, capture d'écran.

**Vision** — « qu'est-ce que tu vois ? », « lis ce mail », « clique sur le bouton
lecture », « écris X dans le champ Y », webcam.

**Bureautique & mémoire** — notes, dictée continue, listes (courses…), Google
Agenda/Docs/Sheets, Gmail, Obsidian, « souviens-toi que… » (mémoire durable).

**Infos hors ligne** — heure dans le monde, capitales, monnaies, calcul mental,
conversions, blagues, mot de passe, épellation, comptes à rebours.

**Messages & urgence** — SMS/appel Twilio, WhatsApp, mail Outlook/Gmail, mode
urgence (SMS + appel avec position). Alertes véhicule OBD-II.

**Automatisations** — galerie 1-clic, création par IA en langage naturel,
webhooks (IFTTT / Zapier / Home Assistant).

**Accès mobile** — piloter Nova depuis le téléphone sur le Wi-Fi local
(transcription 100 % locale sur le PC).

---

## Architecture

| Fichier | Rôle |
|---|---|
| `app.py` | Fenêtre, pilule tkinter, boucle d'éveil, orchestration |
| `core.py` | Config, STT (Whisper/Groq), agent multi-IA, TTS |
| `modes.py` | Classifieur vocal + handlers (~2 900 lignes de grammaire FR) |
| `winext.py` | Windows natif : DPAPI, volume, fenêtres, vision, MCI |
| `storage.py` | SQLite (historique, mémoire, listes, rappels, profils) |
| `integrations.py` | Météo, Gmail/Docs, Spotify, Home Assistant, Twilio |
| `fun_mode.py` `files_mode.py` `yt_mode.py` `webinfo.py` `obsidian.py` `iptv.py` `uninstall_mode.py` `mobile.py` | Modules par domaine |
| `ui/` `ui_mobile/` | Interfaces (design → `DESIGN.md`) |
| `test_modes.py` | ~330 tests du classifieur et des handlers |

Fournisseurs d'IA : Claude, OpenAI, Gemini, DeepSeek, Groq, Mistral, xAI (Grok),
OpenRouter, Ollama — avec bascule automatique par santé et latence.

---

## Sécurité & vie privée

- Transcription **en local** par défaut ; le cloud (Groq) est strictement opt-in.
- Clés API et jetons **chiffrés DPAPI** (`secrets.json`), jamais réaffichés.
- Substitution des infos personnelles (« mon adresse »…) **100 % locale**, jamais
  envoyée à une IA.
- Historique, mémoire et contacts dans `nova.db` (SQLite local, jamais versionné).

> Les fichiers de données (`secrets.json`, `nova.db`, `config.json`, `notes.json`…)
> sont exclus du dépôt par `.gitignore` : Nova les crée au premier lancement.

---

## Licence

MIT — voir [LICENSE](LICENSE).
