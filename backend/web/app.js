/* NISAR Change Explorer - application.
   Screens: 01 Find, 02 Check data, 03 Ask, 04a Analysing, 04b Answer, 05 Sources, 06 How we know, 07 Why,
   plus Stories, Watch list, PDF report, Share link and the edge states (first visit, not enough data,
   loading, connection error). All data comes from the backend API in this same server.
   Written with help from Claude (Anthropic), a generative AI tool; reviewed and tested by the team.
   NISAR data: NASA-ISRO, via ASF DAAC. Base map: NASA GIBS Blue Marble and OpenStreetMap. */
"use strict";

// ---------------------------------------------------------------- helpers
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n, d = 0) => (n === null || n === undefined || Number.isNaN(n)) ? "–" : Number(n).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const dshort = (iso) => iso ? `${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]}` : "";
const abs = (u) => !u ? u : (u.startsWith("http") ? u : location.origin + u);
const corners = "";
const GAP = ["2026-07-27", "2026-08-10"];
const NISAR_START = "2026-06-17";

// the API's verdict_code is stable; fall back to the text for results stored before it existed
function vcode(ag) {
  if (ag.verdict_code) return ag.verdict_code;
  return { "Agrees with OPERA": "agrees", "Partly agrees": "partly", "Disagrees": "disagrees" }[ag.verdict] || "";
}
// plain-words block: what was checked, where it failed, and that no human-labelled accuracy exists
function validationHTML(R) {
  const v = R.validation; if (!v) return "";
  const fails = (v.known_failures || []).map((f) => `<li>${esc(f)}</li>`).join("");
  return `<div class="hint small" style="margin-top:8px"><b>What has been checked.</b> ${esc(v.this_place || "")}.
    Accuracy measured against human-labelled data: <b>${esc(v.human_labelled_accuracy || "not measured")}</b>.
    ${fails ? `<br><b>Where it failed.</b><ul style="margin:4px 0 0 18px">${fails}</ul>` : ""}</div>`;
}

function toast(msg, ms = 2600) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), ms);
}

async function api(path, opts = {}) {
  if (window.NCE_DEMO) return demoApi(path, opts);
  return apiServer(path, opts);
}

async function apiServer(path, opts = {}) {
  let r;
  try {
    r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  } catch (e) {
    throw Object.assign(new Error("Can't reach the NISAR Change Explorer server."), { offline: true });
  }
  if (!r.ok) {
    let detail = "";
    try { const j = await r.json(); detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch (_) {}
    throw Object.assign(new Error(detail || `Request failed (${r.status})`), { status: r.status });
  }
  return r.status === 204 ? null : r.json();
}


// ---------------------------------------------------------------- online demo (static files, no server)
// The Vercel demo has no Python server. It answers the same requests from files made by
// scripts/export_demo.py: prepared places, their saved answers and images.
const GITHUB_URL = "https://github.com/abilashprabakar27-ctrl/nisar-change-explorer";
const DEMO = { prepared: null, jobs: {} };
async function demoJson(path) {
  const r = await fetch(path, { cache: "no-cache" });
  if (!r.ok) throw Object.assign(new Error("That isn’t part of the online demo."), { notInDemo: true });
  return r.json();
}
async function demoPrepared() {
  if (!DEMO.prepared) DEMO.prepared = await demoJson("content/prepared.json");
  return DEMO.prepared;
}
function demoFind(bbox) {
  if (!bbox || !DEMO.prepared) return null;
  const cx = (bbox[0] + bbox[2]) / 2, cy = (bbox[1] + bbox[3]) / 2;
  return DEMO.prepared.places.find((p) => cx >= p.bbox[0] && cx <= p.bbox[2] && cy >= p.bbox[1] && cy <= p.bbox[3]) || null;
}
const demoWatch = {
  load() { try { return JSON.parse(localStorage.getItem("nce-watch") || "[]"); } catch (_) { return []; } },
  save(v) { try { localStorage.setItem("nce-watch", JSON.stringify(v)); } catch (_) {} },
};
async function demoApi(path, opts = {}) {
  const method = (opts.method || "GET").toUpperCase();
  const body = opts.body ? JSON.parse(opts.body) : {};
  const [route, query] = path.split("?");
  await demoPrepared();
  if (route === "/demo-areas") return DEMO.prepared.stories;
  if (route === "/places") {
    const q = new URLSearchParams(query).get("q");
    try {
      const r = await fetch("https://nominatim.openstreetmap.org/search?format=json&limit=5&q=" + encodeURIComponent(q));
      return (await r.json()).map((p) => ({ name: p.display_name, lat: +p.lat, lon: +p.lon }));
    } catch (_) { throw new Error("Search isn’t available right now. Try one of the stories instead."); }
  }
  if (route === "/availability") {
    const p = demoFind(body.bbox);
    if (!p) throw Object.assign(new Error("not prepared"), { notInDemo: true });
    return p.availability;
  }
  if (route === "/downloads/status") return { frames_total: 0, dates: [] };
  if (route === "/analyses" && method === "POST") {
    const p = demoFind(body.bbox);
    if (!p) throw Object.assign(new Error("not prepared"), { notInDemo: true });
    const id = "demo-" + Date.now();
    DEMO.jobs[id] = { key: p.key, n: 0 };
    if (body.event_date && p.window && !(body.event_date > p.window[0] && body.event_date <= p.window[1])) toast("The online demo shows the prepared dates for this place.", 4000);
    return { id, status: "queued" };
  }
  if (route.startsWith("/analyses/")) {
    const job = DEMO.jobs[route.split("/")[2]];
    if (!job) throw Object.assign(new Error("not prepared"), { notInDemo: true });
    job.n += 1;
    const steps = [["check", 10], ["prepare", 45], ["detect", 70], ["explain", 92]];
    if (job.n <= steps.length) return { status: "running", step: steps[job.n - 1][0], progress: steps[job.n - 1][1] };
    return { status: "done", progress: 100, step: "done", result: await demoJson(`content/results/${job.key}.json`) };
  }
  if (route === "/sample") return demoJson(`content/results/${DEMO.prepared.sample}.json`);
  const ask = route.match(/^\/results\/([^/]+)\/ask$/);
  if (ask) {
    const answers = await demoJson(`content/ask/${ask[1]}.json`);
    return { answer: answers[body.question] || "We can’t answer that one from this result.", based_on: [], suggestions: [] };
  }
  const res = route.match(/^\/results\/([^/]+)$/);
  if (res) return demoJson(`content/results/${res[1]}.json`);
  if (route === "/learn") return demoJson(`content/learn-${new URLSearchParams(query).get("tag") || "all"}.json`);
  if (route === "/watch" && method === "POST") {
    const items = demoWatch.load();
    items.push({ id: String(Date.now()), name: body.name, bbox: body.bbox, last_result_date: body.last_result_date, new_pass_available: false });
    demoWatch.save(items); return items.at(-1);
  }
  if (route === "/watch" || route === "/watch/check") return demoWatch.load();
  if (route.startsWith("/watch/") && method === "DELETE") { demoWatch.save(demoWatch.load().filter((w) => w.id !== route.split("/")[2])); return null; }
  throw Object.assign(new Error("That isn’t part of the online demo."), { notInDemo: true });
}
function renderNotInDemo() {
  setProgress(0);
  const names = (DEMO.prepared ? DEMO.prepared.places : []).map((p, i) => `<button class="btn small" data-demo="${i}">${esc(p.name)}</button>`).join("");
  ui(`<aside class="side right frame" style="width:440px" role="alert">
    <div class="screenhead"><div><h1>This place isn’t in the online demo</h1></div></div>
    <p>The online version shows a few places we’ve already prepared. To explore anywhere on Earth, you can run the full app on your own computer.</p>
    <div class="lbl">Try one of these instead</div>
    <div class="presets">${names}</div>
    <div class="row"><a class="btn primary" href="${GITHUB_URL}" target="_blank" rel="noopener">Get the full app</a><button class="btn" id="niBack">Back to the map</button></div>
  </aside>`);
  $$("[data-demo]").forEach((b) => b.onclick = () => { const p = DEMO.prepared.places[+b.dataset.demo]; setArea(p.bbox, p.name, p.event_date); go("check"); });
  $("#niBack").onclick = () => { S.area = null; drawArea(); go("find"); };
}

// ---------------------------------------------------------------- state
const S = {
  screen: "find", area: null, areaName: "Study area", boxKm: 25,
  avail: null, question: "change", looking: ["water"], eventDate: null, quick: false,
  jobId: null, result: null, resultKey: null,
  view: "swipe", pol: "hh", swipeX: 0.5, lapseTimer: null, charts: [],
};

// ---------------------------------------------------------------- map
const STYLE = {
  version: 8,
  projection: { type: "globe" },
  sources: {
    gibs: { type: "raster", tileSize: 256, maxzoom: 8, attribution: "NASA GIBS",
      tiles: ["https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg"] },
    osm: { type: "raster", tileSize: 256, maxzoom: 19, attribution: "© OpenStreetMap contributors",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"] },
  },
  layers: [
    { id: "bg", type: "background", paint: { "background-color": "#05080D" } },
    { id: "gibs", type: "raster", source: "gibs", paint: { "raster-brightness-max": 0.85 } },
    { id: "osm", type: "raster", source: "osm", minzoom: 7.5,
      paint: { "raster-saturation": -0.85, "raster-brightness-max": 0.42, "raster-contrast": 0.15, "raster-opacity": 0.92 } },
  ],
  sky: { "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 5, 1, 7, 0] },
};

let map;
function initMap() {
  map = new maplibregl.Map({ container: "map", style: STYLE, center: [84, 18], zoom: 1.7, attributionControl: { compact: true } });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
  map.on("load", () => {
    map.addSource("area", { type: "geojson", data: emptyFC() });
    map.addLayer({ id: "area-fill", type: "fill", source: "area", paint: { "fill-color": "#7DD3FC", "fill-opacity": 0.08 } });
    map.addLayer({ id: "area-line", type: "line", source: "area", paint: { "line-color": "#7DD3FC", "line-width": 1.6 } });
    if (S.area) drawArea();
  });
  map.on("click", (e) => {
    if (S.screen !== "find") return;
    setAreaFromCenter(e.lngLat.lng, e.lngLat.lat, "Selected area");
  });
}
const emptyFC = () => ({ type: "FeatureCollection", features: [] });
function boxPolygon(b) {
  const [w, s, e, n] = b;
  return { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] } }] };
}
function setAreaFromCenter(lon, lat, name) {
  const km = S.boxKm, dLat = km / 2 / 110.57, dLon = km / 2 / (111.32 * Math.cos(lat * Math.PI / 180));
  setArea([+(lon - dLon).toFixed(4), +(lat - dLat).toFixed(4), +(lon + dLon).toFixed(4), +(lat + dLat).toFixed(4)], name);
}
const fitPad = () => innerWidth > 900 ? { top: 60, bottom: 160, left: 460, right: 420 } : { top: 20, bottom: 20, left: 20, right: 20 };
function setArea(bbox, name, eventDate) {
  S.area = bbox; S.areaName = name || "Study area"; S.avail = null; S.result = null;
  if (eventDate) S.eventDate = eventDate;
  drawArea();
  map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: fitPad(), duration: 1800, maxZoom: 11 });
  if (S.screen === "find") renderFind();
}
function drawArea() {
  const src = map && map.getSource && map.getSource("area");
  if (src) src.setData(S.area ? boxPolygon(S.area) : emptyFC());
}
function areaKm2(b) {
  const lat = (b[1] + b[3]) / 2 * Math.PI / 180;
  return Math.abs(b[2] - b[0]) * 111.32 * Math.cos(lat) * Math.abs(b[3] - b[1]) * 110.57;
}

