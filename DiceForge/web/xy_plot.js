import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addStyleOnce, asking, background, element, fitToContent } from "./dom.js";
import { toast } from "./comfy.js";
import { fitNodeHeight } from "./node_size.js";
import { addThemeStyle } from "./theme.js";

// XY Plot keeps one row under its fields: the size of the plot and the cell the next run makes (or what is wrong with a field). index counts up
// after each run (control after generate: increment), so ComfyUI's own Run goes cell by cell: Set Run to N cells, in the node's menu, puts
// index back to the first cell and the batch count to the number of cells. Show the plot plan… opens the whole grid of headers in a window.
const NODE_TYPE = "DiceForgeXYPlot";
const FIELDS = ["x_type", "x_values", "y_type", "y_values"];
const STYLE = `
.dfxy{display:flex;flex-direction:column;box-sizing:border-box;padding:2px 0}
.dfxy .summary{min-height:var(--df-h);box-sizing:border-box;background:var(--df-surface);border:1px solid var(--df-line);border-radius:var(--df-r-field);padding:0 8px;
line-height:calc(var(--df-h) - 2px);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dfxy .error{color:var(--df-error);white-space:pre-wrap}
.dfxyp-back{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:10000;display:flex;align-items:center;justify-content:center}
.dfxyp{background:#353535;color:#ddd;border:1px solid #555;border-radius:10px;max-width:95vw;max-height:88vh;display:flex;flex-direction:column;gap:8px;padding:14px 16px;font:14px system-ui,sans-serif;box-shadow:0 10px 40px #000a;box-sizing:border-box}
.dfxyp h2{margin:0;font-size:20px;color:#fff}.dfxyp .top{display:flex;gap:8px;align-items:center}.dfxyp .top .muted{flex:1}.dfxyp .muted{color:#999;font-size:13px}
.dfxyp button{background:#222;color:#eee;border:1px solid #666;border-radius:6px;padding:3px 9px;cursor:pointer;font:inherit;font-size:13px}.dfxyp button:hover{background:#2c2c2c}
.dfxyp .grid{overflow:auto}.dfxyp table{border-collapse:collapse;font-size:13px}
.dfxyp th,.dfxyp td{border:1px solid #4a4a4a;padding:3px 8px;text-align:center;white-space:nowrap}.dfxyp th{background:#2a2a2a;color:#ccc;font-weight:600}
.dfxyp td{color:#999}.dfxyp td.next{background:#1e3a5f;color:#fff}.dfxyp .error{color:#ff9a9a;white-space:pre-wrap}
`;
const plans = new WeakMap(); // node -> { plan, error }: what its row shows, for its menu and window.

async function preview(values) {
  const response = await api.fetchApi("/diceforge/xy-plot", { method: "POST", body: JSON.stringify(values) });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}
const widgetOf = (node, name) => node.widgets?.find((widget) => widget.name === name);
function setValue(node, name, value) {
  const widget = widgetOf(node, name);
  if (!widget) return;
  widget.value = value;
  widget.callback?.(value);
  node.setDirtyCanvas?.(true, true);
}
// The cell a run at index makes (row by row, round again past the last one), with its column and row labels.
export function nextCell(plan, index) {
  const cell = (Number(index) || 0) % plan.count;
  return { cell, x: plan.x[cell % plan.x.length], y: plan.y_type === "none" ? "" : plan.y[Math.floor(cell / plan.x.length)] };
}
// The node's row: the plot's size and what the next run makes. With Widget control mode on before, index counts up before a run except the
// widget's first one, so which cell comes next can't be told.
export function summaryText(plan, index, before = false) {
  if (plan.x_type === "none") return "Pick what changes on X (and Y) to make a plot.";
  const size = plan.y_type === "none" ? plan.count + (plan.count === 1 ? " cell" : " cells") : `${plan.x.length} × ${plan.y.length} = ${plan.count} cells`;
  if (before) return `${size} · set Widget control mode to after to see the next cell`;
  const { x, y } = nextCell(plan, index);
  return `${size} · next: ${y ? x + ", " + y : x}`;
}
const countsBefore = () => app.extensionManager?.setting?.get("Comfy.WidgetControlMode") === "before";

// Index on the first cell and ComfyUI's batch count on the number of cells: Run then makes the whole plot, and Dice Grid gets it from its first
// cell (new_grid), as it needs to. With Widget control mode on before, the frontend counts up before a run, except a widget's very first one,
// which it keeps to itself: the first cell can't be told, so the plot asks for after (the default).
function setRun(node, plan) {
  const settings = app.extensionManager?.queueSettings;
  if (!settings) return toast("error", "XY Plot", "This ComfyUI has no batch count to set: queue the cells with Run, one by one.");
  if (countsBefore()) {
    return toast("warn", "XY Plot", "Set Widget control mode to after (Settings → Comfy → Node Widget): with before, a plot can't start at its first cell.");
  }
  setValue(node, "index", 0);
  setValue(node, "control_after_generate", "increment");
  settings.batchCount = plan.count;
  toast("info", `Run makes the ${plan.count} cells`, "The batch count is ComfyUI's, for every workflow: put it back to 1 after the plot.");
}

