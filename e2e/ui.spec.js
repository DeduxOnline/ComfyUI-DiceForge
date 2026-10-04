// End-to-end in the browser: the DiceForge frontend extensions in the real ComfyUI page, in both node designs (Nodes 2.0 and classic), against the
// real server. Each test builds its own graph.
const fs = require("fs");
const { test, expect, basePath, writeFile, openComfy, addNodes, connect, widgetValue, setWidget, menuItems, clickMenu, queueFromPage, nodeElement } = require("./helpers");
const { DOWNLOADS } = require("./fixtures");

const ALL_NODES = ["SDXLResolutionListLatent", "ResolutionSelectorRandomLatent", "CLIPTextEncodePositiveNegative", "DiceForgeRandomInt", "DiceForgeRandomFloat",
  "DiceForgeRandomLora", "DiceForgeRandomCheckpoint", "DiceForgeRandomDiffusionModel", "DiceForgeRandomImage", "DiceForgeGrid", "DiceForgeRandomSampler",
  "DiceForgeRandomVAE", "LoadVAEDecodeSave", "VAEDecodeSave", "LoadDiffusionModelCLIP", "DiceForgeLoraStack", "DiceForgeXYPlot", "DiceForgeVariationSeed", "DiceForgeHiresUpscale", "DiceForgeDanbooruEnhancer"];

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
// The entries of the Sampler presets submenu, and clicking one of them (as the right-click menu does).
const submenu = (page, id) => page.evaluate((id) => window.app.extensions.find((item) => item.name === "DiceForge.SamplerPresets")
  .getNodeMenuItems(window.app.graph.getNodeById(id))[0].submenu.options.filter(Boolean).map((item) => item.content), id);
