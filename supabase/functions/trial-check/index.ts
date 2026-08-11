// Nova — scellage serveur de l'essai Pro (14 jours) par empreinte machine.
//
// But : empêcher l'essai « infini » par réinstallation. Le tout premier
// contact d'une machine scelle sa date de début côté serveur (table
// `trial_starts`, machine_hash = clé primaire) ; tout contact ultérieur
// renvoie la MÊME date. Effacer la config locale ne réinitialise donc plus
// rien.
//
// Réponse = jeton « NOVAT1.<payload_b64url>.<sig_b64url> » signé Ed25519 avec
// la même clé privée serveur que les licences (server_secrets), donc vérifiable
// LOCALEMENT par l'app avec la clé publique déjà embarquée. Payload :
//   { k:"trial", m:<empreinte>, s:<epoch début, minuit UTC> }
// + jeton gratuit « NOVAF1 » (k:"free") : crédit Turbo du palier Gratuit,
// vérifiable par styles-chat. Les DEUX sont signés — l'ancien NOVAFREE non
// signé était forgeable à volonté (pentest 2026-08-11).
//
// Auth : pas de JWT (verify_jwt off) — l'empreinte n'est pas un secret et la
// réponse est signée. Défensif : toute erreur → 200 sans jeton (l'app retombe
// alors sur son essai local, jamais de blocage).
import { createClient } from "jsr:@supabase/supabase-js@2";

const supa = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

const TRIAL_DAYS = 14;
// Anti-reset : nombre de NOUVELLES empreintes machine scellées par empreinte
// réseau (IP hachée) et par jour. Sans ça, un script déclare des machines
// fantômes à l'infini (essai perpétuel + remplissage de trial_starts).
const MAX_NEW_PER_IP_DAY = 5;
// Disjoncteur GLOBAL : nouvelles empreintes scellées par jour, toutes IP
// confondues. L'empreinte réseau reste partiellement falsifiable (1re valeur
// du XFF) — ce plafond borne le pire des cas, quoi que fasse l'attaquant.
const MAX_NEW_GLOBAL_DAY = 500;
const IP_SALT = "nova-trial-v1";

// Origines navigateur autorisées (le site). L'app desktop appelle en direct
// (pas de CORS côté reqwest) — restreindre l'en-tête ne la bloque pas.
const ALLOWED_ORIGINS = ["https://www.novaspeak.app", "https://novaspeak.app"];

function corsFor(req: Request): Record<string, string> {
  const origin = req.headers.get("Origin") || "";
  return {
    "Access-Control-Allow-Origin": ALLOWED_ORIGINS.includes(origin)
      ? origin
      : ALLOWED_ORIGINS[0],
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Vary": "Origin",
  };
}

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

async function sha256hex(s: string): Promise<string> {
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Empreinte réseau pseudonyme : PREMIÈRE IP de x-forwarded-for. La dernière
// (ajoutée par la passerelle) variait à chaque requête sur l'infra Supabase —
// le plafond par IP ne se déclenchait jamais (pentest 2026-08-11). La première
// est fournie par le client (falsifiable) : elle reste utile contre les bots
// naïfs, et le disjoncteur global borne le reste.
async function ipHash(req: Request): Promise<string> {
  const xff = req.headers.get("x-forwarded-for") || "";
  const ip = xff.split(",")[0].trim();
  if (!ip) return "";
  return (await sha256hex(IP_SALT + ":" + ip)).slice(0, 16);
}

// Jeton signé, lié à l'empreinte machine. kind: "trial" (NOVAT1) | "free" (NOVAF1)
async function mintToken(kind: "trial" | "free", machine: string, startEpoch: number): Promise<string> {
  const payload = new TextEncoder().encode(JSON.stringify({
    k: kind, m: machine, s: startEpoch,
  }));
  const sig = new Uint8Array(
    await crypto.subtle.sign("Ed25519", await signingKey(), payload));
  const prefix = kind === "trial" ? "NOVAT1" : "NOVAF1";
  return `${prefix}.${b64url(payload)}.${b64url(sig)}`;
}

Deno.serve(async (req) => {
  const CORS = corsFor(req);
  const json = (code: number, body: unknown) =>
    new Response(JSON.stringify(body), {
      status: code,
      headers: { "Content-Type": "application/json; charset=utf-8", ...CORS },
    });

  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json(405, { ok: false });

  let body: { machine?: unknown };
  try { body = await req.json(); } catch { return json(400, { ok: false, error: "Requête invalide." }); }
  if (!body || typeof body !== "object") {
    return json(400, { ok: false, error: "Requête invalide." });
  }
  // Le pentest a montré un 500 sur machine={objet} — validation de TYPE stricte.
  if (typeof body.machine !== "string") {
    return json(400, { ok: false, error: "Empreinte machine invalide." });
  }
  const machine = body.machine.trim().toLowerCase();
  if (!/^[a-f0-9]{16,64}$/.test(machine)) {
    return json(400, { ok: false, error: "Empreinte machine invalide." });
  }

  try {
    const iph = await ipHash(req);
    const today = new Date().toISOString().slice(0, 10);

    let { data: row } = await supa.from("trial_starts")
      .select("started_on").eq("machine_hash", machine).maybeSingle();

    if (!row) {
      // Nouvelle empreinte : borne par empreinte réseau ET disjoncteur global
      // journalier — casse le reset d'essai industrialisé (machines fantômes).
      if (iph) {
        const { count } = await supa.from("trial_starts")
          .select("machine_hash", { count: "exact", head: true })
          .eq("iph", iph).eq("started_on", today);
        if ((count || 0) >= MAX_NEW_PER_IP_DAY) {
          return json(200, { ok: false, error: "indisponible" });
        }
      }
      const { count: globalCount } = await supa.from("trial_starts")
        .select("machine_hash", { count: "exact", head: true })
        .eq("started_on", today);
      if ((globalCount || 0) >= MAX_NEW_GLOBAL_DAY) {
        return json(200, { ok: false, error: "indisponible" });
      }
      // Scelle la date au 1er contact (conflit de PK = déjà scellée → ignoré).
      // L'insertion avec iph peut échouer si la colonne n'existe pas encore
      // (migration 20260804 non appliquée) → repli sans iph, jamais bloquant.
      const { error: insErr } = await supa.from("trial_starts")
        .insert({ machine_hash: machine, iph });
      if (insErr) {
        await supa.from("trial_starts").insert({ machine_hash: machine })
          .then(() => {}, () => {});
      }
      const { data: sealed, error } = await supa.from("trial_starts")
        .select("started_on").eq("machine_hash", machine).single();
      if (error || !sealed) throw new Error("lecture impossible");
      row = sealed;
    }

    // started_on est une DATE (minuit UTC). Epoch secondes de ce minuit.
    const startEpoch = Math.floor(new Date(`${row.started_on}T00:00:00Z`).getTime() / 1000);
    const token = await mintToken("trial", machine, startEpoch);
    const freeToken = await mintToken("free", machine, startEpoch);
    return json(200, {
      ok: true,
      token,
      free_token: freeToken,
      started_on: row.started_on,
      trial_days: TRIAL_DAYS,
    });
  } catch (_e) {
    // Défensif : jamais d'échec dur — l'app retombe sur son essai local.
    return json(200, { ok: false, error: "indisponible" });
  }
});
