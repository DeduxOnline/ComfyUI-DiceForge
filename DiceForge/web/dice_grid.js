import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addStyleOnce, askConfirm, background, element, fitToContent } from "./dom.js";
import { fitNodeHeight } from "./node_size.js";
import { request } from "./comfy.js";
import { addThemeStyle } from "./theme.js";

// The cells of Dice Grid's grid under the node, to keep the best ones: click a cell to star it (★), 💾 Save kept puts the starred ones at full size
// in the output folder (DiceForge/kept), each with the workflow of its run in it like Save Image, and ↺ opens a cell's run (its workflow, seeds
// included) to make it again or go on from it. The cells are those of the grid being made, or the last finished one until the next run.
const NODE_TYPE = "DiceForgeGrid";
const STYLE = `
.dfdg{display:flex;flex-direction:column;gap:5px;box-sizing:border-box;padding:2px 0}
.dfdg .head{display:flex;gap:6px;align-items:center}.dfdg .head .title{flex:1;color:var(--df-muted)}
.dfdg .cells{display:grid;grid-template-columns:repeat(auto-fill,minmax(64px,1fr));gap:4px;max-height:260px;overflow:auto}
.dfdg .cell{position:relative;border:2px solid transparent;border-radius:6px;overflow:hidden;cursor:pointer;background:var(--df-field)}
.dfdg .cell img{width:100%;display:block}.dfdg .cell.kept{border-color:#ffd24a}
.dfdg .cell .star{position:absolute;top:2px;left:3px;color:#ffd24a;font-size:14px;text-shadow:0 0 3px #000}
.dfdg .cell .open{position:absolute;bottom:2px;right:2px;background:#000b;border:none;border-radius:4px;color:#ddd;font-size:12px;padding:0 4px;cursor:pointer}
.dfdg .cell .label{position:absolute;bottom:0;left:0;right:0;background:#000a;color:#ddd;font-size:10px;padding:0 3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dfdg .status{color:var(--df-ok)}
`;
const widgetValue = (node, name, fallback) => node.widgets?.find((widget) => widget.name === name)?.value ?? fallback;
const query = (node, extra = {}) => new URLSearchParams({ node: String(node.id), name: widgetValue(node, "name", "grid"), ...extra });

app.registerExtension({
  name: "DiceForge.DiceGridCells",
  nodeCreated(node) {
    if (node.comfyClass !== NODE_TYPE) return;
    addThemeStyle();
    addStyleOnce("dfdg-style", STYLE);
    const panel = element("div", { class: "dfdg df-ui" });
    fitToContent(node.addDOMWidget("grid_cells", "diceforge_grid_cells", panel, { serialize: false }), panel);
    let cells = [], status = "", stamp = Date.now();
    const say = (text) => { status = text; render(); };
    async function load() {
      try {
        cells = (await request(`/diceforge/grid?${query(node)}`)).cells;
      } catch {
        cells = [];
      }
      stamp = Date.now();
      render();
    }
    async function keep(cell) {
      try {
        const kept = new Set((await request("/diceforge/grid/keep", { method: "POST", body: JSON.stringify({ node: String(node.id), name: widgetValue(node, "name", "grid"), file: cell.file, kept: !cell.kept }) })).kept);
        cells = cells.map((item) => ({ ...item, kept: kept.has(item.file) }));
        render();
      } catch (error) {
        say(error.message);
      }
    }
    async function saveKept() {
      try {
        const { saved } = await request("/diceforge/grid/save", { method: "POST", body: JSON.stringify({ node: String(node.id), name: widgetValue(node, "name", "grid") }) });
        say(`Saved ${saved.length} in output: ${saved.join(", ")}`);
      } catch (error) {
        say(error.message);
      }
    }
    async function openRun(cell) {
      if (!(await askConfirm("Open the workflow of this run (its prompts and seeds), as dropping its image on ComfyUI would?"))) return;
      const response = await api.fetchApi(`/diceforge/grid/image?${query(node, { file: cell.file, full: "1" })}`);
      if (!response.ok) return say(await response.text());
      const file = new File([await response.blob()], `dice-grid-${cell.file}`, { type: "image/png" });
      await app.handleFile(file);
    }
    function render() {
      const kept = cells.filter((cell) => cell.kept).length;
      const tiles = cells.map((cell) => {
        const label = [cell.row, cell.label].filter(Boolean).join(" / ");
        const tile = element("div", { class: "cell" + (cell.kept ? " kept" : ""), title: `${label ? `${label}: ` : ""}click to ${cell.kept ? "unstar" : "star (keep)"} it`,
          onclick: () => background(keep(cell)) },
        element("img", { src: api.apiURL(`/diceforge/grid/image?${query(node, { file: cell.file, t: stamp })}`), loading: "lazy" }),
        ...(cell.kept ? [element("span", { class: "star" }, "★")] : []),
        ...(label ? [element("span", { class: "label" }, label)] : []),
        ...(cell.full ? [element("button", { class: "open", title: "Open this run's workflow (prompts, seeds) to make it again", onclick: (event) => { event.stopPropagation(); background(openRun(cell)); } }, "↺")] : []));
        return tile;
      });
      panel.replaceChildren(
        element("div", { class: "head" }, element("span", { class: "title" }, cells.length ? `${cells.length} cells · ${kept} kept` : ""),
          element("button", { class: "save primary", ...(kept ? {} : { disabled: "" }), title: "Save the starred cells at full size in output/DiceForge/kept, with their workflow", onclick: () => background(saveKept()) }, `💾 Save ${kept} kept`)),
        cells.length ? element("div", { class: "cells" }, ...tiles) : element("div", { class: "empty" }, "Run the workflow: the cells of the grid show here, to star the best ones."),
        ...(status ? [element("div", { class: "status" }, status)] : []));
      fitNodeHeight(node);
    }
    const onExecuted = node.onExecuted;
    node.onExecuted = function () {
      status = "";
      background(load());
      return onExecuted?.apply(this, arguments);
    };
    node.diceforgeLoadCells = load; // For the tests.
    render();
    setTimeout(() => background(load()), 300); // A loaded workflow: the grid it was making (the node's id is known by then).
  },
});
