// End-to-end in the browser, the models: Model info, the previews, the LoRA, Checkpoint and Diffusion Model Browsers (Civitai search and
// downloads, moving, favorites, batch actions) and LoRA Stack, in both node designs (Nodes 2.0 and classic), against the real server.
// Each test builds its own graph.
const fs = require("fs");
const { test, expect, basePath, writeFile, openComfy, addNodes, connect, widgetValue, menuItems, clickMenu } = require("./helpers");
const { DOWNLOADS } = require("./fixtures");
const { lookUp, cardTitles } = require("./ui-shared");

for (const vue of [true, false]) {
  test.describe(vue ? "Nodes 2.0" : "classic nodes", () => {
    test.beforeEach(async ({ page }) => openComfy(page, { vue }));

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
        const url = (await (await fetch("/extensions")).json()).find((name) => name.endsWith("/media.js")); // As ComfyUI loaded it: the same module.
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
      await page.locator(".dflb .status button.undo").click(); // ↶ Undo: back, with its preview and Civitai data.
      await expect(page.locator(".dflb .status")).toContainText("Brought back 1 LoRA.");
      expect(fs.readdirSync(loras(`${folder}_moved`)).sort()).toEqual(["neon.preview.png", "neon.safetensors"]);
      await expect(page.locator(".dflb .card", { hasText: "Neon - v1" })).toBeVisible();
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
      await page.locator(".dflb .top input:not([type=checkbox])").fill("inkmaker");
      expect(await cardTitles(page)).toEqual(["Ink - v2 [Illustrious]"]);
      await page.locator(".dflb .top input:not([type=checkbox])").fill("");
      await page.locator(".dflb .top select").last().selectOption("downloads");
      expect((await cardTitles(page)).slice(0, 2)).toEqual(["Ink - v2 [Illustrious]", "Glow - v1 [Pony]"]);
      await page.keyboard.press("Escape");
      await clickMenu(page, loader, "DiceForge.ModelBrowser", "LoRA Browser");
      await expect(page.locator(".dflb .top select").last()).toHaveValue("downloads"); // Opens where it was closed.
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
      await connect(page, encode, 1, sampler, "positive");
      await connect(page, encode, 2, sampler, "negative");
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
  });
}
