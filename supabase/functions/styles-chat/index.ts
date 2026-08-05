// Nova — relais « styles-chat » : reformulation (Styles) via Anthropic avec
// la clé SERVEUR (server_secrets.anthropic_api_key) — la clé du fournisseur
// ne quitte JAMAIS le serveur.
//
// L'app envoie une requête au format OpenAI chat/completions (c'est le format
// que son client HTTP connaît déjà) ; ce relais le traduit vers l'API
// Messages d'Anthropic (Haiku) et renvoie la réponse au même format OpenAI.
//
// Sécurité : jeton NOVA1 signé Ed25519 vérifié (palier Pro/Ultra/Business),
// expiration + révocation en temps réel (même logique fail-open que « turbo »),
// quota quotidien ATOMIQUE par machine (styles_consume_capped) avec
// remboursement si le fournisseur échoue.
//
// RGPD : le texte dicté transite en mémoire uniquement — rien n'est écrit en
// base, rien n'est journalisé. Anthropic API : pas d'entraînement sur les
// données, DPA disponible.
import { createClient } from "jsr:@supabase/supabase-js@2";
// vérification Ed25519 en pur JS (@noble), identique à « turbo »
import * as ed from "npm:@noble/ed25519@2";

const supa = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

// clé PUBLIQUE de vérification des jetons NOVA1 (la même que dans l'app)
const PUBLIC_KEY_B64 = "Q+U/LqaeFgLSDkvqiAXRcHQ8DSwqU9NcrHiPt8A6EJE=";
const GRACE_MS = 7 * 24 * 3600 * 1000;
const TRIAL_SECS = 14 * 24 * 3600; // durée de l'essai Pro
const ANTHROPIC_MODEL = "claude-haiku-4-5-20251001";
const MAX_TEXT_CHARS = 8000; // une dictée reste une dictée
const MAX_SYSTEM_CHARS = 4000;
const PROVIDER_TIMEOUT_MS = 25_000;

// fair-use quotidien par machine (interne, jamais affiché dans l'UI)
const DAILY_CAP: Record<string, number> = {
  pro: 500,
  ultra: 2000,
  business: 5000,
};
const TRIAL_DAILY_CAP = 50; // essai Pro : généreux mais borné

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

const un64 = (s: string) =>
  Uint8Array.from(
    atob(s.replace(/-/g, "+").replace(/_/g, "/") +
      "=".repeat((4 - s.length % 4) % 4)),
    (c) => c.charCodeAt(0),
  );

