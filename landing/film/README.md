# Le film Nova — source de rendu (v4)

Film de présentation (42 s, 19 plans) affiché sur la landing
(`landing/index.html`, section `#film`). Rendu **déterministe** et
reproductible, sans dépendance externe : tout est synthétisé, sauf un vrai
écran de l'app (`assets/shot-models.png`, la collection de modèles).

## Pièces

- `cinematic.html` — le film. Rendu piloté par `window.seek(t)` (aucune
  animation CSS : chaque image est calculée depuis le temps `t`, ce qui permet
  une capture propre image par image). `window.setLang('fr'|'en')` bascule les
  textes ; `window.DUR` donne la durée. 19 plans courts (montage rapide) :
  orbe → accroche → touche F9 → la bulle réelle qui écoute → POP e-mail propre
  → Messages (envol) → To-do (coches + rayures) → Prompt IA → carrousel des
  Styles (indicateur glissant) → détection automatique (badge qui saute
  d'app en app) → **vrai écran de la collection de modèles** (Ken Burns +
  balayage lumineux) → Style sur mesure (Ultra) → Intelligence privée (verrou)
  → Turbo (traînées) → « partout » → compteur 150 mots/min (anneau) → stat
  hebdo (4 820 mots, courbe) → mises à jour (flèche → coche) → clôture.
  Micro-animations générales : poussière ambiante, étincelles aux coupes
  (CUTS), éclats « glint », ressorts (eSpring), curseur qui clique réellement.
- `audio.py` — bande-son **stéréo** (`numpy`) calée sur chaque plan :
  whooshs de coupe alternés G/D, thock mécanique, ticks de frappe randomisés,
  pop de reformulation, envol Messages, coches ascendantes, marimba des
  Styles, boops du badge auto, pose d'écran + scintillement (collection),
  cloche Ultra, verrou feutré, whoosh Turbo, cliquets (compteur + stat hebdo),
  rotation → carillon (mise à jour), accord final. Lit musical : pad chaud +
  arpège feutré ~110 BPM (14,8 → 33,2 s), **ducking** sous les SFX, **réverbe
  par convolution** (RI synthétique normalisée en énergie). Produit
  `nova-film-audio.wav` (stéréo, non versionné, régénérable).
- `render.py` — Playwright rend chaque image (30 fps, 1600×900) et pousse le
  flux dans ffmpeg (`imageio_ffmpeg`) muxé avec le WAV → `../nova-film3.mp4`
  (FR) et `../nova-film3-en.mp4` (EN), plus les posters `../film3-poster*.jpg`.

## Régénérer

```sh
python3 landing/film/audio.py      # → nova-film-audio.wav
python3 landing/film/render.py     # → ../nova-film3*.mp4 + posters
```
