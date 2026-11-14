// Builds presentation/ASTRA_presentation.pptx (pptxgenjs). Run: node build_deck.js
const pptxgen = require("pptxgenjs");
const path = require("path");
const fs = require("fs");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const sharp = require("sharp");
const lu = require("react-icons/lu");
const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js");

const THEME = { name: "ASTRA Hull", headFontFace: "Calibri", bodyFontFace: "Calibri",
  colors: { dk1: "0E1726", lt1: "E6EDF7", dk2: "142035", lt2: "93A4BF", accent1: "9DB4FF", accent2: "3DD68C",
    accent3: "F2C94C", accent4: "F2994A", accent5: "EF5350", accent6: "C9B6FF", hlink: "9DB4FF", folHlink: "C9B6FF" } };
const HEX = { hull: "0E1726", panel: "142035", raised: "1B2A44", ink: "E6EDF7", muted: "93A4BF", accent: "9DB4FF",
  ok: "3DD68C", attn: "F2C94C", review: "F2994A", urgent: "EF5350", violet: "C9B6FF" };
const SHOTS = path.join(__dirname, "..", "docs", "screenshots");

async function icon(name, color) {
  const svg = renderToStaticMarkup(React.createElement(lu[name], { color: "#" + color, size: 256 }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  pres.title = "ASTRA — NASA Space Apps Challenge 2026";
  pres.author = "ASTRA team";
  const C = pres.SchemeColor;

  pres.defineSlideMaster({ title: "ASTRA_TITLE", background: { color: HEX.hull }, objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.3, w: 11.7, h: 1.4, fontSize: 60, bold: true, color: HEX.ink, charSpacing: 6, align: "left" }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 3.8, w: 11.0, h: 1.6, fontSize: 22, color: HEX.muted }, text: "" } },
  ] });
  pres.defineSlideMaster({ title: "ASTRA_CONTENT", background: { color: HEX.hull }, slideNumber: { x: 12.5, y: 7.0, color: HEX.muted, fontSize: 10 }, objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 12.1, h: 0.9, fontSize: 36, bold: true, color: HEX.ink, align: "left" }, text: "" } },
    { text: { text: "ASTRA · NASA Space Apps 2026 · all crew data shown is synthetic", options: { x: 0.6, y: 7.0, w: 9, h: 0.3, fontSize: 10, color: HEX.muted } } },
  ] });

  const notesFor = {};
  const card = (s, x, y, w, h, fill = HEX.panel) => s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color: "29405F", width: 1 } });
  const txt = (s, t, o) => s.addText(t, { isTextBox: true, margin: 0, color: HEX.ink, fontSize: 15, valign: "top", ...o });

  // 1 Title
  pres.addSection({ title: "Introduction" });
  let s = pres.addSlide({ masterName: "ASTRA_TITLE", sectionTitle: "Introduction" });
  s.addText("ASTRA", { placeholder: "title" });
  s.addText("Astronaut Self-assessment, Tracking and Response Assistant\nHealth monitoring and medical decision support that keeps working when Earth is 20 light-minutes away", { placeholder: "body" });
  s.addShape(pres.shapes.OVAL, { x: 10.4, y: 0.9, w: 1.6, h: 1.6, fill: { color: HEX.hull }, line: { color: HEX.accent, width: 10 } });
  s.addShape(pres.shapes.OVAL, { x: 10.85, y: 1.35, w: 0.7, h: 0.7, fill: { color: HEX.ok }, line: { color: HEX.ok, width: 0 } });
  txt(s, "NASA Space Apps Challenge 2026 · Health Monitoring Software for Astronauts on Space Missions", { x: 0.8, y: 6.3, w: 11, h: 0.4, fontSize: 14, color: HEX.violet });
  s.addNotes("ASTRA is a decision-support prototype for long missions. It is not an autonomous doctor. Everything you will see uses synthetic crew data.");

  // 2 Problem: five hazards
  s = pres.addSlide({ masterName: "ASTRA_CONTENT", sectionTitle: "Introduction" });
  s.addText("Five hazards, one crew, no ambulance", { placeholder: "title" });
  const hz = [["LuRadiation", "Space radiation", "Invisible; only dosimeters measure it"], ["LuUsers", "Isolation and confinement", "Mood, sleep, workload, team"],
    ["LuSatelliteDish", "Distance from Earth", "Delayed or no real-time medical help"], ["LuOrbit", "Gravity fields", "Heart, bones, muscles, balance, eyes"],
    ["LuWind", "Hostile and closed environment", "CO₂, air, water, food, microbes"]];
  for (let i = 0; i < hz.length; i++) {
    const x = 0.6 + i * 2.45;
    card(s, x, 1.6, 2.25, 3.6);
    s.addImage({ data: await icon(hz[i][0], HEX.accent), x: x + 0.7, y: 1.95, w: 0.85, h: 0.85 });
    txt(s, hz[i][1], { x: x + 0.2, y: 3.0, w: 1.85, h: 0.8, fontSize: 17, bold: true, align: "center" });
    txt(s, hz[i][2], { x: x + 0.2, y: 3.85, w: 1.85, h: 1.1, fontSize: 14, color: HEX.muted, align: "center" });
  }
  txt(s, "The challenge asks for blood pressure, heart rate, blood glucose, body temperature, sleep duration and mood — and for software that helps astronauts evaluate and respond to change on their own.", { x: 0.6, y: 5.6, w: 12, h: 0.9, fontSize: 16 });
  s.addNotes("NASA's Human Research Program groups spaceflight risks under five hazards. On a Mars transit, a question to a flight surgeon can take 40 minutes round-trip. The crew needs onboard tools.");

  // 3 What ASTRA does
  pres.addSection({ title: "Solution" });
  s = pres.addSlide({ masterName: "ASTRA_CONTENT", sectionTitle: "Solution" });
  s.addText("Monitor, analyze, respond, coordinate", { placeholder: "title" });
  const pillars = [["LuActivity", "Monitor", "42 indicators from manual forms, medical devices, wearables and cabin sensors — one validated pipeline with full provenance"],
    ["LuChartLine", "Analyze", "Each value is compared with the astronaut's own approved baseline; trends, gaps and data quality are explained"],
    ["LuSiren", "Respond", "Four alert levels, a medical-event lifecycle, verification checklists and preloaded procedures"],
    ["LuSend", "Coordinate", "Structured medical reports queued for the ground and sent when the Earth link allows"]];
  for (let i = 0; i < 4; i++) {
    const y = 1.55 + i * 1.3;
    s.addShape(pres.shapes.OVAL, { x: 0.7, y, w: 0.95, h: 0.95, fill: { color: HEX.raised }, line: { color: HEX.accent, width: 1.5 } });
    s.addImage({ data: await icon(pillars[i][0], HEX.accent), x: 0.92, y: y + 0.22, w: 0.5, h: 0.5 });
    txt(s, pillars[i][1], { x: 1.9, y: y + 0.05, w: 2.2, h: 0.5, fontSize: 22, bold: true });
    txt(s, pillars[i][2], { x: 4.0, y: y + 0.08, w: 8.6, h: 0.9, fontSize: 16, color: HEX.muted });
  }
  s.addNotes("Four responsibilities from our specification. Everything runs on the onboard server, without internet or external AI.");

  // 4 Overview screenshot
  s = pres.addSlide({ masterName: "ASTRA_CONTENT", sectionTitle: "Solution" });
  s.addText("One glance: is anything wrong, and what do I do next?", { placeholder: "title" });
  s.addImage({ path: path.join(__dirname, "shot_overview.png"), x: 0.6, y: 1.4, w: 7.4, h: 5.4, sizing: { type: "crop", w: 7.4, h: 5.4 } });
  const pts = [["Status lamp", "Green, yellow, orange, red — grey when data is missing. Missing data is never shown as healthy."],
    ["Every value has context", "Personal baseline, z-score, age, device and quality; click for full provenance."],
    ["Labelled honestly", "Synthetic data and demonstration rules are marked everywhere."]];
  pts.forEach((p, i) => { txt(s, p[0], { x: 8.4, y: 1.5 + i * 1.75, w: 4.4, h: 0.45, fontSize: 19, bold: true, color: HEX.accent });
    txt(s, p[1], { x: 8.4, y: 1.95 + i * 1.75, w: 4.4, h: 1.1, fontSize: 15, color: HEX.ink }); });
  s.addNotes("This is the commander's overview during the synthetic emergency scenario.");

  // 5 Data pipeline
  pres.addSection({ title: "How it works" });
  s = pres.addSlide({ masterName: "ASTRA_CONTENT", sectionTitle: "How it works" });
  s.addText("Every measurement takes the same path", { placeholder: "title" });
  const steps = ["Manual form\nDevice adapter\nWearable\nCabin sensor", "Validate\nunit · range · time\nidentity · device", "Store\noriginal + canonical\nprovenance · quality", "Assess\nbaseline · rules\nsymptoms · context", "Alert & event\nprocedure · report\nreal-time update"];
  for (let i = 0; i < steps.length; i++) {
    const x = 0.6 + i * 2.5;
    card(s, x, 1.8, 2.1, 2.4, i === 0 ? HEX.raised : HEX.panel);
    txt(s, steps[i], { x: x + 0.15, y: 1.95, w: 1.8, h: 2.1, fontSize: 15, align: "center", valign: "middle" });
    if (i < steps.length - 1) s.addShape(pres.shapes.RIGHT_ARROW, { x: x + 2.13, y: 2.8, w: 0.33, h: 0.4, fill: { color: HEX.accent }, line: { color: HEX.accent } });
  }
  txt(s, "Rejected, never silently changed: unsupported units, impossible values, future timestamps, wrong astronaut for a device. Duplicates are recognised by ID, so retries are safe.", { x: 0.6, y: 4.6, w: 12, h: 0.9, fontSize: 16 });
  txt(s, "POST /api/v1/telemetry — the same API for the simulator and for any future physical device (7 adapters ready, none claimed as hardware-validated).", { x: 0.6, y: 5.6, w: 12, h: 0.8, fontSize: 15, color: HEX.muted });
  s.addNotes("Four input methods, one validation and storage path. The simulator uses the same entry points as real devices.");

  // 6 Rules honesty
  s = pres.addSlide({ masterName: "ASTRA_CONTENT", sectionTitle: "How it works" });
  s.addText("No invented medical thresholds", { placeholder: "title" });
  const cls = [["Clinician-approved", HEX.muted, "0 active", "The mechanism exists: a flight surgeon approves an individual reference range. ASTRA ships with none."],
    ["NASA operational references", HEX.ok, "2 rules", "Cabin CO₂ 1-hour average ≤ 3 mmHg (NASA-STD-3001 V2 [6004]). 8.5 h sleep period for crew scheduling ([V1 6001])."],
    ["Demonstration only", HEX.attn, "14 rules", "Statistical rules relative to each astronaut's own approved baseline, clearly labelled synthetic."]];
  cls.forEach((c, i) => { const x = 0.6 + i * 4.15; card(s, x, 1.6, 3.9, 4.4);
    txt(s, c[2], { x: x + 0.3, y: 1.85, w: 3.3, h: 0.9, fontSize: 40, bold: true, color: c[1] });
    txt(s, c[0], { x: x + 0.3, y: 2.85, w: 3.3, h: 0.5, fontSize: 19, bold: true });
    txt(s, c[3], { x: x + 0.3, y: 3.45, w: 3.3, h: 2.3, fontSize: 15, color: HEX.muted }); });
  txt(s, "Every rule is versioned, carries its source and approval status, and is stored with each assessment it produced.", { x: 0.6, y: 6.25, w: 12, h: 0.5, fontSize: 15 });
  s.addNotes("We did not make up clinical cut-offs. NASA numbers are used only for what NASA uses them for.");

  // 7 Emergency workflow
  pres.addSection({ title: "Demonstration" });
  s = pres.addSlide({ masterName: "ASTRA_CONTENT", sectionTitle: "Demonstration" });
  s.addText("Synthetic emergency, start to finish", { placeholder: "title" });
  s.addImage({ path: path.join(__dirname, "shot_response.png"), x: 0.6, y: 1.4, w: 7.4, h: 5.4, sizing: { type: "crop", w: 7.4, h: 5.4 } });
  const flow = [["Detected", "HR z +20, SpO₂ z −14, shortness of breath"], ["Verifying", "Checklist: repeat with second devices"], ["Escalated", "CMO notified, report queued (link offline)"],
    ["Acknowledged", "Link restored, ground confirms receipt"], ["Resolved", "Only medical personnel, with a reason"]];
  flow.forEach((f, i) => { s.addShape(pres.shapes.OVAL, { x: 8.4, y: 1.55 + i * 1.05, w: 0.32, h: 0.32, fill: { color: i === 4 ? HEX.ok : HEX.urgent }, line: { color: HEX.hull } });
    txt(s, f[0], { x: 8.9, y: 1.48 + i * 1.05, w: 4, h: 0.4, fontSize: 17, bold: true });
    txt(s, f[1], { x: 8.9, y: 1.88 + i * 1.05, w: 4, h: 0.5, fontSize: 14, color: HEX.muted }); });
  s.addNotes("The procedure shown is a synthetic workflow placeholder with no treatment instructions. Every action is timestamped and audited.");

  // 8 Offline & privacy
  s = pres.addSlide({ masterName: "ASTRA_CONTENT", sectionTitle: "Demonstration" });
  s.addText("Works without Earth. Respects privacy", { placeholder: "title" });
  card(s, 0.6, 1.5, 5.9, 4.9); card(s, 6.85, 1.5, 5.9, 4.9);
  s.addImage({ data: await icon("LuCloudOff", HEX.accent), x: 0.9, y: 1.8, w: 0.6, h: 0.6 });
  s.addImage({ data: await icon("LuLock", HEX.violet), x: 7.15, y: 1.8, w: 0.6, h: 0.6 });
  txt(s, "Offline-first", { x: 1.7, y: 1.85, w: 4.5, h: 0.5, fontSize: 21, bold: true });
  txt(s, "Behavioral privacy", { x: 7.95, y: 1.85, w: 4.5, h: 0.5, fontSize: 21, bold: true });
  s.addText([{ text: "All assessment, alerts and procedures run onboard", options: { bullet: true, breakLine: true } },
    { text: "Earth link online / degraded / offline with light-time delay", options: { bullet: true, breakLine: true } },
    { text: "Store-and-forward queue with retry, back-off and idempotency keys", options: { bullet: true, breakLine: true } },
    { text: "Browser outbox keeps entries if the onboard server is unreachable", options: { bullet: true } }],
    { isTextBox: true, x: 0.9, y: 2.6, w: 5.3, h: 3.6, fontSize: 15, color: HEX.ink, paraSpaceAfter: 8, valign: "top" });
  s.addText([{ text: "Daily check-in: five-level scales, every question skippable", options: { bullet: true, breakLine: true } },
    { text: "Visible to the astronaut and the flight surgeon only", options: { bullet: true, breakLine: true } },
    { text: "Crew Medical Officer sees a redacted placeholder; other crew see nothing", options: { bullet: true, breakLine: true } },
    { text: "Self-reports are indicators, never a psychiatric diagnosis", options: { bullet: true } }],
    { isTextBox: true, x: 7.15, y: 2.6, w: 5.3, h: 3.6, fontSize: 15, color: HEX.ink, paraSpaceAfter: 8, valign: "top" });
  s.addNotes("Private medical communication follows NASA-STD-3001 [V1 6002].");

  // 9 Evidence
  pres.addSection({ title: "Results" });
  s = pres.addSlide({ masterName: "ASTRA_CONTENT", sectionTitle: "Results" });
  s.addText("Built and verified, not just designed", { placeholder: "title" });
  const stats = [["46", "backend tests passing"], ["9", "browser end-to-end tests"], ["8", "synthetic mission scenarios"], ["21", "traceable sources, 18 verified online"],
    ["12", "NASA risks modelled with limitations"], ["74", "documented API paths"]];
  stats.forEach((st, i) => { const x = 0.6 + (i % 3) * 4.15, y = 1.55 + Math.floor(i / 3) * 2.55;
    txt(s, st[0], { x, y, w: 3.9, h: 1.2, fontSize: 66, bold: true, color: i < 2 ? HEX.ok : HEX.accent });
    txt(s, st[1], { x, y: y + 1.25, w: 3.9, h: 0.6, fontSize: 17, color: HEX.muted }); });
  s.addNotes("All numbers come from the final test run on 14 November 2026; see docs/TESTING.md.");

  // 10 Limitations and next steps
  s = pres.addSlide({ masterName: "ASTRA_CONTENT", sectionTitle: "Results" });
  s.addText("What ASTRA is not — yet", { placeholder: "title" });
  card(s, 0.6, 1.5, 5.9, 4.9); card(s, 6.85, 1.5, 5.9, 4.9);
  txt(s, "Honest limitations", { x: 0.9, y: 1.75, w: 5.3, h: 0.5, fontSize: 21, bold: true, color: HEX.attn });
  txt(s, "Next steps", { x: 7.15, y: 1.75, w: 5.3, h: 0.5, fontSize: 21, bold: true, color: HEX.ok });
  s.addText([{ text: "Not clinically validated; demonstration rules only", options: { bullet: true, breakLine: true } },
    { text: "Procedures are synthetic placeholders", options: { bullet: true, breakLine: true } },
    { text: "No physical device tested", options: { bullet: true, breakLine: true } },
    { text: "Ground segment simulated; prototype security (no TLS, no encryption at rest)", options: { bullet: true } }],
    { isTextBox: true, x: 0.9, y: 2.45, w: 5.3, h: 3.7, fontSize: 15, color: HEX.ink, paraSpaceAfter: 8, valign: "top" });
  s.addText([{ text: "Flight-surgeon review of rules and individual reference ranges", options: { bullet: true, breakLine: true } },
    { text: "Adapters for real wearables and medical devices, then validation", options: { bullet: true, breakLine: true } },
    { text: "TLS, encrypted storage, tamper-evident audit", options: { bullet: true, breakLine: true } },
    { text: "Analog-mission trial (e.g. HERA-style isolation study)", options: { bullet: true } }],
    { isTextBox: true, x: 7.15, y: 2.45, w: 5.3, h: 3.7, fontSize: 15, color: HEX.ink, paraSpaceAfter: 8, valign: "top" });
  s.addNotes("Close by inviting questions. The repository includes a demo script, compliance report and checkpoints for every stage.");

  const out = path.join(__dirname, "ASTRA_presentation.pptx");
  await pres.writeFile({ fileName: out });
  await applyTheme(out, THEME);
  console.log("wrote", out);
})();