// ---------------------------------------------------------------- shell
function setProgress(step) {
  const p = $("#progress");
  $$(".node", p).forEach((n) => n.remove());
  const labels = ["Find a place", "Check the data", "Ask a question", "See the answer"];
  labels.forEach((l, i) => {
    const pos = 12.5 + 25 * i;
    const n = document.createElement("div");
    n.className = "node" + (i + 1 < step ? " done" : i + 1 === step ? " cur" : "");
    n.style.left = pos + "%"; n.innerHTML = `<b></b>${l}`;
    p.appendChild(n);
  });
  $("#progFill").style.width = step ? (12.5 + 25 * (step - 1)) + "%" : "0";
  p.hidden = !step;
}
function setHere() {
  const name = S.result ? S.result.area.name : (S.area ? S.areaName : "");
  const el = $("#here"); if (!el) return;
  el.hidden = !name; $("#hereName").textContent = name;
}
function setNav(which) { setHere(); $$(".top nav button").forEach((b) => b.dataset.nav === which ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current")); }
function ui(html) { document.body.dataset.screen = S.screen; destroyCharts(); stopLapse(); if (vA) { try { vA.remove(); vB.remove(); } catch (_) {} vA = vB = null; } $("#ui").innerHTML = html; requestAnimationFrame(setupScrollHint); }
function destroyCharts() { S.charts.forEach((c) => c.destroy()); S.charts = []; }
function go(screen) {
  S.screen = screen;
  $("#map").style.visibility = ["sources", "evidence", "why", "answer"].includes(screen) ? "hidden" : "visible";
  ({ find: renderFind, check: renderCheck, ask: renderAsk, analysing: renderAnalysing, answer: renderAnswer,
     sources: renderSources, evidence: renderEvidence, why: renderWhy, stories: renderStories })[screen]();
  window.scrollTo(0, 0);
}


// ---------------------------------------------------------------- "scroll down" cue
const HINTS = { answer: "Scroll for the full story, charts and common questions", sources: "Scroll for more",
  evidence: "Scroll for limits and the data we used", why: "Scroll to see every cause we checked" };
let hintCleanup = null;
function setupScrollHint() {
  if (hintCleanup) hintCleanup();
  const box = $("#scrollHint"), btn = box.querySelector("button");
  const page = $("#ui .page"), side = $("#ui .side.frame");
  const phone = innerWidth <= 900;
  let el = page || side;
  if (!el) { box.hidden = true; return; }
  const winScroll = phone || getComputedStyle(el).overflowY === "visible";
  const sc = winScroll ? document.scrollingElement : el;
  const small = !page;
  $("#scrollHintText").textContent = page ? (HINTS[S.screen] || "There’s more below") : "More below";
  box.classList.toggle("small", small);
  let used = false;
  const place = () => {
    const more = sc.scrollHeight - sc.clientHeight - sc.scrollTop > 40;
    if (sc.scrollTop > 160) used = true;
    if (!more || (used && page)) { box.classList.add("gone"); setTimeout(() => box.classList.contains("gone") && (box.hidden = true), 300); return; }
    box.hidden = false; box.classList.remove("gone");
    const r = winScroll ? { left: 0, width: innerWidth, bottom: innerHeight } : el.getBoundingClientRect();
    box.style.left = (r.left + r.width / 2) + "px";
    box.style.top = (Math.min(r.bottom, innerHeight - (phone ? 60 : 56)) - (small ? 16 : 50)) + "px";
  };
  btn.onclick = () => sc.scrollBy({ top: sc.clientHeight * 0.75, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  const target = winScroll ? window : el;
  target.addEventListener("scroll", place, { passive: true }); addEventListener("resize", place);
  const t1 = setTimeout(place, 400), t2 = setTimeout(place, 1500);
  hintCleanup = () => { target.removeEventListener("scroll", place); removeEventListener("resize", place); clearTimeout(t1); clearTimeout(t2); box.hidden = true; };
}


// ---------------------------------------------------------------- data download (like the terminal scripts)
const fmtDur = (sec) => {
  if (sec === null || sec === undefined) return "–";
  if (sec < 45) return "under a minute";
  if (sec < 90) return "about 1 min";
  if (sec < 3600) return `about ${Math.round(sec / 60)} min`;
  const h = Math.floor(sec / 3600), m = Math.round((sec % 3600) / 60);
  return `about ${h} h${m ? " " + m + " min" : ""}`;
};
const fmtMB = (mb) => mb >= 1024 ? (mb / 1024).toFixed(1) + " GB" : Math.round(mb) + " MB";
const sameBox = (a, b) => a && b && a.every((v, i) => Math.abs(v - b[i]) < 1e-4);
let dlTimer = null;
try { const saved = JSON.parse(sessionStorage.getItem("dl") || "null"); if (saved) S.dl = saved; } catch (_) {}

async function dlStatus(scope, eventDate) {
  return api("/downloads/status", { method: "POST", body: JSON.stringify({ bbox: S.area, scope, event_date: eventDate || null }) });
}
function dlStatusHTML(st, scope) {
  const running = S.dl && sameBox(S.dl.bbox, S.area) && !S.dl.finished;
  const bars = st.dates.map((d) => `<i class="${d.cached === d.frames ? "on" : d.cached ? "part" : ""}" ></i>`).join("");
  const what = "Ready to use";
  if (!st.frames_total) return "";
  if (st.all_downloaded) return `<div class="dlstat ok"><span class="lbl">${what}</span><div class="passbar" aria-hidden="true">${bars}</div>
    <span>Everything for this place is ready.</span></div>`;
  const e = st.estimate;
  return `<div class="dlstat"><span class="lbl">${what}</span><div class="passbar" aria-hidden="true">${bars}</div>
    <span class="big2">${st.passes_ready ? "Partly ready" : "Not ready yet"}</span>
    <span class="hint">You can get it ready now, or we’ll do it when you ask your question.</span>
    ${running ? `<span class="hint accent">Getting it ready now.</span>`
      : `<button class="btn ${scope === "all" ? "primary" : ""}" data-dl="${scope}">Get this place ready</button>`}
    ${scope === "question" ? '' : ""}</div>`;
}
function bindDl(root) {
  $$("[data-dl]", root).forEach((b) => b.onclick = () => startDownload(b.dataset.dl, b.dataset.dl === "question" ? S.eventDate : null));
}
async function startDownload(scope, eventDate) {
  try {
    const j = await api("/downloads", { method: "POST", body: JSON.stringify({ bbox: S.area, name: S.areaName, scope, event_date: eventDate }) });
    S.dl = { id: j.id, bbox: S.area, name: S.areaName, scope, min: false };
    sessionStorage.setItem("dl", JSON.stringify(S.dl));
    toast(j.already_running ? "Already getting this place ready." : "Getting this place ready. Feel free to keep exploring.");
    pollDownload();
    refreshDlBlocks();
  } catch (err) { toast(err.message, 5000); }
}
async function pollDownload() {
  clearTimeout(dlTimer);
  if (!S.dl) return;
  let j;
  try { j = await api("/downloads/" + S.dl.id); } catch (err) { if (err.status === 404) { S.dl = null; sessionStorage.removeItem("dl"); $("#dl").hidden = true; return; } dlTimer = setTimeout(pollDownload, 3000); return; }
  S.dl.last = j;
  renderDock(j);
  if (["done", "failed", "cancelled"].includes(j.status)) {
    if (!S.dl.finished) { S.dl.finished = true; sessionStorage.setItem("dl", JSON.stringify(S.dl)); refreshDlBlocks(); }
    return;
  }
  dlTimer = setTimeout(pollDownload, 1000);
}
function renderDock(j) {
  const el = $("#dl"), d = j.download || {}, st = j.status;
  el.hidden = false;
  el.classList.toggle("done", st === "done");
  if (S.dl.min && st !== "done") {
    el.className = "dl frame min";
    el.innerHTML = `<span class="lbl" style="color:var(--cyan)">${esc(j.name || "Download")}</span><b>${st === "queued" ? "Waiting" : Math.round(d.pct || 0) + "%"}</b><span class="hint small">${d.eta_s ? fmtDur(d.eta_s) + " left" : ""}</span>`;
    el.onclick = () => { S.dl.min = false; renderDock(j); };
    return;
  }
  el.className = "dl frame" + (st === "done" ? " done" : ""); el.onclick = null;
  const head = (t) => `<header><span class="lbl">${t}</span><span class="hint small">${esc(j.name || "")}</span>${st === "done" || st === "failed" || st === "cancelled" ? '<button id="dlClose" aria-label="Close">×</button>' : '<button id="dlMin" aria-label="Minimise">–</button>'}</header>`;
  let body;
  if (st === "queued" || (st === "running" && !j.download)) {
    body = head("Getting ready") + `<p class="hint">${esc(((j.events || []).at(-1) || {}).label || "Starting in a moment…")}</p><div class="bar"><span style="width:2%"></span></div>`;
  } else if (st === "running") {
    const extras = j.step === "extras";
    body = head(extras ? "Almost done" : "Getting this place ready") + `
      <div class="pctbig">${Math.round(d.pct || 0)}<span style="font-size:20px;color:var(--muted)">%</span></div>
      <div class="bar" role="progressbar" aria-valuenow="${Math.round(d.pct || 0)}" aria-valuemin="0" aria-valuemax="100"><span style="width:${d.pct || 0}%"></span></div>
      <div class="eta">${extras ? "Just finishing up…" : `<b>${fmtDur(d.eta_s)}</b> to go`}</div>
<div class="row"><button class="btn small" id="dlCancel">Cancel</button></div>`;
  } else if (st === "done") {
    body = head("All set") + `
      <p style="margin:0">This place is ready to explore.</p>
      <div class="row">${S.area && sameBox(S.area, j.bbox) && S.avail && S.screen !== "ask" ? '<button class="btn primary small" id="dlAsk">Ask a question</button>' : ""}</div>`;
  } else if (st === "cancelled") {
    body = head("Paused") + `<p class="hint" style="margin:0">Nothing is lost. Resume whenever you like and it picks up where it left off.</p><div class="row"><button class="btn small primary" id="dlResume">Resume</button></div>`;
  } else {
    body = head("That didn’t work") + `<p class="hint" style="margin:0">${esc(j.error || "Something went wrong.")}</p><div class="row"><button class="btn small primary" id="dlResume">Try again</button></div>`;
  }
  el.innerHTML = body;
  const on = (id, fn) => { const b = document.getElementById(id); if (b) b.onclick = (e) => { e.stopPropagation(); fn(); }; };
  on("dlMin", () => { S.dl.min = true; renderDock(j); });
  on("dlClose", () => { el.hidden = true; S.dl = null; sessionStorage.removeItem("dl"); refreshDlBlocks(); });
  on("dlCancel", async () => { await api(`/downloads/${S.dl.id}/cancel`, { method: "POST" }); toast("Pausing…"); });
  on("dlAsk", () => go("ask"));
  on("dlResume", async () => {
    const r = await api("/downloads", { method: "POST", body: JSON.stringify({ bbox: j.bbox, name: j.name, scope: S.dl.scope || "all", event_date: S.dl.scope === "question" ? S.eventDate : null }) });
    S.dl = { ...S.dl, id: r.id, finished: false }; sessionStorage.setItem("dl", JSON.stringify(S.dl)); pollDownload();
  });
}
// re-draw the status blocks on Check / Ask after a download starts or ends
function refreshDlBlocks() {
  if (S.screen === "check" && $("#dlCheck")) loadDlBlock("#dlCheck", "all");
  if (S.screen === "ask" && $("#dlAsk2")) loadDlBlock("#dlAsk2", "question", S.eventDate);
}
async function loadDlBlock(sel, scope, eventDate) {
  const box = $(sel); if (!box || !S.area) return;
  try { const st = await dlStatus(scope, eventDate); if ($(sel) === box) { box.innerHTML = dlStatusHTML(st, scope); bindDl(box); requestAnimationFrame(setupScrollHint); } }
  catch (_) { box.innerHTML = ""; }
}

// ================================================================ 01 FIND
let demoAreas = [];
async function renderFind() {
  setProgress(1); setNav("find");
  if (S.area && map && map.getZoom() < 5) map.fitBounds([[S.area[0], S.area[1]], [S.area[2], S.area[3]]], { padding: fitPad(), duration: 1500, maxZoom: 11 });
  const a = S.area;
  ui(`
  <aside class="side left frame" aria-label="Find a place">
    <div class="screenhead"><div><h1>Where would you like to look?</h1><small>Pick any place on Earth</small></div></div>
    <form class="searchbox" id="searchForm" role="search">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#7DD3FC" stroke-width="1.8" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="M20 20l-4-4"></path></svg>
      <label class="sr" for="q">Search a place</label>
      <input id="q" type="search" placeholder="Search a town, river or region" autocomplete="off">
      <button class="btn small" type="submit">Search</button>
    </form>
    <ul class="results" id="results"></ul>
    <div><div class="lbl">${window.NCE_DEMO ? "Pick one of these places to explore" : "Or start with a real 2026 event"}</div><div class="presets" id="presets" style="margin-top:8px"></div></div>
    <div class="lbl">${a ? "Your area" : "No area picked yet"}</div>
    ${a ? `
      <div class="statgrid">
        <div><span class="lbl">Place</span><span>${esc(S.areaName)}</span></div>
        <div><span class="lbl">Size</span><b>${fmt(areaKm2(a))} km²</b></div>
        <div><span class="lbl">Centre</span><span class="mono small">${((a[1] + a[3]) / 2).toFixed(3)}°N ${((a[0] + a[2]) / 2).toFixed(3)}°E</span></div>
        <div><span class="lbl">Corners</span><span class="mono small">${a.map((v) => v.toFixed(2)).join(", ")}</span></div>
      </div>` : `<p class="hint">Search for a town or river, or just click anywhere on the globe.</p>`}
    <div class="sizes"><span class="lbl">Area size</span>
      <div class="seg" role="group" aria-label="Area size">${[10, 20, 25].map((k) => `<button data-km="${k}" aria-pressed="${S.boxKm === k}">${k} km</button>`).join("")}</div></div>
    <button class="btn primary" id="toCheck" ${a ? "" : "disabled"}>Check the data</button>
  </aside>`);
  // presets
  if (!demoAreas.length) { try { demoAreas = await api("/demo-areas"); } catch (_) { demoAreas = []; } }
  $("#presets").innerHTML = demoAreas.map((d, i) => `<button class="btn small" data-preset="${i}">${esc(d.name)}</button>`).join("") || '<span class="hint">No demo areas configured.</span>';
  $$("#presets [data-preset]").forEach((b) => b.onclick = () => { const d = demoAreas[+b.dataset.preset]; setArea(d.bbox, d.name, d.event_date); });
  $$(".sizes [data-km]").forEach((b) => b.onclick = () => { S.boxKm = +b.dataset.km; if (S.area) setAreaFromCenter((S.area[0] + S.area[2]) / 2, (S.area[1] + S.area[3]) / 2, S.areaName); else renderFind(); });
  $("#searchForm").onsubmit = async (e) => {
    e.preventDefault();
    const q = $("#q").value.trim(); if (q.length < 2) return;
    $("#results").innerHTML = '<li class="hint">Searching…</li>';
    try {
      const list = await api("/places?q=" + encodeURIComponent(q));
      $("#results").innerHTML = list.length ? list.map((p, i) => `<li><button data-i="${i}"><span>${esc(p.name.split(",")[0])}</span><small>${esc(p.name.split(",").slice(1, 4).join(","))}</small></button></li>`).join("") : '<li class="hint">No places found. Try a nearby town.</li>';
      $$("#results [data-i]").forEach((b) => b.onclick = () => { const p = list[+b.dataset.i]; setAreaFromCenter(p.lon, p.lat, p.name.split(",").slice(0, 2).join(",")); });
    } catch (err) { $("#results").innerHTML = `<li class="hint">${esc(err.message)}</li>`; }
  };
  const tc = $("#toCheck"); if (tc) tc.onclick = () => go("check");
}

// ================================================================ 02 CHECK DATA
async function renderCheck() {
  setProgress(2); setNav("find");
  if (!S.area) return go("find");
  ui(`
  <aside class="side right frame" aria-label="Check data" style="width:420px">
    <div class="screenhead"><div><h1>Is there enough data?</h1><small>${esc(S.areaName)}</small></div></div>
    <div id="checkBody"><div class="skeleton" style="height:70px"></div><div class="skeleton" style="height:120px;margin-top:12px"></div><p class="hint">Looking this place up…</p></div>
  </aside>
  <div class="timelinebar frame" id="tlbar" hidden><div class="lbl">Satellite images of this place</div><div id="timeline"></div></div>`);
  try {
    S.avail = await api("/availability", { method: "POST", body: JSON.stringify({ bbox: S.area }) });
  } catch (err) { return renderError(err, "check"); }
  const A = S.avail, bt = A.best_track || {};
  const q = {}; (bt.quality || []).forEach((x) => q[x] = 0);
  const kind = A.enough_data ? "ok" : A.total_passes ? "no" : "bad";
  if (A.newest_pass) 
  $("#checkBody").innerHTML = `
    <div class="verdict ${kind}">
      <div><strong>${A.enough_data ? "Yes, we can look at this place" : A.total_passes ? "Not quite enough yet" : "Nothing here yet"}</strong><div class="hint">${A.enough_data ? "There are enough satellite images to show you what changed." : "There aren’t enough satellite images here yet, and we’d rather wait than guess."}</div></div></div>
    <div class="statgrid" style="margin-top:14px">
      <div><span class="lbl">Satellite images</span><b>${A.total_passes}</b></div>
      <div><span class="lbl">Most recent</span><b>${esc(A.newest_pass ? dshort(A.newest_pass) : "–")}</b></div>
    </div>
    <div class="lbl" style="margin-top:12px">What you can ask here</div>
    <ul class="cando" style="margin-top:8px">
      ${[["now", "What is here now?"], ["change", "What changed around a date?"], ["much", "How much changed?"], ["why", "Why did it change?"], ["diff", "Compare two dates"]]
        .map(([k, l]) => `<li class="${A.can_answer[k] ? "" : "off"}">${l}</li>`).join("")}
    </ul>
    <div id="dlCheck" style="margin-top:14px"><div class="skeleton" style="height:64px"></div></div>
    <div class="row" style="margin-top:16px">
      <button class="btn" id="backFind">Change area</button>
      <button class="btn primary" id="toAsk" ${A.can_answer.change ? "" : "disabled"}>Ask a question</button>
    </div>`;
  if (!A.total_passes) {
    $("#checkBody").insertAdjacentHTML("beforeend", `<div class="frame state" style="margin-top:12px"><b>Nothing here yet</b><span class="hint">Try somewhere nearby, or keep an eye on this place and we’ll let you know when there’s something to see.</span><button class="btn" id="watchEmpty">Watch this place</button></div>`);
    $("#watchEmpty").onclick = addWatch;
  }
  if (A.total_passes) loadDlBlock("#dlCheck", "all"); else $("#dlCheck").innerHTML = "";
  setupScrollHint();
  $("#backFind").onclick = () => go("find");
  const ta = $("#toAsk"); if (ta) ta.onclick = () => go("ask");
  if (bt.dates && bt.dates.length) { $("#tlbar").hidden = false; $("#timeline").innerHTML = timelineSVG(bt.dates, { quality: bt.quality }); }
}

// pass timeline (shared): dates on a Jun-Nov axis, gap hatched, optional event marker / bars
function timelineSVG(dates, o = {}) {
  const t0 = Date.parse(NISAR_START + "T00:00:00Z"), last = Math.max(Date.parse("2026-11-20"), ...dates.map((d) => Date.parse(d)));
  const W = 1300, x0 = 40, x1 = W - 20, X = (d) => x0 + (Date.parse(d) - t0) / (last - t0) * (x1 - x0);
  let s = `<svg viewBox="0 ${o.bars ? 0 : -10} ${W} ${o.bars ? 150 : 106}" role="img" aria-label="Satellite images from June to November 2026${o.event ? ", change date " + o.event : ""}"><defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="#566070" stroke-width="2"/></pattern></defs>`;
  const base = o.bars ? 108 : 46;
  s += `<rect x="${X(GAP[0])}" y="${base - 18}" width="${X(GAP[1]) - X(GAP[0])}" height="36" fill="url(#hatch)" opacity=".8"/><text x="${(X(GAP[0]) + X(GAP[1])) / 2}" y="${base + 32}" text-anchor="middle" font-family="Inter" font-size="10" fill="#566070">no data</text>`;
  s += `<line x1="${x0}" y1="${base}" x2="${x1}" y2="${base}" stroke="#3B4A60"/>`;
  ["2026-07-01", "2026-08-01", "2026-09-01", "2026-10-01", "2026-11-01"].forEach((m) => s += `<text x="${X(m)}" y="${base + 20}" text-anchor="middle" font-family="Inter" font-size="10" fill="#566070">${MONTHS[+m.slice(5, 7) - 1]}</text>`);
  s += `<text x="${x0}" y="${base + 20}" font-family="Inter" font-size="10" fill="#566070">JUN</text>`;
  if (o.bars) {
    const mx = Math.max(1, ...o.bars.map((b) => b.v));
    o.bars.forEach((b) => { const h = 70 * b.v / mx; s += `<rect x="${X(b.d) - 10}" y="${base - 14 - h}" width="20" height="${h}" fill="${b.after ? "#1D4ED8" : "#60A5FA"}"/><text x="${X(b.d)}" y="${base - 18 - h}" text-anchor="middle" font-family="Inter" font-size="10" fill="#9AA4B2">${fmt(b.v)}</text>`; });
  }
  dates.forEach((d) => {
    const used = o.used ? o.used.includes(d) : true;
    const sel = o.event && d >= o.event;
    s += `<g ${o.clickable ? `class="passpick" data-d="${d}" style="cursor:pointer"` : ""}><circle cx="${X(d)}" cy="${base}" r="${used ? 6 : 4}" fill="${sel && used ? "#7DD3FC" : "#05080D"}" stroke="${used ? "#7DD3FC" : "#566070"}" stroke-width="1.5"/>${o.clickable ? `<rect x="${X(d) - 12}" y="${base - 14}" width="24" height="28" fill="transparent"/>` : ""}<text x="${X(d)}" y="${base - 12}" text-anchor="middle" font-family="Inter" font-size="9.5" fill="#9AA4B2">${dshort(d)}</text></g>`;
  });
  if (o.event) { const x = X(o.event); s += `<line x1="${x}" y1="${base - 42}" x2="${x}" y2="${base + 10}" stroke="#FBBF24" stroke-dasharray="4 4"/><text x="${x + 4}" y="${base - 34}" font-family="Inter" font-size="10" fill="#FCD34D">change date ${dshort(o.event)}</text>`; }
  return s + "</svg>";
}

// ================================================================ 03 ASK
function renderAsk() {
  setProgress(3); setNav("find");
  if (!S.avail) return go("check");
  const dates = (S.avail.best_track || {}).dates || [];
  if (!S.eventDate) S.eventDate = dates[Math.floor(dates.length / 2)] || "2026-09-01";
  const Q = [["now", "What is here now?", "the latest view"], ["diff", "Compare two dates", "what’s different between them"],
             ["change", "What changed?", "before vs after a date"], ["why", "Why did it change?", "likely causes, with evidence"],
             ["much", "How much changed?", "area in hectares and pitches"]];
  ui(`
  <aside class="side left frame" style="width:440px" aria-label="Ask a question">
    <div class="screenhead"><div><h1>What would you like to know?</h1><small>${esc(S.areaName)}</small></div></div>
    <div class="tiles" role="radiogroup" aria-label="Question">
      ${Q.map(([k, t, d]) => `<button class="tile" role="radio" data-q="${k}" aria-checked="${S.question === k}" ${S.avail.can_answer[k] ? "" : "disabled"}><b>${t}</b><span>${d}</span></button>`).join("")}
    </div>
    <div class="lbl">What to look for</div>
    <div class="chips" role="group" aria-label="Looking for">
      <button class="kchip" aria-checked="true" disabled>Water and floods <em>COMPARED WITH OPERA ON ONE SITE</em></button>
      <button class="kchip" aria-checked="false" disabled title="Roadmap">Vegetation loss <em>SOON</em></button>
      <button class="kchip" aria-checked="false" disabled title="Roadmap">New buildings <em>SOON</em></button>
      <button class="kchip" aria-checked="false" disabled title="Roadmap">Ground movement <em>SOON</em></button>
    </div>
    <div class="lbl">Or ask in your own words</div>
    <label class="field"><span class="sr">Type a question</span><input id="freeQ" placeholder="For example: how much land flooded after 7 September?"></label>
    <div id="dlAsk2"></div>
    <label class="row hint" style="font-size:13px"><input type="checkbox" id="quick" ${S.quick ? "checked" : ""}> Quick preview (less detail, but faster)</label>
    <div class="row">
      <button class="btn" id="backCheck">Back</button>
      <button class="btn primary" id="run">Show me what changed</button>
    </div>
  </aside>
  <div class="timelinebar frame">
    <div class="row" style="justify-content:space-between"><div class="lbl">Pick a date just after the event you’re curious about</div><div class="lbl" id="evLbl"></div></div>
    <div id="timeline"></div>
  </div>`);
  const drawTL = () => {
    $("#timeline").innerHTML = timelineSVG(dates, { event: S.eventDate, clickable: true });
    const b = dates.filter((d) => d < S.eventDate).length, a = dates.length - b;
    $("#evLbl").textContent = "";
    $$(".passpick").forEach((g) => g.onclick = () => { S.eventDate = g.dataset.d; drawTL(); });
    clearTimeout(drawTL.t); drawTL.t = setTimeout(() => loadDlBlock("#dlAsk2", "question", S.eventDate), 350);
  };
  drawTL();
  $$(".tile").forEach((t) => t.onclick = () => { S.question = t.dataset.q; $$(".tile").forEach((x) => x.setAttribute("aria-checked", x === t)); });
  $("#freeQ").oninput = (e) => {
    const v = e.target.value.toLowerCase();
    const k = /why|cause/.test(v) ? "why" : /how much|area|hectare/.test(v) ? "much" : /now|today/.test(v) ? "now" : /compare|differ/.test(v) ? "diff" : "change";
    const m = v.match(/(\d{1,2})\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/);
    if (m) { const mm = MONTHS.findIndex((x) => x.toLowerCase() === m[2]) + 1; S.eventDate = `2026-${String(mm).padStart(2, "0")}-${String(m[1]).padStart(2, "0")}`; drawTL(); }
    S.question = S.avail.can_answer[k] ? k : "change";
    $$(".tile").forEach((x) => x.setAttribute("aria-checked", x.dataset.q === S.question));
  };
  $("#quick").onchange = (e) => (S.quick = e.target.checked);
  $("#backCheck").onclick = () => go("check");
  $("#run").onclick = startRun;
}

async function startRun() {
  const body = { bbox: S.area, name: S.areaName, question: S.question === "now" || S.question === "diff" ? "change" : S.question,
                 event_date: S.eventDate, looking_for: S.looking, quick: S.quick };
  try {
    const j = await api("/analyses", { method: "POST", body: JSON.stringify(body) });
    S.jobId = j.id; S.result = null;
    go("analysing");
  } catch (err) { renderError(err, "ask"); }
}

// ================================================================ 04a ANALYSING
const STEP_IDS = ["check", "fetch", "prepare", "detect", "verify", "explain"];
const STEP_LABELS = ["Finding satellite images", "Getting your area", "Getting the images ready",
                     "Looking for changes", "Double-checking", "Putting the answer together"];
function renderAnalysing() {
  setProgress(4); setNav("find");
  ui(`
  <div class="sweep" aria-hidden="true"></div>
  <aside class="side right frame" style="width:420px" aria-label="Analysing" aria-live="polite">
    <div class="screenhead"><div><h1>Working on it</h1><small>${esc(S.areaName)}, around ${dshort(S.eventDate)}</small></div></div>
    <div class="pct"><span id="pct">0</span><small style="font-size:20px;color:var(--muted)">%</small></div>
    <div class="segbar" id="segbar">${STEP_IDS.map(() => "<i></i>").join("")}</div>
    <div class="dlrun" id="dlrun" hidden></div>
    <ol class="steps" id="steps">${STEP_LABELS.map((l, i) => `<li data-s="${STEP_IDS[i]}"><i></i>${l}</li>`).join("")}</ol>
    
    <div class="row"><button class="btn" id="keep">Keep exploring meanwhile</button></div>
  </aside>`);
  $("#keep").onclick = () => { toast("Still working in the background. Come back any time."); go("find"); };
  pollJob();
}
async function pollJob() {
  const id = S.jobId; if (!id) return;
  let j;
  try { j = await api("/analyses/" + id); } catch (err) { if (S.screen === "analysing") renderError(err, "analysing"); return; }
  if (S.screen === "analysing" && $("#pct")) {
    $("#pct").textContent = j.progress || 0;
    const cur = STEP_IDS.indexOf(j.step);
    $$("#steps li").forEach((li, i) => { li.className = (j.status === "done" || i < cur) ? "done" : i === cur ? "active" : ""; });
    $$("#segbar i").forEach((b, i) => b.classList.toggle("on", j.status === "done" || i < cur));
    const d = j.download, box = $("#dlrun");
    if (d && j.step === "fetch" && d.frames_total > 0) {
      box.hidden = false;
      box.innerHTML = `<span class="lbl" style="color:var(--cyan)">Getting satellite images · ${Math.round(d.pct)}%</span>
        <div class="bar"><span style="width:${d.pct}%"></span></div>
        <span><b>${fmtDur(d.eta_s)}</b> to go</span>`;
    } else if (d && j.step === "fetch" && d.frames_total === 0) {
      box.hidden = true;
    } else if (j.step !== "fetch") box.hidden = true;
  }
  if (j.status === "done") { S.result = j.result; S.resultKey = j.result.id; history.replaceState(null, "", "?r=" + j.result.id); return go("answer"); }
  if (j.status === "not_enough_data") return renderNotEnough(j.error, j.detail);
  if (j.status === "failed") return renderError(new Error(j.error || "The analysis failed."), "ask");
  if (S.screen === "analysing" && $("#log")) {
    const line = `${new Date().toLocaleTimeString()}  ${STEP_LABELS[STEP_IDS.indexOf(j.step)] || "Waiting to start"} · ${j.progress || 0}%`;
    if ($("#log").dataset.last !== line.slice(9)) { $("#log").insertAdjacentHTML("beforeend", `<div>${esc(line)}</div>`); $("#log").dataset.last = line.slice(9); $("#log").scrollTop = 1e6; }
  }
  setTimeout(pollJob, 1500);
}


// ---------------------------------------------------------------- plain-words explanation of a result
const ICON = (() => {
  const w = (d) => `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#7DD3FC" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
  return { water: w('<path d="M2 9c3-2 5 2 8 0s5-2 8 0 4 0 4 0M2 15c3-2 5 2 8 0s5-2 8 0 4 0 4 0"/>'),
    map: w('<path d="M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3z"/><path d="M9 3v15M15 6v15"/>'),
    radar: w('<circle cx="12" cy="12" r="2"/><path d="M7 12a5 5 0 0 1 5-5M3 12a9 9 0 0 1 9-9M17 12a5 5 0 0 1-5 5M21 12a9 9 0 0 1-9 9"/>'),
    check: w('<path d="M4 12l5 5L20 6"/>'), why: w('<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5V14M12 17.5v.01"/>').replace('#7DD3FC', '#FCD34D'),
    warn: w('<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.01"/>') };
})();
function plainStory(R) {
  const h = R.headline, A = R.areas_ha, ag = R.agreement || {}, c = R.confidence;
  const b = R.window.before.at(-1), a = R.window.after[0], days = Math.round((Date.parse(a) - Date.parse(b)) / 864e5);
  const place = R.area.name;
  const D = (d) => dshort(d);
  let lead, what;
  if (h.label === "No clear change") {
    lead = `No clear change in ${place} between ${D(b)} and ${D(a)}.`;
    what = `We found <b>no large area that turned into water or dried out</b> between these dates.`;
  } else if (h.label === "Water likely receded") {
    lead = `Water drained away from about ${fmt(h.hectares)} hectares of ${place}.`;
    what = `Between <b>${D(b)} and ${D(a)}</b> (${days} days), about <b>${fmt(A.water_receded)} hectares</b> that were under water became dry land again. That is roughly <b>${fmt(Math.round(A.water_receded / 0.714))} football pitches</b>.`;
  } else {
    lead = `About ${fmt(h.hectares)} hectares of land in ${place} went under water.`;
    what = `Between <b>${D(b)} and ${D(a)}</b> (${days} days), about <b>${fmt(A.became_water)} hectares</b> of dry land turned into water: roughly <b>${fmt(h.football_pitches)} football pitches</b>, or ${h.share_of_area_pct}% of the area you picked. On the picture it is painted <b>dark blue</b>.`;
  }
  const items = [[ICON.water, "What changed", what]];
  const other = [];
  if (A.permanent_water > 0) other.push(`The river and lakes that were already there (${fmt(A.permanent_water)} ha) are shown in black and are <b>not</b> counted as new.`);
  if (h.label !== "Water likely receded" && A.water_receded > 0) other.push(`In other spots about ${fmt(A.water_receded)} ha of water went down (light blue).`);
  if (other.length) items.push([ICON.map, "What else is on the map", other.join(" ")]);
  const sure = { High: "We are fairly sure.", Medium: "We are moderately sure.", Lower: "Treat this with caution." }[c.level] || "";
  const opera = ag.verdict ? ` NASA's separate water map (OPERA, from a different satellite) shows water on <b>${fmt(ag.overlap_pct)}%</b> of the area we mark as new water on the later date. It does not tell us whether that water is new.` : " We could not compare it with NASA's separate water map for these dates.";
  items.push([ICON.check, "HOW SURE WE ARE", `<b>${sure}</b> ${esc(c.reason)}${opera}`]);
  const D2 = (R.drivers || []).filter((d) => d.verdict === "Likely" || d.verdict === "Possible");
  items.push([ICON.why, "Why it probably happened", D2.length
    ? `Most likely cause: <b>${esc(D2.map((d) => d.name).join(" + "))}</b>. ${esc(D2[0].evidence)} This is our best explanation, not a certainty.`
    : `We looked at rain, rivers, land height, earthquakes and fires, but nothing clearly explains it yet.`, "interp"]);
  items.push([ICON.warn, "Worth keeping in mind", `This is an estimate, <b>not an official flood warning</b>. For safety decisions, please follow your local authorities. Tap <b>Watch this place</b> to hear when there’s an update.`]);
  return { lead, items };
}
function plainStoryHTML(R) {
  const st = plainStory(R);
  return `<section class="frame plain" aria-label="What happened here, in plain words">
    <div class="lead">${esc(st.lead)}<small>What happened here, in plain words</small></div>
    <ol>${st.items.map(([ic, t, body, cls]) => `<li class="${cls || ""}"><span class="ic" aria-hidden="true">${ic}</span><div><em>${t}</em>${body}</div></li>`).join("")}</ol>
  </section>`;
}

// ================================================================ 04b ANSWER
function renderAnswer() {
  setProgress(4); setNav("find");
  const R = S.result; if (!R) return go("find");
  const h = R.headline, c = R.confidence, ag = R.agreement || {}, I = R.images;
  const confCls = c.level === "High" ? "green" : c.level === "Medium" ? "amber" : "red";
  const qual = [...new Set(R.passes.filter((p) => p.used).map((p) => p.quality))].join(" / ");
  const A = R.areas_ha, maxT = Math.max(A.became_water, A.water_receded, A.permanent_water, 1);
  const hb = (l, v, m, st) => `<div class="hbar"><span>${l}</span><span class="track"><span style="width:${100 * (v || 0) / m}%;${st}"></span></span><b>${v === null || v === undefined ? "–" : fmt(v)}</b></div>`;
  const wb = R.water_ha.before, wa = R.water_ha.after, maxW = Math.max(wb, wa, 1);
  const maxS = Math.max(ag.nisar_water_ha || 0, ag.opera_water_ha || 0, h.hectares, 1);
  const bLast = R.window.before.at(-1), aFirst = R.window.after[0];
  const ratio = wb > 0 ? wa / wb : null;
  ui(`<div class="page answer">
  <div class="answerhead">
    <div><h1>What changed in ${esc(R.area.name)}?</h1><small class="small muted">${dshort(bLast)} to ${dshort(aFirst)} 2026${R.source === "sample" ? " · example data" : ""}</small></div>
    <div class="row" style="margin-left:auto">
      <button class="btn small" id="watchBtn">Watch this place</button>
      <button class="btn small" id="shareBtn">Share</button>
      <button class="btn small primary" id="reportBtn">Save as PDF</button>
    </div>
  </div>
  <div class="ansgrid">
  <section class="viewer frame" aria-label="Before and after radar images">
    <div class="viewtabs" role="group" aria-label="How to show the images">
      ${[["swipe", "Before / after"], ["change", "Change only"], ["lapse", "Time-lapse"], ["photo", "Photo"]].map(([k, l]) => `<button data-view="${k}" aria-pressed="${S.view === k}">${l}</button>`).join("")}
      <div class="seg" role="group" aria-label="Radar polarization"><span class="lbl" style="padding:0 10px">Show</span>
        ${[["hh", "Water"], ["hv", "Plants"], ["mix", "Colours"]].map(([k, l]) => `<button data-pol="${k}" aria-pressed="${S.pol === k}" ${I[k] ? "" : "disabled"}>${l}</button>`).join("")}</div>
    </div>
    <div class="vmap" id="vBefore"></div><div class="vmap" id="vAfter"></div>
    <div class="swipe" id="swipe"><button aria-label="Drag or use arrow keys to compare before and after">‹ ›</button></div>
    <span class="chip mono vlabel" id="lblB" style="left:12px">Before · ${dshort(bLast)}</span>
    <span class="chip mono cyan vlabel" id="lblA" style="right:12px">After · ${dshort(aFirst)}</span>
    <div class="polnote" id="polnote" style="left:50%;top:50px;transform:translateX(-50%)"></div>
    <div class="legend" id="legend">
      <span><i style="background:#1D4ED8"></i>Likely became water</span><span><i style="background:#60A5FA"></i>Water likely receded</span>
      <span><i style="background:#0A0C10;border:1px solid #566070"></i>River (always water)</span><span><i style="background:#9CA3AF;opacity:.5"></i>Could not read</span>
    </div>
  </section>
  <aside class="answercard frame" aria-label="The answer">
    <div class="row"><span class="chip ${confCls}"><span class="dot"></span>${esc(c.level)} confidence</span></div>
    <div><div class="small" style="color:#93C5FD;font-weight:600">${esc(h.label)}</div>
      <div class="bignum">${fmt(h.hectares)}<small>hectares</small></div>
      <div style="color:var(--soft);font-size:17px">${h.label === "No clear change" ? "Nothing much changed between these dates." : `${h.label === "Water likely receded" ? "dried out" : "went under water"} in ${Math.round((Date.parse(aFirst) - Date.parse(bLast)) / 864e5)} days, between ${dshort(bLast)} and ${dshort(aFirst)}`}</div></div>
    <div class="pitch"><svg width="34" height="22" viewBox="0 0 36 24" fill="none" stroke="#E6EDF3" stroke-width="1.4" aria-hidden="true"><rect x="1" y="1" width="34" height="22"/><path d="M18 1v22"/><circle cx="18" cy="12" r="4"/></svg>
      <span>About <b>${fmt(h.football_pitches)} football pitches</b>, or ${h.share_of_area_pct}% of the study area</span></div>
    <p class="hint">${esc(c.reason)}${ag.overlap_pct !== undefined && ag.overlap_pct !== null ? ` Also water in NASA's OPERA map: ${fmt(ag.overlap_pct)}% of the new-water area.` : ""}</p>
    ${validationHTML(R)}
    <div class="mi"><div><div class="lbl">MEASURED</div>${esc(R.measured)}</div><div><div class="lbl">WHAT IT LIKELY MEANS</div>${esc(R.interpreted)}</div></div>
    <div class="row" style="margin-top:auto;gap:18px">
      <button class="linkbtn" data-go="why">WHY DID IT CHANGE? ›</button>
      <button class="linkbtn" data-go="evidence">HOW WE KNOW THIS ›</button>
    </div>
  </aside>
  </div>
  ${plainStoryHTML(R)}
  <section class="frame chartframe">
    <h3>How the water changed over time (hectares)
      <span class="keys"><span><i style="background:#1D4ED8"></i>Water spreading</span><span><i style="background:#60A5FA"></i>Water going down</span></span></h3>
    <div id="passChart"></div>
  </section>
  <div class="grid3">
    <section class="frame chartframe">${corners}<h3>CHART 1 · CHANGE BY TYPE (HA)</h3>
      ${hb("Became water", A.became_water, maxT, "background:#1D4ED8")}${hb("Water receded", A.water_receded, maxT, "background:#60A5FA")}${hb("River (always)", A.permanent_water, maxT, "background:#334155")}
      <span class="hint small">Vegetation loss and new buildings are on our roadmap; only water has been checked at all.</span></section>
    <section class="frame chartframe">${corners}<h3>CHART 3 · WATER IN THE AREA (HA)</h3>
      <div class="vbars"><div>${fmt(wb)}<i style="height:${100 * wb / maxW}%;background:#60A5FA"></i></div><div>${fmt(wa)}<i style="height:${100 * wa / maxW}%;background:#1D4ED8"></i></div></div>
      <div class="vbars-x"><span>${dshort(bLast)}</span><span>${dshort(aFirst)}</span></div>
      <span class="hint small">${ratio && ratio > 1.15 ? `${ratio.toFixed(1)} times more water in ${Math.round((Date.parse(aFirst) - Date.parse(bLast)) / 864e5)} days.` : ratio && ratio < 0.87 ? "Less water after than before." : "About the same water before and after."}</span></section>
    <section class="frame chartframe">${corners}<h3>CHART 4 · FLOODED AREA BY SOURCE (HA)</h3>
      ${hb("NISAR (ours)", ag.nisar_water_ha ?? h.hectares, maxS, "background:#1D4ED8")}${hb("NASA OPERA", ag.opera_water_ha, maxS, "background:#60A5FA")}
      <div class="hbar"><span class="muted">Normal photo</span><span class="track" style="background:repeating-linear-gradient(45deg,#1C2A3D 0 4px,transparent 4px 8px)"></span><b class="muted small">CLOUD</b></div>
      <span class="hint small">${ag.verdict ? `${fmt(ag.overlap_pct)}% of our new-water area is also water in OPERA.` : "NASA OPERA comparison not available for this date."}</span></section>
  </div>
  <div class="grid2" style="grid-template-columns:minmax(0,1fr) minmax(0,1.1fr)">
    <section class="frame chartframe">${corners}<h3>DO SOURCES AGREE? ${ag.verdict ? `<span class="chip ${vcode(ag) === "agrees" ? "green" : vcode(ag) === "partly" ? "amber" : "red"}" style="margin-left:auto"><span class="dot"></span>${esc(ag.verdict.toUpperCase())} · ${fmt(ag.overlap_pct)}% OVERLAP</span>` : ""}</h3>
      <div class="strip3">
        <figure><div class="tileimg"><img src="${abs(I.hh)}" alt="NISAR radar after"><img src="${abs(I.result)}" alt="Detected change"></div><figcaption>NISAR RADAR</figcaption></figure>
        <figure><div class="tileimg">${ag.map_url ? `<img src="${abs(ag.map_url)}" alt="Agreement with NASA OPERA">` : '<p class="hint small" style="padding:10px">Not available</p>'}</div><figcaption>NASA OPERA MAP</figcaption></figure>
        <figure><div class="tileimg"><img src="${esc(I.photo)}" alt="Normal satellite photo" onerror="this.replaceWith(Object.assign(document.createElement('p'),{className:'hint small',style:'padding:10px',textContent:'Photo not reachable'}))"></div><figcaption>PHOTO · CLOUD LIKELY</figcaption></figure>
      </div>
      <button class="linkbtn" data-go="sources">COMPARE THE SOURCES ›</button></section>
    <section class="frame chartframe assistant">${corners}<h3>💬 ASK ABOUT THIS RESULT</h3>
      <div class="msgs" id="msgs" aria-live="polite"><div class="msg">Ask me about this result. I only answer from its facts.</div></div>
      <div class="sugg" id="sugg">${["Could rain cause this instead of a flood?", "Do other sources agree?", "How sure are you?", "Play the time-lapse"].map((s) => `<button>${s}</button>`).join("")}</div>
      <form class="field" id="askForm"><label class="sr" for="askIn">Your question</label><input id="askIn" placeholder="Ask anything about this place"><button class="btn small">ASK</button></form>
    </section>
  </div>
  </div>`);
  $("#passChart").innerHTML = passChartSVG(R);
  $$("[data-go]").forEach((b) => b.onclick = () => go(b.dataset.go));
  $("#watchBtn").onclick = addWatch; $("#shareBtn").onclick = share; $("#reportBtn").onclick = printReport;
  $$(".viewtabs [data-view]").forEach((b) => b.onclick = () => setView(b.dataset.view));
  $$(".viewtabs [data-pol]").forEach((b) => b.onclick = () => { S.pol = b.dataset.pol; $$(".viewtabs [data-pol]").forEach((x) => x.setAttribute("aria-pressed", x === b)); if (S.view !== "swipe") setView("swipe"); else applyView(); });
  initAssistant();
  initViewer();
}
function setView(v) { S.view = v; $$(".viewtabs [data-view]").forEach((x) => x.setAttribute("aria-pressed", x.dataset.view === v)); applyView(); }

// Chart 2: signed change per pass above the pass timeline, with BEFORE / AFTER brackets
function passChartSVG(R) {
  const P = R.passes.map((p) => p.date), pp = {}; (R.per_pass || []).forEach((x) => pp[x.date] = x);
  const t0 = Date.parse(NISAR_START), t1 = Math.max(Date.parse("2026-11-20"), ...P.map((d) => Date.parse(d)));
  const W = 1320, x0 = 70, x1 = W - 30, X = (d) => x0 + (Date.parse(d) - t0) / (t1 - t0) * (x1 - x0);
  const ch = (R.per_pass || []).map((x) => x.change_ha).filter((v) => v !== null && v !== undefined);
  const mx = Math.max(1, ...ch.map(Math.abs)), zero = 100, H = 70;
  let s = `<svg viewBox="0 0 ${W} 250" role="img" aria-label="How the water changed over time"><defs><pattern id="hatch2" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="#3B4A60" stroke-width="2"/></pattern></defs>
    <line x1="${x0}" y1="${zero}" x2="${x1}" y2="${zero}" stroke="#3B4A60"/><text x="${x0 - 12}" y="${zero + 4}" text-anchor="end" font-family="Inter" font-size="10" fill="#9AA4B2">0</text>
    <text x="${x0 - 12}" y="${zero - H + 4}" text-anchor="end" font-family="Inter" font-size="10" fill="#9AA4B2">+${fmt(mx)}</text>`;
  const ty = 180;
  s += `<rect x="${X(GAP[0])}" y="${ty - 14}" width="${X(GAP[1]) - X(GAP[0])}" height="28" fill="url(#hatch2)"/><text x="${(X(GAP[0]) + X(GAP[1])) / 2}" y="${ty + 30}" text-anchor="middle" font-family="Inter" font-size="10" fill="#566070">no data</text>`;
  ["2026-07-01", "2026-08-01", "2026-09-01", "2026-10-01", "2026-11-01"].forEach((m) => s += `<text x="${X(m)}" y="${ty - 22}" text-anchor="middle" font-family="Inter" font-size="10" fill="#566070">${MONTHS[+m.slice(5, 7) - 1]}</text>`);
  R.passes.forEach((p) => {
    const x = X(p.date), q = pp[p.date], v = q && q.change_ha;
    if (v !== null && v !== undefined) {
      const hgt = Math.max(2, H * Math.abs(v) / mx), up = v >= 0;
      s += `<rect x="${x - 9}" y="${up ? zero - hgt : zero}" width="18" height="${hgt}" fill="${up ? "#1D4ED8" : "#60A5FA"}"/><text x="${x}" y="${up ? zero - hgt - 6 : zero + hgt + 13}" text-anchor="middle" font-family="Inter" font-size="10" fill="#CBD5E1">${up ? "+" : ""}${fmt(v)}</text>`;
    }
    const val = p.quality === "Validated";
    s += `<circle cx="${x}" cy="${ty}" r="6" fill="${val ? "#7DD3FC" : "#05080D"}" stroke="${p.used ? "#E6EDF3" : "#566070"}" stroke-width="1.5"/><text x="${x}" y="${ty + 22}" text-anchor="middle" font-family="Inter" font-size="9.5" fill="#9AA4B2">${dshort(p.date)}</text>`;
  });
  const br = (dates, label) => { if (!dates.length) return; const a = X(dates[0]) - 14, b = X(dates.at(-1)) + 14; s += `<path d="M${a} ${ty + 30} v6 H${b} v-6" fill="none" stroke="#7DD3FC"/><text x="${(a + b) / 2}" y="${ty + 52}" text-anchor="middle" font-family="Inter" font-size="10" fill="#7DD3FC">${label}</text>`; };
  br(R.window.before, "BEFORE"); br(R.window.after, "AFTER");
  return s + "</svg>";
}

const POL_NOTE = { hh: ["", "Water shows up dark."], hv: ["", "Plants and trees show up bright."], mix: ["", "Different surfaces in different colours."] };
let vB, vA, syncing = false;
function viewerStyle() {
  const st = JSON.parse(JSON.stringify(STYLE)); delete st.projection; delete st.sky;
  st.layers.find((l) => l.id === "osm").minzoom = 0; return st;
}
function initViewer() {
  const R = S.result, [w, s, e, n] = R.images.bounds;
  const coords = [[w, n], [e, n], [e, s], [w, s]];
  const opts = (c) => ({ container: c, style: viewerStyle(), bounds: [[w, s], [e, n]], fitBoundsOptions: { padding: 30 }, attributionControl: false });
  vB = new maplibregl.Map(opts("vBefore")); vA = new maplibregl.Map(opts("vAfter"));
  vA.addControl(new maplibregl.AttributionControl({ compact: true }));
  const sync = (src, dst) => src.on("move", () => { if (syncing) return; syncing = true; dst.jumpTo({ center: src.getCenter(), zoom: src.getZoom(), bearing: src.getBearing(), pitch: src.getPitch() }); syncing = false; });
  sync(vB, vA); sync(vA, vB);
  const mB = vB, mA = vA;
  const wait = () => { if (vA !== mA) return; if (mB.isStyleLoaded() && mA.isStyleLoaded()) { addImageLayers(coords); applyView(); } else setTimeout(wait, 120); };
  wait();
  // swipe drag
  const sw = $("#swipe"), viewer = $("#vAfter");
  const setX = (clientX) => { const r = viewer.getBoundingClientRect(); S.swipeX = Math.min(0.98, Math.max(0.02, (clientX - r.left) / r.width)); applySwipe(); };
  let drag = false;
  sw.addEventListener("pointerdown", (ev) => { drag = true; sw.setPointerCapture(ev.pointerId); });
  sw.addEventListener("pointermove", (ev) => drag && setX(ev.clientX));
  sw.addEventListener("pointerup", () => (drag = false));
  sw.querySelector("button").onkeydown = (ev) => { if (ev.key === "ArrowLeft") { S.swipeX = Math.max(0.02, S.swipeX - 0.05); applySwipe(); } if (ev.key === "ArrowRight") { S.swipeX = Math.min(0.98, S.swipeX + 0.05); applySwipe(); } };
}
function addImageLayers(coords) {
  const R = S.result, I = R.images;
  const add = (m, id, url, opacity = 1, before) => {
    if (!url) return;
    m.addSource(id, { type: "image", url: abs(url), coordinates: coords });
    m.addLayer({ id, type: "raster", source: id, paint: { "raster-opacity": opacity, "raster-fade-duration": 0 } }, before);
  };
  add(vB, "before", I.before_hh, 0.95);
  ["hh", "hv", "mix"].forEach((k) => add(vA, "after-" + k, I[k], 0.95));
  add(vA, "photo", I.photo, 1);
  (I.passes || []).forEach((p, i) => add(vA, "pass-" + i, p.url, 0.95));
  add(vA, "result", I.result, 0.9);

}
function setVis(m, id, on) { if (m.getLayer(id)) m.setLayoutProperty(id, "visibility", on ? "visible" : "none"); }
function applyView() {
  if (!vA || !vA.getLayer("result")) return;
  const R = S.result, I = R.images, v = S.view;
  stopLapse();
  ["hh", "hv", "mix"].forEach((k) => setVis(vA, "after-" + k, (v === "swipe") && S.pol === k));
  setVis(vA, "photo", v === "photo");
  (I.passes || []).forEach((_, i) => setVis(vA, "pass-" + i, false));
  setVis(vA, "result", v === "swipe" || v === "change");
  $("#vBefore").style.visibility = v === "swipe" ? "visible" : "hidden";
  $("#swipe").hidden = v !== "swipe"; $("#lblB").hidden = v !== "swipe";
  $("#legend").hidden = !(v === "swipe" || v === "change");
  const pn = $("#polnote");
  if (v === "swipe") { const [k, t] = POL_NOTE[S.pol]; pn.hidden = false; pn.innerHTML = t; $("#lblA").textContent = "After · " + dshort(R.window.after[0]); }
  else if (v === "change") { pn.hidden = false; pn.innerHTML = `Just the change, laid over the map.`; $("#lblA").textContent = "Change, " + dshort(R.window.before.at(-1)) + " to " + dshort(R.window.after[0]); }
  else if (v === "photo") { pn.hidden = false; pn.innerHTML = `An ordinary photo from ${dshort(R.window.after[0])}. Clouds often hide the ground.`; $("#lblA").textContent = "Photo"; }
  else if (v === "lapse") { pn.hidden = false; startLapse(); }
  applySwipe();
}
function applySwipe() {
  const el = $("#vAfter"), sw = $("#swipe");
  if (!el) return;
  if (S.view === "swipe") { const pct = S.swipeX * 100; el.style.clipPath = `inset(0 0 0 ${pct}%)`; sw.style.left = pct + "%"; }
  else el.style.clipPath = "none";
}
function startLapse() {
  const P = S.result.images.passes || []; if (!P.length) { $("#polnote").textContent = "No time-lapse for this place yet."; return; }
  let i = 0;
  const step = () => {
    P.forEach((_, k) => setVis(vA, "pass-" + k, k === i));
    $("#lblA").textContent = `${P[i].group === "before" ? "Before" : "After"} · ${dshort(P[i].date)}`;
    $("#polnote").innerHTML = `Pass ${i + 1} of ${P.length}`;
    i = (i + 1) % P.length;
  };
  step(); S.lapseTimer = setInterval(step, 1300);
}
function stopLapse() { if (S.lapseTimer) clearInterval(S.lapseTimer); S.lapseTimer = null; }

function chart(id, type, labels, data, colors, horizontal = false) {
  const el = document.getElementById(id); if (!el) return;
  Chart.defaults.color = "#9AA4B2"; Chart.defaults.font.family = "Inter"; Chart.defaults.font.size = 10;
  S.charts.push(new Chart(el, {
    type, data: { labels, datasets: [{ data, backgroundColor: colors, borderWidth: 0 }] },
    options: { indexAxis: horizontal ? "y" : "x", maintainAspectRatio: false, animation: { duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 700 },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => fmt(c.raw) + " ha" } } },
      scales: { x: { grid: { color: "#1C2A3D" }, ticks: { color: "#9AA4B2" } }, y: { grid: { color: horizontal ? "transparent" : "#1C2A3D" }, ticks: { color: "#CBD5E1" } } } },
  }));
}

