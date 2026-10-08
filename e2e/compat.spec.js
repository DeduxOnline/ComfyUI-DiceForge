// Workflows saved with earlier DiceForge versions (e2e/workflows/<version>.json, made from each release by e2e/qa/snapshot.js) open in this
// version, in both node designs: every node type still exists, every widget keeps its value under its name (a widget added, removed or moved
// must not shift the values of the others), the prompt sent to the server keeps every input it had with the same value, and nothing errors.
// What a newer version adds (a widget, an input, a field of a JSON value) is fine. A failure is a workflow of users that breaks: keep it working
// (a migration on loading, like CLIP Dual Text Encode's outputs), or it is a new major version (CHANGELOG). The compat agent
// (.claude/agents/compat.md) looks into failures here.
const { test, expect, openComfy } = require("./helpers");
const { corpus, widgetChanges, promptChanges, load } = require("./qa/compat");

for (const vue of [true, false]) {
  test.describe(vue ? "Old workflows, Nodes 2.0" : "Old workflows, classic nodes", () => {
    test.beforeEach(async ({ page }) => openComfy(page, { vue }));

    if (!corpus().length) {
      test.skip("no released version yet: the first published release adds its workflow (e2e/qa/snapshot.js)", () => {});
    }
    for (const saved of corpus()) {
      test(`a workflow of DiceForge ${saved.diceforge} opens with every node, value and prompt input it had`, async ({ page }) => {
        const now = await load(page, saved.workflow);
        expect(widgetChanges(saved, now), `what DiceForge ${saved.diceforge}'s workflow lost or changed`).toEqual([]);
        expect(promptChanges(saved, now), `what the prompt of DiceForge ${saved.diceforge}'s workflow lost or changed`).toEqual([]);
      });
    }
  });
}

