// End-to-end tests of DiceForge: a real ComfyUI server (server.js) and a real browser. Each worker has its own server, with its own port and
// folder (settings.js), so the tests run side by side, each in any worker: a test must not need the state another test left on its server.
const { defineConfig } = require("@playwright/test");
const { WORKERS, portOf } = require("./settings");

module.exports = defineConfig({
  testDir: ".",
  testMatch: "*.spec.js",
  fullyParallel: true,
  workers: WORKERS,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["html", { open: "never", outputFolder: "report" }]],
  outputDir: "results",
  use: {
    viewport: { width: 1600, height: 1000 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    launchOptions: process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
  },
  // One server per worker: the worker with parallel index n tests the server of slot n (its port and base folder, see settings.js).
  webServer: Array.from({ length: WORKERS }, (_, slot) => ({
    command: "node server.js",
    env: { DICEFORGE_E2E_SLOT: String(slot) },
    url: `http://127.0.0.1:${portOf(slot)}/object_info/DiceForgeLoraStack`, // Ready when DiceForge is loaded, not only when the server answers.
    timeout: 180_000,
    reuseExistingServer: false,
    stdout: "pipe",
    stderr: "pipe",
    gracefulShutdown: { signal: "SIGTERM", timeout: 10_000 },
  })),
});