// "Common questions": plain answers built from this result's own numbers (no chat, nothing made up)
function initAssistant() {
  $$("#faq details").forEach((d) => d.addEventListener("toggle", async () => {
    if (!d.open || d.dataset.done) return;
    d.dataset.done = "1";
    try {
      const a = await api(`/results/${S.result.id}/ask`, { method: "POST", body: JSON.stringify({ question: d.dataset.q }) });
      d.querySelector("p").textContent = a.answer;
    } catch (err) { d.querySelector("p").textContent = err.message; delete d.dataset.done; }
  }));
}

// ================================================================ 05 SOURCES
function pageHead(n, title, sub) {
  return `<div class="pagehead"><div><h1>${title}</h1><small class="small muted">${sub}</small></div>
    <button class="btn back" id="back">Back to the answer</button></div>`;
}
function renderSources() {
  setProgress(0); setNav("find");
  const R = S.result; if (!R) return go("find");
  const ag = R.agreement || {}, I = R.images;
  const ok = vcode(ag) === "agrees", part = vcode(ag) === "partly";
  const max = Math.max(ag.nisar_water_ha || 0, ag.opera_water_ha || 0, 1);
  const bar = (l, v, st) => `<div class="hbar"><span>${l}</span><span class="track"><span style="width:${100 * (v || 0) / max}%;${st}"></span></span><b>${fmt(v)}</b></div>`;
  ui(`<div class="page">${pageHead("05", "DO SOURCES AGREE?", `${esc(R.area.name.toUpperCase())} · ${dshort(R.window.after[0])} 2026 · TWO RADAR-BASED MAPS`)}
    ${ag.verdict ? `
    <section class="frame banner verdict ${ok ? "ok" : part ? "no" : "bad"}">${corners}
      <div><strong style="font:400 22px var(--disp)">${esc(ag.verdict.toUpperCase())}</strong><div class="hint">${ok ? "Two radar-based maps mark the same places as water." : part ? "Most of our new-water area is also water in OPERA; some is seen only by one map." : "The two maps see different amounts of water. Read why below."}</div></div>
      <div class="row" style="margin-left:auto;gap:32px">
        <div class="num"><span class="lbl">Overlap</span><b>${fmt(ag.overlap_pct)}%</b></div>
        <div class="num"><span class="lbl">NISAR saw</span><b>${fmt(ag.nisar_water_ha)} ha</b></div>
        <div class="num"><span class="lbl">NASA OPERA saw</span><b>${fmt(ag.opera_water_ha)} ha</b></div>
      </div></section>` : `<section class="frame state"><b>No NASA OPERA map to compare with</b><span class="hint">There’s no other map close to this date to compare with.</span></section>`}
    <div class="grid3">
      <figure class="frame">${corners}<div class="tileimg"><img src="${abs(I.hh)}" alt="NISAR radar after the change"><img src="${abs(I.result)}" alt="Detected change"><span class="chip cyan mono tag">${fmt(R.headline.hectares)} HA</span></div>
        <figcaption><b><span class="accent">01/</span> NISAR RADAR</b><span class="lbl">${dshort(R.window.after[0])} 2026 · L-BAND · OUR RESULT</span>Sees through cloud and at night.</figcaption></figure>
      <figure class="frame">${corners}<div class="tileimg">${ag.map_url ? `<img src="${abs(ag.map_url)}" alt="Agreement map: blue both, light blue only NISAR, amber only OPERA">` : ""}<span class="chip mono tag">${ag.opera_water_ha ? fmt(ag.opera_water_ha) + " HA" : "–"}</span></div>
        <figcaption><b><span class="accent">02/</span> AGREEMENT WITH NASA OPERA</b><span class="lbl">SENTINEL-1 · SEPARATE NASA PRODUCT</span>
          <span class="row small"><span><i style="display:inline-block;width:12px;height:10px;background:#1D4ED8"></i> both</span><span><i style="display:inline-block;width:12px;height:10px;background:#93C5FD"></i> only NISAR</span><span><i style="display:inline-block;width:12px;height:10px;background:#F59E0B"></i> only OPERA</span></span></figcaption></figure>
      <figure class="frame"><div class="tileimg"><img src="${esc(I.photo)}" alt="Normal satellite photo from NASA Worldview, likely cloudy" onerror="this.replaceWith(Object.assign(document.createElement('p'),{className:'hint',style:'padding:20px',textContent:'Photo not reachable right now.'}))"><span class="chip tag">Photo</span></div>
        <figcaption><b>Ordinary photo</b><span class="lbl">NASA Worldview · ${dshort(R.window.after[0])}</span></figcaption></figure>
    </div>
    ${ag.verdict ? `<div>
      <section class="frame" style="padding:18px;display:flex;flex-direction:column;gap:14px"><h3>Water seen by each source (hectares)</h3>
        ${bar("NISAR (ours)", ag.nisar_water_ha, "background:#1D4ED8")}${bar("NASA OPERA", ag.opera_water_ha, "background:#60A5FA")}${bar("Both agree", ag.both_ha, "background:repeating-linear-gradient(90deg,#7DD3FC 0 2px,transparent 2px 5px);border:1px solid #7DD3FC")}
</section>
    </div>` : ""}</div>`);
  $("#back").onclick = () => go("answer");
}

