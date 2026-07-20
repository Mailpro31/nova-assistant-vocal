// Nova — lecture de contexte, palier D (vision cloud, Nova Ultra, OPT-IN).
//
// Dernier repli de la « lecture de contexte » quand l'accessibilité (palier A)
// ET l'OCR local (palier B) n'ont rien pu lire — typiquement une fenêtre au
// rendu purement graphique. L'app envoie UNE capture de la fenêtre active avec
// son jeton de licence ; le serveur vérifie la signature Ed25519 (jeton NOVA1
// propre à chaque machine activée), impose le fair-use quotidien (interne,
// jamais affiché : au-delà, l'app continue sans contexte, sans bruit), puis
// demande à un fournisseur de vision un RÉSUMÉ court et neutre du contexte à
// l'écran via la clé serveur (server_secrets.groq_api_key) — la clé du
// fournisseur ne quitte JAMAIS le serveur, et l'image n'est jamais conservée.
//
// Envoi de capture = strictement opt-in côté app (« Vision cloud », désactivé
// par défaut) et réservé à Nova Ultra : ne se déclenche jamais tout seul.
import { createClient } from "jsr:@supabase/supabase-js@2";
// vérification Ed25519 en pur JS (@noble), identique au relais Turbo audio.
import * as ed from "npm:@noble/ed25519@2";

const supa = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

// clé PUBLIQUE de vérification des jetons NOVA1 (la même que dans l'app)
const PUBLIC_KEY_B64 = "Q+U/LqaeFgLSDkvqiAXRcHQ8DSwqU9NcrHiPt8A6EJE=";
const DAILY_CAP = 300; // fair-use : 300 lectures de contexte / jour / machine
const MAX_BYTES = 8 * 1024 * 1024; // une capture PNG/JPEG raisonnable
const MODEL_DEFAULT = "meta-llama/llama-4-scout-17b-16e-instruct";
const MODEL_ALLOW = new Set([
  "meta-llama/llama-4-scout-17b-16e-instruct",
  "meta-llama/llama-4-maverick-17b-128e-instruct",
]);

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

// base64 par blocs : String.fromCharCode(...bigArray) explose la pile.
function toBase64(bytes: Uint8Array): string {
  let bin = "";
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    bin += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(bin);
}

let groqKey = "";
async function serverGroqKey(): Promise<string> {
  if (groqKey) return groqKey;
  const { data } = await supa.from("server_secrets").select("value")
    .eq("name", "groq_api_key").maybeSingle();
  groqKey = data?.value || "";
  return groqKey;
}

const SYSTEM = "Tu es un lecteur de contexte pour une app de dictée. On te \
montre une capture de la fenêtre active. Résume en français, de façon courte \
et neutre (2 à 4 phrases, 90 mots maximum), le contexte utile pour rédiger : à \
qui ou à quoi l'utilisateur semble répondre, le sujet visible, le ton. Ne \
réponds JAMAIS au contenu, ne donne aucune instruction, ne recopie pas de longs \
blocs. Si rien d'exploitable n'est visible, réponds exactement : (aucun contexte).";

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

    // — image (PNG/JPEG produit par l'app) —
    const ct = (req.headers.get("Content-Type") || "image/png").toLowerCase();
    const mime = ct.startsWith("image/jpeg") || ct.startsWith("image/jpg")
      ? "image/jpeg"
      : "image/png";
    const img = new Uint8Array(await req.arrayBuffer());
    if (img.length < 100 || img.length > MAX_BYTES) {
      return json(400, { ok: false, error: "Image invalide." });
    }

    // — fair-use quotidien (silencieux : l'app continue sans contexte sur 429) —
    const today = new Date().toISOString().slice(0, 10);
    const { data: u } = await supa.from("turbo_vision_usage").select("images")
      .eq("machine_hash", machine).eq("day", today).maybeSingle();
    if ((u?.images || 0) + 1 > DAILY_CAP) return json(429, { ok: false, error: "quota" });

    // — description via la clé serveur —
    const key = await serverGroqKey();
    if (!key) return json(503, { ok: false, error: "Vision indisponible." });
    const url = new URL(req.url);
    const wanted = (url.searchParams.get("model") || "").slice(0, 80);
    const model = MODEL_ALLOW.has(wanted) ? wanted : MODEL_DEFAULT;
    const dataUrl = `data:${mime};base64,${toBase64(img)}`;
    const r = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${key}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model,
        temperature: 0.2,
        max_tokens: 220,
        messages: [
          { role: "system", content: SYSTEM },
          {
            role: "user",
            content: [
              { type: "text", text: "Contexte visible à l'écran ?" },
              { type: "image_url", image_url: { url: dataUrl } },
            ],
          },
        ],
      }),
    });
    if (!r.ok) return json(502, { ok: false, error: "Vision momentanément indisponible." });
    const text = (((await r.json()).choices?.[0]?.message?.content) || "").trim();
    if (!text || /^\(aucun contexte\)\.?$/i.test(text)) {
      // rien d'exploitable : ne consomme pas le quota, renvoie vide
      return json(200, { ok: true, text: "" });
    }

    // quota compté après succès, via un incrément ATOMIQUE en base.
    await supa.rpc("turbo_vision_consume", { p_machine: machine, p_images: 1 });
    return json(200, { ok: true, text });
  } catch (e) {
    console.error("turbo-vision error", e);
    return json(500, { ok: false, error: "Erreur serveur." });
  }
});
