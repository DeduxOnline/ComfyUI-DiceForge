import { app } from "../../scripts/app.js";
import { addStyleOnce, background, element } from "./dom.js";
import { fitNodeHeight } from "./node_size.js";

// Danbooru Tag Enhancer shows, under its inputs, the prompt the last run made: Danbooru picks a new post on every run, so the one you like is copied
// from here (click the text). Also the added tags, the post (↗ opens it) and the search that found it. Kept in the node's properties, so it is still
// there after a reload and travels with the workflow.
const NODE_TYPE = "DiceForgeDanbooruEnhancer";
const RATINGS = { g: "general", s: "sensitive", q: "questionable", e: "explicit" };
const STYLE = `
.dfdb{font:12px system-ui,sans-serif;color:#ccc;display:flex;flex-direction:column;gap:4px;box-sizing:border-box;padding:2px 0}
.dfdb .head{color:#888;display:flex;gap:6px;align-items:center}.dfdb .head a{color:#9cc8ff;text-decoration:none;margin-left:auto}
.dfdb .text{background:#222;border:1px solid #444;border-radius:5px;padding:5px 7px;white-space:pre-wrap;word-break:break-word;cursor:copy;max-height:220px;overflow:auto;user-select:text}
.dfdb .text.copied{border-color:#6a9a6a}.dfdb .added{color:#9c9}.dfdb .empty{color:#777;font-style:italic;padding:6px}
`;

app.registerExtension({
  name: "DiceForge.DanbooruPreview",
  nodeCreated(node) {
    if (node.comfyClass !== NODE_TYPE) return;
    addStyleOnce("dfdb-style", STYLE);
    const panel = element("div", { class: "dfdb" });
    node.addDOMWidget("danbooru_preview", "diceforge_danbooru_preview", panel, { serialize: false, getMinHeight: () => panel.scrollHeight + 4 });
    let shownFrom; // The result the panel shows (undefined: not drawn yet).
    function render() {
      const last = node.properties?.dice_forge_danbooru;
      shownFrom = last;
      if (!last?.text) {
        panel.replaceChildren(element("div", { class: "empty" }, "Run the workflow to see the prompt made from a Danbooru post here."));
      } else {
        const text = element("div", { class: "text", title: "Click to copy" }, last.text);
        text.addEventListener("click", () => {
          if (window.getSelection()?.toString()) return; // Selecting a part to copy it yourself.
          background(navigator.clipboard?.writeText(last.text)); // A refused copy (no permission) is logged, not thrown.
          text.classList.add("copied");
          setTimeout(() => text.classList.remove("copied"), 600);
        });
        panel.replaceChildren(
          element("div", { class: "head" }, `Last run · post #${last.id}${RATINGS[last.rating] ? ` (${RATINGS[last.rating]})` : ""}`,
            element("a", { href: last.url, target: "_blank", rel: "noopener", title: `Found with: ${last.search || "any post"}` }, "↗ post")),
          text,
          element("div", { class: "added" }, last.added ? `+ ${last.added}` : "Nothing to add: the post has no other tags."));
      }
      fitNodeHeight(node);
    }
    const onExecuted = node.onExecuted;
    node.onExecuted = function (output) {
      const result = output?.dice_forge_danbooru?.[0];
      if (result) {
        node.properties ??= {};
        node.properties.dice_forge_danbooru = result;
        render();
      }
      return onExecuted?.apply(this, arguments);
    };
    // Drawn again when the saved result arrives (a loaded workflow gives the node its properties after this extension ran, in the classic canvas).
    const timer = setInterval(() => { if (node.properties?.dice_forge_danbooru !== shownFrom) render(); }, 500);
    const onRemoved = node.onRemoved;
    node.onRemoved = function () {
      clearInterval(timer);
      return onRemoved?.apply(this, arguments);
    };
    render();
  },
});
