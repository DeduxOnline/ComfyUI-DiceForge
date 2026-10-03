import { app } from "../../scripts/app.js";
import { addStyleOnce, background, element } from "./dom.js";
import { fitNodeHeight } from "./node_size.js";
import { setField } from "./wildcards.js";

// CLIP Dual Text Encode shows, under its inputs, the positive and negative prompts as the last run encoded them: choices, wildcards and variables
// filled in, with the seed and mode they came from. Click a prompt to copy it. They are kept in the node's properties, so they are still there after
// a reload and travel with the workflow (also the one saved in an image). When a prompt was changed since, the preview is dimmed until the next run.
// History: the last runs' prompts (20, plus the pinned ones), newest first. From an entry: ↺ Seed puts back its prompts, seed and mode (with control
// after generate on fixed), so the next run gives the same prompts again (in the modes where the same seed does); Use text puts the prompts as
// encoded in the fields, every choice made; 📌 keeps it past the 20; ✕ removes it.
const NODE_TYPE = "CLIPTextEncodePositiveNegative";
const STYLE = `
.dfpp{font:12px system-ui,sans-serif;color:#ccc;display:flex;flex-direction:column;gap:4px;box-sizing:border-box;padding:2px 0;max-height:420px;overflow:auto}
.dfpp .head{color:#888;display:flex;gap:6px;justify-content:space-between}.dfpp .head .changed{color:#d9b36a}
.dfpp .box{background:#222;border:1px solid #444;border-radius:5px;padding:4px 6px;white-space:pre-wrap;word-break:break-word;cursor:copy;max-height:130px;overflow:auto}
.dfpp .box b{color:#888;font-weight:400;margin-right:6px}.dfpp .box.copied{border-color:#6a9a6a}.dfpp .empty{color:#777;font-style:italic}
.dfpp.stale .box{opacity:.55}
.dfpp .toggle{align-self:flex-start;background:none;border:none;color:#9cc8ff;cursor:pointer;padding:0;font:inherit}
.dfpp .history{display:flex;flex-direction:column;gap:3px}.dfpp .entry{border:1px solid #3a3a3a;border-radius:5px;padding:3px 5px;display:flex;flex-direction:column;gap:2px}
.dfpp .entry.pinned{border-color:#8a7a3a}.dfpp .entry .meta{display:flex;gap:4px;align-items:center;color:#888}.dfpp .entry .meta .when{flex:1}
.dfpp .entry .text{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#bbb}
.dfpp .entry button{background:#222;color:#ddd;border:1px solid #555;border-radius:4px;padding:0 5px;font:11px system-ui,sans-serif;cursor:pointer}
.dfpp .entry button:disabled{opacity:.4;cursor:default}.dfpp .entry button.on{border-color:#b8962e;color:#ffd24a}
`;
const HISTORY = 20; // Kept runs, the pinned ones not counted.
// The history with a new run first: a run like the newest one (a cached run, or the same seed again) is not added twice; past HISTORY, the oldest
// unpinned ones go.
export function addToHistory(history, entry, limit = HISTORY) {
  const list = Array.isArray(history) ? history.filter((item) => item && typeof item === "object") : [];
  const same = (item) => ["positive", "negative", "seed", "seed_mode", "source_positive", "source_negative"].every((key) => item[key] === entry[key]);
  if (list[0] && same(list[0])) return list;
  const next = [entry, ...list];
  let unpinned = 0;
  return next.filter((item) => item.pinned || ++unpinned <= limit);
}

