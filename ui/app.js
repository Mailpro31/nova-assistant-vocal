/* Nova — logique UI (design bleu nuit, maquettes nova-design) */
let STATE = null;
let editingAutoId = null;
let editingNoteId = null;
let autoType = "open_url";
let selProfileId = null;
let recordingKbd = null;

/* ------------------------------------------------------------- helpers -- */
function api(method, ...args) {
  if (!window.pywebview) return Promise.resolve(null);
  return window.pywebview.api[method](...args);
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove("show"), 2400);
}

function $(id) { return document.getElementById(id); }

function deepGet(obj, path) {
  return path.split(".").reduce((o, k) => (o || {})[k], obj);
}

function deepPatch(path, value) {
  const patch = {};
  let cur = patch;
  const keys = path.split(".");
  keys.forEach((k, i) => {
    if (i === keys.length - 1) cur[k] = value;
    else cur = cur[k] = {};
  });
  return api("save_config", patch).then((cfg) => {
    if (STATE) STATE.config = cfg;
    applyConfigToUI();
  });
}

function timeAgo(ts) {
  const d = Date.now() - ts;
  if (d < 60e3) return "À l'instant";
  if (d < 3600e3) return `Il y a ${Math.floor(d / 60e3)} min`;
  if (d < 86400e3) return `Il y a ${Math.floor(d / 3600e3)} h`;
  return new Date(ts).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" }) +
    ", " + new Date(ts).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

const svgIcon = (p, s = 14) =>
  `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;

const ICONS = {
  globe: svgIcon('<circle cx="12" cy="12" r="9"></circle><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"></path>'),
  app: svgIcon('<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"></rect><path d="M3.5 9h17"></path><path d="M6.5 6.8h.01M9 6.8h.01"></path>'),
  note: svgIcon('<path d="M6 3.5h9.5L19.5 7.5V20.5H6z"></path><path d="M15 3.5v4.5h4.5"></path><path d="M9 12h6M9 15.5h6"></path>'),
  keys: svgIcon('<rect x="3" y="7" width="18" height="10" rx="2"></rect><path d="M7 12h.01M11 12h.01M15 12h.01M7.5 14.5h9"></path>'),
  cmd: svgIcon('<path d="M5 7l4 5-4 5"></path><path d="M12 17h7"></path>'),
  msg: svgIcon('<path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z"></path>'),
  nav: svgIcon('<path d="m3 11 19-8-8 19-2.5-8.5Z"></path>'),
  media: svgIcon('<path d="m6 4 14 8-14 8Z"></path>'),
  phone: svgIcon('<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3 19.5 19.5 0 0 1-6-6 19.8 19.8 0 0 1-3-8.7A2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.13.96.36 1.9.7 2.8a2 2 0 0 1-.45 2.1L8.1 9.9a16 16 0 0 0 6 6l1.3-1.27a2 2 0 0 1 2.1-.45c.9.34 1.84.57 2.8.7a2 2 0 0 1 1.7 2Z"></path>'),
  alert: svgIcon('<path d="M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.7 3.86a2 2 0 0 0-3.4 0Z"></path><path d="M12 9v4"></path><path d="M12 17h.01"></path>'),
  user: svgIcon('<circle cx="12" cy="8" r="4"></circle><path d="M4 21c0-4 3.6-6 8-6s8 2 8 6"></path>'),
  car: svgIcon('<path d="M5 11 6.5 6.5A2 2 0 0 1 8.4 5h7.2a2 2 0 0 1 1.9 1.5L19 11"></path><path d="M3 11h18v6h-2a2 2 0 1 1-4 0H9a2 2 0 1 1-4 0H3Z"></path>'),
  search: svgIcon('<circle cx="11" cy="11" r="7"></circle><path d="m21 21-4-4"></path>'),
  spark: svgIcon('<rect x="6" y="6" width="12" height="12" rx="2.5"></rect><path d="M12 2.5v3.5M12 18v3.5M2.5 12H6M18 12h3.5"></path>'),
  clock: svgIcon('<circle cx="12" cy="13" r="8"></circle><path d="M12 9.5V13l2.5 2.5M9.5 2.5h5"></path>'),
  cloud: svgIcon('<path d="M17.5 18.5H7a4.5 4.5 0 1 1 .8-8.93A6 6 0 0 1 19.4 12a3.5 3.5 0 0 1-1.9 6.5Z"></path>'),
  cal: svgIcon('<rect x="3.5" y="5" width="17" height="15.5" rx="2.5"></rect><path d="M3.5 10h17M8 2.5V7M16 2.5V7"></path>'),
  link: svgIcon('<path d="M10 13.5a4 4 0 0 0 6 .5l3-3a4 4 0 1 0-5.7-5.7l-1.6 1.6"></path><path d="M14 10.5a4 4 0 0 0-6-.5l-3 3a4 4 0 1 0 5.7 5.7l1.6-1.6"></path>'),
  lock: svgIcon('<rect x="4.5" y="10" width="15" height="10.5" rx="2"></rect><path d="M8 10V7a4 4 0 0 1 8 0v3"></path>'),
};

const MODE_ICONS = {
  automatisation: "app", note: "note", "mémo": "note", dictée: "note",
  navigation: "nav", media: "media", "média": "media", message: "msg",
  call: "phone", appel: "phone", urgence: "alert", "véhicule": "car",
  recherche: "search", ia: "spark", system: "user", profil: "user",
  timer: "clock", time: "clock", weather: "cloud", music: "media",
  calendar: "cal", timer_cancel: "clock",
};

const MODE_LABELS = {
  automatisation: "Automatisation", note: "Note vocale", navigation: "Navigation",
  media: "Média", message: "Message", call: "Appel", urgence: "Urgence",
  recherche: "Recherche web", ia: "IA", system: "Profil", inconnu: "Non reconnu",
  "dictée": "Dictée", "véhicule": "Véhicule",
  timer: "Minuteur", timer_cancel: "Minuteur", time: "Heure",
  weather: "Météo", music: "Musique", calendar: "Agenda",
};

/* --------------------------------------------------------------- nav ----- */
document.querySelectorAll(".nav-item").forEach((b) => {
  b.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".page").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    $("page-" + b.dataset.page).classList.add("active");
    if (b.dataset.page === "ia") loadIntelligence();
    if (b.dataset.page === "aide") loadAide();
    if (b.dataset.page === "maison") loadMaison();
  });
});

/* ---------------------------------------------------------- Maison (2.13) */
/* picker d'entités Home Assistant : la datalist du champ ID se remplit
   avec les entités RÉELLES de la box, filtrées par le type choisi */
function fillHaDatalist() {
  const map = { light: "light", switch: "switch", sensor: "sensor",
                scene: "scene", climate: "climate", lock: "lock",
                alarm: "alarm_control_panel", vacuum: "vacuum",
                battery: "sensor" };
  const domain = map[$("he-type").value] || "";
  api("ha_entities_available", domain).then((ents) => {
    const dl = $("ha-entity-options");
    if (!dl || !ents) return;
    dl.innerHTML = ents.map((s) =>
      `<option value="${esc(s.id)}">${esc(s.name)} (${esc(s.state)})</option>`).join("");
  }).catch(() => {});
}

$("he-type").addEventListener("change", fillHaDatalist);

function loadMaison() {
  fillHaDatalist();
  if (!STATE) return;
  const cfg = STATE.config;
  $("ha-url").value = cfg.ha_url || "";
  $("mu-spotify").value = (cfg.music || {}).spotify_uri || "";
  $("mu-youtube").value = (cfg.music || {}).youtube_url || "";
  $("ha-dot").className = "acc-dot" + (cfg.ha_url ? " on" : "");
  renderHaEntities(cfg.ha_entities || {});
  renderRoutines(cfg.routines || {});
}

const HA_TYPE_LABEL = { light: "Lumière", switch: "Prise", sensor: "Capteur" };
function renderHaEntities(ents) {
  const keys = Object.keys(ents);
  $("he-list").innerHTML = keys.length ? keys.map((k) => `
    <div class="ca-row">
      <span class="ca-name">${esc(k)}</span>
      <span class="badge">${HA_TYPE_LABEL[ents[k].type] || ents[k].type}</span>
      <span class="ca-target">${esc(ents[k].id)}</span>
      <button class="icon-btn red" title="Supprimer" data-name="${esc(k)}" onclick="haDelete(this.dataset.name)">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>
      </button>
    </div>`).join("") : `<div class="ca-row" style="color:var(--dim);">Aucun appareil. Ajoutez vos lumières et prises Home Assistant.</div>`;
}

function renderRoutines(routines) {
  const keys = Object.keys(routines);
  $("ro-list").innerHTML = keys.length ? keys.map((k) => `
    <div class="ca-row">
      <span class="ca-name">« mode ${esc(k)} »</span>
      <span class="ca-target">${esc((routines[k] || []).join(" · "))}</span>
      <button class="icon-btn red" title="Supprimer" data-name="${esc(k)}" onclick="roDelete(this.dataset.name)">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>
      </button>
    </div>`).join("") : `<div class="ca-row" style="color:var(--dim);">Aucune routine. Créez « boulot » pour l'activer par « au boulot ».</div>`;
}

