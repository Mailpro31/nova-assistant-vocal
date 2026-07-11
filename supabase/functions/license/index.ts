// Nova — activation de licence liée à la machine + récupération de clé après
// paiement. Auth : pas de JWT — la clé d'achat / le session_id Stripe
// (inforgeables) SONT les secrets ; le webhook Stripe alimente la table.
// NB : la passerelle supabase.co réécrit tout text/html en text/plain
// (anti-hameconnage) — la page « voici votre clé » vit donc sur le site
// vitrine (Vercel), qui interroge ici GET /key en JSON.
import { createClient } from "jsr:@supabase/supabase-js@2";

const supa = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

const SUCCESS_PAGE = "https://nova-landing-omega-ten.vercel.app/merci.html";
const GRACE_MS = 7 * 24 * 3600 * 1000;      // 7 j de grâce après fin de période
const SEAT_IDLE_MS = 30 * 24 * 3600 * 1000; // un poste inactif 30 j libère sa place

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

let privKey: CryptoKey | null = null;
async function signingKey(): Promise<CryptoKey> {
  if (privKey) return privKey;
  const { data, error } = await supa.from("server_secrets").select("value")
    .eq("name", "ed25519_private_b64").single();
  if (error || !data) throw new Error("cle de signature absente");
  const seed = Uint8Array.from(atob(data.value), (c) => c.charCodeAt(0));
  // enveloppe PKCS8 d'une graine Ed25519 brute (WebCrypto ne lit pas le raw privé)
  const prefix = new Uint8Array([0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05,
    0x06, 0x03, 0x2b, 0x65, 0x70, 0x04, 0x22, 0x04, 0x20]);
  const pkcs8 = new Uint8Array(prefix.length + seed.length);
  pkcs8.set(prefix); pkcs8.set(seed, prefix.length);
  privKey = await crypto.subtle.importKey("pkcs8", pkcs8, { name: "Ed25519" },
    false, ["sign"]);
  return privKey;
}

function b64url(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

// Jeton NOVA1 — même format que licensing.verify_key côté app :
// payload {t,e,x,s} + m (empreinte machine, vérifiée localement par l'app)
async function mintToken(lic: Record<string, unknown>, machine: string) {
  const end = lic.current_period_end
    ? new Date(lic.current_period_end as string).getTime() : 0;
  const exp = end ? Math.floor((end + GRACE_MS) / 1000) : 0;
  const payload = new TextEncoder().encode(JSON.stringify({
    t: lic.tier, e: lic.email, x: exp, s: lic.seats, m: machine,
  }));
  const sig = new Uint8Array(
    await crypto.subtle.sign("Ed25519", await signingKey(), payload));
  return `NOVA1.${b64url(payload)}.${b64url(sig)}`;
}

const json = (code: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status: code,
    headers: { "Content-Type": "application/json; charset=utf-8", ...CORS },
  });

async function activate(req: Request): Promise<Response> {
  let body: { key?: string; machine?: string };
  try { body = await req.json(); } catch { return json(400, { ok: false, error: "Requête invalide." }); }
  const key = (body.key || "").trim().toUpperCase();
  const machine = (body.machine || "").trim().toLowerCase();
  if (!/^NOVA-[A-Z0-9-]{8,40}$/.test(key) || !/^[a-f0-9]{16,64}$/.test(machine)) {
    return json(400, { ok: false, error: "Clé ou empreinte machine invalide." });
  }
  const { data: lic } = await supa.from("licenses").select("*")
    .eq("key", key).maybeSingle();
  if (!lic) return json(404, { ok: false, error: "Clé inconnue." });
  if (lic.status === "canceled") {
    return json(403, { ok: false, error: "Abonnement résilié — réabonnez-vous pour réactiver Nova." });
  }
  const end = lic.current_period_end ? new Date(lic.current_period_end).getTime() : 0;
  if (end && Date.now() > end + GRACE_MS) {
    return json(403, { ok: false, error: "Abonnement expiré — le paiement n'a pas été renouvelé." });
  }
  const { data: acts } = await supa.from("activations").select("*")
    .eq("license_id", lic.id);
  const now = Date.now();
  const mine = (acts || []).find((a) => a.machine_hash === machine);
  const others = (acts || []).filter((a) =>
    a.machine_hash !== machine &&
    now - new Date(a.last_seen).getTime() < SEAT_IDLE_MS);
  if (!mine && others.length >= lic.seats) {
    return json(403, { ok: false, error:
      `Licence déjà utilisée sur ${lic.seats} appareil(s). Un appareil inutilisé pendant 30 jours libère sa place automatiquement.` });
  }
  await supa.from("activations").upsert(
    { license_id: lic.id, machine_hash: machine, last_seen: new Date().toISOString() },
    { onConflict: "license_id,machine_hash" });
  const token = await mintToken(lic, machine);
  // Turbo passe par la fonction « turbo » (relais) : le jeton ci-dessous
  // sert d'identité par machine — aucune clé fournisseur ne sort du serveur.
  return json(200, { ok: true, token, tier: lic.tier });
}

// Clé d'une session de paiement — consommé par la page merci.html du site
// vitrine (le session_id Stripe est inforgeable et propre à l'acheteur).
async function keyOf(sessionId: string): Promise<Response> {
  const { data: lic } = await supa.from("licenses")
    .select("key,tier").eq("checkout_session_id", sessionId).maybeSingle();
  if (!lic) return json(404, { ok: false, error: "Paiement en cours de traitement." });
  return json(200, { ok: true, key: lic.key, tier: lic.tier });
}

Deno.serve(async (req: Request) => {
  try {
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    const url = new URL(req.url);
    if (req.method === "POST" && url.pathname.endsWith("/activate")) {
      return await activate(req);
    }
    const sid = url.searchParams.get("session_id");
    if (req.method === "GET" && sid && url.pathname.endsWith("/key")) {
      return await keyOf(sid);
    }
    if (req.method === "GET" && sid) {
      // anciens liens : la page rend sur le site vitrine (supabase.co interdit le HTML)
      return new Response(null, { status: 302, headers: {
        Location: `${SUCCESS_PAGE}?session_id=${encodeURIComponent(sid)}`, ...CORS } });
    }
    return json(404, { ok: false, error: "Introuvable." });
  } catch (e) {
    console.error("license error", e);
    return json(500, { ok: false, error: "Erreur serveur." });
  }
});
