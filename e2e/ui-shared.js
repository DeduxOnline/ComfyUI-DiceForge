// What the browser tests (ui-*.spec.js) share: the DiceForge node types, and ways to reach a prompt field, a model's info, the LoRA Browser's
// cards and the Sampler presets submenu in either node design.

const { expect } = require("@playwright/test");

const ALL_NODES = ["DiceForgeSDXLResolutionList", "DiceForgeResolutionSelector", "DiceForgeCLIPDualTextEncode", "DiceForgeWildcardsToText", "DiceForgeRandomInt", "DiceForgeRandomFloat",
  "DiceForgeRandomLora", "DiceForgeRandomCheckpoint", "DiceForgeRandomDiffusionModel", "DiceForgeRandomImage", "DiceForgeGrid", "DiceForgeRandomSampler",
  "DiceForgeRandomVAE", "DiceForgeLoadVAEDecodeSave", "DiceForgeVAEDecodeSave", "DiceForgeLoadDiffusionModelCLIP", "DiceForgeLoraStack", "DiceForgeXYPlot", "DiceForgeVariationSeed", "DiceForgeAnimaNAG", "DiceForgeHiresUpscale", "DiceForgeDanbooruEnhancer", "DiceForgeWildcardNote"];

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

// The Wildcard Browser in its cards or lines mode (it opens in the one used last). Its mode button gets its label once the list is drawn, so
// that is waited for first: a browser still loading is not taken for the other mode.
async function wildcardMode(dialog, mode) {
  const button = dialog.locator("button.mode");
  await expect(button).toHaveText(/Cards|Lines/);
  if ((await button.textContent()) === (mode === "cards" ? "🃏 Cards" : "📄 Lines")) await button.click();
  await expect(button).toHaveText(mode === "cards" ? "📄 Lines" : "🃏 Cards");
}

// An entry of a LoRA Stack row's ⋯ menu.
async function rowMenu(page, panel, index, text) {
  await panel.locator(".row").nth(index).locator("button.more").click();
  await page.locator(".df-menu button", { hasText: text }).click();
}
module.exports = { ALL_NODES, promptField, lookUp, cardTitles, submenu, clickSubmenu, wildcardMode, rowMenu };
