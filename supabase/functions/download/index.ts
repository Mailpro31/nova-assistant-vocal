// Nova — porte e-mail du téléchargement gratuit : POST /code envoie un code à
// 6 chiffres (Resend, 15 min de validité), POST /verify le contrôle puis rend
// l'URL de l'installateur et range l'adresse dans « waitlist » (source
// download). JAMAIS BLOQUANT : si l'e-mail ne part pas (quota, panne, config
// absente), on rend l'URL directement — on ne perd pas un utilisateur pour un
// formulaire. Public, sans JWT ; pot de miel + limites d'envoi côté table.
import { createClient } from "jsr:@supabase/supabase-js@2";

const supa = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

const DL_URL =
  "https://github.com/Mailpro31/nova-assistant-vocal/releases/latest/download/Nova-Setup.exe";
const TTL_MIN = 15;          // validité du code
const MAX_SENDS_H = 3;       // envois max par adresse et par heure
const MAX_ATTEMPTS = 5;      // essais max par code

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

let mailCfg: { key: string; from: string } | null | undefined;
async function mailConfig() {
  if (mailCfg !== undefined) return mailCfg;
  const { data } = await supa.from("server_secrets").select("name,value")
    .in("name", ["resend_api_key", "email_from"]);
  const m = Object.fromEntries((data || []).map((r) => [r.name, r.value]));
  mailCfg = (m.resend_api_key && m.email_from)
    ? { key: m.resend_api_key, from: m.email_from } : null;
  return mailCfg;
}

