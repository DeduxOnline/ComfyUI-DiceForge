import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addStyleOnce, asking, element, openLink, safeURL } from "./dom.js";
import { shouldBlur, videoPreview } from "./media.js";
import { dateText, statsChips } from "./civitai_meta.js";
import { applySettings, settingsOf } from "./apply_settings.js";

// "Model info" in the node menu, for every node with a model file picked in a list (Load Checkpoint, Load Diffusion Model, Load LoRA, Load VAE,
// Load CLIP and the DiceForge loaders): a dialog like rgthree's LoRA info, with the file's sha256, what Civitai knows about it, and your own notes.

// Model kind of a widget, by its name, and whether its value looks like a model file.
const KIND_BY_WIDGET = [
  [/ckpt|checkpoint/i, "checkpoints"],
  [/unet|diffusion/i, "diffusion_models"],
  [/lora/i, "loras"],
  [/vae/i, "vae"],
  [/clip|text_encoder/i, "text_encoders"],
];
export const MODEL_FILE = /\.(safetensors|ckpt|pt|pth|bin|gguf|sft)$/i;
function modelWidgets(node) {
  const found = [];
  for (const widget of node.widgets ?? []) {
    if (typeof widget.value !== "string" || !MODEL_FILE.test(widget.value)) continue;
    const match = KIND_BY_WIDGET.find(([pattern]) => pattern.test(widget.name));
    if (match) found.push({ kind: match[1], file: widget.value });
  }
  return found;
}

const STYLE = `
.dfmi-back{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:10000;display:flex;align-items:center;justify-content:center}
.dfmi{background:#353535;color:#ddd;border:1px solid #555;border-radius:10px;width:min(960px,94vw);max-height:92vh;overflow:auto;padding:18px 20px;font:14px system-ui,sans-serif;box-shadow:0 10px 40px #000a}
.dfmi h2{margin:0 0 10px;font-size:22px;color:#fff}
.dfmi .tags{margin-bottom:12px}.dfmi .tag{display:inline-block;padding:2px 8px;border-radius:5px;margin-right:6px;font-weight:600;font-size:13px}
.dfmi .t1{background:#4b3565;color:#d9c8f0}.dfmi .t2{background:#35584a;color:#c8f0dc}
.dfmi .t3{background:#3a3a3a;color:#ddd;text-transform:uppercase;font-size:12px}.dfmi .stats{display:inline-flex;gap:6px;margin-left:4px;vertical-align:middle}
.dfmi .stat{background:#2a2a2a;border:1px solid #4a4a4a;border-radius:5px;padding:1px 7px;font-size:13px;font-weight:600}
.dfmi .versions{display:flex;flex-wrap:wrap;gap:6px}.dfmi .version{display:inline-block;background:#2f2f2f;border:1px solid #555;border-radius:5px;padding:2px 8px;text-decoration:none;color:#ddd}
.dfmi .version.mine{background:#1f5fa8;border-color:#3b82d0;color:#fff}.dfmi .version.newer{border-color:#6a9a6a;color:#bfe8bf}
.dfmi table{width:100%;border-collapse:collapse;margin-bottom:14px}
.dfmi td{border:1px solid #4a4a4a;padding:7px 10px;vertical-align:top}.dfmi td:first-child{width:170px;color:#bbb;white-space:nowrap}
.dfmi a{color:#9cc8ff}.dfmi code{font-size:12px;word-break:break-all}
.dfmi input,.dfmi textarea{width:100%;box-sizing:border-box;background:#262626;color:#eee;border:1px solid #555;border-radius:4px;padding:5px 7px;font:inherit}
.dfmi textarea{min-height:52px;resize:vertical}
.dfmi .slider{display:flex;align-items:center;gap:8px}.dfmi .slider>button{flex:none;width:42px;height:64px;padding:0;font-size:26px;line-height:1}
.dfmi .stage{position:relative;flex:1;height:min(62vh,640px);background:#1e1e1e;border-radius:8px;overflow:hidden;display:flex;align-items:center;justify-content:center}
.dfmi .stage img,.dfmi .stage video{max-width:100%;max-height:100%;object-fit:contain;display:block;cursor:zoom-in}
.dfmi .blur{filter:blur(28px);cursor:pointer}.dfmi .count{text-align:center;color:#999;font-size:13px;margin-top:6px}
.dfmi .dots{display:flex;justify-content:center;gap:5px;margin-top:6px;flex-wrap:wrap}.dfmi .dots span{width:8px;height:8px;border-radius:50%;background:#555;cursor:pointer}.dfmi .dots span.on{background:#ddd}
.dfmi .meta{position:absolute;left:0;right:0;bottom:0;max-height:55%;overflow:auto;background:rgba(24,24,24,.92);padding:10px 12px;box-sizing:border-box;opacity:0;transition:opacity .15s;font-size:13px}
.dfmi .stage:hover .meta,.dfmi .meta:focus-within{opacity:1}
.dfmi .meta .chip{display:inline-block;border:1px solid #555;border-radius:5px;padding:2px 7px;margin:0 5px 5px 0;cursor:copy}.dfmi .meta .chip b{color:#999;font-weight:400;margin-right:5px}
.dfmi .meta a.chip{cursor:pointer;color:#fff}.dfmi .meta .prompt{border:1px solid #4a4a4a;border-radius:5px;padding:6px 8px;margin-top:4px;white-space:pre-wrap;word-break:break-word;cursor:copy}
.dfmi .meta .prompt b{color:#999;font-weight:400;margin-right:5px}
.dfmi .meta button.use{background:#24402a;border-color:#4a7a4a;color:#d6f5dc;padding:3px 10px;margin:0 5px 5px 0;font-size:13px}.dfmi .meta .applied{color:#9c9;margin-top:4px;white-space:pre-wrap}
.dfmi .row{display:flex;gap:8px;justify-content:flex-end;margin-top:14px}
.dfmi button{background:#222;color:#eee;border:1px solid #666;border-radius:6px;padding:7px 16px;cursor:pointer;font:inherit}
.dfmi button:hover{background:#2c2c2c}.dfmi .muted{color:#999}.dfmi .words span{display:inline-block;background:#262626;border:1px solid #555;border-radius:4px;padding:1px 6px;margin:0 4px 4px 0;cursor:copy}
`;
const addStyle = () => addStyleOnce("dfmi-style", STYLE);

