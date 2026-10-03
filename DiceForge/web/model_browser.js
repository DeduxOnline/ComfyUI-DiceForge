import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { openModelInfo } from "./model_info.js";
import { insertIntoNode } from "./wildcards.js";
import { openCivitaiSearch } from "./civitai.js";
import { dragSource, dropTarget, pickFolder } from "./move_dialog.js";
import { addStyleOnce, background, element } from "./dom.js";

// Model browsers (node menu): LoRA, Checkpoint and Diffusion Model Browser. The model files as cards with a preview, name, base model and trigger words from Civitai
// (looked up by the file's hash, as in Model info), a folder tree, search and filters. What a card's button does depends on the node it was opened
// from: "Use" puts the file in a loader's list, "Use folder" puts a folder in Random LoRA / Random Checkpoint, "+ Triggers" inserts a LoRA's trigger
// words into CLIP Dual Text Encode's prompt. The browsers also manage the files (manage: true): ＋ Find on Civitai downloads new ones (civitai.js),
// ✎ renames one, ⇄ moves one to another folder (or drag its card onto a folder in the tree) and 🗑 deletes one, with its preview and Model info.
// ☆ on a card makes it a favorite (kept in its Model info, so it goes with the file); ★ Favorites in the tree shows only those.
const CLIP_NODE = "CLIPTextEncodePositiveNegative";
const BROWSERS = [
  { kind: "loras", icon: "🎴", title: "LoRA", one: "LoRA", plural: "LoRAs", widget: /lora/i, random: "DiceForgeRandomLora", randomName: "Random LoRA", triggers: true, manage: true },
  { kind: "checkpoints", icon: "🗃️", title: "Checkpoint", one: "checkpoint", plural: "checkpoints", widget: /ckpt|checkpoint/i, random: "DiceForgeRandomCheckpoint", randomName: "Random Checkpoint", triggers: false, manage: true },
  { kind: "diffusion_models", icon: "🧊", title: "Diffusion Model", one: "diffusion model", plural: "diffusion models", widget: /unet|diffusion/i, random: "DiceForgeRandomDiffusionModel",
    randomName: "Random Diffusion Model", triggers: false, manage: true,
    civitaiHint: "Civitai lists diffusion models as Checkpoints: pick a version whose file is the diffusion model alone (often marked fp8, unet or \"model only\"); a full checkpoint belongs in the Checkpoint Browser." },
];

// What a browser can do for a node: set a model list widget, set a folder widget, or insert trigger words. null when the node has none of them.
function targetOf(node, spec) {
  if (node.comfyClass === CLIP_NODE) return spec.triggers ? { triggers: true } : null;
  const combo = (widget) => Array.isArray(widget.options?.values);
  if (node.comfyClass === spec.random) {
    const folder = node.widgets?.find((widget) => widget.name === "folder" && combo(widget));
    return folder ? { folder } : null;
  }
  const model = node.widgets?.find((widget) => spec.widget.test(widget.name) && combo(widget) && widget.options.values.some((value) => /\.(safetensors|ckpt|pt|pth|bin|gguf|sft)$/i.test(value)));
  return model ? { model } : null;
}
// Base model families of Civitai's names: LoRAs of another family do not work on the model; within a family (SDXL, Pony, Illustrious, NoobAI) a LoRA
// often works on another base's model, but not as well. Unknown bases compare as nothing.
function family(base) {
  const name = base.toLowerCase();
  const families = [[/pony|illustrious|noob|sdxl|playground/, "SDXL"], [/^sd ?1/, "SD 1"], [/^sd ?2/, "SD 2"], [/^sd ?3\.5/, "SD 3.5"], [/^sd ?3/, "SD 3"],
    [/^flux\.?1|^flux 1/, "Flux.1"], [/^flux\.?2/, "Flux.2"], [/hunyuan video/, "Hunyuan Video"], [/^wan/, "Wan"]];
  return families.find(([pattern]) => pattern.test(name))?.[1] ?? name;
}
function compareBases(lora, model) {
  if (!lora || !model || lora.toLowerCase() === model.toLowerCase()) return null;
  if (family(lora) === family(model)) return { level: "warn", text: `Made for ${lora}, the model is ${model}: it may work, but not as well.` };
  return { level: "bad", text: `Made for ${lora}, the model is ${model}: a LoRA for another model family does not work on it.` };
}
function setWidget(node, widget, value) {
  widget.value = value;
  widget.callback?.(value, app.canvas, node);
  node.setDirtyCanvas?.(true, true);
  app.graph?.setDirtyCanvas?.(true, true);
}

