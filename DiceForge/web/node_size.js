import { app } from "../../scripts/app.js";

// Node height of the DiceForge nodes. Nodes 2.0 draws a node at least as tall as its stored height, and a new node's stored height counts the
// advanced inputs too, which are hidden until "Show advanced inputs": that left an empty gap under the inputs, also after hiding them again. In
// Nodes 2.0 the DiceForge nodes store a small height instead, so they fit what they show and grow and shrink with the advanced inputs. The
// classic canvas draws from the stored height, so there it is the full height. A node taller than what it shows (a workflow saved so, or
// content that got smaller) is fitted again too. A height the user gave the node (its corner dragged) stays, also after a reload: the height
// set here is kept in the node's properties, and a node of another height (not the full one either, which the frontend sets when widgets come
// and go) was sized by the user. Without that record (a workflow from before it), a node with a text field keeps a taller height, which the
// field takes. The DiceForge panels (previews, cells, the LoRA list) ask for the height of their content, no more.
const SMALL_HEIGHT = 60;
const FITTED = "dice_forge_height";
const isDiceForge = (node) => /DiceForge/i.test(node.constructor?.nodeData?.python_module ?? "");
const vueNodes = () => !!app.extensionManager?.setting?.get?.("Comfy.VueNodes.Enabled");
const stretches = (node) => (node.widgets ?? []).some((widget) => widget.type === "customtext" || widget.inputEl?.tagName === "TEXTAREA"
  || widget.element?.tagName === "TEXTAREA" || !!widget.element?.querySelector?.("textarea"));

export function fitNodeHeight(node) {
  const full = node.computeSize()[1], height = node.size[1], fitted = node.properties?.[FITTED];
  const userSized = Math.abs(height - full) > 1 && (fitted == null ? stretches(node) && height > full : Math.abs(height - fitted) > 1);
  let next = height;
  if (vueNodes()) {
    if (!userSized && height > SMALL_HEIGHT) next = SMALL_HEIGHT;
  } else if (height < full || (!userSized && height > full + 1)) {
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
