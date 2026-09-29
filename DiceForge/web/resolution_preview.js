import { app } from "../../scripts/app.js";

// Live size preview for the DiceForge resolution nodes. Both use the core resolution preview widget; this extension feeds it through two hidden
// helper widgets: a size or aspect ratio as the ratio ("1216:832") and the megapixels, so the core preview math gives exactly the size to show.
// Fixed sizes and ratios show their size live; random options show the size of the last run, as long as the settings (other than the seed) are the same.

// The node's rounding of a fixed size (SDXLResolutionListLatent.round_to_multiple): of the multiples just below and above each side, the pair closest
// to the exact aspect ratio, then closest in pixels.
function roundToMultiple(width, height, multiple) {
  const steps = (value) => [...new Set([Math.max(multiple, Math.floor(value / multiple) * multiple), Math.max(multiple, Math.ceil(value / multiple) * multiple)])];
  const ratio = Math.log(width / height), pixels = width * height;
  const key = ([w, h]) => [Math.round(Math.abs(Math.log(w / h) - ratio) * 1e9) / 1e9, Math.abs(w * h - pixels), w, h];
  let best = null;
  for (const w of steps(width)) for (const h of steps(height)) {
    const candidate = [w, h];
    if (!best) { best = candidate; continue; }
    const [a, b] = [key(candidate), key(best)];
    const index = a.findIndex((value, i) => value !== b[i]);
    if (index >= 0 && a[index] < b[index]) best = candidate;
  }
  return best;
}

// The node's rescale (sdxl_resolution_list_latent.rescaled): by percentage of each side, to a width and/or height, or to a longest side.
function rescaled(width, height, current) {
  if (current.rescale === "to Width/Height") {
    const targetWidth = Number(current.rescale_width) || 0, targetHeight = Number(current.rescale_height) || 0;
    if (targetWidth && targetHeight) return [targetWidth, targetHeight];
    if (targetWidth) return [targetWidth, (height * targetWidth) / width];
    if (targetHeight) return [(width * targetHeight) / height, targetHeight];
    return [width, height];
  }
  if (current.rescale === "to longest side") {
    const side = Number(current.longer_side ?? 1024);
    return width >= height ? [side, (height * side) / width] : [(width * side) / height, side];
  }
  const factor = Number(current.percent ?? 100) / 100;
  return [width * factor, height * factor];
}

function widgetValue(node, name) {
  return node.widgets?.find((widget) => widget.name === name)?.value;
}

// Per node: the settings that decide the size (the seed is left out: with "randomize" it changes right after each run), and the preview for fixed choices.
const NODES = {
  SDXLResolutionListLatent: {
    settings: (node) => ({
      group: widgetValue(node, "resolution"),
      size: String(widgetValue(node, "resolution.size") ?? ""),
      max_aspect: widgetValue(node, "resolution.max_aspect") ?? null,
      rescale: String(widgetValue(node, "rescale") ?? "by percentage"),
      percent: widgetValue(node, "rescale.percent") ?? null,
      rescale_width: widgetValue(node, "rescale.width") ?? null,
      rescale_height: widgetValue(node, "rescale.height") ?? null,
      longer_side: widgetValue(node, "rescale.longer_side") ?? null,
      multiple: Number(widgetValue(node, "multiple") ?? 8),
    }),
    isRandom: (current) => current.group !== "Standard" && current.group !== "High-Res",
    usesMaxAspect: (current) => current.group === "Random Chaos",
    // The final size, as the node computes it (rescale, then rounding to multiple), given to the preview as ratio and megapixels of an exact
    // multiple, which the preview keeps as it is.
    fixed: (current) => {
      const match = /^(\d+)\s*x\s*(\d+)/.exec(current.size);
      if (!match || !(current.multiple > 0)) return null;
      const [exactWidth, exactHeight] = rescaled(Number(match[1]), Number(match[2]), current);
      if (!(exactWidth > 0) || !(exactHeight > 0)) return null;
      const [width, height] = roundToMultiple(exactWidth, exactHeight, current.multiple);
      return { ratio: `${width}:${height}`, megapixels: (width * height) / (1024 * 1024) };
    },
  },
  ResolutionSelectorRandomLatent: {
    settings: (node) => ({
      aspect_ratio: String(widgetValue(node, "aspect_ratio") ?? ""),
      megapixels: Number(widgetValue(node, "megapixels") ?? 1),
      multiple: Number(widgetValue(node, "multiple") ?? 8),
      max_aspect: Number(widgetValue(node, "max_aspect") ?? 2),
    }),
    isRandom: (current) => current.aspect_ratio.startsWith("Random"),
    usesMaxAspect: (current) => current.aspect_ratio.startsWith("Random Chaos"),
    // The aspect ratio and megapixels as they are: the same as the core preview without this extension.
    fixed: (current) => {
      const match = /^(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)/.exec(current.aspect_ratio);
      return match ? { ratio: `${match[1]}:${match[2]}`, megapixels: current.megapixels } : null;
    },
  },
};

// Preview input for the current settings: the fixed choice, the last run's size when a random choice has the same settings, or null ("—").
function previewInput(config, node, last) {
  const current = config.settings(node);
  if (!config.isRandom(current)) return config.fixed(current);
  if (!last) return null;
  for (const [key, value] of Object.entries(current)) {
    if (key === "max_aspect" && !config.usesMaxAspect(current)) continue;
    if (String(last[key]) !== String(value)) return null;
  }
  return { ratio: `${last.width}:${last.height}`, megapixels: (last.width * last.height) / (1024 * 1024) };
}

