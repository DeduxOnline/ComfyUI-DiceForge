// The ComfyUI internals DiceForge's frontend (DiceForge/web) relies on, checked in the ComfyUI these tests run with: the version CI pins, and
// ComfyUI master on the weekly run (.github/workflows/tests.yml). When an update of ComfyUI renames, moves or changes one of them, the test that
// fails names it and the DiceForge files that use it, instead of a feature breaking somewhere else. The comfy-watcher agent
// (.claude/agents/comfy-watcher.md) starts from here.
const { test, expect, openComfy, addNodes, connect, queueFromPage } = require("./helpers");

const changed = (what, files) => `ComfyUI changed ${what}: DiceForge uses it in ${files}`;

test.describe("ComfyUI as DiceForge uses it", () => {
  test("app, api and LiteGraph have what DiceForge calls", async ({ page }) => {
    await openComfy(page, { vue: false });
    const missing = await page.evaluate(async () => {
      const { app } = await import("/scripts/app.js");
      const { api } = await import("/scripts/api.js");
      const needed = {
        "app.registerExtension": app.registerExtension, "app.graph.serialize": app.graph?.serialize, "app.loadGraphData": app.loadGraphData,
        "app.queuePrompt": app.queuePrompt, "app.graphToPrompt": app.graphToPrompt, "app.handleFile": app.handleFile,
        "app.refreshComboInNodes": app.refreshComboInNodes, "app.canvas.ds": app.canvas?.ds,
        "app.extensionManager.setting.get": app.extensionManager?.setting?.get, "app.extensionManager.setting.set": app.extensionManager?.setting?.set,
        "app.extensionManager.toast.add": app.extensionManager?.toast?.add,
        "app.extensionManager.queueSettings.batchCount": typeof app.extensionManager?.queueSettings?.batchCount === "number", // xy_plot.js: Set Run to N cells.
        "api.fetchApi": api.fetchApi, "api.apiURL": api.apiURL, "api.addEventListener": api.addEventListener,
        "LiteGraph.createNode": window.LiteGraph?.createNode,
      };
      return Object.entries(needed).filter(([, value]) => !value).map(([name]) => name);
    });
    expect(missing, changed("these names of scripts/app.js, scripts/api.js and LiteGraph", "most of DiceForge/web")).toEqual([]);
    expect(await page.evaluate(() => [typeof window.LiteGraph.NODE_TITLE_HEIGHT, typeof window.LiteGraph.NODE_WIDGET_HEIGHT]),
      changed("LiteGraph's node sizes", "e2e/qa/lib.js")).toEqual(["number", "number"]);
  });

  test("a run is sent through api.queuePrompt, with the workflow its images get", async ({ page }) => {
    await openComfy(page, { vue: false });
    await addNodes(page, [{ type: "DiceForgeRandomInt" }]);
    const sent = await page.evaluate(async () => { // Answered here, as by the server: nothing runs.
      const { api } = await import("/scripts/api.js");
      const queuePrompt = api.queuePrompt;
      let seen = null;
      api.queuePrompt = async (number, data) => {
        seen = { keys: Object.keys(data ?? {}), nodes: Array.isArray(data?.workflow?.nodes) };
        return { prompt_id: "dice-forge-contract", number: 0, node_errors: {} };
      };
      try {
        await window.app.queuePrompt(0);
      } finally {
        api.queuePrompt = queuePrompt;
      }
      return seen;
    });
    expect(sent, changed("how a run is sent (api.queuePrompt(number, { output, workflow }), the workflow saved in its images)", "prompt_preview.js"))
      .toEqual({ keys: expect.arrayContaining(["output", "workflow"]), nodes: true });
  });

  test("the settings DiceForge registers are there, with their defaults", async ({ page }) => {
    await openComfy(page, { vue: false });
    const values = await page.evaluate(() => ["DiceForge.BlurNSFW", "DiceForge.PromptHighlight", "DiceForge.TagAutocomplete"]
      .map((id) => window.app.extensionManager.setting.get(id)));
    expect(values, changed("the settings of extensions (registerExtension({ settings }))", "media.js, prompt_highlight.js, tag_autocomplete.js"))
      .toEqual([true, true, true]);
  });

  test("loading a workflow calls the hooks DiceForge uses: nodeCreated, a node's onConfigure", async ({ page }) => {
    await openComfy(page, { vue: false });
    await page.evaluate(() => {
      window.contractCalls = { nodeCreated: 0, onConfigure: 0 };
      window.app.registerExtension({
        name: "DiceForge.ContractProbe",
        nodeCreated(node) {
          window.contractCalls.nodeCreated++;
          const onConfigure = node.onConfigure;
          node.onConfigure = function (...args) {
            window.contractCalls.onConfigure++;
            return onConfigure?.apply(this, args);
          };
        },
      });
    });
    await addNodes(page, [{ type: "DiceForgeRandomInt" }]);
    await page.evaluate(async () => window.app.loadGraphData(window.app.graph.serialize()));
    const calls = await page.evaluate(() => window.contractCalls);
    expect(calls.nodeCreated, changed("nodeCreated", "every DiceForge extension")).toBeGreaterThan(1);
    expect(calls.onConfigure, changed("a node's onConfigure on loading", "node_size.js, lora_stack.js and the previews")).toBeGreaterThan(0);
  });

  test("a run sends the events DiceForge listens to: execution_start, execution_cached, executed", async ({ page, request }) => {
    await openComfy(page, { vue: false });
    const [value, preview] = await addNodes(page, [{ type: "DiceForgeRandomInt" }, { type: "PreviewAny", pos: [400, 40] }]);
    await connect(page, value, 0, preview, 0);
    await page.evaluate(async () => {
      const { api } = await import("/scripts/api.js");
      window.contractEvents = [];
      for (const name of ["execution_start", "execution_cached", "executed"]) api.addEventListener(name, () => window.contractEvents.push(name));
    });
    await queueFromPage(page, request);
    await expect.poll(() => page.evaluate(() => [...new Set(window.contractEvents)].sort((a, b) => a.localeCompare(b))),
      changed("the names of the run events", "dice_grid.js, prompt_preview.js")).toEqual(["executed", "execution_cached", "execution_start"]);
  });
});