async function verifyToken(tok: string): Promise<Record<string, unknown> | null> {
  const m = /^NOVA1\.([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)$/.exec(tok || "");
  if (!m) return null;
  // décodage + vérif + parse sous une seule garde : un segment base64 ou un
  // JSON invalide renvoie null (→ 401), jamais une exception non gérée (→ 500)
  try {
    const payload = un64(m[1]), sig = un64(m[2]);
    if (!(await ed.verifyAsync(sig, payload, PUB_BYTES))) return null;
    return JSON.parse(new TextDecoder().decode(payload));
  } catch {
    return null;
  }
}

// Jeton d'essai « NOVAT1.<payload>.<sig> » (émis par trial-check, même clé) :
// { k:"trial", m:<machine>, s:<epoch début> }. Valide 14 jours après s.
// Sans ça, un utilisateur EN ESSAI n'a aucun jeton NOVA1 à présenter : le
// cloud lui répondait 401 et l'app retombait sur le moteur local (lent) —
// exactement à l'opposé de la démonstration qu'on veut faire pendant l'essai.
async function verifyTrialToken(tok: string): Promise<Record<string, unknown> | null> {
  const m = /^NOVAT1\.([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)$/.exec(tok || "");
  if (!m) return null;
  try {
    const payload = un64(m[1]), sig = un64(m[2]);
    if (!(await ed.verifyAsync(sig, payload, PUB_BYTES))) return null;
    const data = JSON.parse(new TextDecoder().decode(payload));
    if (data.k !== "trial" || !data.m || !data.s) return null;
    if (Date.now() / 1000 > Number(data.s) + TRIAL_SECS) return null;
    return data;
  } catch {
    return null;
  }
}

let anthropicKey = "";
async function serverAnthropicKey(): Promise<string> {
  if (anthropicKey) return anthropicKey;
  const { data } = await supa.from("server_secrets").select("value")
    .eq("name", "anthropic_api_key").maybeSingle();
  anthropicKey = data?.value || "";
  return anthropicKey;
}

// Révocation en temps réel, FAIL-OPEN strict : identique à « turbo » — on ne
// refuse QUE si TOUTES les licences de la machine sont résiliées/expirées.
async function licenseRevoked(machine: string): Promise<boolean> {
  try {
    const { data: acts } = await supa.from("activations")
      .select("license_id").eq("machine_hash", machine);
    if (!acts || !acts.length) return false;
    const ids = acts.map((a) => a.license_id);
    const { data: lics } = await supa.from("licenses")
      .select("status,current_period_end").in("id", ids);
    if (!lics || !lics.length) return false;
    const now = Date.now();
    const anyValid = lics.some((l) => {
      if (l.status === "canceled") return false;
      const end = l.current_period_end ? new Date(l.current_period_end).getTime() : 0;
      if (end && now > end + GRACE_MS) return false;
      return true;
    });
    return !anyValid;
  } catch {
    return false;
  }
}

Deno.serve(async (req: Request) => {
  try {
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    if (req.method !== "POST") return json(404, { ok: false, error: "Introuvable." });

    // L'app poste sur {base_url}/chat/completions (format OpenAI)
    if (!new URL(req.url).pathname.endsWith("/chat/completions")) {
      return json(404, { ok: false, error: "Introuvable." });
    }

    // — authentification : jeton NOVA1 (abonné) ou NOVAT1 (essai) signé —
    const tok = (req.headers.get("Authorization") || "").replace(/^Bearer\s+/i, "");
    let machine: string;
    let cap: number;
    if (tok.startsWith("NOVAT1.")) {
      const t = await verifyTrialToken(tok);
      if (!t) return json(401, { ok: false, error: "Essai expiré ou jeton invalide." });
      machine = String(t.m);
      cap = TRIAL_DAILY_CAP;
    } else {
      const p = await verifyToken(tok);
      const tier = String(p?.t || "");
      if (!p || !(tier in DAILY_CAP)) {
        return json(401, { ok: false, error: "Abonnement Nova requis." });
      }
      if (!p.x || Date.now() / 1000 > Number(p.x)) {
        return json(401, { ok: false, error: "Licence expirée." });
      }
      machine = String(p.m || "");
      if (!machine) return json(401, { ok: false, error: "Jeton invalide." });
      if (await licenseRevoked(machine)) {
        return json(403, { ok: false, error: "Abonnement résilié." });
      }
      cap = DAILY_CAP[tier];
    }

    // — requête au format OpenAI : messages[system? + user] —
    let body: {
      messages?: { role?: string; content?: string }[];
      temperature?: number;
    };
    try {
      body = await req.json();
    } catch {
      return json(400, { ok: false, error: "Requête invalide." });
    }
    const messages = Array.isArray(body.messages) ? body.messages : [];
    const system = String(
      messages.find((m) => m.role === "system")?.content || "",
    ).slice(0, MAX_SYSTEM_CHARS);
    const text = String(
      messages.find((m) => m.role === "user")?.content || "",
    ).slice(0, MAX_TEXT_CHARS);
    if (!text.trim()) return json(400, { ok: false, error: "Texte vide." });

    // — quota quotidien atomique, consommé AVANT l'appel fournisseur —
    let consumed = false;
    {
      const { data, error } = await supa.rpc("styles_consume_capped", {
        p_machine: machine, p_count: 1, p_cap: cap });
      if (error) {
        // RPC absente (migration en retard) → repli legacy fail-open
        const today = new Date().toISOString().slice(0, 10);
        const { data: u } = await supa.from("styles_usage").select("count")
          .eq("machine_hash", machine).eq("day", today).maybeSingle();
        if ((u?.count || 0) + 1 > cap) {
          return json(429, { ok: false, error: "quota" });
        }
      } else if (data !== true) {
        return json(429, { ok: false, error: "quota" });
      } else {
        consumed = true;
      }
    }

    // — appel Anthropic (clé serveur, jamais exposée) —
    const key = await serverAnthropicKey();
    if (!key) return json(503, { ok: false, error: "Service indisponible." });
    const r = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: ANTHROPIC_MODEL,
        max_tokens: Math.min(4096, Math.max(256, Math.ceil(text.length * 1.5))),
        system: system ||
          "Reformule le texte dicté selon les consignes. Réponds UNIQUEMENT avec le texte reformulé, sans préambule ni commentaire.",
        messages: [{ role: "user", content: text }],
        temperature: typeof body.temperature === "number"
          ? Math.min(1, Math.max(0, body.temperature))
          : 0.3,
      }),
      signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS),
    });
    if (!r.ok) {
      // remboursement : un échec fournisseur ne consomme pas le quota
      if (consumed) {
        await supa.rpc("styles_consume", { p_machine: machine, p_count: -1 });
      }
      return json(502, { ok: false, error: "Service momentanément indisponible." });
    }
    const out = await r.json();
    const content = String(out?.content?.[0]?.text || "").trim();
    if (!content) {
      if (consumed) {
        await supa.rpc("styles_consume", { p_machine: machine, p_count: -1 });
      }
      return json(502, { ok: false, error: "Réponse vide." });
    }

    // schéma legacy (RPC plafonnée absente) : consommation après succès
    if (!consumed) {
      await supa.rpc("styles_consume", { p_machine: machine, p_count: 1 });
    }

    // Réponse au format OpenAI attendu par le client de l'app
    return json(200, {
      choices: [{ message: { role: "assistant", content } }],
    });
  } catch (e) {
    console.error("styles-chat error", e);
    return json(500, { ok: false, error: "Erreur serveur." });
  }
});
