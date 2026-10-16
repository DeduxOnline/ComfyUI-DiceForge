// Helpers for the end-to-end tests: running workflows through ComfyUI's queue, and driving the ComfyUI page (in the Nodes 2.0 or classic design).
const fs = require("fs");
const path = require("path");
const { test: base, expect } = require("@playwright/test");
const { BASE } = require("./settings");

// Every test fails on an uncaught error in the page (a broken frontend extension).
const test = base.extend({
  pageErrors: [async ({ page }, use) => {
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await use(errors);
    expect(errors, "errors in the page").toEqual([]);
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
// cancel, or the text to type in a prompt (true keeps its proposed text). times: how many to answer (all by default).
async function answerQuestions(page, answer = () => true, times) {
  const question = page.locator('[role="dialog"]').filter({ has: page.locator("h2", { hasText: /^DiceForge$/ }) });
  await page.addLocatorHandler(question, async (dialog) => {
    const field = dialog.locator("input");
    const prompt = (await field.count()) > 0;
    const reply = await answer({ prompt, text: await dialog.innerText() });
    if (reply === false || reply == null) return dialog.getByRole("button", { name: prompt ? "Close" : "Cancel" }).click();
    if (typeof reply === "string") await field.fill(reply);
    await dialog.getByRole("button", { name: "Confirm" }).click();
  }, times ? { times } : undefined);
}

module.exports = { test, expect, runPrompt, shown, basePath, writeFile, openComfy, addNodes, connect, widgetValue, setWidget, menuItems, clickMenu, queueFromPage, nodeElement, answerQuestions };
