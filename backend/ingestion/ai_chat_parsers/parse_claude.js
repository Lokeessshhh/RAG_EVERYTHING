/**
 * parse_claude.js
 * Parses a Claude shared conversation HTML file.
 *
 * Usage:
 *   node parse_claude.js                         (uses default path)
 *   node parse_claude.js path/to/file.html       (custom path)
 *
 * Output:
 *   test_output/parsed_claude.txt   - clean readable conversation
 *   test_output/parsed_claude.json  - structured JSON [{role, text}, ...]
 *
 * Strategy:
 *   Claude (claude.ai) SSR-renders shared conversations into the DOM.
 *   Each turn is wrapped in a div with data-test-render-count attribute.
 *
 *   User turns:      contain  data-testid="user-message"
 *   Assistant turns: contain  data-is-streaming="false"  (the response wrapper)
 *                   with inner class "font-claude-response"
 *
 *   Both sit at the same level so we collect all turns with their HTML
 *   positions and sort them to preserve conversation order.
 */

"use strict";

const fs   = require("fs");
const path = require("path");

// ── Config ────────────────────────────────────────────────────────────────────
const inputFile  = process.argv[2] || "test_output/claude_raw_html.html";
const outputDir  = "test_output";
const outputTxt  = path.join(outputDir, "parsed_claude.txt");
const outputJson = path.join(outputDir, "parsed_claude.json");
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

/** Convert HTML block to clean plain text, preserving readable structure */
function htmlToText(rawHtml) {
  let text = rawHtml;

  // Remove tool-use UI elements (thinking steps, file actions labels)
  // These are inside <button> tags with aria-expanded attribute
  text = text.replace(/<button\b[^>]*aria-expanded[^>]*>[\s\S]*?<\/button>/gi, "");

  // Remove file thumbnail/action blocks (data-testid="file-thumbnail" etc)
  text = text.replace(/<div[^>]*data-testid="file-thumbnail"[^>]*>[\s\S]*?<\/div>/gi, "");

  // Tables: add structure
  text = text.replace(/<th[^>]*>/gi, " | ");
  text = text.replace(/<\/th>/gi, " |");
  text = text.replace(/<td[^>]*>/gi, " | ");
  text = text.replace(/<\/td>/gi, " |");
  text = text.replace(/<\/tr>/gi, "\n");

  // Headings: add newlines
  text = text.replace(/<\/?(h[1-6])[^>]*>/gi, "\n");

  // Block elements: newlines
  text = text.replace(/<\/?(p|div|section|article|blockquote|pre)[^>]*>/gi, "\n");
  text = text.replace(/<br\s*\/?>/gi, "\n");

  // Lists
  text = text.replace(/<li[^>]*>/gi, "\n- ");
  text = text.replace(/<\/li>/gi, "");
  text = text.replace(/<\/?(ul|ol)[^>]*>/gi, "\n");

  // Code: preserve with backticks
  text = text.replace(/<code[^>]*>([\s\S]*?)<\/code>/gi, (_, inner) => {
    const cleaned = inner.replace(/<[^>]+>/g, "").trim();
    return "`" + cleaned + "`";
  });

  // Strong/em: strip tags (plain text)
  text = text.replace(/<\/?(strong|b|em|i|u|s)[^>]*>/gi, "");

  // Strip all remaining tags
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

  // Remove Claude tool-use UI noise lines (status labels that leaked through)
  // These are short single-line artifacts from the tool-use accordion UI
  const NOISE_LINES = new Set([
    "Done", "Script", "Running", "Stopped",
    "Created a file, read a file",
    "Created a file",
    "Read a file",
    "Viewed a file",
    "Edited a file",
    "Ran a command",
    "Presented file",
    "Edited 2 files, read a file",
    "Edited 2 files, viewed a file, read a file",
    "Viewed a file, created a file, read a file",
    "Viewed a file, edited a file, ran a command",
    "Viewed a file, created a file",
    "Ran a command, read a file",
    "Files hidden in shared chats",
  ]);

  text = text
    .split("\n")
    .filter(line => !NOISE_LINES.has(line.trim()))
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

  return text;
}

// ── Find matching closing div ─────────────────────────────────────────────────
/**
 * Given the position of '<' of an opening <div...>, find the position
 * just after the matching </div>.
 */
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
// User message: data-testid="user-message" on a div
// Walk back from the testid attr to find the opening <div, then grab its block.

function extractUserTurns(html) {
  const turns = [];
  const re = /data-testid="user-message"/g;
  let m;
  while ((m = re.exec(html)) !== null) {
    const attrPos = m.index;
    // Find the opening <div that owns this attribute
    const divStart = html.lastIndexOf("<div", attrPos);
    if (divStart === -1) continue;
    const blockEnd = findClosingDiv(html, divStart);
    const blockHtml = html.slice(divStart, blockEnd);
    turns.push({ pos: attrPos, role: "user", rawHtml: blockHtml });
  }
  return turns;
}

// ── Extract assistant turns ───────────────────────────────────────────────────
// Assistant response: data-is-streaming="false" on the response wrapper div
// Inside it, actual prose lives in divs with class "standard-markdown" or
// "progressive-markdown". We extract only those blocks to avoid tool-use
// accordion UI noise (buttons, sr-only spans, file labels, "Done", etc.)

function extractAssistantTurns(html) {
  const turns = [];
  const re = /data-is-streaming="false"/g;
  let m;
  while ((m = re.exec(html)) !== null) {
    const attrPos = m.index;
    // Find the opening <div that owns data-is-streaming
    const divStart = html.lastIndexOf("<div", attrPos);
    if (divStart === -1) continue;
    const blockEnd = findClosingDiv(html, divStart);
    const blockHtml = html.slice(divStart, blockEnd);

    // Collect all standard-markdown / progressive-markdown prose blocks
    const proseParts = [];
    const proseRe = /class="(?:standard-markdown|progressive-markdown)[^"]*"/g;
    let pm;
    while ((pm = proseRe.exec(blockHtml)) !== null) {
      const proseAttrPos = pm.index;
      const proseDivStart = blockHtml.lastIndexOf("<div", proseAttrPos);
      if (proseDivStart === -1) continue;
      const proseEnd = findClosingDiv(blockHtml, proseDivStart);
      proseParts.push(blockHtml.slice(proseDivStart, proseEnd));
    }

    // Fall back to full font-claude-response block if no prose divs found
    let contentHtml;
    if (proseParts.length > 0) {
      contentHtml = proseParts.join("\n");
    } else {
      const contentIdx = blockHtml.indexOf("font-claude-response");
      if (contentIdx === -1) continue;
      const contentDivStart = blockHtml.lastIndexOf("<div", contentIdx);
      if (contentDivStart === -1) continue;
      const contentEnd = findClosingDiv(blockHtml, contentDivStart);
      contentHtml = blockHtml.slice(contentDivStart, contentEnd);
    }

    turns.push({ pos: attrPos, role: "assistant", rawHtml: contentHtml });
  }
  return turns;
}

// ── Run extraction ────────────────────────────────────────────────────────────
const userTurns      = extractUserTurns(html);
const assistantTurns = extractAssistantTurns(html);

// Merge and sort by position in HTML
const allTurns = [...userTurns, ...assistantTurns];
allTurns.sort((a, b) => a.pos - b.pos);

if (allTurns.length === 0) {
  process.stderr.write(
    "ERROR: No conversation turns found.\n" +
    "The page may not have rendered fully. Try re-fetching:\n" +
    "  python parse_claude.py <url>\n"
  );
  process.exit(1);
}

// Convert to clean messages, deduplicate
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
