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
const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
const dshort = (iso) => iso ? `${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]}` : "";
const abs = (u) => !u ? u : (u.startsWith("http") ? u : location.origin + u);
const corners = '<span class="corners"><i></i><i></i></span>';
const GAP = ["2026-07-27", "2026-08-10"];
const NISAR_START = "2026-06-17";

function toast(msg, ms = 2600) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), ms);
}

async function api(path, opts = {}) {
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
  const labels = ["01 FIND A PLACE", "02 CHECK DATA", "03 ASK A QUESTION", "04 SEE THE ANSWER"];
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
function setNav(which) { $$(".top nav button").forEach((b) => b.dataset.nav === which ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current")); }
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
const HINTS = { answer: "SCROLL DOWN · PLAIN-WORDS SUMMARY, CHARTS AND ASSISTANT", sources: "SCROLL DOWN · WHY THE NUMBERS DIFFER",
  evidence: "SCROLL DOWN · LIMITS AND DATA USED", why: "SCROLL DOWN · EVERY CAUSE WE CHECKED" };
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
  $("#scrollHintText").textContent = page ? (HINTS[S.screen] || "SCROLL DOWN FOR MORE") : "MORE BELOW";
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
  const bars = st.dates.map((d) => `<i class="${d.cached === d.frames ? "on" : d.cached ? "part" : ""}" title="${dshort(d.date)}: ${d.cached === d.frames ? "on this computer" : "not downloaded"}"></i>`).join("");
  const what = scope === "question" ? "PASSES THIS QUESTION NEEDS" : "NISAR DATA ON THIS COMPUTER";
  if (!st.frames_total) return "";
  if (st.all_downloaded) return `<div class="dlstat ok"><span class="lbl">${what}</span><div class="passbar" aria-hidden="true">${bars}</div>
    <span>✓ All ${st.passes_total} passes are on this computer: answers come in seconds.</span></div>`;
  const e = st.estimate;
  return `<div class="dlstat"><span class="lbl">${what}</span><div class="passbar" aria-hidden="true">${bars}</div>
    <span class="big2">${st.passes_ready} OF ${st.passes_total} PASSES DOWNLOADED</span>
    <span class="hint">About <b>${fmtMB(e.mb)}</b> still to download: <b>${fmtDur(e.seconds)}</b> at ${e.mbps} MB/s${e.measured ? " (your last download's speed)" : " (rough first guess; it gets accurate once the download starts)"}.</span>
    ${running ? `<span class="hint accent">Downloading now: see the download panel.</span>`
      : `<button class="btn ${scope === "all" ? "primary" : ""}" data-dl="${scope}">⭳ DOWNLOAD ${scope === "question" ? "THESE " + st.passes_total + " PASSES FIRST" : "ALL " + st.passes_total + " PASSES"}</button>`}
    ${scope === "question" ? '<span class="hint small">Or just run the analysis: it downloads them itself and shows the same progress.</span>' : ""}</div>`;
}
function bindDl(root) {
  $$("[data-dl]", root).forEach((b) => b.onclick = () => startDownload(b.dataset.dl, b.dataset.dl === "question" ? S.eventDate : null));
}
async function startDownload(scope, eventDate) {
  try {
    const j = await api("/downloads", { method: "POST", body: JSON.stringify({ bbox: S.area, name: S.areaName, scope, event_date: eventDate }) });
    S.dl = { id: j.id, bbox: S.area, name: S.areaName, scope, min: false };
    sessionStorage.setItem("dl", JSON.stringify(S.dl));
    toast(j.already_running ? "This area is already downloading." : "Download started. You can keep exploring.");
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
    el.innerHTML = `${corners}<span class="lbl" style="color:var(--cyan)">⭳ ${esc((j.name || "AREA").toUpperCase())}</span><b class="mono">${st === "queued" ? "WAITING" : Math.round(d.pct || 0) + "%"}</b><span class="hint small">${d.eta_s ? fmtDur(d.eta_s) + " left" : ""}</span>`;
    el.onclick = () => { S.dl.min = false; renderDock(j); };
    return;
  }
  el.className = "dl frame" + (st === "done" ? " done" : ""); el.onclick = null;
  const head = (t) => `<header><span class="lbl">${t}</span><span class="hint small">${esc(j.name || "")}</span>${st === "done" || st === "failed" || st === "cancelled" ? '<button id="dlClose" aria-label="Close">×</button>' : '<button id="dlMin" aria-label="Minimise">–</button>'}</header>`;
  let body;
  if (st === "queued" || (st === "running" && !j.download)) {
    body = head("⭳ PREPARING DOWNLOAD") + `<p class="hint">${esc(((j.events || []).at(-1) || {}).label || "Waiting for the previous download to finish…")}</p><div class="bar"><span style="width:2%"></span></div>`;
  } else if (st === "running") {
    const extras = j.step === "extras";
    body = head(extras ? "⭳ FINISHING UP" : "⭳ DOWNLOADING NISAR DATA") + `
      <div class="pctbig">${Math.round(d.pct || 0)}<span style="font-size:20px;color:var(--muted)">%</span><small>${d.frames_done} OF ${d.frames_total} FILES</small></div>
      <div class="bar" role="progressbar" aria-valuenow="${Math.round(d.pct || 0)}" aria-valuemin="0" aria-valuemax="100"><span style="width:${d.pct || 0}%"></span></div>
      <div class="eta">${extras ? "Radar done. Getting rain, land height and fire data…" : `<b>${fmtDur(d.eta_s)}</b> left`}</div>
      <div class="nums"><div><span class="lbl">DOWNLOADED</span><b>${fmtMB(d.mb_done || 0)}</b></div><div><span class="lbl">OF ABOUT</span><b>${fmtMB(d.mb_total || 0)}</b></div><div><span class="lbl">SPEED</span><b>${d.mbps} MB/s</b></div></div>
      ${d.current && d.current.length ? `<span class="hint small">Now reading: ${d.current.map(dshort).join(", ")} · only your area is read from each file</span>` : ""}
      <span class="hint small">Time left is worked out from ${esc(d.estimated_from)}. ${j.skipped ? j.skipped + " file(s) were already on this computer." : ""}</span>
      <div class="row"><button class="btn small" id="dlCancel">CANCEL</button></div>`;
  } else if (st === "done") {
    body = head("✓ DOWNLOAD COMPLETE") + `
      <p style="margin:0">${d.frames_total ? `${d.frames_total} file(s), ${fmtMB(d.mb_done)} in ${fmtDur(d.elapsed_s).replace("about ", "")}.` : "Everything was already on this computer."} Answers for this area now come in seconds.</p>
      <div class="row">${S.area && sameBox(S.area, j.bbox) && S.avail && S.screen !== "ask" ? '<button class="btn primary small" id="dlAsk">ASK A QUESTION ›</button>' : ""}</div>`;
  } else if (st === "cancelled") {
    body = head("DOWNLOAD STOPPED") + `<p class="hint" style="margin:0">Files already downloaded are kept. Resume any time; it continues from there.</p><div class="row"><button class="btn small primary" id="dlResume">RESUME</button></div>`;
  } else {
    body = head("DOWNLOAD FAILED") + `<p class="hint" style="margin:0">${esc(j.error || "Something went wrong.")}</p><div class="row"><button class="btn small primary" id="dlResume">TRY AGAIN</button></div>`;
  }
  el.innerHTML = corners + body;
  const on = (id, fn) => { const b = document.getElementById(id); if (b) b.onclick = (e) => { e.stopPropagation(); fn(); }; };
  on("dlMin", () => { S.dl.min = true; renderDock(j); });
  on("dlClose", () => { el.hidden = true; S.dl = null; sessionStorage.removeItem("dl"); refreshDlBlocks(); });
  on("dlCancel", async () => { await api(`/downloads/${S.dl.id}/cancel`, { method: "POST" }); toast("Stopping after the current read…"); });
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
  <aside class="side left frame" aria-label="Find a place">${corners}
    <div class="screenhead"><span class="idx">01/</span><h1>FIND A PLACE</h1></div>
    <form class="searchbox" id="searchForm" role="search">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#7DD3FC" stroke-width="1.8" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="M20 20l-4-4"></path></svg>
      <label class="sr" for="q">Search a place</label>
      <input id="q" type="search" placeholder="Search a town, river or region" autocomplete="off">
      <button class="btn small" type="submit">GO</button>
    </form>
    <ul class="results" id="results"></ul>
    <div><div class="lbl">OR TRY A STORY</div><div class="presets" id="presets" style="margin-top:8px"></div></div>
    <div class="lbl">STUDY AREA ${a ? "" : "· CLICK THE MAP TO PLACE ONE"}</div>
    ${a ? `
      <div class="statgrid">
        <div><span class="lbl">PLACE</span><span>${esc(S.areaName)}</span></div>
        <div><span class="lbl">SIZE</span><b>${fmt(areaKm2(a))}</b><span class="lbl">KM²</span></div>
        <div><span class="lbl">CENTRE</span><span class="mono small">${((a[1] + a[3]) / 2).toFixed(3)}°N ${((a[0] + a[2]) / 2).toFixed(3)}°E</span></div>
        <div><span class="lbl">BOX</span><span class="mono small">${a.map((v) => v.toFixed(2)).join(", ")}</span></div>
      </div>` : `<p class="hint">Search for a place, or click anywhere on the globe. NISAR radar sees through cloud, day and night.</p>`}
    <div class="sizes"><span class="lbl">AREA SIZE</span>
      <div class="seg" role="group" aria-label="Area size">${[10, 20, 25].map((k) => `<button data-km="${k}" aria-pressed="${S.boxKm === k}">${k} KM</button>`).join("")}</div></div>
    <button class="btn primary" id="toCheck" ${a ? "" : "disabled"}>CHECK NISAR DATA ›</button>
  </aside>
  <aside class="side right glance" style="padding:0;background:none;gap:12px;width:300px" aria-label="Coverage at a glance">
    <div class="lbl" style="padding:4px 0">COVERAGE AT A GLANCE</div>
    <div class="frame card">${corners}<span class="lbl">REPEAT</span><b class="big">12</b><span class="hint">days between NISAR passes</span></div>
    <div class="frame card">${corners}<span class="lbl">CALIBRATED DATA SINCE</span><b class="big">17 JUN</b><span class="hint">2026 · Validated from 21 Oct</span></div>
    <div class="frame card">${corners}<span class="lbl">NO DATA</span><b class="big" style="font-size:20px">27 JUL – 10 AUG</b><span class="hint">a permanent gap; we never fill it in</span></div>
  </aside>`);
  // presets
  if (!demoAreas.length) { try { demoAreas = await api("/demo-areas"); } catch (_) { demoAreas = []; } }
  $("#presets").innerHTML = demoAreas.map((d, i) => `<button class="btn small" data-preset="${i}">${esc(d.name.toUpperCase())}</button>`).join("") || '<span class="hint">No demo areas configured.</span>';
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
  <aside class="side right frame" aria-label="Check data" style="width:420px">${corners}
    <div class="screenhead"><span class="idx">02/</span><div><h1>CHECK DATA</h1><small>${esc(S.areaName)}</small></div></div>
    <div id="checkBody"><div class="skeleton" style="height:70px"></div><div class="skeleton" style="height:120px;margin-top:12px"></div><p class="hint">Asking NASA's archive which NISAR passes cover this area…</p></div>
  </aside>
  <div class="timelinebar frame" id="tlbar" hidden>${corners}<div class="lbl">NISAR PASSES OVER THIS AREA · SAME TRACK</div><div id="timeline"></div></div>`);
  try {
    S.avail = await api("/availability", { method: "POST", body: JSON.stringify({ bbox: S.area }) });
  } catch (err) { return renderError(err, "check"); }
  const A = S.avail, bt = A.best_track || {};
  const q = {}; (bt.quality || []).forEach((x) => q[x] = 0);
  const kind = A.enough_data ? "ok" : A.total_passes ? "no" : "bad";
  if (A.newest_pass) $("#latestText").textContent = "LATEST PASS " + dshort(A.newest_pass);
  $("#checkBody").innerHTML = `
    <div class="verdict ${kind}"><span class="badge ${kind === "ok" ? "v-Likely" : "v-Possible"}">${kind === "ok" ? "✓" : "!"}</span>
      <div><strong>${esc(A.verdict.toUpperCase())}</strong><div class="hint">${A.enough_data ? "We can compare before and after on one track." : "We need at least 2 passes before and 2 after on the same track, so we won't guess."}</div></div></div>
    <div class="statgrid" style="margin-top:14px">
      <div><span class="lbl">PASSES ON BEST TRACK</span><b>${A.total_passes}</b></div>
      <div><span class="lbl">TRACK</span><b>${esc(bt.track || "–")} ${esc(bt.direction || "")}</b></div>
      <div><span class="lbl">QUALITY</span><span>${esc((bt.quality || []).join(" / ") || "–")}</span></div>
      <div><span class="lbl">NEWEST PASS</span><span>${esc(A.newest_pass ? dshort(A.newest_pass) : "–")}</span></div>
    </div>
    <p class="hint small" style="margin-top:10px">${A.tracks.length} track(s) cover this area. We use only one, so every image sees the ground from the same angle.</p>
    <div class="lbl" style="margin-top:12px">WHAT YOU CAN ASK HERE</div>
    <ul class="cando" style="margin-top:8px">
      ${[["now", "What is here now?"], ["change", "What changed around a date?"], ["much", "How much changed?"], ["why", "Why did it change?"], ["diff", "Compare two dates"]]
        .map(([k, l]) => `<li class="${A.can_answer[k] ? "" : "off"}">${A.can_answer[k] ? "✓" : "×"} ${l}</li>`).join("")}
    </ul>
    <div id="dlCheck" style="margin-top:14px"><div class="skeleton" style="height:64px"></div></div>
    <div class="row" style="margin-top:16px">
      <button class="btn" id="backFind">‹ CHANGE AREA</button>
      <button class="btn primary" id="toAsk" ${A.can_answer.change ? "" : "disabled"}>ASK A QUESTION ›</button>
    </div>`;
  if (!A.total_passes) {
    $("#checkBody").insertAdjacentHTML("beforeend", `<div class="frame state" style="margin-top:12px">${corners}<b>NO NISAR DATA HERE YET</b><span class="hint">Try a nearby area, or watch this place and we'll mark it when a pass arrives.</span><button class="btn" id="watchEmpty">WATCH THIS PLACE</button></div>`);
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
  let s = `<svg viewBox="0 ${o.bars ? 0 : -10} ${W} ${o.bars ? 150 : 106}" role="img" aria-label="NISAR passes from June to November 2026${o.event ? ", change date " + o.event : ""}"><defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="#566070" stroke-width="2"/></pattern></defs>`;
  const base = o.bars ? 108 : 46;
  s += `<rect x="${X(GAP[0])}" y="${base - 18}" width="${X(GAP[1]) - X(GAP[0])}" height="36" fill="url(#hatch)" opacity=".8"/><text x="${(X(GAP[0]) + X(GAP[1])) / 2}" y="${base + 32}" text-anchor="middle" font-family="JetBrains Mono" font-size="10" fill="#566070">NO DATA</text>`;
  s += `<line x1="${x0}" y1="${base}" x2="${x1}" y2="${base}" stroke="#3B4A60"/>`;
  ["2026-07-01", "2026-08-01", "2026-09-01", "2026-10-01", "2026-11-01"].forEach((m) => s += `<text x="${X(m)}" y="${base + 20}" text-anchor="middle" font-family="JetBrains Mono" font-size="10" fill="#566070">${MONTHS[+m.slice(5, 7) - 1]}</text>`);
  s += `<text x="${x0}" y="${base + 20}" font-family="JetBrains Mono" font-size="10" fill="#566070">JUN</text>`;
  if (o.bars) {
    const mx = Math.max(1, ...o.bars.map((b) => b.v));
    o.bars.forEach((b) => { const h = 70 * b.v / mx; s += `<rect x="${X(b.d) - 10}" y="${base - 14 - h}" width="20" height="${h}" fill="${b.after ? "#1D4ED8" : "#60A5FA"}"/><text x="${X(b.d)}" y="${base - 18 - h}" text-anchor="middle" font-family="JetBrains Mono" font-size="10" fill="#9AA4B2">${fmt(b.v)}</text>`; });
  }
  dates.forEach((d) => {
    const used = o.used ? o.used.includes(d) : true;
    const sel = o.event && d >= o.event;
    s += `<g ${o.clickable ? `class="passpick" data-d="${d}" style="cursor:pointer"` : ""}><circle cx="${X(d)}" cy="${base}" r="${used ? 6 : 4}" fill="${sel && used ? "#7DD3FC" : "#05080D"}" stroke="${used ? "#7DD3FC" : "#566070"}" stroke-width="1.5"/>${o.clickable ? `<rect x="${X(d) - 12}" y="${base - 14}" width="24" height="28" fill="transparent"/>` : ""}<text x="${X(d)}" y="${base - 12}" text-anchor="middle" font-family="JetBrains Mono" font-size="9.5" fill="#9AA4B2">${dshort(d)}</text></g>`;
  });
  if (o.event) { const x = X(o.event); s += `<line x1="${x}" y1="${base - 42}" x2="${x}" y2="${base + 10}" stroke="#FBBF24" stroke-dasharray="4 4"/><text x="${x + 4}" y="${base - 34}" font-family="JetBrains Mono" font-size="10" fill="#FCD34D">CHANGE DATE ${dshort(o.event)}</text>`; }
  return s + "</svg>";
}

// ================================================================ 03 ASK
function renderAsk() {
  setProgress(3); setNav("find");
  if (!S.avail) return go("check");
  const dates = (S.avail.best_track || {}).dates || [];
  if (!S.eventDate) S.eventDate = dates[Math.floor(dates.length / 2)] || "2026-09-01";
  const Q = [["now", "What is here now?", "the latest radar view"], ["diff", "Compare two dates", "differences between passes"],
             ["change", "What changed?", "before vs after a date"], ["why", "Why did it change?", "likely causes, with evidence"],
             ["much", "How much changed?", "area in hectares and pitches"]];
  ui(`
  <aside class="side left frame" style="width:440px" aria-label="Ask a question">${corners}
    <div class="screenhead"><span class="idx">03/</span><div><h1>ASK A QUESTION</h1><small>${esc(S.areaName)}</small></div></div>
    <div class="tiles" role="radiogroup" aria-label="Question">
      ${Q.map(([k, t, d]) => `<button class="tile" role="radio" data-q="${k}" aria-checked="${S.question === k}" ${S.avail.can_answer[k] ? "" : "disabled"}><b>${t}</b><span>${d}</span></button>`).join("")}
    </div>
    <div class="lbl">LOOKING FOR</div>
    <div class="chips" role="group" aria-label="Looking for">
      <button class="kchip" aria-checked="true" disabled>Water and floods <em>VALIDATED METHOD</em></button>
      <button class="kchip" aria-checked="false" disabled title="Roadmap">Vegetation loss <em>SOON</em></button>
      <button class="kchip" aria-checked="false" disabled title="Roadmap">New buildings <em>SOON</em></button>
      <button class="kchip" aria-checked="false" disabled title="Roadmap">Ground movement <em>SOON</em></button>
    </div>
    <div class="lbl">OR TYPE YOUR QUESTION</div>
    <label class="field"><span class="sr">Type a question</span><input id="freeQ" placeholder="e.g. how much land flooded after 7 September?"></label>
    <div id="dlAsk2"></div>
    <label class="row hint" style="font-size:13px"><input type="checkbox" id="quick" ${S.quick ? "checked" : ""}> Quick preview (40 m, faster)</label>
    <div class="row">
      <button class="btn" id="backCheck">‹ BACK</button>
      <button class="btn primary" id="run">RUN ANALYSIS ›</button>
    </div>
    <p class="hint small">First run of a new place reads NISAR files from NASA (minutes). Places already run load in seconds.</p>
  </aside>
  <div class="timelinebar frame">${corners}
    <div class="row" style="justify-content:space-between"><div class="lbl">CLICK A PASS: THE CHANGE HAPPENED JUST BEFORE IT</div><div class="lbl" id="evLbl"></div></div>
    <div id="timeline"></div>
  </div>`);
  const drawTL = () => {
    $("#timeline").innerHTML = timelineSVG(dates, { event: S.eventDate, clickable: true });
    const b = dates.filter((d) => d < S.eventDate).length, a = dates.length - b;
    $("#evLbl").textContent = `${b} PASSES BEFORE · ${a} AFTER · WE USE THE CLOSEST 2 + 2`;
    $$(".passpick").forEach((g) => g.onclick = () => { S.eventDate = g.dataset.d; drawTL(); });
    clearTimeout(drawTL.t); drawTL.t = setTimeout(() => loadDlBlock("#dlAsk2", "question", S.eventDate), 350);
  };
  drawTL();
  $$(".tile").forEach((t) => t.onclick = () => { S.question = t.dataset.q; $$(".tile").forEach((x) => x.setAttribute("aria-checked", x === t)); });
  $("#freeQ").oninput = (e) => {
    const v = e.target.value.toLowerCase();
    const k = /why|cause/.test(v) ? "why" : /how much|area|hectare/.test(v) ? "much" : /now|today/.test(v) ? "now" : /compare|differ/.test(v) ? "diff" : "change";
    const m = v.match(/(\d{1,2})\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/);
    if (m) { const mm = MONTHS.indexOf(m[2].toUpperCase()) + 1; S.eventDate = `2026-${String(mm).padStart(2, "0")}-${String(m[1]).padStart(2, "0")}`; drawTL(); }
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
const STEP_LABELS = ["Finding NISAR passes", "Reading the study area from each pass", "Lining up passes and calming radar speckle",
                     "Comparing before and after", "Checking against NASA OPERA", "Writing the answer"];
function renderAnalysing() {
  setProgress(4); setNav("find");
  ui(`
  <div class="sweep" aria-hidden="true"></div>
  <aside class="side right frame" style="width:420px" aria-label="Analysing" aria-live="polite">${corners}
    <div class="screenhead"><span class="idx">04/</span><div><h1>ANALYSING</h1><small>${esc(S.areaName)} · CHANGE DATE ${dshort(S.eventDate)}</small></div></div>
    <div class="pct"><span id="pct">0</span><small style="font-size:20px;color:var(--muted)">%</small></div>
    <div class="segbar" id="segbar">${STEP_IDS.map(() => "<i></i>").join("")}</div>
    <div class="dlrun" id="dlrun" hidden></div>
    <ol class="steps" id="steps">${STEP_LABELS.map((l, i) => `<li data-s="${STEP_IDS[i]}"><i></i>${l}</li>`).join("")}</ol>
    <div class="lbl">ACTIVITY</div><div class="log" id="log"></div>
    <div class="row"><button class="btn" id="keep">KEEP EXPLORING</button></div>
    <p class="hint small">A new place can take several minutes the first time: NASA's archive is in the US, and we read only your area from each file.</p>
  </aside>`);
  $("#keep").onclick = () => { toast("The analysis keeps running. Come back with the progress bar."); go("find"); };
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
      box.innerHTML = `<span class="lbl" style="color:var(--cyan)">⭳ DOWNLOADING FROM NASA · ${Math.round(d.pct)}%</span>
        <div class="bar"><span style="width:${d.pct}%"></span></div>
        <span><b>${fmtMB(d.mb_done)}</b> of about ${fmtMB(d.mb_total)} · ${d.mbps} MB/s · <b>${fmtDur(d.eta_s)}</b> left · file ${Math.min(d.frames_done + 1, d.frames_total)} of ${d.frames_total}</span>`;
    } else if (d && j.step === "fetch" && d.frames_total === 0) {
      box.hidden = false; box.innerHTML = `<span>✓ All files already on this computer: no download needed.</span>`;
    } else if (j.step !== "fetch") box.hidden = true;
  }
  if (j.status === "done") { S.result = j.result; S.resultKey = j.result.id; history.replaceState(null, "", "?r=" + j.result.id); return go("answer"); }
  if (j.status === "not_enough_data") return renderNotEnough(j.error, j.detail);
  if (j.status === "failed") return renderError(new Error(j.error || "The analysis failed."), "ask");
  if (S.screen === "analysing" && $("#log")) {
    const line = `${new Date().toLocaleTimeString()}  ${STEP_LABELS[STEP_IDS.indexOf(j.step)] || "Waiting in the queue"} · ${j.progress || 0}%`;
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
  const D = (d) => { const [n, m] = dshort(d).split(" "); return `${n} ${m[0]}${m.slice(1).toLowerCase()}`; };
  let lead, what;
  if (h.label === "No clear change") {
    lead = `No clear change in ${place} between ${D(b)} and ${D(a)}.`;
    what = `We compared the radar images from before and after and found <b>no large area that turned into water or dried out</b>. Small differences were too small or too short-lived to count.`;
  } else if (h.label === "Water likely receded") {
    lead = `Water drained away from about ${fmt(h.hectares)} hectares of ${place}.`;
    what = `Between <b>${D(b)} and ${D(a)}</b> (${days} days), about <b>${fmt(A.water_receded)} hectares</b> that were under water became dry land again. That is roughly <b>${fmt(Math.round(A.water_receded / 0.714))} football pitches</b>.`;
  } else {
    lead = `About ${fmt(h.hectares)} hectares of land in ${place} went under water.`;
    what = `Between <b>${D(b)} and ${D(a)}</b> (${days} days), about <b>${fmt(A.became_water)} hectares</b> of dry land turned into water: roughly <b>${fmt(h.football_pitches)} football pitches</b>, or ${h.share_of_area_pct}% of the area you picked. On the picture it is painted <b>dark blue</b>.`;
  }
  const items = [[ICON.water, "WHAT CHANGED", what]];
  const other = [];
  if (A.permanent_water > 0) other.push(`The river and lakes that were already there (${fmt(A.permanent_water)} ha) are shown in black and are <b>not</b> counted as new.`);
  if (h.label !== "Water likely receded" && A.water_receded > 0) other.push(`In other spots about ${fmt(A.water_receded)} ha of water went down (light blue).`);
  if (other.length) items.push([ICON.map, "WHAT ELSE IS ON THE MAP", other.join(" ")]);
  items.push([ICON.radar, "HOW WE SAW IT", `The NISAR satellite flew over ${R.window.before.length + R.window.after.length} times on the same path, before and after. Its radar sees through cloud and at night. Calm water bounces the radar away, so it looks <b>dark</b>. Land that suddenly turns dark and <b>stays dark on the next pass</b> is most likely new water.`]);
  const sure = { High: "We are fairly sure.", Medium: "We are moderately sure.", Lower: "Treat this with caution." }[c.level] || "";
  const opera = ag.verdict ? ` NASA's separate water map (OPERA, from a different satellite) agrees on <b>${fmt(ag.overlap_pct)}%</b> of the water we found.` : " We could not compare it with NASA's separate water map for these dates.";
  items.push([ICON.check, "HOW SURE WE ARE", `<b>${sure}</b> ${esc(c.reason)}${opera}`]);
  const D2 = (R.drivers || []).filter((d) => d.verdict === "Likely" || d.verdict === "Possible");
  items.push([ICON.why, "WHY IT PROBABLY HAPPENED", D2.length
    ? `Most likely cause: <b>${esc(D2.map((d) => d.name).join(" + "))}</b>. ${esc(D2[0].evidence)} This is our best explanation from other data, not something the radar measures directly.`
    : `We checked rain, rivers, land height, earthquakes and fires, but none clearly explains it yet. This part is an interpretation, not a measurement.`, "interp"]);
  items.push([ICON.warn, "KEEP IN MIND", `This is an estimate from space, <b>not an official flood warning</b>. Very wet fields and young rice can look like water. For safety decisions, follow your local authorities. Tap <b>Watch this place</b> to know when the next pass arrives (every 12 days).`]);
  return { lead, items };
}
function plainStoryHTML(R) {
  const st = plainStory(R);
  return `<section class="frame plain" aria-label="What happened here, in plain words">${corners}
    <div class="lead">${esc(st.lead)}<small>WHAT HAPPENED HERE · IN PLAIN WORDS</small></div>
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
    <span class="idx">04/</span>
    <div><h1>WHAT CHANGED IN ${esc(R.area.name.toUpperCase())}?</h1><small class="mono small muted">${dshort(bLast)} → ${dshort(aFirst)} 2026 · TRACK ${esc(R.track.track)} ${esc(R.track.direction)} · ${R.window.before.length + R.window.after.length} PASSES · ${esc(qual.toUpperCase())} DATA${R.source === "sample" ? " · SAMPLE DATA" : ""}</small></div>
    <div class="row" style="margin-left:auto">
      <button class="btn small" id="watchBtn">🔔 WATCH THIS PLACE</button>
      <button class="btn small" id="shareBtn">SHARE</button>
      <button class="btn small primary" id="reportBtn">EXPORT REPORT</button>
    </div>
  </div>
  <div class="ansgrid">
  <section class="viewer frame" aria-label="Before and after radar images">${corners}
    <div class="viewtabs" role="group" aria-label="How to show the images">
      ${[["swipe", "SWIPE"], ["change", "CHANGE ONLY"], ["lapse", "TIME-LAPSE"], ["photo", "NORMAL PHOTO"]].map(([k, l]) => `<button data-view="${k}" aria-pressed="${S.view === k}">${l}</button>`).join("")}
      <div class="seg" role="group" aria-label="Radar polarization"><span class="lbl" style="padding:0 10px">POLARIZATION</span>
        ${[["hh", "HH"], ["hv", "HV"], ["mix", "COLOUR MIX"]].map(([k, l]) => `<button data-pol="${k}" aria-pressed="${S.pol === k}" ${I[k] ? "" : "disabled"}>${l}</button>`).join("")}</div>
    </div>
    <div class="vmap" id="vBefore"></div><div class="vmap" id="vAfter"></div>
    <div class="swipe" id="swipe"><button aria-label="Drag or use arrow keys to compare before and after">‹ ›</button></div>
    <span class="chip mono vlabel" id="lblB" style="left:12px">BEFORE · ${dshort(bLast)}</span>
    <span class="chip mono cyan vlabel" id="lblA" style="right:12px">AFTER · ${dshort(aFirst)}</span>
    <div class="polnote" id="polnote" style="left:50%;top:50px;transform:translateX(-50%)"></div>
    <div class="legend" id="legend">
      <span><i style="background:#1D4ED8"></i>Likely became water</span><span><i style="background:#60A5FA"></i>Water likely receded</span>
      <span><i style="background:#0A0C10;border:1px solid #566070"></i>River (always water)</span><span><i style="background:#9CA3AF;opacity:.5"></i>Could not read</span>
    </div>
  </section>
  <aside class="answercard frame" aria-label="The answer">${corners}
    <div class="row"><span class="chip ${confCls}"><span class="dot"></span>CONFIDENCE · ${esc(c.level.toUpperCase())}</span><span class="chip cyan">✓ ${esc((R.provenance.polarization_used || "HH").toUpperCase())} RADAR</span></div>
    <div><div class="mono small" style="color:#93C5FD;letter-spacing:1.5px">${esc(h.label.toUpperCase())}</div>
      <div class="bignum">${fmt(h.hectares)}<small>HA</small></div>
      <div style="color:var(--soft);font-size:17px">${h.label === "No clear change" ? "no clear change between the passes" : `${h.label === "Water likely receded" ? "drained away" : "became water"} in ${Math.round((Date.parse(aFirst) - Date.parse(bLast)) / 864e5)} days, ${dshort(bLast)} → ${dshort(aFirst)}`}</div></div>
    <div class="pitch"><svg width="34" height="22" viewBox="0 0 36 24" fill="none" stroke="#E6EDF3" stroke-width="1.4" aria-hidden="true"><rect x="1" y="1" width="34" height="22"/><path d="M18 1v22"/><circle cx="18" cy="12" r="4"/></svg>
      <span>About <b>${fmt(h.football_pitches)} football pitches</b>, or ${h.share_of_area_pct}% of the study area</span></div>
    <p class="hint">${esc(c.reason)}${ag.overlap_pct !== undefined && ag.overlap_pct !== null ? ` NASA's own water map overlap: ${fmt(ag.overlap_pct)}%.` : ""}</p>
    <div class="mi"><div><div class="lbl">MEASURED</div>${esc(R.measured)}</div><div><div class="lbl">WHAT IT LIKELY MEANS</div>${esc(R.interpreted)}</div></div>
    <div class="row" style="margin-top:auto;gap:18px">
      <button class="linkbtn" data-go="why">WHY DID IT CHANGE? ›</button>
      <button class="linkbtn" data-go="evidence">HOW WE KNOW THIS ›</button>
    </div>
  </aside>
  </div>
  ${plainStoryHTML(R)}
  <section class="frame chartframe">${corners}
    <h3>CHART 2 · CHANGE AT EACH SATELLITE PASS (HA OF WATER GAINED OR LOST)
      <span class="keys"><span><i style="background:#1D4ED8"></i>Water spreading</span><span><i style="background:#60A5FA"></i>Water going down</span><span><i style="background:#7DD3FC;border-radius:50%"></i>Validated pass</span><span><i style="border:1px solid #7DD3FC;border-radius:50%"></i>Provisional / Beta</span></span></h3>
    <div id="passChart"></div>
  </section>
  <div class="grid3">
    <section class="frame chartframe">${corners}<h3>CHART 1 · CHANGE BY TYPE (HA)</h3>
      ${hb("Became water", A.became_water, maxT, "background:#1D4ED8")}${hb("Water receded", A.water_receded, maxT, "background:#60A5FA")}${hb("River (always)", A.permanent_water, maxT, "background:#334155")}
      <span class="hint small">Vegetation loss and new buildings are on our roadmap; only water is validated.</span></section>
    <section class="frame chartframe">${corners}<h3>CHART 3 · WATER IN THE AREA (HA)</h3>
      <div class="vbars"><div>${fmt(wb)}<i style="height:${100 * wb / maxW}%;background:#60A5FA"></i></div><div>${fmt(wa)}<i style="height:${100 * wa / maxW}%;background:#1D4ED8"></i></div></div>
      <div class="vbars-x"><span>${dshort(bLast)}</span><span>${dshort(aFirst)}</span></div>
      <span class="hint small">${ratio && ratio > 1.15 ? `${ratio.toFixed(1)} times more water in ${Math.round((Date.parse(aFirst) - Date.parse(bLast)) / 864e5)} days.` : ratio && ratio < 0.87 ? "Less water after than before." : "About the same water before and after."}</span></section>
    <section class="frame chartframe">${corners}<h3>CHART 4 · FLOODED AREA BY SOURCE (HA)</h3>
      ${hb("NISAR (ours)", ag.nisar_water_ha ?? h.hectares, maxS, "background:#1D4ED8")}${hb("NASA OPERA", ag.opera_water_ha, maxS, "background:#60A5FA")}
      <div class="hbar"><span class="muted">Normal photo</span><span class="track" style="background:repeating-linear-gradient(45deg,#1C2A3D 0 4px,transparent 4px 8px)"></span><b class="muted small">CLOUD</b></div>
      <span class="hint small">${ag.verdict ? `NASA OPERA confirms ${fmt(ag.overlap_pct)}% of our water.` : "NASA OPERA comparison not available for this date."}</span></section>
  </div>
  <div class="grid2" style="grid-template-columns:minmax(0,1fr) minmax(0,1.1fr)">
    <section class="frame chartframe">${corners}<h3>DO SOURCES AGREE? ${ag.verdict ? `<span class="chip ${ag.verdict === "Confirmed" ? "green" : ag.verdict === "Partly confirmed" ? "amber" : "red"}" style="margin-left:auto"><span class="dot"></span>${esc(ag.verdict.toUpperCase())} · ${fmt(ag.overlap_pct)}% OVERLAP</span>` : ""}</h3>
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
  let s = `<svg viewBox="0 0 ${W} 250" role="img" aria-label="Change in water area at each NISAR pass"><defs><pattern id="hatch2" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="#3B4A60" stroke-width="2"/></pattern></defs>
    <line x1="${x0}" y1="${zero}" x2="${x1}" y2="${zero}" stroke="#3B4A60"/><text x="${x0 - 12}" y="${zero + 4}" text-anchor="end" font-family="JetBrains Mono" font-size="10" fill="#9AA4B2">0</text>
    <text x="${x0 - 12}" y="${zero - H + 4}" text-anchor="end" font-family="JetBrains Mono" font-size="10" fill="#9AA4B2">+${fmt(mx)}</text>`;
  const ty = 180;
  s += `<rect x="${X(GAP[0])}" y="${ty - 14}" width="${X(GAP[1]) - X(GAP[0])}" height="28" fill="url(#hatch2)"/><text x="${(X(GAP[0]) + X(GAP[1])) / 2}" y="${ty + 30}" text-anchor="middle" font-family="JetBrains Mono" font-size="10" fill="#566070">NO DATA</text>`;
  ["2026-07-01", "2026-08-01", "2026-09-01", "2026-10-01", "2026-11-01"].forEach((m) => s += `<text x="${X(m)}" y="${ty - 22}" text-anchor="middle" font-family="JetBrains Mono" font-size="10" fill="#566070">${MONTHS[+m.slice(5, 7) - 1]}</text>`);
  R.passes.forEach((p) => {
    const x = X(p.date), q = pp[p.date], v = q && q.change_ha;
    if (v !== null && v !== undefined) {
      const hgt = Math.max(2, H * Math.abs(v) / mx), up = v >= 0;
      s += `<rect x="${x - 9}" y="${up ? zero - hgt : zero}" width="18" height="${hgt}" fill="${up ? "#1D4ED8" : "#60A5FA"}"/><text x="${x}" y="${up ? zero - hgt - 6 : zero + hgt + 13}" text-anchor="middle" font-family="JetBrains Mono" font-size="10" fill="#CBD5E1">${up ? "+" : ""}${fmt(v)}</text>`;
    }
    const val = p.quality === "Validated";
    s += `<circle cx="${x}" cy="${ty}" r="6" fill="${val ? "#7DD3FC" : "#05080D"}" stroke="${p.used ? "#E6EDF3" : "#566070"}" stroke-width="1.5"/><text x="${x}" y="${ty + 22}" text-anchor="middle" font-family="JetBrains Mono" font-size="9.5" fill="#9AA4B2">${dshort(p.date)}</text>`;
  });
  const br = (dates, label) => { if (!dates.length) return; const a = X(dates[0]) - 14, b = X(dates.at(-1)) + 14; s += `<path d="M${a} ${ty + 30} v6 H${b} v-6" fill="none" stroke="#7DD3FC"/><text x="${(a + b) / 2}" y="${ty + 52}" text-anchor="middle" font-family="JetBrains Mono" font-size="10" fill="#7DD3FC">${label}</text>`; };
  br(R.window.before, "BEFORE"); br(R.window.after, "AFTER");
  return s + "</svg>";
}

const POL_NOTE = { hh: ["HH", "Same-direction radar: water looks black."], hv: ["HV", "Cross-direction radar: plants look bright."], mix: ["MIX", "Red = HH, green = HV, blue = HH/HV: each colour is a surface type."] };
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
  if (v === "swipe") { const [k, t] = POL_NOTE[S.pol]; pn.hidden = false; pn.innerHTML = `<b class="mono small accent">${k}</b>${t}`; $("#lblA").textContent = "AFTER · " + dshort(R.window.after[0]); }
  else if (v === "change") { pn.hidden = false; pn.innerHTML = `<b class="mono small accent">CHANGE</b>Only the change, over the map.`; $("#lblA").textContent = "CHANGE " + dshort(R.window.before.at(-1)) + " → " + dshort(R.window.after[0]); }
  else if (v === "photo") { pn.hidden = false; pn.innerHTML = `<b class="mono small accent">PHOTO</b>NASA Worldview true colour, ${dshort(R.window.after[0])}. Expect cloud: that is why we use radar.`; $("#lblA").textContent = "NORMAL PHOTO"; }
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
  const P = S.result.images.passes || []; if (!P.length) { $("#polnote").textContent = "No per-pass images in this result."; return; }
  let i = 0;
  const step = () => {
    P.forEach((_, k) => setVis(vA, "pass-" + k, k === i));
    $("#lblA").textContent = `${P[i].group.toUpperCase()} · ${dshort(P[i].date)}`;
    $("#polnote").innerHTML = `<b class="mono small accent">TIME-LAPSE</b>HH radar, pass ${i + 1} of ${P.length}`;
    i = (i + 1) % P.length;
  };
  step(); S.lapseTimer = setInterval(step, 1300);
}
function stopLapse() { if (S.lapseTimer) clearInterval(S.lapseTimer); S.lapseTimer = null; }

function chart(id, type, labels, data, colors, horizontal = false) {
  const el = document.getElementById(id); if (!el) return;
  Chart.defaults.color = "#9AA4B2"; Chart.defaults.font.family = "JetBrains Mono"; Chart.defaults.font.size = 10;
  S.charts.push(new Chart(el, {
    type, data: { labels, datasets: [{ data, backgroundColor: colors, borderWidth: 0 }] },
    options: { indexAxis: horizontal ? "y" : "x", maintainAspectRatio: false, animation: { duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 700 },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => fmt(c.raw) + " ha" } } },
      scales: { x: { grid: { color: "#1C2A3D" }, ticks: { color: "#9AA4B2" } }, y: { grid: { color: horizontal ? "transparent" : "#1C2A3D" }, ticks: { color: "#CBD5E1" } } } },
  }));
}

