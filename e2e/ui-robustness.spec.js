// End-to-end robustness in the browser, in both node designs: workflows survive saving and loading without losing a value, damaged workflows
// open without breaking the page, copies of nodes are independent, failed runs leave the page working, the Wildcard Browser copes with an
// unreadable file, the autocomplete works with the mouse and in the negative prompt, and the resolution previews show exactly the size a run makes
// after any series of changes. Every test also fails on any error in the page (helpers.js).
const fs = require("fs");
const { test, expect, basePath, openComfy, addNodes, connect, widgetValue, setWidget, menuItems, clickMenu, queueFromPage, nodeElement } = require("./helpers");

const ALL_NODES = ["DiceForgeSDXLResolutionList", "DiceForgeResolutionSelector", "DiceForgeCLIPDualTextEncode", "DiceForgeWildcardsToText", "DiceForgeRandomInt", "DiceForgeRandomFloat",
  "DiceForgeRandomLora", "DiceForgeRandomCheckpoint", "DiceForgeRandomDiffusionModel", "DiceForgeRandomImage", "DiceForgeGrid", "DiceForgeRandomSampler",
  "DiceForgeRandomVAE", "DiceForgeLoadVAEDecodeSave", "DiceForgeVAEDecodeSave", "DiceForgeLoadDiffusionModelCLIP", "DiceForgeLoraStack", "DiceForgeXYPlot", "DiceForgeVariationSeed", "DiceForgeAnimaNAG", "DiceForgeHiresUpscale", "DiceForgeDanbooruEnhancer", "DiceForgeWildcardNote"];
const STACK = JSON.stringify({ rows: [{ lora: "style/ink.safetensors", strength: 0.7, random: true, min: 0.4, max: 0.9, group: "A", triggers: "custom", trigger_words: ["ink style"] },
  { lora: "detail.safetensors", strength: 1.2, on: false }], groups: { A: { min: 0, max: 1 } }, separate_clip: true });
// Values that differ from the defaults, so a value lost on the way shows.
const CHANGES = {
  DiceForgeSDXLResolutionList: { resolution: "High-Res", "resolution.size": "1152 x 1536", seed: 123456789, rescale: "to longest side", "rescale.longer_side": 2048, multiple: 64, batch: 3, seed_mode: "deck" },
  DiceForgeResolutionSelector: { aspect_ratio: "Random Chaos Portrait", megapixels: 2.3, seed: 42, multiple: 32, batch: 2, max_aspect: 3.5, seed_mode: "balanced", rescale: "to Width/Height", "rescale.width": 1200, "rescale.height": 0 },
  DiceForgeCLIPDualTextEncode: { positive: "портрет, {a|b} __color__ 🎲\nвторая строка", negative: "нет, ${x}", seed: 9007199254740991, seed_mode: "mutate", trim: false },
  DiceForgeRandomInt: { min: -50, max: 50, step: 5, seed: 7, seed_mode: "sequential" },
  DiceForgeRandomFloat: { min: -1.5, max: 2.25, step: 0.25, seed: 8, seed_mode: "shuffle", parts: 7 },
  DiceForgeRandomSampler: { samplers: "euler,\ndpmpp_2m", schedulers: "karras", seed: 11, seed_mode: "deck" },
  DiceForgeGrid: { count: 9, columns: 3, cell_width: 256, save: false, filename_prefix: "e2e/ui grid", name: "ui grid", legend: "легенда", legend_position: "bottom", numbered: true },
  DiceForgeLoraStack: { loras: STACK, seed: 99, seed_mode: "shuffle" },
  DiceForgeWildcardNote: { text: "строка, __color__\nsecond line", wildcard: "hair/style", mode: "replace file" },
};
const values = (page, id) => page.evaluate((id) => Object.fromEntries(window.app.graph.getNodeById(id).widgets
  .filter((widget) => !["preview_ratio", "preview_megapixels"].includes(widget.name) && widget.serialize !== false && widget.type !== "button")
  .map((widget) => [widget.name, widget.value ?? null])), id); // An empty list (no model files here) is undefined before saving, null after.
const reload = (page, workflow) => page.evaluate(async (workflow) => { window.app.graph.clear(); await window.app.loadGraphData(JSON.parse(workflow)); }, workflow);
const serialized = (page) => page.evaluate(() => JSON.stringify(window.app.graph.serialize()));
const nodeIds = (page) => page.evaluate(() => window.app.graph.nodes.map((node) => [node.id, node.comfyClass]));