const STYLE = `
.dflb-back{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:10000;display:flex;align-items:center;justify-content:center}
.dflb{background:#353535;color:#ddd;border:1px solid #555;border-radius:10px;width:min(1400px,96vw);height:min(900px,92vh);display:flex;flex-direction:column;padding:14px 16px;font:14px system-ui,sans-serif;box-shadow:0 10px 40px #000a;box-sizing:border-box}
.dflb h2{margin:0 0 10px;font-size:20px;color:#fff}.dflb .top{display:flex;gap:8px;margin-bottom:10px;align-items:center;flex-wrap:wrap}
.dflb input,.dflb select{background:#262626;color:#eee;border:1px solid #555;border-radius:4px;padding:6px 8px;font:inherit}.dflb .top input{flex:1;min-width:160px}
.dflb button{background:#222;color:#eee;border:1px solid #666;border-radius:6px;padding:5px 12px;cursor:pointer;font:inherit}.dflb button:hover{background:#2c2c2c}
.dflb button:disabled{opacity:.5;cursor:default}.dflb button.go{border-color:#4a7a4a;color:#bfe8bf}
.dflb .main{display:flex;gap:12px;flex:1;min-height:0}.dflb .tree{width:230px;flex:none;overflow:auto;border:1px solid #4a4a4a;border-radius:6px;padding:6px}
.dflb .tree .row{display:flex;align-items:center;gap:6px;padding:3px 6px;border-radius:4px;cursor:pointer}.dflb .tree .row:hover{background:#2c2c2c}
.dflb .tree .row.sel{background:#2f3f55}.dflb .tree .twist{width:14px;flex:none;color:#999;text-align:center}.dflb .tree .twist:hover{color:#fff}
.dflb .tree .tools{display:flex;gap:6px;margin-bottom:6px}.dflb .tree .tools button{flex:1}.dflb .tree .row.drop{background:#35584a;outline:1px dashed #8fd0a8}
.dflb .pic .fav{position:absolute;right:6px;top:6px;background:#000a;border:none;border-radius:5px;color:#ddd;font-size:18px;line-height:1;padding:3px 6px}
.dflb .pic .fav.on{color:#ffd24a}.dflb .pic .fav:hover{background:#000d}.dflb .tree .row.favs .name{color:#ffd24a}.dflb .tree .row .name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.dflb .tree button{padding:0 6px;font-size:12px}
.dflb .grid{flex:1;overflow:auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;align-content:start;grid-auto-rows:max-content}
.dflb .card{background:#2a2a2a;border:1px solid #474747;border-radius:8px;overflow:hidden;display:flex;flex-direction:column}.dflb .card.sel{border-color:#6a9ad8}
.dflb .pic{aspect-ratio:3/4;background:#1e1e1e;display:flex;align-items:center;justify-content:center;overflow:hidden;position:relative}
.dflb .pic img,.dflb .pic video{width:100%;height:100%;object-fit:cover;display:block}.dflb .pic .none{font-size:40px;opacity:.35}
.dflb .blur{filter:blur(22px);cursor:pointer}.dflb .base{position:absolute;left:6px;top:6px;background:#35584acc;color:#c8f0dc;border-radius:4px;padding:1px 6px;font-size:12px;font-weight:600}
.dflb .body{padding:7px 8px;display:flex;flex-direction:column;gap:5px;flex:1}.dflb .title{font-weight:600;color:#fff;word-break:break-word}
.dflb .muted{color:#999;font-size:12px;word-break:break-all}.dflb .words span{display:inline-block;background:#262626;border:1px solid #555;border-radius:4px;padding:0 5px;margin:0 3px 3px 0;font-size:12px;cursor:copy}
.dflb .buttons{display:flex;gap:5px;flex-wrap:wrap;margin-top:auto}.dflb .buttons button{padding:3px 8px;font-size:12px}.dflb .status{color:#9c9;font-size:13px;min-height:18px}
`;
const addStyle = () => addStyleOnce("dflb-style", STYLE);
const pathParts = (file) => file.split(/[\\/]/);
const folderOf = (file) => pathParts(file).slice(0, -1).join("/");
const shortName = (file) => pathParts(file).pop().replace(/\.[^.]+$/, "");