async function openModelInfo(kind, file) {
  addStyle();
  const panel = element("div", { class: "dfmi" }, element("h2", {}, file), element("p", { class: "muted" }, "Computing the sha256 and asking Civitai… a large model takes a few seconds the first time."));
  const back = element("div", { class: "dfmi-back", onclick: (event) => event.target === back && close() }, panel);
  const onKey = (event) => !asking() && event.key === "Escape" && close();
  function close() {
    back.remove();
    document.removeEventListener("keydown", onKey);
  }
  document.addEventListener("keydown", onKey);
  document.body.append(back);
  const load = async (refresh) => {
    const response = await api.fetchApi(`/diceforge/model-info?kind=${encodeURIComponent(kind)}&file=${encodeURIComponent(file)}${refresh ? "&refresh=1" : ""}`);
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  };
  try {
    render(panel, await load(false), close, load);
  } catch (error) {
    panel.replaceChildren(element("h2", {}, file), element("p", {}, `Could not read the model info: ${error.message}`), element("div", { class: "row" }, element("button", { onclick: close }, "Close")));
  }
}

// Civitai's example images one at a time: ‹ › (or the arrow keys, or the dots), and how the image was made over it on hover (the prompts and
// settings from Civitai; click one to copy it). R-rated and up start blurred: the first click reveals, the next opens the full size.
const META_CHIPS = [["seed", "seed"], ["steps", "steps"], ["cfgScale", "cfg"], ["sampler", "sampler"], ["Schedule type", "schedule"], ["scheduler", "scheduler"],
  ["Clip skip", "clip skip"], ["Denoising strength", "denoise"], ["Size", "size"], ["Model", "model"], ["VAE", "vae"]];