function initAssistant() {
  const ask = async (q) => {
    if (!q) return;
    if (/time-?lapse/i.test(q)) { setView("lapse"); $(".viewer").scrollIntoView({ behavior: "smooth" }); return; }
    $("#msgs").insertAdjacentHTML("beforeend", `<div class="msg me">${esc(q)}</div>`);
    try {
      const a = await api(`/results/${S.result.id}/ask`, { method: "POST", body: JSON.stringify({ question: q }) });
      $("#msgs").insertAdjacentHTML("beforeend", `<div class="msg">${esc(a.answer)}<small>BASED ON · ${esc(a.based_on.join(" · ").toUpperCase())}</small></div>`);
      $("#sugg").innerHTML = a.suggestions.slice(0, 3).map((s) => `<button>${esc(s)}</button>`).join("");
      $$("#sugg button").forEach((b) => b.onclick = () => ask(b.textContent));
    } catch (err) { $("#msgs").insertAdjacentHTML("beforeend", `<div class="msg">${esc(err.message)}</div>`); }
    $("#msgs").scrollTop = 1e6;
  };
  $$("#sugg button").forEach((b) => b.onclick = () => ask(b.textContent));
  $("#askForm").onsubmit = (e) => { e.preventDefault(); const q = $("#askIn").value.trim(); $("#askIn").value = ""; ask(q); };
}

