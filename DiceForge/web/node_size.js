import { app } from "../../scripts/app.js";

// Node height of the DiceForge nodes. Nodes 2.0 draws a node at least as tall as its stored height, and a new node's stored height counts the
// advanced inputs too, which are hidden until "Show advanced inputs": that left an empty gap under the inputs, also after hiding them again. In
// Nodes 2.0 the DiceForge nodes store a small height instead, so they fit what they show and grow and shrink with the advanced inputs. The
// classic canvas draws from the stored height, so there it is the full height. A node taller than what it shows (a workflow saved so, or
// content that got smaller) is fitted again too, unless it has a text field, which takes the extra height, so a node the user made taller for
// its text keeps its height. The DiceForge panels (previews, cells, the LoRA list) ask for the height of their content, no more.
const SMALL_HEIGHT = 60;
const isDiceForge = (node) => /DiceForge/i.test(node.constructor?.nodeData?.python_module ?? "");
const vueNodes = () => !!app.extensionManager?.setting?.get?.("Comfy.VueNodes.Enabled");
const stretches = (node) => (node.widgets ?? []).some((widget) => widget.type === "customtext" || widget.inputEl?.tagName === "TEXTAREA"
  || widget.element?.tagName === "TEXTAREA" || !!widget.element?.querySelector?.("textarea"));

export function fitNodeHeight(node) {
  const full = node.computeSize()[1], keep = stretches(node);
  if (vueNodes()) {
    if (node.size[1] > SMALL_HEIGHT && (!keep || node.size[1] <= full + 1)) node.setSize([node.size[0], SMALL_HEIGHT]);
  } else if (node.size[1] < full || (!keep && node.size[1] > full + 1)) {
    node.setSize([node.size[0], full]);
  }
  node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
  name: "DiceForge.NodeSize",
  nodeCreated(node) {
    if (!isDiceForge(node)) return;
    requestAnimationFrame(() => fitNodeHeight(node)); // After the other DiceForge extensions add their widgets to the node.
    const onConfigure = node.onConfigure;
    node.onConfigure = function (...args) {
      const result = onConfigure?.apply(this, args);
      requestAnimationFrame(() => fitNodeHeight(node)); // A loaded workflow's node: its saved height, unless it has the gap.
      return result;
    };
  },
});
