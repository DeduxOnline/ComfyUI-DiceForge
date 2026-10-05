// End-to-end through ComfyUI's own queue and server: workflows in the API format run by the real server with DiceForge loaded, and the DiceForge
// server routes. No browser.
const fs = require("fs");
const path = require("path");
const { test, expect, runPrompt, shown, basePath, writeFile } = require("./helpers");
const { MODELS, DOWNLOADS } = require("./fixtures");

const NODES = ["SDXLResolutionListLatent", "ResolutionSelectorRandomLatent", "CLIPTextEncodePositiveNegative", "DiceForgeWildcardsToText", "DiceForgeRandomInt", "DiceForgeRandomFloat",
  "DiceForgeRandomLora", "DiceForgeRandomCheckpoint", "DiceForgeRandomDiffusionModel", "DiceForgeRandomImage", "DiceForgeGrid", "DiceForgeRandomSampler",
  "DiceForgeRandomVAE", "LoadVAEDecodeSave", "VAEDecodeSave", "LoadDiffusionModelCLIP", "DiceForgeLoraStack", "DiceForgeXYPlot", "DiceForgeVariationSeed", "DiceForgeHiresUpscale", "DiceForgeDanbooruEnhancer"];
const clip = (positive, negative = "", { seed = 0, mode = "random" } = {}) => ({
  1: { class_type: "CLIPTextEncodePositiveNegative", inputs: { positive, negative, seed, seed_mode: mode, trim: true } },
  2: { class_type: "PreviewAny", inputs: { source: ["1", 3] } },
  3: { class_type: "PreviewAny", inputs: { source: ["1", 4] } },
});
const randomInt = (inputs) => ({
  1: { class_type: "DiceForgeRandomInt", inputs: { min: 1, max: 5, step: 1, seed: 0, seed_mode: "random", ...inputs } },
  2: { class_type: "PreviewAny", inputs: { source: ["1", 0] } },
});
const pixelSpace = { 10: { class_type: "EmptyImage", inputs: { width: 64, height: 48, batch_size: 2, color: 0xff0000 } }, 11: { class_type: "VAELoader", inputs: { vae_name: "pixel_space" } },
  12: { class_type: "VAEEncode", inputs: { pixels: ["10", 0], vae: ["11", 0] } } };
const outputFiles = (subfolder, prefix) => fs.readdirSync(basePath("output", subfolder)).filter((name) => name.startsWith(prefix));

