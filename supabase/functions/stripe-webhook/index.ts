// Nova — webhook Stripe : paiement → clé de licence ; renouvellement →
// prolongation ; résiliation → blocage. Auth : signature Stripe (HMAC-SHA256,
// secret whsec_ stocké dans server_secrets) — pas de JWT.
import { createClient } from "jsr:@supabase/supabase-js@2";

const supa = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

let whsec: string | null = null;
async function webhookSecret(): Promise<string> {
  if (whsec) return whsec;
  const { data } = await supa.from("server_secrets").select("value")
    .eq("name", "stripe_webhook_secret").maybeSingle();
  whsec = data?.value || "";
  return whsec;
}

async function verifySignature(body: string, header: string | null): Promise<boolean> {
  const secret = await webhookSecret();
  if (!secret || !header) return false;
  const parts = Object.fromEntries(
    header.split(",").map((p) => p.split("=", 2) as [string, string]));
  const t = parts["t"], v1 = parts["v1"];
  if (!t || !v1) return false;
  if (Math.abs(Date.now() / 1000 - Number(t)) > 600) return false; // anti-rejeu
  const key = await crypto.subtle.importKey("raw",
    new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" },
    false, ["sign"]);
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", key,
    new TextEncoder().encode(`${t}.${body}`)));
  const hex = [...mac].map((b) => b.toString(16).padStart(2, "0")).join("");
  if (hex.length !== v1.length) return false;
  let diff = 0;                                  // comparaison temps constant
  for (let i = 0; i < hex.length; i++) diff |= hex.charCodeAt(i) ^ v1.charCodeAt(i);
  return diff === 0;
}

// Clé d'achat lisible, sans caractères ambigus (0/O, 1/I/L exclus)
function newKey(): string {
  const A = "ABCDEFGHJKMNPQRSTVWXYZ23456789";
  const r = crypto.getRandomValues(new Uint8Array(15));
  const s = [...r].map((b) => A[b % A.length]).join("");
  return `NOVA-${s.slice(0, 5)}-${s.slice(5, 10)}-${s.slice(10, 15)}`;
}

// ----------------------------------------------- e-mail de livraison de clé --
// DORMANT tant que `resend_api_key` + `email_from` sont absents de
// server_secrets (même principe que licensing.PUBLIC_KEY_B64) : aucun envoi,
// aucun échec — merci.html reste alors le seul canal de remise de la clé.
const TIER_LABEL: Record<string, string> = {
  pro: "Pro", ultra: "Ultra", business: "Business",
};
const SITE = "https://novaspeak.app";
// installeur signé, publié dans le dépôt public des téléchargements (nom d'asset stable)
const DL = "https://github.com/Mailpro31/nova-releases/releases/latest/download/Nova-Setup.exe";
// capture réelle de l'app (bulle + menu des Styles), servie par le site lui-même
const SHOT = "https://novaspeak.app/shots/email-styles.png";

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

