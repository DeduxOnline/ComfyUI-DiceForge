import { app } from "../../scripts/app.js";

// Live size preview for SDXL Resolution List (Latent): the same size math as the node for fixed sizes; random groups show what they can pick.
const NODE_TYPE = "SDXLResolutionListLatent";
const CHAOS_PIXELS = 1024 * 1024;

// Python round() ties to even; Math.round ties up.
function roundHalfToEven(value) {
  const floor = Math.floor(value);
  if (value - floor !== 0.5) return Math.round(value);
  return floor % 2 === 0 ? floor : floor + 1;
}

function widgetValue(node, name) {
  return node.widgets?.find((widget) => widget.name === name)?.value;
}

// Preview for the node's current inputs: [main text, muted text].
function previewText(node) {
  const group = widgetValue(node, "resolution");
  const size = String(widgetValue(node, "resolution.size") ?? "");
  const scale = Number(widgetValue(node, "scale") ?? 1);
  const multiple = Number(widgetValue(node, "multiple") ?? 8);
  if (!(scale > 0) || !(multiple > 0)) return ["—", ""];
  if (group === "Random") return [`random: ${size}`, ""];
  if (group === "Random Chaos") {
    const maxAspect = Number(widgetValue(node, "resolution.max_aspect") ?? 2);
    const megapixels = (CHAOS_PIXELS * scale * scale) / (1024 * 1024);
    return [`random ${size.toLowerCase()}, up to ${+maxAspect.toFixed(2)}:1`, `≤ ${megapixels.toFixed(2)} MP`];
  }
  const match = /^(\d+)\s*x\s*(\d+)/.exec(size);
  if (!match) return ["—", ""];
  const snap = (pixels) => Math.max(multiple, roundHalfToEven(roundHalfToEven(pixels * scale) / multiple) * multiple);
  const width = snap(Number(match[1]));
  const height = snap(Number(match[2]));
  return [`${width} × ${height}`, `${((width * height) / (1024 * 1024)).toFixed(2)} MP`];
}

app.registerExtension({
  name: "ResolutionForge.SDXLResolutionPreview",
  nodeCreated(node) {
    if (node.comfyClass !== NODE_TYPE) return;
    // Laid out like the core Resolution Selector preview: the size, then the megapixels in a muted color.
    const element = document.createElement("div");
    Object.assign(element.style, {
      display: "flex", alignItems: "center", justifyContent: "center", gap: "8px", width: "100%", minHeight: "24px",
      fontSize: "12px", fontVariantNumeric: "tabular-nums", pointerEvents: "none",
    });
    const main = element.appendChild(document.createElement("span"));
    const muted = element.appendChild(document.createElement("span"));
    muted.style.opacity = "0.6";
    main.textContent = "—";
    node.addDOMWidget("size_preview", "resolution_forge_preview", element, {
      serialize: false,
      getValue: () => undefined,
      setValue: () => {},
      getMinHeight: () => 24,
      getMaxHeight: () => 24,
    });
    // Widget values change through several paths (the nested list swaps its inputs), so the text is refreshed on a short timer while the node exists.
    const timer = setInterval(() => {
      const [text, note] = previewText(node);
      if (main.textContent !== text) main.textContent = text;
      if (muted.textContent !== note) muted.textContent = note;
    }, 200);
    const onRemoved = node.onRemoved;
    node.onRemoved = function () {
      clearInterval(timer);
      return onRemoved?.apply(this, arguments);
    };
  },
});
