// QA tools, for the tester agent (.claude/agents/tester.md) and anyone checking DiceForge by eye: ComfyUI in either node design on the e2e
// server (node server.js), pictures of nodes, pictures side by side, and a node measured for empty areas and cut-off content. What they write
// goes to e2e/qa/out (not in git).
const fs = require("fs");
const path = require("path");
const { chromium } = require("@playwright/test");
const { URL } = require("../settings");
const { openComfy } = require("../helpers");

const OUT = path.join(__dirname, "out");
// A file under e2e/qa/out, its folder made.
function outPath(...parts) {
  const file = path.join(OUT, ...parts);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  return file;
}

// The Chromium: CHROMIUM_PATH, else Playwright's own, else one kept for the machine in PLAYWRIGHT_BROWSERS_PATH/chromium (another Playwright's).
function chromiumPath() {
  if (process.env.CHROMIUM_PATH) return process.env.CHROMIUM_PATH;
  if (fs.existsSync(chromium.executablePath())) return undefined;
  const shared = process.env.PLAYWRIGHT_BROWSERS_PATH ? path.join(process.env.PLAYWRIGHT_BROWSERS_PATH, "chromium") : "";
  return shared && fs.existsSync(shared) ? shared : undefined;
}

// A browser on the e2e server's ComfyUI, in Nodes 2.0 (vue) or the classic design, with an empty graph. errors gets what the page reports:
// uncaught errors, and console errors once the page is open (while it opens, ComfyUI asks for user files that are not there yet) of the page
// itself (not of other sites it asks, like ComfyUI's release news).
async function open({ vue = true, width = 1800, height = 1300 } = {}) {
  const browser = await chromium.launch({ executablePath: chromiumPath() });
  const page = await browser.newPage({ baseURL: URL, viewport: { width, height } });
  const errors = [];
  let opened = false;
  page.on("pageerror", (error) => errors.push(`page error: ${error.message}`));
  page.on("console", (message) => {
    const where = message.location()?.url ?? "";
    const place = where ? ` (${where})` : "";
    if (opened && message.type() === "error" && (!where || where.startsWith(URL))) errors.push(`console: ${message.text()}${place}`);
  });
  await openComfy(page, { vue });
  opened = true;
  return { browser, page, errors, vue };
}

const frames = (page) => page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));

// A picture of a node, its title included, at e2e/qa/out/<name>.png; returns the file.
async function shot(page, id, name) {
  const file = outPath(`${name}.png`);
  await page.evaluate(() => window.app.canvas.setDirty(true, true));
  await frames(page);
  const element = page.locator(`[data-node-id="${id}"]`);
  if (await element.count()) {
    await element.screenshot({ path: file });
    return file;
  }
  const clip = await page.evaluate((id) => { // The classic canvas: the node's box on the page.
    const { app, LiteGraph } = window, node = app.graph.getNodeById(id), { scale, offset } = app.canvas.ds;
    const canvas = app.canvas.canvas.getBoundingClientRect(), title = LiteGraph.NODE_TITLE_HEIGHT;
    return { x: canvas.left + (node.pos[0] + offset[0]) * scale - 4, y: canvas.top + (node.pos[1] - title + offset[1]) * scale - 4,
      width: node.size[0] * scale + 8, height: (node.size[1] + title) * scale + 8 };
  }, id);
  await page.screenshot({ path: file, clip });
  return file;
}