$("btn-ha-save").addEventListener("click", () => {
  const ents = { ...(STATE?.config?.ha_entities || {}) };
  api("set_ha", $("ha-url").value.trim(), ents);
  const tok = $("ha-token").value.trim();
  if (tok) api("set_secret", "ha_token", tok);
  toast("Home Assistant enregistré"); $("ha-token").value = "";
  setTimeout(refresh, 200);
});
$("btn-ha-test").addEventListener("click", () => {
  const tok = $("ha-token").value.trim();
  const save = tok ? api("set_secret", "ha_token", tok) : Promise.resolve();
  save.then(() => api("set_ha", $("ha-url").value.trim(), STATE?.config?.ha_entities || {}))
    .then(() => api("ha_test")).then((r) => {
      $("ha-status").textContent = (r.ok ? "✓ " : "✗ ") + r.msg;
      $("ha-status").style.color = r.ok ? "#30D158" : "#FF6950";
    });
});
$("btn-he-add").addEventListener("click", () => {
  const name = $("he-name").value.trim().toLowerCase();
  const id = $("he-id").value.trim();
  if (!name || !id) { toast("Nom et identifiant requis"); return; }
  const ents = { ...(STATE?.config?.ha_entities || {}) };
  ents[name] = { type: $("he-type").value, id };
  api("set_ha", STATE?.config?.ha_url || "", ents).then(() => {
    $("he-name").value = ""; $("he-id").value = "";
    toast(`« ${name} » ajouté`); refresh();
  });
});
window.haDelete = (name) => {
  const ents = { ...(STATE?.config?.ha_entities || {}) };
  delete ents[name];
  api("set_ha", STATE?.config?.ha_url || "", ents).then(() => { toast("Supprimé"); refresh(); });
};
$("btn-ro-add").addEventListener("click", () => {
  const name = $("ro-name").value.trim().toLowerCase();
  const steps = $("ro-steps").value.split(",").map((s) => s.trim()).filter(Boolean);
  if (!name || !steps.length) { toast("Nom et au moins une cible requis"); return; }
  const r = { ...(STATE?.config?.routines || {}) };
  r[name] = steps;
  api("set_routines", r).then(() => {
    $("ro-name").value = ""; $("ro-steps").value = "";
    toast(`Routine « ${name} » prête`); refresh();
  });
});
window.roDelete = (name) => {
  const r = { ...(STATE?.config?.routines || {}) };
  delete r[name];
  api("set_routines", r).then(() => { toast("Supprimée"); refresh(); });
};
$("btn-mu-save").addEventListener("click", () => {
  api("set_music", $("mu-spotify").value.trim(), $("mu-youtube").value.trim())
    .then(() => toast("Musique attitrée enregistrée"));
});

/* page « Que dire ? » : générée depuis les capacités réelles de Nova
   (rechargée à chaque visite : les applis personnalisées évoluent) */
function loadAide() {
  api("get_capabilities").then((cap) => {
    const chip = (t) => `<span class="aide-chip">${esc(t)}</span>`;
    const bloc = (titre, sub, items) => `
      <div class="card aide-card">
        <div class="aide-title">${titre}</div>
        ${sub ? `<div class="aide-sub">${sub}</div>` : ""}
        <div class="aide-chips">${items.map(chip).join("")}</div>
      </div>`;
    let html = (cap.exemples || []).map(([titre, phrases]) =>
      bloc(esc(titre), "", phrases.map((p) => `« ${p} »`))).join("");
    html += bloc("Sites ouvrables à la voix", "« ouvre… », « va sur… »", cap.sites || []);
    html += bloc("Applications", "« ouvre… », « lance… » (personnalisables dans Réglages)", cap.apps || []);
    html += bloc("Pages de réglages Windows", "« ouvre les paramètres de… »", cap.settings || []);
    html += bloc("Raccourcis vocaux", "dits seuls, tels quels", cap.shortcuts || []);
    $("aide-content").innerHTML = html;
  });
}

/* ------------------------------------------------------------- refresh -- */
function refresh() {
  return api("get_state").then((s) => {
    if (!s) return;
    STATE = s;
    renderStatus();
    renderHistory(s.history);
    renderNotes();
    renderAutos();
    renderProfiles();
    applyConfigToUI();
    renderProvGrid();
  });
}

function renderStatus() {
  const st = STATE.status, cfg = STATE.config;
  // hero
  const listening = st.listening;
  $("mic-btn").classList.toggle("listening", listening);
  $("hero-title").textContent = listening ? "Je t'écoute…" : "Parlez à Nova";
  const hk = (cfg.hotkey || "").split("+").map((k) =>
    `<span class="kbd">${esc(k.charAt(0).toUpperCase() + k.slice(1)).replace("Space", "Espace")}</span>`).join(" + ");
  const wname = esc((cfg.wake_word || "Nova").replace(/^./, (c) => c.toUpperCase()));
  $("hero-hint").innerHTML = cfg.continuous_listening
    ? `Appuyez sur ${hk}, ou dites « ${wname}, ouvre YouTube » d'une seule traite`
    : `Appuyez sur ${hk} (mot d'éveil désactivé)`;
  // date
  $("home-date").textContent = new Date().toLocaleDateString("fr-FR",
    { weekday: "long", day: "numeric", month: "long" }).replace(/^./, (c) => c.toUpperCase());
  // cartes statut
  const w = st.whisper;
  $("st-whisper").innerHTML = w === "prêt"
    ? `<span class="dot ok"></span><b>Active</b><span class="sub">· ${esc(cfg.language)}-${esc(cfg.language.toUpperCase())} · ${esc(cfg.whisper_model)}</span>`
    : w.startsWith("erreur")
      ? `<span class="dot err"></span><b>Erreur</b><span class="sub">· ${esc(w.slice(0, 40))}</span>`
      : `<span class="dot warn"></span><b>Chargement…</b>`;
  const provNames = { anthropic: "Claude", openai: "OpenAI", gemini: "Gemini", deepseek: "DeepSeek", groq: "Groq", mistral: "Mistral", xai: "Grok", openrouter: "OpenRouter", ollama: "Ollama", off: "Aucun" };
  $("st-ia").innerHTML = st.provider === "off"
    ? `<span class="dot off"></span><b>Aucun</b><span class="sub">· page Intelligence</span>`
    : `<span class="dot ok"></span><b>${provNames[st.provider] || st.provider}</b><span class="sub">· ${cfg.provider === "auto" ? "choisi en auto" : "connecté"}</span>`;
  const wakeOn = cfg.continuous_listening;
  const wk = st.wake || {};
  const wakeLbl = cfg.wake_engine === "porcupine"
    ? (st.porcupine.state === "actif" ? `« ${st.porcupine.detail} »` : "Porcupine")
    : `« ${cfg.wake_word || "Nova"} »`;
  const wakeErr = wakeOn && (cfg.wake_engine === "porcupine"
    ? st.porcupine.state === "erreur" : wk.state === "erreur");
  const wakeErrDetail = cfg.wake_engine === "porcupine" ? st.porcupine.detail : wk.detail;
  $("st-wake").innerHTML = wakeOn
    ? (wakeErr
      ? `<span class="dot err"></span><b>Erreur</b><span class="sub">· ${esc((wakeErrDetail || "").slice(0, 34))}</span>`
      : `<span class="dot blue"></span><b>${esc(wakeLbl)}</b><span class="sub">· activé</span>`)
    : `<span class="dot off"></span><b>Désactivé</b><span class="sub">· Réglages</span>`;
  // état détaillé de la détection Whisper (Réglages > Écoute)
  const ws = $("wake-status");
  if (ws) {
    if (!wakeOn || cfg.wake_engine !== "whisper") {
      $("row-wake-status").style.display = "none";
    } else {
      $("row-wake-status").style.display = "";
      let txt = wk.state || "inactif";
      if (wk.state === "erreur") txt = "Erreur : " + (wk.detail || "");
      else if (wk.state === "actif") txt = "Actif" + (wk.heard ? ` · entendu : « ${wk.heard} »` : " · dites quelque chose pour tester");
      ws.textContent = txt;
      ws.style.color = wk.state === "erreur" ? "var(--err)" : "";
    }
  }
  // chip sidebar
  $("chip-dot").classList.toggle("on", wakeOn || listening);
  $("chip-label").textContent = st.dictation ? "Dictée en cours…"
    : (listening ? "Nova écoute…" : (wakeOn ? "Écoute active" : "Écoute inactive"));
  // bannière dictée
  $("dictee-banner").classList.toggle("show", listening);
  // statut porcupine dans réglages
  const ps = $("porcupine-status");
  if (ps) ps.textContent = st.porcupine.state === "actif"
    ? `Actif — dites « ${st.porcupine.detail} »`
    : (st.porcupine.detail || "Inactif");
  // OBD live
  renderObdLive(st.obd);
  // Graph
  renderGraphStatus(st.status_graph || st.graph);
  // minuteurs & rappels
  renderTimers(st.timers || []);
  renderReminders(st.reminders || []);
  renderStats(st.stats);
  renderAccounts(st.accounts);
  renderFacts(st.facts || []);
  renderMics(st.mics || []);
  const mm = $("sw-mic-mute");
  if (mm) mm.classList.toggle("on", !!st.mic_muted);
}

/* rappels à heure fixe (« rappelle-moi le sport à 15 h 30 ») */
function renderReminders(rems) {
  const box = $("reminders-list");
  if (!box) return;
  const card = $("timers-card");
  box.innerHTML = rems.map((r) => `
    <div class="timer-row">
      <span class="t-label">${esc(r.text)}</span>
      <span class="t-remaining">${esc(r.time)}${r.date ? "" : " · tous les jours"}</span>
      <button class="icon-btn red" title="Supprimer le rappel"
              onclick="api('delete_reminder','${r.id}').then(refresh)">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>
      </button>
    </div>`).join("");
  if (card && rems.length) card.style.display = "";
}

/* micros disponibles (Réglages > Écoute) */
let _micsSig = "";
function renderMics(mics) {
  const sel = $("cfg-mic");
  if (!sel) return;
  const sig = JSON.stringify(mics.map((m) => m.index + m.name));
  if (sig === _micsSig) return;   // pas de re-render pendant qu'on choisit
  _micsSig = sig;
  const cur = STATE?.config?.mic_device_index;
  sel.innerHTML = '<option value="">Micro par défaut Windows</option>' +
    mics.map((m) => `<option value="${m.index}" ${cur === m.index ? "selected" : ""}>${esc(m.name)}${m.default ? " (défaut)" : ""}</option>`).join("");
  if (cur !== null && cur !== undefined && cur !== "") sel.value = String(cur);
}

function renderFacts(facts) {
  const box = $("facts-list");
  if (!box) return;
  box.innerHTML = facts.length ? facts.map((f) => `
    <div class="ca-row">
      <span class="ca-target" style="flex:1;">${esc(f.fact)}</span>
      <button class="icon-btn red" title="Oublier" onclick="api('delete_fact','${f.id}').then(refresh)">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>
      </button>
    </div>`).join("")
    : `<div class="ca-row" style="color:var(--dim);">Encore rien : dites « Nova, souviens-toi que… »</div>`;
}

