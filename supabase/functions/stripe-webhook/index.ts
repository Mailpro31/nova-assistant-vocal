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
  await supa.from("licenses").insert({
    key: newKey(),
    tier,
    email: s.customer_details?.email || "",
    stripe_customer_id: String(s.customer || ""),
    stripe_subscription_id: String(s.subscription || ""),
    checkout_session_id: s.id,
    status: "active",
    current_period_end: new Date(Date.now() + PROVISIONAL_MS).toISOString(),
    seats: 2,
  });
}

async function onInvoicePaid(inv: Record<string, any>) {
  const subId = String(inv.subscription || "");
  if (!subId) return;
  let end = 0;                       // fin de période = max des lignes facturées
  for (const line of inv.lines?.data || []) {
    if (line.period?.end && line.period.end > end) end = line.period.end;
  }
  if (!end) return;
  await supa.from("licenses")
    .update({ current_period_end: new Date(end * 1000).toISOString(), status: "active" })
    .eq("stripe_subscription_id", subId);
}

async function onSubscriptionEvent(sub: Record<string, any>, deleted: boolean) {
  const status = deleted ? "canceled"
    : (sub.status === "past_due" || sub.status === "unpaid") ? "past_due"
    : sub.status === "canceled" ? "canceled" : "active";
  await supa.from("licenses").update({ status })
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
    }
    return new Response(JSON.stringify({ received: true }), {
      headers: { "Content-Type": "application/json" },
    });
  } catch (e) {
    console.error("webhook error", e);
    return new Response("erreur serveur", { status: 500 });
  }
});
