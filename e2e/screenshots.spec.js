// Screenshots of the DiceForge nodes in the Nodes 2.0 design for the README and the node help (DiceForge/web/docs/images), taken in the real ComfyUI page with the test files of
// the end-to-end server (stand-in models, wildcards, images). Not part of the test run: DICEFORGE_SCREENSHOTS=1 npx playwright test screenshots.spec.js
const path = require("path");
const fs = require("fs");
const { test, expect, openComfy, addNodes, connect, setWidget, clickMenu, queueFromPage, nodeElement, writeFile } = require("./helpers");
const { wildcardMode } = require("./ui-shared");
const { png } = require("./fixtures");

const OUT = path.join(__dirname, "..", "DiceForge", "web", "docs", "images");
test.skip(!process.env.DICEFORGE_SCREENSHOTS, "Screenshots only on request: DICEFORGE_SCREENSHOTS=1");
test.use({ deviceScaleFactor: 2, viewport: { width: 2200, height: 1300 } });
test.describe.configure({ timeout: 180_000 });

// A screenshot of the nodes (and anything else given by selector) together, with a margin of canvas around them.
async function shot(page, ids, file, { extra = [], margin = 24 } = {}) {
  await page.waitForTimeout(800); // Previews and panels settle.
  const boxes = [];
  for (const id of ids) boxes.push(await nodeElement(page, id).boundingBox());
  for (const selector of extra) boxes.push(await page.locator(selector).first().boundingBox());
  const left = Math.min(...boxes.map((box) => box.x)) - margin, top = Math.min(...boxes.map((box) => box.y)) - margin;
  const right = Math.max(...boxes.map((box) => box.x + box.width)) + margin, bottom = Math.max(...boxes.map((box) => box.y + box.height)) + margin;
  fs.mkdirSync(OUT, { recursive: true });
  await page.screenshot({ path: path.join(OUT, file), clip: { x: Math.max(0, left), y: Math.max(0, top), width: right - left, height: bottom - top } });
}
const showAdvanced = (page, id) => page.evaluate((id) => { const node = window.app.graph.getNodeById(id); node.showAdvanced = true; node.setDirtyCanvas(true, true); }, id);
// A soft gradient for pictures the stand-ins serve as tiny squares (Danbooru posts), so the screenshots show the layout.
const picture = (hue) => `<svg xmlns="http://www.w3.org/2000/svg" width="270" height="360"><defs><linearGradient id="g" x2="0" y2="1">` +
  `<stop offset="0" stop-color="hsl(${hue},45%,62%)"/><stop offset="1" stop-color="hsl(${hue + 40},40%,32%)"/></linearGradient></defs><rect width="100%" height="100%" fill="url(#g)"/></svg>`;
const lookUp = (request, kind, file) => request.get(`/diceforge/model-info?kind=${kind}&file=${encodeURIComponent(file)}`);