const copy = (text) => navigator.clipboard?.writeText(String(text));
function metaPanel(image) {
  const meta = image.meta ?? {};
  const chips = META_CHIPS.filter(([key]) => meta[key] != null).map(([key, label]) =>
    element("span", { class: "chip", title: "Click to copy", onclick: () => copy(meta[key]) }, element("b", {}, label), String(meta[key])));
  const prompts = [["prompt", "positive"], ["negativePrompt", "negative"]].filter(([key]) => meta[key]).map(([key, label]) =>
    element("div", { class: "prompt", title: "Click to copy", onclick: () => copy(meta[key]) }, element("b", {}, label), meta[key]));
  const link = image.page ? [element("a", { class: "chip", href: image.page, target: "_blank", rel: "noopener" }, "civitai 🔗")] : [];
  const result = element("div", { class: "applied" });
  const settings = settingsOf(meta);
  const use = Object.keys(settings).length ? [element("button", { class: "use", title: "Put this image's prompts, seed, steps, CFG, sampler, scheduler and size into the workflow",
    onclick: () => {
      const { done, skipped } = applySettings(settings);
      result.textContent = [done.length ? `Set: ${done.join("; ")}.` : "Nothing in the workflow to put them in.", skipped.length ? `Not set: ${skipped.join("; ")}.` : ""].filter(Boolean).join("\n");
    } }, "⤵ Use these settings")] : [];
  const none = chips.length || prompts.length ? []
    : [element("span", { class: "muted" }, image.hasMeta !== false ? "Refresh from Civitai to see how this image was made." : "Civitai has no generation data for this image.")];
  return element("div", { class: "meta" }, element("div", {}, ...use, ...link, ...chips, ...none), ...prompts, result);
}
function slider(images) {
  if (!images.length) return element("div");
  let index = 0;
  const stage = element("div", { class: "stage" });
  const count = element("div", { class: "count" });
  const dots = element("div", { class: "dots" });
  const revealed = new Set();
  function show(next) {
    index = (next + images.length) % images.length;
    const image = images[index];
    const large = image.full ? image.full.replace("/original=true/", "/width=1200/") : image.url; // Big enough for the slider, smaller than the original.
    const video = image.type === "video" ? videoPreview(large) : null; // A video waits for ▶.
    const media = video ? video.video : element("img", { src: large });
    media.title = "Click to open the full size";
    if (shouldBlur(image) && !revealed.has(index)) media.classList.add("blur"); // Civitai's R and up: blurred until clicked (Blur NSFW).
    media.addEventListener("click", () => {
      if (media.classList.contains("blur")) media.classList.remove("blur"), revealed.add(index);
      else openLink(image.full || image.url);
    });
    media.addEventListener("error", () => { if (media.src !== image.url) media.src = safeURL(image.url); }, { once: true }); // The small copy instead.
    stage.replaceChildren(video ? video.wrapper : media, metaPanel(image));
    count.textContent = `${index + 1} / ${images.length}`;
    dots.replaceChildren(...images.map((_, dot) => element("span", { class: dot === index ? "on" : "", onclick: () => show(dot) })));
  }
  const onKey = (event) => {
    if (!stage.isConnected) return document.removeEventListener("keydown", onKey, true); // Closed, or drawn again (Refresh).
    if (asking() || event.key !== "ArrowLeft" && event.key !== "ArrowRight" || event.target.closest?.("input, textarea")) return;
    event.preventDefault();
    show(index + (event.key === "ArrowRight" ? 1 : -1));
  };
  document.addEventListener("keydown", onKey, true);
  show(0);
  const arrows = images.length > 1;
  return element("div", { class: "gallery" },
    element("div", { class: "slider" }, ...(arrows ? [element("button", { class: "prev", title: "Previous image (←)", onclick: () => show(index - 1) }, "‹")] : []),
      stage, ...(arrows ? [element("button", { class: "next", title: "Next image (→)", onclick: () => show(index + 1) }, "›")] : [])),
    count, ...(arrows ? [dots] : []));
}

// The model's versions on Civitai, newest first: yours marked, a newer one than yours marked new; each opens its page.
const VERSION_STATES = { mine: { className: "mine", title: "Your version", mark: "● " }, newer: { className: "newer", title: "Newer than yours", mark: "🆕 " },
  other: { className: "", title: "", mark: "" } };