function openPlan(node) {
  addStyleOnce("dfxy-style", STYLE);
  const body = element("div", { class: "grid" });
  const info = element("span", { class: "muted" });
  const back = element("div", { class: "dfxyp-back" }, element("div", { class: "dfxyp" }, element("h2", {}, `XY plot · ${node.title || "XY Plot"}`),
    element("div", { class: "top" }, info, element("button", { onclick: () => close() }, "Close")), body));
  const onKey = (event) => { if (asking()) return; if (event.key === "Escape") { event.stopPropagation(); close(); } };
  let shownKey;
  const timer = setInterval(draw, 400); // The next cell moves with each run.
  function close() {
    clearInterval(timer);
    back.remove();
    document.removeEventListener("keydown", onKey, true);
  }
  back.addEventListener("mousedown", (event) => { if (event.target === back) close(); });
  document.addEventListener("keydown", onKey, true);
  function draw() {
    const { plan, error } = plans.get(node) ?? {};
    const index = widgetOf(node, "index")?.value, before = countsBefore();
    const key = JSON.stringify([plan, error, index, before]);
    if (key === shownKey) return;
    shownKey = key;
    if (!plan) {
      info.textContent = "";
      body.replaceChildren(element("div", { class: "error" }, error || "The plot is being read…"));
      return;
    }
    const next = before ? -1 : nextCell(plan, index).cell;
    const rows = plan.y_type === "none" ? [""] : plan.y;
    info.textContent = summaryText(plan, index, before) + (before ? "" : ` (cell ${next})`);
    body.replaceChildren(element("table", {},
      element("tr", {}, element("th", {}, plan.y_type === "none" ? plan.x_type : `${plan.y_type} \\ ${plan.x_type}`), ...plan.x.map((label) => element("th", {}, label))),
      ...rows.map((label, row) => element("tr", {}, element("th", {}, label),
        ...plan.x.map((_, column) => element("td", { class: row * plan.x.length + column === next ? "next" : "" }, String(row * plan.x.length + column)))))));
  }
  document.body.append(back);
  draw();
}

app.registerExtension({
  name: "DiceForge.XYPlot",
  nodeCreated(node) {
    if (node.comfyClass !== NODE_TYPE) return;
    addThemeStyle();
    addStyleOnce("dfxy-style", STYLE);
    const panel = element("div", { class: "dfxy df-ui" });
    fitToContent(node.addDOMWidget("xy_preview", "diceforge_xy_preview", panel, { serialize: false }), panel);
    let fieldsKey = null, planKey = null, shownKey = null, plan = null, error = ""; // planKey: the fields plan and error are for.
    function render() {
      const index = widgetOf(node, "index")?.value, before = countsBefore();
      const key = JSON.stringify([planKey, error, index, before]);
      if (key === shownKey) return;
      shownKey = key;
      plans.set(node, { plan, error });
      if (error) panel.replaceChildren(element("div", { class: "error" }, error));
      else if (plan) panel.replaceChildren(element("div", { class: "summary", title: "The plot, and the cell the next run makes" }, summaryText(plan, index, before)));
      else panel.replaceChildren();
      fitNodeHeight(node);
    }
    async function refresh() {
      const values = Object.fromEntries(FIELDS.map((name) => [name, widgetOf(node, name)?.value ?? ""]));
      const key = JSON.stringify(values);
      if (key !== fieldsKey) {
        fieldsKey = key;
        let answer = null, failed = "";
        try {
          answer = await preview(values);
        } catch (failure) {
          failed = failure.message;
        }
        if (key !== fieldsKey) return; // An older answer after a newer edit.
        [plan, error, planKey] = [answer, failed, key];
      }
      if (planKey === fieldsKey) render(); // Also when only index moved: the next cell.
    }
    const timer = setInterval(() => background(refresh()), 500);
    const onRemoved = node.onRemoved;
    node.onRemoved = function () {
      clearInterval(timer);
      return onRemoved?.apply(this, arguments);
    };
    background(refresh());
  },
  getNodeMenuItems(node) {
    if (node.comfyClass !== NODE_TYPE) return [];
    const plan = plans.get(node)?.plan;
    return [
      ...(plan && plan.x_type !== "none" ? [{ content: `▶ Set Run to ${plan.count} cells, from index 0`, callback: () => setRun(node, plan) }] : []),
      { content: "▦ Show the plot plan…", callback: () => openPlan(node) },
    ];
  },
});
