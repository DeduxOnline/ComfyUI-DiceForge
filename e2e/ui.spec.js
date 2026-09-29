// End-to-end in the browser: the DiceForge frontend extensions in the real ComfyUI page, in both node designs (Nodes 2.0 and classic), against the
// real server. Each test builds its own graph.
const fs = require("fs");
const { test, expect, basePath, writeFile, openComfy, addNodes, connect, widgetValue, setWidget, menuItems, clickMenu, queueFromPage, nodeElement } = require("./helpers");

const ALL_NODES = ["SDXLResolutionListLatent", "ResolutionSelectorRandomLatent", "CLIPTextEncodePositiveNegative", "DiceForgeRandomInt", "DiceForgeRandomFloat",
  "DiceForgeRandomLora", "DiceForgeRandomCheckpoint", "DiceForgeRandomDiffusionModel", "DiceForgeRandomImage", "DiceForgeGrid", "DiceForgeRandomSampler",
  "DiceForgeRandomVAE", "LoadVAEDecodeSave", "VAEDecodeSave", "LoadDiffusionModelCLIP", "DiceForgeLoraStack"];

// A prompt field of CLIP Dual Text Encode, marked so a locator finds it in either design (Nodes 2.0: the node's textareas in order; classic: the
// widget's own textarea).
async function promptField(page, id, name) {
  await page.evaluate(([id, name]) => {
    const node = window.app.graph.getNodeById(id);
    const vue = document.querySelectorAll(`[data-node-id="${id}"] textarea`);
    const element = vue.length ? vue[name === "positive" ? 0 : 1] : node.widgets.find((widget) => widget.name === name).inputEl;
    element.setAttribute("data-e2e", `${id}-${name}`);
  }, [id, name]);
  return page.locator(`[data-e2e="${id}-${name}"]`);
}
const lookUp = (request, kind, file) => request.get(`/diceforge/model-info?kind=${kind}&file=${encodeURIComponent(file)}`);
const cardTitles = (page) => page.$$eval(".dflb .card", (cards) => cards.map((card) => card.querySelector(".title").innerText + (card.querySelector(".base") ? ` [${card.querySelector(".base").innerText}]` : "")));