function renderStats(s) {
  const card = $("stats-card");
  if (!card || !s) return;
  card.style.display = s.total ? "" : "none";
  if (!s.total) return;
  const top = (s.top || []).map((t) => `${esc(t.mode)} (${t.count})`).join(" · ");
  $("stats-line").innerHTML =
    `<b>${s.total}</b> commandes au total · <b>${s.rate}%</b> réussies · ` +
    `<b>${s.today}</b> aujourd'hui${top ? " · Top : " + top : ""}`;
}

function renderAccounts(acc) {
  if (!acc || !$("acc-gg-dot")) return;
  const pend = acc.pending || {};
  $("acc-gg-dot").className = "acc-dot" + (acc.google ? " on" : "");
  $("acc-sp-dot").className = "acc-dot" + (acc.spotify ? " on" : "");
  $("acc-gg-status").textContent = acc.google ? "Connecté ✓" : (pend.google || "");
  $("acc-sp-status").textContent = acc.spotify ? "Connecté ✓" : (pend.spotify || "");
}

function fmtRemaining(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
  if (h) return `${h} h ${String(m).padStart(2, "0")} min`;
  if (m) return `${m} min ${String(ss).padStart(2, "0")} s`;
  return `${ss} s`;
}

function renderTimers(items) {
  const card = $("timers-card");
  if (!card) return;
  card.style.display = items.length ? "" : "none";
  if (!items.length) return;
  $("timers-list").innerHTML = items.map((t) => `
    <div class="timer-row">
      <span class="timer-label">${esc(t.label || "Minuteur")}</span>
      <span class="timer-remaining">${fmtRemaining(t.remaining)}</span>
      <button class="icon-btn red" title="Annuler" onclick="api('cancel_timer','${t.id}').then(refresh)">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>
      </button>
    </div>`).join("");
}

/* ---------------------------------------------------------- historique --- */
function renderHistory(items) {
  const box = $("hist-list");
  if (!items || !items.length) {
    box.innerHTML = `<div class="hist-empty">Aucune commande pour le moment — parlez à Nova !</div>`;
    return;
  }
  box.innerHTML = items.map((h) => {
    const ico = ICONS[MODE_ICONS[h.mode] || "globe"];
    const label = MODE_LABELS[h.mode] || h.mode;
    return `<div class="hist-row">
      <div class="hist-ico ${h.ok ? "" : "ko"}">${ico}</div>
      <div class="hist-body">
        <span class="hist-phrase">« ${esc(h.text)} »</span>
        <span class="hist-action">${esc(label)} · ${esc(h.result || h.final || "")}</span>
      </div>
      <span class="hist-time">${timeAgo(h.ts)}</span>
      <button class="icon-btn blue" title="Rejouer cette commande" onclick="replayCmd(this)" data-text="${esc(h.text)}">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3.5 7.5"/><path d="M3 3v4.5H7.5"/></svg>
      </button>
      ${h.ok
        ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#30D158" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5 10 17.5 19 7"/></svg>'
        : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#FF6950" stroke-width="2" stroke-linecap="round"><path d="M7 7l10 10M17 7 7 17"/></svg>'}
    </div>`;
  }).join("");
}

window.replayCmd = (btn) => {
  const t = btn.dataset.text;
  if (!t) return;
  api("run_text", t);
  toast(`Je rejoue : « ${t.slice(0, 40)} »`);
};

let histTimer = null;
$("hist-search").addEventListener("input", (e) => {
  clearTimeout(histTimer);
  histTimer = setTimeout(() => {
    api("history", e.target.value, 60).then(renderHistory);
  }, 250);
});

function clearHistory() {
  api("clear_history").then(() => api("history", "", 60).then(renderHistory));
}

/* --------------------------------------------------------------- notes --- */
function renderNotes() {
  const notes = STATE.notes || [];
  $("notes-count").textContent = notes.length + (notes.length > 1 ? " notes" : " note");
  const list = $("notes-list");
  list.innerHTML = notes.map((n) => `
    <div class="note-card ${n.id === editingNoteId ? "sel" : ""}" data-id="${n.id}">
      <div class="n-title-row">
        <span class="n-title">${esc(n.title)}</span>
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#0A84FF" stroke-width="2.2" stroke-linecap="round"><path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 10v4"/></svg>
      </div>
      <div class="n-extract">${esc(n.text.replace(/\n+/g, " ").slice(0, 120))}</div>
      <div class="n-date">${esc(n.created)}</div>
    </div>`).join("") +
    `<button class="note-new" onclick="newNote()">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
      Nouvelle note
    </button>`;
  list.querySelectorAll(".note-card").forEach((el) => {
    el.addEventListener("click", () => selectNote(el.dataset.id));
  });
  if (!editingNoteId && notes.length) selectNote(notes[0].id);
  else if (editingNoteId && !notes.some((n) => n.id === editingNoteId)) {
    editingNoteId = null;
    if (notes.length) selectNote(notes[0].id);
    else { $("ne-title").value = ""; $("ne-body").value = ""; $("ne-meta-txt").textContent = ""; }
  }
}

function selectNote(id) {
  const n = (STATE.notes || []).find((x) => x.id === id);
  if (!n) return;
  editingNoteId = id;
  $("ne-title").value = n.title;
  $("ne-body").value = n.text;
  $("ne-meta-txt").textContent = n.created;
  document.querySelectorAll(".note-card").forEach((el) =>
    el.classList.toggle("sel", el.dataset.id === id));
}

function newNote() {
  api("add_note", "", "Nouvelle note").then(() => refresh().then(() => {
    const first = (STATE.notes || [])[0];
    if (first) selectNote(first.id);
    $("ne-title").focus();
  }));
}

let noteSaveTimer = null;
function scheduleNoteSave() {
  if (!editingNoteId) return;
  clearTimeout(noteSaveTimer);
  noteSaveTimer = setTimeout(() => {
    api("update_note", editingNoteId, $("ne-body").value, $("ne-title").value)
      .then(() => api("get_state").then((s) => { STATE = s; renderNotes(); }));
  }, 600);
}
$("ne-title").addEventListener("input", scheduleNoteSave);
$("ne-body").addEventListener("input", scheduleNoteSave);
$("ne-delete").addEventListener("click", () => {
  if (!editingNoteId) return;
  api("delete_note", editingNoteId).then(() => { editingNoteId = null; refresh(); });
});

/* ------------------------------------------------------- automatisations - */
const TYPE_META = {
  open_url: { label: "Site", ico: "globe", cl: "Adresse du site", ph: "https://…", aide: "S'ouvre dans le navigateur par défaut." },
  open_app: { label: "App", ico: "app", cl: "Application", ph: "Chemin de l'exécutable ou nom (spotify, notepad…)", aide: "Ajoutez des arguments dans le champ dédié (ex. profil Chrome)." },
  keys: { label: "Raccourci", ico: "keys", cl: "Combinaison de touches", ph: "Ex. ctrl+shift+s, win+l", aide: "Nova simule la frappe des touches." },
  shell: { label: "Commande", ico: "cmd", cl: "Commande système", ph: "Ex. shutdown /s /t 3600", aide: "Exécutée dans un terminal masqué. À utiliser avec prudence." },
  webhook: { label: "Webhook", ico: "link", cl: "URL du webhook", ph: "https://hooks.zapier.com/…", aide: "Appelée en POST avec la phrase dictée (IFTTT, Zapier, Make, Home Assistant…) : des milliers d'apps connectables." },
  web_search: { label: "Recherche", ico: "search", cl: "Termes de recherche", ph: "météo Paris", aide: "Recherche Google." },
  note: { label: "Note", ico: "note", cl: "Contenu", ph: "", aide: "" },
};