function keyEmailHtml(key: string, tierLabel: string): string {
  const step = (n: string, html: string) =>
    `<tr><td style="vertical-align:top;padding:0 12px 14px 0">
       <div style="width:22px;height:22px;border-radius:11px;background:#0A84FF;color:#ffffff;
         font:600 12px/22px -apple-system,'Segoe UI',sans-serif;text-align:center">${n}</div></td>
     <td style="padding:0 0 14px;font:400 13.5px/1.5 -apple-system,'Segoe UI',sans-serif;color:#3A3A3E">${html}</td></tr>`;
  return `<!doctype html><html lang="fr"><body style="margin:0;padding:0;background:#F5F5F7">
<div style="display:none;max-height:0;overflow:hidden">Votre clé Nova ${tierLabel} — activez-la en une minute.</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F5F5F7;padding:36px 16px">
<tr><td align="center">
<table role="presentation" width="480" cellpadding="0" cellspacing="0"
  style="max-width:480px;width:100%;background:#ffffff;border:1px solid #E6E6EA;border-radius:16px">
<tr><td style="padding:36px 40px 32px">

  <div style="font:700 20px/1 -apple-system,'SF Pro Display','Segoe UI',sans-serif;
    letter-spacing:-.3px;color:#1D1D1F;padding-bottom:4px">Nova</div>
  <div style="font:400 12px/1.4 -apple-system,'Segoe UI',sans-serif;color:#98989F;
    padding-bottom:22px">La dictée qui écrit pour vous.</div>

  <div style="font:700 19px/1.3 -apple-system,'SF Pro Display','Segoe UI',sans-serif;
    letter-spacing:-.3px;color:#1D1D1F;padding-bottom:8px">
    Bienvenue dans Nova&nbsp;${tierLabel}.</div>
  <div style="font:400 13.5px/1.55 -apple-system,'Segoe UI',sans-serif;color:#5A5A5E;
    padding-bottom:20px">Voici votre clé de licence. Conservez cet e-mail&nbsp;:
    la clé active Nova sur deux ordinateurs, entièrement hors ligne.</div>

  <div style="background:#1A1A1D;border-radius:10px;padding:16px 18px;text-align:center;
    font:600 16px/1.4 ui-monospace,Menlo,Consolas,monospace;letter-spacing:1.5px;
    color:#ffffff;margin-bottom:26px">${key}</div>

  <table role="presentation" cellpadding="0" cellspacing="0" style="width:100%">
    ${step("1", `<a href="${DL}" style="color:#0A84FF;text-decoration:none;font-weight:600">T&eacute;l&eacute;chargez Nova pour Windows</a> et lancez l&rsquo;installation.`)}
    ${step("2", `Ouvrez <b>R&eacute;glages&nbsp;&rarr;&nbsp;Abonnement</b>, collez votre cl&eacute;, puis <b>Activer</b>.`)}
    ${step("3", `Maintenez <b>F9</b> et parlez &mdash; Nova &eacute;crit pour vous, dans le bon Style.`)}
  </table>

  <div style="padding:6px 0 24px">
    <img src="${SHOT}" width="320" alt="Le menu des Styles de Nova"
      style="width:320px;max-width:100%;border-radius:12px;border:1px solid #E6E6EA;display:block">
    <div style="font:400 11px/1.5 -apple-system,'Segoe UI',sans-serif;color:#98989F;padding-top:8px">
      Vos Styles&nbsp;: E-mail, Prompt&nbsp;IA, To-do list, Prise de notes, Messages&hellip;</div>
  </div>

  <div style="border-top:1px solid #ECECF0;padding-top:16px;
    font:400 11.5px/1.6 -apple-system,'Segoe UI',sans-serif;color:#98989F">
    Votre re&ccedil;u et vos factures vous sont envoy&eacute;s par Stripe.
    En activant votre cl&eacute;, vous demandez la fourniture imm&eacute;diate du service et
    renoncez &agrave; votre droit de r&eacute;tractation, conform&eacute;ment aux
    <a href="${SITE}/conditions.html" style="color:#0A84FF;text-decoration:none">conditions de vente</a>.
    Une question&nbsp;? <a href="mailto:mailprosasha2@gmail.com"
    style="color:#0A84FF;text-decoration:none">&Eacute;crivez-nous</a> &middot;
    <a href="${SITE}/confidentialite.html" style="color:#0A84FF;text-decoration:none">Confidentialit&eacute;</a>
  </div>

</td></tr></table>
</td></tr></table></body></html>`;
}

async function sendKeyEmail(to: string, key: string, tier: string) {
  try {
    if (!to) return;
    const cfg = await mailConfig();
    if (!cfg) return;                          // dormant : pas encore configuré
    const label = TIER_LABEL[tier] || tier;
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { "Authorization": `Bearer ${cfg.key}`,
                 "Content-Type": "application/json" },
      body: JSON.stringify({
        from: cfg.from,
        to: [to],
        subject: `Votre clé Nova ${label}`,
        html: keyEmailHtml(key, label),
      }),
    });
    if (!r.ok) console.error("resend", r.status, await r.text());
  } catch (e) {
    console.error("resend error", e);          // l'e-mail n'échoue jamais le webhook
  }
}

const PROVISIONAL_MS = 35 * 24 * 3600 * 1000;  // en attendant invoice.paid

async function onCheckoutCompleted(s: Record<string, any>) {
  if (s.mode !== "subscription") return;
  const tier = (s.metadata?.tier || "").toLowerCase();
  if (!/^(pro|ultra|business)$/.test(tier)) {
    console.error("tier absent des metadata du Payment Link", s.id);
    return;
  }
  // idempotent : Stripe peut renvoyer l'événement
  const { data: existing } = await supa.from("licenses").select("id")
    .eq("checkout_session_id", s.id).maybeSingle();
  if (existing) return;
  // ANTI-FRAUDE : la licence n'est active et la clé envoyée que si le
  // paiement est confirmé MAINTENANT. Un checkout à débit différé (SEPA) ou
  // une carte qui échouera donne checkout.session.completed avec
  // payment_status != "paid" → licence "pending", sans e-mail ; invoice.paid
  // l'activera si (et seulement si) l'encaissement aboutit.
  const paid = s.payment_status === "paid";
  const key = newKey();
  const email = s.customer_details?.email || "";
  await supa.from("licenses").insert({
    key,
    tier,
    email,
    stripe_customer_id: String(s.customer || ""),
    stripe_subscription_id: String(s.subscription || ""),
    checkout_session_id: s.id,
    status: paid ? "active" : "pending",
    current_period_end: new Date(Date.now() + PROVISIONAL_MS).toISOString(),
    seats: 2,
  });
  if (paid) await sendKeyEmail(email, key, tier);   // best-effort, jamais bloquant
}

