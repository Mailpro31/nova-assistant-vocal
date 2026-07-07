# Audit & optimisation de la pipeline STT — conduite

Branche : `stt-optim` · 3 commits · outil de mesure : `bench_stt.py`

Objectif du brief : **auditer et, si justifié, améliorer** la pipeline STT
existante de `core.py` pour l'usage EN CONDUITE (bruit moteur/route, débit
pressé, mains occupées) — **sans la remplacer**. Ne touche pas à `modes.py`,
`app.py`, l'UI, ni les modules par domaine.

---

## 1. Ce qui a été mesuré

Un banc reproductible (`bench_stt.py`) qui **ne modifie rien** :

- **12 commandes de conduite** courtes (appel, minuteur, navigation, musique,
  média, message, météo, ouverture d'app…), synthétisées par la voix Windows
  (SAPI, 16 kHz).
- **Bruit routier synthétique** : grondement moteur/route (bruit brownien,
  domine le grave) + souffle pneus/vent, mélangé à **4 conditions** :
  propre, +5 dB, 0 dB, −5 dB (du calme au très bruyant).
- Chaque clip passe dans la **vraie** pipeline (`transcribe` pour le chemin
  précis, `transcribe_routed(fast=True)` pour le vrai chemin commande).
- **3 métriques** par condition :
  - **Intention** via `modes.classify` — *la métrique qui compte* : « dix
    minutes » et « 10 minutes » déclenchent le même minuteur.
  - **WER** (taux d'erreur mot) avec « dix » ≡ « 10 » normalisé.
  - **Latence** moyenne par clip.

> Limite honnête : la voix SAPI n'est pas une vraie voix humaine et le WER
> sur-pénalise ses artefacts. Les **chiffres absolus** sont donc indicatifs ;
> c'est le **delta avant/après** et la **stabilité au bruit** qui sont fiables.

---

## 2. Constat (Phase 0 — avant toute modification)

La pipeline est saine mais présentait un **paradoxe pour la conduite** :

1. **Le chemin commande utilisait le modèle le moins précis.** Au volant, les
   commandes courtes passent par le modèle rapide `base` en **beam 1** (le
   moins précis) parce que le modèle précis `small` en beam 5 met **9–11 s**
   par clip — inutilisable en conduite. Mesuré : intention **5–7/12** selon le
   bruit, contre 8–9/12 pour `small`.
2. **L'amorçage `stt_prompt` était pauvre** : ~18 mots figés, plafond 220 car.,
   **sans** le vocabulaire riche de `modes.py` (noms d'applis/sites, verbes),
   alors que Whisper accepte un prompt bien plus long.
3. **VAD en double** : Nova segmente déjà (VAD énergétique adaptatif), puis
   faster-whisper refait un VAD Silero avec ses **paramètres par défaut**.
4. **Aucun pré-filtrage anti-bruit** avant transcription.

Deux découvertes matérielles :

- **`int8_float16` (suggéré par le brief) est indisponible sur ce CPU** — c'est
  un type GPU. Les types CPU réels sont `int8`, `int8_float32`, `float32`.
- **Le GPU (GTX 1650) est inutilisable en l'état** : pilote NVIDIA 451.67 trop
  ancien pour CUDA 12 (CTranslate2 voit 0 device). Levier réel mais **hors
  cadre** (mise à jour pilote requise).

---

## 3. Ce qui a changé (Phase 1 — 3 commits, tests avant/après)

| Commit | Changement | Justifié par |
|---|---|---|
| `f58341a` | **Banc de mesure** `bench_stt.py` | Impossible d'améliorer sans mesurer |
| `bff1f0a` | **Prompt d'amorçage enrichi** : personnel d'abord (contacts, automatisations, profil — jamais tronqués), puis verbes de commande, puis clés `modes.SITES`/`APPS` (import paresseux, **lecture seule**), puis villes ; plafond 220 → 520 | +1 à +2 intentions sur le chemin rapide, et forte baisse du WER sur les deux chemins |
| `9bac7d2` | **Chemin commande en beam 3** : `transcribe_quick` prend un paramètre `beam` (défaut **1** — éveil et aperçus live inchangés) ; seul `transcribe_routed(fast)` passe **beam 3** | Atteint la précision de `small` à ~1/4 du temps |

**Non retenu, et pourquoi :**
- **VAD interne** laissé par défaut : à l'exploration, `vad_filter` ON vs OFF
  donnait des résultats **identiques** (Nova a déjà retiré les silences) →
  aucun gain à le régler, on ne touche pas.
- **Pré-filtre passe-haut anti-moteur** : gain **marginal** et seulement sur le
  chemin précis (lent) ; sur le chemin rapide le beam 3 suffit. Coût CPU d'un
  filtre Python pur non justifié. Documenté comme levier de secours.

---

## 4. Impact précision / latence (avant → après)

**Chemin commande RÉEL (le trajet conduite) — `base` :**

| Condition | Intention | WER | Latence |
|---|---|---|---|
| propre | 6/12 → **9/12** | 28.2% → **5.4%** | 2.33 → 2.71 s |
| +5 dB | 5/12 → **9/12** | 25.0% → **3.3%** | 2.30 → 2.47 s |
| 0 dB | 7/12 → **9/12** | 20.1% → **8.2%** | 2.30 → 2.60 s |
| −5 dB | 5/12 → **9/12** | 30.9% → **18.6%** | 2.29 → 2.59 s |

→ D'une précision **erratique (5–7/12 selon le bruit)** à un **9/12 stable à
tous les niveaux de bruit**, y compris −5 dB, pour **+0,3 s** seulement.

**Chemin précis (dictée / phrases longues) — `small`**, bénéficie du même
prompt enrichi :

| Condition | Intention | WER |
|---|---|---|
| propre | 8/12 → **11/12** | 21.2% → **7.2%** |
| +5 dB | 9/12 → **11/12** | 16.5% → **5.6%** |
| 0 dB | 9/12 → **12/12** | 17.9% → **1.4%** |
| −5 dB | 7/12 → **11/12** | 28.3% → **8.3%** |

**Éveil « Nova » : inchangé** (beam 1 préservé) — `test_wake.py` : 10/10 PASS.

---

## 5. Phase 2 nécessaire ?

**Non.** La Phase 1, dans le cadre faster-whisper existant, amène déjà le chemin
commande à la précision du gros modèle tout en gardant sa vitesse. Un backend
alternatif (Parakeet / ONNX CPU) n'apporterait rien de décisif ici et :

- il n'existe pas de portage **CPU-only fiable pour Windows** qui batte
  nettement ce résultat sans complexité de packaging ;
- le brief demandait de **ne pas forcer** l'intégration dans ce cas et de rester
  sur faster-whisper — ce que je fais.

**Seul vrai levier restant, hors cadre :** activer le **GPU** (GTX 1650) via une
**mise à jour du pilote NVIDIA** (→ CUDA 12) + le bundling cuDNN/cuBLAS. Cela
rendrait `small`/beam 5 quasi instantané. À envisager plus tard si tu veux la
précision maximale sans compromis de latence.

---

## 6. Tests

| Test | Résultat |
|---|---|
| `test_wake.py` (chaîne d'éveil complète) | **WAKE TEST OK** (10/10 PASS) |
| `test_pipeline.py --whisper` (règles + modèle) | **RESULT: OK** |

Reproduire : fermer `Nova.exe`, puis
`.venv\Scripts\python.exe bench_stt.py --tag <étiquette>`.
