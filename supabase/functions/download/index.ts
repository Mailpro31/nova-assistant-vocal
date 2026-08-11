// Nova — porte e-mail du téléchargement gratuit : POST /code envoie un code à
// 6 chiffres (Resend, 15 min de validité), POST /verify le contrôle puis rend
// l'URL de l'installateur et range l'adresse dans « waitlist » (source
// download). JAMAIS BLOQUANT : si l'e-mail ne peut pas partir (config dormante,
// insert en échec, quota, panne), on rend l'URL directement — on ne perd pas un
// utilisateur pour un formulaire. Public, sans JWT ; pot de miel + limites de
// débit par e-mail ET par empreinte réseau (IP hachée, jamais stockée en clair).
import { createClient } from "jsr:@supabase/supabase-js@2";

const supa = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

const DL_URL =
  "https://github.com/Mailpro31/nova-releases/releases/latest/download/Nova-Setup.exe";
const TTL_MIN = 15;          // validité du code
const MAX_SENDS_H = 3;       // envois max par adresse et par heure
const MAX_SENDS_IP_H = 12;   // envois max par empreinte réseau et par heure
const MAX_ATTEMPTS = 5;      // essais de code max par adresse (fenêtre active)
const IP_SALT = "nova-dl-v1"; // sel de hachage d'empreinte (anti-abus, pseudonyme)

// Restreint au site Nova (les apps desktop appellent en direct, sans CORS).
const ALLOWED_ORIGIN = "https://www.novaspeak.app";
const CORS = {
  "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};
const json = (code: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status: code,
    headers: { "Content-Type": "application/json; charset=utf-8", ...CORS },
  });

// Ne mémorise QUE le succès : en dormance (secrets absents) ou après une lecture
// en échec, on relit — sinon un isolat resterait bloqué en mode ouvert.
let mailCfg: { key: string; from: string } | null = null;
async function mailConfig() {
  if (mailCfg) return mailCfg;
  const { data, error } = await supa.from("server_secrets").select("name,value")
    .in("name", ["resend_api_key", "email_from"]);
  if (error) return null;
  const m = Object.fromEntries((data || []).map((r) => [r.name, r.value]));
  if (m.resend_api_key && m.email_from) {
    mailCfg = { key: m.resend_api_key, from: m.email_from };
  }
  return mailCfg;
}

