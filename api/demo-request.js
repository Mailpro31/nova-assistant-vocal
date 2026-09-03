// Nova — réception des demandes de démonstration (Campus / Business).
//
// Same-origin par construction : la CSP du site impose `form-action 'self'` et
// une liste `connect-src` fermée, donc le formulaire ne peut pas poster vers un
// tiers. Cette fonction est la seule cible autorisée ; elle relaie ensuite la
// demande par e-mail côté serveur, où la CSP du navigateur ne s'applique plus.
//
// Variables d'environnement (Vercel, jamais dans le dépôt) :
//   RESEND_API_KEY  clé du fournisseur d'envoi transactionnel
//   DEMO_INBOX      boîte de réception des demandes
//   DEMO_FROM       expéditeur vérifié sur le domaine (ex. "Nova <no-reply@…>")
// Absentes : la fonction répond 503 et la page affiche le repli de contact.

const FIELDS = {
  organisation: 160,
  kind: 20,
  seats: 40,
  idp: 60,
  timeline: 40,
  contact_name: 120,
  contact_email: 254,
  message: 2000,
};
const KINDS = new Set(['education', 'company']);
const SEATS = new Set(['1-50', '51-250', '251-1000', '1000+']);
const TIMELINES = new Set(['now', 'quarter', 'year', 'exploring']);
const IDPS = new Set(['entra', 'google', 'ldap', 'other', 'none']);
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i;

const esc = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// Chemin interne uniquement : jamais d'origine externe, jamais de « // ».
function safeNext(v, fallback) {
  const s = String(v || '');
  return /^\/[A-Za-z0-9._~\-/]*$/.test(s) && !s.startsWith('//') ? s : fallback;
}

async function readBody(req) {
  if (req.body && typeof req.body === 'object') return { data: req.body, form: false };
  const raw = await new Promise((resolve, reject) => {
    let buf = '';
    req.on('data', (c) => {
      buf += c;
      if (buf.length > 64_000) reject(new Error('too_large'));
    });
    req.on('end', () => resolve(buf));
    req.on('error', reject);
  });
  const ct = String(req.headers['content-type'] || '');
  if (ct.includes('application/json')) return { data: JSON.parse(raw || '{}'), form: false };
  return { data: Object.fromEntries(new URLSearchParams(raw)), form: true };
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return res.status(405).json({ ok: false, error: 'method_not_allowed' });
  }

  let data;
  let isForm;
  try {
    const parsed = await readBody(req);
    data = parsed.data || {};
    isForm = parsed.form;
  } catch {
    return res.status(400).json({ ok: false, error: 'bad_request' });
  }

  const lang = data.lang === 'fr' ? 'fr' : 'en';
  const back = safeNext(data.next, lang === 'fr' ? '/demonstration.html' : '/demo.html');
  // Le formulaire natif attend une redirection, la version JS attend du JSON.
  const wantsHtml = isForm && !String(req.headers.accept || '').includes('application/json');
  const done = (code, payload, hash) =>
    wantsHtml
      ? res.redirect(303, `${back}#${hash}`)
      : res.status(code).json(payload);

  // Pot de miel : on répond comme si tout allait bien, sans rien envoyer.
  if (data.website) return done(200, { ok: true }, 'envoye');

  const v = {};
  for (const [name, max] of Object.entries(FIELDS)) {
    const s = String(data[name] ?? '').trim();
    if (s.length > max) return done(400, { ok: false, error: 'too_long' }, 'erreur');
    v[name] = s;
  }

  const invalid =
    !v.organisation ||
    !v.contact_name ||
    !EMAIL_RE.test(v.contact_email) ||
    !KINDS.has(v.kind) ||
    !SEATS.has(v.seats) ||
    !TIMELINES.has(v.timeline) ||
    !IDPS.has(v.idp);
  if (invalid) return done(400, { ok: false, error: 'invalid' }, 'erreur');

  const key = process.env.RESEND_API_KEY;
  const inbox = process.env.DEMO_INBOX;
  const from = process.env.DEMO_FROM;
  if (!key || !inbox || !from) {
    console.error('demo-request: configuration d’envoi incomplète');
    return done(503, { ok: false, error: 'unavailable' }, 'erreur');
  }

  const rows = [
    ['Organisation', v.organisation],
    ['Nature', v.kind === 'education' ? 'Établissement' : 'Entreprise'],
    ['Postes', v.seats],
    ['Fournisseur d’identité', v.idp],
    ['Échéance', v.timeline],
    ['Contact', `${v.contact_name} <${v.contact_email}>`],
    ['Langue de la page', lang],
    ['Message', v.message || '—'],
  ];

  try {
    const r = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        from,
        to: [inbox],
        reply_to: v.contact_email,
        subject: `Demande de démonstration — ${v.organisation}`,
        html: rows.map(([k, val]) => `<p><strong>${esc(k)}</strong> : ${esc(val)}</p>`).join(''),
        text: rows.map(([k, val]) => `${k} : ${val}`).join('\n'),
      }),
    });
    if (!r.ok) {
      console.error('demo-request: envoi refusé', r.status);
      return done(502, { ok: false, error: 'send_failed' }, 'erreur');
    }
  } catch (e) {
    console.error('demo-request: envoi impossible', e);
    return done(502, { ok: false, error: 'send_failed' }, 'erreur');
  }

  return done(200, { ok: true }, 'envoye');
}