function versionList(civitai) {
  const mine = civitai.versions.find((version) => version.id === civitai.version_id);
  return element("div", { class: "versions" }, ...civitai.versions.map((version) => {
    let state = VERSION_STATES.other;
    if (version.id === civitai.version_id) state = VERSION_STATES.mine;
    else if (mine && version.published > mine.published) state = VERSION_STATES.newer;
    return element("a", { class: `version ${state.className}`, href: `https://civitai.com/models/${civitai.model_id}?modelVersionId=${version.id}`,
      target: "_blank", rel: "noopener", title: [state.title, version.base_model, dateText(version.published)].filter(Boolean).join(" · ") },
    `${state.mark}${version.name}`);
  }));
}
function render(panel, info, close, load) {
  const civitai = info.civitai ?? {};
  const user = info.user ?? {};
  const title = user.name || (civitai.found ? `${civitai.model_name} - ${civitai.version_name}` : info.file);
  let saveTimer = null;
  const fields = {};
  const save = () => {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      const values = Object.fromEntries(Object.entries(fields).map(([key, input]) => [key, input.value]));
      api.fetchApi("/diceforge/model-info", { method: "POST", body: JSON.stringify({ kind: info.kind, file: info.file, user: values }) });
    }, 400);
  };
  const edit = (key, placeholder, multiline) => {
    const input = element(multiline ? "textarea" : "input", { placeholder, oninput: save });
    input.value = user[key] ?? "";
    fields[key] = input;
    return input;
  };
  const words = element("div", { class: "words" }, ...(civitai.trigger_words ?? []).map((word) =>
    element("span", { title: "Click to copy", onclick: () => navigator.clipboard?.writeText(word) }, word)));
  const civitaiCell = civitai.found
    ? element("a", { href: civitai.url, target: "_blank", rel: "noopener" }, "View on Civitai")
    : element("span", { class: "muted" }, civitai.error ? `Civitai could not be reached: ${civitai.error}` : "Not found on Civitai (a private, merged or renamed-and-edited file).");
  const rows = [
    ["File", element("code", {}, info.file)],
    ["Hash (sha256)", element("code", {}, info.sha256)],
    ["Size", info.size >= 1024 ** 3 ? `${(info.size / 1024 ** 3).toFixed(2)} GB` : `${(info.size / 1024 ** 2).toFixed(1)} MB`],
    ["Civitai", civitaiCell],
    ...(civitai.found ? [["Base model", civitai.base_model ?? "—"], ["Civitai trigger words", civitai.trigger_words?.length ? words : element("span", { class: "muted" }, "none")]] : []),
    ...(civitai.found && civitai.versions?.length ? [["Versions", versionList(civitai)]] : []),
    ...(civitai.found && (civitai.creator || civitai.updated) ? [["Creator, updated", [civitai.creator && `by ${civitai.creator}`, civitai.updated && `updated ${dateText(civitai.updated)}`].filter(Boolean).join(" · ")]] : []),
    ["Name", edit("name", civitai.found ? `${civitai.model_name} - ${civitai.version_name}` : "Your name for this model")],
    ["Trigger words", edit("trigger_words", "Words to put in the prompt")],
    ["Recommended settings", edit("settings", "Steps, CFG, sampler, scheduler, resolution…", true)],
    ["Notes", edit("notes", "Anything to remember about this model", true)],
  ];
  const images = slider(civitai.images ?? []);
  const refresh = element("button", { onclick: async () => {
    refresh.textContent = "Asking Civitai…";
    try { render(panel, await load(true), close, load); } catch (error) { refresh.textContent = `Failed: ${error.message}`; }
  } }, "Refresh from Civitai");
  panel.replaceChildren(
    element("h2", {}, title),
    element("div", { class: "tags" }, element("span", { class: "tag t1" }, civitai.type ?? info.kind), ...(civitai.base_model ? [element("span", { class: "tag t2" }, civitai.base_model)] : []),
      ...(civitai.found ? (civitai.tags ?? []).map((tag) => element("span", { class: "tag t3" }, tag)) : []),
      ...(civitai.found && civitai.stats ? [element("span", { class: "stats" }, ...statsChips(civitai.stats))] : [])),
    element("table", {}, ...rows.map(([label, value]) => element("tr", {}, element("td", {}, label), element("td", {}, value)))),
    images,
    element("div", { class: "row" }, refresh, element("button", { onclick: close }, "Close")),
  );
}

app.registerExtension({
  name: "DiceForge.ModelInfo",
  getNodeMenuItems(node) {
    return modelWidgets(node).map(({ kind, file }) => ({ content: `🛈 Model info: ${file.split(/[\\/]/).pop()}`, callback: () => openModelInfo(kind, file) }));
  },
});

export { openModelInfo, modelWidgets };
