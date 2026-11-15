const pptxgen = require("pptxgenjs");
const { applyTheme } = require("/home/sanjayvasudevan/.claude/skills/synced/162057ab-16e1-4c33-a7f3-f6a8ec41a4fc_c983e226-d5a7-4b6e-9384-ba9b242acc35/pptx/scripts/apply_theme.js");

const OUT = process.argv[2];
const THEME = {
  name: "Radar Water",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "0B1F2A", lt1: "FFFFFF", dk2: "12404F", lt2: "E8F0F3",
    accent1: "1B9AAA", accent2: "F2A541", accent3: "6FB3C0", accent4: "D9552B",
    accent5: "4A6572", accent6: "8DB255", hlink: "1B9AAA", folHlink: "4A6572",
  },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "NISAR Change Explorer";
pres.author = "Sanjay Vasudevan";
const C = pres.SchemeColor;

pres.defineSlideMaster({
  title: "DARK", background: { color: "0B1F2A" },
  objects: [
    { text: { text: "NISAR Change Explorer", options: { x: 0.5, y: 5.2, w: 5, h: 0.25, fontSize: 10, color: "6FB3C0", margin: 0 } } },
  ],
  slideNumber: { x: 9.0, y: 5.2, w: 0.5, h: 0.25, fontSize: 10, color: "6FB3C0", align: "right", margin: 0 },
});
pres.defineSlideMaster({
  title: "LIGHT", background: { color: "FFFFFF" },
  objects: [
    { text: { text: "NISAR Change Explorer", options: { x: 0.5, y: 5.2, w: 5, h: 0.25, fontSize: 10, color: "4A6572", margin: 0 } } },
  ],
  slideNumber: { x: 9.0, y: 5.2, w: 0.5, h: 0.25, fontSize: 10, color: "4A6572", align: "right", margin: 0 },
});

const H = (s, text, dark) => s.addText(text, { isTextBox: true, margin: 0, x: 0.5, y: 0.35, w: 9, h: 0.85, fontFace: "Cambria", fontSize: 34, bold: true, color: dark ? "FFFFFF" : "0B1F2A", valign: "middle", objectName: "title" });
const T = (s, text, o) => s.addText(text, { isTextBox: true, margin: 0, fontFace: "Calibri", ...o });

// ---------- 1. Title ----------
{
  const s = pres.addSlide({ masterName: "DARK" });
  T(s, "NASA SPACE APPS 2026  ·  DANCING WITH THE SARS", { x: 0.6, y: 0.7, w: 8.8, h: 0.3, fontSize: 12, color: "6FB3C0", charSpacing: 2, objectName: "kicker" });
  s.addText("Where did the water go?", { isTextBox: true, margin: 0, x: 0.6, y: 1.25, w: 6.4, h: 1.8, fontFace: "Cambria", fontSize: 48, bold: true, color: "FFFFFF", valign: "top", objectName: "title" });
  T(s, "NISAR Change Explorer reads L-band radar through cloud and night, shows where water likely appeared or left, and compares the result with NASA's OPERA water maps.", { x: 0.6, y: 3.1, w: 6.2, h: 1.1, fontSize: 18, color: "E8F0F3", valign: "top", objectName: "subtitle" });
  // concentric ripple motif (water)
  [[7.2, 1.0, 2.6, 18], [7.65, 1.45, 1.7, 40], [8.1, 1.9, 0.8, 70]].forEach(([x, y, d, t], i) =>
    s.addShape(pres.ShapeType.ellipse, { x, y, w: d, h: d, fill: { color: "1B9AAA", transparency: t }, line: { color: "6FB3C0", width: 1, transparency: 40 }, objectName: "ripple" + i }));
  T(s, [
    { text: "TEAM", options: { bold: true, color: "F2A541", fontSize: 11, charSpacing: 2, breakLine: true } },
    { text: "Abilash (lead)  ·  Sanjay Vasudevan  ·  Arshad", options: { breakLine: true } },
    { text: "Arya  ·  Nevedha  ·  Vishal" },
  ], { x: 0.6, y: 4.3, w: 8.4, h: 0.8, fontSize: 14, color: "E8F0F3", valign: "top", paraSpaceAfter: 3, objectName: "team" });
  s.addNotes("Open with the question, not the technology. People want to know where the water went; radar can answer it, but the data is hard to use.");
}

