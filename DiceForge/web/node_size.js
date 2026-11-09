import { app } from "../../scripts/app.js";

// Node height of the DiceForge nodes in the classic canvas: a node is never shorter than its content, and a taller one is fitted again,
// unless the user dragged its corner (kept in properties.dice_forge_height, also after a reload). The DiceForge panels (previews, cells,
// the LoRA list) ask for the height of their content, no more. In Nodes 2.0 nothing fits the height: the node keeps the size the user set
// (the author's choice, 2026-11-09), so a node does not grow or shrink by itself.
const FITTED = "dice_forge_height";
const isDiceForge = (node) => /DiceForge/i.test(node.constructor?.nodeData?.python_module ?? "");
const vueNodes = () => !!app.extensionManager?.setting?.get?.("Comfy.VueNodes.Enabled");
const stretches = (node) => (node.widgets ?? []).some((widget) => widget.type === "customtext" || widget.inputEl?.tagName === "TEXTAREA"
  || widget.element?.tagName === "TEXTAREA" || !!widget.element?.querySelector?.("textarea"));

export function fitNodeHeight(node) {
  if (vueNodes()) return; // Nodes 2.0 keeps the height the user set.
  const full = node.computeSize()[1], height = node.size[1], fitted = node.properties?.[FITTED];
  const userSized = Math.abs(height - full) > 1 && (fitted == null ? stretches(node) && height > full : Math.abs(height - fitted) > 1);
  let next = height;
  if (height < full || (!userSized && height > full + 1)) {
    next = full; // The classic canvas draws the content in the stored height: never less than it needs.
  }
  if (next !== height) node.setSize([node.size[0], next]);
  if (!userSized || next !== height) (node.properties ??= {})[FITTED] = next;
  node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
  name: "DiceForge.NodeSize",
  nodeCreated(node) {
    if (!isDiceForge(node)) return;
    requestAnimationFrame(() => fitNodeHeight(node)); // After the other DiceForge extensions add their widgets to the node.
    const onConfigure = node.onConfigure;
    node.onConfigure = function (...args) {
      // Loading keeps the properties the workflow doesn't have: a height a panel fitted the new node to is not the saved one's.
      if (!(FITTED in (args[0]?.properties ?? {}))) delete node.properties?.[FITTED];
      const result = onConfigure?.apply(this, args);
      requestAnimationFrame(() => fitNodeHeight(node)); // A loaded workflow's node: its saved height, unless it has the gap.
      return result;
    };
  },
});