// Pictures side by side in one picture, at e2e/qa/out/<name>.png: rows of { title, pictures: [{ label, file }] }. Returns the file.
async function sheet(browser, rows, name) {
  const page = await browser.newPage({ viewport: { width: 1700, height: 900 } });
  const escape = (text) => String(text).replace(/[&<>"]/g, (character) => `&#${character.codePointAt(0)};`);
  const picture = ({ label, file }) => `<figure><figcaption>${escape(label)}</figcaption><img src="data:image/png;base64,${fs.readFileSync(file).toString("base64")}"></figure>`;
  const row = ({ title, pictures }) => `<section><h2>${escape(title)}</h2><div>${pictures.map(picture).join("")}</div></section>`;
  await page.setContent(`<style>body{background:#151515;color:#ddd;font:13px system-ui,sans-serif;margin:10px}h2{font-size:14px;color:#ffd24a;margin:8px 0 4px}
    section>div{display:flex;gap:14px;align-items:flex-start}figure{margin:0}figcaption{color:#8ab4f8;margin-bottom:3px}img{max-width:400px;display:block}</style>
    ${rows.map(row).join("")}`);
  const file = outPath(`${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  await page.close();
  return file;
}

// A node measured in the page: what it is, its heights, and its problems (empty: none found):
// - an empty area: under the widgets (the classic canvas), in the body (Nodes 2.0), or under a panel's content (a preview, a list: any widget of
//   the page's own elements that is no text field, which may grow);
// - cut-off content: a panel's content taller than its place (unless it scrolls), a classic node shorter than what it shows.
// GAP: how much empty height counts: the classic canvas leaves 8 to 16 pixels under the last widget of a fitted node, real gaps are 40 and more.
const GAP = 24;
async function measure(page, id) {
  const node = await page.evaluate(measureNode, [id, GAP]);
  const panels = await page.evaluate(measurePanels, [id, GAP]);
  return { ...node, panels: panels.panels, problems: [...panels.problems, ...node.problems] };
}

// In the page: the node as a whole (Nodes 2.0: what is left of its body after its parts; classic: what is under its last widget).
function measureNode([id, gap]) {
  const { app, LiteGraph } = window, node = app.graph.getNodeById(id), problems = [];
  app.canvas.draw(true, true);
  const root = document.querySelector(`[data-node-id="${id}"]`);
  const result = { id, type: node.type, design: root ? "vue" : "classic", stored: Math.round(node.size[1]), fits: Math.round(node.computeSize()[1]), problems };
  if (root) {
    const body = root.querySelector('[data-testid^="node-body"]');
    if (!body) return result;
    const style = getComputedStyle(body);
    const parts = [...body.children].filter((child) => child.offsetParent !== null && getComputedStyle(child).position !== "absolute");
    const taken = parts.reduce((sum, part) => sum + part.offsetHeight, 0) + (Number.parseFloat(style.rowGap) || 0) * Math.max(0, parts.length - 1);
    result.free = Math.round(body.clientHeight - Number.parseFloat(style.paddingTop) - Number.parseFloat(style.paddingBottom) - taken);
    if (result.free > gap) problems.push(`${result.free}px empty in the node`);
    return result;
  }
  const shown = (node.widgets ?? []).filter((widget) => !widget.hidden && widget.type !== "hidden" && widget.y !== undefined && node.isWidgetVisible?.(widget) !== false);
  const height = (widget) => widget.computedHeight ?? widget.computeSize?.(node.size[0])?.[1] ?? LiteGraph.NODE_WIDGET_HEIGHT;
  result.free = Math.round(node.size[1] - Math.max(0, ...shown.map((widget) => widget.y + height(widget))));
  if (shown.length && result.free > gap) problems.push(`${result.free}px empty under the widgets`);
  if (node.size[1] < node.computeSize()[1] - 2) problems.push(`shorter than what it shows (${result.stored} of ${result.fits})`);
  return result;
}

// In the page: the node's panels, the widgets of its own elements that are no text fields (a text field may take the extra height). Each needs
// what its children take, from the first one's top to the last one's bottom, with its padding and border, and has its row (Nodes 2.0) or its
// own box (classic).
function measurePanels([id, gap]) {
  const node = window.app.graph.getNodeById(id), vue = !!document.querySelector(`[data-node-id="${id}"]`), panels = [], problems = [];
  const px = (element, keys) => keys.reduce((sum, key) => sum + (Number.parseFloat(getComputedStyle(element)[key]) || 0), 0);
  const needs = (element) => {
    const shown = [...element.children].filter((child) => child.offsetParent !== null);
    const frame = px(element, ["paddingTop", "paddingBottom", "borderTopWidth", "borderBottomWidth"]);
    if (!shown.length) return frame;
    return Math.max(...shown.map((child) => child.offsetTop + child.offsetHeight)) - Math.min(...shown.map((child) => child.offsetTop)) + frame;
  };
  const elements = (node.widgets ?? []).filter((widget) => widget.element?.offsetParent && !widget.element.matches("textarea") && !widget.element.querySelector("textarea"));
  for (const { name, element } of elements) {
    const room = vue ? (element.closest('[data-testid="node-widget"]') ?? element).offsetHeight : element.offsetHeight;
    const content = needs(element), scrolls = /auto|scroll/.test(getComputedStyle(element).overflowY);
    panels.push({ name, room, needs: Math.round(content) });
    if (room - content > gap) problems.push(`${name}: ${Math.round(room - content)}px empty under its content`);
    if (!scrolls && Math.max(content, element.scrollHeight) - Math.max(room, element.offsetHeight) > 2) problems.push(`${name}: content cut off (${Math.round(content)}px in ${room}px)`);
  }
  return { panels, problems };
}

// The graph saved and loaded again with every node `height` tall (a workflow saved so, without the fitted height node_size.js keeps, which
// would make it the user's height): the ids stay.
async function reloadTall(page, height = 900) {
  const workflow = await page.evaluate(() => window.app.graph.serialize());
  for (const node of workflow.nodes) {
    node.size = [node.size[0], height];
    delete node.properties?.dice_forge_height;
  }
  await page.evaluate(async (data) => {
    window.app.graph.clear();
    await window.app.loadGraphData(data);
    window.app.canvas.ds.scale = 1;
    window.app.canvas.ds.offset = [0, 0];
  }, workflow);
  await page.waitForTimeout(700);
  await frames(page);
}

module.exports = { OUT, outPath, chromiumPath, open, frames, shot, sheet, measure, reloadTall, GAP };
