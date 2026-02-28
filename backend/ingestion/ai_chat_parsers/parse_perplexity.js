/**
 * parse_perplexity.js
 * Parses a Perplexity shared conversation HTML file.
 *
 * Usage:
 *   node parse_perplexity.js                         (uses default path)
 *   node parse_perplexity.js path/to/file.html       (custom path)
 *
 * Output:
 *   test_output/parsed_perplexity.txt   - clean readable conversation
 *   test_output/parsed_perplexity.json  - structured JSON [{role, text}, ...]
 *
 * Strategy:
 *   Perplexity (perplexity.ai) is a Next.js app that SSR-renders shared
 *   conversations into the DOM.
 *
 *   User turns:      divs with class containing "group/query"
 *                    → inner <span> holds the raw query text
 *   Assistant turns: divs with id="markdown-content-N" (N = 0,1,2,...)
 *                    → inner class "prose dark:prose-invert" holds the answer
 *
 *   Both are collected with their HTML positions and sorted to preserve order.
 */

"use strict";

const fs   = require("fs");
const path = require("path");

// ── Config ────────────────────────────────────────────────────────────────────
const inputFile  = process.argv[2] || "test_output/perplexity_raw_html.html";
const outputDir  = "test_output";
const outputTxt  = path.join(outputDir, "parsed_perplexity.txt");
const outputJson = path.join(outputDir, "parsed_perplexity.json");
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
    .replace(/&#x2F;/g, "/")
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)))
    .replace(/&#x([0-9a-fA-F]+);/g, (_, h) => String.fromCharCode(parseInt(h, 16)));
}

/** Convert HTML block to clean plain text */
function htmlToText(rawHtml) {
  let text = rawHtml;

  // Tables
  text = text.replace(/<th[^>]*>/gi, " | ");
  text = text.replace(/<\/th>/gi, " |");
  text = text.replace(/<td[^>]*>/gi, " | ");
  text = text.replace(/<\/td>/gi, " |");
  text = text.replace(/<\/tr>/gi, "\n");

  // Headings / block elements
  text = text.replace(/<\/?(h[1-6])[^>]*>/gi, "\n");
  text = text.replace(/<\/?(p|div|section|article|blockquote|pre)[^>]*>/gi, "\n");
  text = text.replace(/<br\s*\/?>/gi, "\n");

  // Lists
  text = text.replace(/<li[^>]*>/gi, "\n- ");
  text = text.replace(/<\/li>/gi, "");
  text = text.replace(/<\/?(ul|ol)[^>]*>/gi, "\n");

  // Code
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
    .replace(/[ \t]+/g, " ")
    .replace(/ +\n/g, "\n")
    .replace(/\n +/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

  return text;
}

/** Find the matching closing </div> position, starting from the opening <div at openPos */
function findClosingDiv(html, openPos) {
  let depth = 0;
  let i = openPos;
  while (i < html.length) {
    if (html[i] !== "<") { i++; continue; }
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

// ── Extract user turns ────────────────────────────────────────────────────────
// User messages: divs with class containing "group/query"
// The text is in a <span> inside a rounded bubble div.

function extractUserTurns(html) {
  const turns = [];
  // Match the class attribute containing "group/query"
  const re = /class="[^"]*group\/query[^"]*"/g;
  let m;
  while ((m = re.exec(html)) !== null) {
    const attrPos = m.index;
    const divStart = html.lastIndexOf("<div", attrPos);
    if (divStart === -1) continue;
    const blockEnd = findClosingDiv(html, divStart);
    const blockHtml = html.slice(divStart, blockEnd);
    turns.push({ pos: attrPos, role: "user", rawHtml: blockHtml });
  }
  return turns;
}

// ── Extract assistant turns ───────────────────────────────────────────────────
// Assistant answers: divs with id="markdown-content-N"
// Content is inside class="prose dark:prose-invert ..."

function extractAssistantTurns(html) {
  const turns = [];
  const re = /id="markdown-content-(\d+)"/g;
  let m;
  while ((m = re.exec(html)) !== null) {
    const attrPos = m.index;
    const divStart = html.lastIndexOf("<div", attrPos);
    if (divStart === -1) continue;
    const blockEnd = findClosingDiv(html, divStart);
    const blockHtml = html.slice(divStart, blockEnd);

    // Try to find the prose block inside for cleaner extraction
    const proseIdx = blockHtml.indexOf("prose dark:prose-invert");
    let contentHtml = blockHtml;
    if (proseIdx !== -1) {
      const proseDivStart = blockHtml.lastIndexOf("<div", proseIdx);
      if (proseDivStart !== -1) {
        const proseEnd = findClosingDiv(blockHtml, proseDivStart);
        contentHtml = blockHtml.slice(proseDivStart, proseEnd);
      }
    }

    turns.push({ pos: attrPos, role: "assistant", rawHtml: contentHtml });
  }
  return turns;
}

// ── Run extraction ────────────────────────────────────────────────────────────
const userTurns      = extractUserTurns(html);
const assistantTurns = extractAssistantTurns(html);

const allTurns = [...userTurns, ...assistantTurns];
allTurns.sort((a, b) => a.pos - b.pos);

if (allTurns.length === 0) {
  process.stderr.write(
    "ERROR: No conversation turns found.\n" +
    "The page may be behind a login wall or not fully rendered.\n" +
    "Try re-fetching: python parse_perplexity.py <url>\n"
  );
  process.exit(1);
}

// Clean and deduplicate
const messages  = [];
const seenTexts = new Set();

for (const turn of allTurns) {
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
