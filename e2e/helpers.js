// Helpers for the end-to-end tests: running workflows through ComfyUI's queue, and driving the ComfyUI page (in the Nodes 2.0 or classic design).
const fs = require("fs");
const path = require("path");
const { test: base, expect } = require("@playwright/test");
const { BASE } = require("./settings");

// Every test fails on an uncaught error in the page (a broken frontend extension), and on a DiceForge question it failed to answer.
const test = base.extend({
  pageErrors: [async ({ page }, use) => {
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await use(errors);
    expect(errors, "errors in the page").toEqual([]);
    expect(watchers.get(page)?.failures ?? [], "DiceForge questions not answered").toEqual([]);
  }, { auto: true }],
});

// Queues an API-format workflow and waits for it: { status, outputs, cached (node ids taken from the cache), error }, or { rejected } when
// ComfyUI refuses it before running (validation).
async function runPrompt(request, prompt) {
  const response = await request.post("/prompt", { data: { prompt, client_id: "diceforge-e2e", extra_data: { extra_pnginfo: { workflow: { diceforge_e2e: true } } } } });
  const body = await response.json();
  if (!response.ok()) return { rejected: body };
  const id = body.prompt_id;
  for (let attempt = 0; attempt < 600; attempt++) {
    const entry = (await (await request.get(`/history/${id}`)).json())[id];
    if (entry?.status?.status_str) {
      const messages = entry.status.messages ?? [];
      const cached = messages.find(([type]) => type === "execution_cached")?.[1]?.nodes ?? [];
      const error = messages.find(([type]) => type === "execution_error")?.[1];
      return { status: entry.status.status_str, outputs: entry.outputs, cached: cached.map(String), error: error?.exception_message };
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Prompt ${id} did not finish`);
}
// The text a Preview Any node showed.
const shown = (result, id) => result.outputs?.[id]?.text?.[0];
// A file in the test ComfyUI's base directory.
const basePath = (...parts) => path.join(BASE, ...parts);
function writeFile(relative, text) {
  const file = basePath(relative);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, text);
  const later = Date.now() / 1000 + 5; // A new modification time, even within the same second.
  fs.utimesSync(file, later, later);
  return file;
}

// Opens ComfyUI in the Nodes 2.0 (vue) or classic design, with an empty graph.
async function openComfy(page, { vue = true } = {}) {
  const ready = () => page.waitForFunction(() => window.app?.graph && window.LiteGraph && window.app.extensionManager?.setting, null, { timeout: 60_000 });
  await page.goto("/");
  await ready();
  if ((await page.evaluate(() => window.app.extensionManager.setting.get("Comfy.VueNodes.Enabled"))) !== vue) {
    await page.evaluate((value) => window.app.extensionManager.setting.set("Comfy.VueNodes.Enabled", value), vue);
    await page.reload();
    await ready();
  }
  // Ready when DiceForge's extensions are registered and the page has drawn twice (instead of a fixed second for every test).
  await page.waitForFunction(() => window.app.extensions?.some((extension) => extension.name === "DiceForge.Wildcards"), null, { timeout: 60_000 });
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.keyboard.press("Escape");
  await page.evaluate(() => {
    window.app.graph.clear();
    window.app.canvas.ds.scale = 1;
    window.app.canvas.ds.offset = [0, 0];
    window.app.canvas.setDirty(true, true);
  });
}

// Adds nodes: [{ type, pos, widgets: { name: value } }]; returns their ids.
async function addNodes(page, nodes) {
  const ids = await page.evaluate((nodes) => nodes.map(({ type, pos = [40, 40], widgets = {} }) => {
    const node = window.LiteGraph.createNode(type);
    node.pos = pos;
    window.app.graph.add(node);
    for (const [name, value] of Object.entries(widgets)) {
      const widget = node.widgets.find((widget) => widget.name === name);
      widget.value = value;
      widget.callback?.(value);
    }
    return node.id;
  }), nodes);
  await page.evaluate(() => window.app.canvas.setDirty(true, true));
  await page.waitForTimeout(500);
  return ids;
}
const connect = (page, from, output, to, input) => page.evaluate(([from, output, to, input]) => {
  const graph = window.app.graph;
  graph.getNodeById(from).connect(output, graph.getNodeById(to), input);
}, [from, output, to, input]);
const widgetValue = (page, id, name) => page.evaluate(([id, name]) => window.app.graph.getNodeById(id).widgets.find((widget) => widget.name === name).value, [id, name]);
const setWidget = (page, id, name, value) => page.evaluate(([id, name, value]) => {
  const widget = window.app.graph.getNodeById(id).widgets.find((widget) => widget.name === name);
  widget.value = value;
  widget.callback?.(value);
}, [id, name, value]);
// The node menu entries an extension adds, and clicking one of them (like the right-click menu does).
const menuItems = (page, id, extension) => page.evaluate(([id, extension]) =>
  window.app.extensions.find((item) => item.name === extension).getNodeMenuItems(window.app.graph.getNodeById(id)).map((item) => item.content), [id, extension]);
const clickMenu = (page, id, extension, content) => page.evaluate(([id, extension, content]) => {
  const items = window.app.extensions.find((item) => item.name === extension).getNodeMenuItems(window.app.graph.getNodeById(id));
  items.find((item) => item.content.includes(content)).callback();
}, [id, extension, content]);
// Queues the graph from the page (like the Run button) and waits for the queue to empty.
async function queueFromPage(page, request) {
  await page.evaluate(() => window.app.queuePrompt(0, 1));
  for (let attempt = 0; attempt < 300; attempt++) {
    await page.waitForTimeout(200);
    const queue = await (await request.get("/queue")).json();
    if (!queue.queue_running.length && !queue.queue_pending.length) return;
  }
  throw new Error("The queue did not empty");
}
// The element of a node in the page: its Nodes 2.0 element, or null in the classic design.
const nodeElement = (page, id) => page.locator(`[data-node-id="${id}"]`);

// The DiceForge questions (ComfyUI's dialogs titled DiceForge) answered as they show: answer({ prompt, text }) gives true to confirm, false to
// cancel, or the text to type in a prompt (true keeps its proposed text). times: how many to answer (all by default). It watches in the
// background, not as a locator handler: a handler only runs before a locator action or assertion, so a question raised by a node menu's
// callback and followed by expect.poll would never be answered. One watcher per page: a later call gives it new answers and a new count, so
// two can't race for the same question. An answer that fails (a button renamed, an answer function that throws) is logged at once and fails
// the test at its end (pageErrors), instead of leaving the question open without a word. It stops when the page closes.
const watchers = new WeakMap(); // page -> { answer, left, failures }
async function answerQuestions(page, answer = () => true, times = Infinity) {
  const known = watchers.get(page);
  if (known && !known.stopped) return void Object.assign(known, { answer, left: times });
  const state = { answer, left: times, failures: known?.failures ?? [], stopped: false };
  watchers.set(page, state);
  const question = page.locator('[role="dialog"]').filter({ has: page.locator("h2", { hasText: /^DiceForge$/ }) }).first();
  const reply = async (dialog) => {
    const field = dialog.locator("input");
    const prompt = (await field.count()) > 0;
    const given = await state.answer({ prompt, text: await dialog.innerText() });
    if (given === false || given == null) return dialog.getByRole("button", { name: prompt ? "Close" : "Cancel" }).click();
    if (typeof given === "string") await field.fill(given);
    await dialog.getByRole("button", { name: "Confirm" }).click();
  };
  const watch = async () => {
    for (;;) {
      await question.waitFor({ state: "visible", timeout: 0 });
      const shown = await question.elementHandle();
      // Past its count, a question is left to the test, until it closes or a later call gives answers for it.
      while (state.left <= 0 && await shown?.isVisible()) await page.waitForTimeout(100);
      if (state.left > 0 && await shown?.isVisible()) {
        state.left--;
        await reply(question);
      }
      await shown?.waitForElementState("hidden"); // Gone (or hidden) before the next question is looked for.
    }
  };
  watch().catch((error) => {
    state.stopped = true; // The next call starts a new watcher.
    if (page.isClosed()) return; // The end of the test.
    state.failures.push(error.message);
    console.error(`[e2e] A DiceForge question was not answered: ${error.message}`);
  });
}

module.exports = { test, expect, runPrompt, shown, basePath, writeFile, openComfy, addNodes, connect, widgetValue, setWidget, menuItems, clickMenu, queueFromPage, nodeElement, answerQuestions };