/* modèles prêts à l'emploi (1 clic) */
const TEMPLATES = [
  /* Essentiels */
  { cat: "Essentiels", name: "YouTube", phrase: "ouvre youtube", phrases: ["ouvre youtube", "va sur youtube"], type: "open_url", target: "https://www.youtube.com", ico: "globe" },
  { cat: "Essentiels", name: "Gmail", phrase: "ouvre mes mails", phrases: ["ouvre mes mails", "ouvre gmail"], type: "open_url", target: "https://mail.google.com", ico: "msg" },
  { cat: "Essentiels", name: "WhatsApp Web", phrase: "ouvre whatsapp", type: "open_url", target: "https://web.whatsapp.com", ico: "msg" },
  { cat: "Essentiels", name: "Google Agenda", phrase: "ouvre mon agenda", phrases: ["ouvre mon agenda", "ouvre l'agenda"], type: "open_url", target: "https://calendar.google.com", ico: "cal" },
  { cat: "Essentiels", name: "Google Maps", phrase: "ouvre maps", type: "open_url", target: "https://maps.google.com", ico: "globe" },
  { cat: "Essentiels", name: "Google Drive", phrase: "ouvre drive", type: "open_url", target: "https://drive.google.com", ico: "app" },
  { cat: "Essentiels", name: "ChatGPT", phrase: "ouvre chatgpt", type: "open_url", target: "https://chatgpt.com", ico: "spark" },
  { cat: "Essentiels", name: "Claude", phrase: "ouvre claude", type: "open_url", target: "https://claude.ai", ico: "spark" },
  /* Musique & vidéo */
  { cat: "Musique & vidéo", name: "Spotify", phrase: "ouvre spotify", phrases: ["ouvre spotify", "lance spotify"], type: "open_url", target: "https://open.spotify.com", ico: "media" },
  { cat: "Musique & vidéo", name: "Deezer", phrase: "ouvre deezer", type: "open_url", target: "https://www.deezer.com", ico: "media" },
  { cat: "Musique & vidéo", name: "YouTube Music", phrase: "ouvre youtube music", type: "open_url", target: "https://music.youtube.com", ico: "media" },
  { cat: "Musique & vidéo", name: "Netflix", phrase: "lance netflix", phrases: ["lance netflix", "ouvre netflix"], type: "open_url", target: "https://www.netflix.com", ico: "media" },
  { cat: "Musique & vidéo", name: "Prime Video", phrase: "ouvre prime video", type: "open_url", target: "https://www.primevideo.com", ico: "media" },
  { cat: "Musique & vidéo", name: "Disney+", phrase: "ouvre disney plus", type: "open_url", target: "https://www.disneyplus.com", ico: "media" },
  { cat: "Musique & vidéo", name: "Twitch", phrase: "ouvre twitch", type: "open_url", target: "https://www.twitch.tv", ico: "media" },
  /* Réseaux sociaux */
  { cat: "Réseaux sociaux", name: "Instagram", phrase: "ouvre instagram", type: "open_url", target: "https://www.instagram.com", ico: "globe" },
  { cat: "Réseaux sociaux", name: "TikTok", phrase: "ouvre tiktok", type: "open_url", target: "https://www.tiktok.com", ico: "globe" },
  { cat: "Réseaux sociaux", name: "X (Twitter)", phrase: "ouvre twitter", type: "open_url", target: "https://x.com", ico: "globe" },
  { cat: "Réseaux sociaux", name: "Facebook", phrase: "ouvre facebook", type: "open_url", target: "https://www.facebook.com", ico: "globe" },
  { cat: "Réseaux sociaux", name: "Messenger", phrase: "ouvre messenger", type: "open_url", target: "https://www.messenger.com", ico: "msg" },
  { cat: "Réseaux sociaux", name: "LinkedIn", phrase: "ouvre linkedin", type: "open_url", target: "https://www.linkedin.com", ico: "globe" },
  { cat: "Réseaux sociaux", name: "Discord", phrase: "ouvre discord", type: "open_url", target: "https://discord.com/app", ico: "msg" },
  { cat: "Réseaux sociaux", name: "Reddit", phrase: "ouvre reddit", type: "open_url", target: "https://www.reddit.com", ico: "globe" },
  /* Travail & docs */
  { cat: "Travail & docs", name: "Notion", phrase: "ouvre notion", type: "open_url", target: "https://www.notion.so", ico: "app" },
  { cat: "Travail & docs", name: "Google Docs", phrase: "ouvre google docs", type: "open_url", target: "https://docs.google.com", ico: "app" },
  { cat: "Travail & docs", name: "Google Sheets", phrase: "ouvre google sheets", type: "open_url", target: "https://sheets.google.com", ico: "app" },
  { cat: "Travail & docs", name: "Canva", phrase: "ouvre canva", type: "open_url", target: "https://www.canva.com", ico: "app" },
  { cat: "Travail & docs", name: "Figma", phrase: "ouvre figma", type: "open_url", target: "https://www.figma.com", ico: "app" },
  { cat: "Travail & docs", name: "GitHub", phrase: "ouvre github", type: "open_url", target: "https://github.com", ico: "cmd" },
  { cat: "Travail & docs", name: "Teams", phrase: "ouvre teams", type: "open_url", target: "https://teams.microsoft.com", ico: "msg" },
  { cat: "Travail & docs", name: "Slack", phrase: "ouvre slack", type: "open_url", target: "https://app.slack.com", ico: "msg" },
  { cat: "Travail & docs", name: "Outlook", phrase: "ouvre outlook", type: "open_url", target: "https://outlook.live.com", ico: "msg" },
  /* Windows */
  { cat: "Windows", name: "Verrouiller le PC", phrase: "verrouille le pc", phrases: ["verrouille le pc", "verrouille l'ordinateur", "verrouille l'ordi"], type: "keys", target: "win+l", ico: "lock" },
  { cat: "Windows", name: "Capture d'écran", phrase: "fais une capture", phrases: ["fais une capture", "capture d'ecran", "fais un screenshot"], type: "keys", target: "win+shift+s", ico: "app" },
  { cat: "Windows", name: "Explorateur", phrase: "ouvre l'explorateur", phrases: ["ouvre l'explorateur", "explorateur de fichiers"], type: "keys", target: "win+e", ico: "app" },
  { cat: "Windows", name: "Gestionnaire des tâches", phrase: "gestionnaire des taches", type: "keys", target: "ctrl+shift+escape", ico: "app" },
  { cat: "Windows", name: "Paramètres Windows", phrase: "ouvre les parametres", phrases: ["ouvre les parametres", "ouvre les reglages windows"], type: "open_app", target: "ms-settings:", ico: "app" },
  { cat: "Windows", name: "Calculatrice", phrase: "ouvre la calculatrice", phrases: ["ouvre la calculatrice", "lance la calculatrice"], type: "open_app", target: "calc", ico: "app" },
  { cat: "Windows", name: "Bloc-notes", phrase: "ouvre le bloc-notes", type: "open_app", target: "notepad", ico: "note" },
  { cat: "Windows", name: "Corbeille", phrase: "ouvre la corbeille", type: "open_app", target: "shell:RecycleBinFolder", ico: "app" },
  { cat: "Windows", name: "Éteindre dans 1 h", phrase: "eteins le pc dans une heure", phrases: ["eteins le pc dans une heure", "eteins l'ordinateur dans une heure"], type: "shell", target: "shutdown /s /t 3600", reply: "Extinction dans une heure", ico: "cmd" },
  { cat: "Windows", name: "Annuler l'extinction", phrase: "annule l'extinction", phrases: ["annule l'extinction", "annule l'arret"], type: "shell", target: "shutdown /a", reply: "Extinction annulée", ico: "cmd" },
  /* Achats & services */
  { cat: "Achats & services", name: "Amazon", phrase: "ouvre amazon", type: "open_url", target: "https://www.amazon.fr", ico: "globe" },
  { cat: "Achats & services", name: "Leboncoin", phrase: "ouvre leboncoin", type: "open_url", target: "https://www.leboncoin.fr", ico: "globe" },
  { cat: "Achats & services", name: "Vinted", phrase: "ouvre vinted", type: "open_url", target: "https://www.vinted.fr", ico: "globe" },
  { cat: "Achats & services", name: "Uber Eats", phrase: "ouvre uber eats", type: "open_url", target: "https://www.ubereats.com", ico: "globe" },
  { cat: "Achats & services", name: "Deliveroo", phrase: "ouvre deliveroo", type: "open_url", target: "https://deliveroo.fr", ico: "globe" },
  { cat: "Achats & services", name: "Doctolib", phrase: "ouvre doctolib", type: "open_url", target: "https://www.doctolib.fr", ico: "cal" },
  { cat: "Achats & services", name: "SNCF Connect", phrase: "ouvre sncf", type: "open_url", target: "https://www.sncf-connect.com", ico: "globe" },
  { cat: "Achats & services", name: "Booking", phrase: "ouvre booking", type: "open_url", target: "https://www.booking.com", ico: "globe" },
];

function renderTemplates() {
  const have = new Set((STATE.automations || []).flatMap((a) => a.phrases.map((p) => p.toLowerCase())));
  const chip = (t, i) => {
    const on = have.has(t.phrase.toLowerCase());
    return `<button class="tpl-chip ${on ? "added" : ""}" data-tpl="${i}" ${on ? "disabled" : ""}>
      <span class="tpl-ico">${ICONS[t.ico] || ICONS.app}</span>
      <span class="tpl-body">
        <span class="tpl-name">${esc(t.name)}</span>
        <span class="tpl-phrase">« ${esc(t.phrase)} »</span>
      </span>
      ${on
        ? '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#30D158" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5 10 17.5 19 7"/></svg>'
        : '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>'}
    </button>`;
  };
  const cats = [...new Set(TEMPLATES.map((t) => t.cat))];
  $("tpl-grid").innerHTML = cats.map((cat) => `
    <div class="tpl-cat">${esc(cat)}</div>
    <div class="tpl-grid">${TEMPLATES.map((t, i) => t.cat === cat ? chip(t, i) : "").join("")}</div>`).join("");
  document.querySelectorAll("[data-tpl]").forEach((b) =>
    b.addEventListener("click", () => {
      const t = TEMPLATES[+b.dataset.tpl];
      api("save_automation", {
        name: t.name, phrases: t.phrases || [t.phrase],
        action: { type: t.type, target: t.target, args: t.args || "" },
        reply: t.reply || "",
      }).then(() => refresh().then(() => toast(`« ${t.phrase} » ajoutée`)));
    }));
}

/* création par IA : décrire en français, Nova propose l'automatisation */
$("btn-auto-ai").addEventListener("click", () => {
  const desc = $("auto-ai-desc").value.trim();
  if (!desc) { toast("Décrivez d'abord ce que vous voulez automatiser"); return; }
  $("auto-ai-spin").style.display = "";
  $("btn-auto-ai").disabled = true;
  api("suggest_automation", desc).then((r) => {
    $("auto-ai-spin").style.display = "none";
    $("btn-auto-ai").disabled = false;
    if (!r) { toast("L'IA n'a pas pu proposer d'automatisation (configurez une IA sur la page Intelligence)"); return; }
    $("auto-ai-desc").value = "";
    openAutoModal(null, r);
  });
});
$("auto-ai-desc").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("btn-auto-ai").click();
});

function renderAutos() {
  const autos = STATE.automations || [];
  const nbConflits = autos.filter((a) => a.conflict && a.enabled !== false).length;
  const bandeau = nbConflits ? `
    <div class="card auto-conflict-bar">
      <span>⚠ ${nbConflits} automatisation${nbConflits > 1 ? "s" : ""} masque${nbConflits > 1 ? "nt" : ""} des commandes intégrées de Nova (plus complètes). Elles passent avant et peuvent bloquer.</span>
      <button class="btn small" onclick="disableConflicts()">Désactiver les doublons</button>
    </div>` : "";
  $("auto-list").innerHTML = bandeau + autos.map((a) => {
    const t = TYPE_META[a.action.type] || TYPE_META.open_url;
    const cible = a.action.target + (a.action.args ? " · " + a.action.args : "");
    const off = a.enabled === false;
    return `<div class="card auto-row${off ? " auto-off" : ""}" data-id="${a.id}">
      <div class="auto-ico">${ICONS[t.ico]}</div>
      <div class="auto-body">
        <div class="auto-phrase-row">
          <span class="auto-phrase">« ${esc(a.phrases[0] || a.name)} »</span>
          <span class="badge">${t.label}</span>
          ${a.phrases.length > 1 ? `<span class="badge">+${a.phrases.length - 1}</span>` : ""}
          ${a.conflict ? `<span class="badge warn" title="Cette phrase déclenche déjà ${esc(a.conflict)} : l'automatisation passe avant et la masque">⚠ masque ${esc(a.conflict)}</span>` : ""}
          ${off ? `<span class="badge">désactivée</span>` : ""}
        </div>
        <div class="auto-target">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;"><path d="M4 12h15M14 6l6 6-6 6"/></svg>
          <span>${esc(cible)}</span>
        </div>
      </div>
      <div class="auto-actions">
        <button class="switch${off ? "" : " on"}" title="${off ? "Activer" : "Désactiver"}" onclick="toggleAuto('${a.id}')"></button>
        <button class="icon-btn blue" title="Tester" onclick="testAuto('${a.id}', this)">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.5v15l13-7.5z"/></svg>
        </button>
        <button class="icon-btn" title="Modifier" onclick="openAutoModal('${a.id}')">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>
        </button>
        <button class="icon-btn red" title="Supprimer" onclick="deleteAuto('${a.id}')">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13M10 11v5M14 11v5"/></svg>
        </button>
      </div>
    </div>`;
  }).join("") || `<div class="card auto-row" style="justify-content:center;color:var(--dim);">Aucune automatisation. Créez la première, ou piochez dans les modèles ci-dessous !</div>`;
  renderTemplates();
}

