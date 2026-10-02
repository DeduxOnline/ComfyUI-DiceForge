import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addStyleOnce, element } from "./dom.js";

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
const MODEL_FILE = /\.(safetensors|ckpt|pt|pth|bin|gguf|sft)$/i;
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
.dfmi table{width:100%;border-collapse:collapse;margin-bottom:14px}
.dfmi td{border:1px solid #4a4a4a;padding:7px 10px;vertical-align:top}.dfmi td:first-child{width:170px;color:#bbb;white-space:nowrap}
.dfmi a{color:#9cc8ff}.dfmi code{font-size:12px;word-break:break-all}
.dfmi input,.dfmi textarea{width:100%;box-sizing:border-box;background:#262626;color:#eee;border:1px solid #555;border-radius:4px;padding:5px 7px;font:inherit}
.dfmi textarea{min-height:52px;resize:vertical}
.dfmi .imgs{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px}
.dfmi .imgs img,.dfmi .imgs video{width:100%;border-radius:6px;display:block;cursor:zoom-in}
.dfmi .blur{filter:blur(24px);cursor:pointer}
.dfmi .row{display:flex;gap:8px;justify-content:flex-end;margin-top:14px}
.dfmi button{background:#222;color:#eee;border:1px solid #666;border-radius:6px;padding:7px 16px;cursor:pointer;font:inherit}
.dfmi button:hover{background:#2c2c2c}.dfmi .muted{color:#999}.dfmi .words span{display:inline-block;background:#262626;border:1px solid #555;border-radius:4px;padding:1px 6px;margin:0 4px 4px 0;cursor:copy}
`;
const addStyle = () => addStyleOnce("dfmi-style", STYLE);

async function openModelInfo(kind, file) {
  addStyle();
  const panel = element("div", { class: "dfmi" }, element("h2", {}, file), element("p", { class: "muted" }, "Computing the sha256 and asking Civitai… a large model takes a few seconds the first time."));
  const back = element("div", { class: "dfmi-back", onclick: (event) => event.target === back && close() }, panel);
  const onKey = (event) => event.key === "Escape" && close();
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
    ["Name", edit("name", civitai.found ? `${civitai.model_name} - ${civitai.version_name}` : "Your name for this model")],
    ["Trigger words", edit("trigger_words", "Words to put in the prompt")],
    ["Recommended settings", edit("settings", "Steps, CFG, sampler, scheduler, resolution…", true)],
    ["Notes", edit("notes", "Anything to remember about this model", true)],
  ];
  const images = element("div", { class: "imgs" }, ...(civitai.images ?? []).map((image) => {
    const media = image.type === "video"
      ? element("video", { src: image.url, muted: "", loop: "", autoplay: "", playsinline: "" })
      : element("img", { src: image.url, loading: "lazy" });
    media.title = "Click to open the full size";
    media.addEventListener("click", () => {
      if (media.classList.contains("blur")) media.classList.remove("blur"); // First click on a blurred one only reveals it.
      else window.open(image.full || image.url, "_blank", "noopener");
    });
    if ((image.nsfwLevel ?? 1) >= 4) media.classList.add("blur"); // Civitai's R and up: blurred until clicked.
    return media;
  }));
  const refresh = element("button", { onclick: async () => {
    refresh.textContent = "Asking Civitai…";
    try { render(panel, await load(true), close, load); } catch (error) { refresh.textContent = `Failed: ${error.message}`; }
  } }, "Refresh from Civitai");
  panel.replaceChildren(
    element("h2", {}, title),
    element("div", { class: "tags" }, element("span", { class: "tag t1" }, civitai.type ?? info.kind), ...(civitai.base_model ? [element("span", { class: "tag t2" }, civitai.base_model)] : [])),
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
