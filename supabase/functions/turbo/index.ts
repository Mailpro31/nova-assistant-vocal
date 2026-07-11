// Nova — relais Turbo : l'app envoie l'audio avec son jeton de licence ;
// le serveur vérifie la signature Ed25519 (chaque machine activée a son
// jeton propre = identité par utilisateur), applique le fair-use quotidien
// (3 h d'audio/jour/machine — interne, jamais affiché dans l'UI : au-delà,
// l'app retombe en Intelligence privée sans bruit), puis transcrit via Groq
// avec la clé serveur (server_secrets.groq_api_key) — la clé du fournisseur
// ne quitte JAMAIS le serveur.
import { createClient } from "jsr:@supabase/supabase-js@2";
// vérification Ed25519 en pur JS (@noble) : indépendante des variations
// WebCrypto d'un runtime à l'autre — testée de bout en bout (jeton réel
// → 200 + texte Groq ; signature altérée → 401)
import * as ed from "npm:@noble/ed25519@2";

const supa = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

// clé PUBLIQUE de vérification des jetons NOVA1 (la même que dans l'app)
const PUBLIC_KEY_B64 = "Q+U/LqaeFgLSDkvqiAXRcHQ8DSwqU9NcrHiPt8A6EJE=";
const DAILY_CAP_S = 3 * 3600; // fair-use : 3 h d'audio / jour / machine
const MAX_BYTES = 25 * 1024 * 1024;

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
  const payload = un64(m[1]), sig = un64(m[2]);
  let okSig = false;
  try {
    okSig = await ed.verifyAsync(sig, payload, PUB_BYTES);
  } catch {
    okSig = false;
  }
  if (!okSig) return null;
  try { return JSON.parse(new TextDecoder().decode(payload)); } catch { return null; }
}

let groqKey = "";
async function serverGroqKey(): Promise<string> {
  if (groqKey) return groqKey;
  const { data } = await supa.from("server_secrets").select("value")
    .eq("name", "groq_api_key").maybeSingle();
  groqKey = data?.value || "";
  return groqKey;
}

Deno.serve(async (req: Request) => {
  try {
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    if (req.method !== "POST") return json(404, { ok: false, error: "Introuvable." });

    // — authentification : jeton NOVA1 signé, palier Ultra, non expiré —
    const tok = (req.headers.get("Authorization") || "").replace(/^Bearer\s+/i, "");
    const p = await verifyToken(tok);
    if (!p || p.t !== "ultra") return json(401, { ok: false, error: "Licence Ultra requise." });
    if (p.x && Date.now() / 1000 > Number(p.x)) {
      return json(401, { ok: false, error: "Licence expirée." });
    }
    const machine = String(p.m || "");
    if (!machine) return json(401, { ok: false, error: "Jeton invalide." });

    // — audio (WAV 16 kHz mono 16 bits produit par l'app) —
    const wav = new Uint8Array(await req.arrayBuffer());
    if (wav.length < 100 || wav.length > MAX_BYTES) {
      return json(400, { ok: false, error: "Audio invalide." });
    }
    const seconds = Math.max(1, Math.round((wav.length - 44) / 32000));

    // — fair-use quotidien (silencieux : l'app retombe en local sur 429) —
    const today = new Date().toISOString().slice(0, 10);
    const { data: u } = await supa.from("turbo_usage").select("seconds")
      .eq("machine_hash", machine).eq("day", today).maybeSingle();
    const used = u?.seconds || 0;
    if (used + seconds > DAILY_CAP_S) return json(429, { ok: false, error: "quota" });

    // — transcription via la clé serveur —
    const key = await serverGroqKey();
    if (!key) return json(503, { ok: false, error: "Turbo indisponible." });
    const url = new URL(req.url);
    const form = new FormData();
    form.append("file", new Blob([wav], { type: "audio/wav" }), "audio.wav");
    form.append("model", (url.searchParams.get("model") || "whisper-large-v3-turbo").slice(0, 60));
    const lang = (url.searchParams.get("language") || "").slice(0, 8);
    if (lang) form.append("language", lang);
    const prompt = (url.searchParams.get("prompt") || "").slice(0, 200);
    if (prompt) form.append("prompt", prompt);
    const r = await fetch("https://api.groq.com/openai/v1/audio/transcriptions", {
      method: "POST",
      headers: { Authorization: `Bearer ${key}` },
      body: form,
    });
    if (!r.ok) return json(502, { ok: false, error: `stt ${r.status}` });
    const text = ((await r.json()).text || "").trim();

    // usage compté après succès (un échec fournisseur ne consomme pas le quota)
    await supa.from("turbo_usage").upsert(
      { machine_hash: machine, day: today, seconds: used + seconds,
        updated_at: new Date().toISOString() },
      { onConflict: "machine_hash,day" },
    );
    return json(200, { ok: true, text });
  } catch (e) {
    console.error("turbo error", e);
    return json(500, { ok: false, error: "Erreur serveur." });
  }
});
