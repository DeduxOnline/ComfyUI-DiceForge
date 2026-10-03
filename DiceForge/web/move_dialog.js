import { addStyleOnce, element } from "./dom.js";

// The folder picker of "⇄ Move" in the model browsers and the Wildcard Browser: the existing folders (the current one marked), the top folder, and a
// field for a new folder (made by the move, a / for subfolders). Resolves with the folder ("" for the top folder), or null when cancelled.
const STYLE = `
.dfmv-back{position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:10003;display:flex;align-items:center;justify-content:center}
.dfmv{background:#353535;color:#ddd;border:1px solid #555;border-radius:10px;width:min(460px,92vw);max-height:80vh;display:flex;flex-direction:column;gap:8px;padding:14px 16px;font:14px system-ui,sans-serif;box-shadow:0 10px 40px #000a;box-sizing:border-box}
.dfmv h3{margin:0;font-size:16px;color:#fff;word-break:break-all}.dfmv .list{overflow:auto;border:1px solid #4a4a4a;border-radius:6px;padding:4px;min-height:80px}
.dfmv .item{padding:4px 8px;border-radius:4px;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.dfmv .item:hover{background:#2f3f55}
.dfmv .item.here{color:#888;cursor:default}.dfmv .item.here:hover{background:none}
.dfmv input{background:#262626;color:#eee;border:1px solid #555;border-radius:4px;padding:6px 8px;font:inherit}.dfmv .row{display:flex;gap:8px}.dfmv .row input{flex:1}
.dfmv button{background:#222;color:#eee;border:1px solid #666;border-radius:6px;padding:5px 12px;cursor:pointer;font:inherit}.dfmv button:hover{background:#2c2c2c}
`;
const TOP = "(top folder)";

export function pickFolder({ title, folders, current = "" }) {
  addStyleOnce("dfmv-style", STYLE);
  return new Promise((resolve) => {
    const back = element("div", { class: "dfmv-back" });
    const done = (value) => {
      back.remove();
      document.removeEventListener("keydown", onKey, true);
      resolve(value);
    };
    const onKey = (event) => {
      if (event.key !== "Escape") return;
      event.stopPropagation(); // Only the picker closes, not the browser under it.
      done(null);
    };
    const item = (folder) => {
      const here = folder === current;
      return element("div", { class: "item" + (here ? " here" : ""), "data-folder": folder, title: here ? "It is already here" : `Move to ${folder || TOP}`,
        onclick: () => { if (!here) done(folder); } }, `📁 ${folder || TOP}${here ? " (here)" : ""}`);
    };
    const field = element("input", { placeholder: "New folder, for example styles/anime" });
    const go = () => {
      const folder = field.value.trim().replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
      if (folder && folder !== current) done(folder);
    };
    field.addEventListener("keydown", (event) => { if (event.key === "Enter") go(); });
    back.addEventListener("mousedown", (event) => { if (event.target === back) done(null); });
    document.addEventListener("keydown", onKey, true);
    back.append(element("div", { class: "dfmv" },
      element("h3", {}, title),
      element("div", { class: "list" }, ...["", ...folders.filter(Boolean)].map(item)),
      element("div", { class: "row" }, field, element("button", { class: "go", onclick: go }, "Move")),
      element("div", { class: "row" }, element("span", { style: "flex:1" }), element("button", { onclick: () => done(null) }, "Cancel"))));
    document.body.append(back);
    field.focus();
  });
}

// Drag and drop between a browser's items and its folder tree: what is dragged (its kind and name), and whether a drop target accepts it.
export const DRAG_TYPE = "application/x-diceforge-move";
export function dragged(event) {
  try { return JSON.parse(event.dataTransfer.getData(DRAG_TYPE)); } catch { return null; }
}
// Makes target a drop place for items of kind: highlighted while one is over it, onDrop(name) when it is dropped.
export function dropTarget(target, kind, onDrop) {
  const accepts = (event) => event.dataTransfer?.types?.includes(DRAG_TYPE);
  target.addEventListener("dragover", (event) => {
    if (!accepts(event)) return;
    event.preventDefault();
    event.stopPropagation(); // The innermost folder takes it, not the tree around it.
    event.dataTransfer.dropEffect = "move";
    target.classList.add("drop");
  });
  target.addEventListener("dragleave", () => target.classList.remove("drop"));
  target.addEventListener("drop", (event) => {
    target.classList.remove("drop");
    const item = dragged(event);
    if (!item || item.kind !== kind) return;
    event.preventDefault();
    event.stopPropagation();
    onDrop(item.name);
  });
}
export function dragSource(source, kind, name) {
  source.setAttribute("draggable", "true");
  source.addEventListener("dragstart", (event) => {
    event.dataTransfer.setData(DRAG_TYPE, JSON.stringify({ kind, name }));
    event.dataTransfer.effectAllowed = "move";
  });
}