async function sha256hex(s: string): Promise<string> {
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function codeEmailHtml(code: string, lang: string): string {
  const fr = lang !== "en";
  const title = fr ? "Votre code de téléchargement" : "Your download code";
  const p = fr
    ? `Entrez ce code sur novaspeak.app pour lancer le téléchargement. Il est valable ${TTL_MIN}&nbsp;minutes.`
    : `Enter this code on novaspeak.app to start your download. It is valid for ${TTL_MIN}&nbsp;minutes.`;
  const foot = fr
    ? "Vous n'êtes pas à l'origine de cette demande&nbsp;? Ignorez simplement cet e-mail."
    : "Didn't request this? Just ignore this email.";
  return `<!doctype html><html lang="${fr ? "fr" : "en"}"><body style="margin:0;padding:0;background:#F5F5F7">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F5F5F7;padding:36px 16px">
<tr><td align="center">
<table role="presentation" width="420" cellpadding="0" cellspacing="0"
  style="max-width:420px;width:100%;background:#ffffff;border:1px solid #E6E6EA;border-radius:16px">
<tr><td style="padding:32px 36px 28px">
  <div style="font:700 19px/1 -apple-system,'SF Pro Display','Segoe UI',sans-serif;
    letter-spacing:-.3px;color:#1D1D1F;padding-bottom:4px">Nova</div>
  <div style="font:400 12px/1.4 -apple-system,'Segoe UI',sans-serif;color:#98989F;
    padding-bottom:20px">${fr ? "La dictée qui écrit pour vous." : "Dictation that writes for you."}</div>
  <div style="font:700 16px/1.3 -apple-system,'Segoe UI',sans-serif;letter-spacing:-.2px;
    color:#1D1D1F;padding-bottom:8px">${title}</div>
  <div style="font:400 13px/1.55 -apple-system,'Segoe UI',sans-serif;color:#5A5A5E;
    padding-bottom:18px">${p}</div>
  <div style="background:#1A1A1D;border-radius:10px;padding:16px;text-align:center;
    font:700 26px/1 ui-monospace,Menlo,Consolas,monospace;letter-spacing:10px;
    color:#ffffff;margin-bottom:18px">${code}</div>
  <div style="border-top:1px solid #ECECF0;padding-top:12px;
    font:400 11px/1.6 -apple-system,'Segoe UI',sans-serif;color:#98989F">${foot}</div>
</td></tr></table>
</td></tr></table></body></html>`;
}

async function sendCode(to: string, code: string, lang: string): Promise<boolean> {
  try {
    const cfg = await mailConfig();
    if (!cfg) return false;
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { "Authorization": `Bearer ${cfg.key}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        from: cfg.from,
        to: [to],
        subject: lang === "en"
          ? `Your Nova download code: ${code}`
          : `Votre code de téléchargement Nova : ${code}`,
        html: codeEmailHtml(code, lang),
      }),
    });
    if (!r.ok) console.error("resend code", r.status, await r.text());
    return r.ok;
  } catch (e) {
    console.error("resend code error", e);
    return false;
  }
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

async function requestCode(b: Record<string, unknown>): Promise<Response> {
  if (b.website) return json(200, { ok: true, sent: true });   // pot de miel
  const email = String(b.email || "").trim().toLowerCase();
  const lang = b.lang === "en" ? "en" : "fr";
  if (email.length > 254 || !EMAIL_RE.test(email)) {
    return json(400, { ok: false, error: "invalid_email" });
  }
  // limite d'envoi : 3 codes / heure / adresse
  const { count } = await supa.from("download_codes")
    .select("id", { count: "exact", head: true })
    .eq("email", email)
    .gt("created_at", new Date(Date.now() - 3600_000).toISOString());
  if ((count || 0) >= MAX_SENDS_H) return json(429, { ok: false, error: "too_many" });
  const code = String(100000 + (crypto.getRandomValues(new Uint32Array(1))[0] % 900000));
  await supa.from("download_codes").insert({
    email,
    code_hash: await sha256hex(`${email}:${code}`),
    expires_at: new Date(Date.now() + TTL_MIN * 60_000).toISOString(),
  });
  const sent = await sendCode(email, code, lang);
  // e-mail impossible (dormant, quota, panne) → on ouvre : l'utilisateur
  // télécharge quand même, l'adresse est quand même enregistrée
  if (!sent) {
    await supa.from("waitlist").upsert(
      { email, lang, source: "download" },
      { onConflict: "email", ignoreDuplicates: true });
    return json(200, { ok: true, open: true, url: DL_URL });
  }
  return json(200, { ok: true, sent: true });
}

async function verifyCode(b: Record<string, unknown>): Promise<Response> {
  const email = String(b.email || "").trim().toLowerCase();
  const code = String(b.code || "").trim();
  if (!EMAIL_RE.test(email) || !/^\d{6}$/.test(code)) {
    return json(400, { ok: false, error: "bad_code" });
  }
  const { data: row } = await supa.from("download_codes")
    .select("*").eq("email", email).is("consumed_at", null)
    .order("created_at", { ascending: false }).limit(1).maybeSingle();
  if (!row || new Date(row.expires_at).getTime() < Date.now()) {
    return json(400, { ok: false, error: "expired" });
  }
  if (row.attempts >= MAX_ATTEMPTS) return json(429, { ok: false, error: "too_many" });
  if (row.code_hash !== await sha256hex(`${email}:${code}`)) {
    await supa.from("download_codes").update({ attempts: row.attempts + 1 })
      .eq("id", row.id);
    return json(400, { ok: false, error: "bad_code" });
  }
  await supa.from("download_codes").update(
    { consumed_at: new Date().toISOString() }).eq("id", row.id);
  const lang = b.lang === "en" ? "en" : "fr";
  await supa.from("waitlist").upsert(
    { email, lang, source: "download" },
    { onConflict: "email", ignoreDuplicates: true });
  return json(200, { ok: true, url: DL_URL });
}

Deno.serve(async (req: Request) => {
  try {
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    if (req.method !== "POST") return json(405, { ok: false });
    let b: Record<string, unknown>;
    try { b = await req.json(); } catch { return json(400, { ok: false }); }
    if (!b || typeof b !== "object") return json(400, { ok: false });
    const path = new URL(req.url).pathname;
    if (path.endsWith("/code")) return await requestCode(b);
    if (path.endsWith("/verify")) return await verifyCode(b);
    return json(404, { ok: false });
  } catch (e) {
    console.error("download error", e);
    return json(500, { ok: false });
  }
});