// ================================================================ 06 HOW WE KNOW
function renderEvidence() {
  setProgress(0); setNav("evidence");
  const R = S.result, P = R ? R.provenance : null, acc = R && R.accuracy, ag = R && R.agreement || {};
  const stat = (l, v, note) => `<div class="frame card">${corners}<span class="lbl">${l}</span><b class="big">${v}</b><span class="hint">${note}</span></div>`;
  ui(`<div class="page">${pageHead("06", "HOW WE KNOW THIS", R ? `${esc(R.area.name.toUpperCase())} · METHOD ${esc(P.method)}` : "THE METHOD")}
    ${R ? `<div class="grid3">
      ${stat("PRECISION", acc ? acc.precision_pct + "%" : "–", acc ? `When we say "water", we are right ${acc.precision_pct} times in 100.` : "Not scored yet: needs hand-checked points.")}
      ${stat("RECALL", acc ? acc.recall_pct + "%" : "–", acc ? `We find ${acc.recall_pct} of every 100 truly flooded places.` : "Not scored yet.")}
      ${stat("OVERLAP WITH NASA OPERA", ag.overlap_pct !== undefined ? fmt(ag.overlap_pct) + "%" : "–", "Share of our new-water area that is also water in OPERA on the later date. It does not tell us the water is new.")}
    </div>` : ""}
    <div class="grid2">
      <section class="frame" style="padding:18px;display:flex;flex-direction:column;gap:12px">${corners}<h3>CHECK OF HAND-LABELLED POINTS</h3>
        ${acc ? `<div class="matrix"><span></span><span>REALLY WATER</span><span>REALLY DRY</span>
          <span>WE SAID WATER</span><div style="background:rgba(29,78,216,.28);border-color:#1D4ED8"><b style="color:#93C5FD">${acc.tp}</b><span class="lbl">CORRECT</span></div><div><b style="color:#F87171">${acc.fp}</b><span class="lbl">FALSE ALARM</span></div>
          <span>WE SAID DRY</span><div><b style="color:#FBBF24">${acc.fn}</b><span class="lbl">MISSED</span></div><div><b>${acc.tn}</b><span class="lbl">CORRECT</span></div></div>`
          : `<p class="hint">No check points scored for this result yet. Run <span class="mono">make_checkpoints.py</span> and <span class="mono">score.py</span>.</p>`}
      </section>
      <section class="frame" style="padding:18px;display:flex;flex-direction:column;gap:14px">${corners}<h3>METHOD · SIX STEPS</h3>
        <div class="pipeline">${[["CHECK", "2 passes before + 2 after, one track"], ["FETCH", "read only the area"], ["PREPARE", "20 m grid, Lee filter"], ["DETECT", "dark in HH and HV, 3 dB"], ["VERIFY", "NASA OPERA"], ["EXPLAIN", "answer, causes, limits"]]
          .map(([t, s], i) => `<div><em><span>0${i + 1}</span></em><b>${t}</b>${s}</div>`).join("")}</div>
        <p class="hint small">No black-box AI decides the answer: every step is a published radar technique.</p></section>
    </div>
    ${R ? `<div class="grid2">
      <section class="frame" style="padding:18px;display:flex;flex-direction:column;gap:12px"><h3>What could be wrong</h3>
        <ul class="list">${R.limits.map((l) => `<li><span>${esc(l)}</span></li>`).join("")}</ul>
</section>
      <section class="frame" style="padding:18px;display:flex;flex-direction:column;gap:12px"><h3>Data we used</h3>
        <table class="datatable"><tbody>
          <tr><td>NASA–ISRO NISAR satellite images</td></tr>
          ${(R.credits && R.credits.sources || []).map((s) => `<tr><td><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a></td></tr>`).join("")}
        </tbody></table>${R.credits && R.credits.notice ? `<p class="hint small">${esc(R.credits.notice)}</p>` : ""}</section>
    </div>` : `<section class="frame state"><b>Run an analysis to see the evidence behind it</b><button class="btn primary" id="startFind">Find a place</button></section>`}
    <section class="frame" style="padding:18px"><h3>Want to learn more?</h3><ul class="list" id="learn" style="margin-top:10px"></ul></section>
  </div>`);
  const back = $("#back"); if (back) { back.onclick = () => go(R ? "answer" : "find"); if (!R) back.textContent = "Back"; }
  const sf = $("#startFind"); if (sf) sf.onclick = () => go("find");
  api("/learn?tag=learn").then((L) => { $("#learn").innerHTML = L.resources.map((r) => `<li><span><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a></span></li>`).join(""); }).catch(() => {});
}