test.describe("@api workflows and routes", () => {
  test("ComfyUI loads every DiceForge node", async ({ request }) => {
    const info = await (await request.get("/object_info")).json();
    for (const node of NODES) expect(info[node]?.python_module, node).toContain("DiceForge");
    for (const [node, section] of [["SDXLResolutionListLatent", "required"], ["ResolutionSelectorRandomLatent", "optional"]]) {
      const rescale = info[node].input[section].rescale; // Resolution Selector's is optional: a prompt without it gets 100%.
      expect(rescale[1].options.map((option) => option.key)).toEqual(["by percentage", "to Width/Height", "to longest side"]);
      expect(rescale[1].advanced).toBeFalsy(); // In view, not under the advanced inputs.
    }
    expect(info.CLIPTextEncodePositiveNegative.input.required.negative[1].advanced).toBe(true);
  });

  test("CLIP Dual Text Encode fills in wildcards, yaml keys, weights and variables", async ({ request }) => {
    const prompt = "${g={male|female}}__color__ hair, __hair/*__, {2$$__characters/*/outfit__}, __weighted__, __outfit/${g}__";
    for (let seed = 0; seed < 8; seed++) {
      const result = await runPrompt(request, clip(prompt, "not __outfit/${g}__", { seed }));
      expect(result.status).toBe("success");
      const [color, hair, outfitA, outfitB, weighted, outfit] = shown(result, "2").split(", ");
      expect(["red hair", "blue hair", "green hair", "white hair"]).toContain(color);
      expect(["bob cut", "long hair", "blonde hair"]).toContain(hair);
      expect(outfitA).not.toBe(outfitB);
      expect(["blue dress", "white apron", "jeans"]).toEqual(expect.arrayContaining([outfitA, outfitB]));
      expect(["common", "rare"]).toContain(weighted);
      expect(shown(result, "3")).toBe(`not ${outfit}`);
    }
  });

  test("deck deals every wildcard line over runs, combinations counts through all", async ({ request }) => {
    const deck = [];
    for (let seed = 0; seed < 4; seed++) deck.push(shown(await runPrompt(request, clip("__color__", "", { seed, mode: "deck" })), "2"));
    expect(deck.sort()).toEqual(["blue", "green", "red", "white"]);
    const combinations = new Set();
    for (let seed = 0; seed < 8; seed++) combinations.add(shown(await runPrompt(request, clip("__color__ {cat|dog}", "", { seed, mode: "combinations" })), "2"));
    expect(combinations.size).toBe(8);
  });

  test("the same inputs come from the cache, until a wildcard file changes", async ({ request }) => {
    const prompt = clip("__hair/style__", "", { seed: 42 });
    await runPrompt(request, prompt);
    expect((await runPrompt(request, prompt)).cached).toContain("1");
    writeFile("models/wildcards/hair/style.txt", "pixie cut\n");
    const changed = await runPrompt(request, prompt);
    expect(changed.cached).not.toContain("1");
    expect(shown(changed, "2")).toBe("pixie cut");
    writeFile("models/wildcards/hair/style.txt", "bob cut\nlong hair\n");
  });

  test("shuffle remembers between runs on the server, and a seed that came before gives its value again", async ({ request }) => {
    const values = [];
    for (const seed of [901, 47, 3, 1999, 650]) { // Any new seeds (randomize): a whole round without repeats.
      const result = await runPrompt(request, randomInt({ seed, seed_mode: "shuffle" }));
      expect(result.cached).not.toContain("1");
      values.push(shown(result, "2"));
    }
    expect([...values].sort()).toEqual(["1", "2", "3", "4", "5"]);
    const again = await runPrompt(request, randomInt({ seed: 3, seed_mode: "shuffle" }));
    expect(shown(again, "2")).toBe(values[2]);
  });

  test("<lora:...> in the prompt: the tags leave the text, a LoRA that isn't there stops the run with its name", async ({ request }) => {
    const result = await runPrompt(request, clip("1girl, <lora:ink:0.8>, smile", "lowres, <lora:style/ink>"));
    expect(result.status).toBe("success");
    expect([shown(result, "2"), shown(result, "3")]).toEqual(["1girl, smile", "lowres"]);
    const missing = await runPrompt(request, clip("<lora:nope:1> cat"));
    expect(missing.status).toBe("error");
    expect(missing.error).toContain("no LoRA file for <lora:nope>");
  });

  test("a missing wildcard stops the run with a clear message", async ({ request }) => {
    const result = await runPrompt(request, clip("__nope__"));
    expect(result.status).toBe("error");
    expect(result.error).toContain("Wildcard __nope__ not found");
  });

  test("SDXL Resolution List and Resolution Selector make latents of the right size", async ({ request }) => {
    const size = (node) => ({ ...node, 2: { class_type: "PreviewAny", inputs: { source: ["1", 1] } }, 3: { class_type: "PreviewAny", inputs: { source: ["1", 2] } } });
    let result = await runPrompt(request, size({ 1: { class_type: "SDXLResolutionListLatent", inputs: { resolution: "Standard", "resolution.size": "1216 x 832", seed: 0, rescale: "by percentage", "rescale.percent": 100, multiple: 8, batch: 1, seed_mode: "random" } } }));
    expect([shown(result, "2"), shown(result, "3")]).toEqual(["1216", "832"]);
    result = await runPrompt(request, size({ 1: { class_type: "SDXLResolutionListLatent", inputs: { resolution: "Standard", "resolution.size": "1024 x 1024", seed: 0, rescale: "by percentage", "rescale.percent": 150, multiple: 16, batch: 1, seed_mode: "random" } } }));
    expect([shown(result, "2"), shown(result, "3")]).toEqual(["1536", "1536"]); // 150%: each side, 2.25 times the pixels.
    result = await runPrompt(request, size({ 1: { class_type: "SDXLResolutionListLatent", inputs: { resolution: "Standard", "resolution.size": "832 x 1216", seed: 0, rescale: "to longest side", "rescale.longer_side": 1536, multiple: 8, batch: 1, seed_mode: "random" } } }));
    expect([shown(result, "2"), shown(result, "3")]).toEqual(["1048", "1536"]);
    result = await runPrompt(request, size({ 1: { class_type: "SDXLResolutionListLatent", inputs: { resolution: "Standard", "resolution.size": "1216 x 832", seed: 0, rescale: "to Width/Height", "rescale.width": 1920, "rescale.height": 1080, multiple: 8, batch: 1, seed_mode: "random" } } }));
    expect([shown(result, "2"), shown(result, "3")]).toEqual(["1920", "1080"]);
    const listed = new Set();
    for (let seed = 0; seed < 4; seed++) {
      result = await runPrompt(request, size({ 1: { class_type: "SDXLResolutionListLatent", inputs: { resolution: "Random", "resolution.size": "Vertical Listed", seed, rescale: "by percentage", "rescale.percent": 100, multiple: 8, batch: 1, seed_mode: "deck" } } }));
      listed.add(`${shown(result, "2")}x${shown(result, "3")}`);
      expect(result.outputs["1"].dice_forge_last_size[0].group).toBe("Random");
    }
    expect([...listed].sort()).toEqual(["640x1536", "768x1344", "832x1216", "896x1152"]);
    const selector = (inputs) => size({ 1: { class_type: "ResolutionSelectorRandomLatent", inputs: { aspect_ratio: "16:9 (Widescreen)", megapixels: 1.0, seed: 0, multiple: 8, batch: 1, max_aspect: 2.0, seed_mode: "random", ...inputs } } });
    result = await runPrompt(request, selector({})); // Without rescale, as before it existed.
    expect([shown(result, "2"), shown(result, "3")]).toEqual(["1368", "768"]);
    result = await runPrompt(request, selector({ rescale: "by percentage", "rescale.percent": 150 }));
    expect([shown(result, "2"), shown(result, "3")]).toEqual(["2048", "1152"]);
    result = await runPrompt(request, selector({ rescale: "to longest side", "rescale.longer_side": 1920 }));
    expect([shown(result, "2"), shown(result, "3")]).toEqual(["1920", "1080"]);
    result = await runPrompt(request, selector({ rescale: "to Width/Height", "rescale.width": 0, "rescale.height": 1152 }));
    expect([shown(result, "2"), shown(result, "3")]).toEqual(["2048", "1152"]);
    result = await runPrompt(request, size({ 1: { class_type: "ResolutionSelectorRandomLatent", inputs: { aspect_ratio: "Random Chaos Portrait", megapixels: 1.0, seed: 3, multiple: 64, batch: 1, max_aspect: 2.0, seed_mode: "random" } } }));
    const [width, height] = [Number(shown(result, "2")), Number(shown(result, "3"))];
    expect(width % 64).toBe(0);
    expect(height).toBeGreaterThan(width);
    expect(width * height).toBeLessThanOrEqual(1024 * 1024);
  });

  test("a resolution node from the cache still reports its size to the preview", async ({ request }) => {
    const prompt = { 1: { class_type: "SDXLResolutionListLatent", inputs: { resolution: "Random", "resolution.size": "Any Listed", seed: 777, rescale: "by percentage", "rescale.percent": 100, multiple: 8, batch: 1, seed_mode: "random" } },
      2: { class_type: "PreviewAny", inputs: { source: ["1", 1] } } };
    const first = await runPrompt(request, prompt);
    const again = await runPrompt(request, prompt);
    expect(again.cached).toContain("1");
    expect(again.outputs["1"].dice_forge_last_size).toEqual(first.outputs["1"].dice_forge_last_size);
  });

  test("VAE Decode + Save and Load VAE + Decode + Save write PNG files with the workflow", async ({ request }) => {
    let result = await runPrompt(request, { ...pixelSpace, 1: { class_type: "VAEDecodeSave", inputs: { samples: ["12", 0], vae: ["11", 0], filename_prefix: "e2e/vds_%width%x%height%" } } });
    expect(result.status).toBe("success");
    expect(result.outputs["1"].images.map((image) => image.filename)).toEqual(["vds_64x48_00001_.png", "vds_64x48_00002_.png"]);
    const png = fs.readFileSync(basePath("output", "e2e", "vds_64x48_00001_.png"));
    expect(png.includes(Buffer.from("workflow"))).toBe(true);
    expect(png.includes(Buffer.from("diceforge_e2e"))).toBe(true);
    result = await runPrompt(request, { ...pixelSpace, 1: { class_type: "LoadVAEDecodeSave", inputs: { samples: ["12", 0], vae_name: "pixel_space", filename_prefix: "e2e/load_vds" } } });
    expect(result.status).toBe("success");
    expect(outputFiles("e2e", "load_vds_")).toHaveLength(2);
    // image_output: Preview shows without saving, Hide&Save saves without showing, Hide does neither; the vae output feeds the next nodes.
    result = await runPrompt(request, { ...pixelSpace, 1: { class_type: "VAEDecodeSave", inputs: { samples: ["12", 0], vae: ["11", 0], filename_prefix: "e2e/io_preview", image_output: "Preview" } } });
    expect(result.outputs["1"].images.every((image) => image.type === "temp")).toBe(true);
    expect(outputFiles("e2e", "io_preview")).toHaveLength(0);
    result = await runPrompt(request, { ...pixelSpace, 1: { class_type: "LoadVAEDecodeSave", inputs: { samples: ["12", 0], vae_name: "pixel_space", filename_prefix: "e2e/io_quiet", image_output: "Hide&Save" } } });
    expect(result.status).toBe("success");
    expect(result.outputs["1"]?.images ?? []).toHaveLength(0);
    expect(outputFiles("e2e", "io_quiet")).toHaveLength(2);
    result = await runPrompt(request, { ...pixelSpace,
      1: { class_type: "LoadVAEDecodeSave", inputs: { samples: ["12", 0], vae_name: "pixel_space", filename_prefix: "e2e/io_hidden", image_output: "Hide" } },
      2: { class_type: "VAEEncode", inputs: { pixels: ["1", 0], vae: ["1", 1] } }, // The loaded VAE, passed on.
      3: { class_type: "VAEDecodeSave", inputs: { samples: ["2", 0], vae: ["1", 1], filename_prefix: "e2e/io_again_%width%x%height%" } } });
    expect(result.status).toBe("success");
    expect(outputFiles("e2e", "io_hidden")).toHaveLength(0);
    expect(outputFiles("e2e", "io_again_64x48")).toHaveLength(2);
    expect((await request.post("/prompt", { data: { prompt: { ...pixelSpace, 1: { class_type: "VAEDecodeSave", inputs: { samples: ["12", 0], vae: ["11", 0], filename_prefix: "x", image_output: "Sideways" } } } } })).status()).toBe(400);
  });

  test("Dice Grid collects runs and saves the finished grid", async ({ request }) => {
    const grid = (label) => ({ 1: { class_type: "EmptyImage", inputs: { width: 64, height: 64, batch_size: 1, color: 0x3366cc } },
      2: { class_type: "DiceForgeGrid", inputs: { image: ["1", 0], label, count: 3, columns: 0, cell_width: 64, save: true, filename_prefix: "e2e/grid", name: "e2e", new_grid: false, legend: "E2E grid", legend_position: "top", numbered: false } },
      3: { class_type: "PreviewAny", inputs: { source: ["2", 1] } } });
    const cells = [];
    for (const label of ["a", "b", "c"]) cells.push(shown(await runPrompt(request, grid(label)), "3"));
    expect(cells).toEqual(["1", "2", "3"]);
    expect(outputFiles("e2e", "grid_")).toHaveLength(1);
  });

  test("Random Image loads the images of a folder like Load Image", async ({ request }) => {
    const names = [];
    for (let seed = 0; seed < 2; seed++) {
      const result = await runPrompt(request, { 1: { class_type: "DiceForgeRandomImage", inputs: { folder: "e2e", seed, seed_mode: "deck", path: "" } },
        2: { class_type: "PreviewAny", inputs: { source: ["1", 2] } }, 3: { class_type: "GetImageSize", inputs: { image: ["1", 0] } }, 4: { class_type: "PreviewAny", inputs: { source: ["3", 0] } } });
      expect(result.status).toBe("success");
      names.push(`${shown(result, "2")}:${shown(result, "4")}`);
    }
    expect(names.sort()).toEqual(["e2e/blue.png:16", "e2e/red.png:32"]);
  });

  test("Random Sampler's outputs are accepted by KSampler's lists", async ({ request }) => {
    const result = await runPrompt(request, { 1: { class_type: "DiceForgeRandomSampler", inputs: { samplers: "euler", schedulers: "karras", seed: 0, seed_mode: "random" } },
      2: { class_type: "KSampler", inputs: { sampler_name: ["1", 0], scheduler: ["1", 1], seed: 0, steps: 1, cfg: 1, denoise: 1 } },
      3: { class_type: "PreviewAny", inputs: { source: ["2", 0] } } });
    const errors = result.rejected.node_errors["2"].errors.map((error) => `${error.type} ${error.extra_info?.input_name ?? ""}`);
    expect(errors.join()).toContain("required_input_missing model"); // No model in this test: only the links are checked.
    expect(errors.join()).not.toContain("return_type_mismatch");
  });

  test("XY Plot: KSampler takes its outputs; each index is one cell, and Dice Grid finishes the grid after the last", async ({ request }) => {
    const xy = (index) => ({ index, x_type: "cfg", x_values: "4, 5", y_type: "sampler", y_values: "euler, dpmpp_2m", seed: 3, steps: 2, cfg: 6, sampler_name: "euler",
      scheduler: "normal", denoise: 1, lora_name: "None", lora_strength: 1 });
    const linked = await runPrompt(request, { 1: { class_type: "DiceForgeXYPlot", inputs: xy(0) },
      2: { class_type: "KSampler", inputs: { seed: ["1", 2], steps: ["1", 3], cfg: ["1", 4], sampler_name: ["1", 5], scheduler: ["1", 6], denoise: ["1", 7] } },
      3: { class_type: "PreviewAny", inputs: { source: ["2", 0] } } });
    const errors = linked.rejected.node_errors["2"].errors.map((error) => `${error.type} ${error.extra_info?.input_name ?? ""}`);
    expect(errors.join()).toContain("required_input_missing model"); // No model here: only the links are checked.
    expect(errors.join()).not.toContain("return_type_mismatch");
    const grid = (index) => ({ 1: { class_type: "DiceForgeXYPlot", inputs: xy(index) }, 2: { class_type: "EmptyImage", inputs: { width: 64, height: 64, batch_size: 1, color: 0x33cc66 } },
      3: { class_type: "DiceForgeGrid", inputs: { image: ["2", 0], label: ["1", 8], row_label: ["1", 9], count: ["1", 10], columns: ["1", 11], new_grid: ["1", 12], cell_width: 64, save: true,
        filename_prefix: "e2e/xy", name: "xy", legend: "", legend_position: "top", numbered: false } },
      4: { class_type: "PreviewAny", inputs: { source: ["1", 8] } }, 5: { class_type: "PreviewAny", inputs: { source: ["3", 1] } } });
    const runs = [];
    for (let index = 0; index < 4; index++) {
      const result = await runPrompt(request, grid(index));
      expect(result.status).toBe("success");
      runs.push(`${shown(result, "4")}=${shown(result, "5")}`);
    }
    expect(runs).toEqual(["CFG 4=1", "CFG 5=2", "CFG 4=3", "CFG 5=4"]);
    expect(outputFiles("e2e", "xy_")).toHaveLength(1);
    const bad = await runPrompt(request, { 1: { class_type: "DiceForgeXYPlot", inputs: { ...xy(0), x_values: "4, x" } }, 2: { class_type: "PreviewAny", inputs: { source: ["1", 8] } } });
    expect(JSON.stringify(bad.rejected ?? bad.error)).toContain("not a number");
  });

  test("Wildcards to Text fills in a prompt from the seed, as CLIP Dual Text Encode does", async ({ request }) => {
    const prompt = (seed) => ({
      1: { class_type: "DiceForgeWildcardsToText", inputs: { text: "a __color__ car, {big|small}", seed, seed_mode: "deck", trim: true } },
      2: { class_type: "CLIPTextEncodePositiveNegative", inputs: { positive: "a __color__ car, {big|small}", negative: "", seed, seed_mode: "deck", trim: true } },
      3: { class_type: "PreviewAny", inputs: { source: ["1", 0] } }, 4: { class_type: "PreviewAny", inputs: { source: ["2", 3] } },
    });
    for (const seed of [0, 1, 2]) {
      const result = await runPrompt(request, prompt(seed));
      expect(result.status, result.error).toBe("success");
      expect(shown(result, "3")).toMatch(/^a (red|blue|green|white) car, (big|small)$/);
      expect(shown(result, "3")).toBe(shown(result, "4")); // The same text for the same seed.
    }
  });

  test("Variation Seed's model goes to KSampler and its label to Dice Grid", async ({ request }) => {
    const result = await runPrompt(request, {
      1: { class_type: "DiceForgeVariationSeed", inputs: { variation_seed: 3, variation_strength: 0.1 } },
      2: { class_type: "KSampler", inputs: { model: ["1", 0], seed: 0, steps: 1, cfg: 1, sampler_name: "euler", scheduler: "normal", denoise: 1 } },
      3: { class_type: "EmptyImage", inputs: { width: 64, height: 64, batch_size: 1, color: 0 } },
      4: { class_type: "DiceForgeGrid", inputs: { image: ["3", 0], label: ["1", 1], count: 0, columns: 0, cell_width: 64, save: false, filename_prefix: "e2e/var", name: "var",
        new_grid: false, legend: "", legend_position: "top", numbered: false } },
      5: { class_type: "PreviewAny", inputs: { source: ["2", 0] } },
    });
    const errors = Object.values(result.rejected.node_errors).flatMap((node) => node.errors.map((error) => `${error.type} ${error.extra_info?.input_name ?? ""}`));
    expect(errors.join()).toContain("required_input_missing model"); // No checkpoint here: only the links are checked.
    expect(errors.join()).not.toContain("return_type_mismatch");
  });

  test("HiresFix (Load VAE) rescales the image, encodes it with the VAE from its list and passes both on", async ({ request }) => {
    const result = await runPrompt(request, {
      1: { class_type: "EmptyImage", inputs: { width: 64, height: 48, batch_size: 1, color: 0x3366cc } },
      2: { class_type: "DiceForgeHiresUpscale", inputs: { image: ["1", 0], model_name: "None", rescale_after_model: true, rescale_method: "lanczos", rescale: "by percentage",
        "rescale.percent": 200, crop: "disabled", vae_name: "pixel_space", image_output: "Preview", filename_prefix: "e2e/hires" } },
      3: { class_type: "GetImageSize", inputs: { image: ["2", 0] } },
      4: { class_type: "PreviewAny", inputs: { source: ["3", 0] } },
      5: { class_type: "PreviewAny", inputs: { source: ["3", 1] } },
      6: { class_type: "VAEDecode", inputs: { samples: ["2", 1], vae: ["2", 2] } },
      7: { class_type: "GetImageSize", inputs: { image: ["6", 0] } },
      8: { class_type: "PreviewAny", inputs: { source: ["7", 0] } },
    });
    expect(result.status, result.error).toBe("success");
    expect([shown(result, "4"), shown(result, "5"), shown(result, "8")]).toEqual(["128", "96", "128"]); // 200%, and the latent decodes back to that size.
    expect(result.outputs["2"].images).toHaveLength(1); // Preview: shown on the node.
  });

  test("Danbooru Tag Enhancer adds the tags of a Danbooru post (a general one) to the prompt, and fixed mode takes the post of post_ids", async ({ request }) => {
    const prompt = (mode = "random", ids = "") => ({ 1: { class_type: "DiceForgeDanbooruEnhancer", inputs: { tags: "hatsune miku, masterpiece", source: "danbooru", rating: "general",
      mode, post_ids: ids, posts: 1, max_tags: 15, include_general: true, include_appearance: true, include_clothes: true, include_background: true,
      include_count: true, include_character: false, include_copyright: false, include_artist: false, exclude: "", position: "after", wildcard_seed: 0 } },
      2: { class_type: "PreviewAny", inputs: { source: ["1", 0] } }, 3: { class_type: "PreviewAny", inputs: { source: ["1", 2] } } });
    const result = await runPrompt(request, prompt());
    expect(result.status, result.error).toBe("success");
    expect(shown(result, "2")).toBe("hatsune miku, masterpiece, 1girl, smile, twintails"); // Post 101: rating:g leaves the explicit one out.
    expect(shown(result, "3")).toMatch(/\/posts\/101$/);
    expect(result.outputs["1"].dice_forge_danbooru[0]).toMatchObject({ post_ids: "101", search: "hatsune_miku rating:g", mode: "random", // Shown on the node.
      posts: [{ id: 101, rating: "g", preview: expect.stringContaining("/image/danbooru/101.png") }] }); // masterpiece: no post has it.
    expect((await runPrompt(request, prompt())).status).toBe("success"); // The same inputs run again: a new post each time, never from the cache.
    const fixed = await runPrompt(request, prompt("fixed", "102"));
    expect(fixed.status, fixed.error).toBe("success");
    expect(shown(fixed, "2")).toBe("hatsune miku, masterpiece, 1girl, nude"); // Your pick: no search, the rating doesn't matter.
    expect((await runPrompt(request, prompt("fixed", ""))).error).toContain("fixed mode needs post_ids");
  });

  test("Danbooru Tag Enhancer in fixed mode comes from the cache until a wildcard file changes; it fits between two CLIP Dual Text Encodes", async ({ request }) => {
    writeFile("models/wildcards/e2e_booru.txt", "hatsune miku\n");
    const chain = () => ({
      1: { class_type: "CLIPTextEncodePositiveNegative", inputs: { positive: "__e2e_booru__, {masterpiece|masterpiece}", negative: "", seed: 0, seed_mode: "random", trim: true } },
      2: { class_type: "DiceForgeDanbooruEnhancer", inputs: { tags: ["1", 3], source: "danbooru", rating: "general", mode: "fixed", post_ids: "101", posts: 1,
        max_tags: 15, include_general: true, include_appearance: true, include_clothes: true, include_background: true, include_count: true,
        include_character: false, include_copyright: false, include_artist: false, exclude: "", position: "after", wildcard_seed: 7 } },
      3: { class_type: "CLIPTextEncodePositiveNegative", inputs: { positive: ["2", 0], negative: "", seed: 0, seed_mode: "random", trim: true } },
      4: { class_type: "PreviewAny", inputs: { source: ["3", 3] } },
    });
    const first = await runPrompt(request, chain());
    expect(first.status, first.error).toBe("success");
    expect(shown(first, "4")).toBe("hatsune miku, masterpiece, 1girl, smile, twintails"); // The first node's text, the post's tags, through the second.
    expect((await runPrompt(request, chain())).cached).toContain("2"); // Fixed: the same inputs, from the cache.
    writeFile("models/wildcards/e2e_booru.txt", "hatsune miku, smile\n");
    const changed = await runPrompt(request, chain());
    expect(changed.cached).not.toContain("2");
    expect(shown(changed, "4")).toBe("hatsune miku, smile, masterpiece, 1girl, twintails"); // smile is in the prompt now: not added again.
  });

  test("Danbooru Tag Enhancer takes Safebooru posts with source safebooru", async ({ request }) => {
    const prompt = { 1: { class_type: "DiceForgeDanbooruEnhancer", inputs: { tags: "hatsune miku", source: "safebooru", rating: "general", mode: "random", post_ids: "",
      posts: 1, max_tags: 15, include_general: true, include_appearance: true, include_clothes: true, include_background: true, include_count: true,
      include_character: false, include_copyright: false, include_artist: false, exclude: "", position: "after", wildcard_seed: 0 } },
      2: { class_type: "PreviewAny", inputs: { source: ["1", 0] } }, 3: { class_type: "PreviewAny", inputs: { source: ["1", 2] } } };
    const result = await runPrompt(request, prompt);
    expect(result.status, result.error).toBe("success");
    expect(shown(result, "2")).toMatch(/^hatsune miku, (1girl, smile, twintails|smile, 1girl, twintails|1girl, twintails, smile)$/); // Its general tags.
    expect(shown(result, "3")).toMatch(/\/safebooru\/index\.php\?page=post&s=view&id=301$/);
    expect(result.outputs["1"].dice_forge_danbooru[0]).toMatchObject({ site: "safebooru", search: "hatsune_miku rating:safe",
      posts: [{ id: 301, rating: "g", safe: true, preview: expect.stringContaining("/safebooru/thumbnails/301/thumbnail_picture.jpg") }] });
  });

  test("Danbooru Tag Enhancer takes e621 posts with source e621 (its ratings, its species tags)", async ({ request }) => {
    const prompt = (rating, mode = "random", ids = "") => ({ 1: { class_type: "DiceForgeDanbooruEnhancer", inputs: { tags: "fox, anthro", source: "e621", rating,
      mode, post_ids: ids, posts: 2, max_tags: 15, include_general: true, include_appearance: true, include_clothes: true, include_background: true,
      include_count: true, include_character: false, include_copyright: false, include_artist: false, exclude: "", position: "after", wildcard_seed: 0 } },
      2: { class_type: "PreviewAny", inputs: { source: ["1", 0] } }, 3: { class_type: "PreviewAny", inputs: { source: ["1", 2] } } });
    const result = await runPrompt(request, prompt("general"));
    expect(result.status, result.error).toBe("success");
    expect(shown(result, "2")).toBe("fox, anthro, solo, grin, canine"); // Post 201: e621's safe; its species too.
    expect(shown(result, "3")).toMatch(/\/e621\/posts\/201$/);
    expect(result.outputs["1"].dice_forge_danbooru[0]).toMatchObject({ site: "e621", search: "fox anthro rating:s", post_ids: "201",
      posts: [{ id: 201, rating: "s", rating_name: "safe", safe: true, preview: expect.stringContaining("/image/e621/201.png") }] });
    const explicit = await runPrompt(request, prompt("questionable + explicit"));
    expect(explicit.status, explicit.error).toBe("success");
    expect(explicit.outputs["1"].dice_forge_danbooru[0]).toMatchObject({ search: "fox anthro -rating:s", posts: [{ id: 202, safe: false, preview: "" }] });
    const fixed = await runPrompt(request, prompt("general", "fixed", "201"));
    expect(fixed.status, fixed.error).toBe("success");
    expect(shown(fixed, "2")).toBe("fox, anthro, solo, grin, canine");
  });

  test("Wildcard Browser routes", async ({ request }) => {
    const list = await (await request.get("/diceforge/wildcards")).json();
    const names = list.files.map((file) => file.name);
    expect(names).toEqual(expect.arrayContaining(["color", "hair/style", "characters/alice/outfit", "outfit/male"]));
    expect(list.files.find((file) => file.name === "characters/alice/outfit").yaml).toBe("pack.yaml");
    expect((await request.post("/diceforge/wildcards/file", { data: { name: "e2e/new list", text: "one\ntwo" } })).ok()).toBe(true);
    expect(fs.readFileSync(basePath("models", "wildcards", "e2e", "new list.txt"), "utf8")).toBe("one\ntwo\n");
    const result = await runPrompt(request, clip("__e2e/new list__"));
    expect(["one", "two"]).toContain(shown(result, "2"));
    expect((await request.post("/diceforge/wildcards/file", { data: { name: "../escape", text: "x" } })).status()).toBe(400);
  });

  test("Wildcard files: create, read, update, rename and delete", async ({ request }) => {
    const file = (...parts) => basePath("models", "wildcards", ...parts);
    expect((await request.post("/diceforge/wildcards/file", { data: { name: "e2e_crud/fruit", text: "apple", create: true } })).ok()).toBe(true);
    expect((await request.post("/diceforge/wildcards/file", { data: { name: "e2e_crud/fruit", text: "", create: true } })).status()).toBe(409);
    expect(await (await request.get("/diceforge/wildcards/file?name=e2e_crud/fruit")).json()).toMatchObject({ text: "apple" });
    expect((await request.post("/diceforge/wildcards/file", { data: { name: "e2e_crud/fruit", text: "apple\npear" } })).ok()).toBe(true);
    const renamed = await request.post("/diceforge/wildcards/rename", { data: { name: "e2e_crud/fruit", to: "e2e_crud_moved/fruits" } });
    expect(await renamed.json()).toMatchObject({ renamed: "e2e_crud/fruit", to: "e2e_crud_moved/fruits" });
    expect(fs.existsSync(file("e2e_crud"))).toBe(false); // The folder left empty went too.
    expect(fs.readFileSync(file("e2e_crud_moved", "fruits.txt"), "utf8")).toBe("apple\npear\n");
    expect(["apple", "pear"]).toContain(shown(await runPrompt(request, clip("__e2e_crud_moved/fruits__")), "2")); // The node finds the new name.
    expect((await request.post("/diceforge/wildcards/rename", { data: { name: "e2e_crud_moved/fruits", to: "color" } })).status()).toBe(409);
    expect((await request.post("/diceforge/wildcards/rename", { data: { name: "characters/alice/outfit", to: "x" } })).status()).toBe(400); // yaml
    expect((await request.delete("/diceforge/wildcards/file?name=e2e_crud_moved/fruits")).ok()).toBe(true);
    expect(fs.existsSync(file("e2e_crud_moved"))).toBe(false);
    expect((await request.get("/diceforge/wildcards/file?name=e2e_crud_moved/fruits")).status()).toBe(404);
    expect((await request.delete("/diceforge/wildcards/file?name=e2e_crud_moved/fruits")).status()).toBe(404);
    const names = (await (await request.get("/diceforge/wildcards")).json()).files.map((entry) => entry.name);
    expect(names.filter((name) => name.startsWith("e2e_crud"))).toEqual([]);
  });

  test("Model info looks the file up on Civitai (the stand-in) and the browser shows it", async ({ request }) => {
    const info = await (await request.get("/diceforge/model-info?kind=loras&file=style/ink.safetensors")).json();
    expect(info.civitai).toMatchObject({ found: true, model_name: "Ink", base_model: "Illustrious", trigger_words: ["ink style", "lineart"] });
    expect(info.sha256).toHaveLength(64);
    const unknown = await (await request.get("/diceforge/model-info?kind=loras&file=detail.safetensors")).json();
    expect(unknown.civitai.found).toBe(false);
    const browser = await (await request.get("/diceforge/model-browser?kind=loras")).json();
    const cards = Object.fromEntries(browser.files.map((entry) => [entry.file.replace(/\\/g, "/"), entry]));
    expect(Object.keys(cards).sort()).toEqual(Object.keys(MODELS).filter((file) => file.startsWith("loras/")).map((file) => file.slice(6)).sort());
    expect(cards["style/ink.safetensors"]).toMatchObject({ checked: true, found: true, name: "Ink - v2", base_model: "Illustrious" });
    expect(cards["detail.safetensors"].preview).toBe(true);
    expect((await request.get("/diceforge/model-preview?kind=loras&file=detail.safetensors")).headers()["content-type"]).toContain("image/png");
    const bases = await (await request.post("/diceforge/model-bases", { data: { items: [{ kind: "loras", file: "style/ink.safetensors" }, { kind: "loras", file: "style/pony_glow.safetensors" }] } })).json();
    expect(bases.bases).toEqual(["Illustrious", null]); // Pony not looked up yet.
  });

  test("LoRA files: found and downloaded from Civitai, renamed, deleted", async ({ request }) => {
    const loras = (...parts) => basePath("models", "loras", ...parts);
    const found = await (await request.get("/diceforge/civitai/search?kind=loras&query=")).json();
    const byName = Object.fromEntries(found.items.map((item) => [item.name, item]));
    expect(byName.Neon.versions.map((version) => [version.name, version.base_model, version.installed])).toEqual([["v2", "Illustrious", null], ["v1", "SDXL 1.0", null]]);
    expect(byName.Ink.versions[0].installed).toBe("style/ink.safetensors"); // Already here: known by its hash.
    const job = await (await request.post("/diceforge/civitai/download", { data: { kind: "loras", version_id: 502, folder: "e2e_civitai" } })).json();
    expect(job).toMatchObject({ status: "downloading", file: "e2e_civitai/neon_glow_v1.safetensors" });
    await expect.poll(async () => (await (await request.get("/diceforge/civitai/downloads")).json()).jobs.find((entry) => entry.id === job.id).status).toBe("done");
    expect(fs.readFileSync(loras("e2e_civitai", "neon_glow_v1.safetensors"), "utf8")).toBe(DOWNLOADS[502]);
    expect(fs.existsSync(loras("e2e_civitai", "neon_glow_v1.preview.png"))).toBe(true);
    const card = (await (await request.get("/diceforge/model-browser?kind=loras")).json()).files.find((entry) => entry.file.replace(/\\/g, "/") === "e2e_civitai/neon_glow_v1.safetensors");
    expect(card).toMatchObject({ found: true, checked: true, preview: true, name: "Neon - v1", base_model: "SDXL 1.0", trigger_words: ["neon glow"] });
    const loraNode = await (await request.get("/object_info/DiceForgeRandomLora")).json(); // ComfyUI's lists have it, without a restart.
    expect(JSON.stringify(loraNode.DiceForgeRandomLora.input)).toContain("e2e_civitai");
    expect((await request.post("/diceforge/civitai/download", { data: { version_id: 502, folder: "e2e_civitai" } })).status()).toBe(409);
    const renamed = await (await request.post("/diceforge/models/rename", { data: { kind: "loras", file: "e2e_civitai/neon_glow_v1.safetensors", to: "e2e_civitai_moved/neon" } })).json();
    expect(renamed).toEqual({ renamed: "e2e_civitai/neon_glow_v1.safetensors", to: "e2e_civitai_moved/neon.safetensors" });
    expect(fs.existsSync(loras("e2e_civitai"))).toBe(false);
    expect(fs.readdirSync(loras("e2e_civitai_moved")).sort()).toEqual(["neon.preview.png", "neon.safetensors"]);
    const info = await (await request.get("/diceforge/model-info?kind=loras&file=e2e_civitai_moved/neon.safetensors")).json();
    expect(info.civitai).toMatchObject({ found: true, model_name: "Neon" }); // Its info moved with it.
    expect((await request.post("/diceforge/models/rename", { data: { kind: "loras", file: "e2e_civitai_moved/neon.safetensors", to: "style/ink" } })).status()).toBe(409);
    expect((await request.delete("/diceforge/models/file?kind=loras&file=e2e_civitai_moved/neon.safetensors")).ok()).toBe(true);
    expect(fs.existsSync(loras("e2e_civitai_moved"))).toBe(false);
    expect((await request.delete("/diceforge/models/file?kind=loras&file=e2e_civitai_moved/neon.safetensors")).status()).toBe(404);
    expect((await request.get("/diceforge/civitai/key")).ok()).toBe(true);
  });

  test("Checkpoint and diffusion model files: Civitai's Checkpoints, downloaded, renamed, deleted", async ({ request }) => {
    for (const kind of ["checkpoints", "diffusion_models"]) {
      const found = await (await request.get(`/diceforge/civitai/search?kind=${kind}`)).json();
      expect(found.items.map((item) => item.name)).toEqual(["Studio XL"]); // Checkpoint type only, for both.
      const job = await (await request.post("/diceforge/civitai/download", { data: { kind, version_id: 601, folder: "e2e_civitai" } })).json();
      await expect.poll(async () => (await (await request.get("/diceforge/civitai/downloads")).json()).jobs.find((entry) => entry.id === job.id).status).toBe("done");
      expect(fs.readFileSync(basePath("models", kind, "e2e_civitai", "studio_xl.safetensors"), "utf8")).toBe(DOWNLOADS[601]);
      const renamed = await (await request.post("/diceforge/models/rename", { data: { kind, file: "e2e_civitai/studio_xl.safetensors", to: "e2e_studio" } })).json();
      expect(renamed.to).toBe("e2e_studio.safetensors");
      const card = (await (await request.get(`/diceforge/model-browser?kind=${kind}`)).json()).files.find((entry) => entry.file === "e2e_studio.safetensors");
      expect(card).toMatchObject({ found: true, name: "Studio XL - v1", base_model: "SDXL 1.0", preview: true });
      expect((await request.delete(`/diceforge/models/file?kind=${kind}&file=e2e_studio.safetensors`)).ok()).toBe(true);
      expect(fs.existsSync(basePath("models", kind, "e2e_civitai"))).toBe(false);
    }
    expect((await request.post("/diceforge/civitai/download", { data: { kind: "checkpoints", version_id: 501 } })).status()).toBe(400); // A LoRA is no checkpoint.
  });

  test("LoRA Stack presets are saved as files and listed", async ({ request }) => {
    const stack = { rows: [{ lora: "style/ink.safetensors", strength: 0.8, random: true, min: 0.5, max: 0.9 }], groups: {}, separate_clip: false };
    expect((await request.post("/diceforge/lora-presets", { data: { name: "e2e set", stack } })).ok()).toBe(true);
    expect(fs.existsSync(basePath("user", "DiceForge", "lora_presets", "e2e set.json"))).toBe(true);
    const listing = await (await request.get("/diceforge/lora-presets")).json();
    expect(listing.presets.map((preset) => preset.name)).toContain("e2e set");
    expect((await request.post("/diceforge/lora-presets", { data: { name: "e2e set", stack } })).status()).toBe(409);
    expect((await request.delete("/diceforge/lora-presets?name=e2e%20set")).ok()).toBe(true);
  });
});
