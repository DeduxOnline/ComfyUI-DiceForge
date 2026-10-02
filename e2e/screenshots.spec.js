// Screenshots of the DiceForge nodes in the Nodes 2.0 design for the README (docs/images), taken in the real ComfyUI page with the test files of
// the end-to-end server (stand-in models, wildcards, images). Not part of the test run: DICEFORGE_SCREENSHOTS=1 npx playwright test screenshots.spec.js
const path = require("path");
const fs = require("fs");
const { test, expect, openComfy, addNodes, connect, setWidget, clickMenu, queueFromPage, nodeElement } = require("./helpers");

const OUT = path.join(__dirname, "..", "docs", "images");
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
const lookUp = (request, kind, file) => request.get(`/diceforge/model-info?kind=${kind}&file=${encodeURIComponent(file)}`);

test.describe("README screenshots (Nodes 2.0)", () => {
  test.beforeEach(async ({ page }) => openComfy(page, { vue: true }));

  test("resolution nodes", async ({ page }) => {
    const [sdxl] = await addNodes(page, [{ type: "SDXLResolutionListLatent", pos: [400, 220], widgets: { "resolution.size": "1216 x 832" } }]);
    await setWidget(page, sdxl, "rescale.percent", 150);
    await showAdvanced(page, sdxl);
    await expect(nodeElement(page, sdxl)).toContainText("1824 × 1248");
    await shot(page, [sdxl], "sdxl_resolution_list.png");
    await page.evaluate(() => window.app.graph.clear());
    const [selector] = await addNodes(page, [{ type: "ResolutionSelectorRandomLatent", pos: [400, 220], widgets: { aspect_ratio: "16:9 (Widescreen)" } }]);
    await setWidget(page, selector, "rescale", "to longest side");
    await setWidget(page, selector, "rescale.longer_side", 1920);
    await expect(nodeElement(page, selector)).toContainText("1920 × 1080");
    await shot(page, [selector], "resolution_selector.png");
  });

  test("CLIP Dual Text Encode and the autocomplete", async ({ page }) => {
    const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [400, 220], widgets: {
      positive: "${g={male|female}}photo of a __outfit/${g}__ person, {2$$__characters/*/outfit__}, __color__ hair, {3::smiling|serious}",
      negative: "blurry, lowres", seed: 42, seed_mode: "deck" } }]);
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
    await page.waitForTimeout(800);
    await page.locator(".dfmi").first().screenshot({ path: path.join(OUT, "model_info.png") });
  });

  test("utility nodes", async ({ page }) => {
    const ids = await addNodes(page, [
      { type: "VAEDecodeSave", pos: [400, 220] },
      { type: "LoadVAEDecodeSave", pos: [720, 220] },
      { type: "LoadDiffusionModelCLIP", pos: [1040, 220], widgets: { unet_name: "flux1-dev.safetensors", clip_name1: "clip_l.safetensors" } },
    ]);
    await expect(nodeElement(page, ids[2])).toContainText("flux1-dev.safetensors");
    await shot(page, ids, "utility_nodes.png");
  });
});
