/**
 * parse_grok.js
 * Parses a Grok shared conversation HTML file.
 *
 * Usage:
 *   node parse_grok.js                         (uses default path)
 *   node parse_grok.js path/to/file.html       (custom path)
 *
 * Output:
 *   test_output/parsed_grok.txt   - clean readable conversation
 *   test_output/parsed_grok.json  - structured JSON [{role, text}, ...]
 *
 * Strategy:
 *   Grok (grok.com) is a Next.js app that server-side renders conversations
 *   into the DOM. Each turn lives in a div with id="response-<uuid>":
 *
 *   User turns:      outer div has class containing "items-end"
 *   Assistant turns: outer div has class containing "items-start"
 *
 *   Both have an inner div with class "response-content-markdown" holding the
 *   rendered HTML content (paragraphs, lists, code blocks, etc.).
 */

"use strict";

const fs   = require("fs");
const path = require("path");

// ── Config ────────────────────────────────────────────────────────────────────
const inputFile  = process.argv[2] || "test_output/grok_raw_html.html";
const outputDir  = "test_output";
const outputTxt  = path.join(outputDir, "parsed_grok.txt");
const outputJson = path.join(outputDir, "parsed_grok.json");
// ─────────────────────────────────────────────────────────────────────────────

if (!fs.existsSync(inputFile)) {
  process.stderr.write(`ERROR: File not found: ${inputFile}\n`);
  process.exit(1);
}
if (!fs.existsSync(outputDir)) fs.mkdirSync(outputDir, { recursive: true });

const html = fs.readFileSync(inputFile, "utf8");

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Decode HTML entities */
function decodeEntities(str) {
  return str
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&#x2F;/g, "/");
}

/** Convert an HTML block into clean plain text, preserving structure */
function htmlToText(rawHtml) {
  let text = rawHtml;

  // Block-level elements: add newlines
  text = text.replace(/<\/?(p|div|section|article|header|footer|h[1-6]|blockquote|pre)[^>]*>/gi, "\n");
  text = text.replace(/<br\s*\/?>/gi, "\n");
  text = text.replace(/<li[^>]*>/gi, "\n- ");
  text = text.replace(/<\/li>/gi, "");
  text = text.replace(/<\/?(ul|ol)[^>]*>/gi, "\n");
  text = text.replace(/<\/?(tr|td|th)[^>]*>/gi, "\n");

  // Code blocks: preserve inline
  text = text.replace(/<code[^>]*>([\s\S]*?)<\/code>/gi, (_, inner) => {
    return "`" + inner.replace(/<[^>]+>/g, "").trim() + "`";
  });

  // Strip remaining tags
  text = text.replace(/<[^>]+>/g, "");

  // Decode entities
  text = decodeEntities(text);

  // Normalise whitespace
  text = text
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .replace(/[ \t]+/g, " ")           // collapse horizontal whitespace
    .replace(/ +\n/g, "\n")            // trim trailing spaces on lines
    .replace(/\n +/g, "\n")            // trim leading spaces on lines
    .replace(/\n{3,}/g, "\n\n")        // max 2 blank lines
    .trim();

  return text;
}

// ── Extract the conversation block ───────────────────────────────────────────
// Each turn: <div class="... items-end|items-start ..." id="response-<uuid>" ...>
//   ...
//   <div class="relative response-content-markdown markdown ...">
//     CONTENT
//   </div>
//   ...
// </div>

/**
 * Find the position of the matching closing </div> for the <div> that starts at `openPos`.
 * `openPos` should point to the '<' of the opening tag.
 */
function findClosingDiv(html, openPos) {
  let depth = 0;
  let i = openPos;
  while (i < html.length) {
    if (html[i] !== "<") { i++; continue; }
    // Self-closing or void? skip
    if (html.startsWith("</div", i)) {
      depth--;
      if (depth === 0) {
        const end = html.indexOf(">", i);
        return end === -1 ? html.length : end + 1;
      }
      i += 6;
    } else if (html.startsWith("<div", i)) {
      depth++;
      i += 4;
    } else {
      i++;
    }
  }
  return html.length;
}

/**
 * Extract all turns from the HTML.
 * Returns [{pos, role, rawHtml}] sorted by position.
 */
function extractTurns(html) {
  const turns = [];

  // Match outer response divs: capture role (items-end = user, items-start = assistant)
  // Pattern: class="... items-end ..." id="response-UUID"  OR items-start variant
  const outerRe = /class="([^"]*?(?:items-end|items-start)[^"]*?)" id="response-([0-9a-f-]+)"/g;
  let m;

  while ((m = outerRe.exec(html)) !== null) {
    const classAttr = m[1];
    const role = classAttr.includes("items-end") ? "user" : "assistant";
    const matchPos = m.index;

    // Walk back to find the '<div' that owns this class/id
    let divStart = html.lastIndexOf("<div", matchPos);
    if (divStart === -1) continue;

    // Find the full outer div block
    const outerHtml = html.slice(divStart, findClosingDiv(html, divStart));

    // Inside it, find the response-content-markdown div
    const markdownIdx = outerHtml.indexOf("response-content-markdown");
    if (markdownIdx === -1) continue;

    // Find the opening <div for the markdown container
    const mdDivStart = outerHtml.lastIndexOf("<div", markdownIdx);
    if (mdDivStart === -1) continue;

    const mdHtml = outerHtml.slice(mdDivStart, findClosingDiv(outerHtml, mdDivStart));

    turns.push({ pos: matchPos, role, rawHtml: mdHtml });
  }

  // Sort by position to preserve conversation order
  turns.sort((a, b) => a.pos - b.pos);
  return turns;
}

// ── Run extraction ────────────────────────────────────────────────────────────
const rawTurns = extractTurns(html);

if (rawTurns.length === 0) {
  process.stderr.write(
    "ERROR: No conversation turns found.\n" +
    "The page may not have fully rendered. Try re-fetching:\n" +
    "  python parse_grok.py <url>\n"
  );
  process.exit(1);
}

// Convert to clean messages and deduplicate
const messages = [];
const seenTexts = new Set();

for (const turn of rawTurns) {
  const text = htmlToText(turn.rawHtml);
  if (!text || text.length < 2) continue;
  if (seenTexts.has(text)) continue;
  seenTexts.add(text);
  messages.push({ role: turn.role, text });
}

if (messages.length === 0) {
  process.stderr.write("ERROR: All extracted turns were empty after cleaning.\n");
  process.exit(1);
}

// ── Write outputs ─────────────────────────────────────────────────────────────
// Output JSON to stdout (for programmatic use)
process.stdout.write(JSON.stringify(messages));