test.describe("README screenshots (Nodes 2.0)", () => {
  test.beforeEach(async ({ page }) => openComfy(page, { vue: true }));

  test("resolution nodes", async ({ page }) => {
    const [sdxl] = await addNodes(page, [{ type: "DiceForgeSDXLResolutionList", pos: [400, 220], widgets: { "resolution.size": "1216 x 832" } }]);
    await setWidget(page, sdxl, "rescale.percent", 150);
    await showAdvanced(page, sdxl);
    await expect(nodeElement(page, sdxl)).toContainText("1824 × 1248");
    await shot(page, [sdxl], "sdxl_resolution_list.png");
    await page.evaluate(() => window.app.graph.clear());
    const [selector] = await addNodes(page, [{ type: "DiceForgeResolutionSelector", pos: [400, 220], widgets: { aspect_ratio: "16:9 (Widescreen)" } }]);
    await setWidget(page, selector, "rescale", "to longest side");
    await setWidget(page, selector, "rescale.longer_side", 1920);
    await expect(nodeElement(page, selector)).toContainText("1920 × 1080");
    await shot(page, [selector], "resolution_selector.png");
  });

  test("CLIP Dual Text Encode and the autocomplete", async ({ page }) => {
    const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [400, 220], widgets: {
      positive: "${g={male|female}}photo of a __outfit/${g}__ person, {2$$__characters/*/outfit__}, __color__ hair, {3::smiling|serious}",
      negative: "blurry, lowres", seed: 42, seed_mode: "deck" } }]);
    await setWidget(page, id, "control_after_generate", "fixed");
    await showAdvanced(page, id);
    await shot(page, [id], "clip_dual_text_encode.png");
    const field = page.locator(`[data-node-id="${id}"] textarea`).first();
    await field.click();
    await page.keyboard.press("Control+End");
    await page.keyboard.type(", __hair/");
    await expect(page.locator(".dfwc-pop")).toContainText("__hair/style__");
    await shot(page, [id], "wildcard_autocomplete.png", { extra: [".dfwc-pop"] });
    await page.keyboard.press("Escape");
    await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
    await page.locator(".dfwc .tree > .row", { hasText: /^color/ }).locator(".name").click();
    await expect(page.locator(".dfwc .edit textarea")).toHaveValue(/red/);
    await page.locator(".dfwc .edit textarea").press("Control+End");
    await page.keyboard.type("\nyellow"); // An unsaved change: Save •.
    await expect(page.locator(".dfwc button.save")).toHaveText("Save •");
    await page.waitForTimeout(500);
    await page.locator(".dfwc").first().screenshot({ path: path.join(OUT, "wildcard_browser.png") });
  });

  test("random numbers and sampler", async ({ page }) => {
    const ids = await addNodes(page, [
      { type: "DiceForgeRandomInt", pos: [400, 220], widgets: { min: 20, max: 40, step: 2, seed_mode: "deck" } },
      { type: "DiceForgeRandomFloat", pos: [720, 220], widgets: { min: 4.5, max: 8, step: 0.5, seed_mode: "shuffle" } },
      { type: "DiceForgeRandomSampler", pos: [1040, 220], widgets: { samplers: "euler, dpmpp_2m, dpmpp_2m_sde", schedulers: "normal, karras", seed_mode: "deck" } },
    ]);
    await expect(nodeElement(page, ids[2]).locator("textarea").first()).toHaveValue("euler, dpmpp_2m, dpmpp_2m_sde");
    await shot(page, ids, "random_numbers_sampler.png");
  });

  test("random loaders", async ({ page }) => {
    const ids = await addNodes(page, [
      { type: "DiceForgeRandomLora", pos: [400, 220], widgets: { folder: "style", seed_mode: "deck" } },
      { type: "DiceForgeRandomCheckpoint", pos: [720, 220], widgets: { seed_mode: "shuffle" } },
      { type: "DiceForgeRandomDiffusionModel", pos: [1040, 220] },
      { type: "DiceForgeRandomVAE", pos: [1360, 220] },
    ]);
    await expect(nodeElement(page, ids[0])).toContainText("style");
    await shot(page, ids, "random_loaders.png");
  });

  test("Random Image and Dice Grid after a few runs", async ({ page, request }) => {
    const [image, grid] = await addNodes(page, [
      { type: "DiceForgeRandomImage", pos: [400, 220], widgets: { folder: "e2e", seed: 0, control_after_generate: "increment", seed_mode: "deck" } },
      { type: "DiceForgeGrid", pos: [840, 220], widgets: { count: 4, cell_width: 128, save: false, name: "readme", new_grid: true, legend: "Random Image, deck", numbered: false } },
    ]);
    await connect(page, image, 0, grid, "image");
    await connect(page, image, 2, grid, "label");
    for (let run = 0; run < 4; run++) {
      await queueFromPage(page, request);
      await setWidget(page, grid, "new_grid", false);
    }
    await expect(nodeElement(page, grid).locator("img").first()).toBeVisible();
    await shot(page, [image, grid], "random_image_dice_grid.png");
  });

  test("LoRA Stack, LoRA Browser and Model info", async ({ page, request }) => {
    for (const file of ["style/ink.safetensors", "style/pony_glow.safetensors", "style/flux_film.safetensors"]) await lookUp(request, "loras", file);
    await lookUp(request, "checkpoints", "illustrious_base.safetensors");
    const [checkpoint, stack] = await addNodes(page, [
      { type: "CheckpointLoaderSimple", pos: [400, 220], widgets: { ckpt_name: "illustrious_base.safetensors" } },
      { type: "DiceForgeLoraStack", pos: [840, 220] },
    ]);
    await connect(page, checkpoint, 0, stack, "model");
    await connect(page, checkpoint, 1, stack, "clip");
    const panel = page.locator(".dfls").first();
    await expect(panel.locator(".model")).toContainText("Illustrious", { timeout: 20_000 });
    await panel.locator("button.add").click();
    await page.locator(".dflb select").first().selectOption("");
    await page.waitForTimeout(800);
    await page.locator(".dflb").first().screenshot({ path: path.join(OUT, "lora_browser.png") });
    for (const name of ["Ink", "Glow", "Film"]) await page.locator(".dflb .card", { hasText: name }).locator("button", { hasText: "+ Add" }).click();
    await page.keyboard.press("Escape");
    await panel.locator(".row").nth(0).locator("button", { hasText: "🎲" }).click();
    await panel.locator(".row").nth(1).locator("select").selectOption("A");
    await panel.locator(".row").nth(2).locator("select").selectOption("A");
    await shot(page, [checkpoint, stack], "lora_stack.png");
    await page.evaluate(() => window.app.graph.clear());
    const [loader] = await addNodes(page, [{ type: "LoraLoader", pos: [400, 220], widgets: { lora_name: "style/ink.safetensors" } }]);
    await clickMenu(page, loader, "DiceForge.ModelInfo", "Model info");
    await expect(page.locator(".dfmi h2")).toHaveText("Ink - v2");
    await page.locator(".dfmi .stage").scrollIntoViewIfNeeded();
    await page.locator(".dfmi .stage").hover(); // How the image was made, over it.
    await expect(page.locator(".dfmi .stage .meta")).toHaveCSS("opacity", "1");
    await page.waitForTimeout(800);
    await page.locator(".dfmi").first().screenshot({ path: path.join(OUT, "model_info.png") });
  });

  test("Find LoRAs on Civitai", async ({ page, request }) => {
    const [loader] = await addNodes(page, [{ type: "LoraLoader", pos: [400, 220] }]);
    await clickMenu(page, loader, "DiceForge.ModelBrowser", "LoRA Browser");
    await page.locator(".dflb button.find").click();
    const dialog = page.locator(".dfcv");
    await expect(dialog.locator(".card", { hasText: "Ink" })).toContainText("Already here");
    await dialog.locator("input[list]").fill("styles/neon");
    await dialog.locator(".card", { hasText: "Neon" }).locator("button", { hasText: "Download" }).click();
    await expect(dialog.locator(".job.done")).toContainText("styles/neon/neon_glow.safetensors");
    await page.waitForTimeout(800);
    await dialog.screenshot({ path: path.join(OUT, "civitai_search.png") });
    expect((await request.delete("/diceforge/models/file?kind=loras&file=styles/neon/neon_glow.safetensors")).ok()).toBe(true);
  });

  test("KSampler presets in the right-click menu", async ({ page, request }) => {
    await lookUp(request, "checkpoints", "illustrious_base.safetensors");
    const [checkpoint, sampler] = await addNodes(page, [
      { type: "CheckpointLoaderSimple", pos: [400, 260], widgets: { ckpt_name: "illustrious_base.safetensors" } },
      { type: "KSampler", pos: [760, 260] },
    ]);
    await connect(page, checkpoint, 0, sampler, 0);
    await nodeElement(page, sampler).locator(".lg-node-header").first().click({ button: "right" });
    await page.getByText("Sampler presets").first().hover();
    const last = page.getByText(/NoobAI \(v-pred\) ·/).first();
    await expect(last).toBeVisible();
    await page.waitForTimeout(600);
    const boxes = [await nodeElement(page, checkpoint).boundingBox(), await nodeElement(page, sampler).boundingBox(),
      await page.getByText("Sampler presets").first().boundingBox(), await last.boundingBox(), await page.getByText("Save current as preset").first().boundingBox()];
    const left = Math.min(...boxes.map((box) => box.x)) - 24, top = Math.min(...boxes.map((box) => box.y)) - 24;
    const right = Math.max(...boxes.map((box) => box.x + box.width)) + 40, bottom = Math.max(...boxes.map((box) => box.y + box.height)) + 40;
    await page.screenshot({ path: path.join(OUT, "sampler_presets.png"), clip: { x: left, y: top, width: right - left, height: bottom - top } });
    expect(right - left).toBeGreaterThan(400);
  });

  test("utility nodes", async ({ page }) => {
    const ids = await addNodes(page, [
      { type: "DiceForgeVAEDecodeSave", pos: [400, 220] },
      { type: "DiceForgeLoadVAEDecodeSave", pos: [720, 220] },
      { type: "DiceForgeLoadDiffusionModelCLIP", pos: [1040, 220], widgets: { unet_name: "flux1-dev.safetensors", clip_name1: "clip_l.safetensors" } },
    ]);
    await expect(nodeElement(page, ids[2])).toContainText("flux1-dev.safetensors");
    await shot(page, ids, "utility_nodes.png");
  });

  test("Wildcards to Text, the Syntax guide and the prompt history", async ({ page, request }) => {
    const [words, text] = await addNodes(page, [{ type: "DiceForgeWildcardsToText", pos: [400, 220], widgets: {
      text: "photo of a {smiling|serious} person, __color__ hair, {2$$hat|scarf|bow} // a note", seed: 7 } }, { type: "PreviewAny", pos: [1000, 220] }]);
    await connect(page, words, 0, text, 0);
    await setWidget(page, words, "control_after_generate", "fixed");
    await queueFromPage(page, request);
    await expect(nodeElement(page, text).locator("textarea")).toHaveValue(/photo of a/);
    await shot(page, [words, text], "wildcards_to_text.png");

    const [encode, prompt, image, show] = await addNodes(page, [
      { type: "DiceForgeCLIPDualTextEncode", pos: [400, 700], widgets: { positive: "1girl, {red|blue|green} dress, __hair/style__", seed: 5, control_after_generate: "increment" } },
      { type: "PreviewAny", pos: [1000, 700] },
      { type: "EmptyImage", pos: [1300, 700], widgets: { width: 64, height: 64 } },
      { type: "PreviewImage", pos: [1600, 700] },
    ]);
    await connect(page, encode, 3, prompt, 0); // Connected: ComfyUI runs only nodes whose outputs go somewhere.
    await connect(page, image, 0, show, 0); // An image made in the same runs: kept with each run's prompts.
    for (let run = 0; run < 3; run++) {
      await setWidget(page, image, "color", [0x7a5cc0, 0xc06a5c, 0x5cc08a][run]);
      await queueFromPage(page, request);
    }
    await clickMenu(page, encode, "DiceForge.PromptPreview", "Prompt history");
    await expect(page.locator(".dfph .entry")).toHaveCount(3);
    await page.waitForTimeout(800);
    await page.locator(".dfph").screenshot({ path: path.join(OUT, "prompt_history.png") });
    await page.keyboard.press("Escape");

    await clickMenu(page, encode, "DiceForge.Wildcards", "Syntax guide");
    await expect(page.locator(".dfsg h3").first()).toHaveText("Wildcards");
    await page.waitForTimeout(500);
    await page.locator(".dfsg").screenshot({ path: path.join(OUT, "syntax_guide.png") });
    await page.keyboard.press("Escape");
  });

  test("Wildcard Browser cards", async ({ page }) => {
    writeFile("models/wildcards/POSES.yaml", "POSES:\n  sitting: sitting, hands on lap,\n  standing: standing, arms crossed,\n  kneeling: kneeling,\n  lying: lying on back,\n");
    for (const [index, pose] of ["sitting", "standing", "kneeling"].entries()) writeFile(`models/wildcards/POSES/${pose}.png`, png(120, 160, [[150, 110, 190], [190, 120, 100], [100, 160, 140]][index]));
    const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [400, 220], widgets: { positive: "1girl" } }]);
    await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
    const dialog = page.locator(".dfwc");
    await wildcardMode(dialog, "cards");
    await dialog.locator('.row[data-name="POSES.yaml"] .name').click();
    await expect(dialog.locator(".card")).toHaveCount(4);
    await page.waitForTimeout(800);
    await dialog.screenshot({ path: path.join(OUT, "wildcard_cards.png") });
    await dialog.locator("button.mode").click(); // Back to lines for the next time.
    await page.keyboard.press("Escape");
  });

  test("Danbooru Tag Enhancer", async ({ page, request }) => {
    let hue = 200;
    await page.route("**/image/danbooru/**", (route) => route.fulfill({ contentType: "image/svg+xml", body: picture((hue += 70)) }));
    const [id] = await addNodes(page, [{ type: "DiceForgeDanbooruEnhancer", pos: [400, 220], widgets: { tags: "1girl, hatsune miku", posts: 1 } }]);
    await showAdvanced(page, id);
    await queueFromPage(page, request);
    await expect(page.locator(".dfdb .added")).toContainText("+ ");
    await expect(page.locator(".dfdb a.thumb img")).toHaveJSProperty("naturalWidth", 270);
    await shot(page, [id], "danbooru_tag_enhancer.png");
  });
});