// ================================================================ 05 SOURCES
function pageHead(n, title, sub) {
  return `<div class="pagehead"><span class="idx">${n}/</span><div><h1>${title}</h1><small class="mono small muted">${sub}</small></div>
    <button class="btn back" id="back">‹ BACK TO THE ANSWER</button></div>`;
}
function renderSources() {
  setProgress(0); setNav("find");
  const R = S.result; if (!R) return go("find");
  const ag = R.agreement || {}, I = R.images;
  const ok = ag.verdict === "Confirmed", part = ag.verdict === "Partly confirmed";
  const max = Math.max(ag.nisar_water_ha || 0, ag.opera_water_ha || 0, 1);
  const bar = (l, v, st) => `<div class="hbar"><span>${l}</span><span class="track"><span style="width:${100 * (v || 0) / max}%;${st}"></span></span><b>${fmt(v)}</b></div>`;
  ui(`<div class="page">${pageHead("05", "DO SOURCES AGREE?", `${esc(R.area.name.toUpperCase())} · ${dshort(R.window.after[0])} 2026 · INDEPENDENT VIEWS`)}
    ${ag.verdict ? `
    <section class="frame banner verdict ${ok ? "ok" : part ? "no" : "bad"}">${corners}
      <div><strong style="font:400 22px var(--disp)">${esc(ag.verdict.toUpperCase())}</strong><div class="hint">${ok ? "Two independent radar sources mark the same places as water." : part ? "Most of our water is confirmed; some is seen only by one source." : "The sources see different amounts of water. Read why below."}</div></div>
      <div class="row" style="margin-left:auto;gap:32px">
        <div class="num"><span class="lbl">OVERLAP</span><b>${fmt(ag.overlap_pct)}%</b></div>
        <div class="num"><span class="lbl">NISAR WATER</span><b>${fmt(ag.nisar_water_ha)} HA</b></div>
        <div class="num"><span class="lbl">NASA OPERA</span><b>${fmt(ag.opera_water_ha)} HA</b></div>
      </div></section>` : `<section class="frame state">${corners}<b>NASA OPERA CHECK NOT AVAILABLE</b><span class="hint">${esc(ag.error || "No OPERA water map was found near this date.")}</span></section>`}
    <div class="grid3">
      <figure class="frame">${corners}<div class="tileimg"><img src="${abs(I.hh)}" alt="NISAR radar after the change"><img src="${abs(I.result)}" alt="Detected change"><span class="chip cyan mono tag">${fmt(R.headline.hectares)} HA</span></div>
        <figcaption><b><span class="accent">01/</span> NISAR RADAR</b><span class="lbl">${dshort(R.window.after[0])} 2026 · L-BAND · OUR RESULT</span>Sees through cloud and at night.</figcaption></figure>
      <figure class="frame">${corners}<div class="tileimg">${ag.map_url ? `<img src="${abs(ag.map_url)}" alt="Agreement map: blue both, light blue only NISAR, amber only OPERA">` : ""}<span class="chip mono tag">${ag.opera_water_ha ? fmt(ag.opera_water_ha) + " HA" : "–"}</span></div>
        <figcaption><b><span class="accent">02/</span> AGREEMENT WITH NASA OPERA</b><span class="lbl">SENTINEL-1 · INDEPENDENT NASA PRODUCT</span>
          <span class="row small"><span><i style="display:inline-block;width:12px;height:10px;background:#1D4ED8"></i> both</span><span><i style="display:inline-block;width:12px;height:10px;background:#93C5FD"></i> only NISAR</span><span><i style="display:inline-block;width:12px;height:10px;background:#F59E0B"></i> only OPERA</span></span></figcaption></figure>
      <figure class="frame">${corners}<div class="tileimg"><img src="${esc(I.photo)}" alt="Normal satellite photo from NASA Worldview, likely cloudy" onerror="this.replaceWith(Object.assign(document.createElement('p'),{className:'hint',style:'padding:20px',textContent:'Photo not reachable right now.'}))"><span class="chip mono tag">PHOTO</span></div>
        <figcaption><b><span class="accent">03/</span> NORMAL PHOTO</b><span class="lbl">NASA WORLDVIEW · ${dshort(R.window.after[0])}</span>Context only: cloud usually hides floods.</figcaption></figure>
    </div>
    <div class="grid2">
      <section class="frame" style="padding:18px;display:flex;flex-direction:column;gap:14px">${corners}<h3>WATER BY SOURCE (HA)</h3>
        ${bar("NISAR (ours)", ag.nisar_water_ha, "background:#1D4ED8")}${bar("NASA OPERA", ag.opera_water_ha, "background:#60A5FA")}${bar("Both agree", ag.both_ha, "background:repeating-linear-gradient(90deg,#7DD3FC 0 2px,transparent 2px 5px);border:1px solid #7DD3FC")}
        ${ag.single_pass ? `<p class="hint small">Single pass ${dshort(ag.single_pass.date)} alone: ${fmt(ag.single_pass.nisar_water_ha)} ha, ${fmt(ag.single_pass.overlap_pct)}% overlap. Our answer uses water seen on both later passes.</p>` : ""}</section>
      <section class="frame" style="padding:18px;display:flex;flex-direction:column;gap:10px">${corners}<h3>WHY THE NUMBERS CAN DIFFER</h3>
        <div class="reason"><span class="lbl">01 · TIMING</span>OPERA looked on one day; our answer needs water on both later passes.</div>
        <div class="reason"><span class="lbl">02 · WAVELENGTH</span>NISAR's longer L-band wave sees water under crops that C-band can miss, and wet fields can confuse both.</div>
        <div class="reason"><span class="lbl">03 · DETAIL</span>OPERA uses 30 m squares, ours 20 m, so edges are counted differently.</div></section>
    </div></div>`);
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
      ${stat("OVERLAP WITH NASA OPERA", ag.overlap_pct !== undefined ? fmt(ag.overlap_pct) + "%" : "–", "Share of our water that NASA's own map confirms.")}
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
      <section class="frame" style="padding:18px;display:flex;flex-direction:column;gap:12px">${corners}<h3>LIMITS · WHAT COULD BE WRONG</h3>
        <ul class="list">${R.limits.map((l) => `<li><span>${esc(l)}</span></li>`).join("")}</ul>
        <h3>HOW THIS RESULT WAS MADE</h3>
        <table class="datatable"><tbody>
          <tr><td>Water cut-off</td><td class="mono">HH < ${P.threshold_db} dB${P.threshold_hv_db !== null && P.threshold_hv_db !== undefined ? ` and HV < ${P.threshold_hv_db} dB` : ""} (${esc(P.threshold_mode || "")})</td></tr>
          <tr><td>Grid</td><td class="mono">${P.resolution_m} m · EPSG ${P.epsg}</td></tr>
          <tr><td>Unreadable area</td><td class="mono">${Math.round(P.masked_fraction * 100)}%</td></tr>
          <tr><td>Change seen on every later pass</td><td class="mono">${Math.round(P.persistence * 100)}%</td></tr>
          <tr><td>Time taken</td><td class="mono">${P.seconds} s</td></tr></tbody></table></section>
      <section class="frame" style="padding:18px;display:flex;flex-direction:column;gap:12px">${corners}<h3>DATA USED</h3>
        <table class="datatable"><thead><tr><th>SOURCE</th><th>USED FOR</th></tr></thead><tbody>
          ${R.passes.filter((p) => p.used).map((p) => `<tr><td>NISAR GCOV ${dshort(p.date)}</td><td>${esc(p.quality)} · track ${esc(p.track)} ${esc(p.direction)}</td></tr>`).join("")}
          ${(R.credits && R.credits.sources || []).map((s) => `<tr><td><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a></td><td>${esc(s.used_for || "")}</td></tr>`).join("")}
        </tbody></table>${R.credits && R.credits.notice ? `<p class="hint small">${esc(R.credits.notice)}</p>` : ""}</section>
    </div>` : `<section class="frame state">${corners}<b>RUN AN ANALYSIS TO SEE ITS EVIDENCE</b><button class="btn primary" id="startFind">FIND A PLACE ›</button></section>`}
    <section class="frame" style="padding:18px">${corners}<h3>LEARN MORE</h3><ul class="list" id="learn" style="margin-top:10px"></ul></section>
  </div>`);
  const back = $("#back"); if (back) { back.onclick = () => go(R ? "answer" : "find"); if (!R) back.textContent = "‹ BACK"; }
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
  ui(`<div class="page">${pageHead("07", "WHY DID IT CHANGE?", `${esc(R.area.name.toUpperCase())} · ${fmt(R.headline.hectares)} HA · ${dshort(R.window.before.at(-1))} → ${dshort(R.window.after[0])}`)}
    <div class="row"><span class="chip amber">INTERPRETATION · NOT A MEASUREMENT</span></div>
    <section class="frame cyan banner">${corners}<span class="lbl">MOST LIKELY CAUSE</span>
      <strong style="font:400 20px var(--disp)">${top.length ? esc(top.map((d) => d.name).join(" + ").toUpperCase()) : "NO CAUSE HAS STRONG EVIDENCE YET"}</strong>
      <span class="hint" style="margin-left:auto;max-width:380px">${D.filter((d) => d.verdict === "Not supported").length} cause(s) were checked and ruled out; ${D.filter((d) => d.verdict === "Not checked").length} could not be checked.</span></section>
    <div class="grid2">
      <section class="frame" style="padding:18px;display:flex;flex-direction:column;gap:10px;min-height:340px">${corners}<h3>DAILY RAIN OVER THE AREA (MM) · NISAR PASSES MARKED</h3>
        ${rain.length ? '<div style="flex:1;position:relative;min-height:260px"><canvas id="cRain" role="img" aria-label="Daily rainfall"></canvas></div>' : '<p class="hint">No rainfall file for this area yet. Run <span class="mono">prepare_demo.py</span> to fetch NASA POWER rainfall.</p>'}</section>
      <section class="frame" style="padding:18px;display:flex;flex-direction:column;gap:10px">${corners}<h3>POSSIBLE CAUSES · CHECKED AGAINST EVIDENCE</h3>
        ${D.map((d, i) => `<article class="driver ${d.verdict === "Likely" ? "top" : ""}"><header><span class="mono small accent">0${i + 1}</span><h4>${esc(d.name)}</h4><span class="badge ${vcls(d.verdict)}">${esc(d.verdict.toUpperCase())}</span></header>
          <p style="margin:0;color:var(--soft)">${esc(d.evidence)}</p><span class="lbl">EVIDENCE · ${esc(d.source.toUpperCase())}</span></article>`).join("")}</section>
    </div>
    <section class="frame" style="padding:18px">${corners}<h3>WHAT'S NEXT FOR NISAR HERE</h3><ul class="list" id="next" style="margin-top:10px"></ul></section>
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
  ui(`<aside class="side left frame" style="width:460px">${corners}
    <div class="screenhead"><span class="idx">··/</span><h1>STORIES</h1></div>
    <p class="hint">Real 2026 events, each a guided path: find the place, check the data, see what changed and why.</p>
    ${demoAreas.map((d, i) => `<article class="driver"><header><span class="mono small accent">0${i + 1}</span><h4>${esc(d.name)}</h4></header>
      <p style="margin:0;color:var(--soft)">${esc(d.story || "")}</p><span class="lbl">CHANGE DATE · ${dshort(d.event_date)} 2026</span>
      <div class="row"><button class="btn small primary" data-story="${i}">OPEN STORY ›</button></div></article>`).join("") || '<p class="hint">No stories configured.</p>'}
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
    toast("Watching this place. We'll mark it when a new NISAR pass arrives.");
  } catch (err) { toast(err.message); }
}
async function openWatch() {
  setNav("watch");
  const ov = $("#overlay");
  ov.innerHTML = `<div class="overlay"><div class="frame">${corners}<div class="screenhead"><span class="idx">··/</span><h1>WATCH LIST</h1></div>
    <p class="hint">Watched places are re-checked every hour for a new NISAR pass (every 12 days).</p><div id="wl"><div class="skeleton" style="height:60px"></div></div>
    <div class="row"><button class="btn" id="wCheck">CHECK NOW</button><button class="btn" id="wClose">CLOSE</button></div></div></div>`;
  const draw = (items) => $("#wl").innerHTML = items.length ? items.map((w) => `<div class="watchrow"><div><b>${esc(w.name)}</b><div class="hint small">Last result ${w.last_result_date ? dshort(w.last_result_date) : "–"} · newest pass ${w.newest_pass ? dshort(w.newest_pass) : "not checked yet"}</div></div>
      ${w.new_pass_available ? '<span class="chip cyan">NEW PASS AVAILABLE</span>' : '<span class="chip">UP TO DATE</span>'}<button class="btn small" data-del="${w.id}" aria-label="Stop watching ${esc(w.name)}">REMOVE</button></div>`).join("")
    : '<p class="hint">You are not watching any place yet. Use "Watch this place" on an answer.</p>';
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
    <p>${dshort(R.window.before.at(-1))} → ${dshort(R.window.after[0])} 2026 · NISAR track ${esc(R.track.track)} ${esc(R.track.direction)} · ${esc([...new Set(R.passes.filter((p) => p.used).map((p) => p.quality))].join("/"))} data${R.source === "sample" ? " · SAMPLE DATA" : ""}</p>
    <h2 style="font-size:22pt;margin:6pt 0">${esc(R.headline.label)}: ${fmt(R.headline.hectares)} ha <span style="font-size:12pt;color:#555">(about ${fmt(R.headline.football_pitches)} football pitches)</span></h2>
    <p><b>Confidence: ${esc(R.confidence.level)}.</b> ${esc(R.confidence.reason)}</p>
    <div style="position:relative"><img src="${abs(R.images.hh)}" alt="NISAR HH radar after the change"><img src="${abs(R.images.result)}" alt="Detected change" style="position:absolute;inset:0"></div>
    <table><tr><th>Measured</th><td>${esc(R.measured)}</td></tr><tr><th>What it likely means</th><td>${esc(R.interpreted)}</td></tr>
      <tr><th>Became water / receded / permanent</th><td>${fmt(R.areas_ha.became_water)} / ${fmt(R.areas_ha.water_receded)} / ${fmt(R.areas_ha.permanent_water)} ha</td></tr>
      <tr><th>NASA OPERA check</th><td>${ag.verdict ? `${esc(ag.verdict)} · ${fmt(ag.overlap_pct)}% of our water confirmed` : "not available"}</td></tr>
      <tr><th>Likely causes (interpretation)</th><td>${(R.drivers || []).filter((d) => d.verdict !== "Not checked").map((d) => `${esc(d.name)}: ${esc(d.verdict)}`).join("; ")}</td></tr></table>
    <h3 style="margin:10pt 0 4pt">What happened here, in plain words</h3>
    <p><b>${esc(plainStory(R).lead)}</b></p>
    ${plainStory(R).items.map(([, t, body]) => `<p style="margin:3pt 0"><b>${t.charAt(0) + t.slice(1).toLowerCase()}:</b> ${body.replace(/<(?!\/?b>)[^>]+>/g, "")}</p>`).join("")}
    <p><b>Limits.</b> ${esc(R.limits.join(" "))}</p>
    <p style="font-size:9pt;color:#555">Made with NISAR Change Explorer. Radar: NASA–ISRO NISAR (ASF DAAC). ${esc((R.credits && R.credits.sources || []).map((s) => s.title).join(", "))}. ${esc(R.credits && R.credits.notice || "")} Link: ${esc(location.origin + location.pathname + "?r=" + R.id)}</p>`;
  setTimeout(() => window.print(), 300);
}

// ================================================================ EDGE STATES
function renderNotEnough(msg, detail) {
  setProgress(3);
  ui(`<aside class="side right frame" style="width:440px" role="alert">${corners}
    <div class="screenhead"><span class="idx">!/</span><h1 style="color:#FCD34D">NOT ENOUGH DATA YET</h1></div>
    <p>${esc(msg)}</p>
    ${detail && detail.before ? `<p class="hint">Passes before: ${detail.before.map(dshort).join(", ") || "none"} · after: ${detail.after.map(dshort).join(", ") || "none"}</p>` : ""}
    <div class="row"><button class="btn primary" id="neWatch">WATCH AND TELL ME</button><button class="btn" id="neDate">CHOOSE ANOTHER DATE</button><button class="btn" id="neArea">USE ANOTHER AREA</button></div>
  </aside>`);
  $("#neWatch").onclick = addWatch; $("#neDate").onclick = () => go("ask"); $("#neArea").onclick = () => go("find");
}
function renderError(err, from) {
  ui(`<aside class="side right frame" style="width:460px" role="alert">${corners}
    <div class="screenhead"><span class="idx">!/</span><h1 style="color:#FCA5A5">${err.offline ? "CAN'T REACH THE SERVER" : "SOMETHING WENT WRONG"}</h1></div>
    <p>${esc(err.message)}</p>
    <div class="frame state" style="border-style:dashed;border-color:#FBBF24">${corners}<span class="lbl" style="color:#FBBF24">SAVED SAMPLE · NOT LIVE</span>
      <span class="hint">Open a labelled sample result so you can still explore every screen.</span><button class="btn" id="openSample">OPEN SAVED SAMPLE</button></div>
    <div class="row"><button class="btn primary" id="retry">TRY AGAIN</button><button class="btn" id="home2">START AGAIN</button></div>
  </aside>`);
  $("#retry").onclick = () => go(from || "find"); $("#home2").onclick = () => go("find");
  $("#openSample").onclick = async () => { try { S.result = await api("/sample"); go("answer"); } catch (e) { toast("Sample not reachable either: is the server running?"); } };
}


// ---------------------------------------------------------------- welcome screen
function runIntro(show) {
  const el = $("#intro");
  if (!show) { el.remove(); return; }
  const name = "NISAR CHANGE EXPLORER", title = $("#introTitle");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const t0 = reduce ? 0.2 : 1.75;   // name starts when the globe lands
  title.innerHTML = [...name].map((ch, i) => ch === " " ? '<span class="sp"> </span>' : `<span style="animation-delay:${(t0 + i * 0.06).toFixed(2)}s">${ch}</span>`).join("");
  const after = t0 + name.length * 0.06 + 0.25;
  $(".intro-tag", el).style.animationDelay = after + "s";
  $(".intro-go", el).style.animationDelay = (after + 0.35) + "s";
  if (!reduce) setTimeout(() => el.classList.add("impact"), 1330);
  const leave = () => {
    if (el.classList.contains("leaving")) return;
    el.classList.add("leaving"); document.removeEventListener("keydown", key);
    setTimeout(() => { el.remove(); $("#q") && $("#q").focus(); }, 700);
  };
  const key = (e) => { if (e.key === "Enter" || e.key === "Escape") leave(); };
  $("#introGo").onclick = leave; $("#introSkip").onclick = leave; document.addEventListener("keydown", key);
  setTimeout(() => $("#introGo").focus(), (after + 0.4) * 1000);
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