// Repairs of nodes saved by older versions. The nested resolution list of SDXL Resolution List can come back with a size where its group belongs
// ("Any Listed" instead of "Random", and no size list), which the backend can't run: the group whose size list has that value is picked, with it.
async function repairResolutionGroup(node) {
  const group = node.widgets?.find((widget) => widget.name === "resolution");
  const groups = group?.options?.values;
  if (!group || !Array.isArray(groups) || groups.includes(group.value)) return;
  const stale = String(group.value);
  for (const candidate of groups) {
    group.value = candidate;
    group.callback?.(candidate);
    await new Promise((resolve) => setTimeout(resolve, 0)); // The size list of the group is built after the change.
    const size = node.widgets.find((widget) => widget.name === "resolution.size");
    if (size?.options?.values?.includes(stale)) {
      size.value = stale;
      size.callback?.(stale);
      console.info(`[DiceForge] ${node.comfyClass} #${node.id}: resolution repaired to ${candidate} / ${stale} (saved by an older version).`);
      return;
    }
  }
  group.value = groups[0]; // An unknown value: the first group, so the node runs.
  group.callback?.(groups[0]);
}
// Workflows saved while SDXL Resolution List had a scale number (before the rescale list) have that number where rescale now is, and the values
// after it (multiple, batch, seed_mode) one place off: they are put back, with scale as by percentage (1.5: 150).
const CONTROL_MODES = ["fixed", "increment", "decrement", "randomize"];
function savedScale(info) {
  const values = info?.widgets_values;
  if (!Array.isArray(values)) return null;
  const at = values.findIndex((value, index) => CONTROL_MODES.includes(value) && [1, 2, 3].every((offset) => typeof values[index + offset] === "number"));
  return at < 0 ? null : { scale: values[at + 1], multiple: values[at + 2], batch: values[at + 3], seedMode: values[at + 4] };
}
async function migrateScale(node, saved) {
  const set = (name, value) => {
    const widget = node.widgets?.find((widget) => widget.name === name);
    if (!widget || value === undefined) return;
    widget.value = value;
    widget.callback?.(value);
  };
  set("rescale", "by percentage");
  await new Promise((resolve) => setTimeout(resolve, 0)); // The percent input is built after the change.
  set("rescale.percent", Math.max(1, Math.round(saved.scale * 100)));
  set("multiple", saved.multiple);
  set("batch", saved.batch);
  if (node.widgets?.find((widget) => widget.name === "seed_mode")?.options?.values?.includes(saved.seedMode)) set("seed_mode", saved.seedMode);
  console.info(`[DiceForge] ${node.comfyClass} #${node.id}: scale ${saved.scale} became rescale by percentage ${Math.round(saved.scale * 100)} (saved by an older version).`);
}
// Inputs left from older versions (vae_alignment) that the node no longer has: unconnected ones are removed.
function removeStaleInputs(node) {
  const names = new Set((node.widgets ?? []).map((widget) => widget.name));
  for (let index = (node.inputs?.length ?? 0) - 1; index >= 0; index--) {
    const input = node.inputs[index];
    if (input.widget && !names.has(input.widget.name) && input.link == null) node.removeInput(index);
  }
}

// Hidden helper widget, added last so saved widget values keep their order.
function addHelper(node, name, value) {
  const widget = node.addWidget("text", name, value, () => {}, { serialize: false, hidden: true });
  widget.hidden = true;
  widget.computeSize = () => [0, -4];
  return widget;
}

app.registerExtension({
  name: "DiceForge.ResolutionPreview",
  nodeCreated(node) {
    const config = NODES[node.comfyClass];
    if (!config) return;
    const ratio = addHelper(node, "preview_ratio", "");
    const megapixels = addHelper(node, "preview_megapixels", 0);
    // The preview reads the helpers (Resolution Selector's preview reads its own inputs when this extension is not loaded).
    const preview = node.widgets.find((widget) => widget.name === "preview");
    if (preview?.options) Object.assign(preview.options, { ratio_widget: "preview_ratio", megapixels_widget: "preview_megapixels", multiple_widget: "multiple" });
    // Workflows saved before seed_mode existed have a helper's value where seed_mode now is: fall back to the default.
    const onConfigure = node.onConfigure;
    node.onConfigure = function (info) {
      const scale = node.comfyClass === "SDXLResolutionListLatent" ? savedScale(info) : null;
      const seedMode = node.widgets?.find((widget) => widget.name === "seed_mode");
      if (seedMode && !seedMode.options?.values?.includes(seedMode.value)) seedMode.value = "random";
      const result = onConfigure?.apply(this, arguments);
      repairResolutionGroup(node)
        .then(() => scale && migrateScale(node, scale))
        .then(() => removeStaleInputs(node));
      return result;
    };
    let last = null;
    // The node sends the size of each run with the settings it came from.
    const onExecuted = node.onExecuted;
    node.onExecuted = function (output) {
      last = output?.dice_forge_last_size?.[0] ?? last;
      return onExecuted?.apply(this, arguments);
    };
    // Widget values change through several paths (the nested list swaps its inputs), so the helpers are refreshed on a short timer while the node exists.
    const timer = setInterval(() => {
      const input = previewInput(config, node, last);
      const nextRatio = input ? input.ratio : "";
      const nextMegapixels = input ? input.megapixels : 0;
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