// ---------- 2. What it does ----------
{
  const s = pres.addSlide({ masterName: "LIGHT" });
  H(s, "Pick a place. Ask what changed.", false);
  T(s, "THE PROBLEM", { x: 0.5, y: 1.45, w: 4.2, h: 0.3, fontSize: 12, bold: true, color: "4A6572", charSpacing: 2 });
  T(s, [
    { text: "NISAR L-band radar sees through cloud and night, so it works when photos fail.", options: { bullet: true, breakLine: true } },
    { text: "Each pass is a 2 to 7 GB file. Most people never open one.", options: { bullet: true, breakLine: true } },
    { text: "A clean change map with no caveats is worse than no map.", options: { bullet: true } },
  ], { x: 0.5, y: 1.85, w: 4.2, h: 2.9, fontSize: 16, color: "0B1F2A", valign: "top", paraSpaceAfter: 10 });
  s.addShape(pres.ShapeType.roundRect, { x: 5.1, y: 1.45, w: 4.4, h: 3.4, rectRadius: 0.12, fill: { color: C.background2 }, line: { type: "none" }, objectName: "get-card" });
  T(s, "WHAT YOU GET BACK", { x: 5.4, y: 1.7, w: 3.8, h: 0.3, fontSize: 12, bold: true, color: "12404F", charSpacing: 1 });
  const gets = ["A before and after view", "Where water likely appeared or left, in hectares", "A comparison with NASA OPERA water maps", "A confidence level with the reason", "What was measured, and where it failed", "\"Insufficient data\" when passes are too few"];
  T(s, gets.map((g, i) => ({ text: g, options: { bullet: true, breakLine: i < gets.length - 1 } })), { x: 5.4, y: 2.1, w: 3.8, h: 2.6, fontSize: 14, color: "0B1F2A", valign: "top", paraSpaceAfter: 6 });
  s.addNotes("Likely, never confirmed. Fewer than two good passes a side, or over 30 percent masked, gives insufficient data and no number.");
}

// ---------- 3. How it works ----------
{
  const s = pres.addSlide({ masterName: "LIGHT" });
  H(s, "How it works", false);
  const steps = [
    ["1", "Check", "One track, one direction. Two passes before, two after."],
    ["2", "Fetch", "Read only the study window (25 km at most) from each huge file."],
    ["3", "Prepare", "Validity mask, speckle filter, steep slopes masked."],
    ["4", "Detect", "Water before vs after on the L-band HH and HV channels. Must stay dark on every after pass."],
    ["5", "Compare", "Overlap with OPERA water maps where a tile exists. OPERA is not ground truth."],
    ["6", "Explain", "Confidence label, area, known failures, what was not checked."],
  ];
  steps.forEach(([n, h, d], i) => {
    const col = i % 3, row = Math.floor(i / 3);
    const x = 0.5 + col * 3.07, y = 1.35 + row * 1.62;
    s.addShape(pres.ShapeType.roundRect, { x, y, w: 2.86, h: 1.5, rectRadius: 0.12, fill: { color: C.background2 }, line: { type: "none" }, objectName: "step" + n });
    s.addShape(pres.ShapeType.ellipse, { x: x + 0.18, y: y + 0.17, w: 0.42, h: 0.42, fill: { color: i % 2 ? "12404F" : "1B9AAA" }, line: { type: "none" }, objectName: "num" + n });
    T(s, n, { x: x + 0.18, y: y + 0.17, w: 0.42, h: 0.42, fontSize: 16, bold: true, color: "FFFFFF", align: "center", valign: "middle" });
    T(s, h, { x: x + 0.72, y: y + 0.17, w: 2.0, h: 0.42, fontSize: 20, bold: true, color: "0B1F2A", valign: "middle", fontFace: "Cambria" });
    T(s, d, { x: x + 0.18, y: y + 0.7, w: 2.52, h: 0.76, fontSize: 13, color: "0B1F2A", valign: "top" });
  });
  T(s, [
    { text: "The rule we do not bend:  ", options: { bold: true, color: "D9552B" } },
    { text: "under 2 good passes a side, or over 30% masked: \"insufficient data\", no number." },
  ], { x: 0.5, y: 4.62, w: 9, h: 0.35, fontSize: 14, color: "0B1F2A", valign: "middle" });
  s.addNotes("Sources: NISAR GCOV (ASF DAAC), NASA OPERA DSWx, Copernicus DEM, ESA WorldCover. Confidence is a rule-based label, not a probability.");
}

