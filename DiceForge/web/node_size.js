import { app } from "../../scripts/app.js";

// Node height of the DiceForge nodes. Nodes 2.0 draws a node at least as tall as its stored height, and a new node's stored height counts the
// advanced inputs too, which are hidden until "Show advanced inputs": that left an empty gap under the inputs, also after hiding them again. In
// Nodes 2.0 the DiceForge nodes store a small height instead, so they fit what they show and grow and shrink with the advanced inputs. A node the
// user made taller keeps its height. The classic canvas draws from the stored height, so there it is at least the full height, as before.
const SMALL_HEIGHT = 60;
const isDiceForge = (node) => /DiceForge/i.test(node.constructor?.nodeData?.python_module ?? "");
const vueNodes = () => !!app.extensionManager?.setting?.get?.("Comfy.VueNodes.Enabled");

export function fitNodeHeight(node) {
  const full = node.computeSize()[1];
  if (vueNodes()) {
    if (node.size[1] > SMALL_HEIGHT && node.size[1] <= full + 1) node.setSize([node.size[0], SMALL_HEIGHT]);
  } else if (node.size[1] < full) {
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