// A seeded random number generator, so a failing series of changes can be run again.
function generator(seed) {
  let state = seed >>> 0;
  const next = () => { state = (state * 1664525 + 1013904223) >>> 0; return state / 2 ** 32; };
  return { pick: (list) => list[Math.floor(next() * list.length)], int: (low, high, step = 1) => low + step * Math.floor(next() * (Math.floor((high - low) / step) + 1)) };
}

for (const vue of [true, false]) {
  test.describe(vue ? "Nodes 2.0 robustness" : "classic robustness", () => {
    test.beforeEach(async ({ page }) => openComfy(page, { vue }));

    test("every DiceForge node keeps every value through save and load, twice", async ({ page }) => {
      const ids = await addNodes(page, ALL_NODES.map((type, index) => ({ type, pos: [40 + (index % 4) * 420, 40 + Math.floor(index / 4) * 460], widgets: CHANGES[type] ?? {} })));
      const before = {};
      for (const [index, id] of ids.entries()) before[ALL_NODES[index]] = await values(page, id);
      for (const [type, changes] of Object.entries(CHANGES)) for (const [name, value] of Object.entries(changes)) expect(before[type][name], `${type}.${name}`).toEqual(value);
      for (let round = 0; round < 2; round++) {
        await reload(page, await serialized(page));
        await page.waitForTimeout(500);
        for (const [id, type] of await nodeIds(page)) expect(await values(page, id), `${type}, round ${round + 1}`).toEqual(before[type]);
      }
      expect(JSON.parse(before.DiceForgeLoraStack.loras)).toEqual(JSON.parse(STACK));
    });

    test("damaged workflows open without breaking the page", async ({ page }) => {
      await addNodes(page, ALL_NODES.map((type, index) => ({ type, pos: [40 + (index % 4) * 420, 40 + Math.floor(index / 4) * 460] })));
      const good = JSON.parse(await serialized(page));
      const damages = [
        (values) => values.slice(0, 1), // Too few values.
        (values) => [...values, "extra", 5, null, { x: 1 }], // Too many.
        (values) => values.map(() => null),
        (values) => values.map((value) => (typeof value === "number" ? "not a number" : typeof value === "string" ? 12345 : value)),
        () => [],
        // Not a list at all ("not a list") is left out: ComfyUI's own loading stops on it for any node with an optional nested list.
      ];
      for (const [index, damage] of damages.entries()) {
        const workflow = structuredClone(good);
        for (const node of workflow.nodes) node.widgets_values = damage(node.widgets_values ?? []);
        await reload(page, JSON.stringify(workflow));
        await page.waitForTimeout(300);
        expect((await nodeIds(page)).length, `damage ${index}`).toBe(ALL_NODES.length);
        await expect(page.getByText("Loading aborted"), `damage ${index}`).toHaveCount(0);
      }
      for (const loras of ["{oops", "null", "[]", "5", '"text"', '{"rows": 5}', '{"rows": [null, 5, "x", {"lora": 5}, {"strength": 1}]}', '{"rows": [{"lora": "a"}], "groups": [1]}',
        '{"rows": [{"lora": "style/ink.safetensors", "trigger_words": "ink style", "min": "x", "group": {"a": 1}}]}']) {
        const workflow = structuredClone(good);
        const stack = workflow.nodes.find((node) => node.type === "DiceForgeLoraStack");
        stack.widgets_values[0] = loras;
        await reload(page, JSON.stringify(workflow));
        await expect(page.getByText("Loading aborted"), loras).toHaveCount(0);
        await expect(page.locator(".dfls").first().locator("button.add"), loras).toBeAttached();
        await page.locator(".dfls").first().locator("button.add").dispatchEvent("click"); // The panel still works: the browser opens.
        await expect(page.locator(".dflb")).toBeVisible();
        await page.keyboard.press("Escape");
      }
    });

    test("a copied node is independent of the original", async ({ page }) => {
      const [stack, encode] = await addNodes(page, [{ type: "DiceForgeLoraStack", widgets: { loras: STACK } }, { type: "DiceForgeCLIPDualTextEncode", pos: [500, 40], widgets: { positive: "original" } }]);
      await page.evaluate(([stack, encode]) => {
        const graph = window.app.graph;
        window.app.canvas.selectItems([graph.getNodeById(stack), graph.getNodeById(encode)]);
        window.app.canvas.copyToClipboard();
        window.app.canvas.graph_mouse = [100, 700];
        window.app.canvas.pasteFromClipboard();
      }, [stack, encode]);
      await page.waitForTimeout(500);
      const copies = await page.evaluate(([stack, encode]) => window.app.graph.nodes.filter((node) => ![stack, encode].includes(node.id)).map((node) => [node.id, node.comfyClass]), [stack, encode]);
      expect(copies.map(([, type]) => type).sort()).toEqual(["DiceForgeCLIPDualTextEncode", "DiceForgeLoraStack"]);
      const stackCopy = copies.find(([, type]) => type === "DiceForgeLoraStack")[0];
      const encodeCopy = copies.find(([, type]) => type === "DiceForgeCLIPDualTextEncode")[0];
      expect(await widgetValue(page, stackCopy, "loras")).toBe(STACK);
      await expect(page.locator(".dfls")).toHaveCount(2);
      // Removing a row in the copy's panel leaves the original alone.
      const copyPanel = page.locator(".dfls").nth(1);
      await copyPanel.locator(".row").first().locator("button", { hasText: "✕" }).click();
      await expect.poll(async () => JSON.parse(await widgetValue(page, stackCopy, "loras")).rows.length).toBe(1);
      expect(JSON.parse(await widgetValue(page, stack, "loras")).rows.length).toBe(2);
      await setWidget(page, encodeCopy, "positive", "copy");
      expect(await widgetValue(page, encode, "positive")).toBe("original");
    });

    test("after a failed run the page keeps working, and the fixed workflow runs", async ({ page, request }) => {
      const [encode, preview] = await addNodes(page, [
        { type: "DiceForgeCLIPDualTextEncode", widgets: { positive: "a __no_such_wildcard__ car" } },
        { type: "PreviewAny", pos: [500, 40] },
      ]);
      await connect(page, encode, 3, preview, 0);
      await queueFromPage(page, request);
      const failed = Object.values(await (await request.get("/history?max_items=1")).json())[0];
      expect(JSON.stringify(failed.status.messages)).toContain("Wildcard __no_such_wildcard__ not found");
      await setWidget(page, encode, "positive", "a {red|blue} car");
      await queueFromPage(page, request);
      const fixed = Object.values(await (await request.get("/history?max_items=1")).json())[0];
      expect(["a red car", "a blue car"]).toContain(fixed.outputs[String(preview)].text[0]);
    });

    test("the Wildcard Browser marks an unreadable file and still opens the others", async ({ page }) => {
      const file = basePath("models", "wildcards", `e2e_unreadable_${vue ? "vue" : "classic"}.txt`);
      fs.writeFileSync(file, Buffer.from([0xea, 0xf0, 0xe0, 0xf1, 0xed, 0xfb, 0xe9, 0x0a]));
      try {
        const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60] }]);
        await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
        const row = page.locator(".dfwc .row", { hasText: `e2e_unreadable_${vue ? "vue" : "classic"}` });
        await expect(row).toContainText("⚠");
        await expect(row).toHaveAttribute("title", /not UTF-8/);
        await row.locator(".name").click();
        await expect(page.locator(".dfwc .status")).toContainText("not UTF-8");
        await page.locator(".dfwc .tree > .row", { hasText: /^color/ }).locator(".name").click();
        await expect(page.locator(".dfwc .edit textarea")).toHaveValue(/red\nblue/);
        await page.keyboard.press("Escape");
      } finally {
        fs.rmSync(file, { force: true });
      }
    });

    test("the autocomplete works with the mouse, in the negative prompt, and closes when the field loses focus", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60] }]);
      await page.evaluate((id) => { const node = window.app.graph.getNodeById(id); node.showAdvanced = true; node.setDirtyCanvas(true, true); }, id);
      await page.waitForTimeout(500);
      await page.evaluate(([id]) => {
        const node = window.app.graph.getNodeById(id);
        const vue = document.querySelectorAll(`[data-node-id="${id}"] textarea`);
        const element = vue.length ? vue[1] : node.widgets.find((widget) => widget.name === "negative").inputEl;
        element.setAttribute("data-e2e", "negative");
      }, [id]);
      const negative = page.locator('[data-e2e="negative"]');
      const focusAtEnd = () => negative.evaluate((field) => { field.focus(); field.setSelectionRange(field.value.length, field.value.length); });
      await focusAtEnd();
      await page.keyboard.type("blurry, __hair/");
      await expect(page.locator(".dfwc-pop")).toContainText("__hair/style__");
      await page.locator(".dfwc-pop div", { hasText: "__hair/color__" }).dispatchEvent("mousedown");
      await expect.poll(() => widgetValue(page, id, "negative")).toBe("blurry, __hair/color__");
      await expect(page.locator(".dfwc-pop")).toHaveCount(0);
      await focusAtEnd();
      await page.keyboard.type(" __");
      await expect(page.locator(".dfwc-pop")).toBeVisible();
      await page.mouse.click(1500, 900); // Elsewhere on the canvas.
      await expect(page.locator(".dfwc-pop")).toHaveCount(0);
      await focusAtEnd();
      await page.keyboard.type("col");
      await expect(page.locator(".dfwc-pop div").first()).toContainText("__color__");
      await page.keyboard.press("ArrowDown");
      await page.keyboard.press("ArrowUp");
      await page.keyboard.press("Tab");
      await expect.poll(() => widgetValue(page, id, "negative")).toBe("blurry, __hair/color__ __color__");
    });

    test("after any series of changes, the resolution previews show exactly the size a run makes", async ({ page, request }) => {
      const [sdxl, selector, width1, height1, width2, height2] = await addNodes(page, [
        { type: "DiceForgeSDXLResolutionList" }, { type: "DiceForgeResolutionSelector", pos: [40, 520] },
        { type: "PreviewAny", pos: [600, 40] }, { type: "PreviewAny", pos: [600, 260] }, { type: "PreviewAny", pos: [600, 520] }, { type: "PreviewAny", pos: [600, 740] },
      ]);
      await connect(page, sdxl, 1, width1, 0);
      await connect(page, sdxl, 2, height1, 0);
      await connect(page, selector, 1, width2, 0);
      await connect(page, selector, 2, height2, 0);
      const options = (id, name) => page.evaluate(([id, name]) => window.app.graph.getNodeById(id).widgets.find((widget) => widget.name === name).options.values, [id, name]);
      const random = generator(vue ? 2024 : 4202);
      for (let round = 0; round < 5; round++) {
        for (let step = 0; step < 8; step++) { // A series of changes, in any order, before looking.
          const [id, fixedGroups] = random.pick([[sdxl, ["Standard", "High-Res"]], [selector, null]]);
          const change = random.pick(["group", "rescale", "value", "multiple", "megapixels"]);
          if (change === "group") {
            if (fixedGroups) {
              await setWidget(page, id, "resolution", random.pick(fixedGroups));
              await setWidget(page, id, "resolution.size", random.pick(await options(id, "resolution.size")));
            } else {
              await setWidget(page, id, "aspect_ratio", random.pick((await options(id, "aspect_ratio")).filter((name) => !name.startsWith("Random"))));
            }
          } else if (change === "rescale") {
            await setWidget(page, id, "rescale", random.pick(["by percentage", "to Width/Height", "to longest side"]));
          } else if (change === "multiple") {
            await setWidget(page, id, "multiple", random.int(8, 128, 8));
          } else if (change === "megapixels" && !fixedGroups) {
            await setWidget(page, id, "megapixels", random.int(3, 30) / 10);
          } else {
            const mode = await widgetValue(page, id, "rescale");
            if (mode === "by percentage") await setWidget(page, id, "rescale.percent", random.int(25, 250, 5));
            else if (mode === "to longest side") await setWidget(page, id, "rescale.longer_side", random.int(512, 3072, 8));
            else {
              await setWidget(page, id, "rescale.width", random.pick([0, random.int(512, 2560, 8)]));
              await setWidget(page, id, "rescale.height", random.pick([0, random.int(512, 2560, 8)]));
            }
          }
        }
        await queueFromPage(page, request);
        const history = Object.values(await (await request.get("/history?max_items=1")).json())[0];
        expect(history.status.status_str, JSON.stringify(history.status.messages).slice(0, 300)).toBe("success");
        const ran = [`${history.outputs[String(width1)].text[0]}:${history.outputs[String(height1)].text[0]}`, `${history.outputs[String(width2)].text[0]}:${history.outputs[String(height2)].text[0]}`];
        const settings = [await values(page, sdxl), await values(page, selector)];
        // The preview follows the inputs on a short timer: it settles on exactly the size the run made.
        await expect.poll(async () => [await widgetValue(page, sdxl, "preview_ratio"), await widgetValue(page, selector, "preview_ratio")],
          { message: `round ${round}: ${JSON.stringify(settings)}`, timeout: 3000 }).toEqual(ran);
      }
    });

    test("many DiceForge nodes at once stay responsive and save", async ({ page }) => {
      const started = Date.now();
      await addNodes(page, Array.from({ length: 64 }, (_, index) => ({ type: ALL_NODES[index % ALL_NODES.length], pos: [40 + (index % 8) * 420, 40 + Math.floor(index / 8) * 460] })));
      const workflow = await serialized(page);
      await reload(page, workflow);
      expect((await nodeIds(page)).length).toBe(64);
      expect(Date.now() - started).toBeLessThan(60_000);
    });
  });
}
