# Nova — conventions du dépôt

## Langage visuel (OBLIGATOIRE pour toute interface, sans exception)

Style **Apple / macOS, minimaliste premium** — décision produit ferme. Toute
nouvelle surface (fenêtre, panneau, écran, dialogue) suit ces règles ; toute
surface existante qui s'en écarte doit y être ramenée.

- **Typographie** : `-apple-system,"SF Pro Display","SF Pro Text","Segoe UI",
  Inter,system-ui,sans-serif` (la variable `--font` existante). Titres
  19–22 px / 600–700 / letter-spacing négatif ; corps 13 px ; sous-titres
  11.5 px gris ; libellés de section 11 px MAJUSCULES gris.
- **Arrondis partout** : fenêtres 13 px, groupes/cartes 9–13 px, champs et
  boutons 6 px, pilules/interrupteurs 999 px. Aucun angle droit visible.
- **Palette** : fond fenêtre `#1F1F22`, barre latérale `#28282C`, groupes
  `#2C2C30`, champs/insets `#1A1A1D`, hairlines `rgba(255,255,255,.055–.075)`,
  texte `#F2F2F4`, secondaire `#98989F`, succès `#30D158`, verrou Ultra
  `#C9B6F0`. **Accent d'action UNIQUE : bleu Apple `#0A84FF`** (boutons
  primaires, interrupteurs actifs, sélections, focus) — jamais un autre accent
  pour une action.
- **Composants canoniques** (voir la fenêtre réglages de `ui/dock.html`) :
  listes groupées arrondies à rangées 44 px séparées par hairline ; note
  `.foot` sous chaque groupe ; interrupteurs style macOS ; menus déroulants à
  bloc de chevrons bleu ; cartes de choix avec coche bleue ; fenêtres de
  configuration en **barre latérale à catégories** (icônes carrées colorées).
- **Identité** : l'orbe « bille de verre » et les fonds verre/pastel du dock et
  de l'onboarding sont l'identité de Nova et restent — mais toute ACTION y est
  bleu `#0A84FF`.

## Règles produit (UI)

- **Jamais d'emoji dans l'UI** — icônes SVG au trait (stroke ≈ 2, linecap
  round).
- **Jamais de nom de modèle IA visible** (ni Whisper, ni Qwen, ni Claude…) :
  parler de « Meilleure IA », « profil de puissance », etc.
- Textes utilisateur **en français**, ton sobre (pas de superlatifs criards).
- Fonctionnalité au-dessus du palier : griser les contrôles + badge
  « NÉCESSITE NOVA ULTRA » (`licensing.has(...)` décide).
- tkinter (pilule de repli) ne sait pas faire de vrais arrondis : on y applique
  au minimum la palette et la typographie ci-dessus.

## Garde-fous d'ingénierie

- **« Jamais de plantage »** : tout point d'entrée défensif (try/except +
  repli) ; WebView2 absent → repli pilule tkinter ; IA en échec → collage du
  texte brut (`format_rules`) — le curseur ne reste jamais vide.
- `licensing` est **dormant** tant que `PUBLIC_KEY_B64` est vide : `has()`
  renvoie True partout. Tout nouveau gate doit rester un no-op en dormant.
- **Deux écrans de réglages, c'est voulu** : la fenêtre tkinter (mode pilule)
  et l'écran du dock web (`ui/dock.html`) coexistent. Ne PAS les unifier :
  `webview.start()` exige le thread principal, que le tray possède en mode
  pilule — un webview de réglages y est donc impossible. Toute nouvelle
  option de réglage doit être ajoutée **aux deux** écrans.
- Windows-only à l'exécution ; le développement se fait sous Linux.

## Vérifications avant tout commit

- Python : `ruff check .` + `python -m compileall -q .` + `python test_v3.py`.
- HTML/UI : capture Playwright (Chromium dans `/opt/pw-browsers`, flags
  swiftshader pour WebGL) + **0 erreur console** ; vérifier l'état verrouillé
  ET déverrouillé des sections gatées.
