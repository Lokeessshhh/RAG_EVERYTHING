/**
 * parse_gemini.js
 * Parses a Gemini shared conversation HTML file.
 *
 * Usage:
 *   node parse_gemini.js                         (uses default path)
 *   node parse_gemini.js path/to/file.html       (custom path)
 *
 * Output:
 *   test_output/parsed_gemini.txt   - clean readable conversation
 *   test_output/parsed_gemini.json  - structured JSON [{role, text}, ...]
 *
 * Strategy A (primary): Parse Angular SSR-rendered DOM
 *   - User turns:  class="user-query-container" or class="query-text"
 *   - Model turns: class="markdown markdown-main-panel"
 * Strategy B (fallback): Parse WIZ_global_data.TSDtV blob
 *   - Encoded as largest JSON string, turns split by U+221E (infinity sign)
 */

const fs   = require("fs");
const path = require("path");

// ── Config ────────────────────────────────────────────────────────────────────
const inputFile  = process.argv[2] || "test_output/gemini_raw_html.html";
const outputDir  = "test_output";
const outputTxt  = path.join(outputDir, "parsed_gemini.txt");
const outputJson = path.join(outputDir, "parsed_gemini.json");
// ─────────────────────────────────────────────────────────────────────────────

if (!fs.existsSync(inputFile)) {
  process.stderr.write(`ERROR: File not found: ${inputFile}\n`);
  process.exit(1);
}
if (!fs.existsSync(outputDir)) fs.mkdirSync(outputDir, { recursive: true });

const html = fs.readFileSync(inputFile, "utf8");

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Strip all HTML tags and decode common entities */
function stripTags(raw) {
  return raw
    .replace(/<[^>]+>/g, " ")          // remove tags
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, " ")
    .replace(/\s{2,}/g, " ")
    .trim();
}

/** Collapse excessive blank lines */
function cleanText(text) {
  return text.replace(/\r\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}

// ── Strategy A: DOM parsing ───────────────────────────────────────────────────
// Gemini SSR renders conversation as interleaved user-query and model response blocks.
// User queries  -> inside elements with class "user-query-container" or "query-text"
// Model answers -> inside elements with class "markdown markdown-main-panel"

function parseFromDOM(html) {
  const messages = [];

  // ---- User turn extraction ----
  // Pattern: <div ... class="... user-query-container ...">...<p ...>TEXT</p>...</div>
  // Also handles: <div ... class="... query-text ..."...>TEXT</div>
  const userPatterns = [
    /class="[^"]*user-query-container[^"]*"[^>]*>([\s\S]*?)<\/div>/g,
    /class="[^"]*query-text[^"]*"[^>]*>([\s\S]*?)<\/(?:div|p|span)>/g,
    /class="[^"]*user-query-bubble[^"]*"[^>]*>([\s\S]*?)<\/(?:div|p|span)>/g,
  ];

  // ---- Model turn extraction ----
  // Pattern: <div ... class="markdown markdown-main-panel ...">...</div>
  // We collect all <p> and <li> text inside each markdown block
  const modelPattern = /class="markdown markdown-main-panel[^"]*"[^>]*>([\s\S]*?)<\/div>(?=\s*<\/div>)/g;

  // Collect positions so we can interleave user + model in order
  const turns = [];

  // Find user turns
  for (const re of userPatterns) {
    let m;
    re.lastIndex = 0;
    while ((m = re.exec(html)) !== null) {
      const text = cleanText(stripTags(m[1]));
      if (text && text.length > 2) {
        turns.push({ pos: m.index, role: "user", text });
      }
    }
  }

  // Find model turns - extract all <p> / <li> content from each markdown block
  let m;
  modelPattern.lastIndex = 0;
  while ((m = modelPattern.exec(html)) !== null) {
    const block = m[1];
    // Extract paragraphs and list items
    const parts = [];
    const pRe = /<(?:p|li|h[1-6])[^>]*>([\s\S]*?)<\/(?:p|li|h[1-6])>/g;
    let pm;
    while ((pm = pRe.exec(block)) !== null) {
      const t = cleanText(stripTags(pm[1]));
      if (t) parts.push(t);
    }
    const text = parts.length ? parts.join("\n\n") : cleanText(stripTags(block));
    if (text && text.length > 10) {
      turns.push({ pos: m.index, role: "assistant", text });
    }
  }

  // Sort by position in HTML to get correct conversation order
  turns.sort((a, b) => a.pos - b.pos);

  // UI noise strings to skip
  const NOISE = new Set(["You said", "Gemini said", "Copy", "Edit", "Share", "More"]);

  // Deduplicate and filter noise
  const seen = new Set();
  for (const t of turns) {
    if (NOISE.has(t.text)) continue;
    if (!seen.has(t.text)) {
      seen.add(t.text);
      messages.push({ role: t.role, text: t.text });
    }
  }

  return messages;
}