// ================================================================ 07 WHY
function renderWhy() {
  setProgress(0); setNav("find");
  const R = S.result; if (!R) return go("find");
  const D = R.drivers || [], top = D.filter((d) => d.verdict === "Likely");
  const vcls = (v) => "v-" + v.split(" ")[0];
  const rain = (D.find((d) => d.name === "Heavy rain") || {}).series || [];
  ui(`<div class="page">${pageHead("07", "Why did it change?", `${esc(R.area.name)} · ${fmt(R.headline.hectares)} ha · ${dshort(R.window.before.at(-1))} to ${dshort(R.window.after[0])}`)}
    <div class="row"><span class="chip amber">Our best explanation, not a measurement</span></div>
    <section class="frame cyan banner"><span class="lbl">Most likely cause</span>
      <strong style="font-size:20px">${top.length ? esc(top.map((d) => d.name).join(" and ")) : "Nothing clearly stands out yet"}</strong>
      <span class="hint" style="margin-left:auto;max-width:380px">We ruled out ${D.filter((d) => d.verdict === "Not supported").length} other cause(s), and couldn’t check ${D.filter((d) => d.verdict === "Not checked").length}.</span></section>
    <div class="grid2">
      <section class="frame" style="padding:18px;display:flex;flex-direction:column;gap:10px;min-height:340px"><h3>Daily rain over the area (mm)</h3>
        ${rain.length ? '<div style="flex:1;position:relative;min-height:260px"><canvas id="cRain" role="img" aria-label="Daily rainfall"></canvas></div>' : '<p class="hint">Rainfall isn’t available for this place yet.</p>'}</section>
      <section class="frame" style="padding:18px;display:flex;flex-direction:column;gap:10px"><h3>Everything we checked</h3>
        ${D.map((d, i) => `<article class="driver ${d.verdict === "Likely" ? "likely" : ""}"><header><h4>${esc(d.name)}</h4><span class="badge ${vcls(d.verdict)}">${esc(d.verdict)}</span></header>
          <p style="margin:0;color:var(--soft)">${d.verdict === "Not checked" ? "We couldn’t check this one for this place." : esc(d.evidence)}</p><span class="lbl">Source: ${esc(d.source)}</span></article>`).join("")}</section>
    </div>
    <section class="frame" style="padding:18px"><h3>What’s next for NISAR</h3><ul class="list" id="next" style="margin-top:10px"></ul></section>
  </div>`);
  $("#back").onclick = () => go("answer");
  if (rain.length) {
    const passes = new Set([...R.window.before, ...R.window.after]);
    S.charts.push(new Chart($("#cRain"), { type: "bar",
      data: { labels: rain.map((r) => dshort(r.date)), datasets: [{ data: rain.map((r) => r.mm), backgroundColor: rain.map((r) => passes.has(r.date) ? "#7DD3FC" : (r.date >= R.window.before.at(-1) && r.date <= R.window.after[0]) ? "#60A5FA" : "#334155") }] },
      options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { maxTicksLimit: 10 }, grid: { display: false } }, y: { grid: { color: "#1C2A3D" } } } } }));
  }
  api("/learn?tag=next").then((L) => { $("#next").innerHTML = L.resources.map((r) => `<li><span><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a></span></li>`).join(""); }).catch(() => {});
}

