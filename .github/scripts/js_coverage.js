// Merges the JavaScript coverage of the end-to-end tests and reports, per file of DiceForge/web, which functions no test called.
// The input is e2e/coverage-js/*.json, written by e2e/helpers.js while DICEFORGE_JS_COVERAGE is set: each test's V8 coverage of the
// scripts served from /extensions/DiceForge/. A function counts as run when any test called it. Prints a table, and writes the same table
// (with the functions that never ran, by line) to the job summary when GITHUB_STEP_SUMMARY is set. It reports; it does not fail the job.
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const WEB = path.join(ROOT, "DiceForge", "web");
const INPUT = path.join(ROOT, "e2e", "coverage-js");
const PREFIX = "/extensions/DiceForge/";

// Every .js file of web/, so a file no test loaded shows as 0 %.
function scriptsIn(folder) {
  return fs.readdirSync(folder, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(folder, entry.name);
    if (entry.isDirectory()) return scriptsIn(full);
    return entry.name.endsWith(".js") ? [path.relative(WEB, full).split(path.sep).join("/")] : [];
  });
}

const files = new Map(); // relative path -> { text, functions: Map key -> { name, line, ran } }
for (const relative of scriptsIn(WEB)) {
  files.set(relative, { text: fs.readFileSync(path.join(WEB, relative), "utf8"), functions: new Map(), loaded: false });
}

const lineOf = (text, offset) => text.slice(0, offset).split("\n").length;

let runs = 0;
if (fs.existsSync(INPUT)) {
  for (const name of fs.readdirSync(INPUT).filter((file) => file.endsWith(".json"))) {
    const run = JSON.parse(fs.readFileSync(path.join(INPUT, name), "utf8"));
    runs++;
    for (const entry of run.entries) {
      const at = entry.url.indexOf(PREFIX);
      if (at < 0) continue;
      const relative = decodeURIComponent(entry.url.slice(at + PREFIX.length).split("?")[0]);
      const file = files.get(relative);
      if (!file) continue; // A script that is not in web/ (for example one a test made up).
      file.loaded = true;
      for (const fn of entry.functions) {
        const first = fn.ranges?.[0];
        if (!first) continue;
        const key = `${first.startOffset}-${first.endOffset}`;
        const known = file.functions.get(key) ?? { name: fn.functionName || "(anonymous)", line: lineOf(file.text, first.startOffset), ran: false };
        known.ran = known.ran || first.count > 0;
        file.functions.set(key, known);
      }
    }
  }
}

const rows = [];
const never = [];
let totalFunctions = 0, totalRan = 0;
for (const [relative, file] of [...files].sort(([a], [b]) => a.localeCompare(b))) {
  const all = [...file.functions.values()];
  const ran = all.filter((fn) => fn.ran).length;
  totalFunctions += all.length;
  totalRan += ran;
  const percent = all.length ? Math.round((100 * ran) / all.length) : null;
  rows.push({ relative, loaded: file.loaded, functions: all.length, ran, percent });
  for (const fn of all.filter((item) => !item.ran)) never.push({ relative, line: fn.line, name: fn.name });
}

const cell = (value) => String(value).replace(/\|/g, "\\|");
const out = [];
out.push(`JavaScript coverage of the end-to-end tests: ${runs} test runs, ${totalRan} of ${totalFunctions} functions called (${
  totalFunctions ? Math.round((100 * totalRan) / totalFunctions) : 0} %).`);
out.push("");
out.push("| File | Functions | Called | % | Loaded |");
out.push("| --- | ---: | ---: | ---: | --- |");
for (const row of rows) {
  out.push(`| ${cell(row.relative)} | ${row.functions} | ${row.ran} | ${row.percent ?? "-"} | ${row.loaded ? "yes" : "no test loads it"} |`);
}
out.push("");
out.push(`Functions no test called: ${never.length}.`);
for (const item of never) out.push(`- ${item.relative}:${item.line} ${item.name}`);

const text = out.join("\n") + "\n";
process.stdout.write(text);
if (process.env.GITHUB_STEP_SUMMARY) fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, text);
