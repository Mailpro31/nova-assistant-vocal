// Nova — inscription aux nouveautés (formulaire de la landing).
// Public, sans JWT : l'e-mail donné volontairement est la seule donnée ;
// un pot de miel (champ « website ») écarte les robots naïfs, l'upsert
// idempotent absorbe les doublons, et une limite par empreinte réseau (IP
// hachée, jamais stockée en clair) borne les inscriptions massives d'un même
// réseau — pour ne pas polluer la liste et griller la réputation d'envoi.
// Service role uniquement côté table (RLS).
import { createClient } from "jsr:@supabase/supabase-js@2";

const supa = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

const MAX_PER_IP_H = 10;       // inscriptions max par empreinte réseau et par heure
const IP_SALT = "nova-wl-v1";  // sel de hachage d'empreinte (anti-abus, pseudonyme)

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

async function sha256hex(s: string): Promise<string> {
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
async function ipHash(req: Request): Promise<string> {
  const ip = (req.headers.get("x-forwarded-for") || "").split(",")[0].trim();
  if (!ip) return "";
  return (await sha256hex(IP_SALT + ":" + ip)).slice(0, 16);
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

Deno.serve(async (req: Request) => {
  try {
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    if (req.method !== "POST") return json(405, { ok: false });
    let b: { email?: string; lang?: string; website?: string };
    try { b = await req.json(); } catch { return json(400, { ok: false }); }
    if (!b || typeof b !== "object") return json(400, { ok: false });
    if (b.website) return json(200, { ok: true });   // pot de miel : on fait semblant
    const email = String(b.email || "").trim().toLowerCase();
    if (email.length > 254 || !EMAIL_RE.test(email)) {
      return json(400, { ok: false, error: "invalid_email" });
    }
    const lang = b.lang === "en" ? "en" : "fr";
    const iph = await ipHash(req);
    // limite par empreinte réseau (fenêtre 1 h glissante)
    if (iph) {
      const { count } = await supa.from("waitlist")
        .select("id", { count: "exact", head: true })
        .eq("iph", iph)
        .gt("created_at", new Date(Date.now() - 3600_000).toISOString());
      if ((count || 0) >= MAX_PER_IP_H) return json(429, { ok: false, error: "too_many" });
    }
    const { error } = await supa.from("waitlist")
      .upsert({ email, lang, iph }, { onConflict: "email", ignoreDuplicates: true });
    if (error) { console.error("waitlist insert", error); return json(500, { ok: false }); }
    return json(200, { ok: true });
  } catch (e) {
    console.error("waitlist error", e);
    return json(500, { ok: false });
  }
});
