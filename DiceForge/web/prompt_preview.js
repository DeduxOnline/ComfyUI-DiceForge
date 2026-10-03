import { app } from "../../scripts/app.js";
import { addStyleOnce, element } from "./dom.js";

// CLIP Dual Text Encode shows, under its inputs, the positive and negative prompts as the last run encoded them: choices, wildcards and variables
// filled in, with the seed and mode they came from. Click a prompt to copy it. They are kept in the node's properties, so they are still there after
// a reload and travel with the workflow (also the one saved in an image). When a prompt was changed since, the preview is dimmed until the next run.
const NODE_TYPE = "CLIPTextEncodePositiveNegative";
const STYLE = `
.dfpp{font:12px system-ui,sans-serif;color:#ccc;display:flex;flex-direction:column;gap:4px;box-sizing:border-box;padding:2px 0;max-height:320px;overflow:auto}
.dfpp .head{color:#888;display:flex;gap:6px;justify-content:space-between}.dfpp .head .changed{color:#d9b36a}
.dfpp .box{background:#222;border:1px solid #444;border-radius:5px;padding:4px 6px;white-space:pre-wrap;word-break:break-word;cursor:copy;max-height:130px;overflow:auto}
.dfpp .box b{color:#888;font-weight:400;margin-right:6px}.dfpp .box.copied{border-color:#6a9a6a}.dfpp .empty{color:#777;font-style:italic}
.dfpp.stale .box{opacity:.55}
`;

app.registerExtension({
  name: "DiceForge.PromptPreview",
  nodeCreated(node) {
    if (node.comfyClass !== NODE_TYPE) return;
    addStyleOnce("dfpp-style", STYLE);
    const panel = element("div", { class: "dfpp" });
    node.addDOMWidget("prompt_preview", "diceforge_prompt_preview", panel, { serialize: false, getMinHeight: () => Math.min(panel.scrollHeight, 320) + 4 });
    const text = (name) => String(node.widgets?.find((widget) => widget.name === name)?.value ?? "");
    const box = (label, value) => {
      const item = element("div", { class: "box", title: "Click to copy" }, element("b", {}, label), value ? value : element("span", { class: "empty" }, "(empty)"));
      item.addEventListener("click", () => {
        navigator.clipboard?.writeText(value);
        item.classList.add("copied");
        setTimeout(() => item.classList.remove("copied"), 600);
      });
      return item;
    };
    let shownFrom; // The prompts the panel shows (undefined: not drawn yet).
    function render() {
      const last = node.properties?.dice_forge_prompts;
      shownFrom = last;
      if (!last) panel.replaceChildren(element("div", { class: "empty" }, "Run the workflow to see the prompts as encoded here."));
      else {
        const mode = [last.seed_mode, last.note].filter(Boolean).join(", ");
        panel.replaceChildren(element("div", { class: "head" }, element("span", {}, `Last run · seed ${last.seed}${mode ? ` (${mode})` : ""}`), element("span", { class: "changed" })),
          box("positive", last.positive ?? ""), box("negative", last.negative ?? ""));
      }
      markStale();
      node.setSize?.([node.size[0], Math.max(node.size[1], node.computeSize()[1])]); // Room for the preview in the classic canvas.
      node.setDirtyCanvas?.(true, true);
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
    const timer = setInterval(() => { if (node.properties?.dice_forge_prompts !== shownFrom) render(); else markStale(); }, 400);
    const onRemoved = node.onRemoved;
    node.onRemoved = function () {
      clearInterval(timer);
      return onRemoved?.apply(this, arguments);
    };
    render();
  },
});
