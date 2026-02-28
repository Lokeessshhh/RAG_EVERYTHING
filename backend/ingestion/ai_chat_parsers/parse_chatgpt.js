/**
 * parse_chat.js
 * Parses a ChatGPT shared conversation HTML file.
 *
 * Usage:
 *   node parse_chat.js                      (uses default path)
 *   node parse_chat.js path/to/file.html    (custom path)
 *
 * Output:
 *   test_output/parsed_chat.txt   - clean readable conversation
 *   test_output/parsed_chat.json  - structured JSON [{role, text}, ...]
 */

const fs   = require("fs");
const path = require("path");

// ── Config ────────────────────────────────────────────────────────────────────
const inputFile = process.argv[2] || "test_output/raw_html.html";
const outputDir  = "test_output";
const outputTxt  = path.join(outputDir, "parsed_chat.txt");
const outputJson = path.join(outputDir, "parsed_chat.json");
// ─────────────────────────────────────────────────────────────────────────────

if (!fs.existsSync(inputFile)) {
  process.stderr.write(`ERROR: File not found: ${inputFile}\n`);
  process.exit(1);
}
if (!fs.existsSync(outputDir)) fs.mkdirSync(outputDir, { recursive: true });

// ── Step 1: Extract the React Flight stream payload ───────────────────────────
const html = fs.readFileSync(inputFile, "utf8");

const ENQUEUE_PREFIX = 'window.__reactRouterContext.streamController.enqueue("';
const enqueueIdx = html.indexOf(ENQUEUE_PREFIX);
if (enqueueIdx === -1) {
  process.stderr.write("ERROR: Could not find React stream data. Page structure may have changed.\n");
  process.exit(1);
}

const start = enqueueIdx + ENQUEUE_PREFIX.length;
let end = -1;
let inEscape = false;
for (let i = start; i < html.length; i++) {
  const ch = html[i];
  if (inEscape) {
    inEscape = false;
    continue;
  }
  if (ch === "\\") {
    inEscape = true;
    continue;
  }
  if (ch === '"') {
    end = i;
    break;
  }
}

if (end === -1) {
  process.stderr.write("ERROR: Could not find end of enqueue() string payload.\n");
  process.exit(1);
}

const rawPayload = html.slice(start, end);

let flightData;
try {
  const jsonStr = JSON.parse(`"${rawPayload}"`);
  flightData = JSON.parse(jsonStr);
} catch (e) {
  process.stderr.write(`ERROR: Failed to parse flight data: ${e.message}\n`);
  process.exit(1);
}

// ── Step 2: Resolve index references and extract messages ─────────────────────
// ChatGPT's flight format is a flat array where objects use numeric keys
// (_46, _48, etc.) as index references into the same array.
//
// Message node:   { _46: <msg_obj_idx>, _72: <parent_idx> }
//   msg_obj:      { _48: <author_idx>, _54: <content_idx> }
//     author:     { _50: <role_idx> }
//     content:    { _58: <parts_idx> }
//       parts:    [ text_idx, ... ]

function resolve(idx) {
  return typeof idx === "number" ? flightData[idx] : idx;
}

function cleanText(raw) {
  return raw
    // ChatGPT wraps entity annotations in invisible Unicode private-use markers
    // (U+E201 / U+E202) - strip them first so the regex below can match
    .replace(/[\uE201\uE202]/g, "")
    // Replace entity annotations with their display name (last quoted segment)
    // entity["company","Upstash"]             -> Upstash
    // entity["software","Grok","xAI chatbot"] -> xAI chatbot
    .replace(/entity\[(?:"[^"]*",)*"([^"]*)"\]/g, "$1")
    // Remove markdown directives like :::writing{variant="standard"}:::
    .replace(/:::writing\{[^}]*\}/g, "").replace(/:::/g, "")
    // Collapse 3+ blank lines into 2
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

const messages  = [];
const seenTexts = new Set(); // deduplicate: ChatGPT embeds the conversation twice

for (let i = 0; i < flightData.length; i++) {
  const item = flightData[i];
  if (
    typeof item !== "object" || item === null || Array.isArray(item) ||
    item._46 === undefined || item._72 === undefined
  ) continue;

  const msgObj = flightData[item._46];
  if (!msgObj || typeof msgObj !== "object" || Array.isArray(msgObj)) continue;

  // Role
  let role = "unknown";
  if (msgObj._48 !== undefined) {
    const authorObj = flightData[msgObj._48];
    if (authorObj && authorObj._50 !== undefined) role = resolve(authorObj._50);
  }
  if (!["user", "assistant"].includes(role)) continue;

  // Text
  let text = "";
  if (msgObj._54 !== undefined) {
    const contentObj = flightData[msgObj._54];
    if (contentObj && contentObj._58 !== undefined) {
      const partsArr = flightData[contentObj._58];
      if (Array.isArray(partsArr)) {
        text = partsArr
          .map((p) => { const v = resolve(p); return typeof v === "string" ? v : ""; })
          .join("");
      }
    }
  }

  text = cleanText(text);
  if (!text || seenTexts.has(text)) continue;
  seenTexts.add(text);
  messages.push({ role, text });
}

// ── Step 3: Write outputs ─────────────────────────────────────────────────────
if (messages.length === 0) {
  process.stderr.write("ERROR: No messages extracted. Page structure may differ.\n");
  process.exit(1);
}

// Output JSON to stdout (for programmatic use)
process.stdout.write(JSON.stringify(messages));