// ================================================================ STORIES
async function renderStories() {
  setProgress(0); setNav("stories");
  if (!demoAreas.length) { try { demoAreas = await api("/demo-areas"); } catch (_) {} }
  ui(`<aside class="side left frame" style="width:460px">
    <div class="screenhead"><div><h1>Flood stories</h1><small>Real events from 2026</small></div></div>
    <p class="hint">Each one takes you to the place and date, so you can see what changed and why.</p>
    ${demoAreas.map((d, i) => `<article class="driver"><header><h4>${esc(d.name)}</h4></header>
      <p style="margin:0;color:var(--soft)">${esc(d.story || "")}</p><span class="lbl">Around ${dshort(d.event_date)} 2026</span>
      <div class="row"><button class="btn small primary" data-story="${i}">Open this story</button></div></article>`).join("") || '<p class="hint">No stories have been added yet.</p>'}
  </aside>`);
  $$("[data-story]").forEach((b) => b.onclick = async () => {
    const d = demoAreas[+b.dataset.story];
    setArea(d.bbox, d.name, d.event_date); S.screen = "find";
    go("check");
  });
}

// ================================================================ WATCH LIST
async function addWatch() {
  const R = S.result, bbox = R ? R.area.bbox : S.area; if (!bbox) return;
  try {
    await api("/watch", { method: "POST", body: JSON.stringify({ bbox, name: R ? R.area.name : S.areaName, last_result_date: R ? R.window.after.at(-1) : null, analysis_id: R ? R.id : null }) });
    toast("Added to your watch list. We’ll let you know when there’s an update.");
  } catch (err) { toast(err.message); }
}
async function openWatch() {
  setNav("watch");
  const ov = $("#overlay");
  ov.innerHTML = `<div class="overlay"><div class="frame"><div class="screenhead"><div><h1>My places</h1></div></div>
    <p class="hint">We’ll let you know when there’s something new to see.</p><div id="wl"><div class="skeleton" style="height:60px"></div></div>
    <div class="row"><button class="btn" id="wCheck">Check now</button><button class="btn" id="wClose">Close</button></div></div></div>`;
  const draw = (items) => $("#wl").innerHTML = items.length ? items.map((w) => `<div class="watchrow"><div><b>${esc(w.name)}</b><div class="hint small">Last looked at ${w.last_result_date ? dshort(w.last_result_date) : "–"}</div></div>
      ${w.new_pass_available ? '<span class="chip cyan">Something new</span>' : '<span class="chip">Up to date</span>'}<button class="btn small" data-del="${w.id}" aria-label="Stop watching ${esc(w.name)}">Remove</button></div>`).join("")
    : '<p class="hint">You’re not watching anywhere yet. Tap “Watch this place” on any answer to add it here.</p>';
  const load = async () => { try { const items = await api("/watch"); draw(items); bind(); } catch (err) { $("#wl").innerHTML = `<p class="hint">${esc(err.message)}</p>`; } };
  const bind = () => $$("[data-del]").forEach((b) => b.onclick = async () => { await api("/watch/" + b.dataset.del, { method: "DELETE" }); load(); });
  $("#wClose").onclick = () => { ov.innerHTML = ""; setNav("find"); };
  $("#wCheck").onclick = async () => { $("#wl").innerHTML = '<div class="skeleton" style="height:60px"></div>'; try { draw(await api("/watch/check", { method: "POST" })); bind(); } catch (err) { $("#wl").innerHTML = `<p class="hint">${esc(err.message)}</p>`; } };
  load();
}

