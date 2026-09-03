# `api/` — fonctions serverless du site

## `demo-request.mjs`

Reçoit les demandes de démonstration des pages Campus / Business
(`/demo.html` et `/demonstration.html`).

La CSP du site (`vercel.json`) impose `form-action 'self'` et une liste
`connect-src` fermée : le formulaire ne peut donc poster que vers cette
fonction, sur la même origine. Le relais vers l'extérieur se fait côté
serveur, hors de portée de la CSP — celle-ci n'a pas eu à être modifiée.

### Variables d'environnement (à définir dans Vercel, jamais dans le dépôt)

| Variable         | Rôle                                                        |
| ---------------- | ----------------------------------------------------------- |
| `RESEND_API_KEY` | Clé d'API du fournisseur d'envoi transactionnel (Resend).     |
| `DEMO_INBOX`     | Adresse qui reçoit les demandes.                              |
| `DEMO_FROM`      | Expéditeur vérifié sur le domaine, ex. `Nova <no-reply@novaspeak.app>`. |

Tant que l'une des trois manque, la fonction répond `503` et la page affiche
son message d'échec : aucune demande n'est perdue silencieusement, mais aucune
n'est reçue non plus. Il faut donc poser les trois variables avant d'annoncer
le formulaire.

### Garde-fous

- Pot de miel (`website`) : réponse `200` sans envoi.
- Valeurs des listes déroulantes validées contre une liste fermée côté serveur.
- Corps de requête plafonné à 64 ko, chaque champ borné en longueur.
- `next` (redirection sans JS) restreint aux chemins internes.
- Aucun secret ni adresse en clair dans le dépôt.

### Pourquoi `.mjs` et non `.js`

Le dépôt n'a pas de `package.json` à la racine (projet Python). Sans
`"type": "module"`, Vercel traiterait un `.js` contenant `export default`
comme du CommonJS : le build passerait, la fonction casserait à l'exécution.
L'extension `.mjs` lève l'ambiguïté sans imposer un `package.json` à un dépôt
qui n'en a pas besoin.