async function fetchList(kind) {
  const response = await api.fetchApi(`/diceforge/model-browser?kind=${kind}`);
  if (!response.ok) throw new Error(await response.text());
  return (await response.json()).files;
}
// Hash + Civitai lookup of one file (the Model info route), then its card data again from the list.
async function lookUp(kind, file) {
  const response = await api.fetchApi(`/diceforge/model-info?kind=${kind}&file=${encodeURIComponent(file)}`);
  if (!response.ok) throw new Error(await response.text());
  return (await fetchList(kind)).find((entry) => entry.file === file);
}

// target: what the buttons do (targetOf for a node's menu), or { pick(file), label, hint, base } from another extension (LoRA Stack): pick returns
// true to close the browser, or a message to show; base (the connected model's base model) starts the list on the files that fit it.
async function openBrowser(node, spec, target = targetOf(node, spec)) {
  addStyle();
  const { kind } = spec;
  const what = spec.one;
  let files = [], folder = "", selectedFile = target?.model?.value, stopLookUp = null;
  const search = element("input", { placeholder: "Search by file, name or trigger word…" });
  const base = element("select", {}, element("option", { value: "" }, "All base models"));
  const FITS = "\u0001fits";
  const FAVORITES = "\u0002favorites"; // The ★ Favorites row of the tree, as the picked "folder".
  const sort = element("select", {}, ...[["name", "Name"], ["new", "Newest first"], ["base", "Base model"]].map(([value, label]) => element("option", { value }, label)));
  const status = element("div", { class: "status" });
  const tree = element("div", { class: "tree" });
  const grid = element("div", { class: "grid" });
  const lookAll = element("button", { title: `Compute the hash of every ${what} not looked up yet and ask Civitai about it, one by one` }, "Look up all on Civitai");
  const back = element("div", { class: "dflb-back" });
  const onKey = (event) => { if (event.key === "Escape" && !document.querySelector(".dfmi-back, .dfcv-back, .dfmv-back")) { event.stopPropagation(); close(); } };
  function close() {
    stopLookUp?.();
    back.remove();
    document.removeEventListener("keydown", onKey, true);
  }
  back.addEventListener("mousedown", (event) => { if (event.target === back) close(); });
  document.addEventListener("keydown", onKey, true);
  const say = (text) => { status.textContent = text; };

  function replaceEntry(entry) {
    if (!entry) return;
    files = files.map((file) => (file.file === entry.file ? entry : file));
  }
  function action(entry) {
    if (target?.model) {
      const use = element("button", { class: "go", onclick: () => {
        setWidget(node, target.model, entry.file);
        selectedFile = entry.file;
        say(`${shortName(entry.file)} is now in ${target.model.name}.`);
        draw();
      } }, entry.file === target.model.value ? "In use" : "Use");
      use.disabled = entry.file === target.model.value;
      return [use];
    }
    if (target?.pick) {
      return [element("button", { class: "go", onclick: () => {
        const result = target.pick(entry.file);
        if (result === true) close();
        else if (typeof result === "string") say(result);
      } }, target.label)];
    }
    if (target?.triggers) {
      return [element("button", { class: "go", title: entry.trigger_words.length ? entry.trigger_words.join(", ") : "No trigger words known: look it up on Civitai or add your own in Info", onclick: () => {
        if (!entry.trigger_words.length) return say(`${shortName(entry.file)}: no trigger words known. Look it up on Civitai, or add your own in 🛈 Info.`);
        const field = insertIntoNode(node, entry.trigger_words.join(", "));
        say(`Added the trigger words of ${shortName(entry.file)} to ${field}.`);
      } }, "+ Triggers")];
    }
    return [];
  }
  function picture(entry) {
    const box = element("div", { class: "pic" });
    const url = entry.preview ? api.apiURL(`/diceforge/model-preview?kind=${kind}&file=${encodeURIComponent(entry.file)}&t=${entry.mtime}`) : entry.image?.url;
    if (!url) box.append(element("span", { class: "none" }, spec.icon));
    else {
      const media = !entry.preview && entry.image?.type === "video"
        ? element("video", { src: url, muted: "", loop: "", autoplay: "", playsinline: "" })
        : element("img", { src: url, loading: "lazy" });
      if (!entry.preview && (entry.image?.nsfwLevel ?? 1) >= 4) { // Civitai's R and up: blurred until clicked, as in Model info.
        media.classList.add("blur");
        media.addEventListener("click", () => media.classList.remove("blur"));
      }
      media.addEventListener("error", () => media.replaceWith(element("span", { class: "none", title: "The preview could not be loaded" }, spec.icon)));
      box.append(media);
    }
    if (entry.base_model) {
      const fit = target?.base ? compareBases(entry.base_model, target.base) : null;
      box.append(element("span", { class: "base", title: fit?.text ?? "" }, `${fit ? (fit.level === "bad" ? "⛔ " : "⚠️ ") : ""}${entry.base_model}`));
    }
    box.append(element("button", { class: "fav" + (entry.favorite ? " on" : ""), title: entry.favorite ? "A favorite: click to remove the star" : "Add to favorites",
      onclick: (event) => { event.stopPropagation(); background(setFavorite(entry, !entry.favorite)); } }, entry.favorite ? "★" : "☆"));
    return box;
  }
  function card(entry) {
    const words = element("div", { class: "words" }, ...entry.trigger_words.slice(0, 8).map((word) =>
      element("span", { title: "Click to copy", onclick: () => { background(navigator.clipboard?.writeText(word)); say(`Copied "${word}".`); } }, word)));
    const lookUpButton = element("button", { onclick: async () => {
      lookUpButton.disabled = true;
      lookUpButton.textContent = "Looking up…";
      try {
        replaceEntry(await lookUp(kind, entry.file));
        draw();
      } catch (error) {
        say(`${shortName(entry.file)}: ${error.message}`);
        lookUpButton.textContent = "Look up failed";
      }
    } }, entry.checked ? "↻ Civitai" : "🔍 Civitai");
    const info = element("button", { onclick: () => {
      background(openModelInfo(kind, entry.file));
      const watch = setInterval(async () => { // When the Info dialog closes, the card shows what it looked up or what you typed there.
        if (document.querySelector(".dfmi-back")) return;
        clearInterval(watch);
        if (!back.isConnected) return;
        replaceEntry((await fetchList(kind)).find((item) => item.file === entry.file));
        draw();
      }, 300);
    } }, "🛈 Info");
    const link = entry.url ? [element("button", { onclick: () => window.open(entry.url, "_blank", "noopener") }, "Civitai ↗")] : [];
    const manage = spec.manage ? [
      element("button", { class: "rename", title: `Rename this ${what} (with its preview and info); a / puts it in a folder`, onclick: () => background(renameFile(entry)) }, "✎"),
      element("button", { class: "move", title: `Move this ${what} to another folder (or drag the card onto a folder in the tree)`, onclick: () => background(moveFile(entry)) }, "⇄"),
      element("button", { class: "delete", title: `Delete this ${what} file, its preview and info`, onclick: () => background(deleteFile(entry)) }, "🗑")] : [];
    const note = !entry.checked ? "Not looked up yet" : entry.found ? "" : "Not on Civitai";
    const box = element("div", { class: "card" + (entry.file === selectedFile ? " sel" : "") },
      picture(entry),
      element("div", { class: "body" },
        element("div", { class: "title" }, entry.name || shortName(entry.file)),
        element("div", { class: "muted" }, entry.file, ` · ${(entry.size / 1024 ** 2).toFixed(0)} MB`, note ? ` · ${note}` : ""),
        words,
        ...(entry.settings ? [element("div", { class: "muted", title: "Your recommended settings, from Model info" }, `⚙ ${entry.settings}`)] : []),
        element("div", { class: "buttons" }, ...action(entry), info, lookUpButton, ...link, ...manage)));
    if (spec.manage) dragSource(box, kind, entry.file);
    return box;
  }
  // Update and Delete: the server moves or removes the file with its companions; the loader lists are refreshed, and a loader of this browser that
  // used the file follows it to its new name.
  async function reload() {
    files = await fetchList(kind);
    draw();
    background(app.refreshComboInNodes?.());
  }
  async function renameTo(file, to, moved) {
    const response = await api.fetchApi("/diceforge/models/rename", { method: "POST", body: JSON.stringify({ kind, file, to }) });
    if (!response.ok) return say(await response.text());
    const result = await response.json();
    if (result.to === file) return;
    if (target?.model?.value === file) setWidget(node, target.model, result.to);
    if (selectedFile === file) selectedFile = result.to;
    await reload();
    say(`${moved ? "Moved" : "Renamed"} ${file} to ${result.to}. Workflows that use the old name need the new one.`);
  }
  async function renameFile(entry) {
    const to = prompt(`New name for ${entry.file} (the extension stays; folders with /):`, entry.file.replace(/\.[^./\\]+$/, ""))?.trim();
    if (to) await renameTo(entry.file, to, false);
  }
  // Move: the same file name in another folder ("" for the top folder), picked in the folder picker or by dropping the card on the tree.
  async function moveFile(entry, to) {
    const from = folderOf(entry.file);
    const folders = [...new Set(files.flatMap((item) => { const parts = pathParts(item.file).slice(0, -1); return parts.map((_, index) => parts.slice(0, index + 1).join("/")); }))]
      .sort((a, b) => a.localeCompare(b));
    const destination = to ?? await pickFolder({ title: `Move ${pathParts(entry.file).pop()} to…`, folders, current: from });
    if (destination == null || destination === from) return;
    await renameTo(entry.file, `${destination ? `${destination}/` : ""}${pathParts(entry.file).pop()}`, true);
  }
  async function deleteFile(entry) {
    if (!confirm(`Delete ${entry.file}, its preview and its info? This can't be undone.`)) return;
    const response = await api.fetchApi(`/diceforge/models/file?kind=${kind}&file=${encodeURIComponent(entry.file)}`, { method: "DELETE" });
    if (!response.ok) return say(await response.text());
    await reload();
    say(`Deleted ${entry.file}.`);
  }
  async function setFavorite(entry, favorite) {
    const response = await api.fetchApi("/diceforge/model-favorite", { method: "POST", body: JSON.stringify({ kind, file: entry.file, favorite }) });
    if (!response.ok) return say(await response.text());
    files = files.map((item) => (item.file === entry.file ? { ...item, favorite } : item));
    say(favorite ? `${shortName(entry.file)} is a favorite.` : `${shortName(entry.file)} is no longer a favorite.`);
    draw();
  }
  function matches(entry) {
    const query = search.value.trim().toLowerCase();
    const text = [entry.file, entry.name, entry.base_model, ...entry.trigger_words].join(" ").toLowerCase();
    const inFolder = folder === FAVORITES ? entry.favorite : !folder || folderOf(entry.file) === folder || folderOf(entry.file).startsWith(folder + "/");
    const baseOk = !base.value || (base.value === FITS ? compareBases(entry.base_model, target.base)?.level !== "bad" : entry.base_model === base.value);
    return inFolder && baseOk && (!query || query.split(/\s+/).every((word) => text.includes(word)));
  }
  // Folders open in the tree, kept per kind between openings (and reloads) in this browser. Subfolders start closed; ▸ opens one, and the folder
  // picked in the tree (or the one a Random loader uses) is opened to.
  const openKey = `diceforge.browser.${kind}.open`;
  const opened = (() => { try { return new Set(JSON.parse(localStorage.getItem(openKey)) || []); } catch { return new Set(); } })();
  const keepOpened = () => { try { localStorage.setItem(openKey, JSON.stringify([...opened])); } catch { /* No storage: open only for this visit. */ } };
  const openTo = (path) => {
    const parts = path ? path.split("/") : [];
    parts.slice(0, -1).forEach((_, index) => opened.add(parts.slice(0, index + 1).join("/")));
  };
  function drawTree() {
    const counts = new Map([["", files.length]]);
    for (const entry of files) {
      const parts = pathParts(entry.file).slice(0, -1);
      parts.forEach((_, index) => { const path = parts.slice(0, index + 1).join("/"); counts.set(path, (counts.get(path) ?? 0) + 1); });
    }
    const folders = [...counts.keys()].sort((a, b) => a.localeCompare(b));
    const parents = new Set(folders.map((path) => path.split("/").slice(0, -1).join("/")).filter(Boolean));
    openTo(folder);
    if (typeof target?.folder?.value === "string") openTo(target.folder.value); // The folder the Random loader uses shows.
    const shown = folders.filter((path) => { // Every folder above it open.
      const parts = path.split("/");
      return parts.slice(0, -1).every((_, index) => opened.has(parts.slice(0, index + 1).join("/")));
    });
    const toggle = (path) => { if (opened.has(path)) opened.delete(path); else opened.add(path); keepOpened(); drawTree(); };
    const tools = parents.size ? [element("div", { class: "tools" },
      element("button", { class: "open-all", title: "Open every folder", onclick: () => { parents.forEach((path) => opened.add(path)); keepOpened(); drawTree(); } }, "Expand all"),
      element("button", { class: "close-all", title: "Close every folder", onclick: () => { opened.clear(); keepOpened(); drawTree(); } }, "Collapse all"))] : [];
    const favorites = files.filter((entry) => entry.favorite).length;
    const favoritesRow = element("div", { class: "row favs" + (folder === FAVORITES ? " sel" : ""), "data-path": FAVORITES, style: "padding-left:6px",
      title: "Your favorites (☆ on a card)", onclick: () => { folder = FAVORITES; draw(); } },
      element("span", { class: "name" }, "★ Favorites"), element("span", { class: "muted" }, favorites));
    tree.replaceChildren(...tools, ...shown.flatMap((path) => (path === "" ? [path, FAVORITES] : [path])).map((path) => path === FAVORITES ? favoritesRow : (() => {
      const depth = path ? path.split("/").length : 0;
      const twist = parents.has(path)
        ? element("span", { class: "twist", title: opened.has(path) ? "Close the folder" : "Open the folder", onclick: (event) => { event.stopPropagation(); toggle(path); } }, opened.has(path) ? "▾" : "▸")
        : element("span", { class: "twist" });
      const useFolder = target?.folder && path && target.folder.options.values.includes(path)
        ? [element("button", { title: `Pick the ${spec.plural} of ${path} in ${spec.randomName}`, onclick: (event) => {
            event.stopPropagation();
            setWidget(node, target.folder, path);
            say(`${spec.randomName} now picks from ${path}.`);
            drawTree();
          } }, target.folder.value === path ? "In use" : "Use folder")]
        : [];
      const row = element("div", { class: "row" + (path === folder ? " sel" : ""), "data-path": path, style: `padding-left:${6 + depth * 12}px`, onclick: () => { folder = path; draw(); } },
        ...(path ? [twist] : []), element("span", { class: "name" }, path ? `📁 ${path.split("/").pop()}` : `All ${spec.plural}`), element("span", { class: "muted" }, counts.get(path)), ...useFolder);
      if (spec.manage) { // A card dropped on a folder moves there; on "All", to the top folder.
        dropTarget(row, kind, (file) => {
          const entry = files.find((item) => item.file === file);
          if (entry) background(moveFile(entry, path));
        });
        row.title = `Drop a card here to move it to ${path || "the top folder"}`;
      }
      return row;
    })()));
  }
  function draw() {
    const bases = [...new Set(files.map((entry) => entry.base_model).filter(Boolean))].sort((a, b) => a.localeCompare(b, undefined, { numeric: true })); // SD 1.5 before SDXL 1.0, Flux.1 D before Flux.1 S.
    const chosen = base.value;
    base.replaceChildren(element("option", { value: "" }, "All base models"),
      ...(target?.base ? [element("option", { value: FITS, title: "The same base, the same family (⚠) and the ones not looked up yet" }, `Fits the model (${target.base})`)] : []),
      ...bases.map((name) => element("option", { value: name }, name)));
    base.value = chosen === FITS || bases.includes(chosen) ? chosen : "";
    const order = {
      name: (a, b) => (a.name || shortName(a.file)).localeCompare(b.name || shortName(b.file)),
      new: (a, b) => b.mtime - a.mtime,
      base: (a, b) => (a.base_model || "~").localeCompare(b.base_model || "~") || shortName(a.file).localeCompare(shortName(b.file)),
    }[sort.value];
    const shown = files.filter(matches).sort(order);
    grid.replaceChildren(...(shown.length ? shown.map(card) : [element("div", { class: "muted" }, files.length ? `No ${what} matches.` : `No ${what} files: put them in ComfyUI/models/${kind}.`)]));
    const missing = files.filter((entry) => !entry.checked).length;
    lookAll.textContent = missing ? `Look up all on Civitai (${missing})` : "All looked up";
    lookAll.disabled = !missing && !stopLookUp;
    drawTree();
  }
  lookAll.addEventListener("click", async () => {
    if (stopLookUp) return stopLookUp();
    let stopped = false;
    stopLookUp = () => { stopped = true; };
    lookAll.textContent = "Stop";
    const queue = files.filter((entry) => !entry.checked).map((entry) => entry.file);
    for (const [index, file] of queue.entries()) {
      if (stopped) break;
      say(`Looking up ${index + 1} of ${queue.length}: ${shortName(file)} (hashing a large file takes a few seconds)…`);
      try { replaceEntry(await lookUp(kind, file)); } catch (error) { say(`${shortName(file)}: ${error.message}`); }
      if (back.isConnected) draw(), (lookAll.textContent = "Stop");
    }
    stopLookUp = null;
    if (back.isConnected) {
      say(stopped ? "Stopped." : "Done.");
      draw();
    }
  });
  for (const input of [search, base, sort]) input.addEventListener(input === search ? "input" : "change", draw);
  const hint = target?.pick ? target.hint : target?.model ? `Use puts a ${what} in ${target.model.name}.` : target?.folder ? `Use folder sets the folder ${spec.randomName} picks from.` : target?.triggers ? `+ Triggers inserts a ${what}'s trigger words where the cursor was in the prompt.` : "";
  back.append(element("div", { class: "dflb" },
    element("h2", {}, `${spec.title} Browser`),
    element("div", { class: "top" }, search, base, sort, lookAll,
      ...(spec.manage ? [element("button", { class: "go find", title: `Search Civitai and download ${spec.plural} into models/${kind}`, onclick: () => background(openCivitaiSearch({
        kind, title: spec.title, plural: spec.plural, icon: spec.icon, hint: spec.civitaiHint ?? "", base: target?.base, folders: [...new Set(files.map((entry) => folderOf(entry.file)).filter(Boolean))].sort((a, b) => a.localeCompare(b)),
        onChange: () => background(reload().then(() => say("The download is done: it is in the list."))),
      })) }, "＋ Find on Civitai")] : []),
      element("button", { onclick: close }, "Close")),
    element("div", { class: "top" }, element("span", { class: "muted" }, hint), status),
    element("div", { class: "main" }, tree, grid)));
  document.body.append(back);
  say("Loading…");
  try {
    files = await fetchList(kind);
    say("");
  } catch (error) {
    say(`Could not list the ${spec.plural}: ${error.message}`);
  }
  draw();
  if (target?.base) { // Starts on the files that fit the model; All base models shows every one.
    base.value = FITS;
    draw();
  }
  search.focus();
  grid.querySelector(".card.sel")?.scrollIntoView({ block: "center" });
}

app.registerExtension({
  name: "DiceForge.ModelBrowser",
  getNodeMenuItems(node) {
    return BROWSERS.filter((spec) => targetOf(node, spec)).map((spec) => ({ content: `${spec.icon} ${spec.title} Browser`, callback: () => openBrowser(node, spec) }));
  },
});

export { openBrowser as openModelBrowser, BROWSERS, family, compareBases };