window.toggleAuto = (id) => {
  const a = (STATE.automations || []).find((x) => x.id === id);
  if (!a) return;
  const { conflict, ...clean } = a;
  api("save_automation", { ...clean, enabled: a.enabled === false }).then(refresh);
};

window.disableConflicts = () => {
  const cibles = (STATE.automations || []).filter((a) => a.conflict && a.enabled !== false);
  Promise.all(cibles.map((a) => {
    const { conflict, ...clean } = a;
    return api("save_automation", { ...clean, enabled: false });
  })).then(() => { toast(`${cibles.length} automatisation(s) désactivée(s) : les commandes intégrées reprennent la main`); refresh(); });
};

function testAuto(id, btn) {
  api("test_automation", id).then((ok) => {
    btn.innerHTML = ok
      ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#30D158" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5 10 17.5 19 7"/></svg>'
      : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#FF6950" stroke-width="2.2" stroke-linecap="round"><path d="M7 7l10 10M17 7 7 17"/></svg>';
    setTimeout(() => {
      btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.5v15l13-7.5z"/></svg>';
    }, 1800);
  });
}

function deleteAuto(id) {
  api("delete_automation", id).then(refresh);
}

function setAutoType(t) {
  autoType = t;
  const meta = TYPE_META[t];
  $("am-target-label").textContent = meta.cl;
  $("am-target").placeholder = meta.ph;
  $("am-target-hint").textContent = meta.aide;
  $("am-args-field").style.display = t === "open_app" ? "" : "none";
  document.querySelectorAll("#am-seg button").forEach((b) =>
    b.classList.toggle("on", b.dataset.type === t));
}
document.querySelectorAll("#am-seg button").forEach((b) =>
  b.addEventListener("click", () => setAutoType(b.dataset.type)));

function openAutoModal(id, prefill) {
  editingAutoId = id || null;
  const a = id ? (STATE.automations || []).find((x) => x.id === id) : prefill || null;
  $("am-title").textContent = id ? "Modifier l'automatisation"
    : (prefill ? "Proposition de l'IA, vérifiez et validez" : "Nouvelle automatisation");
  $("am-phrase").value = a ? a.phrases.join(" ; ") : "";
  $("am-target").value = a ? a.action.target : "";
  $("am-args").value = a ? (a.action.args || "") : "";
  $("am-reply").value = a ? (a.reply || "") : "";
  setAutoType(a ? a.action.type : "open_url");
  $("modal-auto").classList.add("open");
  setTimeout(() => $("am-phrase").focus(), 60);
}

function closeAutoModal() {
  $("modal-auto").classList.remove("open");
}
$("modal-auto").addEventListener("click", (e) => {
  if (e.target === $("modal-auto")) closeAutoModal();
});

function saveAutoModal() {
  const phrases = $("am-phrase").value.split(";").map((s) => s.trim()).filter(Boolean);
  const target = $("am-target").value.trim();
  if (!phrases.length || !target) { toast("Phrase et cible sont obligatoires"); return; }
  api("save_automation", {
    id: editingAutoId || undefined,
    name: phrases[0],
    phrases,
    action: { type: autoType, target, args: $("am-args").value.trim() },
    reply: $("am-reply").value.trim(),
  }).then(() => { closeAutoModal(); refresh(); toast("Automatisation enregistrée"); });
}

/* -------------------------------------------------------- intelligence --- */
const PROVIDERS = [
  { id: "anthropic", nom: "Claude", ph: "sk-ant-…", logo: '<path d="M12 3l7.5 18h-3.4l-1.5-3.8H9.4L7.9 21H4.5Zm0 5.6-2 5.6h4Z" fill="currentColor" stroke="none"></path>' },
  { id: "openai", nom: "OpenAI", ph: "sk-…", logo: '<circle cx="12" cy="12" r="3"></circle><path d="M12 3v3M12 18v3M4.2 7.5l2.6 1.5M17.2 15l2.6 1.5M4.2 16.5 6.8 15M17.2 9l2.6-1.5"></path>' },
  { id: "gemini", nom: "Gemini", ph: "AIza…", logo: '<path d="M12 2.5C12.6 7.8 16.2 11.4 21.5 12 16.2 12.6 12.6 16.2 12 21.5 11.4 16.2 7.8 12.6 2.5 12 7.8 11.4 11.4 7.8 12 2.5Z" fill="currentColor" stroke="none"></path>' },
  { id: "deepseek", nom: "DeepSeek", ph: "sk-…", logo: '<path d="M3.5 12a8.5 8.5 0 0 1 15.2-5.2c1 .1 1.9.4 2.8 1-1 .4-1.7.6-2.3 1.4A8.5 8.5 0 1 1 3.5 12Z"></path>' },
  { id: "groq", nom: "Groq", ph: "gsk_…", logo: '<path d="M13 2 4.5 13.5h5L10 22l8.5-11.5h-5z" fill="currentColor" stroke="none"></path>' },
  { id: "mistral", nom: "Mistral", ph: "clé Mistral", logo: '<path d="M4 8h8.5a2.3 2.3 0 1 0-2.2-3M4 12h13.5a2.3 2.3 0 1 1-2.2 3M4 16h6.5"></path>' },
  { id: "xai", nom: "Grok (xAI)", ph: "xai-…", logo: '<path d="M5 4l14 16M19 4l-6.5 7.4M5 20l6.5-7.4"></path>' },
  { id: "openrouter", nom: "OpenRouter", ph: "sk-or-…", logo: '<path d="M3 7h5c3 0 4.5 10 7.5 10H21M3 17h5c1.5 0 2.5-2.5 3.5-5"></path><path d="M18 4l3 3-3 3M18 14l3 3-3 3"></path>' },
  { id: "ollama", nom: "Ollama", ph: "", logo: '<rect x="5" y="8" width="14" height="12" rx="4"></rect><path d="M8.5 8V6a3.5 3.5 0 0 1 7 0v2"></path><circle cx="9.5" cy="13.5" r=".9" fill="currentColor" stroke="none"></circle><circle cx="14.5" cy="13.5" r=".9" fill="currentColor" stroke="none"></circle>' },
];
let selProvider = null;

function renderProvGrid() {
  if (!STATE) return;
  const cfg = STATE.config, secrets = STATE.secrets || {};
  const health = STATE.status.providers || {};
  const auto = cfg.provider === "auto";
  if (selProvider === null) {
    selProvider = cfg.provider !== "auto" && cfg.provider !== "off" ? cfg.provider : "anthropic";
  }
  $("sw-provider-auto").classList.toggle("on", auto);
  $("prov-grid").innerHTML = PROVIDERS.map((p) => {
    const hasKey = p.id === "ollama" ? STATE.status.ollama_running : !!secrets[p.id];
    const h = health[p.id];
    let sub, cls = "";
    if (p.id === "ollama") {
      sub = STATE.status.ollama_running ? "Local · privé" : "non détecté";
      cls = hasKey ? "ok" : "";
    } else if (!hasKey) {
      sub = "Clé requise";
    } else if (h && h.ok) {
      sub = "Validée ✓" + (h.ms ? ` · ${h.ms} ms` : "");
      cls = "ok";
    } else if (h && h.ok === false) {
      sub = "Erreur — voir détail";
      cls = "ko";
    } else {
      sub = "Clé enregistrée · à tester";
      cls = "warn";
    }
    const pick = auto && STATE.status.provider === p.id
      ? '<span class="prov-pick">auto</span>' : "";
    return `<button class="prov-card ${selProvider === p.id ? "sel" : ""}" data-prov="${p.id}">
      ${pick}
      <span class="prov-tile"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${p.logo}</svg></span>
      <span style="display:flex;flex-direction:column;gap:1px;align-items:center;">
        <span class="prov-name">${p.nom}</span>
        <span class="prov-sub ${cls}">${sub}</span>
      </span>
    </button>`;
  }).join("");
  document.querySelectorAll(".prov-card").forEach((b) =>
    b.addEventListener("click", () => {
      selProvider = b.dataset.prov;
      // en mode auto, cliquer une carte ouvre sa configuration SANS désactiver l'auto
      if (STATE.config.provider === "auto") { renderProvGrid(); return; }
      api("save_config", { provider: selProvider }).then((c) => { STATE.config = c; renderProvGrid(); });
    }));
  renderProvConfig();
}

$("sw-provider-auto").addEventListener("click", () => {
  const on = !$("sw-provider-auto").classList.contains("on");
  api("save_config", { provider: on ? "auto" : (selProvider || "anthropic") })
    .then((c) => { STATE.config = c; renderProvGrid(); });
});

function fmtAgo(ts) {
  if (!ts) return "";
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 90) return " · à l'instant";
  if (s < 3600) return ` · il y a ${Math.round(s / 60)} min`;
  if (s < 86400) return ` · il y a ${Math.round(s / 3600)} h`;
  return ` · il y a ${Math.round(s / 86400)} j`;
}

const CHECK_SVG = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5 10 17.5 19 7"/></svg>';