for (const vue of [true, false]) {
  test.describe(vue ? "Nodes 2.0" : "classic nodes", () => {
    test.beforeEach(async ({ page }) => openComfy(page, { vue }));

    test("every DiceForge node can be added", async ({ page }) => {
      const ids = await addNodes(page, ALL_NODES.map((type, index) => ({ type, pos: [40 + (index % 4) * 420, 40 + Math.floor(index / 4) * 420] })));
      const widgets = await page.evaluate((ids) => ids.map((id) => window.app.graph.getNodeById(id)?.widgets?.length ?? -1), ids);
      expect(widgets.every((count) => count > 0)).toBe(true);
      if (vue) await expect(nodeElement(page, ids[0])).toBeVisible();
    });

    test("SDXL Resolution List previews fixed sizes live and random sizes after a run", async ({ page, request }) => {
      const [id, preview] = await addNodes(page, [{ type: "SDXLResolutionListLatent", widgets: { "resolution.size": "1216 x 832" } }, { type: "PreviewAny", pos: [500, 40] }]);
      await connect(page, id, 1, preview, 0); // An output, so the workflow can run.
      await expect.poll(() => widgetValue(page, id, "preview_ratio")).toBe("1216:832");
      await setWidget(page, id, "scale", 1.5); // scale sides by: 1216 x 832 becomes 1824 x 1248.
      await expect.poll(() => widgetValue(page, id, "preview_ratio")).toBe("1824:1248");
      await setWidget(page, id, "scale", 1.0);
      await setWidget(page, id, "resolution", "Random");
      await expect.poll(() => widgetValue(page, id, "preview_ratio")).toBe(""); // Not run yet: "—".
      await queueFromPage(page, request);
      await expect.poll(() => widgetValue(page, id, "preview_ratio")).toMatch(/^\d+:\d+$/);
      if (vue) await expect(nodeElement(page, id)).toContainText("×");
    });

    test("typing __ in CLIP Dual Text Encode suggests wildcards", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60] }]);
      const positive = await promptField(page, id, "positive");
      await positive.click();
      await page.keyboard.type("1girl, __hair/st");
      await expect(page.locator(".dfwc-pop")).toContainText("__hair/style__");
      await page.keyboard.press("Enter");
      await expect.poll(() => widgetValue(page, id, "positive")).toBe("1girl, __hair/style__");
      await expect(page.locator(".dfwc-pop")).toHaveCount(0);
      await page.keyboard.type(", __col");
      await expect(page.locator(".dfwc-pop div").first()).toContainText("__color__");
      await page.keyboard.press("Escape");
      await expect(page.locator(".dfwc-pop")).toHaveCount(0);
    });

    test("Wildcard Browser adds wildcards to the prompt and edits files", async ({ page }) => {
      writeFile(`models/wildcards/edit_${vue ? "vue" : "classic"}.txt`, "one\ntwo\n");
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60], widgets: { positive: "1girl" } }]);
      expect(await menuItems(page, id, "DiceForge.Wildcards")).toEqual(["🎲 Wildcard Browser"]);
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      await expect(page.locator(".dfwc .row").first()).toBeVisible();
      await page.locator(".dfwc .tree > .row", { hasText: /^color/ }).locator("button.add").click(); // color.txt at the top, not hair/color.txt.
      await page.locator(".dfwc .folder > .row", { hasText: "hair" }).first().locator("button.add").click();
      await expect.poll(() => widgetValue(page, id, "positive")).toBe("1girl, __color__, __hair/*__");
      const file = `edit_${vue ? "vue" : "classic"}`; // A file of its own: the tests share the server's files.
      await page.locator(".dfwc .row", { hasText: file }).locator(".name").click();
      await expect(page.locator(".dfwc .edit textarea")).toHaveValue("one\ntwo");
      await page.locator(".dfwc .edit textarea").fill("one\ntwo\n2::three");
      await page.locator(".dfwc button", { hasText: "Save" }).click();
      await expect(page.locator(".dfwc .status")).toContainText(`Saved ${file}.txt`);
      expect(fs.readFileSync(basePath("models", "wildcards", `${file}.txt`), "utf8")).toBe("one\ntwo\n2::three\n");
      await page.keyboard.press("Escape");
      await expect(page.locator(".dfwc")).toHaveCount(0);
    });

    test("Model info shows what Civitai knows and keeps your notes", async ({ page, request }) => {
      const [id] = await addNodes(page, [{ type: "LoraLoader", widgets: { lora_name: "style/ink.safetensors" } }]);
      const items = await menuItems(page, id, "DiceForge.ModelInfo");
      expect(items).toEqual(["🛈 Model info: ink.safetensors"]);
      await clickMenu(page, id, "DiceForge.ModelInfo", "Model info");
      await expect(page.locator(".dfmi h2")).toHaveText("Ink - v2");
      await expect(page.locator(".dfmi")).toContainText("Illustrious");
      await expect(page.locator(".dfmi .words")).toContainText("ink style");
      await page.locator('.dfmi textarea[placeholder^="Steps"]').fill("28 steps, CFG 5");
      await expect.poll(async () => (await (await lookUp(request, "loras", "style/ink.safetensors")).json()).user?.settings).toBe("28 steps, CFG 5");
      await page.keyboard.press("Escape");
      await expect(page.locator(".dfmi")).toHaveCount(0);
    });

    test("LoRA Browser picks LoRAs and looks them up on Civitai", async ({ page }) => {
      const [loader, random] = await addNodes(page, [{ type: "LoraLoader" }, { type: "DiceForgeRandomLora", pos: [500, 40] }]);
      await clickMenu(page, loader, "DiceForge.ModelBrowser", "LoRA Browser");
      await expect(page.locator(".dflb h2")).toHaveText("LoRA Browser");
      const flux = page.locator(".dflb .card", { hasText: "flux_film" });
      await flux.locator("button", { hasText: /^(🔍|↻) Civitai$/ }).click();
      await expect(page.locator(".dflb .card", { hasText: "Film - v1" })).toContainText("Flux.1 D");
      await expect(page.locator(".dflb .card", { hasText: "detail" }).locator("button", { hasText: "In use" })).toBeDisabled(); // Load LoRA's first file.
      await expect(page.locator(".dflb .card", { hasText: "detail" }).locator("img")).toHaveJSProperty("naturalWidth", 8); // The preview next to the file.
      await page.locator(".dflb .card", { hasText: "ink" }).locator("button", { hasText: /^Use$/ }).click();
      await expect.poll(() => widgetValue(page, loader, "lora_name")).toMatch(/style[\\/]ink\.safetensors/);
      await page.keyboard.press("Escape");
      await clickMenu(page, random, "DiceForge.ModelBrowser", "LoRA Browser");
      await page.locator(".dflb .tree .row", { hasText: "style" }).locator("button", { hasText: "Use folder" }).click();
      await expect.poll(() => widgetValue(page, random, "folder")).toBe("style");
      await page.keyboard.press("Escape");
    });

    test("Checkpoint Browser puts a checkpoint in Load Checkpoint", async ({ page }) => {
      const [loader] = await addNodes(page, [{ type: "CheckpointLoaderSimple" }]);
      expect(await menuItems(page, loader, "DiceForge.ModelBrowser")).toEqual(["🗃️ Checkpoint Browser"]);
      await clickMenu(page, loader, "DiceForge.ModelBrowser", "Checkpoint Browser");
      await expect(page.locator(".dflb .tree")).toContainText("sdxl");
      await page.locator(".dflb .card", { hasText: "other" }).locator("button", { hasText: /^Use$/ }).click();
      await expect.poll(() => widgetValue(page, loader, "ckpt_name")).toMatch(/sdxl[\\/]other\.safetensors/);
      await page.keyboard.press("Escape");
    });

    test("LoRA Stack: rows, random strength, groups, trigger words, base check and presets", async ({ page, request }) => {
      for (const file of ["style/ink.safetensors", "style/pony_glow.safetensors", "style/flux_film.safetensors"]) await lookUp(request, "loras", file);
      await lookUp(request, "checkpoints", "illustrious_base.safetensors");
      const [checkpoint, stack, other] = await addNodes(page, [
        { type: "CheckpointLoaderSimple", widgets: { ckpt_name: "illustrious_base.safetensors" } },
        { type: "DiceForgeLoraStack", pos: [460, 40] },
        { type: "DiceForgeLoraStack", pos: [460, 560] },
      ]);
      await connect(page, checkpoint, 0, stack, "model");
      const panel = page.locator(".dfls").first();
      await expect(panel.locator(".model")).toContainText("Illustrious", { timeout: 20_000 });
      // Adding from the browser, which starts on the LoRAs that fit the model.
      await panel.locator("button.add").click();
      await expect(page.locator(".dflb select").first()).toHaveValue(/fits/);
      const fitting = await cardTitles(page);
      expect(fitting.join()).not.toContain("Film");
      expect(fitting).toEqual(expect.arrayContaining(["Ink - v2 [Illustrious]", "Glow - v1 [⚠️ Pony]", "detail"]));
      await page.locator(".dflb select").first().selectOption("");
      for (const name of ["Ink", "Glow", "Film"]) await page.locator(".dflb .card", { hasText: name }).locator("button", { hasText: "+ Add" }).click();
      await page.keyboard.press("Escape");
      await expect(panel.locator(".row .name")).toHaveText(["ink", "pony_glow", "flux_film"]);
      await expect(panel.locator(".row").nth(0)).not.toHaveClass(/warn|bad/);
      await expect(panel.locator(".row").nth(1)).toHaveClass(/warn/);
      await expect(panel.locator(".row").nth(2)).toHaveClass(/bad/);
      // Random strength, a group, trigger words.
      await panel.locator(".row").nth(0).locator("button", { hasText: "🎲" }).click();
      await panel.locator(".row").nth(1).locator("select").selectOption("A");
      await panel.locator(".row").nth(2).locator("select").selectOption("A");
      await expect(panel.locator(".group")).toContainText("Group A:");
      await panel.locator(".row").nth(0).locator("button", { hasText: "🏷" }).click();
      await page.locator(".dflt label", { hasText: "lineart" }).locator("input").uncheck();
      await page.keyboard.press("Escape");
      await expect(panel.locator(".row").nth(0).locator("button", { hasText: "🏷" })).toHaveText("🏷1");
      const rows = JSON.parse(await widgetValue(page, stack, "loras")).rows;
      expect(rows.map((row) => [row.lora.replace(/\\/g, "/"), !!row.random, row.group ?? ""])).toEqual([["style/ink.safetensors", true, ""], ["style/pony_glow.safetensors", false, "A"], ["style/flux_film.safetensors", false, "A"]]);
      expect(rows[0]).toMatchObject({ triggers: "custom", trigger_words: ["ink style"] });
      // Presets: save from this stack, apply in the other one.
      page.once("dialog", (dialog) => dialog.accept(`e2e preset ${vue ? "vue" : "classic"}`));
      await panel.locator("button", { hasText: "Save preset" }).click();
      await expect(panel).toContainText("Saved the preset");
      await page.locator(".dfls").nth(1).locator("button", { hasText: "Presets" }).click();
      await page.locator(".dflp .item", { hasText: `e2e preset ${vue ? "vue" : "classic"}` }).locator("button", { hasText: "Replace" }).click();
      await expect(page.locator(".dfls").nth(1).locator(".row .name")).toHaveText(["ink", "pony_glow", "flux_film"]);
      expect(JSON.parse(await widgetValue(page, other, "loras")).rows[0].trigger_words).toEqual(["ink style"]);
      // The rows come back with a saved workflow.
      const workflow = await page.evaluate(() => window.app.graph.serialize());
      await page.evaluate(async (workflow) => { window.app.graph.clear(); await window.app.loadGraphData(workflow); }, workflow);
      await expect(page.locator(".dfls").first().locator(".row .name")).toHaveText(["ink", "pony_glow", "flux_film"]);
    });

    test("a workflow queued from the page fills in the prompt", async ({ page, request }) => {
      const [encode, preview] = await addNodes(page, [
        { type: "CLIPTextEncodePositiveNegative", widgets: { positive: "a __color__ car, {2$$__characters/*/outfit__}", seed: 3 } },
        { type: "PreviewAny", pos: [500, 40] },
      ]);
      await connect(page, encode, 2, preview, 0);
      await queueFromPage(page, request);
      const history = Object.values(await (await request.get("/history?max_items=1")).json())[0];
      const text = history.outputs[String(preview)].text[0];
      expect(text).toMatch(/^a (red|blue|green|white) car, [a-z ]+, [a-z ]+$/);
    });

    if (vue) {
      test("DiceForge nodes fit their inputs when advanced inputs are shown and hidden", async ({ page }) => {
        const [id] = await addNodes(page, [{ type: "SDXLResolutionListLatent" }]);
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
