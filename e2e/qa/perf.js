// How fast DiceForge stays with a lot of data: thousands of wildcard files, a big yaml card pack, thousands of LoRAs, a big tag list, a canvas
// full of DiceForge nodes. Adds the data to the running e2e server's folders (under perf/, removed at the end), times the routes and the windows,
// and compares each time with its budget and with the last run. For the perf agent (.claude/agents/perf.md) and anyone after a change that
// touches lists, search or the canvas.
//   node e2e/qa/perf.js [--scale 1] [--keep]       --scale 2: twice the data; --keep: leave the data for a closer look
// Needs the e2e server running (e2e/qa/serve.sh start). Writes e2e/qa/out/perf/<time>.json and prints a table.
const fs = require("fs");
const path = require("path");
const { BASE, URL } = require("../settings");
const { addNodes, clickMenu } = require("../helpers");
const { ALL_NODES } = require("../ui-shared");
const { open, outPath } = require("./lib");

const option = (name, fallback) => {
  const at = process.argv.indexOf(`--${name}`);
  return at > 0 ? process.argv[at + 1] : fallback;
};
const SCALE = Number(option("scale", 1));
const COUNTS = Object.fromEntries(Object.entries({ wildcards: 3000, yamlKeys: 1000, loras: 1500, tags: 100000, nodes: 100 })
  .map(([name, count]) => [name, Math.max(10, Math.round(count * SCALE))]));
// Budgets in milliseconds, for SCALE 1 on a CPU-only machine: over it is SLOW, over twice is TOO SLOW.
const BUDGETS = {
  "GET wildcards list": 1500, "GET wildcards search": 1500, "POST wildcards replace (preview)": 3000, "GET model-browser loras": 3000,
  "GET tags (autocomplete)": 300, "GET tags/browse": 1500, "GET object_info DiceForgeLoraStack": 1500,
  "Wildcard Browser: open": 3000, "Wildcard Browser: search": 1500, "LoRA Browser: open": 4000, "LoRA Browser: search": 1500,
  "Canvas: add nodes": 5000, "Canvas: save and load": 5000,
};

const PERF = (...parts) => path.join(BASE, ...parts);
const DATA = [PERF("models", "wildcards", "perf"), PERF("models", "loras", "perf"), PERF("user", "DiceForge", "tags", "perf_tags.csv")];
const words = ["red", "blue", "long hair", "short hair", "smile", "night", "forest", "city", "rain", "school uniform", "dress", "armor"];

function makeData() {
  for (let index = 0; index < COUNTS.wildcards; index++) {
    const file = PERF("models", "wildcards", "perf", `group${index % 30}`, `list${index}.txt`);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, Array.from({ length: 20 }, (_, line) => `${words[(index + line) % words.length]} ${index}-${line}`).join("\n"));
  }
  const yaml = Array.from({ length: COUNTS.yamlKeys }, (_, index) => `card${index}:\n  - ${words[index % words.length]} ${index}\n  - __perf/group1/list1__`).join("\n");
  fs.writeFileSync(PERF("models", "wildcards", "perf", "cards.yaml"), yaml);
  for (let index = 0; index < COUNTS.loras; index++) {
    const file = PERF("models", "loras", "perf", `set${index % 20}`, `lora_${index}.safetensors`);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, `perf lora ${index}`);
  }
  fs.mkdirSync(path.dirname(DATA[2]), { recursive: true });
  fs.writeFileSync(DATA[2], Array.from({ length: COUNTS.tags }, (_, index) => `perf_tag_${index},0,${COUNTS.tags - index},`).join("\n"));
}
const removeData = () => DATA.forEach((item) => fs.rmSync(item, { recursive: true, force: true }));

// The median of three runs of a step, in milliseconds.
async function timed(step) {
  const times = [];
  for (let run = 0; run < 3; run++) {
    const start = performance.now();
    await step(run);
    times.push(performance.now() - start);
  }
  return times.sort((a, b) => a - b)[1];
}

async function routes() {
  const get = async (route) => {
    const response = await fetch(URL + route);
    if (!response.ok) throw new Error(`${route}: ${response.status}`);
    await response.arrayBuffer();
  };
  const post = async (route, body) => {
    const response = await fetch(URL + route, { method: "POST", body: JSON.stringify(body) });
    if (!response.ok) throw new Error(`${route}: ${response.status} ${await response.text()}`);
    await response.arrayBuffer();
  };
  return {
    "GET wildcards list": await timed(() => get("/diceforge/wildcards")),
    "GET wildcards search": await timed(() => get("/diceforge/wildcards/search?q=forest")),
    "POST wildcards replace (preview)": await timed(() => post("/diceforge/wildcards/replace", { find: "forest", replace: "woods", apply: false })),
    "GET model-browser loras": await timed(() => get("/diceforge/model-browser?kind=loras")),
    "GET tags (autocomplete)": await timed((run) => get(`/diceforge/tags?q=perf_tag_${run}9&limit=12`)),
    "GET tags/browse": await timed(() => get("/diceforge/tags/browse?q=perf_tag_9")),
    "GET object_info DiceForgeLoraStack": await timed(() => get("/object_info/DiceForgeLoraStack")),
  };
}