// ================================================================ SHARE + PDF REPORT
async function share() {
  const url = location.origin + location.pathname + "?r=" + S.result.id;
  try { await navigator.clipboard.writeText(url); toast("Link copied: " + url); } catch (_) { prompt("Copy this link", url); }
}
function printReport() {
  const R = S.result, ag = R.agreement || {};
  $("#report").innerHTML = `
    <h1>What changed in ${esc(R.area.name)}?</h1>
    <p>${dshort(R.window.before.at(-1))} → ${dshort(R.window.after[0])} 2026 · NISAR track ${esc(R.track.track)} ${esc(R.track.direction)} · ${esc([...new Set(R.passes.filter((p) => p.used).map((p) => p.quality))].join("/"))} data${R.source === "sample" ? " · sample data" : ""}</p>
    <h2 style="font-size:22pt;margin:6pt 0">${esc(R.headline.label)}: ${fmt(R.headline.hectares)} ha <span style="font-size:12pt;color:#555">(about ${fmt(R.headline.football_pitches)} football pitches)</span></h2>
    <p><b>Confidence: ${esc(R.confidence.level)}.</b> ${esc(R.confidence.reason)}</p>
    ${validationHTML(R)}
    <div style="position:relative"><img src="${abs(R.images.hh)}" alt="NISAR HH radar after the change"><img src="${abs(R.images.result)}" alt="Detected change" style="position:absolute;inset:0"></div>
    <table><tr><th>Measured</th><td>${esc(R.measured)}</td></tr><tr><th>What it likely means</th><td>${esc(R.interpreted)}</td></tr>
      <tr><th>Became water / receded / permanent</th><td>${fmt(R.areas_ha.became_water)} / ${fmt(R.areas_ha.water_receded)} / ${fmt(R.areas_ha.permanent_water)} ha</td></tr>
      <tr><th>NASA OPERA check</th><td>${ag.verdict ? `${esc(ag.verdict)} · ${fmt(ag.overlap_pct)}% of our new-water area is also water in OPERA` : "not available"}</td></tr>
      <tr><th>Likely causes (interpretation)</th><td>${(R.drivers || []).filter((d) => d.verdict !== "Not checked").map((d) => `${esc(d.name)}: ${esc(d.verdict)}`).join("; ")}</td></tr></table>
    <h3 style="margin:10pt 0 4pt">What happened here, in plain words</h3>
    <p><b>${esc(plainStory(R).lead)}</b></p>
    ${plainStory(R).items.map(([, t, body]) => `<p style="margin:3pt 0"><b>${t}:</b> ${body.replace(/<(?!\/?b>)[^>]+>/g, "")}</p>`).join("")}
    <p><b>Limits.</b> ${esc(R.limits.join(" "))}</p>
    <p style="font-size:9pt;color:#555">Made with NISAR Change Explorer. Radar: NASA–ISRO NISAR (ASF DAAC). ${esc((R.credits && R.credits.sources || []).map((s) => s.title).join(", "))}. ${esc(R.credits && R.credits.notice || "")} Link: ${esc(location.origin + location.pathname + "?r=" + R.id)}</p>`;
  setTimeout(() => window.print(), 300);
}