function renderProvConfig() {
  const box = $("prov-config");
  if (!selProvider || selProvider === "ollama") { box.style.display = "none"; return; }
  const p = PROVIDERS.find((x) => x.id === selProvider);
  const cfg = STATE.config.providers[selProvider] || {};
  const hasKey = !!(STATE.secrets || {})[selProvider];
  box.style.display = "";
  $("pc-name").textContent = p.nom;
  $("pc-model-label").textContent = (cfg.model || "") + " · API " + p.nom;
  $("pc-key").value = "";
  $("pc-key").placeholder = hasKey ? "●●●●●●●●  (clé enregistrée — coller pour remplacer)" : `Clé API ${p.nom} (${p.ph})`;
  $("pc-model").value = cfg.model || "";
  // dernier test connu (persisté) : on voit tout de suite si la clé est validée
  const h = (STATE.status.providers || {})[selProvider];
  $("pc-test-result").innerHTML = !h ? (hasKey ? '<span class="test-warn">Clé enregistrée — cliquez sur Tester</span>' : "") : h.ok
    ? `<span class="test-ok">${CHECK_SVG}Clé validée · ${h.ms} ms${fmtAgo(h.ts)}</span>`
    : `<span class="test-ko">${esc((h.detail || "échec du test").slice(0, 90))}</span>`;
}

$("pc-test").addEventListener("click", () => {
  const key = $("pc-key").value.trim();
  const model = $("pc-model").value.trim();
  const doTest = () => {
    $("pc-test-spin").style.display = "";
    $("pc-test-result").innerHTML = "";
    api("test_provider", selProvider).then((r) => {
      $("pc-test-spin").style.display = "none";
      $("pc-test-result").innerHTML = r.ok
        ? `<span class="test-ok"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5 10 17.5 19 7"/></svg>Connexion réussie · ${r.ms} ms</span>`
        : `<span class="test-ko">${esc(r.detail.slice(0, 90))}</span>`;
      refresh();
    });
  };
  const saveModel = model ? api("save_config", { providers: { [selProvider]: { model } } }) : Promise.resolve();
  saveModel.then(() => {
    if (key) api("set_secret", selProvider, key).then((sec) => {
      STATE.secrets = sec; $("pc-key").value = "";
      if (selProvider === "groq" && !((STATE.config.stt || {}).cloud_enabled)) {
        toast("Astuce : la même clé active la reconnaissance vocale Groq (Réglages > Écoute)");
      }
      doTest();
    });
    else doTest();
  });
});

// Entrée dans le champ clé ou modèle = enregistrer + tester (zéro clic superflu)
["pc-key", "pc-model"].forEach((id) =>
  $(id).addEventListener("keydown", (e) => { if (e.key === "Enter") $("pc-test").click(); }));

function loadIntelligence() {
  api("suggest_models").then((data) => {
    if (!data) return;
    const pc = data.pc;
    $("ollama-badge").className = "badge " + (pc.ollama_running ? "green" : "");
    $("ollama-badge").textContent = pc.ollama_running ? "Ollama détecté"
      : (pc.ollama_installed ? "Ollama installé (lancez-le)" : "Ollama non installé");
    const fits = data.models.filter((m) => m.fits);
    const maxB = fits.length ? fits[fits.length - 1].name.match(/([\d.]+)b/i) : null;
    $("pc-grid").innerHTML = `
      <div class="pc-tile"><span class="k">Mémoire vive</span><span class="v">${pc.ram_gb} Go</span><span class="m">${pc.cpu_cores} cœurs CPU</span></div>
      <div class="pc-tile"><span class="k">Carte graphique</span><span class="v">${esc(pc.gpu || "Aucune détectée")}</span><span class="m">${pc.gpu ? "accélération disponible" : "calcul sur CPU"}</span></div>
      <div class="pc-tile verdict"><span class="k">Verdict</span><span class="v">Jusqu'à ${maxB ? maxB[1] + " Mds de paramètres" : "modèles légers"}</span><span class="m">${fits.length} modèles compatibles</span></div>`;
    $("model-list").innerHTML = data.models.map((m) => `
      <div class="model-row" data-model="${m.name}">
        <div class="model-body">
          <div class="model-name-row">
            <span class="model-name">${m.name}</span>
            ${m.recommended ? '<span class="badge blue">Recommandé</span>' : ""}
            ${!m.fits ? '<span class="badge">RAM insuffisante</span>' : ""}
          </div>
          <span class="model-desc">${m.desc}</span>
          <div class="progress-row" style="display:none;">
            <span class="progress-lbl"></span>
          </div>
        </div>
        <span class="model-size">${m.size_gb} Go</span>
        ${m.installed
          ? '<span class="model-installed"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5 10 17.5 19 7"/></svg>Installé</span>'
          : `<button class="model-install" ${m.fits ? "" : "disabled"} onclick="pullModel('${m.name}', this)">Installer</button>`}
      </div>`).join("");
  });
}

function pullModel(name, btn) {
  btn.disabled = true;
  btn.textContent = "…";
  api("ollama_pull", name);
  const row = btn.closest(".model-row");
  const prog = row.querySelector(".progress-row");
  const lbl = row.querySelector(".progress-lbl");
  prog.style.display = "flex";
  const timer = setInterval(() => {
    api("pull_status").then((st) => {
      const s = st[name];
      if (!s) return;
      lbl.textContent = s.progress || "téléchargement…";
      if (s.status === "terminé") {
        clearInterval(timer);
        loadIntelligence();
        toast(name + " installé");
      } else if (s.status === "erreur") {
        clearInterval(timer);
        lbl.textContent = "Erreur : " + s.progress;
        btn.disabled = false;
        btn.textContent = "Réessayer";
      }
    });
  }, 1200);
}

/* ------------------------------------------------------------ réglages --- */
const SHORTCUTS = [
  { key: "hotkey", nom: "Invoquer Nova", desc: "Ouvre la pilule flottante" },
  { key: "dictation_hotkey", nom: "Dictée continue", desc: "Démarrer / arrêter : tout ce que vous dites s'écrit au curseur" },
  { key: "note_hotkey", nom: "Nouvelle note vocale", desc: "Enregistre et transcrit directement dans Notes" },
];

function renderShortcuts() {
  const cfg = STATE.config;
  $("shortcuts-card").innerHTML = SHORTCUTS.map((s, i) => {
    const combo = (cfg[s.key] || "").split("+").filter(Boolean);
    const isRec = recordingKbd === s.key;
    return `<div class="setting-row">
      <div class="grow">
        <span class="s-name">${s.nom}</span>
        <span class="s-desc">${s.desc}</span>
      </div>
      <button class="kbd-btn ${isRec ? "recording" : ""}" data-shortcut="${s.key}">
        ${isRec ? "<span>Appuyez sur les touches…</span>"
          : combo.map((k) => `<span class="kbd">${esc(k.charAt(0).toUpperCase() + k.slice(1)).replace("Space", "Espace")}</span>`).join("")}
      </button>
    </div>`;
  }).join("") + `<div class="setting-foot">Cliquez sur un raccourci pour l'enregistrer à nouveau. Échap pour annuler.</div>`;
  document.querySelectorAll("[data-shortcut]").forEach((b) =>
    b.addEventListener("click", () => { recordingKbd = b.dataset.shortcut; renderShortcuts(); }));
}

document.addEventListener("keydown", (e) => {
  if (!recordingKbd) return;
  e.preventDefault();
  e.stopPropagation();
  if (e.key === "Escape") { recordingKbd = null; renderShortcuts(); return; }
  const mods = [];
  if (e.ctrlKey) mods.push("ctrl");
  if (e.altKey) mods.push("alt");
  if (e.shiftKey) mods.push("shift");
  if (e.metaKey) mods.push("windows");
  let k = e.key.toLowerCase();
  if (["control", "alt", "shift", "meta"].includes(k)) return; // attendre la touche finale
  if (k === " ") k = "space";
  const combo = [...mods, k].join("+");
  const key = recordingKbd;
  recordingKbd = null;
  deepPatch(key, combo).then(() => { renderShortcuts(); toast("Raccourci enregistré : " + combo); });
});

function applyConfigToUI() {
  if (!STATE) return;
  const cfg = STATE.config;
  // switches génériques
  document.querySelectorAll("[data-cfg]").forEach((sw) => {
    sw.classList.toggle("on", !!deepGet(cfg, sw.dataset.cfg));
  });
  // champs
  $("cfg-wake-engine").value = cfg.wake_engine || "whisper";
  $("cfg-wake-word").value = cfg.wake_word || "";
  $("row-wake-word").style.display = cfg.wake_engine === "whisper" ? "" : "none";
  $("row-porcupine").style.display = cfg.wake_engine === "porcupine" ? "" : "none";
  $("cfg-porcupine-kw").value = cfg.porcupine_keyword || "jarvis";
  $("cfg-porcupine-sens").value = cfg.porcupine_sensitivity || 0.6;
  $("cfg-wake-model").value = cfg.wake_model || "base";
  $("cfg-pill-hide").value = cfg.pill_hide_mode || "timer";
  $("cfg-timer-style").value = cfg.timer_style || "web";
  renderCustomApps(cfg.custom_apps || {});
  $("row-wake-model").style.display = cfg.wake_engine === "whisper" ? "" : "none";
  $("cfg-whisper-model").value = cfg.whisper_model || "small";
  $("row-groq").style.display = (cfg.stt || {}).cloud_enabled ? "" : "none";
  $("cfg-silence").value = cfg.silence_seconds;
  $("cfg-tts-rate").value = (cfg.tts || {}).rate ?? 1;
  $("cfg-tts-volume").value = (cfg.tts || {}).volume ?? 100;
  $("cfg-msg-delivery").value = (cfg.modes?.message || {}).delivery || "auto";
  $("cfg-nav-app").value = (cfg.modes?.navigation || {}).app || "gmaps";
  $("cfg-translate").value = (cfg.neural || {}).translate_to || "";
  $("cfg-urg-name").value = (cfg.modes?.emergency || {}).contact_name || "";
  $("cfg-urg-phone").value = (cfg.modes?.emergency || {}).contact_phone || "";
  $("cfg-urg-trigger").value = (cfg.modes?.emergency || {}).trigger || "urgence";
  $("urgence-word").textContent = (cfg.modes?.emergency || {}).trigger || "urgence";
  $("cfg-twilio-from").value = (cfg.twilio || {}).from_number || "";
  $("cfg-obd-temp").value = (cfg.obd || {}).coolant_alert_c || 105;
  // héritage JARVIS 2.14
  const eng = (cfg.tts || {}).engine || "sapi";
  $("cfg-tts-engine").value = eng;
  $("cfg-edge-voice").style.display = eng === "edge" ? "" : "none";
  $("cfg-edge-voice").value = (cfg.tts || {}).edge_voice || "fr-FR-DeniseNeural";
  if (document.activeElement !== $("cfg-city")) $("cfg-city").value = cfg.city || "";
  if (document.activeElement !== $("cfg-iptv-src"))
    $("cfg-iptv-src").value = (cfg.iptv || {}).source || "";
  if (document.activeElement !== $("cfg-obsidian"))
    $("cfg-obsidian").value = cfg.obsidian_vault || "";
  const clap = cfg.double_clap || "off";
  $("cfg-clap").value = clap.startsWith("light:") ? "light" : clap;
  $("cfg-clap-light").style.display = clap.startsWith("light:") ? "" : "none";
  if (clap.startsWith("light:") && document.activeElement !== $("cfg-clap-light"))
    $("cfg-clap-light").value = clap.slice(6);
  $("sw-mobile").classList.toggle("on", !!cfg.mobile_enabled);
  if (document.activeElement !== $("cfg-mobile-token"))
    $("cfg-mobile-token").value = cfg.mobile_token || "";
  renderShortcuts();
}

