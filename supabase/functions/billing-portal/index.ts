// Nova — portail de facturation Stripe : l'app envoie son jeton de licence
// NOVA1 (signature Ed25519 vérifiée ici, comme « turbo »/« styles-chat ») ;
// on remonte de la machine (activations) à la licence puis au client Stripe,
// et on crée une session du portail client hébergé par Stripe (résiliation,
// changement de palier avec prorata, moyen de paiement, factures). L'app
// ouvre l'URL renvoyée.
//
// La clé API Stripe (server_secrets.stripe_secret_key) ne quitte JAMAIS le
// serveur ; seule une URL de session éphémère est renvoyée.
import { createClient } from "jsr:@supabase/supabase-js@2";
// vérification Ed25519 en pur JS (@noble), identique à « turbo »
import * as ed from "npm:@noble/ed25519@2";

const supa = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

// clé PUBLIQUE de vérification des jetons NOVA1 (la même que dans l'app)
const PUBLIC_KEY_B64 = "Q+U/LqaeFgLSDkvqiAXRcHQ8DSwqU9NcrHiPt8A6EJE=";
const RETURN_URL = "https://novaspeak.app";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
};

const json = (code: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status: code,
    headers: { "Content-Type": "application/json; charset=utf-8", ...CORS },
  });

const PUB_BYTES = Uint8Array.from(atob(PUBLIC_KEY_B64), (c) => c.charCodeAt(0));

async function verifyToken(tok: string): Promise<Record<string, unknown> | null> {
  const m = /^NOVA1\.([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)$/.exec(tok || "");
  if (!m) return null;
  const un64 = (s: string) =>
    Uint8Array.from(
      atob(s.replace(/-/g, "+").replace(/_/g, "/") +
        "=".repeat((4 - s.length % 4) % 4)),
      (c) => c.charCodeAt(0),
    );
  try {
    const payload = un64(m[1]), sig = un64(m[2]);
    if (!(await ed.verifyAsync(sig, payload, PUB_BYTES))) return null;
    return JSON.parse(new TextDecoder().decode(payload));
  } catch {
    return null;
  }
}

let stripeKey = "";
async function serverStripeKey(): Promise<string> {
  if (stripeKey) return stripeKey;
  const { data } = await supa.from("server_secrets").select("value")
    .eq("name", "stripe_secret_key").maybeSingle();
  stripeKey = data?.value || "";
  return stripeKey;
}

Deno.serve(async (req: Request) => {
  try {
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    if (req.method !== "POST") return json(404, { ok: false, error: "Introuvable." });

    // — authentification : jeton NOVA1 signé (la clé d'achat ne sort jamais
    //   de l'app ; le jeton lié à la machine suffit) —
    const tok = (req.headers.get("Authorization") || "").replace(/^Bearer\s+/i, "");
    const p = await verifyToken(tok);
    const machine = String(p?.m || "");
    if (!p || !machine) return json(401, { ok: false, error: "Jeton invalide." });

    // — machine → licence → client Stripe —
    const { data: act } = await supa.from("activations")
      .select("license_id").eq("machine_hash", machine)
      .order("last_seen", { ascending: false }).limit(1).maybeSingle();
    if (!act) return json(403, { ok: false, error: "Machine non activée." });
    const { data: lic } = await supa.from("licenses")
      .select("stripe_customer_id").eq("id", act.license_id).maybeSingle();
    if (!lic?.stripe_customer_id) {
      return json(404, { ok: false, error: "Aucun abonnement Stripe lié à cette licence." });
    }

    const sk = await serverStripeKey();
    if (!sk) return json(503, { ok: false, error: "Facturation indisponible." });

    const r = await fetch("https://api.stripe.com/v1/billing_portal/sessions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${sk}`,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({
        customer: String(lic.stripe_customer_id),
        return_url: RETURN_URL,
      }),
      signal: AbortSignal.timeout(15_000),
    });
    if (!r.ok) {
      console.error("stripe portal error", r.status);
      return json(502, { ok: false, error: "Portail momentanément indisponible." });
    }
    const session = await r.json();
    return json(200, { ok: true, url: session.url });
  } catch (e) {
    console.error("billing-portal error", e);
    return json(500, { ok: false, error: "Erreur serveur." });
  }
});