// ── Strategy B: WIZ_global_data TSDtV parsing ────────────────────────────────
// Some Gemini share pages embed conversation in WIZ_global_data.TSDtV
// as a double-encoded JSON array: [[userText + U+221E + modelText, ...]]

function parseFromWIZ(html) {
  const WIZ_PREFIX = "window.WIZ_global_data = {";
  const wizIdx = html.indexOf(WIZ_PREFIX);
  if (wizIdx === -1) return [];

  const start = wizIdx + WIZ_PREFIX.length - 1;
  let depth = 0, inStr = false, esc = false, end = start;
  for (let i = start; i < html.length; i++) {
    const ch = html[i];
    if (esc)          { esc = false; continue; }
    if (ch === "\\")  { esc = true;  continue; }
    if (ch === '"' && !esc) { inStr = !inStr; continue; }
    if (!inStr) {
      if (ch === "{") depth++;
      else if (ch === "}") { depth--; if (depth === 0) { end = i + 1; break; } }
    }
  }

  let wiz;
  try { wiz = JSON.parse(html.slice(start, end)); } catch { return []; }

  const tsdtv = wiz.TSDtV;
  if (!tsdtv || !tsdtv.startsWith("%.@.")) return [];
  const raw = tsdtv.slice(4);

  // Find largest JSON string literal in raw blob
  let best = null, i = 0;
  while (i < raw.length) {
    if (raw[i] === '"') {
      let j = i + 1, e = false;
      while (j < raw.length) {
        if (e) { e = false; j++; continue; }
        if (raw[j] === "\\") { e = true; j++; continue; }
        if (raw[j] === '"') break;
        j++;
      }
      const len = j - i - 1;
      if (!best || len > best.len) best = { pos: i + 1, len, end: j };
      i = j + 1;
    } else { i++; }
  }
  if (!best) return [];

  let decoded, pairs;
  try {
    decoded = JSON.parse('"' + raw.slice(best.pos, best.end) + '"');
    const outer = JSON.parse(decoded);
    pairs = Array.isArray(outer[0]) ? outer[0] : outer;
  } catch { return []; }

  const SEP = "\u221e"; // ∞
  const messages = [];
  const seen = new Set();

  for (const pair of pairs) {
    if (typeof pair !== "string") continue;
    const sepIdx = pair.indexOf(SEP);
    if (sepIdx === -1) continue;
    const userText  = cleanText(pair.slice(0, sepIdx));
    const modelText = cleanText(pair.slice(sepIdx + 1));
    const key = userText + "|||" + modelText;
    if (seen.has(key)) continue;
    seen.add(key);
    if (userText)  messages.push({ role: "user",      text: userText  });
    if (modelText) messages.push({ role: "assistant", text: modelText });
  }
  return messages;
}

// ── Run both strategies ───────────────────────────────────────────────────────
let messages = parseFromDOM(html);

if (messages.length === 0) {
  messages = parseFromWIZ(html);
}

if (messages.length === 0) {
  process.stderr.write(
    "ERROR: No conversation content found.\n" +
    "The page may not have fully rendered. Re-fetch with a longer wait:\n" +
    "  python parse_gemini.py <url>\n"
  );
  process.exit(1);
}

// ── Write outputs ─────────────────────────────────────────────────────────────
// Output JSON to stdout (for programmatic use)
process.stdout.write(JSON.stringify(messages));
