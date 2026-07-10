# Backend licences Nova (Supabase, projet `nova-licences`)

Sources des edge functions déployées — **le déploiement fait foi**, ces
copies servent au versionnage et à la relecture.

- `license/` — activation d'une clé d'achat liée à la machine (2 postes,
  libération après 30 j d'inactivité) + `GET /key` pour la page merci.html.
- `stripe-webhook/` — paiement → clé générée ; renouvellement → prolongation ;
  résiliation → blocage. Signature Stripe vérifiée (HMAC).

Secrets (table `server_secrets`, RLS sans policy = service role uniquement) :
`ed25519_private_b64` (jamais dans ce dépôt), `stripe_webhook_secret`.
NB : la passerelle supabase.co réécrit tout text/html en text/plain
(anti-hameçonnage) — les pages HTML vivent sur le site vitrine (Vercel).
