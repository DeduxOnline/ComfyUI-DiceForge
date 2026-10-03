import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addStyleOnce, background, element } from "./dom.js";
import { fitNodeHeight } from "./node_size.js";

// XY Plot shows under its fields what the plot will be: the values of X and Y as the grid's headers, the number of images, or what is wrong with
// a field. ▶ Queue N queues every cell, one run each with index 0, 1, 2…; click again to stop queueing (the runs already queued stay).
const NODE_TYPE = "DiceForgeXYPlot";
const FIELDS = ["x_type", "x_values", "y_type", "y_values"];
const SHOWN = 10; // Labels shown per axis; the rest as "+N".
const STYLE = `
.dfxy{font:12px system-ui,sans-serif;color:#ccc;display:flex;flex-direction:column;gap:5px;box-sizing:border-box;padding:2px 0}
.dfxy .axis{display:flex;flex-wrap:wrap;gap:3px;align-items:center}.dfxy .axis b{color:#999;font-weight:600;margin-right:3px}
.dfxy .axis span{background:#262626;border:1px solid #4a4a4a;border-radius:4px;padding:0 5px}.dfxy .error{color:#ff9a9a;white-space:pre-wrap}
.dfxy button{background:#24402a;color:#d6f5dc;border:1px solid #4a7a4a;border-radius:6px;padding:5px 10px;cursor:pointer;font:inherit;font-weight:600}
.dfxy button:hover{background:#2c4f33}.dfxy button.stop{background:#4a2a2a;border-color:#8a4a4a;color:#ffd6d6}.dfxy .hint{color:#888}
`;

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

app.registerExtension({
  name: "DiceForge.XYPlot",
  nodeCreated(node) {
    if (node.comfyClass !== NODE_TYPE) return;
    addStyleOnce("dfxy-style", STYLE);
    const panel = element("div", { class: "dfxy" });
    node.addDOMWidget("xy_preview", "diceforge_xy_preview", panel, { serialize: false, getMinHeight: () => panel.scrollHeight + 4 });
    let shownKey = null, plan = null, error = "", queueing = null; // queueing: { done, stop } while ▶ Queue runs.
    const axis = (name, type, labels) => element("div", { class: "axis" }, element("b", {}, `${name} · ${type}`),
      ...labels.slice(0, SHOWN).map((text) => element("span", {}, text)), ...(labels.length > SHOWN ? [element("span", {}, `+${labels.length - SHOWN}`)] : []));
    function render() {
      if (error) {
        panel.replaceChildren(element("div", { class: "error" }, error));
      } else if (plan) {
        const button = element("button", { class: queueing ? "stop" : "", title: queueing ? "Stop queueing (the runs already queued stay)" : "Queue a run for every cell, index 0 to the last",
          onclick: () => {
            if (queueing) queueing.stop = true;
            else background(queueAll());
          } },
        queueing ? `■ Stop (${queueing.done} / ${plan.count} queued)` : `▶ Queue ${plan.count} image${plan.count === 1 ? "" : "s"}`);
        panel.replaceChildren(
          ...(plan.x_type === "none" ? [element("div", { class: "hint" }, "Pick what changes on X (and Y) to make a plot.")] : [axis("X", plan.x_type, plan.x)]),
          ...(plan.y_type === "none" ? [] : [axis("Y", plan.y_type, plan.y)]),
          element("div", { class: "hint" }, plan.y_type === "none" ? `${plan.x.length} images in one row` : `${plan.x.length} × ${plan.y.length} = ${plan.count} images`),
          button);
      } else {
        panel.replaceChildren();
      }
      fitNodeHeight(node);
    }
    async function refresh() {
      const values = Object.fromEntries(FIELDS.map((name) => [name, widgetOf(node, name)?.value ?? ""]));
      const key = JSON.stringify(values);
      if (key === shownKey) return;
      shownKey = key;
      try {
        plan = await preview(values);
        error = "";
      } catch (failure) {
        plan = null;
        error = failure.message;
      }
      if (key === shownKey) render(); // Not an older answer after a newer edit.
    }
    async function queueAll() {
      if (!plan || queueing) return;
      const count = plan.count;
      queueing = { done: 0, stop: false };
      render();
      try {
        for (let index = 0; index < count && !queueing.stop; index++) {
          setValue(node, "index", index);
          await app.queuePrompt(0, 1);
          queueing.done = index + 1;
          render();
        }
      } finally {
        queueing = null;
        setValue(node, "index", 0);
        render();
      }
    }
    node.diceforgeQueueAll = queueAll; // For the tests.
    const timer = setInterval(() => background(refresh()), 500);
    const onRemoved = node.onRemoved;
    node.onRemoved = function () {
      clearInterval(timer);
      return onRemoved?.apply(this, arguments);
    };
    background(refresh());
  },
});
