# Le film Nova — source de rendu

Film de présentation (~40 s, 16 plans) affiché sur la landing
(`landing/index.html`, section `#film`). Rendu **déterministe** et
reproductible, sans dépendance externe : tout est synthétisé.

## Pièces

- `cinematic.html` — le film. Rendu piloté par `window.seek(t)` (aucune
  animation CSS : chaque image est calculée depuis le temps `t`, ce qui permet
  une capture propre image par image). `window.setLang('fr'|'en')` bascule les
  textes ; `window.DUR` donne la durée. 16 plans courts : orbe → accroche →
  touche F9 pressée → la boucle (dictée brute → e-mail reformulé) → Messages →
  To-do cochée → Notes → Prompt IA envoyé → carrousel des Styles → Style sur
  mesure (Ultra) → Intelligence privée (verrou) → Turbo → « partout » →
  compteur 150 mots/min → clôture.
- `audio.py` — synthétise la bande-son (`numpy`) calée sur chaque plan :
  cloches chaudes, **thock** de touche mécanique, ticks de frappe, **pop de
  reformulation**, swoosh d'envoi, coches de to-do, marimba des Styles, cloche
  Ultra, verrou feutré, whoosh Turbo, cliquet accéléré du compteur, accord
  final — sur un pad ambiant discret. Produit `nova-film-audio.wav`
  (non versionné, régénérable).
- `render.py` — Playwright rend chaque image (30 fps, 1280×720) et pousse le
  flux dans ffmpeg (`imageio_ffmpeg`) muxé avec le WAV → `../nova-film2.mp4`
  (FR) et `../nova-film2-en.mp4` (EN), plus les posters `../film2-poster*.jpg`.

## Régénérer

```sh
python3 landing/film/audio.py      # → nova-film-audio.wav
python3 landing/film/render.py     # → ../nova-film2*.mp4 + posters
```