/* switches génériques */
document.querySelectorAll("[data-cfg]").forEach((sw) => {
  sw.addEventListener("click", () => {
    const on = !sw.classList.contains("on");
    deepPatch(sw.dataset.cfg, on).then(() => refresh());
  });
});

/* champs réglages : listeners */
$("cfg-wake-engine").addEventListener("change", (e) => deepPatch("wake_engine", e.target.value).then(refresh));
$("cfg-wake-word").addEventListener("blur", (e) => deepPatch("wake_word", e.target.value.trim() || "nova"));
$("cfg-wake-model").addEventListener("change", (e) => deepPatch("wake_model", e.target.value));
$("cfg-pill-hide").addEventListener("change", (e) => deepPatch("pill_hide_mode", e.target.value));
$("cfg-timer-style").addEventListener("change", (e) => deepPatch("timer_style", e.target.value));

/* fenêtre déplaçable comme toutes les applis : la barre de titre de chaque
   page (et la zone logo) sert de poignée — les boutons restent cliquables */
document.querySelectorAll(".page-head").forEach((el) =>
  el.classList.add("pywebview-drag-region"));

/* applications personnalisées (« ouvre X ») */
function renderCustomApps(apps) {
  const box = $("ca-list");
  if (!box) return;
  const keys = Object.keys(apps);
  box.innerHTML = keys.length ? keys.map((k) => `
    <div class="ca-row">
      <span class="ca-name">${esc(k)}</span>
      <span class="ca-target">${esc(apps[k])}</span>
      <button class="icon-btn red" title="Supprimer" data-name="${esc(k)}" onclick="caDelete(this.dataset.name)">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>
      </button>
    </div>`).join("") : "";
}

window.caDelete = (name) => {
  const apps = { ...(STATE?.config?.custom_apps || {}) };
  delete apps[name];
  api("set_custom_apps", apps).then(() => { toast("Supprimé"); refresh(); });
};

$("btn-ca-add").addEventListener("click", () => {
  const name = $("ca-name").value.trim().toLowerCase();
  const target = $("ca-target").value.trim();
  if (!name || !target) { toast("Nom et commande requis"); return; }
  const apps = { ...(STATE?.config?.custom_apps || {}), [name]: target };
  api("set_custom_apps", apps).then(() => {
    $("ca-name").value = ""; $("ca-target").value = "";
    toast(`« Ouvre ${name} » est prêt`);
    refresh();
  });
});

/* comptes Google / Spotify */
$("btn-gg-connect").addEventListener("click", async () => {
  const id = $("ac-gg-id").value.trim(), sec = $("ac-gg-secret").value.trim();
  if (id) await api("set_secret", "google_client_id", id);
  if (sec) await api("set_secret", "google_client_secret", sec);
  const r = await api("account_start", "google");
  toast(r.ok ? "Le navigateur s'ouvre : autorise Nova sur ton compte Google"
             : r.error || "Impossible de lancer la connexion");
  $("ac-gg-id").value = ""; $("ac-gg-secret").value = "";
});
$("btn-gg-disconnect").addEventListener("click", () =>
  api("account_disconnect", "google").then(() => { toast("Gmail déconnecté"); refresh(); }));
$("btn-sp-connect").addEventListener("click", async () => {
  const id = $("ac-sp-id").value.trim();
  if (id) await api("set_secret", "spotify_client_id", id);
  const r = await api("account_start", "spotify");
  toast(r.ok ? "Le navigateur s'ouvre : autorise Nova sur ton compte Spotify"
             : r.error || "Impossible de lancer la connexion");
  $("ac-sp-id").value = "";
});
$("btn-sp-disconnect").addEventListener("click", () =>
  api("account_disconnect", "spotify").then(() => { toast("Spotify déconnecté"); refresh(); }));
$("cfg-porcupine-kw").addEventListener("change", (e) => deepPatch("porcupine_keyword", e.target.value));
$("cfg-porcupine-sens").addEventListener("change", (e) => deepPatch("porcupine_sensitivity", parseFloat(e.target.value)));
$("btn-pick-ppn").addEventListener("click", () => api("pick_ppn").then((p) => { if (p) { toast("Mot personnalisé sélectionné"); refresh(); } }));
$("cfg-whisper-model").addEventListener("change", (e) => { deepPatch("whisper_model", e.target.value); toast("Redémarrez Nova pour charger le nouveau modèle"); });
$("cfg-silence").addEventListener("change", (e) => deepPatch("silence_seconds", Math.min(3, Math.max(0.5, parseFloat(e.target.value) || 1.2))));
$("cfg-tts-rate").addEventListener("change", (e) => deepPatch("tts.rate", parseInt(e.target.value)));
$("cfg-tts-volume").addEventListener("change", (e) => deepPatch("tts.volume", parseInt(e.target.value)));
$("cfg-msg-delivery").addEventListener("change", (e) => deepPatch("modes.message.delivery", e.target.value));
$("cfg-nav-app").addEventListener("change", (e) => deepPatch("modes.navigation.app", e.target.value));
$("cfg-translate").addEventListener("blur", (e) => deepPatch("neural.translate_to", e.target.value.trim()));
$("cfg-urg-name").addEventListener("blur", (e) => deepPatch("modes.emergency.contact_name", e.target.value.trim()));
$("cfg-urg-phone").addEventListener("blur", (e) => deepPatch("modes.emergency.contact_phone", e.target.value.trim()));
$("cfg-urg-trigger").addEventListener("blur", (e) => deepPatch("modes.emergency.trigger", e.target.value.trim() || "urgence"));
$("cfg-twilio-from").addEventListener("blur", (e) => deepPatch("twilio.from_number", e.target.value.trim()));
$("cfg-obd-temp").addEventListener("change", (e) => deepPatch("obd.coolant_alert_c", parseInt(e.target.value) || 105));

/* héritage JARVIS 2.14 : micro, voix Edge, ville, IPTV, Obsidian, clap, mobile */
$("cfg-mic").addEventListener("change", (e) => {
  const v = e.target.value;
  deepPatch("mic_device_index", v === "" ? null : parseInt(v))
    .then(() => toast(v === "" ? "Micro par défaut Windows" : "Micro changé"));
});
$("sw-mic-mute").addEventListener("click", () => {
  const on = !$("sw-mic-mute").classList.contains("on");
  api("set_mic_mute", on).then(() => {
    $("sw-mic-mute").classList.toggle("on", on);
    toast(on ? "Micro coupé" : "Micro rétabli");
  });
});
$("cfg-tts-engine").addEventListener("change", (e) => {
  deepPatch("tts.engine", e.target.value).then(() => {
    $("cfg-edge-voice").style.display = e.target.value === "edge" ? "" : "none";
  });
});
$("cfg-edge-voice").addEventListener("change", (e) => deepPatch("tts.edge_voice", e.target.value));
$("cfg-city").addEventListener("blur", (e) => deepPatch("city", e.target.value.trim()));
$("cfg-obsidian").addEventListener("blur", (e) => deepPatch("obsidian_vault", e.target.value.trim()));
$("btn-iptv-load").addEventListener("click", () => {
  const src = $("cfg-iptv-src").value.trim();
  $("iptv-status").textContent = "chargement…";
  api("iptv_load", src).then((r) => {
    $("iptv-status").textContent = r.ok
      ? (r.count ? `${r.count} chaînes chargées` : "playlist effacée")
      : "échec : " + (r.error || "?");
    if (r.ok && r.count) toast("« Mets la télé » est prêt");
  });
});
function saveClap() {
  const kind = $("cfg-clap").value;
  const val = kind === "light"
    ? "light:" + ($("cfg-clap-light").value.trim() || "salon") : kind;
  deepPatch("double_clap", val);
  $("cfg-clap-light").style.display = kind === "light" ? "" : "none";
}
$("cfg-clap").addEventListener("change", saveClap);
$("cfg-clap-light").addEventListener("blur", saveClap);
$("sw-mobile").addEventListener("click", () => {
  const on = !$("sw-mobile").classList.contains("on");
  api("set_mobile", on, $("cfg-mobile-token").value.trim()).then((info) => {
    $("sw-mobile").classList.toggle("on", info.enabled);
    $("mobile-url").textContent = info.enabled
      ? `→ http://${info.ip}:${info.port}` + (info.has_token ? "?k=…" : "") : "";
    toast(info.enabled
      ? `Accès mobile activé : http://${info.ip}:${info.port} (même Wi-Fi)`
      : "Accès mobile désactivé");
  });
});
api("mobile_info").then((info) => {
  if (info && info.enabled)
    $("mobile-url").textContent = `→ http://${info.ip}:${info.port}`;
}).catch(() => {});

/* filtre de la page « Que dire ? » */
$("aide-search").addEventListener("input", (e) => {
  const q = e.target.value.toLowerCase();
  document.querySelectorAll("#aide-content .aide-chip").forEach((c) => {
    c.style.display = !q || c.textContent.toLowerCase().includes(q) ? "" : "none";
  });
  document.querySelectorAll("#aide-content .aide-card").forEach((card) => {
    const visible = [...card.querySelectorAll(".aide-chip")]
      .some((c) => c.style.display !== "none");
    card.style.display = visible ? "" : "none";
  });
});