async function windows(page) {
  const times = {};
  const [clip, loader] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60] }, { type: "LoraLoader", pos: [900, 60] }]);
  const openAndClose = async (open, ready, close) => {
    const start = performance.now();
    await open();
    await ready();
    const time = performance.now() - start;
    await close();
    return time;
  };
  times["Wildcard Browser: open"] = await timed(() => openAndClose(() => clickMenu(page, clip, "DiceForge.Wildcards", "Wildcard Browser"),
    () => page.locator(".dfwc .row", { hasText: "perf" }).first().waitFor(), () => page.keyboard.press("Escape")));
  await clickMenu(page, clip, "DiceForge.Wildcards", "Wildcard Browser");
  const wildcardSearch = page.locator(".dfwc input[placeholder^='Search wildcards']");
  times["Wildcard Browser: search"] = await timed(async (run) => {
    const name = `list${Math.floor(COUNTS.wildcards / 2) + run}`; // A file of the data, whatever its size.
    await wildcardSearch.fill(name);
    await page.locator(".dfwc .row", { hasText: name }).first().waitFor();
  });
  await wildcardSearch.fill("");
  await page.keyboard.press("Escape");
  times["LoRA Browser: open"] = await timed(() => openAndClose(() => clickMenu(page, loader, "DiceForge.ModelBrowser", "LoRA Browser"),
    () => page.locator(".dflb .card").first().waitFor(), () => page.keyboard.press("Escape")));
  await clickMenu(page, loader, "DiceForge.ModelBrowser", "LoRA Browser");
  const loraSearch = page.locator(".dflb input[placeholder^='Search by file']");
  times["LoRA Browser: search"] = await timed(async (run) => {
    const name = `lora_${Math.floor(COUNTS.loras / 2) + run}`;
    await loraSearch.fill(name);
    await page.locator(".dflb .card", { hasText: name }).first().waitFor();
  });
  await page.keyboard.press("Escape");
  return times;
}

async function canvas(page) {
  const types = Array.from({ length: COUNTS.nodes }, (_, index) => ALL_NODES[index % ALL_NODES.length]);
  const add = await timed(async () => {
    await page.evaluate(() => window.app.graph.clear());
    await page.evaluate((types) => types.forEach((type, index) => {
      const node = window.LiteGraph.createNode(type);
      node.pos = [(index % 10) * 520, Math.floor(index / 10) * 700];
      window.app.graph.add(node);
    }), types);
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  });
  const reload = await timed(() => page.evaluate(async () => {
    await window.app.loadGraphData(window.app.graph.serialize());
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  }));
  await page.evaluate(() => window.app.graph.clear());
  return { "Canvas: add nodes": add, "Canvas: save and load": reload };
}

function verdict(name, time) {
  const budget = (BUDGETS[name] ?? Infinity) * SCALE;
  if (time > budget * 2) return "TOO SLOW";
  return time > budget ? "SLOW" : "ok";
}

function lastRun() {
  const folder = outPath("perf", "x");
  const files = fs.readdirSync(path.dirname(folder)).filter((name) => name.endsWith(".json")).sort((a, b) => a.localeCompare(b));
  return files.length ? JSON.parse(fs.readFileSync(path.join(path.dirname(folder), files.at(-1)), "utf8")) : null;
}

(async () => {
  const before = lastRun();
  removeData();
  console.log(`Data: ${COUNTS.wildcards} wildcard files, ${COUNTS.yamlKeys} yaml cards, ${COUNTS.loras} LoRAs, ${COUNTS.tags} tags; ${COUNTS.nodes} nodes`);
  makeData();
  const results = { scale: SCALE, counts: COUNTS, times: {}, errors: [] };
  try {
    console.log("The routes…");
    Object.assign(results.times, await routes());
    for (const vue of [true, false]) {
      const { browser, page, errors } = await open({ vue });
      const design = vue ? "Nodes 2.0" : "classic";
      try {
        console.log(`${design}: the windows…`);
        for (const [name, time] of Object.entries(await windows(page))) results.times[`${name} (${design})`] = time;
        console.log(`${design}: the canvas…`);
        for (const [name, time] of Object.entries(await canvas(page))) results.times[`${name} (${design})`] = time;
        results.errors.push(...errors.map((error) => `${design}: ${error}`));
      } finally {
        await browser.close();
      }
    }
  } finally {
    if (!process.argv.includes("--keep")) removeData();
  }
  const file = outPath("perf", `${new Date().toISOString().replace(/[:.]/g, "-")}.json`);
  fs.writeFileSync(file, JSON.stringify(results, null, 2));
  let slow = 0;
  for (const [name, time] of Object.entries(results.times)) {
    const state = verdict(name.replace(/ \((Nodes 2\.0|classic)\)$/, ""), time);
    slow += state === "ok" ? 0 : 1;
    const previous = before?.scale === SCALE ? before.times[name] : undefined;
    const change = previous ? ` (last ${Math.round(previous)} ms, ${time > previous ? "+" : ""}${Math.round(((time - previous) / previous) * 100)}%)` : "";
    console.log(`${state.padEnd(8)} ${String(Math.round(time)).padStart(6)} ms  ${name}${change}`);
  }
  if (results.errors.length) console.log(`Page errors:\n  ${results.errors.join("\n  ")}`);
  console.log(`${slow} over budget. Saved: ${file}`);
  process.exitCode = slow || results.errors.length ? 1 : 0;
})().catch((error) => {
  console.error(error);
  if (!process.argv.includes("--keep")) removeData();
  process.exitCode = 2;
});
