import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addStyleOnce, background, element } from "./dom.js";
import { fitNodeHeight } from "./node_size.js";

// Random Image shows, under its inputs, the image the last run picked: the picture, its file and folder, its size (and frames of an animated one) and
// the seed and mode it came from. Click the picture to open it full size, the file name to copy it. Kept in the node's properties, so it is still
// there after a reload and travels with the workflow; a file of the input folder is shown from there, one from another folder (path) through a
// temporary copy, which ComfyUI clears on restart: then the preview says so until the next run.
const NODE_TYPE = "DiceForgeRandomImage";
const STYLE = `
.dfip{font:12px system-ui,sans-serif;color:#ccc;display:flex;flex-direction:column;gap:4px;box-sizing:border-box;padding:2px 0}
.dfip .head{color:#888}.dfip .pic{display:flex;justify-content:center;background:#1e1e1e;border-radius:6px;overflow:hidden;min-height:40px}
.dfip .pic img{max-width:100%;max-height:360px;object-fit:contain;display:block;cursor:zoom-in}
.dfip .file{background:#222;border:1px solid #444;border-radius:5px;padding:4px 6px;word-break:break-all;cursor:copy}.dfip .file.copied{border-color:#6a9a6a}
.dfip .size{color:#999}.dfip .empty{color:#777;font-style:italic;padding:6px}
`;
const viewURL = (view, stamp) => api.apiURL(`/view?${new URLSearchParams({ filename: view.filename, subfolder: view.subfolder ?? "", type: view.type ?? "input", t: stamp })}`);

app.registerExtension({
  name: "DiceForge.ImagePreview",
  nodeCreated(node) {
    if (node.comfyClass !== NODE_TYPE) return;
    addStyleOnce("dfip-style", STYLE);
    const panel = element("div", { class: "dfip" });
    node.addDOMWidget("image_preview", "diceforge_image_preview", panel, { serialize: false, getMinHeight: () => panel.scrollHeight + 4 });
    let shownFrom; // The pick the panel shows (undefined: not drawn yet).
    function render() {
      const last = node.properties?.dice_forge_image;
      shownFrom = last;
      if (!last?.view?.filename) {
        panel.replaceChildren(element("div", { class: "empty" }, "Run the workflow to see the picked image here."));
      } else {
        const url = viewURL(last.view, last.stamp ?? 0);
        const picture = element("img", { src: url, alt: last.file, title: "Click to open it full size" });
        picture.addEventListener("click", () => window.open(url, "_blank", "noopener"));
        picture.addEventListener("load", () => fit());
        picture.addEventListener("error", () => picture.replaceWith(element("div", { class: "empty" },
          last.view.type === "temp" ? "The preview was a temporary copy, cleared since: run again to see it." : `${last.file} is no longer there.`)));
        const file = element("div", { class: "file", title: `${last.folder}/${last.file} (click to copy)` }, last.file);
        file.addEventListener("click", () => {
          background(navigator.clipboard?.writeText(last.file)); // A refused copy (no permission) is logged, not thrown.
          file.classList.add("copied");
          setTimeout(() => file.classList.remove("copied"), 600);
        });
        const mode = last.seed_mode ? ` (${last.seed_mode})` : "";
        panel.replaceChildren(element("div", { class: "head" }, `Last run · seed ${last.seed}${mode}`), element("div", { class: "pic" }, picture), file,
          element("div", { class: "size" }, `${last.width} × ${last.height}${last.frames > 1 ? ` · ${last.frames} frames` : ""} · ${last.folder}`));
      }
      fit();
    }
    // Room for the preview: taller in the classic canvas, no gap in Nodes 2.0 (node_size.js).
    const fit = () => fitNodeHeight(node);
    const onExecuted = node.onExecuted;
    node.onExecuted = function (output) {
      const result = output?.dice_forge_image?.[0];
      if (result) {
        node.properties ??= {};
        node.properties.dice_forge_image = { ...result, stamp: Date.now() }; // A new run of the same file shows it again, not a cached copy.
        render();
      }
      return onExecuted?.apply(this, arguments);
    };
    // Drawn again when the saved pick arrives (a loaded workflow gives the node its properties after this extension ran, in the classic canvas).
    const timer = setInterval(() => { if (node.properties?.dice_forge_image !== shownFrom) render(); }, 500);
    const onRemoved = node.onRemoved;
    node.onRemoved = function () {
      clearInterval(timer);
      return onRemoved?.apply(this, arguments);
    };
    render();
  },
});