app.registerExtension({
  name: "DiceForge.PromptPreview",
  nodeCreated(node) {
    if (node.comfyClass !== NODE_TYPE) return;
    addStyleOnce("dfpp-style", STYLE);
    const panel = element("div", { class: "dfpp" });
    node.addDOMWidget("prompt_preview", "diceforge_prompt_preview", panel, { serialize: false, getMinHeight: () => Math.min(panel.scrollHeight, 420) + 4 });
    const text = (name) => String(node.widgets?.find((widget) => widget.name === name)?.value ?? "");
    const box = (label, value) => {
      const item = element("div", { class: "box", title: "Click to copy" }, element("b", {}, label), value ? value : element("span", { class: "empty" }, "(empty)"));
      item.addEventListener("click", () => {
        background(navigator.clipboard?.writeText(value)); // A refused copy (no permission) is logged, not thrown.
        item.classList.add("copied");
        setTimeout(() => item.classList.remove("copied"), 600);
      });
      return item;
    };
    let shownFrom, shownHistory, historyOpen = false; // What the panel shows (undefined: not drawn yet), and whether the history is open.
    const widget = (name) => node.widgets?.find((item) => item.name === name);
    const setValue = (name, value) => {
      const item = widget(name);
      if (!item) return;
      item.value = value;
      item.callback?.(value);
    };
    const saveHistory = (history) => {
      node.properties ??= {};
      node.properties.dice_forge_history = history;
      render();
      node.graph?.setDirtyCanvas?.(true, true);
    };
    function historyEntry(item, index) {
      const when = item.time ? new Date(item.time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
      const update = (change) => {
        const history = [...(node.properties?.dice_forge_history ?? [])];
        change(history);
        saveHistory(history);
      };
      return element("div", { class: "entry" + (item.pinned ? " pinned" : ""), "data-index": index },
        element("div", { class: "meta" },
          element("span", { class: "when" }, `${when} · seed ${item.seed} (${item.seed_mode})`),
          element("button", { class: "pin" + (item.pinned ? " on" : ""), title: item.pinned ? "Pinned: kept past the last 20 (click to unpin)" : "Pin: keep it past the last 20",
            onclick: () => update((history) => { history[index] = { ...item, pinned: !item.pinned }; }) }, "📌"),
          element("button", { class: "reseed", // Every seed mode gives the same prompts for the same seed.
            title: "Put back its prompts, seed and mode (control after generate: fixed): the next run gives these prompts again",
            onclick: () => {
              if (item.source_positive != null) setField(node, "positive", item.source_positive);
              if (item.source_negative != null) setField(node, "negative", item.source_negative);
              setValue("seed", item.seed);
              setValue("seed_mode", item.seed_mode);
              setValue("control_after_generate", "fixed");
              node.setDirtyCanvas?.(true, true);
            } }, "↺ Seed"),
          element("button", { class: "use-text", title: "Put these prompts as encoded in the fields: every choice and wildcard fixed",
            onclick: () => { setField(node, "positive", item.positive ?? ""); setField(node, "negative", item.negative ?? ""); } }, "Use text"),
          element("button", { class: "forget", title: "Remove it from the history", onclick: () => update((history) => { history.splice(index, 1); }) }, "✕")),
        element("div", { class: "text", title: `${item.positive}${item.negative ? `\n\nnegative: ${item.negative}` : ""}` }, item.positive || "(empty)"));
    }
    function render() {
      const last = node.properties?.dice_forge_prompts;
      const history = Array.isArray(node.properties?.dice_forge_history) ? node.properties.dice_forge_history : [];
      shownFrom = last;
      shownHistory = node.properties?.dice_forge_history;
      if (!last) panel.replaceChildren(element("div", { class: "empty" }, "Run the workflow to see the prompts as encoded here."));
      else {
        const mode = [last.seed_mode, last.note].filter(Boolean).join(", ");
        const toggle = element("button", { class: "toggle", onclick: () => { historyOpen = !historyOpen; render(); } },
          `${historyOpen ? "▾" : "▸"} History (${history.length})`);
        panel.replaceChildren(element("div", { class: "head" }, element("span", {}, `Last run · seed ${last.seed}${mode ? ` (${mode})` : ""}`), element("span", { class: "changed" })),
          box("positive", last.positive ?? ""), box("negative", last.negative ?? ""),
          ...(history.length ? [toggle] : []), ...(historyOpen && history.length ? [element("div", { class: "history" }, ...history.map(historyEntry))] : []));
      }
      markStale();
      fitNodeHeight(node); // Room for the preview: taller in the classic canvas, no gap in Nodes 2.0 (node_size.js).
    }
    // Dimmed while the prompts in the fields are not the ones the preview came from.
    function markStale() {
      const last = node.properties?.dice_forge_prompts;
      const stale = !!last && last.source_positive != null && (last.source_positive !== text("positive") || last.source_negative !== text("negative"));
      panel.classList.toggle("stale", stale);
      const note = panel.querySelector(".changed");
      if (note) note.textContent = stale ? "prompt changed since" : "";
    }
    const onExecuted = node.onExecuted;
    node.onExecuted = function (output) {
      const result = output?.dice_forge_prompts?.[0];
      if (result) {
        node.properties ??= {};
        node.properties.dice_forge_prompts = { ...result, source_positive: text("positive"), source_negative: text("negative") };
        node.properties.dice_forge_history = addToHistory(node.properties.dice_forge_history, { ...node.properties.dice_forge_prompts, time: Date.now() });
        render();
      }
      return onExecuted?.apply(this, arguments);
    };
    const onConfigure = node.onConfigure;
    node.onConfigure = function () {
      const result = onConfigure?.apply(this, arguments);
      requestAnimationFrame(render); // A loaded workflow: the prompts of its last run.
      return result;
    };
    // Drawn again when the saved prompts arrive (a loaded workflow gives the node its properties after this extension ran, in the classic canvas),
    // else only the "changed since" mark is checked.
    const timer = setInterval(() => {
      if (node.properties?.dice_forge_prompts !== shownFrom || node.properties?.dice_forge_history !== shownHistory) render();
      else markStale();
    }, 400);
    const onRemoved = node.onRemoved;
    node.onRemoved = function () {
      clearInterval(timer);
      return onRemoved?.apply(this, arguments);
    };
    render();
  },
});