// ================================================================ EDGE STATES
function renderNotEnough(msg, detail) {
  setProgress(3);
  ui(`<aside class="side right frame" style="width:440px" role="alert">
    <div class="screenhead"><div><h1 style="color:#FCD34D">Not enough data yet</h1></div></div>
    <p>There aren’t enough satellite images around this date yet. Try another date, or we can let you know when there are.</p>
    <div class="row"><button class="btn primary" id="neWatch">Let me know when there is</button><button class="btn" id="neDate">Try another date</button><button class="btn" id="neArea">Try another area</button></div>
  </aside>`);
  $("#neWatch").onclick = addWatch; $("#neDate").onclick = () => go("ask"); $("#neArea").onclick = () => go("find");
}
function renderError(err, from) {
  if (err && err.notInDemo) return renderNotInDemo();
  ui(`<aside class="side right frame" style="width:460px" role="alert">
    <div class="screenhead"><div><h1 style="color:#FCA5A5">${err.offline ? "We can’t reach the server" : "Something went wrong"}</h1></div></div>
    <p>${err.offline ? "The app isn’t responding right now. Please check it’s still running and try again." : "We couldn’t finish this one. Please try again, or pick another place or date."}</p>
    <div class="frame state" style="border-style:dashed;border-color:#FBBF24"><span class="lbl" style="color:#FBBF24">Saved example (not live data)</span>
      <span class="hint">You can still look around using a saved example result.</span><button class="btn" id="openSample">Open the example</button></div>
    <div class="row"><button class="btn primary" id="retry">Try again</button><button class="btn" id="home2">Start over</button></div>
  </aside>`);
  $("#retry").onclick = () => go(from || "find"); $("#home2").onclick = () => go("find");
  $("#openSample").onclick = async () => { try { S.result = await api("/sample"); go("answer"); } catch (e) { toast("That didn’t work either. Please check the app is still running."); } };
}


// ---------------------------------------------------------------- welcome screen
function runIntro(show) {
  const el = $("#intro");
  if (!show) { el.remove(); return; }
  const name = "NISAR Change Explorer", title = $("#introTitle");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const t0 = reduce ? 0.2 : 1.45;   // name starts as the globe settles
  title.innerHTML = [...name].map((ch, i) => ch === " " ? '<span class="sp"> </span>' : `<span style="animation-delay:${(t0 + i * 0.035).toFixed(3)}s">${ch}</span>`).join("");
  const after = t0 + name.length * 0.035 + 0.2;
  $(".intro-tag", el).style.animationDelay = after + "s";
  $(".intro-go", el).style.animationDelay = (after + 0.35) + "s";
  const leave = () => {
    if (el.classList.contains("leaving")) return;
    el.classList.add("leaving"); document.removeEventListener("keydown", key);
    setTimeout(() => { el.remove(); $("#q") && $("#q").focus(); }, 700);
  };
  const key = (e) => { if (e.key === "Enter" || e.key === "Escape") leave(); };
  $("#introGo").onclick = leave; $("#introSkip").onclick = leave; document.addEventListener("keydown", key);

}

// ================================================================ boot
function boot() {
  initMap();
  $("#homeBtn").onclick = () => { $("#overlay").innerHTML = ""; go("find"); };
  $$(".top nav button").forEach((b) => b.onclick = () => {
    $("#overlay").innerHTML = "";
    if (b.dataset.nav === "watch") return openWatch();
    go(b.dataset.nav);
  });
  const r = new URLSearchParams(location.search).get("r");
  runIntro(!r);
  if (S.dl && !S.dl.finished) pollDownload();   // a shared result link opens straight on the answer
  if (r) {
    api("/results/" + encodeURIComponent(r)).then((res) => { S.result = res; S.area = res.area.bbox; S.areaName = res.area.name; drawArea(); go("answer"); })
      .catch((err) => renderError(err, "find"));
  } else go("find");
  // map gentle spin on the first screen
  let spin = true;
  map.on("mousedown", () => (spin = false)); map.on("touchstart", () => (spin = false));
  const rotate = () => { if (spin && S.screen === "find" && !S.area && !matchMedia("(prefers-reduced-motion: reduce)").matches && map.getZoom() < 3) { const c = map.getCenter(); map.easeTo({ center: [c.lng + 3, c.lat], duration: 1000, easing: (t) => t }); } };
  map.on("moveend", rotate); map.on("load", rotate);
}
boot();
