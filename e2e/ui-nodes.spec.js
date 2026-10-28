// End-to-end in the browser, the nodes: adding every DiceForge node, the resolution previews, Dice Grid, XY Plot, KSampler presets,
// Random Image and node heights, in both node designs (Nodes 2.0 and classic), against the real server. Each test builds its own graph.
const fs = require("fs");
const { test, expect, basePath, openComfy, drawn, addNodes, connect, widgetValue, setWidget, menuItems, clickMenu, queueFromPage, nodeElement, answerQuestions } = require("./helpers");
const { ALL_NODES, lookUp, submenu, clickSubmenu } = require("./ui-shared");
const { measure, reloadTall } = require("./qa/lib");

for (const vue of [true, false]) {
  test.describe(vue ? "Nodes 2.0" : "classic nodes", () => {
    test.beforeEach(async ({ page }) => openComfy(page, { vue }));

    test("every DiceForge node can be added", async ({ page }) => {
      const ids = await addNodes(page, ALL_NODES.map((type, index) => ({ type, pos: [40 + (index % 4) * 420, 40 + Math.floor(index / 4) * 420] })));
      const widgets = await page.evaluate((ids) => ids.map((id) => window.app.graph.getNodeById(id)?.widgets?.length ?? -1), ids);
      expect(widgets.every((count) => count > 0)).toBe(true);
      if (vue) await expect(nodeElement(page, ids[0])).toBeVisible();
    });

    test("every DiceForge node fits what it shows: no empty area, nothing cut off, also from a workflow saved too tall", async ({ page }) => { // NOSONAR: expect.poll(...) below.
      const ids = await addNodes(page, ALL_NODES.map((type, index) => ({ type, pos: [40 + (index % 4) * 520, 40 + Math.floor(index / 4) * 700] })));
      const problems = async () => {
        const found = [];
        for (const [index, id] of ids.entries()) found.push(...(await measure(page, id)).problems.map((problem) => `${ALL_NODES[index]}: ${problem}`));
        return found;
      };
      await expect.poll(problems).toEqual([]); // The checks of the tester's tools (qa/lib.js): previews, lists and the node itself.
      await reloadTall(page, 900);
      await expect.poll(problems).toEqual([]);
    });

    test("SDXL Resolution List previews fixed sizes live and random sizes after a run", async ({ page, request }) => {
      const [id, preview] = await addNodes(page, [{ type: "DiceForgeSDXLResolutionList", widgets: { "resolution.size": "1216 x 832" } }, { type: "PreviewAny", pos: [500, 40] }]);
      await connect(page, id, 1, preview, 0); // An output, so the workflow can run.
      await expect.poll(() => widgetValue(page, id, "preview_ratio")).toBe("1216:832");
      await setWidget(page, id, "rescale.percent", 150); // Each side: 1216 x 832 becomes 1824 x 1248.
      await expect.poll(() => widgetValue(page, id, "preview_ratio")).toBe("1824:1248");
      await setWidget(page, id, "rescale", "to longest side");
      await expect.poll(() => widgetValue(page, id, "preview_ratio")).toBe("1536:1048"); // longer_side 1536 by default.
      await setWidget(page, id, "rescale", "to Width/Height");
      await setWidget(page, id, "rescale.width", 1920);
      await setWidget(page, id, "rescale.height", 1080);
      await expect.poll(() => widgetValue(page, id, "preview_ratio")).toBe("1920:1080");
      await setWidget(page, id, "rescale", "by percentage");
      await setWidget(page, id, "resolution", "Random");
      await expect.poll(() => widgetValue(page, id, "preview_ratio")).toBe(""); // Not run yet: "—".
      await queueFromPage(page, request);
      await expect.poll(() => widgetValue(page, id, "preview_ratio")).toMatch(/^\d+:\d+$/);
      if (vue) await expect(nodeElement(page, id)).toContainText("×");
    });

    test("Resolution Selector previews its size with rescale", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "DiceForgeResolutionSelector", widgets: { aspect_ratio: "16:9 (Widescreen)" } }]);
      await expect.poll(() => widgetValue(page, id, "preview_ratio")).toBe("1368:768");
      await setWidget(page, id, "rescale.percent", 150);
      await expect.poll(() => widgetValue(page, id, "preview_ratio")).toBe("2048:1152");
      await setWidget(page, id, "rescale", "to longest side");
      await setWidget(page, id, "rescale.longer_side", 1920);
      await expect.poll(() => widgetValue(page, id, "preview_ratio")).toBe("1920:1080");
      if (vue) await expect(nodeElement(page, id)).toContainText("1920 × 1080");
    });

    test("Dice Grid's cells panel: star the best cells, save them at full size with their workflow, open a cell's run", async ({ page, request }) => {
      const [image, grid] = await addNodes(page, [
        { type: "EmptyImage", widgets: { width: 96, height: 64 } },
        { type: "DiceForgeGrid", pos: [460, 40], widgets: { count: 0, cell_width: 64, save: false, name: `cells-${vue}` } },
      ]);
      await connect(page, image, 0, grid, "image");
      // Pure colors: the Nodes 2.0 color picker (frontend 1.55) rounds others on their way through it (4000000 becomes 3999744).
      for (const color of [0x000000, 0xff0000, 0x0000ff]) {
        await setWidget(page, image, "color", color);
        await queueFromPage(page, request);
      }
      const panel = page.locator(".dfdg").first();
      await expect(panel.locator(".cell")).toHaveCount(3);
      await expect(panel.locator("button.save")).toBeDisabled();
      await panel.locator(".cell").nth(1).click();
      await expect(panel.locator(".cell.kept")).toHaveCount(1);
      await expect(panel.locator(".title")).toHaveText("3 cells · 1 kept");
      await panel.locator("button.save").click();
      await expect(panel.locator(".status")).toContainText("Saved 1 in output: DiceForge/kept/kept_");
      const kept = fs.readdirSync(basePath("output", "DiceForge", "kept"));
      expect(kept.length).toBeGreaterThan(0);
      const saved = fs.readFileSync(basePath("output", "DiceForge", "kept", kept.sort().at(-1)));
      expect(saved.includes(Buffer.from("workflow"))).toBe(true); // The run's workflow is in the PNG.
      // ↺ opens that run's workflow, as dropping its image would: the run's two nodes, with that run's color.
      await answerQuestions(page, undefined, 1);
      await panel.locator(".cell").nth(1).locator("button.open").click();
      // The graph already has these two nodes: wait for the opened run's color (the graph before it had the last run's, 0x0000ff).
      const color = () => page.evaluate(() => window.app.graph.nodes.find((node) => node.comfyClass === "EmptyImage")?.widgets.find((widget) => widget.name === "color").value);
      await expect.poll(color).toBe(0xff0000);
      expect(await page.evaluate(() => window.app.graph.nodes.map((node) => node.comfyClass).sort().join())).toBe("DiceForgeGrid,EmptyImage");
    });

    test("XY Plot keeps one row about the plot, and Run with the batch count from its menu makes every cell into Dice Grid", async ({ page, request }) => {
      const [xy, image, grid] = await addNodes(page, [
        { type: "DiceForgeXYPlot", widgets: { x_type: "steps", x_values: "10, 20", y_type: "scheduler", y_values: "normal, karras", seed: 123 } },
        { type: "EmptyImage", pos: [460, 40], widgets: { width: 64, height: 64 } },
        { type: "DiceForgeGrid", pos: [860, 40], widgets: { count: 4, cell_width: 64, name: `xy-ui-${vue}`, filename_prefix: `e2e/xyui${vue ? "v" : "c"}` } },
      ]);
      await connect(page, image, 0, grid, "image");
      await connect(page, xy, 8, grid, "label");
      await connect(page, xy, 9, grid, "row_label");
      const row = page.locator(".dfxy").first();
      const extension = "DiceForge.XYPlot";
      await expect(row).toHaveText("2 × 2 = 4 cells · next: 10 steps, normal");
      await setWidget(page, xy, "index", 3);
      await expect(row).toHaveText("2 × 2 = 4 cells · next: 20 steps, karras");
      await setWidget(page, xy, "x_values", "10, x");
      await expect(row.locator(".error")).toContainText("not a number");
      await expect.poll(() => menuItems(page, xy, extension)).toEqual(["▦ Show the plot plan…"]); // Nothing to run.
      await setWidget(page, xy, "x_values", "10, 20");
      await expect(row).toHaveText("2 × 2 = 4 cells · next: 20 steps, karras");
      expect(await menuItems(page, xy, extension)).toEqual(["▶ Set Run to 4 cells, from index 0", "▦ Show the plot plan…"]);
      await clickMenu(page, xy, extension, "Set Run");
      expect(await widgetValue(page, xy, "index")).toBe(0);
      expect(await widgetValue(page, xy, "control_after_generate")).toBe("increment");
      expect(await page.evaluate(() => window.app.extensionManager.queueSettings.batchCount)).toBe(4);
      try {
        await page.evaluate(() => window.app.queuePrompt(0, window.app.extensionManager.queueSettings.batchCount)); // As the Run button does.
      } finally {
        await page.evaluate(() => { window.app.extensionManager.queueSettings.batchCount = 1; });
      }
      expect(await widgetValue(page, xy, "index")).toBe(4); // Counted up after each run: the next one is the first cell again.
      await expect(row).toHaveText("2 × 2 = 4 cells · next: 10 steps, normal");
      expect(await widgetValue(page, xy, "seed")).toBe(123); // The same seed for every cell: XY Plot's seed has no control after generate.
      const folder = basePath("output", "e2e");
      await expect.poll(() => fs.existsSync(folder) && fs.readdirSync(folder).some((name) => name.startsWith(`xyui${vue ? "v" : "c"}_`)), { timeout: 60_000 }).toBe(true);
      const queue = async () => { const body = await (await request.get("/queue")).json(); return body.queue_running.length + body.queue_pending.length; };
      await expect.poll(queue, { timeout: 60_000 }).toBe(0);
      await clickMenu(page, xy, extension, "plot plan");
      const plan = page.locator(".dfxyp");
      await expect(plan.locator("th")).toHaveText(["scheduler \\ steps", "10 steps", "20 steps", "normal", "karras"]);
      await expect(plan.locator("td.next")).toHaveText("0");
      await page.keyboard.press("Escape");
      await expect(plan).toHaveCount(0);
    });

    test("KSampler presets: the right-click submenu, Auto from the checkpoint's base model, saving and deleting your own", async ({ page, request }) => {
      await lookUp(request, "checkpoints", "illustrious_base.safetensors");
      const [checkpoint, sampler] = await addNodes(page, [
        { type: "CheckpointLoaderSimple", widgets: { ckpt_name: "illustrious_base.safetensors" } },
        { type: "KSampler", pos: [460, 200] },
      ]);
      expect(await menuItems(page, sampler, "DiceForge.SamplerPresets")).toEqual(["🎲 Sampler presets"]);
      expect(await menuItems(page, checkpoint, "DiceForge.SamplerPresets")).toEqual([]);
      const values = () => Promise.all(["steps", "cfg", "sampler_name", "scheduler"].map((name) => widgetValue(page, sampler, name)));
      // The real right-click menu: the submenu lists the built-in presets.
      if (vue) {
        await nodeElement(page, sampler).locator(".lg-node-header, [data-testid='node-title']").first().click({ button: "right" });
      } else {
        const point = await page.evaluate((id) => {
          const canvas = window.app.canvas, node = window.app.graph.getNodeById(id), box = canvas.canvas.getBoundingClientRect();
          const [x, y] = canvas.ds.convertCanvasToOffset([node.pos[0] + 60, node.pos[1] + 40]);
          return { x: box.left + x, y: box.top + y };
        }, sampler);
        await page.mouse.click(point.x, point.y, { button: "right" });
      }
      await page.getByText("Sampler presets").first()[vue ? "hover" : "click"](); // Nodes 2.0 opens submenus on hover, the classic menu on click.
      await page.getByText(/Illustrious · 28 steps/).first().click();
      await expect.poll(values).toEqual([28, 6, "euler_ancestral", "normal"]);
      // Auto: the connected checkpoint is Illustrious on Civitai; with nothing connected it says so and changes nothing.
      await setWidget(page, sampler, "steps", 7);
      await page.evaluate(() => window.app.extensionManager.toast.removeAll?.());
      await clickSubmenu(page, sampler, "Auto");
      await expect(page.getByText(/connected to the model input/).first()).toBeVisible();
      expect((await values())[0]).toBe(7);
      await connect(page, checkpoint, 0, sampler, 0);
      await clickSubmenu(page, sampler, "NoobAI (v-pred)");
      await expect.poll(values).toEqual([30, 4.5, "euler", "normal"]);
      await clickSubmenu(page, sampler, "Auto");
      await expect.poll(values).toEqual([28, 6, "euler_ancestral", "normal"]);
      // Your own: saved from the node's values, then in the menu, then deleted.
      await setWidget(page, sampler, "steps", 21);
      await setWidget(page, sampler, "scheduler", "karras");
      await answerQuestions(page, ({ prompt }) => (prompt ? "E2E mine" : true));
      await clickSubmenu(page, sampler, "Save current");
      await expect.poll(async () => (await (await request.get("/diceforge/sampler-presets")).json()).user.map((item) => item.name)).toContain("E2E mine");
      await expect.poll(() => submenu(page, sampler)).toContain("★ E2E mine · 21 steps · CFG 6");
      await setWidget(page, sampler, "steps", 5);
      await clickSubmenu(page, sampler, "★ E2E mine");
      await expect.poll(values).toEqual([21, 6, "euler_ancestral", "karras"]);
      await clickSubmenu(page, sampler, "🗑 Delete E2E mine");
      await expect.poll(() => submenu(page, sampler)).not.toContain("★ E2E mine · 21 steps · CFG 6");
      expect((await (await request.get("/diceforge/sampler-presets")).json()).user).toEqual([]);
    });

    test("Random Image shows the picked image, its file and seed, also from the cache and after a reload", async ({ page, request }) => {
      const [image, name] = await addNodes(page, [
        { type: "DiceForgeRandomImage", widgets: { folder: "e2e", seed: 1, control_after_generate: "fixed", seed_mode: "sequential" } },
        { type: "PreviewAny", pos: [500, 40] },
      ]);
      await connect(page, image, 2, name, 0);
      const panel = page.locator(".dfip").first();
      await expect(panel).toContainText("Run the workflow to see the picked image here.");
      await queueFromPage(page, request);
      const history = Object.values(await (await request.get("/history?max_items=1")).json())[0];
      const file = history.outputs[String(name)].text[0]; // e2e/red.png or e2e/blue.png, by the seed.
      await expect(panel.locator(".file")).toHaveText(file);
      await expect(panel.locator(".head")).toHaveText("Last run · seed 1 (sequential)");
      await expect(panel.locator(".size")).toHaveText(file.endsWith("red.png") ? "32 × 16 · input/e2e" : "16 × 24 · input/e2e");
      await expect(panel.locator("img")).toHaveJSProperty("naturalWidth", file.endsWith("red.png") ? 32 : 16); // From the input folder.
      await page.evaluate((id) => { delete window.app.graph.getNodeById(id).properties.dice_forge_image; }, image);
      await expect(panel).toContainText("Run the workflow");
      await queueFromPage(page, request); // The same inputs: the node comes from ComfyUI's cache, and still shows its pick.
      await expect(panel.locator(".file")).toHaveText(file);
      const workflow = await page.evaluate(() => window.app.graph.serialize());
      await page.evaluate(async (data) => { window.app.graph.clear(); await window.app.loadGraphData(data); }, workflow);
      await expect(page.locator(".dfip").first().locator(".file")).toHaveText(file); // Kept with the workflow.
      await expect(page.locator(".dfip").first().locator("img")).toHaveJSProperty("naturalWidth", file.endsWith("red.png") ? 32 : 16);
    });

    test("a node saved taller than it shows is fitted again, unless a text field takes the extra height", async ({ page }) => { // NOSONAR: expect.poll(...) below.
      const [plain, sampler, image, clip] = await addNodes(page, [{ type: "DiceForgeRandomInt" }, { type: "DiceForgeRandomSampler", pos: [400, 40] },
        { type: "DiceForgeRandomImage", pos: [800, 40] }, { type: "DiceForgeCLIPDualTextEncode", pos: [1200, 40] }]);
      const workflow = await page.evaluate(() => window.app.graph.serialize());
      for (const node of workflow.nodes) { // As a workflow saved with an empty gap under the inputs, before the fitted height was kept.
        node.size = [node.size[0], 900];
        delete node.properties.dice_forge_height;
      }
      await page.evaluate(async (data) => { window.app.graph.clear(); await window.app.loadGraphData(data); }, workflow);
      const stored = (id) => page.evaluate((id) => window.app.graph.getNodeById(id).size[1], id);
      await expect.poll(() => stored(plain)).toBeLessThan(300); // Nothing takes the extra height: it goes.
      await expect.poll(() => stored(image)).toBeLessThan(400); // Its preview is as tall as what it shows, not as the node was.
      expect(await stored(sampler)).toBe(900); // Its samplers and schedulers fields grow with it: the user's height stays.
      expect(await stored(clip)).toBe(900); // Its prompt fields take the extra height.
    });

    test("a node the user made taller keeps its height, also after a reload and when its panel is fitted", async ({ page }) => { // NOSONAR: expect.poll(...) below.
      const [plain, image, fitted] = await addNodes(page, [{ type: "DiceForgeRandomInt" }, { type: "DiceForgeRandomImage", pos: [400, 40] },
        { type: "DiceForgeRandomInt", pos: [800, 40] }]);
      const stored = (id) => page.evaluate((id) => window.app.graph.getNodeById(id).size[1], id);
      await expect.poll(() => page.evaluate((id) => window.app.graph.getNodeById(id).properties.dice_forge_height, plain)).toBeGreaterThan(0);
      await page.evaluate((ids) => { // As a drag of the corner: the frontend sets the size.
        for (const id of ids) { const node = window.app.graph.getNodeById(id); node.setSize([node.size[0], 700]); }
      }, [plain, image]);
      await page.evaluate((id) => window.app.graph.getNodeById(id).onExecuted({ dice_forge_image: [{ seed: 1, seed_mode: "random" }] }), image);
      const workflow = await page.evaluate(() => window.app.graph.serialize());
      await page.evaluate(async (data) => { window.app.graph.clear(); await window.app.loadGraphData(data); }, workflow);
      await drawn(page);
      await expect.poll(() => stored(fitted)).toBeLessThan(300); // Not resized: fitted as before.
      expect(await stored(plain)).toBe(700);
      expect(await stored(image)).toBe(700); // Its preview asked for its own height: the user's stays.
      if (vue) await expect.poll(async () => (await nodeElement(page, plain).boundingBox()).height).toBeGreaterThan(500); // Drawn that tall too.
    });

    test("bypassed, the model nodes pass the model and the CLIP on: LoRA Stack, Random LoRA, Variation Seed, Anima NAG", async ({ page }) => {
      const [checkpoint, stack, lora, variation, nag, sampler, encode] = await addNodes(page, [
        { type: "CheckpointLoaderSimple" },
        { type: "DiceForgeLoraStack", pos: [420, 40] },
        { type: "DiceForgeRandomLora", pos: [820, 40] },
        { type: "DiceForgeVariationSeed", pos: [1220, 40] },
        { type: "DiceForgeAnimaNAG", pos: [1620, 40] },
        { type: "KSampler", pos: [2020, 40] },
        { type: "CLIPTextEncode", pos: [1220, 520] },
      ]);
      const inputs = (bypass) => page.evaluate(async ([ids, bypass]) => {
        const node = (id) => window.app.graph.getNodeById(id);
        const link = (from, slot, to, input) => node(from).connect(slot, node(to), node(to).findInputSlot(input));
        if (!bypass) { // Linked once, by input name: widget inputs have slots too.
          const [checkpoint, stack, lora, variation, nag, sampler, encode] = ids;
          link(checkpoint, 0, stack, "model");
          link(checkpoint, 1, stack, "clip");
          link(stack, 0, lora, "model");
          link(stack, 1, lora, "clip");
          link(lora, 0, variation, "model");
          link(variation, 0, nag, "model");
          link(nag, 0, sampler, "model");
          link(lora, 1, encode, "clip");
        }
        for (const id of ids.slice(1, 5)) node(id).mode = bypass ? 4 : 0;
        const { output } = await window.app.graphToPrompt();
        return { model: output[ids[5]].inputs.model, clip: output[ids[6]].inputs.clip, left: ids.slice(1, 5).filter((id) => String(id) in output).length };
      }, [[checkpoint, stack, lora, variation, nag, sampler, encode], bypass]);
      expect(await inputs(false)).toEqual({ model: [String(nag), 0], clip: [String(lora), 1], left: 4 });
      expect(await inputs(true)).toEqual({ model: [String(checkpoint), 0], clip: [String(checkpoint), 1], left: 0 }); // Straight from the checkpoint.
    });

    if (vue) {
      test("DiceForge nodes fit their inputs when advanced inputs are shown and hidden", async ({ page }) => { // NOSONAR: expect.poll(...) assertions below.
        const [id] = await addNodes(page, [{ type: "DiceForgeSDXLResolutionList" }]);
        const height = async () => (await nodeElement(page, id).boundingBox()).height;
        await expect.poll(async () => page.evaluate((id) => window.app.graph.getNodeById(id).size[1], id)).toBeLessThan(100);
        const before = await height();
        await nodeElement(page, id).getByText(/Show advanced/).click();
        await expect.poll(height).toBeGreaterThan(before + 40);
        await nodeElement(page, id).getByText(/Hide advanced/).click();
        await expect.poll(height).toBeLessThan(before + 2);
      });
    }
  });
}