for (const vue of [true, false]) {
  test.describe(vue ? "ComfyUI as DiceForge uses it, Nodes 2.0" : "ComfyUI as DiceForge uses it, classic nodes", () => {
    test.beforeEach(async ({ page }) => openComfy(page, { vue }));

    test("a node's class, data and DOM widgets", async ({ page }) => {
      const [clip, spare] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode" }, { type: "DiceForgeRandomInt", pos: [600, 40] }]);
      const facts = await page.evaluate(([clip, spare]) => {
        const node = window.app.graph.getNodeById(clip), other = window.app.graph.getNodeById(spare);
        const plain = other.addDOMWidget("contract_probe", "contract_probe", document.createElement("div"), { serialize: false });
        const result = {
          comfyClass: node.comfyClass, module: node.constructor?.nodeData?.python_module ?? "", margin: plain.margin, layout: typeof plain.computeLayoutSize,
          methods: ["addDOMWidget", "computeSize", "setSize", "setDirtyCanvas"].filter((name) => typeof node[name] !== "function"),
        };
        window.app.graph.remove(other);
        return result;
      }, [clip, spare]);
      expect(facts.comfyClass, changed("node.comfyClass", "most of DiceForge/web")).toBe("DiceForgeCLIPDualTextEncode");
      expect(facts.module, changed("node.constructor.nodeData.python_module", "node_size.js")).toMatch(/DiceForge/i);
      expect(facts.methods, changed("these node methods", "most of DiceForge/web")).toEqual([]);
      expect(facts.margin, changed("a DOM widget's default margin (the classic canvas makes the element 2 × margin shorter)", "dom.js fitToContent")).toBe(10);
      expect(facts.layout, changed("computeLayoutSize of DOM widgets (fitToContent removes it so a panel doesn't take a share of a taller node)", "dom.js"))
        .toBe("function");
    });

    test("a panel sized by computeSize gets exactly that height", async ({ page }) => {
      const [image] = await addNodes(page, [{ type: "DiceForgeRandomImage" }]);
      await page.evaluate(() => new Promise((resolve) => {
        window.app.canvas.draw(true, true);
        requestAnimationFrame(() => requestAnimationFrame(resolve)); // The DOM widgets' boxes follow a frame later.
      }));
      const sizes = await page.evaluate((id) => {
        const widget = window.app.graph.getNodeById(id).widgets.find((item) => item.name === "image_preview");
        const row = widget.element.closest('[data-testid="node-widget"]');
        return { wanted: widget.computeSize()[1], computed: widget.computedHeight, box: widget.element.parentElement?.style.height, row: !!row,
          body: !!document.querySelector(`[data-node-id="${id}"] [data-testid^="node-body"]`) };
      }, image);
      if (vue) {
        expect(sizes.row && sizes.body, changed("the data-testid of a node's body and widget rows in Nodes 2.0", "e2e/qa/lib.js measure")).toBe(true);
      } else {
        expect(sizes.computed, changed("how the classic canvas sizes a widget with computeSize (its height + 4)", "dom.js fitToContent")).toBe(sizes.wanted + 4);
        expect(Number.parseFloat(sizes.box), changed("the height of a DOM widget's box in the classic canvas (computedHeight - 2 × margin)", "dom.js fitToContent"))
          .toBe(sizes.wanted + 4 - 20);
      }
    });

    test("prompt fields: a textarea in the node", async ({ page }) => {
      const [clip] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode" }]);
      const textareas = await page.evaluate((id) => {
        const widget = window.app.graph.getNodeById(id).widgets.find((item) => item.name === "positive");
        return { inputEl: widget.inputEl?.tagName ?? "", inNode: document.querySelectorAll(`[data-node-id="${id}"] textarea`).length };
      }, clip);
      if (vue) expect(textareas.inNode, changed("the prompt textareas inside [data-node-id] in Nodes 2.0", "prompt_highlight.js, tag_autocomplete.js, wildcards.js")).toBeGreaterThan(0);
      else expect(textareas.inputEl, changed("widget.inputEl of a text widget", "prompt_highlight.js, tag_autocomplete.js, wildcards.js")).toBe("TEXTAREA");
    });

    test("the node menu asks DiceForge for its entries (getNodeMenuItems)", async ({ page }) => {
      const [clip] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [200, 150] }]);
      const point = vue
        ? await page.locator(`[data-node-id="${clip}"] [data-testid^="node-header"]`).boundingBox().then((box) => ({ x: box.x + box.width / 2, y: box.y + box.height / 2 }))
        : await page.evaluate((id) => {
          const { app } = window, node = app.graph.getNodeById(id), { scale, offset } = app.canvas.ds, rect = app.canvas.canvas.getBoundingClientRect();
          return { x: rect.left + (node.pos[0] + 40 + offset[0]) * scale, y: rect.top + (node.pos[1] + 60 + offset[1]) * scale };
        }, clip);
      await page.mouse.click(point.x, point.y, { button: "right" });
      await expect(page.getByText("Prompt history").first(), changed("the node's right-click menu (getNodeMenuItems)", "prompt_preview.js, wildcards.js, sampler_presets.js"))
        .toBeVisible();
      await page.keyboard.press("Escape");
    });

    if (vue) {
      test("Show advanced inputs sets node.showAdvanced", async ({ page }) => {
        const [clip] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode" }]);
        await page.locator(`[data-node-id="${clip}"]`).getByText(/Show advanced inputs/).click();
        await expect.poll(() => page.evaluate((id) => window.app.graph.getNodeById(id).showAdvanced, clip),
          changed("node.showAdvanced (Show advanced inputs in Nodes 2.0)", "the e2e tests and screenshots")).toBe(true);
      });
    }
  });
}