// ---------- 4. Measured ----------
{
  const s = pres.addSlide({ masterName: "LIGHT" });
  H(s, "What we measured, honestly", false);
  T(s, "Overlap (IoU) of our new water with OPERA new water, by window. Line = interval where we have one.", { x: 0.5, y: 1.2, w: 9, h: 0.3, fontSize: 12, color: "4A6572", valign: "top" });
  const PX = 3.5, PW = 4.0, y0 = 1.65, RH = 0.43;
  const rows = [
    ["Tonle Sap east half", "not used for sweeps", 0.68, 0.64, 0.72, "0.68", false],
    ["Tonle Sap west half", "tuning half", 0.69, 0.60, 0.74, "0.69", false],
    ["Window in between", "west 0.01, east 0.78", 0.55, 0.30, 0.72, "0.55", false],
    ["Cropland, 50 km south", "fresh, never tuned on", 0.04, 0.02, 0.07, "0.04", true],
    ["Sentinel-2, in between", "optical check, no interval", 0.14, null, null, "0.14", true],
    ["Sentinel-2, Kanpur", "optical check, no interval", 0.03, null, null, "0.03", true],
  ];
  // grid + axis
  [0, 0.25, 0.5, 0.75, 1].forEach((v) => {
    const x = PX + v * PW;
    s.addShape(pres.ShapeType.line, { x, y: y0 - 0.05, w: 0, h: RH * rows.length + 0.1, line: { color: "D5E1E5", width: 0.75 }, objectName: "grid" });
    T(s, v.toFixed(2).replace(/0$/, ""), { x: x - 0.25, y: y0 + RH * rows.length + 0.07, w: 0.5, h: 0.2, fontSize: 10, color: "4A6572", align: "center", valign: "top" });
  });
  rows.forEach(([name, sub, v, lo, hi, lab, bad], i) => {
    const y = y0 + i * RH, cy = y + RH / 2;
    const col = bad ? "D9552B" : "1B9AAA";
    T(s, name, { x: 0.5, y: y + 0.02, w: 2.95, h: 0.22, fontSize: 12, bold: true, color: "0B1F2A", valign: "top" });
    T(s, sub, { x: 0.5, y: y + 0.22, w: 2.95, h: 0.18, fontSize: 9, color: "4A6572", valign: "top" });
    s.addShape(pres.ShapeType.rect, { x: PX, y: cy - 0.1, w: Math.max(v * PW, 0.03), h: 0.2, fill: { color: col, transparency: lo === null ? 45 : 0 }, line: { type: "none" }, objectName: "bar" + i });
    if (lo !== null) {
      s.addShape(pres.ShapeType.line, { x: PX + lo * PW, y: cy, w: (hi - lo) * PW, h: 0, line: { color: "0B1F2A", width: 2 }, objectName: "ci" + i });
      [lo, hi].forEach((e) => s.addShape(pres.ShapeType.line, { x: PX + e * PW, y: cy - 0.1, w: 0, h: 0.2, line: { color: "0B1F2A", width: 2 }, objectName: "cap" + i }));
    }
    T(s, lab, { x: PX + PW + 0.12, y: cy - 0.14, w: 0.8, h: 0.28, wrap: false, fontSize: 14, bold: true, color: bad ? "D9552B" : "12404F", valign: "middle", fontFace: "Cambria" });
  });
  T(s, "Red: failures. Sentinel-2 bars are a different reference, not comparable with OPERA bars.", { x: 0.5, y: 4.6, w: 5.2, h: 0.2, fontSize: 10, color: "4A6572", valign: "top" });
  s.addShape(pres.ShapeType.roundRect, { x: 8.6, y: 1.55, w: 0.9, h: 2.7, rectRadius: 0.08, fill: { color: "E8F0F3" }, line: { type: "none" }, objectName: "pr" });
  T(s, [
    { text: "East half", options: { bold: true, breakLine: true } },
    { text: "precision", options: { breakLine: true, color: "4A6572" } },
    { text: "0.88", options: { bold: true, fontSize: 18, fontFace: "Cambria", breakLine: true } },
    { text: "recall", options: { breakLine: true, color: "4A6572" } },
    { text: "0.75", options: { bold: true, fontSize: 18, fontFace: "Cambria" } },
  ], { x: 8.62, y: 1.65, w: 0.86, h: 2.5, fontSize: 10, color: "12404F", align: "center", valign: "middle" });
  T(s, "One season, one place. It does not transfer. OPERA is not ground truth. No human-labelled accuracy yet.", { x: 0.5, y: 4.82, w: 9, h: 0.3, fontSize: 12, bold: true, color: "0B1F2A", valign: "top" });
  s.addNotes("East half was not used in the west sweeps but was seen when the final setting was picked, and it adjoins the tuning half: not an independent test. Intervals are a block bootstrap within each window and ignore the much larger spread between places. The fresh east window could not be scored beyond a 21 percent strip, so we make no claim there. Scene-calibrated thresholds were tried and failed.");
}

