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
// L'app lie le jeton à SA propre empreinte (m) : un jeton d'une autre machine
// est rejeté. Aucun secret exposé, réponse infalsifiable.
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

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

const json = (code: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status: code,
    headers: { "Content-Type": "application/json; charset=utf-8", ...CORS },
  });

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

// Jeton d'essai signé, lié à l'empreinte machine.
async function mintTrialToken(machine: string, startEpoch: number): Promise<string> {
  const payload = new TextEncoder().encode(JSON.stringify({
    k: "trial", m: machine, s: startEpoch,
  }));
  const sig = new Uint8Array(
    await crypto.subtle.sign("Ed25519", await signingKey(), payload));
  return `NOVAT1.${b64url(payload)}.${b64url(sig)}`;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json(405, { ok: false });

  let body: { machine?: string };
  try { body = await req.json(); } catch { return json(400, { ok: false, error: "Requête invalide." }); }
  if (!body || typeof body !== "object") {
    return json(400, { ok: false, error: "Requête invalide." });
  }
  const machine = (body.machine || "").trim().toLowerCase();
  if (!/^[a-f0-9]{16,64}$/.test(machine)) {
    return json(400, { ok: false, error: "Empreinte machine invalide." });
  }

  try {
    // Scelle la date au 1er contact ; ne fait rien si déjà scellée (atomique).
    await supa.from("trial_starts").insert({ machine_hash: machine })
      .then(() => {}, () => {}); // conflit de PK = déjà scellée → ignoré
    const { data, error } = await supa.from("trial_starts")
      .select("started_on").eq("machine_hash", machine).single();
    if (error || !data) throw new Error("lecture impossible");

    // started_on est une DATE (minuit UTC). Epoch secondes de ce minuit.
    const startEpoch = Math.floor(new Date(`${data.started_on}T00:00:00Z`).getTime() / 1000);
    const token = await mintTrialToken(machine, startEpoch);
    return json(200, {
      ok: true,
      token,
      started_on: data.started_on,
      trial_days: TRIAL_DAYS,
    });
  } catch (_e) {
    // Défensif : jamais d'échec dur — l'app retombe sur son essai local.
    return json(200, { ok: false, error: "indisponible" });
  }
});
