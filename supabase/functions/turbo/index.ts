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
const GRACE_MS = 7 * 24 * 3600 * 1000; // aligné sur la fonction « license »

// Restreint au site Nova (les apps desktop appellent en direct, sans CORS).
const ALLOWED_ORIGIN = "https://www.novaspeak.app";
const CORS = {
  "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
};

const json = (code: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status: code,
    headers: { "Content-Type": "application/json; charset=utf-8", ...CORS },
  });

const PUB_BYTES = Uint8Array.from(atob(PUBLIC_KEY_B64), (c) => c.charCodeAt(0));

async function verifyToken(
  tok: string,
): Promise<Record<string, unknown> | null> {
  const m = /^NOVA1\.([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)$/.exec(tok || "");
  if (!m) return null;
  const un64 = (s: string) =>
    Uint8Array.from(
      atob(
        s.replace(/-/g, "+").replace(/_/g, "/") +
          "=".repeat((4 - (s.length % 4)) % 4),
      ),
      (c) => c.charCodeAt(0),
    );
  // décodage + vérif + parse sous une seule garde : un segment base64 ou un
  // JSON invalide renvoie null (→ 401), jamais une exception non gérée (→ 500)
  try {
    const payload = un64(m[1]),
      sig = un64(m[2]);
    if (!(await ed.verifyAsync(sig, payload, PUB_BYTES))) return null;
    return JSON.parse(new TextDecoder().decode(payload));
  } catch {
    return null;
  }
}

// Compatibilité avec les NOVA1 signés émis avant l'ajout du champ machine `m`.
// Le hash du jeton fournit une clé de quota stable et pseudonyme ; il ne
// contourne ni la signature, ni l'expiration, ni le palier Ultra.
async function legacyMachineId(tok: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(tok),
  );
  const hex = Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  return `legacy-${hex}`;
}

let groqKey = "";
async function serverGroqKey(): Promise<string> {
  if (groqKey) return groqKey;
  const { data } = await supa
    .from("server_secrets")
    .select("value")
    .eq("name", "groq_api_key")
    .maybeSingle();
  groqKey = data?.value || "";
  return groqKey;
}

// Révocation en TEMPS RÉEL. Le jeton porte x = fin de période + 7 j de grâce :
// il resterait donc valide ~1 mois APRÈS un remboursement / une résiliation
// (stripe-webhook passe la licence en « canceled »), pendant lequel chaque
// requête relaierait vers Groq à NOS frais. On consulte donc l'état VIVANT de
// la/les licence(s) liée(s) à cette machine. FAIL-OPEN strict : toute
// incertitude (lecture en échec, aucune ligne) laisse passer — on n'enferme
// JAMAIS un client légitime ; on ne refuse QUE si TOUTES les licences de la
// machine sont résiliées ou expirées au-delà de la grâce.
async function licenseRevoked(machine: string): Promise<boolean> {
  try {
    const { data: acts } = await supa
      .from("activations")
      .select("license_id")
      .eq("machine_hash", machine);
    if (!acts || !acts.length) return false;
    const ids = acts.map((a) => a.license_id);
    const { data: lics } = await supa
      .from("licenses")
      .select("status,current_period_end")
      .in("id", ids);
    if (!lics || !lics.length) return false;
    const now = Date.now();
    const anyValid = lics.some((l) => {
      if (l.status === "canceled") return false;
      const end = l.current_period_end
        ? new Date(l.current_period_end).getTime()
        : 0;
      if (end && now > end + GRACE_MS) return false;
      return true; // active, ou past_due encore dans la grâce
    });
    return !anyValid;
  } catch {
    return false; // panne de lecture → on laisse passer (fail-open)
  }
}