// remboursement INTÉGRAL → licence désactivée (politique anti-abus des CGV) ;
// un remboursement partiel (geste commercial) ne touche à rien.
async function onChargeRefunded(ch: Record<string, any>) {
  if (!ch.refunded) return;
  const cust = String(ch.customer || "");
  if (!cust) return;
  await supa.from("licenses").update({ status: "canceled" })
    .eq("stripe_customer_id", cust);
}

async function onInvoicePaid(inv: Record<string, any>) {
  const subId = String(inv.subscription || "");
  if (!subId) return;
  let end = 0;                       // fin de période = max des lignes facturées
  for (const line of inv.lines?.data || []) {
    if (line.period?.end && line.period.end > end) end = line.period.end;
  }
  if (!end) return;
  // Paiement différé confirmé : les licences "pending" passent "active" et
  // reçoivent ENFIN leur clé (jamais envoyée au checkout, cf. onCheckoutCompleted).
  const { data: pending } = await supa.from("licenses")
    .select("key, email, tier")
    .eq("stripe_subscription_id", subId)
    .eq("status", "pending");
  await supa.from("licenses")
    .update({ current_period_end: new Date(end * 1000).toISOString(), status: "active" })
    .eq("stripe_subscription_id", subId);
  for (const lic of pending || []) {
    await sendKeyEmail(lic.email, lic.key, lic.tier);
  }
}

// Palier d'un abonnement d'après son prix (montant + intervalle). Les price
// IDs Stripe ne sont pas dans le code : on mappe sur les montants (tarifs de
// lancement 4,99/49 et 14,99/149, ET anciens tarifs 9,99/99 et 19,99/199
// pour les clients historiques). Inconnu → null (le tier stocké est
// conservé). Indispensable pour l'upgrade Pro→Ultra du portail client : sans
// ça, payer la différence ne débloquait rien.
function tierForSubscription(sub: Record<string, any>): string | null {
  const price = sub?.items?.data?.[0]?.price;
  const amount = Number(price?.unit_amount || 0);
  const interval = String(price?.recurring?.interval || "");
  if (!amount || !interval) return null;
  const yearly = interval === "year";
  if ((!yearly && (amount === 499 || amount === 999)) ||
      (yearly && (amount === 4900 || amount === 9900))) return "pro";
  if ((!yearly && (amount === 1499 || amount === 1999)) ||
      (yearly && (amount === 14900 || amount === 19900))) return "ultra";
  return null;
}

async function onSubscriptionEvent(sub: Record<string, any>, deleted: boolean) {
  // Statuts Stripe : incomplete (1er paiement en cours/échoué) et paused ne
  // doivent JAMAIS donner "active" — sinon une carte qui échoue conserve une
  // licence pleinement utilisable. incomplete_expired / unpaid → résilié.
  const status = deleted ? "canceled"
    : sub.status === "incomplete" ? "pending"
    : sub.status === "past_due" ? "past_due"
    : (sub.status === "incomplete_expired" || sub.status === "unpaid"
        || sub.status === "canceled" || sub.status === "paused") ? "canceled"
    : "active";   // active | trialing
  const update: Record<string, unknown> = { status };
  // Upgrade/downgrade (portail client) : le tier suit le prix réel de
  // l'abonnement — jamais sur une résiliation (on conserve le tier pour
  // l'historique, le statut « canceled » suffit à couper les droits).
  if (!deleted) {
    const tier = tierForSubscription(sub);
    if (tier) update.tier = tier;
  }
  await supa.from("licenses").update(update)
    .eq("stripe_subscription_id", String(sub.id));
}

Deno.serve(async (req: Request) => {
  try {
    if (req.method !== "POST") return new Response("ok", { status: 200 });
    const body = await req.text();
    if (!(await verifySignature(body, req.headers.get("Stripe-Signature")))) {
      return new Response("signature invalide", { status: 400 });
    }
    const event = JSON.parse(body);
    const obj = event.data?.object || {};
    switch (event.type) {
      case "checkout.session.completed": await onCheckoutCompleted(obj); break;
      case "invoice.paid":               await onInvoicePaid(obj); break;
      case "customer.subscription.updated": await onSubscriptionEvent(obj, false); break;
      case "customer.subscription.deleted": await onSubscriptionEvent(obj, true); break;
      case "charge.refunded":               await onChargeRefunded(obj); break;
    }
    return new Response(JSON.stringify({ received: true }), {
      headers: { "Content-Type": "application/json" },
    });
  } catch (e) {
    console.error("webhook error", e);
    return new Response("erreur serveur", { status: 500 });
  }
});