async function sha256hex(s: string): Promise<string> {
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// empreinte réseau pseudonyme : PREMIÈRE IP de x-forwarded-for. La dernière
// (ajoutée par la passerelle) variait à chaque requête sur l'infra Supabase —
// les plafonds par IP ne se déclenchaient jamais (pentest 2026-08-11). La
// première est client-fournie (falsifiable) : utile contre les bots naïfs.
async function ipHash(req: Request): Promise<string> {
  const xff = req.headers.get("x-forwarded-for") || "";
  const ip = xff.split(",")[0].trim();
  if (!ip) return "";
  return (await sha256hex(IP_SALT + ":" + ip)).slice(0, 16);
}

async function addToWaitlist(email: string, lang: string, iph: string) {
  await supa.from("waitlist").upsert(
    { email, lang, source: "download", iph },
    { onConflict: "email", ignoreDuplicates: true });
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

async function sendCode(cfg: { key: string; from: string }, to: string,
                        code: string, lang: string): Promise<boolean> {
  try {
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

const EMAIL_RE = /^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$/;

async function requestCode(b: Record<string, unknown>, iph: string): Promise<Response> {
  if (b.website) return json(200, { ok: true, sent: true });   // pot de miel
  const email = String(b.email || "").trim().toLowerCase();
  const lang = b.lang === "en" ? "en" : "fr";
  if (email.length > 254 || !EMAIL_RE.test(email)) {
    return json(400, { ok: false, error: "invalid_email" });
  }
  // dormant (e-mail non configuré) : aucune insertion de code mort — on ouvre
  const cfg = await mailConfig();
  if (!cfg) {
    await addToWaitlist(email, lang, iph);
    return json(200, { ok: true, open: true, url: DL_URL });
  }
  // limites de débit : par adresse ET par empreinte réseau (1 h glissante)
  const since = new Date(Date.now() - 3600_000).toISOString();
  const [byEmail, byIp] = await Promise.all([
    supa.from("download_codes").select("id", { count: "exact", head: true })
      .eq("email", email).gt("created_at", since),
    iph
      ? supa.from("download_codes").select("id", { count: "exact", head: true })
          .eq("iph", iph).gt("created_at", since)
      : Promise.resolve({ count: 0 }),
  ]);
  if ((byEmail.count || 0) >= MAX_SENDS_H || (byIp.count || 0) >= MAX_SENDS_IP_H) {
    return json(429, { ok: false, error: "too_many" });
  }
  const code = String(100000 + (crypto.getRandomValues(new Uint32Array(1))[0] % 900000));
  const { data: row, error: insErr } = await supa.from("download_codes").insert({
    email,
    code_hash: await sha256hex(`${email}:${code}`),
    expires_at: new Date(Date.now() + TTL_MIN * 60_000).toISOString(),
    iph,
  }).select("id").maybeSingle();
  // insert impossible → ne pas remettre de code mort : on ouvre
  if (insErr || !row) {
    console.error("download insert", insErr);
    await addToWaitlist(email, lang, iph);
    return json(200, { ok: true, open: true, url: DL_URL });
  }
  const sent = await sendCode(cfg, email, code, lang);
  if (!sent) {
    // l'e-mail n'est pas parti : la ligne ne servira jamais → on la retire pour
    // ne pas gonfler le compteur de débit, et on ouvre
    await supa.from("download_codes").delete().eq("id", row.id);
    await addToWaitlist(email, lang, iph);
    return json(200, { ok: true, open: true, url: DL_URL });
  }
  return json(200, { ok: true, sent: true });
}

async function verifyCode(b: Record<string, unknown>, iph: string): Promise<Response> {
  const email = String(b.email || "").trim().toLowerCase();
  const code = String(b.code || "").trim();
  if (email.length > 254 || !EMAIL_RE.test(email) || !/^\d{6}$/.test(code)) {
    return json(400, { ok: false, error: "bad_code" });
  }
  // tous les codes encore valides et non consommés de cette adresse (un renvoi
  // n'invalide plus les précédents — livraison d'e-mails dans le désordre OK)
  const nowISO = new Date().toISOString();
  const { data: rows } = await supa.from("download_codes")
    .select("id,code_hash,attempts").eq("email", email).is("consumed_at", null)
    .gt("expires_at", nowISO).order("created_at", { ascending: false });
  const active = rows || [];
  const spent = active.reduce((n, r) => n + (r.attempts || 0), 0);
  if (spent >= MAX_ATTEMPTS) return json(429, { ok: false, error: "locked" });
  const hash = await sha256hex(`${email}:${code}`);
  const hit = active.find((r) => r.code_hash === hash);
  if (!hit) {
    if (active[0]) {   // un mauvais essai coûte une tentative (sur la + récente)
      await supa.from("download_codes")
        .update({ attempts: (active[0].attempts || 0) + 1 }).eq("id", active[0].id);
    }
    return json(400, { ok: false, error: "bad_code" });
  }
  await supa.from("download_codes").update(
    { consumed_at: nowISO }).eq("id", hit.id);
  const lang = b.lang === "en" ? "en" : "fr";
  await addToWaitlist(email, lang, iph);
  return json(200, { ok: true, url: DL_URL });
}

Deno.serve(async (req: Request) => {
  try {
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    if (req.method !== "POST") return json(405, { ok: false });
    let b: Record<string, unknown>;
    try { b = await req.json(); } catch { return json(400, { ok: false }); }
    if (!b || typeof b !== "object") return json(400, { ok: false });
    const iph = await ipHash(req);
    const path = new URL(req.url).pathname;
    if (path.endsWith("/code")) return await requestCode(b, iph);
    if (path.endsWith("/verify")) return await verifyCode(b, iph);
    return json(404, { ok: false });
  } catch (e) {
    console.error("download error", e);
    return json(500, { ok: false });
  }
});
