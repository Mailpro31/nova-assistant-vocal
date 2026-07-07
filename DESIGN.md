# DESIGN.md — Nova (design « bleu nuit » livré par Claude Design)

Source de vérité : maquettes `nova-design/*.dc.html` (pack du 2026-07-05).
Esthétique macOS sombre, accent bleu iOS, verre dépoli simulé.

## 1. Fondations

| Token | Valeur | Usage |
|---|---|---|
| `--bg` | `#141826` | fond du contenu |
| `--sidebar` | `rgba(15,18,28,.98)` | sidebar (blur simulé : opaque sombre) |
| `--card` | `linear-gradient(180deg, rgba(255,255,255,.055), rgba(255,255,255,.03))` | cartes |
| `--line` | `rgba(255,255,255,.08)` | bordures |
| `--txt` | `#f2f5ff` | texte principal |
| `--dim` | `rgba(235,240,255,.52)` | texte secondaire |
| `--faint` | `rgba(235,240,255,.36)` | méta, horodatage |
| `--accent` | `#0A84FF` | actions, focus, sélection |
| `--ok` | `#30D158` | succès, statuts actifs |
| `--err` | `#FF6950` | erreurs (`#FF453A` pour destructif) |
| gradient logo | `#3FA9FF → #0A63E8` | squircle Nova (piste A « Onde ») |

Typo : `-apple-system, "SF Pro Text", "Segoe UI Variable", "Segoe UI", system-ui`.
Corps 13px, titres de page 21px/700 tracking -0.02em, labels 12px/600,
sur-titres 11.5px uppercase letterspacing .05em.

## 2. Structure

Fenêtre 1040×700 frameless. Sidebar 216px : feux tricolores (12px), logo 30px +
« Nova / Assistant vocal », nav 5 items (Accueil, Notes, Automatisations,
Intelligence, Réglages), spacer, chip « Écoute active », version.
Item actif : `linear-gradient(90deg, rgba(10,132,255,.35), rgba(10,132,255,.1))`
+ `inset 0 0 0 1px rgba(10,132,255,.25)`.

## 3. Primitives

- **Card** : radius 12 (14 pour les héros), padding 14-18px, ombre `0 4px 14px rgba(0,0,0,.22)`.
- **Bouton primaire** : fond accent, radius 8, 13px/600, hover brightness 1.08 + translateY(-1px).
- **Bouton fantôme** : `rgba(255,255,255,.1)`, hover `.16`.
- **Toggle macOS** : 36×21, rond 18px blanc, fond accent quand actif.
- **Input** : fond `rgba(255,255,255,.08)`, bord `rgba(255,255,255,.16)`, radius 8,
  focus `border #0A84FF + 0 0 0 3px rgba(10,132,255,.25)`. Clés API en monospace.
- **Badge type** : 10.5px/600 uppercase, fond `rgba(255,255,255,.08)`, radius 5.
- **kbd** : 11px/600, fond `rgba(255,255,255,.08)`, bord `rgba(255,255,255,.16)`
  border-bottom 2px, radius 5.
- **Segmented control** : conteneur `rgba(255,255,255,.08)` radius 8 padding 2,
  segment actif `rgba(255,255,255,.18)` + ombre.
- **Modale** : 440px, fond `rgba(30,34,48,.98)`, radius 16, backdrop `rgba(20,22,30,.42)`.

## 4. Pilule flottante (tkinter)

560×64, radius 32, fond `#1A1B20` (≈ rgba(26,27,31,.82)), 5 états :
repos (tuile logo + « Je t'écoute… » + badge raccourci) · écoute (14 barres
bleues réactives + transcription live + caret clignotant, bord bleuté) ·
réflexion (spinner arc + « Nova réfléchit… ») · succès (check vert + « Exécuté »,
bord verdâtre, 2 s) · erreur (triangle orangé + message + aide, bord orangé).
Variante compacte : bulle 128×44 (9 barres douces) en bas d'écran pendant
l'écoute continue, cliquable.

## 5. Animations

`novaWin` (fenêtre, .55s), `novaIn` (contenu, .6s +.12s), `novaPulse` (bouton
micro), `novaWave` (barres), `novaSpin`, `novaModal/novaFade`. GPU-only
(transform/opacity). Transitions 150ms ease sur hover.

## 6. Accessibilité

Contraste AA sur textes principaux ; focus visible (anneau accent) sur inputs
et boutons ; icônes SVG inline trait 1.7 (jamais d'emoji) ; états ok/erreur
doublés d'un libellé texte.

## 7. Dette acceptée

- Pas de vrai backdrop-blur dans pywebview/tkinter : fonds opaques équivalents.
- Mode clair non prévu par le design pack (sombre uniquement).
