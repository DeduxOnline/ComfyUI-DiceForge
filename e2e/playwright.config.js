// End-to-end tests of DiceForge: a real ComfyUI server (server.js) and a real browser. The tests share one server and its memory (seed modes,
// grids), so they run one at a time.
const { defineConfig } = require("@playwright/test");
const { URL } = require("./settings");

module.exports = defineConfig({
  testDir: ".",
  testMatch: "*.spec.js",
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["html", { open: "never", outputFolder: "report" }]],
  outputDir: "results",
  use: {
    baseURL: URL,
    viewport: { width: 1600, height: 1000 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    launchOptions: process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
  },
  webServer: {
    command: "node server.js",
    url: `${URL}/object_info/DiceForgeLoraStack`, // Ready when DiceForge is loaded, not only when the server answers.
    timeout: 180_000,
    reuseExistingServer: false,
    stdout: "pipe",
    stderr: "pipe",
    gracefulShutdown: { signal: "SIGTERM", timeout: 10_000 },
  },
});
