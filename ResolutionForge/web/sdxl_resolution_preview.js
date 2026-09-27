import { app } from "../../scripts/app.js";

// Live size preview for SDXL Resolution List (Latent). The node declares the core resolution preview widget; this extension feeds it through two hidden
// helper widgets: the size after `scale` as the ratio ("1216:832") and its megapixels, so the core preview math gives exactly the node's size.
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

// Size after `scale` for fixed sizes (the node rounds it to `multiple` next, as the preview does), or null for random sizes, which the preview shows as "—".
function scaledSize(node) {
  const group = widgetValue(node, "resolution");
  const match = /^(\d+)\s*x\s*(\d+)/.exec(String(widgetValue(node, "resolution.size") ?? ""));
  const scale = Number(widgetValue(node, "scale") ?? 1);
  if ((group !== "Standard" && group !== "High-Res") || !match || !(scale > 0)) return null;
  return { width: roundHalfToEven(Number(match[1]) * scale), height: roundHalfToEven(Number(match[2]) * scale) };
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
    // Widget values change through several paths (the nested list swaps its inputs), so the helpers are refreshed on a short timer while the node exists.
    const timer = setInterval(() => {
      const size = scaledSize(node);
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