const clickSubmenu = (page, id, content) => page.evaluate(([id, content]) => window.app.extensions.find((item) => item.name === "DiceForge.SamplerPresets")
  .getNodeMenuItems(window.app.graph.getNodeById(id))[0].submenu.options.find((item) => item?.content.includes(content)).callback(), [id, content]);

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

    test("an SDXL Resolution List saved with the old scale number opens as rescale by percentage", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "SDXLResolutionListLatent", widgets: { "resolution.size": "1216 x 832", multiple: 16, batch: 2, seed_mode: "deck" } }]);
      await setWidget(page, id, "rescale.percent", 150);
      const workflow = await page.evaluate(() => window.app.graph.serialize());
      const saved = workflow.nodes.find((node) => node.type === "SDXLResolutionListLatent");
      const at = saved.widgets_values.indexOf("by percentage");
      expect(saved.widgets_values.slice(at, at + 2)).toEqual(["by percentage", 150]);
      saved.widgets_values.splice(at, 2, 1.5); // How the previous version saved it: a scale number (each side 1.5x).
      await page.evaluate(async (workflow) => { window.app.graph.clear(); await window.app.loadGraphData(workflow); }, workflow);
      const node = await page.evaluate(() => window.app.graph.nodes.find((node) => node.comfyClass === "SDXLResolutionListLatent").id);
      await expect.poll(() => widgetValue(page, node, "rescale")).toBe("by percentage");
      await expect.poll(() => widgetValue(page, node, "rescale.percent")).toBe(150);
      expect([await widgetValue(page, node, "multiple"), await widgetValue(page, node, "batch"), await widgetValue(page, node, "seed_mode")]).toEqual([16, 2, "deck"]);
      await expect.poll(() => widgetValue(page, node, "preview_ratio")).toBe("1824:1248");
    });

    test("Resolution Selector previews its size with rescale", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "ResolutionSelectorRandomLatent", widgets: { aspect_ratio: "16:9 (Widescreen)" } }]);
      await expect.poll(() => widgetValue(page, id, "preview_ratio")).toBe("1368:768");
      await setWidget(page, id, "rescale.percent", 150);
      await expect.poll(() => widgetValue(page, id, "preview_ratio")).toBe("2048:1152");
      await setWidget(page, id, "rescale", "to longest side");
      await setWidget(page, id, "rescale.longer_side", 1920);
      await expect.poll(() => widgetValue(page, id, "preview_ratio")).toBe("1920:1080");
      if (vue) await expect(nodeElement(page, id)).toContainText("1920 × 1080");
    });

    test("a Resolution Selector saved before rescale opens at 100% with its values in place", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "ResolutionSelectorRandomLatent", widgets: { aspect_ratio: "4:3 (Standard)", megapixels: 2.0, multiple: 64, batch: 3, seed_mode: "deck" } }]);
      const workflow = await page.evaluate(() => window.app.graph.serialize());
      const saved = workflow.nodes.find((node) => node.type === "ResolutionSelectorRandomLatent");
      const at = saved.widgets_values.indexOf("by percentage");
      saved.widgets_values.splice(at, 2); // How a version without rescale saved it.
      await page.evaluate(async (workflow) => { window.app.graph.clear(); await window.app.loadGraphData(workflow); }, workflow);
      const node = await page.evaluate(() => window.app.graph.nodes.find((node) => node.comfyClass === "ResolutionSelectorRandomLatent").id);
      await expect.poll(() => widgetValue(page, node, "rescale")).toBe("by percentage");
      await expect.poll(() => widgetValue(page, node, "rescale.percent")).toBe(100);
      const values = await Promise.all(["aspect_ratio", "megapixels", "multiple", "batch", "seed_mode"].map((name) => widgetValue(page, node, name)));
      expect(values).toEqual(["4:3 (Standard)", 2.0, 64, 3, "deck"]);
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
      await positive.fill("");
      await page.keyboard.type("__цв"); // Not only Latin letters.
      await expect(page.locator(".dfwc-pop div").first()).toContainText("__цвет__");
      await page.keyboard.press("Enter");
      await expect.poll(() => widgetValue(page, id, "positive")).toBe("__цвет__");
      await page.keyboard.type(", <lora:in"); // LoRA files after <lora:
      await expect(page.locator(".dfwc-pop div").first()).toContainText("style/ink");
      await page.keyboard.press("Enter");
      await expect.poll(() => widgetValue(page, id, "positive")).toBe("__цвет__, <lora:style/ink:1>");
    });

    test("autocomplete follows the text as typed while the wildcard list loads slowly", async ({ page }) => {
      let requests = 0;
      await page.route("**/diceforge/wildcards", async (route) => {
        const delay = [900, 300, 50][Math.min(requests++, 2)]; // Later requests answer sooner: answers come back out of order.
        await new Promise((resolve) => setTimeout(resolve, delay));
        await route.continue();
      });
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60] }]);
      const positive = await promptField(page, id, "positive");
      await positive.click();
      await page.keyboard.type("__hair/st");
      await page.waitForTimeout(1500); // Every answer is in.
      await expect(page.locator(".dfwc-pop div").first()).toContainText("__hair/style__");
      await page.keyboard.press("Enter");
      await expect.poll(() => widgetValue(page, id, "positive")).toBe("__hair/style__");
      expect(requests).toBe(1); // One shared request, not one per keystroke.
    });

    test("the prompt fields highlight the syntax, with missing wildcards in red", async ({ page }) => {
      const prompt = "${g={male|female}}a __color__ {2$$3::!hat|__nope__|bow} \\{x\\} (smile:1.2) ${g} // note\n/* block */ embedding:easy";
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", widgets: { positive: prompt } }]);
      const field = await promptField(page, id, "positive");
      const layer = field.locator("xpath=preceding-sibling::div[contains(concat(' ', @class, ' '), ' dfhl ')][1]");
      await expect(layer).toHaveCount(1);
      const marked = async (kind) => layer.locator(`span.${kind}`).allTextContents();
      await expect.poll(() => marked("wc")).toEqual(["__color__"]);
      expect(await marked("wc-missing")).toEqual(["__nope__"]); // No wildcard file nope.txt.
      expect(await marked("count")).toEqual(["2$$"]);
      expect(await marked("weight")).toEqual(["3::"]);
      expect(await marked("lock")).toEqual(["!"]);
      expect(await marked("var")).toEqual(["${g=", "}", "${g}"]);
      expect(await marked("b0")).toEqual(["{", "|", "|", "}"]); // A choice at the top.
      expect(await marked("b1")).toEqual(["{", "|", "}"]); // One inside ${g=...}: one level down, another color.
      expect(await marked("esc")).toEqual(["\\{", "\\}"]);
      expect(await marked("attn")).toEqual([":1.2"]);
      expect(await marked("comment")).toEqual(["// note", "/* block */"]);
      expect(await marked("embed")).toEqual(["embedding:easy"]);
      expect(await layer.textContent()).toBe(`${prompt}\n`); // The same text, only colored.
      await expect(field).toHaveAttribute("title", "No wildcard file for __nope__");
      expect(await field.evaluate((element) => getComputedStyle(element).webkitTextFillColor)).toBe("rgba(0, 0, 0, 0)"); // The field shows the layer.
      const [box, inner] = [await field.boundingBox(), await layer.boundingBox()];
      expect(Math.abs(box.x - inner.x)).toBeLessThan(3);
      expect(Math.abs(box.width - inner.width)).toBeLessThan(20); // Inside the field's border, without its scrollbar.
      await field.click();
      await page.keyboard.press("ControlOrMeta+a");
      await page.keyboard.type("{a|{b|c}} {unclosed");
      await expect.poll(() => marked("b1")).toEqual(["{", "|", "}"]); // Nested: another color.
      expect(await marked("bad")).toEqual(["{"]); // Never closed.
      await expect(field).not.toHaveAttribute("title", /No wildcard/);
      await page.evaluate(() => window.app.extensionManager.setting.set("DiceForge.PromptHighlight", false));
      await expect(layer).toHaveCount(0); // Off: the plain field again.
      expect(await field.evaluate((element) => element.classList.contains("dfhl-input"))).toBe(false);
      await page.evaluate(() => window.app.extensionManager.setting.set("DiceForge.PromptHighlight", true));
      await expect(field.locator("xpath=preceding-sibling::div[contains(concat(' ', @class, ' '), ' dfhl ')][1]")).toHaveCount(1);
    });

    test("Wildcard Browser adds wildcards to the prompt and edits files", async ({ page }) => {
      writeFile(`models/wildcards/edit_${vue ? "vue" : "classic"}.txt`, "one\ntwo\n");
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60], widgets: { positive: "1girl" } }]);
      expect(await menuItems(page, id, "DiceForge.Wildcards")).toEqual(["📖 Syntax guide", "🎲 Wildcard Browser"]);
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      await expect(page.locator(".dfwc .row").first()).toBeVisible();
      await page.locator(".dfwc .tree > .row", { hasText: /^color/ }).locator("button.add").click(); // color.txt at the top, not hair/color.txt.
      await page.locator(".dfwc .folder > .row", { hasText: "hair" }).first().locator("button.add").click();
      await expect.poll(() => widgetValue(page, id, "positive")).toBe("1girl, __color__, __hair/*__");
      const file = `edit_${vue ? "vue" : "classic"}`; // A file of its own: the tests share the server's files.
      await page.locator(".dfwc .row", { hasText: file }).locator(".name").click();
      await expect(page.locator(".dfwc .edit textarea")).toHaveValue("one\ntwo");
      const numbers = () => page.locator(".dfwc .code .lines").evaluate((gutter) => gutter.textContent);
      await expect.poll(numbers).toBe("1\n2"); // A line number next to each line.
      await page.locator(".dfwc .edit textarea").fill("one\ntwo\n2::three");
      await expect.poll(numbers).toBe("1\n2\n3"); // Numbered again as you type.
      await expect(page.locator(".dfwc .code .hl .weight")).toHaveText("2::"); // The syntax colored, as in the prompt fields: the line's weight.
      const currentLine = () => page.locator(".dfwc .code").evaluate((code) => code.style.getPropertyValue("--current-line"));
      await expect.poll(currentLine).toBe("46px"); // The caret's line (the third, after typing) is highlighted.
      await page.locator(".dfwc .edit textarea").press("Control+Home");
      await expect.poll(currentLine).toBe("6px"); // And follows the caret.
      await page.locator(".dfwc button", { hasText: "Save" }).click();
      await expect(page.locator(".dfwc .status")).toContainText(`Saved ${file}.txt`);
      expect(fs.readFileSync(basePath("models", "wildcards", `${file}.txt`), "utf8")).toBe("one\ntwo\n2::three\n");
      await page.keyboard.press("Escape");
      await expect(page.locator(".dfwc")).toHaveCount(0);
    });

    test("Wildcard Browser folders open and close, and stay so", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60] }]);
      await page.evaluate(() => localStorage.removeItem("diceforge.wildcards.open"));
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      const hair = page.locator('.dfwc .folder[data-path="hair"]');
      const style = hair.locator(".row", { hasText: "style" });
      await expect(hair).not.toHaveClass(/open/); // Folders start closed.
      await expect(style).toBeHidden();
      await hair.locator("> .row .name").click();
      await expect(style).toBeVisible();
      await page.keyboard.press("Escape");
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      await expect(style).toBeVisible(); // Still open when the browser opens again.
      await page.locator(".dfwc button.close-all").click();
      await expect(style).toBeHidden();
      await page.locator(".dfwc .top input").first().fill("sty"); // A search shows the matches in their folders.
      await expect(style).toBeVisible();
      await page.locator(".dfwc .top input").first().fill("");
      await expect(style).toBeHidden();
      await page.locator(".dfwc button.open-all").click();
      await expect(page.locator('.dfwc .folder[data-path="characters/alice"] .row', { hasText: "outfit" })).toBeVisible();
      await page.locator(".dfwc button.close-all").click();
      await page.keyboard.press("Escape");
    });

    test("Wildcard Browser moves files: Move picks a folder, a file dropped on a folder moves there", async ({ page }) => {
      const top = `wmove_${vue ? "vue" : "classic"}`, wildcards = (...parts) => basePath("models", "wildcards", ...parts);
      writeFile(`models/wildcards/${top}/from/x.txt`, "one\ntwo\n");
      writeFile(`models/wildcards/${top}/to/y.txt`, "y\n");
      try {
        const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60] }]);
        await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
        await page.locator(".dfwc button.open-all").click();
        await page.locator(`.dfwc .row[data-name="${top}/from/x"] .name`).click();
        await page.locator(".dfwc .edit textarea").fill("one\ntwo\nthree"); // Unsaved: stays in the editor through the move.
        await page.locator(".dfwc button.move").click();
        await page.locator(`.dfmv .item[data-folder="${top}/to"]`).click();
        await expect(page.locator(".dfwc .status")).toContainText(`Moved ${top}/from/x to ${top}/to/x`);
        await expect(page.locator(".dfwc .edit textarea")).toHaveValue("one\ntwo\nthree");
        await expect(page.locator(".dfwc button.save")).toHaveText("Save •");
        expect(fs.readFileSync(wildcards(top, "to", "x.txt"), "utf8")).toBe("one\ntwo\n");
        expect(fs.existsSync(wildcards(top, "from"))).toBe(false);
        await page.locator(`.dfwc .row[data-name="${top}/to/y"]`).dragTo(page.locator(`.dfwc .folder[data-path="${top}"] > .row`));
        await expect(page.locator(".dfwc .status")).toContainText(`Moved ${top}/to/y to ${top}/y`);
        expect(fs.existsSync(wildcards(top, "y.txt"))).toBe(true);
        await page.locator(".dfwc button.move").click();
        await page.keyboard.press("Escape"); // Cancels the picker only.
        await expect(page.locator(".dfmv")).toHaveCount(0);
        await expect(page.locator(".dfwc")).toHaveCount(1);
        await page.locator(".dfwc button.close-all").click();
        await page.keyboard.press("Escape");
      } finally {
        fs.rmSync(wildcards(top), { recursive: true, force: true });
      }
    });

    test("Wildcard Browser favorites: ☆ stars a file, ★ Favorites shows only them, the autocomplete puts them first", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60] }]);
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      await page.locator(".dfwc button.open-all").click();
      const style = page.locator('.dfwc .row[data-name="hair/style"]');
      await style.locator("button.fav").click();
      await expect(style.locator("button.fav")).toHaveText("★");
      await page.locator(".dfwc button.close-all").click();
      await page.locator(".dfwc button.only-favorites").click(); // Only favorites, in open folders.
      await expect(page.locator(".dfwc .tree .row[data-name]")).toHaveCount(1);
      await expect(style).toBeVisible();
      await page.locator(".dfwc button.only-favorites").click();
      await expect(page.locator('.dfwc .row[data-name="color"]')).toBeVisible();
      await page.keyboard.press("Escape");
      const field = await promptField(page, id, "positive");
      await field.click();
      await page.keyboard.type("__hair/");
      await expect(page.locator(".dfwc-pop div").first()).toHaveText("★ __hair/style__2"); // Before hair/color, though c comes before s.
      await page.keyboard.press("Escape");
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      await page.locator(".dfwc button.only-favorites").click();
      await page.locator('.dfwc .row[data-name="hair/style"] button.fav').click(); // Unstarred: the favorites list is empty.
      await expect(page.locator(".dfwc .tree")).toContainText("No favorites yet");
      await page.keyboard.press("Escape");
    });

    test("Wildcard Browser creates, renames and deletes files", async ({ page }) => {
      const tag = vue ? "vue" : "classic", wildcards = (...parts) => basePath("models", "wildcards", ...parts);
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60] }]);
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      const answers = [`crud_${tag}/new`, `crud_${tag}/new`, `crud_${tag}_done/renamed`]; // The prompts in order: new file, the same name again, rename.
      page.on("dialog", (dialog) => (dialog.type() === "confirm" ? dialog.accept() : dialog.accept(answers.shift())));
      const editor = page.locator(".dfwc .edit textarea"), save = page.locator(".dfwc button.save"), status = page.locator(".dfwc .status");
      await page.locator(".dfwc button", { hasText: "+ New file" }).click();
      await expect(page.locator(".dfwc .row.sel")).toContainText("new");
      await editor.fill("alpha\nbeta");
      await expect(save).toHaveText("Save •"); // Unsaved changes are marked...
      await editor.press("Control+s");
      await expect(status).toContainText(`Saved crud_${tag}/new.txt`);
      await expect(save).toHaveText("Save"); // ...until saved (Ctrl+S here).
      expect(fs.readFileSync(wildcards(`crud_${tag}`, "new.txt"), "utf8")).toBe("alpha\nbeta\n");
      await page.locator(".dfwc button", { hasText: "+ New file" }).click(); // A taken name: refused, the file keeps its lines.
      await expect(status).toContainText("already exists");
      expect(fs.readFileSync(wildcards(`crud_${tag}`, "new.txt"), "utf8")).toBe("alpha\nbeta\n");
      await page.locator(".dfwc button.rename").click();
      await expect(status).toContainText(`Renamed crud_${tag}/new to crud_${tag}_done/renamed`);
      await expect(page.locator(".dfwc .row.sel")).toContainText("renamed");
      await expect(editor).toHaveValue("alpha\nbeta");
      expect(fs.existsSync(wildcards(`crud_${tag}`))).toBe(false);
      await page.locator(".dfwc button.delete").click();
      await expect(status).toContainText(`Deleted crud_${tag}_done/renamed.txt`);
      expect(fs.existsSync(wildcards(`crud_${tag}_done`))).toBe(false);
      await expect(page.locator(".dfwc .row", { hasText: `crud_${tag}` })).toHaveCount(0);
      await expect(page.locator(".dfwc button.delete")).toBeDisabled();
      await page.locator(".dfwc button.open-all").click(); // The yaml wildcards are in closed folders.
      await page.locator(".dfwc .row", { hasText: "outfit" }).filter({ hasText: "yaml" }).first().locator(".name").click(); // yaml: read-only.
      await expect(page.locator(".dfwc button.rename")).toBeDisabled();
      await expect(page.locator(".dfwc button.delete")).toBeDisabled();
    });

    test("Model info shows what Civitai knows and keeps your notes", async ({ page, request }) => {
      const [id] = await addNodes(page, [{ type: "LoraLoader", widgets: { lora_name: "style/ink.safetensors" } }]);
      const items = await menuItems(page, id, "DiceForge.ModelInfo");
      expect(items).toEqual(["🛈 Model info: ink.safetensors"]);
      await clickMenu(page, id, "DiceForge.ModelInfo", "Model info");
      await expect(page.locator(".dfmi h2")).toHaveText("Ink - v2");
      await expect(page.locator(".dfmi")).toContainText("Illustrious");
      await expect(page.locator(".dfmi .words")).toContainText("ink style");
      // Civitai's images one at a time, with how each was made over it on hover.
      const stage = page.locator(".dfmi .stage");
      await expect(page.locator(".dfmi .count")).toHaveText("1 / 2");
      await expect(stage.locator("img")).toHaveCount(1);
      await expect(stage.locator("img")).toHaveJSProperty("naturalWidth", 8);
      await expect(stage.locator(".meta")).toHaveCSS("opacity", "0");
      await stage.hover();
      await expect(stage.locator(".meta")).toHaveCSS("opacity", "1");
      await expect(stage.locator(".meta")).toContainText("seed3032258275");
      await expect(stage.locator(".meta")).toContainText("cfg4");
      await expect(stage.locator(".meta")).toContainText("samplerEuler a");
      await expect(stage.locator(".meta .prompt").first()).toContainText("Ink test prompt, 1girl");
      await expect(stage.locator(".meta a.chip")).toHaveAttribute("href", /civitai\.com\/images\/70\d/);
      await page.locator(".dfmi button.next").click();
      await expect(page.locator(".dfmi .count")).toHaveText("2 / 2");
      await expect(stage.locator(".meta")).toContainText("Civitai has no generation data for this image.");
      await page.locator('.dfmi textarea[placeholder^="Steps"]').click();
      await page.keyboard.press("ArrowRight"); // In a text field the arrow keys move the cursor, not the images.
      await expect(page.locator(".dfmi .count")).toHaveText("2 / 2");
      await page.locator(".dfmi h2").click();
      await page.keyboard.press("ArrowRight");
      await expect(page.locator(".dfmi .count")).toHaveText("1 / 2"); // Around to the first.
      await page.locator('.dfmi textarea[placeholder^="Steps"]').fill("28 steps, CFG 5");
      await expect.poll(async () => (await (await lookUp(request, "loras", "style/ink.safetensors")).json()).user?.settings).toBe("28 steps, CFG 5");
      await page.keyboard.press("Escape");
      await expect(page.locator(".dfmi")).toHaveCount(0);
    });

    test("Previews: R-rated ones blurred unless Blur NSFW is off (a switch in the browsers), videos wait for ▶", async ({ page }) => {
      const [loader] = await addNodes(page, [{ type: "LoraLoader" }]);
      await clickMenu(page, loader, "DiceForge.ModelBrowser", "LoRA Browser");
      const toggle = page.locator(".dflb .dfblur-switch input");
      await expect(toggle).toBeChecked(); // On by default.
      const probe = () => page.evaluate(async () => { // The module the page loaded (the same instance, by its URL).
        const url = performance.getEntriesByType("resource").map((entry) => entry.name).find((name) => name.endsWith("/media.js"));
        const { civitaiMedia } = await import(url);
        const picture = civitaiMedia("/nothing.png", { nsfwLevel: 5 });
        const safe = civitaiMedia("/nothing.png", { nsfwLevel: 1 });
        const video = civitaiMedia("/nothing.mp4", { nsfwLevel: 1, type: "video" });
        return { blurred: picture.media.classList.contains("blur"), safe: safe.media.classList.contains("blur"), autoplay: video.media.autoplay,
          paused: video.media.paused, play: !!video.wrapper.querySelector("button.play") };
      });
      expect(await probe()).toEqual({ blurred: true, safe: false, autoplay: false, paused: true, play: true });
      await toggle.uncheck();
      await expect.poll(() => page.evaluate(() => window.app.extensionManager.setting.get("DiceForge.BlurNSFW"))).toBe(false);
      expect((await probe()).blurred).toBe(false); // Off: shown as they are.
      await toggle.check();
      await expect.poll(() => page.evaluate(() => window.app.extensionManager.setting.get("DiceForge.BlurNSFW"))).toBe(true);
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

    test("LoRA Browser folders open and close, and stay so", async ({ page }) => {
      const top = `tree_${vue ? "vue" : "classic"}`;
      for (const file of ["a/one", "a/deep/two", "b/three"]) writeFile(`models/loras/${top}/${file}.safetensors`, `${top} ${file}`);
      try {
        await page.evaluate(() => localStorage.removeItem("diceforge.browser.loras.open"));
        const [loader, random] = await addNodes(page, [{ type: "LoraLoader" }, { type: "DiceForgeRandomLora", pos: [500, 40] }]);
        await clickMenu(page, loader, "DiceForge.ModelBrowser", "LoRA Browser");
        const row = (path) => page.locator(`.dflb .tree .row[data-path="${path}"]`);
        await expect(row(top)).toBeVisible();
        await expect(row(`${top}/a`)).toHaveCount(0); // Subfolders start closed.
        await row(top).locator(".twist").click();
        await expect(row(`${top}/a`)).toBeVisible();
        await expect(row(`${top}/a/deep`)).toHaveCount(0);
        await expect(page.locator(".dflb .tree .row.sel")).toContainText(`All LoRAs`); // ▸ opens without picking the folder.
        await row(`${top}/a`).locator(".name").click(); // Picking a folder shows its LoRAs (subfolders included).
        await expect(page.locator(".dflb .card")).toHaveCount(2);
        await page.keyboard.press("Escape");
        await clickMenu(page, loader, "DiceForge.ModelBrowser", "LoRA Browser");
        await expect(row(`${top}/a`)).toBeVisible(); // Still open when the browser opens again.
        await page.locator(".dflb .tree button.open-all").click();
        await expect(row(`${top}/a/deep`)).toBeVisible();
        await page.locator(".dflb .tree button.close-all").click();
        await expect(row(`${top}/a`)).toHaveCount(0);
        await page.keyboard.press("Escape");
        await page.evaluate(([id, value]) => { // A Random LoRA set to a deep folder: the tree opens to it.
          const widget = window.app.graph.getNodeById(id).widgets.find((entry) => entry.name === "folder");
          widget.options.values.push(value);
          widget.value = value;
        }, [random, `${top}/a/deep`]);
        await clickMenu(page, random, "DiceForge.ModelBrowser", "LoRA Browser");
        await expect(row(`${top}/a/deep`).locator("button", { hasText: "In use" })).toBeVisible();
        await page.locator(".dflb .tree button.close-all").click();
        await page.keyboard.press("Escape");
      } finally {
        fs.rmSync(basePath("models", "loras", top), { recursive: true, force: true });
      }
    });

    test("LoRA Browser moves LoRAs: Move picks a folder, a card dropped on a folder moves there", async ({ page }) => {
      const top = `move_${vue ? "vue" : "classic"}`, loras = (...parts) => basePath("models", "loras", ...parts);
      writeFile(`models/loras/${top}/a/one.safetensors`, `${top} one`);
      writeFile(`models/loras/${top}/b/two.safetensors`, `${top} two`);
      try {
        const [loader] = await addNodes(page, [{ type: "LoraLoader" }]);
        await clickMenu(page, loader, "DiceForge.ModelBrowser", "LoRA Browser");
        await page.locator(".dflb .card", { hasText: "one.safetensors" }).locator("button.move").click();
        const picker = page.locator(".dfmv");
        await expect(picker.locator(`.item[data-folder="${top}/a"]`)).toHaveClass(/here/); // Where it is now.
        await picker.locator(`.item[data-folder="${top}/b"]`).click();
        await expect(page.locator(".dflb .status")).toContainText(`Moved ${top}/a/one.safetensors to ${top}/b/one.safetensors`);
        expect(fs.existsSync(loras(top, "b", "one.safetensors")) && !fs.existsSync(loras(top, "a"))).toBe(true); // The empty folder went too.
        await page.locator(".dflb .card", { hasText: "one.safetensors" }).locator("button.move").click();
        await picker.locator("input").fill(`${top}/new place`); // A new folder.
        await picker.locator("input").press("Enter");
        await expect(page.locator(".dflb .status")).toContainText(`to ${top}/new place/one.safetensors`);
        await page.locator(".dflb .card", { hasText: "two.safetensors" }).dragTo(page.locator(`.dflb .tree .row[data-path="${top}"]`));
        await expect(page.locator(".dflb .status")).toContainText(`Moved ${top}/b/two.safetensors to ${top}/two.safetensors`);
        expect(fs.existsSync(loras(top, "two.safetensors"))).toBe(true);
        await page.locator(".dflb .card", { hasText: "two.safetensors" }).locator("button.move").click();
        await page.keyboard.press("Escape"); // Cancels the picker only.
        await expect(picker).toHaveCount(0);
        await expect(page.locator(".dflb")).toHaveCount(1);
        await page.keyboard.press("Escape");
      } finally {
        fs.rmSync(loras(top), { recursive: true, force: true });
      }
    });

    test("LoRA Browser favorites: ☆ stars a LoRA, ★ Favorites shows only them, and they stay", async ({ page }) => {
      const [loader] = await addNodes(page, [{ type: "LoraLoader" }]);
      await clickMenu(page, loader, "DiceForge.ModelBrowser", "LoRA Browser");
      const ink = page.locator(".dflb .card", { hasText: "ink.safetensors" });
      await expect(page.locator(`.dflb .tree .row.favs`)).toContainText("★ Favorites0");
      await ink.locator(".fav").click();
      await expect(ink.locator(".fav")).toHaveText("★");
      await page.locator(".dflb .tree .row.favs").click();
      await expect(page.locator(".dflb .card")).toHaveCount(1);
      await expect(page.locator(".dflb .card")).toContainText("ink.safetensors");
      await page.keyboard.press("Escape");
      await clickMenu(page, loader, "DiceForge.ModelBrowser", "LoRA Browser"); // Kept on the server.
      await expect(page.locator(".dflb .tree .row.favs")).toContainText("★ Favorites1");
      await page.locator(".dflb .card", { hasText: "ink.safetensors" }).locator(".fav").click();
      await expect(page.locator(".dflb .tree .row.favs")).toContainText("★ Favorites0");
      await page.keyboard.press("Escape");
    });

    test("LoRA Browser batch actions: pick cards, then star, move and delete them all", async ({ page }) => {
      const top = `batch_${vue ? "vue" : "classic"}`, loras = (...parts) => basePath("models", "loras", ...parts);
      for (const name of ["batchy_a", "batchy_b", "batchy_c"]) writeFile(`models/loras/${top}/${name}.safetensors`, `${top} ${name}`);
      try {
        const [loader] = await addNodes(page, [{ type: "LoraLoader" }]);
        await clickMenu(page, loader, "DiceForge.ModelBrowser", "LoRA Browser");
        const card = (name) => page.locator(".dflb .card", { hasText: `${name}.safetensors` });
        const bar = page.locator(".dflb .batch");
        await expect(bar).toBeHidden();
        await card("batchy_a").locator(".title").click({ modifiers: ["ControlOrMeta"] });
        await expect(bar.locator(".count")).toHaveText("1 LoRA picked");
        await card("batchy_c").locator(".title").click({ modifiers: ["Shift"] }); // A range: a, b and c.
        await expect(bar.locator(".count")).toHaveText("3 LoRAs picked");
        await expect(page.locator(".dflb .card.picked")).toHaveCount(3);
        await card("batchy_b").locator(".title").click(); // A plain click (not in Select mode) picks nothing.
        await expect(bar.locator(".count")).toHaveText("3 LoRAs picked");
        await bar.locator(".batch-star").click();
        await expect(page.locator(".dflb .status")).toContainText("Starred 3 LoRAs.");
        await expect(page.locator(".dflb .tree .row.favs")).toContainText("★ Favorites3");
        await bar.locator(".batch-move").click();
        await page.locator(".dfmv input").fill(`${top}/moved`);
        await page.locator(".dfmv input").press("Enter");
        await expect(page.locator(".dflb .status")).toContainText(`Moved to ${top}/moved: 3 LoRAs.`);
        expect(fs.readdirSync(loras(top, "moved")).sort()).toEqual(["batchy_a.safetensors", "batchy_b.safetensors", "batchy_c.safetensors"]);
        await expect(bar).toBeHidden(); // The moved files are let go.
        await card("batchy_a").locator(".title").click({ modifiers: ["ControlOrMeta"] });
        await card("batchy_b").locator(".title").click({ modifiers: ["ControlOrMeta"] });
        await card("batchy_a").dragTo(page.locator(`.dflb .tree .row[data-path="${top}"]`)); // Dragging a picked card takes the picked ones along.
        await expect(page.locator(".dflb .status")).toContainText(`Moved to ${top}: 2 LoRAs.`);
        expect(fs.readdirSync(loras(top)).sort()).toEqual(["batchy_a.safetensors", "batchy_b.safetensors", "moved"]);
        await page.locator(".dflb button.select-mode").click(); // Select mode: plain clicks pick.
        await card("batchy_a").locator(".title").click();
        await card("batchy_b").locator(".title").click();
        await expect(bar.locator(".count")).toHaveText("2 LoRAs picked");
        await page.keyboard.press("Escape"); // The first Escape lets go of the picks, the browser stays.
        await expect(bar).toBeHidden();
        await expect(page.locator(".dflb")).toHaveCount(1);
        await page.locator(".dflb .top input").first().fill("batchy");
        await card("batchy_a").locator(".title").click();
        await bar.locator(".pick-all").click(); // Every card shown by the search.
        await expect(bar.locator(".count")).toHaveText("3 LoRAs picked");
        page.once("dialog", (dialog) => dialog.accept());
        await bar.locator(".batch-delete").click();
        await expect(page.locator(".dflb .status")).toContainText("Deleted 3 LoRAs.");
        expect(fs.existsSync(loras(top))).toBe(false);
        await page.keyboard.press("Escape");
      } finally {
        fs.rmSync(loras(top), { recursive: true, force: true });
      }
    });

    test("LoRA Stack adds several picked LoRAs at once", async ({ page }) => {
      const [stack] = await addNodes(page, [{ type: "DiceForgeLoraStack" }]);
      await page.locator(".dfls").first().locator("button.add").click();
      await page.locator(".dflb select").first().selectOption("");
      for (const name of ["ink", "detail"]) await page.locator(".dflb .card", { hasText: `${name}.safetensors` }).locator(".title").click({ modifiers: ["ControlOrMeta"] });
      await page.locator(".dflb .batch .batch-add").click();
      await expect(page.locator(".dflb .status")).toContainText("Added 2 LoRAs.");
      await page.keyboard.press("Escape");
      await expect(page.locator(".dfls").first().locator(".row .name")).toHaveText(["ink", "detail"]);
    });

    test("LoRA Browser keeps its cards full size with many LoRAs", async ({ page }) => {
      const folder = `many_${vue ? "vue" : "classic"}`;
      for (let index = 0; index < 60; index++) writeFile(`models/loras/${folder}/lora_${String(index).padStart(2, "0")}.safetensors`, `${folder} ${index}`);
      try {
        const [loader] = await addNodes(page, [{ type: "LoraLoader" }]);
        await clickMenu(page, loader, "DiceForge.ModelBrowser", "LoRA Browser");
        await expect(page.locator(".dflb .card")).toHaveCount(64);
        const heights = await page.$$eval(".dflb .card", (cards) => cards.map((card) => card.getBoundingClientRect().height));
        expect(Math.min(...heights)).toBeGreaterThan(250); // Not squeezed into the dialog's height (they were 50 px high).
        await page.keyboard.press("Escape");
      } finally {
        fs.rmSync(basePath("models", "loras", folder), { recursive: true, force: true });
      }
    });

    test("LoRA Browser finds and downloads LoRAs on Civitai, renames and deletes them", async ({ page }) => {
      const tag = vue ? "vue" : "classic", folder = `civitai_${tag}`, loras = (...parts) => basePath("models", "loras", ...parts);
      const [loader] = await addNodes(page, [{ type: "LoraLoader" }]);
      await clickMenu(page, loader, "DiceForge.ModelBrowser", "LoRA Browser");
      await page.locator(".dflb button.find").click();
      const dialog = page.locator(".dfcv");
      await expect(dialog.locator(".card", { hasText: "Ink" })).toContainText("Already here: style/ink.safetensors"); // Known by its hash.
      await dialog.locator("input.query").fill("neon");
      await dialog.locator("input.query").press("Enter");
      await expect(dialog.locator(".card")).toHaveCount(1);
      const neon = dialog.locator(".card", { hasText: "Neon" });
      await expect(neon).toContainText("by e2e");
      await expect(neon.locator(".base")).toHaveText("Illustrious");
      await neon.locator("select").selectOption({ label: "v1 · SDXL 1.0" }); // The other version.
      await expect(neon.locator(".base")).toHaveText("SDXL 1.0");
      await dialog.locator("input[list]").fill(folder);
      await neon.locator("button", { hasText: "Download" }).click();
      await expect(dialog.locator(".job.done", { hasText: `${folder}/neon_glow_v1.safetensors` })).toContainText("Done"); // Earlier downloads are listed too.
      await expect(neon).toContainText(`Already here: ${folder}/neon_glow_v1.safetensors`);
      await expect(neon.locator("button", { hasText: "Download" })).toBeDisabled();
      expect(fs.readFileSync(loras(folder, "neon_glow_v1.safetensors"), "utf8")).toBe(DOWNLOADS[502]);
      await page.keyboard.press("Escape"); // Closes only the Civitai dialog: the browser shows the new LoRA.
      await expect(dialog).toHaveCount(0);
      const card = page.locator(".dflb .card", { hasText: "Neon - v1" });
      await expect(card).toContainText("SDXL 1.0");
      await expect(card.locator("img")).toHaveJSProperty("naturalWidth", 8); // Its preview was saved with it.
      await expect.poll(() => page.evaluate((id) => window.app.graph.getNodeById(id).widgets.find((widget) => widget.name === "lora_name").options.values.join("|"), loader))
        .toContain("neon_glow_v1.safetensors"); // Load LoRA's list has it without a restart.
      page.on("dialog", (prompt) => (prompt.type() === "confirm" ? prompt.accept() : prompt.accept(`${folder}_moved/neon`)));
      await card.locator("button.rename").click();
      await expect(page.locator(".dflb .status")).toContainText(`to ${folder}_moved/neon.safetensors`);
      expect(fs.existsSync(loras(folder))).toBe(false);
      expect(fs.readdirSync(loras(`${folder}_moved`)).sort()).toEqual(["neon.preview.png", "neon.safetensors"]);
      await expect(page.locator(".dflb .card", { hasText: "Neon - v1" })).toContainText(`${folder}_moved/neon.safetensors`); // Its Civitai data moved too.
      await page.locator(".dflb .card", { hasText: "Neon - v1" }).locator("button.delete").click();
      await expect(page.locator(".dflb .status")).toContainText(`Deleted ${folder}_moved/neon.safetensors`);
      await expect(page.locator(".dflb .card", { hasText: "Neon" })).toHaveCount(0);
      expect(fs.existsSync(loras(`${folder}_moved`))).toBe(false);
      await page.keyboard.press("Escape");
      await expect(page.locator(".dflb")).toHaveCount(0);
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

    test("Checkpoint Browser downloads a checkpoint from Civitai, uses and deletes it", async ({ page }) => {
      const folder = `ckpt_${vue ? "vue" : "classic"}`, checkpoints = (...parts) => basePath("models", "checkpoints", ...parts);
      const [loader] = await addNodes(page, [{ type: "CheckpointLoaderSimple" }]);
      await clickMenu(page, loader, "DiceForge.ModelBrowser", "Checkpoint Browser");
      await page.locator(".dflb button.find").click();
      const dialog = page.locator(".dfcv");
      await expect(dialog.locator("h2")).toHaveText("Find checkpoints on Civitai");
      await expect(dialog.locator(".card")).toHaveCount(1); // Civitai's Checkpoints only: no LoRA.
      await dialog.locator("input[list]").fill(folder);
      await dialog.locator(".card", { hasText: "Studio XL" }).locator("button", { hasText: "Download" }).click();
      await expect(dialog.locator(".job.done", { hasText: `${folder}/studio_xl.safetensors` })).toContainText("Done");
      expect(fs.readFileSync(checkpoints(folder, "studio_xl.safetensors"), "utf8")).toBe(DOWNLOADS[601]);
      await page.keyboard.press("Escape");
      const card = page.locator(".dflb .card", { hasText: "Studio XL - v1" });
      await card.locator("button", { hasText: /^Use$/ }).click();
      await expect.poll(() => widgetValue(page, loader, "ckpt_name")).toMatch(new RegExp(`${folder}[\\\\/]studio_xl\\.safetensors`));
      page.on("dialog", (prompt) => prompt.accept());
      await card.locator("button.delete").click();
      await expect(page.locator(".dflb .status")).toContainText(`Deleted ${folder}/studio_xl.safetensors`);
      expect(fs.existsSync(checkpoints(folder))).toBe(false);
      await page.keyboard.press("Escape");
    });

    test("Diffusion Model Browser puts a model in Load Diffusion Model and a folder in Random Diffusion Model", async ({ page }) => {
      const [loader, random, both] = await addNodes(page, [{ type: "UNETLoader", widgets: { unet_name: "flux1-dev.safetensors" } }, { type: "DiceForgeRandomDiffusionModel", pos: [500, 40] }, { type: "LoadDiffusionModelCLIP", pos: [900, 40] }]);
      for (const id of [loader, random]) expect(await menuItems(page, id, "DiceForge.ModelBrowser")).toEqual(["🧊 Diffusion Model Browser"]);
      expect(await menuItems(page, both, "DiceForge.ModelBrowser")).toEqual(["🧊 Diffusion Model Browser", "🔤 Text Encoder Browser (clip_name1)", "🔤 Text Encoder Browser (clip_name2)"]);
      await clickMenu(page, loader, "DiceForge.ModelBrowser", "Diffusion Model Browser");
      await expect(page.locator(".dflb h2")).toHaveText("Diffusion Model Browser");
      await page.locator(".dflb .card", { hasText: "flux1-schnell" }).locator("button", { hasText: /^Use$/ }).click();
      await expect.poll(() => widgetValue(page, loader, "unet_name")).toMatch(/flux[\\/]flux1-schnell\.safetensors/);
      await page.locator(".dflb button.find").click();
      await expect(page.locator(".dfcv h2")).toHaveText("Find diffusion models on Civitai");
      await expect(page.locator(".dfcv .hint")).toContainText("diffusion model alone"); // Civitai has them as Checkpoints.
      await page.keyboard.press("Escape");
      await page.keyboard.press("Escape");
      await clickMenu(page, random, "DiceForge.ModelBrowser", "Diffusion Model Browser");
      await page.locator(".dflb .tree .row", { hasText: "flux" }).locator("button", { hasText: "Use folder" }).click();
      await expect.poll(() => widgetValue(page, random, "folder")).toBe("flux");
      await page.keyboard.press("Escape");
    });

    test("Model browsers find model lists in every form: a function, objects, or no list (Asset API); Text Encoder and VAE Browsers", async ({ page }) => {
      const [checkpoint, diffusion, asset, both, vae] = await addNodes(page, [{ type: "CheckpointLoaderSimple" }, { type: "UNETLoader", pos: [420, 40] },
        { type: "UNETLoader", pos: [820, 40], widgets: { unet_name: "flux1-dev.safetensors" } }, { type: "LoadDiffusionModelCLIP", pos: [40, 420] }, { type: "VAELoader", pos: [500, 420] }]);
      await page.evaluate(([checkpoint, diffusion, asset]) => {
        const widget = (id, name) => window.app.graph.getNodeById(id).widgets.find((item) => item.name === name);
        const files = widget(checkpoint, "ckpt_name").options.values.slice();
        widget(checkpoint, "ckpt_name").options.values = () => files; // A function, as some extensions set it.
        const models = widget(diffusion, "unet_name").options.values.slice();
        widget(diffusion, "unet_name").options.values = models.map((content) => ({ content })); // Objects.
        widget(asset, "unet_name").options.values = []; // As an Asset API widget: no list to read, only its value (the canvas still needs a list to draw).
      }, [checkpoint, diffusion, asset]);
      expect(await menuItems(page, checkpoint, "DiceForge.ModelBrowser")).toEqual(["🗃️ Checkpoint Browser"]);
      for (const id of [diffusion, asset]) expect(await menuItems(page, id, "DiceForge.ModelBrowser")).toEqual(["🧊 Diffusion Model Browser"]);
      expect(await menuItems(page, vae, "DiceForge.ModelBrowser")).toEqual(["🎨 VAE Browser"]);
      // Text encoders: Use puts one in the widget it was opened for; Civitai has none, so no Find.
      await clickMenu(page, both, "DiceForge.ModelBrowser", "Text Encoder Browser (clip_name2)");
      await expect(page.locator(".dflb h2")).toHaveText("Text Encoder Browser");
      await expect(page.locator(".dflb button.find")).toHaveCount(0);
      await page.locator(".dflb .card", { hasText: "t5xxl_fp16" }).locator("button", { hasText: /^Use$/ }).click();
      await expect.poll(() => widgetValue(page, both, "clip_name2")).toBe("t5xxl_fp16.safetensors");
      expect(await widgetValue(page, both, "clip_name1")).not.toBe("t5xxl_fp16.safetensors");
      await page.keyboard.press("Escape");
    });

    test("LoRA Browser: Civitai tags, counts, creator and a newer version on the cards; filter by tag, sort by downloads; versions in Model info", async ({ page, request }) => {
      for (const file of ["style/ink.safetensors", "style/pony_glow.safetensors", "style/flux_film.safetensors"]) await lookUp(request, "loras", file);
      const [loader] = await addNodes(page, [{ type: "LoraLoader" }]);
      await clickMenu(page, loader, "DiceForge.ModelBrowser", "LoRA Browser");
      const ink = page.locator(".dflb .card", { hasText: "Ink - v2" });
      await expect(ink.locator(".ctags span")).toHaveText(["anime", "ink", "lineart"]);
      await expect(ink.locator(".stats .stat")).toHaveText(["👍 2.8K", "⬇ 71.1K", "⚡ 920"]); // No comments: not shown.
      await expect(ink.locator(".stats a.newer")).toHaveText("🆕 v3");
      expect(await ink.locator(".stats a.newer").getAttribute("href")).toContain("modelVersionId=199");
      await expect(ink).toContainText("by inkmaker · updated");
      const glow = page.locator(".dflb .card", { hasText: "Glow - v1" });
      await expect(glow.locator(".stats .stat")).toHaveText(["👍 40", "⬇ 900", "💬 3"]);
      await expect(glow.locator(".stats a.newer")).toHaveCount(0); // Its only version.
      await expect(page.locator(".dflb .card", { hasText: "Film - v1" }).locator(".ctags, .stats")).toHaveCount(0); // No page on Civitai.
      // A tag: from the card or the list; the search finds tags and creators too.
      await glow.locator(".ctags span", { hasText: "pony" }).click();
      await expect(page.locator(".dflb .tag-filter")).toHaveValue("pony");
      expect(await cardTitles(page)).toEqual(["Glow - v1 [Pony]"]);
      await page.locator(".dflb .tag-filter").selectOption("");
      await page.locator(".dflb .top input").fill("inkmaker");
      expect(await cardTitles(page)).toEqual(["Ink - v2 [Illustrious]"]);
      await page.locator(".dflb .top input").fill("");
      await page.locator(".dflb .top select").last().selectOption("downloads");
      expect((await cardTitles(page)).slice(0, 2)).toEqual(["Ink - v2 [Illustrious]", "Glow - v1 [Pony]"]);
      await page.keyboard.press("Escape");
      // Model info: the tags and counts by the title, the versions (yours marked, the newer one new).
      await addNodes(page, [{ type: "LoraLoader", pos: [500, 40], widgets: { lora_name: "style/ink.safetensors" } }]);
      const id = await page.evaluate(() => window.app.graph.nodes.at(-1).id);
      await clickMenu(page, id, "DiceForge.ModelInfo", "Model info");
      await expect(page.locator(".dfmi .tag.t3")).toHaveText(["anime", "ink", "lineart"]);
      await expect(page.locator(".dfmi .stats .stat").first()).toHaveText("👍 2.8K");
      await expect(page.locator(".dfmi .version")).toHaveText(["🆕 v3", "● v2"]);
      await expect(page.locator(".dfmi")).toContainText("by inkmaker");
      await page.keyboard.press("Escape");
    });

    test("Model info: Use these settings puts an example image's prompts and settings into the workflow", async ({ page, request }) => {
      await lookUp(request, "loras", "style/ink.safetensors");
      const [lora, encode, sampler, latent] = await addNodes(page, [
        { type: "LoraLoader", widgets: { lora_name: "style/ink.safetensors" } },
        { type: "CLIPTextEncodePositiveNegative", pos: [420, 40] },
        { type: "KSampler", pos: [840, 40], widgets: { sampler_name: "euler", scheduler: "simple" } },
        { type: "EmptyLatentImage", pos: [420, 480] },
      ]);
      await connect(page, encode, 0, sampler, "positive");
      await connect(page, encode, 1, sampler, "negative");
      await clickMenu(page, lora, "DiceForge.ModelInfo", "Model info");
      const stage = page.locator(".dfmi .stage");
      await stage.hover();
      await stage.locator("button.use").click();
      await expect(stage.locator(".applied")).toContainText("prompts in");
      expect(await widgetValue(page, encode, "positive")).toBe("Ink test prompt, 1girl");
      expect(await widgetValue(page, encode, "negative")).toBe("lowres");
      expect(await Promise.all(["seed", "steps", "cfg", "sampler_name", "scheduler"].map((name) => widgetValue(page, sampler, name))))
        .toEqual([3032258275, 30, 4, "euler_ancestral", "simple"]); // Euler a; no schedule given: the scheduler stays.
      await page.keyboard.press("Escape");
      // The name mapping: A1111 names with their schedule, ComfyUI's own names as they are.
      const mapped = await page.evaluate(async () => {
        const { comfySampler, settingsOf } = await import("/extensions/DiceForge/apply_settings.js");
        return [comfySampler("DPM++ 2M Karras"), comfySampler("DPM++ 2M", "Karras"), comfySampler("dpmpp_2m_sde", "exponential"), comfySampler("Euler a", "Automatic"),
          settingsOf({ Size: "832x1216", steps: "28", cfgScale: 5.5, seed: -1 })];
      });
      expect(mapped).toEqual([{ sampler_name: "dpmpp_2m", scheduler: "karras" }, { sampler_name: "dpmpp_2m", scheduler: "karras" },
        { sampler_name: "dpmpp_2m_sde", scheduler: "exponential" }, { sampler_name: "euler_ancestral", scheduler: null }, { width: 832, height: 1216, steps: 28, cfg: 5.5 }]);
      expect(latent).toBeTruthy();
    });

    test("Syntax guide: the prompt syntax by topic, searched, an example inserted into the prompt", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60], widgets: { positive: "1girl" } }]);
      const menu = await page.evaluate((id) => window.app.extensions.flatMap((extension) => extension.getNodeMenuItems?.(window.app.graph.getNodeById(id)) ?? [])
        .filter(Boolean).map((item) => item.content), id);
      expect(menu[0]).toBe("📖 Syntax guide"); // First in the node's menu.
      await clickMenu(page, id, "DiceForge.Wildcards", "Syntax guide");
      const guide = page.locator(".dfsg");
      await expect(guide.locator("h3")).toHaveText(["Wildcards", "Choices", "Variables", "LoRAs and weights", "Comments and escapes", "Wildcard files"]);
      await guide.locator("input").fill("lock");
      await expect(guide.locator(".row")).toHaveCount(1);
      await guide.locator(".row button").click();
      await expect.poll(() => widgetValue(page, id, "positive")).toBe("1girl, {sky|!sea|forest}");
      await expect(guide.locator(".status")).toHaveText("Inserted into the positive prompt.");
      await page.keyboard.press("Escape");
      await expect(guide).toHaveCount(0);
    });

    test("Prompt styles: the family's quality tags in and out with a click, Auto from the connected model, your own saved and deleted", async ({ page, request }) => {
      await lookUp(request, "checkpoints", "illustrious_base.safetensors");
      const [checkpoint, encode] = await addNodes(page, [
        { type: "CheckpointLoaderSimple", widgets: { ckpt_name: "illustrious_base.safetensors" } },
        { type: "CLIPTextEncodePositiveNegative", pos: [460, 40], widgets: { positive: "1girl, smile", negative: "" } },
      ]);
      const items = () => page.evaluate((id) => window.app.extensions.find((item) => item.name === "DiceForge.PromptStyles")
        .getNodeMenuItems(window.app.graph.getNodeById(id))[0].submenu.options.filter(Boolean).map((item) => item.content), encode);
      const click = (content) => page.evaluate(([id, content]) => window.app.extensions.find((item) => item.name === "DiceForge.PromptStyles")
        .getNodeMenuItems(window.app.graph.getNodeById(id))[0].submenu.options.find((item) => item?.content.includes(content)).callback(), [encode, content]);
      const prompts = () => Promise.all([widgetValue(page, encode, "positive"), widgetValue(page, encode, "negative")]);
      await expect.poll(items).toContain("🎨 Illustrious quality");
      await click("Illustrious quality");
      expect(await prompts()).toEqual(["masterpiece, best quality, amazing quality, very aesthetic, absurdres, 1girl, smile",
        "lowres, worst quality, bad quality, bad anatomy, bad hands, jpeg artifacts, signature, watermark, text"]);
      expect(await items()).toContain("✓ Illustrious quality");
      await click("Illustrious quality"); // Again: taken out.
      expect(await prompts()).toEqual(["1girl, smile", ""]);
      await click("Auto"); // Nothing on the model input yet.
      expect(await prompts()).toEqual(["1girl, smile", ""]);
      await connect(page, checkpoint, 0, encode, "model");
      await click("Auto");
      await expect.poll(prompts).toEqual(["masterpiece, best quality, amazing quality, very aesthetic, absurdres, 1girl, smile",
        "lowres, worst quality, bad quality, bad anatomy, bad hands, jpeg artifacts, signature, watermark, text"]);
      // Your own: the prompts as they are, saved under a name, then put into other prompts, then deleted.
      await setWidget(page, encode, "positive", "{prompt}, film grain");
      await setWidget(page, encode, "negative", "cartoon");
      page.on("dialog", (dialog) => (dialog.type() === "prompt" ? dialog.accept(`E2E film ${vue}`) : dialog.accept()));
      await click("Save the prompts as a style");
      await expect.poll(items).toContain(`✓ E2E film ${vue}`); // Saved from these prompts: they have it.
      await setWidget(page, encode, "positive", "a cat");
      await setWidget(page, encode, "negative", "");
      await expect.poll(items).toContain(`★ E2E film ${vue}`); // Other prompts: your style (★), not in them.
      await click(`★ E2E film ${vue}`);
      expect(await prompts()).toEqual(["a cat, film grain", "cartoon"]);
      await click(`🗑 Delete E2E film ${vue}`);
      await expect.poll(items).not.toContain(`🗑 Delete E2E film ${vue}`);
      expect((await (await request.get("/diceforge/styles")).json()).user.map((style) => style.name)).not.toContain(`E2E film ${vue}`);
    });

    test("Tag autocomplete: the Danbooru list downloaded from the node's menu, then the most used tags while a word is typed", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60] }]);
      const menu = () => page.evaluate((id) => window.app.extensions.find((item) => item.name === "DiceForge.TagAutocomplete")
        .getNodeMenuItems(window.app.graph.getNodeById(id))[0].submenu.options.map((item) => item.content), id);
      await expect.poll(menu).toContain("⬇ Download: Danbooru (anime: Illustrious, NoobAI, Anima, Pony)");
      await page.evaluate((id) => window.app.extensions.find((item) => item.name === "DiceForge.TagAutocomplete")
        .getNodeMenuItems(window.app.graph.getNodeById(id))[0].submenu.options[0].callback(), id);
      await expect.poll(menu).toContain("✓ Download again: Danbooru (anime: Illustrious, NoobAI, Anima, Pony)");
      try {
        const positive = await promptField(page, id, "positive");
        await positive.click();
        await page.keyboard.type("1gi");
        await expect(page.locator(".dfwc-pop div").first()).toContainText("1girl");
        await page.keyboard.press("Enter");
        await expect.poll(() => widgetValue(page, id, "positive")).toBe("1girl, ");
        await page.keyboard.type("lo");
        await expect(page.locator(".dfwc-pop div")).toHaveText([/long_hair\s*5M/, /long_sleeves\s*1\.5M/]); // Most used first, with the count.
        await page.keyboard.press("Enter");
        await expect.poll(() => widgetValue(page, id, "positive")).toBe("1girl, long hair, "); // Spaces for underscores.
        await page.keyboard.type("mik");
        await expect(page.locator(".dfwc-pop div").first()).toContainText("miku → hatsune_miku"); // By its alias.
        await page.keyboard.press("Escape");
        await expect(page.locator(".dfwc-pop")).toHaveCount(0);
        // The Tag Browser: search, a type, + Add and − Neg, ★ favorites.
        await clickMenu(page, id, "DiceForge.TagBrowser", "Tag Browser");
        const browser = page.locator(".dftb");
        await expect(browser.locator(".row .name b")).toHaveText(["1girl", "long_hair", "smile", "long_sleeves", "hatsune_miku"]); // Most used first.
        await browser.locator(".top input").fill("long");
        await expect(browser.locator(".row .name b")).toHaveText(["long_hair", "long_sleeves"]);
        await browser.locator(".row", { hasText: "long_sleeves" }).locator("button.neg").click();
        await expect.poll(() => widgetValue(page, id, "negative")).toBe("long sleeves");
        await browser.locator(".top input").fill("");
        await browser.locator(".types button", { hasText: "Characters" }).click();
        await expect(browser.locator(".row .name b")).toHaveText(["hatsune_miku"]);
        await browser.locator(".row button.fav").click();
        await browser.locator(".types button", { hasText: "Favorites" }).click();
        await expect(browser.locator(".row .name b")).toHaveText(["hatsune_miku"]);
        await browser.locator(".row button.add").click();
        await expect(browser.locator(".status")).toContainText("Added hatsune miku to the");
        await page.keyboard.press("Escape");
        await expect(browser).toHaveCount(0);
      } finally {
        fs.rmSync(basePath("user", "DiceForge", "tags"), { recursive: true, force: true }); // No tag suggestions in the other tests.
        fs.rmSync(basePath("user", "DiceForge", "tag_favorites.json"), { force: true });
      }
    });

    test("Dice Grid's cells panel: star the best cells, save them at full size with their workflow, open a cell's run", async ({ page, request }) => {
      const [image, grid] = await addNodes(page, [
        { type: "EmptyImage", widgets: { width: 96, height: 64 } },
        { type: "DiceForgeGrid", pos: [460, 40], widgets: { count: 0, cell_width: 64, save: false, name: `cells-${vue}` } },
      ]);
      await connect(page, image, 0, grid, "image");
      for (let run = 0; run < 3; run++) {
        await setWidget(page, image, "color", run * 4000000);
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
      page.once("dialog", (dialog) => dialog.accept());
      await panel.locator(".cell").nth(1).locator("button.open").click();
      // The graph already has these two nodes: wait for the opened run's color (the graph before it had the last run's, 8000000).
      const color = () => page.evaluate(() => window.app.graph.nodes.find((node) => node.comfyClass === "EmptyImage")?.widgets.find((widget) => widget.name === "color").value);
      await expect.poll(color).toBe(4000000);
      expect(await page.evaluate(() => window.app.graph.nodes.map((node) => node.comfyClass).sort().join())).toBe("DiceForgeGrid,EmptyImage");
    });

    test("XY Plot shows the plot under its fields and queues every cell into Dice Grid", async ({ page, request }) => {
      const [xy, image, grid] = await addNodes(page, [
        { type: "DiceForgeXYPlot", widgets: { x_type: "steps", x_values: "10, 20", y_type: "scheduler", y_values: "normal, karras" } },
        { type: "EmptyImage", pos: [460, 40], widgets: { width: 64, height: 64 } },
        { type: "DiceForgeGrid", pos: [860, 40], widgets: { count: 4, cell_width: 64, name: `xy-ui-${vue}`, filename_prefix: `e2e/xyui${vue ? "v" : "c"}` } },
      ]);
      await connect(page, image, 0, grid, "image");
      await connect(page, xy, 8, grid, "label");
      await connect(page, xy, 9, grid, "row_label");
      const panel = page.locator(".dfxy").first();
      await expect(panel.locator(".axis").first()).toContainText("X · steps10 steps20 steps");
      await expect(panel.locator(".axis").nth(1)).toContainText("Y · schedulernormalkarras");
      await expect(panel).toContainText("2 × 2 = 4 images");
      await setWidget(page, xy, "x_values", "10, x");
      await expect(panel.locator(".error")).toContainText("not a number");
      await expect(panel.locator("button")).toHaveCount(0);
      await setWidget(page, xy, "x_values", "10, 20");
      await panel.locator("button", { hasText: "▶ Queue 4 images" }).click();
      await expect(panel.locator("button")).toHaveText("▶ Queue 4 images", { timeout: 30_000 }); // All queued.
      expect(await widgetValue(page, xy, "index")).toBe(0);
      const folder = basePath("output", "e2e");
      await expect.poll(() => fs.existsSync(folder) && fs.readdirSync(folder).some((name) => name.startsWith(`xyui${vue ? "v" : "c"}_`)), { timeout: 60_000 }).toBe(true);
      const queue = async () => { const body = await (await request.get("/queue")).json(); return body.queue_running.length + body.queue_pending.length; };
      await expect.poll(queue, { timeout: 60_000 }).toBe(0);
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
      page.on("dialog", (dialog) => (dialog.type() === "prompt" ? dialog.accept("E2E mine") : dialog.accept()));
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
      // The node shows the prompts as encoded, with the seed they came from.
      const shown = page.locator(".dfpp").first();
      await expect(shown.locator(".box").first()).toHaveText(`positive${text}`);
      if (vue) { // The negative shows with the advanced inputs, where its field is.
        await expect(shown.locator(".box")).toHaveCount(1);
        await page.evaluate((id) => { const node = window.app.graph.getNodeById(id); node.showAdvanced = true; node.setDirtyCanvas(true, true); }, encode);
      }
      await expect(shown.locator(".box").nth(1)).toContainText("(empty)");
      await expect(shown.locator(".head")).toContainText("seed 3 (random)");
      await expect(shown).not.toHaveClass(/stale/);
      await setWidget(page, encode, "positive", "a __color__ bike"); // Changed since the run: dimmed until the next one.
      await expect(shown).toHaveClass(/stale/);
      await expect(shown.locator(".changed")).toHaveText("prompt changed since");
      // Kept with the workflow: a reload of it shows them again.
      const workflow = await page.evaluate(() => window.app.graph.serialize());
      expect(workflow.nodes.find((node) => String(node.id) === String(encode)).properties.dice_forge_prompts.positive).toBe(text);
      await page.evaluate(async (data) => { window.app.graph.clear(); await window.app.loadGraphData(data); }, workflow);
      await expect(page.locator(".dfpp").first().locator(".box").first()).toHaveText(`positive${text}`);
    });

    test("the prompt history keeps the last runs with their images: put back a seed, use a text, pin, remove", async ({ page, request }) => {
      const [encode, preview, image, show] = await addNodes(page, [
        { type: "CLIPTextEncodePositiveNegative", widgets: { positive: "a {red|blue|green|white|black|pink} car", seed: 1, control_after_generate: "increment" } },
        { type: "PreviewAny", pos: [500, 40] },
        { type: "EmptyImage", pos: [40, 520], widgets: { width: 32, height: 32 } },
        { type: "PreviewImage", pos: [400, 520] },
      ]);
      await connect(page, encode, 2, preview, 0);
      await connect(page, image, 0, show, 0); // An image made in the same runs: kept with each run's prompts.
      for (let run = 0; run < 3; run++) {
        await setWidget(page, image, "color", run * 1000); // Another image each run.
        await queueFromPage(page, request); // Seeds 1, 2, 3.
      }
      const panel = page.locator(".dfpp").first();
      const lastRun = async () => (await panel.locator(".box").first().textContent()).replace(/^positive/, "");
      const texts = (await page.evaluate((id) => window.app.graph.getNodeById(id).properties.dice_forge_history.map((item) => item.positive), encode)).reverse();
      await expect(panel.locator(".history-link")).toHaveCount(0); // Not on the node: in its right-click menu.
      await clickMenu(page, encode, "DiceForge.PromptPreview", "Prompt history");
      const dialog = page.locator(".dfph");
      await expect(dialog.locator(".top .muted")).toHaveText("3 runs, newest first");
      const entries = dialog.locator(".entry");
      await expect(entries.locator(".when")).toHaveText([/seed 3 \(random\)$/, /seed 2 \(random\)$/, /seed 1 \(random\)$/]); // Newest first.
      await expect(entries.locator(".text")).toHaveText([texts[2], texts[1], texts[0]]);
      await expect(entries.first().locator(".shots img")).toHaveCount(1); // Each run's image.
      await expect(entries.first().locator(".shots img")).toHaveJSProperty("naturalWidth", 32);
      const files = await entries.locator(".shots img").evaluateAll((pictures) => pictures.map((picture) => new URL(picture.src).searchParams.get("filename")));
      expect(new Set(files).size).toBe(3); // A different image for each run.
      await setWidget(page, encode, "control_after_generate", "fixed");
      await setWidget(page, encode, "seed", 3);
      await queueFromPage(page, request); // The same as the newest: not added again, its image joins the entry.
      await expect(entries).toHaveCount(3);
      await expect(entries.first().locator(".shots img")).toHaveCount(1); // The same image again (same color): once.
      await entries.nth(2).locator(".reseed").click(); // Seed 1 again: its prompts, seed and mode.
      expect(await widgetValue(page, encode, "seed")).toBe(1);
      expect(await widgetValue(page, encode, "control_after_generate")).toBe("fixed");
      await queueFromPage(page, request);
      await expect(panel.locator(".head")).toContainText("seed 1 (random)");
      expect(await lastRun()).toBe(texts[0]); // The same prompts as that run.
      await expect(entries).toHaveCount(4); // That run is the newest now.
      await entries.filter({ hasText: "seed 2 (random)" }).locator(".use-text").click();
      expect(await widgetValue(page, encode, "positive")).toBe(texts[1]); // Every choice made.
      await entries.last().locator(".pin").click();
      await expect(entries.last()).toHaveClass(/pinned/);
      await entries.first().locator(".forget").click();
      await expect(entries).toHaveCount(3);
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      await page.evaluate(([id, filler]) => { // Many unpinned runs: only the last 20 stay, a pinned one stays too.
        const node = window.app.graph.getNodeById(id);
        const pinned = node.properties.dice_forge_history.filter((item) => item.pinned);
        node.properties.dice_forge_history = [...filler, ...pinned];
      }, [encode, Array.from({ length: 25 }, (_, index) => ({ positive: `old ${index}`, negative: "", seed: 100 + index, seed_mode: "random", time: index + 1 }))]);
      await setWidget(page, encode, "positive", "a {big|small} boat");
      await queueFromPage(page, request);
      await clickMenu(page, encode, "DiceForge.PromptPreview", "Prompt history");
      await expect(dialog.locator(".top .muted")).toHaveText("21 runs, newest first");
      await expect(dialog.locator(".pin.on")).toHaveCount(1);
      await page.keyboard.press("Escape");
      const workflow = await page.evaluate(() => window.app.graph.serialize()); // Kept with the workflow.
      expect(workflow.nodes.find((node) => String(node.id) === String(encode)).properties.dice_forge_history).toHaveLength(21);
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

    test("Danbooru Tag Enhancer shows the prompt it made from a Danbooru post, also after a reload", async ({ page, request }) => {
      const [id] = await addNodes(page, [{ type: "DiceForgeDanbooruEnhancer", widgets: { tags: "hatsune miku" } }]);
      const panel = page.locator(".dfdb").first();
      await expect(panel).toContainText("Run the workflow to see the prompt made from a Danbooru post here.");
      await queueFromPage(page, request); // An output node: it runs with nothing connected.
      await expect(panel.locator(".text")).toHaveText("hatsune miku, 1girl, smile, twintails"); // Post 101: rating:g.
      await expect(panel.locator(".head")).toContainText("Last run · post #101 (general)");
      await expect(panel.locator(".added")).toHaveText("+ 1girl, smile, twintails");
      await expect(panel.locator(".search")).toHaveText("Searched: hatsune_miku rating:g");
      await expect(panel.locator("a")).toHaveAttribute("href", /\/posts\/101$/);
      const workflow = await page.evaluate(() => window.app.graph.serialize());
      expect(workflow.nodes.find((node) => String(node.id) === String(id)).properties.dice_forge_danbooru.id).toBe(101);
      await page.evaluate(async (data) => { window.app.graph.clear(); await window.app.loadGraphData(data); }, workflow);
      await expect(page.locator(".dfdb").first().locator(".text")).toHaveText("hatsune miku, 1girl, smile, twintails"); // Kept with the workflow.
    });

    if (vue) {
      test("DiceForge nodes fit their inputs when advanced inputs are shown and hidden", async ({ page }) => { // NOSONAR: expect.poll(...) assertions below.
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
