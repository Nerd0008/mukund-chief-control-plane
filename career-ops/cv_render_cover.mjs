#!/usr/bin/env node
/**
 * cv_render_cover.mjs — render a cover-letter payload with the EXISTING engine.
 *
 * This is a thin driver, not a reimplementation. It imports two modules out of
 * the Career Ops install (path supplied with --install):
 *
 *   generate-cover-letter.mjs  → buildHtml()      the authoritative renderer
 *   verify-cv-facts.mjs        → verifyFacts()    the authoritative fact gate
 *
 * Behaviour:
 *   * builds the letter HTML through buildHtml();
 *   * runs verifyFacts() over that HTML against the canonical source files;
 *   * writes the HTML when --out is given;
 *   * prints exactly one JSON object on stdout and exits 1 when the fact gate
 *     BLOCKS (so a caller cannot mistake a blocked draft for a usable one).
 *
 * It deliberately does NOT import generate-pdf.mjs: that module launches
 * headless Chromium, and this workflow does not start a browser.
 *
 * Usage:
 *   node cv_render_cover.mjs --install <career-ops-dir> --payload <payload.json> \
 *        [--out <file.html>] [--source <path>]... [--config <cv-facts.json>]
 */

import { readFileSync, writeFileSync, mkdirSync } from "fs";
import { dirname, resolve } from "path";
import { pathToFileURL } from "url";

function flagValue(name) {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : null;
}
function flagValues(name) {
  const out = [];
  process.argv.forEach((arg, i) => {
    if (arg === name && process.argv[i + 1]) out.push(process.argv[i + 1]);
  });
  return out;
}

const install = flagValue("--install");
const payloadPath = flagValue("--payload");
const outPath = flagValue("--out");
const configPath = flagValue("--config");
const sources = flagValues("--source");

if (!install || !payloadPath) {
  console.log(JSON.stringify({
    rendered: false,
    error: "usage: node cv_render_cover.mjs --install <career-ops-dir> --payload <payload.json> [--out <html>] [--source <path>]... [--config <path>]",
  }));
  process.exit(2);
}

const installDir = resolve(install);

try {
  const renderer = await import(pathToFileURL(resolve(installDir, "generate-cover-letter.mjs")).href);
  const facts = await import(pathToFileURL(resolve(installDir, "verify-cv-facts.mjs")).href);

  const payload = JSON.parse(readFileSync(resolve(payloadPath), "utf-8"));
  const html = renderer.buildHtml(payload);

  const factGate = facts.verifyFacts(html, {
    ...(sources.length ? { sourcePaths: sources } : {}),
    ...(configPath ? { configPath } : {}),
    cwd: installDir,
  });

  if (outPath) {
    mkdirSync(dirname(resolve(outPath)), { recursive: true });
    writeFileSync(resolve(outPath), html, "utf-8");
  }

  console.log(JSON.stringify({
    rendered: true,
    renderer: "generate-cover-letter.mjs buildHtml",
    fact_gate_module: "verify-cv-facts.mjs verifyFacts",
    html_path: outPath ? resolve(outPath) : null,
    html_chars: html.length,
    fact_gate: factGate,
    browser_launched: false,
    pdf_rendered: false,
  }));
  process.exit(factGate.verdict === "block" ? 1 : 0);
} catch (err) {
  console.log(JSON.stringify({
    rendered: false,
    error: `${err.name || "Error"}: ${err.message}`,
    browser_launched: false,
    pdf_rendered: false,
  }));
  process.exit(1);
}