// ---------- 5. Honesty features ----------
{
  const s = pres.addSlide({ masterName: "LIGHT" });
  H(s, "What the app does about it", false);
  T(s, "Confidence is a rule-based label. It is not a probability.", { x: 0.5, y: 1.25, w: 9, h: 0.3, fontSize: 14, color: "4A6572", valign: "top" });
  const lad = [
    ["High", "Needs OPERA to agree on 75% of our new-water pixels. Only the tuned Tonle Sap window gets it.", "1B9AAA", "FFFFFF"],
    ["Medium", "A place not checked, or under 100 ha of new water, is capped here. Kanpur lands here. Medium is not \"mapped well\".", "6FB3C0", "0B1F2A"],
    ["Lower", "Most new water on cropland with no OPERA agreement, or OPERA agreement under 50%, or more than 15% unreadable. Morigaon lands here.", "F2A541", "0B1F2A"],
  ];
  lad.forEach(([lvl, d, col, tc], i) => {
    const y = 1.7 + i * 0.95;
    s.addShape(pres.ShapeType.roundRect, { x: 0.5, y, w: 1.4, h: 0.8, rectRadius: 0.1, fill: { color: col }, line: { type: "none" }, objectName: "lvl" + i });
    T(s, lvl, { x: 0.5, y, w: 1.4, h: 0.8, fontSize: 18, bold: true, color: tc, align: "center", valign: "middle", fontFace: "Cambria" });
    s.addShape(pres.ShapeType.roundRect, { x: 2.0, y, w: 3.7, h: 0.8, rectRadius: 0.1, fill: { color: C.background2 }, line: { type: "none" }, objectName: "lvlbody" + i });
    T(s, d, { x: 2.15, y, w: 3.45, h: 0.8, fontSize: 11, color: "0B1F2A", valign: "middle" });
  });
  T(s, "ALSO IN EVERY RESULT", { x: 6.1, y: 1.7, w: 3.4, h: 0.3, fontSize: 12, bold: true, color: "4A6572", charSpacing: 2 });
  T(s, [
    { text: "A validation block: what was measured, the known failures, whether this place was checked, and \"human-labelled accuracy: not measured\".", options: { bullet: true, breakLine: true } },
    { text: "A pass that is off by more than 1.5 dB over stable land cannot support High.", options: { bullet: true, breakLine: true } },
    { text: "Insufficient data when passes are too few. No number.", options: { bullet: true } },
  ], { x: 6.1, y: 2.05, w: 3.4, h: 2.7, fontSize: 13, color: "0B1F2A", valign: "top", paraSpaceAfter: 8 });
  T(s, "The 100 ha, 1.5 dB and 50% limits are provisional. One was changed after we saw a result.", { x: 0.5, y: 4.62, w: 9, h: 0.4, fontSize: 12, bold: true, color: "D9552B", valign: "top" });
  s.addNotes("The cropland rule was refined after the first run put the best-agreeing window at Lower. That moved the tuned window from Lower to High. This is a post hoc choice, not an independent result.");
}

