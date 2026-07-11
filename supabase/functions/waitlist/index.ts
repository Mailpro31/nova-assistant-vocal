// Nova — inscription aux nouveautés (formulaire de la landing).
// Public, sans JWT : l'e-mail donné volontairement est la seule donnée ;
// un pot de miel (champ « website ») écarte les robots naïfs, l'upsert
// idempotent absorbe les doublons. Service role uniquement côté table (RLS).
import { createClient } from "jsr:@supabase/supabase-js@2";

const supa = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

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

Deno.serve(async (req: Request) => {
  try {
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    if (req.method !== "POST") return json(405, { ok: false });
    let b: { email?: string; lang?: string; website?: string };
    try { b = await req.json(); } catch { return json(400, { ok: false }); }
    if (!b || typeof b !== "object") return json(400, { ok: false });
    if (b.website) return json(200, { ok: true });   // pot de miel : on fait semblant
    const email = String(b.email || "").trim().toLowerCase();
    if (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) {
      return json(400, { ok: false, error: "invalid_email" });
    }
    const lang = b.lang === "en" ? "en" : "fr";
    const { error } = await supa.from("waitlist")
      .upsert({ email, lang }, { onConflict: "email", ignoreDuplicates: true });
    if (error) { console.error("waitlist insert", error); return json(500, { ok: false }); }
    return json(200, { ok: true });
  } catch (e) {
    console.error("waitlist error", e);
    return json(500, { ok: false });
  }
});
