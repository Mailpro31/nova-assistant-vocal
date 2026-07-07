/*
 * Nova — accès mobile.
 *
 * Micro : MediaRecorder (webm/opus) envoyé au PC via POST /talk, où
 * faster-whisper transcrit localement. Jamais l'API Web Speech : l'audio
 * ne quitte pas le réseau local. Réponse lue via GET /tts (WAV SAPI).
 * État rafraîchi par polling GET /state toutes les 1200 ms, avec garde
 * anti-chevauchement. HTTP simple, aucune websocket.
 */

"use strict";

// jeton d'appairage éventuel (?k=...), propagé sur toutes les requêtes
const TOKEN = new URLSearchParams(location.search).get("k") || "";

function u(path) {
  if (!TOKEN) return path;
  return path + (path.indexOf("?") >= 0 ? "&" : "?") + "k=" + encodeURIComponent(TOKEN);
}

// fetch borné dans le temps : aucune requête ne reste pendue
function fetchTimeout(url, options, ms) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), ms || 8000);
  const opts = Object.assign({}, options, { signal: ctl.signal });
  return fetch(url, opts).finally(() => clearTimeout(timer));
}

function init() {
  const $ = (id) => document.getElementById(id);
  const badge = $("badge"), connLabel = $("conn-label");
  const warn = $("warn"), warnClose = $("warn-close");
  const echange = $("echange"), userText = $("user-text"), novaText = $("nova-text");
  const btnPlay = $("btn-play");
  const timersEl = $("timers");
  const statusEl = $("status");
  const bars = $("bars").querySelectorAll(".bar");
  const micBtn = $("mic-btn"), icMic = $("ic-mic"), icStop = $("ic-stop"), micLabel = $("mic-label");
  const form = $("cmd-form"), input = $("cmd-input");

  // idle | recording | thinking | playing
  let state = "idle";
  let rec = null, stream = null, chunks = [], autoStop = null;
  let audio = null;                       // lecture WAV en cours
  let pending = false, pendingSince = 0;  // réponse attendue après un envoi
  let lastServerSeen = "", baselineSeen = null;
  let shownUser = "", shownReply = "";
  let pollBusy = false;                   // garde anti-chevauchement du polling
  let rafId = null;
  let statusHoldUntil = 0;                // laisse un message d'erreur visible

  const LABELS = {
    idle: "En attente",
    recording: "Je vous écoute",
    thinking: "Nova réfléchit",
    playing: "Lecture de la réponse",
  };

  // ---- états ---------------------------------------------------------------
  function setState(s) {
    document.body.classList.remove("state-idle", "state-recording",
      "state-thinking", "state-playing");
    document.body.classList.add("state-" + s);
    state = s;
    statusEl.textContent = LABELS[s] || s;
    const recOn = (s === "recording");
    icMic.hidden = recOn;
    icStop.hidden = !recOn;
    micLabel.textContent = recOn ? "Appuyer pour terminer" : "Appuyer pour parler";
    if (recOn) startBars(); else stopBars();
  }

  function flash(text) {
    statusEl.textContent = text;
    statusHoldUntil = Date.now() + 4000;
  }

  // ---- bandeau origine non sécurisée ----------------------------------------
  const insecure = location.protocol !== "https:" &&
    location.hostname !== "localhost" && location.hostname !== "127.0.0.1";
  let warnOk = false;
  try { warnOk = !!sessionStorage.getItem("nova-warn-ok"); } catch (e) {}
  if (insecure && !warnOk) warn.hidden = false;
  warnClose.addEventListener("click", () => {
    warn.hidden = true;
    try { sessionStorage.setItem("nova-warn-ok", "1"); } catch (e) {}
  });

  // ---- état de connexion -----------------------------------------------------
  function setConnected(ok) {
    badge.classList.toggle("on", ok);
    badge.classList.toggle("off", !ok);
    connLabel.textContent = ok ? "connecté" : "hors ligne";
  }
  setConnected(false);

  // ---- dernier échange -------------------------------------------------------
  function showExchange(user, reply) {
    if (user === shownUser && reply === shownReply) return;
    shownUser = user;
    shownReply = reply;
    userText.textContent = user;
    userText.hidden = !user;
    novaText.textContent = reply;
    novaText.hidden = !reply;
    btnPlay.hidden = !reply;
    echange.hidden = !(user || reply);
  }

  function showUser(text) { showExchange(text, ""); }

  // ---- barres animées pendant l'écoute ---------------------------------------
  function startBars() {
    if (rafId) return;
    const step = () => {
      const t = performance.now() / 150;
      bars.forEach((b, i) => {
        let v = 0.4 + 0.3 * Math.sin(t + i * 0.9) + 0.2 * Math.sin(t * 0.5 + i * 1.7);
        v = Math.max(0.1, Math.min(1, v));
        b.style.transform = "scaleY(" + v.toFixed(3) + ")";
      });
      rafId = requestAnimationFrame(step);
    };
    rafId = requestAnimationFrame(step);
  }

  function stopBars() {
    if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
    bars.forEach((b) => { b.style.transform = "scaleY(0.1)"; });
  }

  // ---- lecture de la réponse (WAV généré sur le PC) ---------------------------
  function stopAudio() {
    if (audio) { try { audio.pause(); } catch (e) {} audio = null; }
    if (state === "playing") setState("idle");
  }

  function playReply(text) {
    if (!text) return;
    stopAudio();
    audio = new Audio(u("/tts?text=" + encodeURIComponent(text.slice(0, 350))));
    audio.addEventListener("ended", () => { audio = null; if (state === "playing") setState("idle"); });
    audio.addEventListener("error", () => { audio = null; if (state === "playing") setState("idle"); });
    audio.play().then(() => setState("playing")).catch(() => { audio = null; });
  }

  btnPlay.addEventListener("click", () => {
    if (state === "playing") stopAudio();
    else playReply(shownReply);
  });

  // ---- envoi d'une commande ----------------------------------------------------
  function expectReply() {
    pending = true;
    pendingSince = Date.now();
    baselineSeen = lastServerSeen;
    setState("thinking");
  }

  async function sendText(text) {
    showUser(text);
    setState("thinking");
    try {
      const r = await fetchTimeout(u("/command"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text }),
      }, 10000);
      if (!r.ok) throw new Error("http " + r.status);
      expectReply();
    } catch (e) {
      setState("idle");
      flash("Envoi impossible — vérifiez la connexion");
    }
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || state === "recording") return;
    input.value = "";
    input.blur();
    stopAudio();
    sendText(text);
  });

  // ---- micro (MediaRecorder, tout reste sur le réseau local) --------------------
  const micOk = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia
    && window.MediaRecorder);
  if (!micOk) {
    micBtn.classList.add("disabled");
    micLabel.textContent = "Micro indisponible — utilisez le champ texte";
  }

  async function startRec() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      flash("Micro refusé par le navigateur");
      if (insecure) warn.hidden = false;
      return;
    }
    chunks = [];
    let opts = {};
    if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
      opts = { mimeType: "audio/webm;codecs=opus" };
    }
    try { rec = new MediaRecorder(stream, opts); }
    catch (e) { rec = new MediaRecorder(stream); }
    rec.addEventListener("dataavailable", (e) => {
      if (e.data && e.data.size) chunks.push(e.data);
    });
    rec.addEventListener("stop", onRecStop);
    rec.start();
    setState("recording");
    autoStop = setTimeout(stopRec, 30000); // garde-fou : 30 s maximum
  }

  function stopRec() {
    if (autoStop) { clearTimeout(autoStop); autoStop = null; }
    if (rec && rec.state !== "inactive") rec.stop();
  }

  async function onRecStop() {
    if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null; }
    const blob = new Blob(chunks, { type: (rec && rec.mimeType) || "audio/webm" });
    chunks = [];
    rec = null;
    if (blob.size < 1200) { setState("idle"); return; } // appui trop bref
    setState("thinking");
    try {
      const r = await fetchTimeout(u("/talk"), {
        method: "POST",
        headers: { "Content-Type": blob.type || "audio/webm" },
        body: blob,
      }, 45000);
      if (!r.ok) throw new Error("http " + r.status);
      const data = await r.json();
      if (data && data.text) {
        showUser(data.text);
        expectReply();
      } else {
        setState("idle");
        flash("Je n'ai rien compris — réessayez");
      }
    } catch (e) {
      setState("idle");
      flash("Envoi impossible — vérifiez la connexion");
    }
  }

  micBtn.addEventListener("click", () => {
    if (!micOk || state === "thinking") return;
    if (state === "recording") { stopRec(); return; }
    stopAudio();
    startRec();
  });

  // ---- minuteurs (depuis /state) ---------------------------------------------
  function renderTimers(timers) {
    if (!Array.isArray(timers) || timers.length === 0) {
      timersEl.hidden = true;
      timersEl.textContent = "";
      return;
    }
    timersEl.textContent = "";
    timers.slice(0, 4).forEach((t) => {
      let label = "";
      if (typeof t === "string") label = t;
      else if (t && typeof t === "object") {
        label = t.label || t.name || "Minuteur";
        const rest = t.remaining || t.reste || t.left || "";
        if (rest) label += " — " + rest;
      }
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = label || "Minuteur";
      timersEl.appendChild(chip);
    });
    timersEl.hidden = false;
  }

  // ---- lecture de l'état serveur -----------------------------------------------
  function readState(st) {
    // structure tolérante : app.py peut faire évoluer le contenu de /state
    const last = st.last || st.dernier || {};
    const user = st.last_text || last.text || last.user || "";
    const reply = st.last_reply || last.reply || last.nova || "";
    const stamp = st.last_ts || last.ts || "";
    lastServerSeen = stamp + "|" + reply;

    if (pending) {
      if (reply && lastServerSeen !== baselineSeen) {
        pending = false;
        showExchange(user || shownUser, reply);
        if (state === "thinking") setState("idle");
        playReply(reply);
      } else if (Date.now() - pendingSince > 45000) {
        pending = false;
        if (state === "thinking") setState("idle");
      }
    } else {
      showExchange(user, reply);
    }

    renderTimers(st.timers);

    if (state === "idle" && Date.now() > statusHoldUntil) {
      statusEl.textContent = st.listening ? "Le PC est en écoute"
        : (st.status || LABELS.idle);
    }
  }

  // ---- polling /state (1200 ms, anti-chevauchement) ------------------------------
  async function poll() {
    if (pollBusy) return;
    pollBusy = true;
    try {
      const r = await fetchTimeout(u("/state"), { cache: "no-store" }, 5000);
      if (!r.ok) throw new Error("http " + r.status);
      const st = await r.json();
      setConnected(true);
      readState(st || {});
    } catch (e) {
      setConnected(false);
    } finally {
      pollBusy = false;
    }
  }

  setState("idle");
  poll();
  setInterval(poll, 1200);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
