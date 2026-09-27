import { app } from "../../scripts/app.js";

// Live size preview for SDXL Resolution List (Latent). The node declares the core resolution preview widget; this extension feeds it through two hidden
// helper widgets: a size as the ratio ("1216:832") and its megapixels, so the core preview math gives exactly that size.
// Fixed sizes show the size after `scale`; random sizes show the size of the last run, as long as the settings (other than the seed) are the same.
const NODE_TYPE = "SDXLResolutionListLatent";

// Python round() ties to even; Math.round ties up.
function roundHalfToEven(value) {
  const floor = Math.floor(value);
  if (value - floor !== 0.5) return Math.round(value);
  return floor % 2 === 0 ? floor : floor + 1;
}

function widgetValue(node, name) {
  return node.widgets?.find((widget) => widget.name === name)?.value;
}

// Current settings that decide the size (the seed is left out: with "randomize" it changes right after each run).
function settings(node) {
  return {
    group: widgetValue(node, "resolution"),
    size: String(widgetValue(node, "resolution.size") ?? ""),
    max_aspect: widgetValue(node, "resolution.max_aspect") ?? null,
    scale: Number(widgetValue(node, "scale") ?? 1),
    multiple: Number(widgetValue(node, "multiple") ?? 8),
  };
}

// Size to show: after `scale` for fixed sizes (the preview rounds it to `multiple` like the node), the last run's size for random sizes, or null ("—").
function previewSize(node, last) {
  const current = settings(node);
  if (current.group === "Standard" || current.group === "High-Res") {
    const match = /^(\d+)\s*x\s*(\d+)/.exec(current.size);
    if (!match || !(current.scale > 0)) return null;
    return { width: roundHalfToEven(Number(match[1]) * current.scale), height: roundHalfToEven(Number(match[2]) * current.scale) };
  }
  const same = last && last.group === current.group && last.size === current.size && last.scale === current.scale && last.multiple === current.multiple
    && (current.group !== "Random Chaos" || Number(last.max_aspect) === Number(current.max_aspect));
  return same ? { width: last.width, height: last.height } : null;
}

// Hidden helper widget, added last so saved widget values keep their order.
function addHelper(node, name, value) {
  const widget = node.addWidget("text", name, value, () => {}, { serialize: false, hidden: true });
  widget.hidden = true;
  widget.computeSize = () => [0, -4];
  return widget;
}

app.registerExtension({
  name: "ResolutionForge.SDXLResolutionPreview",
  nodeCreated(node) {
    if (node.comfyClass !== NODE_TYPE) return;
    const ratio = addHelper(node, "preview_ratio", "");
    const megapixels = addHelper(node, "preview_megapixels", 0);
    let last = null;
    // The node sends the size of each run with the settings it came from.
    const onExecuted = node.onExecuted;
    node.onExecuted = function (output) {
      last = output?.resolution_forge_last_size?.[0] ?? last;
      return onExecuted?.apply(this, arguments);
    };
    // Widget values change through several paths (the nested list swaps its inputs), so the helpers are refreshed on a short timer while the node exists.
    const timer = setInterval(() => {
      const size = previewSize(node, last);
      const nextRatio = size ? `${size.width}:${size.height}` : "";
      const nextMegapixels = size ? (size.width * size.height) / (1024 * 1024) : 0;
      if (ratio.value !== nextRatio) ratio.value = nextRatio;
      if (megapixels.value !== nextMegapixels) megapixels.value = nextMegapixels;
    }, 200);
    const onRemoved = node.onRemoved;
    node.onRemoved = function () {
      clearInterval(timer);
      return onRemoved?.apply(this, arguments);
    };
  },
});