/* secrets (write-only) */
document.querySelectorAll("[data-secret-save]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const key = btn.dataset.secretSave;
    const input = $("key-" + key);
    const val = input.value.trim();
    api("set_secret", key, val).then((sec) => {
      STATE.secrets = sec;
      input.value = "";
      input.placeholder = sec[key] ? "●●●●●●●●  (enregistrée)" : input.placeholder;
      toast(val ? "Clé enregistrée (chiffrée localement)" : "Clé effacée");
      renderSecretPlaceholders();
    });
  });
});

function renderSecretPlaceholders() {
  const sec = STATE.secrets || {};
  const defaults = {
    picovoice: "AccessKey Picovoice (gratuite : console.picovoice.ai)",
    groq: "Clé API Groq (console.groq.com)",
    twilio_sid: "Account SID", twilio_token: "Auth Token",
    graph_client_id: "Application (client) ID Azure",
    youtube: "Clé API YouTube Data v3",
    serpapi: "Clé SerpAPI",
  };
  Object.keys(defaults).forEach((k) => {
    const el = $("key-" + k);
    if (el) el.placeholder = sec[k] ? "●●●●●●●●  (enregistrée)" : defaults[k];
  });
}

/* TTS voix */
function loadVoices() {
  api("tts_voices").then((voices) => {
    if (!voices) return;
    const sel = $("cfg-tts-voice");
    const cur = (STATE.config.tts || {}).voice || "";
    sel.innerHTML = '<option value="">Voix par défaut</option>' +
      voices.map((v) => `<option value="${esc(v)}" ${v === cur ? "selected" : ""}>${esc(v.replace("Microsoft ", "").replace(" Desktop", ""))}</option>`).join("");
  });
}
$("cfg-tts-voice").addEventListener("change", (e) => deepPatch("tts.voice", e.target.value));

/* profils */
function renderProfiles() {
  const profiles = STATE.profiles || [];
  const active = STATE.config.active_profile;
  if (!selProfileId || !profiles.some((p) => p.id === selProfileId)) selProfileId = active;
  const sel = $("profile-select");
  sel.innerHTML = profiles.map((p) =>
    `<option value="${p.id}" ${p.id === selProfileId ? "selected" : ""}>${esc(p.name)}${p.id === active ? " ✓" : ""}</option>`).join("");
  const p = profiles.find((x) => x.id === selProfileId);
  if (p) {
    $("pf-name").value = p.name;
    $("pf-lang").value = p.language;
    $("pf-vocab").value = (p.vocabulary || []).join("\n");
    const perso = p.personal || {};
    $("pf-prenom").value = perso.prenom || "";
    $("pf-adresse").value = perso.adresse || "";
    $("pf-tel").value = perso.telephone || "";
    $("pf-email").value = perso.email || "";
    renderContacts(p.contacts || []);
  }
}

function renderContacts(contacts) {
  $("contacts-list").innerHTML = contacts.map((c, i) => `
    <div class="contact-row" data-i="${i}">
      <input class="input c-name" placeholder="Nom" value="${esc(c.name)}">
      <input class="input c-phone" placeholder="+33612345678" value="${esc(c.phone)}">
      <input class="input c-email" placeholder="email (optionnel)" value="${esc(c.email || "")}">
      <button class="icon-btn red" onclick="this.parentElement.remove()">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>
      </button>
    </div>`).join("");
}

function addContactRow() {
  const div = document.createElement("div");
  div.className = "contact-row";
  div.innerHTML = `
    <input class="input c-name" placeholder="Nom">
    <input class="input c-phone" placeholder="+33612345678">
    <input class="input c-email" placeholder="email (optionnel)">
    <button class="icon-btn red" onclick="this.parentElement.remove()">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>
    </button>`;
  $("contacts-list").appendChild(div);
}

function saveProfile() {
  const contacts = [...document.querySelectorAll("#contacts-list .contact-row")].map((r) => ({
    name: r.querySelector(".c-name").value.trim(),
    phone: r.querySelector(".c-phone").value.trim(),
    email: r.querySelector(".c-email").value.trim(),
  })).filter((c) => c.name);
  api("save_profile", {
    id: selProfileId,
    name: $("pf-name").value.trim() || "Profil",
    language: $("pf-lang").value.trim() || "fr",
    vocabulary: $("pf-vocab").value.split("\n").map((s) => s.trim()).filter(Boolean),
    personal: {
      prenom: $("pf-prenom").value.trim(),
      adresse: $("pf-adresse").value.trim(),
      telephone: $("pf-tel").value.trim(),
      email: $("pf-email").value.trim(),
    },
    contacts,
  }).then((profiles) => { STATE.profiles = profiles; renderProfiles(); toast("Profil enregistré"); });
}

function newProfile() {
  api("save_profile", { name: "Profil " + ((STATE.profiles || []).length + 1), language: "fr", vocabulary: [], contacts: [] })
    .then((profiles) => {
      STATE.profiles = profiles;
      selProfileId = profiles[profiles.length - 1].id;
      renderProfiles();
    });
}

$("profile-select").addEventListener("change", (e) => {
  selProfileId = e.target.value;
  api("activate_profile", selProfileId).then(() => refresh());
});

$("btn-del-profile").addEventListener("click", () => {
  api("delete_profile", selProfileId).then((profiles) => {
    if (profiles.length === (STATE.profiles || []).length) { toast("Impossible de supprimer le dernier profil"); return; }
    STATE.profiles = profiles;
    selProfileId = null;
    refresh();
  });
});

/* Microsoft Graph */
$("btn-graph-connect").addEventListener("click", () => {
  api("graph_start").then((r) => {
    if (r && r.error) { toast(r.error); return; }
    if (r && r.userCode) {
      const box = $("graph-code");
      box.style.display = "";
      box.innerHTML = `
        <span>1. Ouvrez <a onclick="api('open_url','${esc(r.verificationUri)}')">${esc(r.verificationUri)}</a></span>
        <span>2. Entrez le code : <span class="code">${esc(r.userCode)}</span></span>`;
    }
  });
});

function renderGraphStatus(g) {
  const el = $("graph-status");
  if (!el || !STATE) return;
  const st = STATE.status.graph || {};
  if (st.connected) {
    el.innerHTML = '<span style="color:var(--ok);font-weight:600;">Compte connecté</span>';
    $("graph-code").style.display = "none";
    $("btn-graph-connect").textContent = "Reconnecter";
    if (!$("btn-graph-disc")) {
      const b = document.createElement("button");
      b.id = "btn-graph-disc";
      b.className = "btn danger small";
      b.textContent = "Déconnecter";
      b.onclick = () => api("graph_disconnect").then(refresh);
      $("btn-graph-connect").after(b);
    }
  } else {
    el.textContent = st.pending === "en attente" ? "En attente de la validation…" : "";
  }
}

/* OBD */
function refreshObdPorts() {
  api("obd_ports").then((ports) => {
    const sel = $("obd-port");
    const cur = (STATE.config.obd || {}).port || "";
    sel.innerHTML = '<option value="">— port série —</option>' +
      (ports || []).map((p) => `<option value="${esc(p.path)}" ${p.path === cur ? "selected" : ""}>${esc(p.path)} · ${esc(p.name)}</option>`).join("");
  });
}
$("obd-port").addEventListener("change", (e) => deepPatch("obd.port", e.target.value));

$("btn-obd").addEventListener("click", () => {
  const connected = STATE.status.obd.connected;
  (connected ? api("obd_disconnect") : api("obd_connect")).then(() => setTimeout(refresh, 400));
});

function renderObdLive(o) {
  const btn = $("btn-obd");
  const live = $("obd-live");
  if (!btn) return;
  btn.textContent = o.connected ? "Déconnecter" : "Connecter";
  btn.className = o.connected ? "btn danger small" : "btn small";
  if (o.connected) {
    const hot = o.coolant != null && o.coolant >= ((STATE.config.obd || {}).coolant_alert_c || 105);
    live.innerHTML = `${o.mock ? "SIMULÉ · " : ""}${o.rpm ?? "—"} tr/min · ${o.speed ?? "—"} km/h · ` +
      `<span class="${hot ? "hot" : ""}">${o.coolant ?? "—"} °C</span>` +
      (o.dtc.length ? ` · <span class="hot">codes : ${o.dtc.join(", ")}</span>` : "");
  } else {
    live.textContent = o.error || "";
  }
}

/* startup */
$("sw-startup").addEventListener("click", () => {
  const on = !$("sw-startup").classList.contains("on");
  api("set_startup", on).then(() => $("sw-startup").classList.toggle("on", on));
});

/* position de la pilule / bulle */
$("btn-reset-pos").addEventListener("click", () => {
  api("reset_float_pos").then(() => toast("Positions réinitialisées"));
});

/* ---------------------------------------------------------------- init --- */
function init() {
  refresh().then(() => {
    api("get_startup").then((on) => $("sw-startup").classList.toggle("on", !!on));
    loadVoices();
    renderSecretPlaceholders();
    refreshObdPorts();
    loadIntelligence();
  });
  setInterval(() => {
    // rafraîchissement léger (statuts + historique) sans écraser les champs en cours d'édition
    api("get_state").then((s) => {
      if (!s) return;
      if (!STATE) { STATE = s; refresh(); return; }
      const ae = document.activeElement || {};
      const editing = ["INPUT", "TEXTAREA"].includes(ae.tagName);
      const editingNote = ["ne-title", "ne-body"].includes(ae.id);
      STATE.status = s.status;
      STATE.history = s.history;
      STATE.secrets = s.secrets;
      // une note dictée à la voix apparaît sans recharger, même si un champ
      // ailleurs a le focus (seule l'édition de la note elle-même est protégée)
      if (!editingNote && JSON.stringify(s.notes) !== JSON.stringify(STATE.notes)) {
        STATE.notes = s.notes;
        renderNotes();
      }
      if (!editing) {
        const autosChanged = JSON.stringify(s.automations) !== JSON.stringify(STATE.automations);
        STATE.config = s.config; STATE.automations = s.automations; STATE.profiles = s.profiles;
        if (autosChanged) renderAutos();
      }
      renderStatus();
      if (!$("hist-search").value) renderHistory(s.history);
    });
  }, 1200);
}

if (window.pywebview) init();
else window.addEventListener("pywebviewready", init);