Deno.serve(async (req: Request) => {
  try {
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    if (req.method !== "POST")
      return json(404, { ok: false, error: "Introuvable." });

    // — authentification : jeton NOVA1 signé, palier Ultra, non expiré —
    const tok = (req.headers.get("Authorization") || "").replace(
      /^Bearer\s+/i,
      "",
    );
    const p = await verifyToken(tok);
    if (!p || p.t !== "ultra")
      return json(401, { ok: false, error: "Licence Ultra requise." });
    // un jeton SANS expiration (x absent/0) est invalide, pas éternel
    if (!p.x || Date.now() / 1000 > Number(p.x)) {
      return json(401, { ok: false, error: "Licence expirée." });
    }
    const boundMachine = String(p.m || "");
    const machine = boundMachine || (await legacyMachineId(tok));
    if (boundMachine && (await licenseRevoked(boundMachine))) {
      return json(403, { ok: false, error: "Abonnement résilié." });
    }

    // — audio (WAV 16 kHz mono 16 bits produit par l'app) —
    const wav = new Uint8Array(await req.arrayBuffer());
    if (wav.length < 100 || wav.length > MAX_BYTES) {
      return json(400, { ok: false, error: "Audio invalide." });
    }
    const seconds = Math.max(1, Math.round((wav.length - 44) / 32000));

    // — fair-use quotidien (silencieux : l'app retombe en local sur 429) —
    // Consommation ATOMIQUE plafonnée AVANT l'appel fournisseur : ferme la
    // course où N requêtes concurrentes lisaient toutes le même compteur.
    // Repli sur l'ancien schéma (contrôle puis incrément post-succès) tant que
    // la migration 20260804 n'est pas appliquée.
    const today = new Date().toISOString().slice(0, 10);
    let consumed = false;
    {
      const { data, error } = await supa.rpc("turbo_consume_capped", {
        p_machine: machine,
        p_seconds: seconds,
        p_cap: DAILY_CAP_S,
      });
      if (error) {
        // RPC absente (migration en retard) → repli legacy ; vraie erreur DB →
        // fail-open (on n'enferme jamais un client légitime), comme avant.
        const { data: u } = await supa
          .from("turbo_usage")
          .select("seconds")
          .eq("machine_hash", machine)
          .eq("day", today)
          .maybeSingle();
        if ((u?.seconds || 0) + seconds > DAILY_CAP_S) {
          return json(429, { ok: false, error: "quota" });
        }
      } else if (data !== true) {
        return json(429, { ok: false, error: "quota" });
      } else {
        consumed = true;
      }
    }

    // — transcription via la clé serveur —
    const key = await serverGroqKey();
    if (!key) return json(503, { ok: false, error: "Turbo indisponible." });
    const url = new URL(req.url);
    const form = new FormData();
    form.append("file", new Blob([wav], { type: "audio/wav" }), "audio.wav");
    // allowlist : le paramètre model n'est JAMAIS relayé tel quel — seuls les
    // modèles audio prévus (sinon, un client Ultra choisit un modèle plus coûteux)
    const ALLOWED_MODELS = [
      "whisper-large-v3-turbo",
      "whisper-large-v3",
      "distil-whisper-large-v3-en",
    ];
    const reqModel = url.searchParams.get("model") || "";
    form.append(
      "model",
      ALLOWED_MODELS.includes(reqModel) ? reqModel : ALLOWED_MODELS[0],
    );
    const lang = (url.searchParams.get("language") || "").slice(0, 8);
    if (lang) form.append("language", lang);
    const prompt = (url.searchParams.get("prompt") || "").slice(0, 200);
    if (prompt) form.append("prompt", prompt);
    const r = await fetch(
      "https://api.groq.com/openai/v1/audio/transcriptions",
      {
        method: "POST",
        headers: { Authorization: `Bearer ${key}` },
        body: form,
      },
    );
    if (!r.ok) {
      // remboursement : un échec fournisseur ne consomme pas le quota
      if (consumed) {
        await supa.rpc("turbo_consume", {
          p_machine: machine,
          p_seconds: -seconds,
        });
      }
      return json(502, {
        ok: false,
        error: "Turbo momentanément indisponible.",
      });
    }
    const text = ((await r.json()).text || "").trim();

    // schéma legacy (RPC plafonnée absente) : consommation après succès
    if (!consumed) {
      await supa.rpc("turbo_consume", {
        p_machine: machine,
        p_seconds: seconds,
      });
    }
    return json(200, { ok: true, text });
  } catch (e) {
    console.error("turbo error", e);
    return json(500, { ok: false, error: "Erreur serveur." });
  }
});