// ---------- 6. Calamity feed and stories ----------
{
  const s = pres.addSlide({ masterName: "LIGHT" });
  H(s, "Recent events, and two stories", false);
  s.addChart(pres.charts.BAR, [{ name: "Events", labels: ["Enough for before/after", "Waiting for after-pass", "None"], values: [49, 38, 22] }], {
    x: 0.5, y: 1.3, w: 4.4, h: 3.1, barDir: "bar", chartColors: ["1B9AAA", "F2A541", "4A6572"], barGapWidthPct: 40,
    showTitle: true, title: "109 recent flood and storm events", titleFontSize: 13, titleColor: "0B1F2A", titleFontFace: "+mn-lt",
    showValue: true, dataLabelPosition: "outEnd", dataLabelColor: "0B1F2A", dataLabelFontSize: 12, dataLabelFontFace: "+mn-lt",
    showLegend: false, catAxisLabelColor: "0B1F2A", valAxisLabelColor: "4A6572", catAxisLabelFontSize: 10, valAxisLabelFontSize: 10,
    catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", catAxisOrientation: "maxMin",
    valGridLine: { color: "D5E1E5", size: 0.75 }, catGridLine: { style: "none" }, valAxisMinVal: 0, valAxisMaxVal: 60, valAxisMajorUnit: 20,
  });
  T(s, "4 live sources: NASA EONET, GDACS, USGS, Copernicus EMS. 19 of the 22 are open-ocean storms.", { x: 0.5, y: 4.45, w: 4.4, h: 0.5, fontSize: 10, color: "4A6572", valign: "top" });
  const st = [
    ["Kanpur, Uttar Pradesh", "Little net flood: 68 ha new water, 68 ha receded. Sentinel-2 marks only 14% of those pixels as new. Medium.", "12404F"],
    ["Morigaon, Assam", "3,299 ha new water. No OPERA tile near the dates, so no reference. Lower.", "4A6572"],
  ];
  st.forEach(([h, d, col], i) => {
    const y = 1.35 + i * 1.75;
    s.addShape(pres.ShapeType.roundRect, { x: 5.2, y, w: 4.3, h: 1.6, rectRadius: 0.12, fill: { color: C.background2 }, line: { type: "none" }, objectName: "story" + i });
    s.addShape(pres.ShapeType.rect, { x: 5.2, y: y + 0.2, w: 0.08, h: 1.2, fill: { color: col }, line: { type: "none" }, objectName: "storybar" + i });
    T(s, h, { x: 5.5, y: y + 0.12, w: 3.85, h: 0.35, fontSize: 17, bold: true, color: "12404F", fontFace: "Cambria", valign: "middle" });
    T(s, d, { x: 5.5, y: y + 0.55, w: 3.85, h: 1.0, fontSize: 13, color: "0B1F2A", valign: "top" });
  });
  T(s, "Real NISAR data. Neither is an accuracy test.", { x: 5.2, y: 4.85, w: 4.3, h: 0.25, fontSize: 10, color: "4A6572", valign: "top" });
  s.addNotes("Counts from the feed run of 15 Nov 2026. Kanpur: 58 ha (86%) of our pixels are water in OPERA, new or not; that does not show they are new. Morigaon last after pass is the day before the 27 Jul to 10 Aug data gap.");
}

// ---------- 7. Next ----------
{
  const s = pres.addSlide({ masterName: "DARK" });
  H(s, "What we don't know yet", true);
  T(s, "OPEN", { x: 0.5, y: 1.5, w: 4.3, h: 0.3, fontSize: 12, bold: true, color: "F2A541", charSpacing: 2 });
  const lim = [
    "Accuracy is from one season at one place, against OPERA.",
    "It failed on the cropland window to the south (0.04). Cause unknown.",
    "Scene-calibrated thresholds did not help.",
    "No accuracy against human-labelled points yet.",
  ];
  T(s, lim.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < lim.length - 1 } })), { x: 0.5, y: 1.9, w: 4.4, h: 3.1, fontSize: 14, color: "E8F0F3", valign: "top", paraSpaceAfter: 8 });
  T(s, "NEXT", { x: 5.4, y: 1.5, w: 4.1, h: 0.3, fontSize: 12, bold: true, color: "6FB3C0", charSpacing: 2 });
  const nxt = [
    "A person spot-checks labelled points on clear Sentinel-2 images.",
    "Build agreement labels to find where it fails.",
    "A learned classifier, kept only if it wins on sites it has not seen.",
    "Run the Crete, Cyclone ARNAB and Uruguay River events.",
  ];
  T(s, nxt.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < nxt.length - 1 } })), { x: 5.4, y: 1.9, w: 4.1, h: 2.4, fontSize: 14, color: "E8F0F3", valign: "top", paraSpaceAfter: 8 });
  T(s, "Treat a map as a lead to check, not a measurement.", { x: 5.4, y: 4.2, w: 4.1, h: 0.8, fontSize: 16, italic: true, color: "FFFFFF", valign: "top", fontFace: "Cambria" });
  s.addNotes("Close on honesty: likely, never confirmed. Publish the real accuracy, whatever it is.");
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();
