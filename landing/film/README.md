# Le film Nova — source de rendu

Film de présentation (~26 s) affiché sur la landing (`landing/index.html`,
section `#film`). Rendu **déterministe** et reproductible, sans dépendance
externe : tout est synthétisé.

## Pièces

- `cinematic.html` — le film. Rendu piloté par `window.seek(t)` (aucune
  animation CSS : chaque image est calculée depuis le temps `t`, ce qui permet
  une capture propre image par image). `window.setLang('fr'|'en')` bascule les
  textes ; `window.DUR` donne la durée. 8 scènes courtes : matérialisation de
  l'orbe → accroche → la boucle (dictée brute → e-mail reformulé) → les Styles →
  Intelligence privée (verrou) → Turbo → « partout où vous écrivez » → clôture.
- `audio.py` — synthétise la bande-son douce (`numpy`) calée sur les beats :
  cloche chaude, ticks de touche, **pop de reformulation**, marimba des Styles,
  verrou feutré, whoosh Turbo, accord final, sur un pad ambiant discret.
  Produit `nova-film-audio.wav` (non versionné, régénérable).
- `render.py` — Playwright rend chaque image (30 fps, 1280×720) et pousse le
  flux dans ffmpeg (`imageio_ffmpeg`) muxé avec le WAV → `../nova-film2.mp4`
  (FR) et `../nova-film2-en.mp4` (EN), plus les posters `../film2-poster*.jpg`.

## Régénérer

```sh
python3 landing/film/audio.py      # → nova-film-audio.wav
python3 landing/film/render.py     # → ../nova-film2*.mp4 + posters
```
