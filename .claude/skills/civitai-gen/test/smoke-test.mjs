#!/usr/bin/env node

// smoke-test.mjs — Smoke tests for civitai-gen skill
//
// Exercises each generate.mjs command against the live API and validates output.
//
// Usage:
//   node test/smoke-test.mjs              # Full suite (spends ~8 buzz)
//   node test/smoke-test.mjs --readonly   # Safe: only tests that don't spend buzz
//   node test/smoke-test.mjs --verbose    # Show full output on failures
//   node test/smoke-test.mjs --keep       # Don't clean up temp output dirs
//
// Exit code: 0 if all pass, 1 if any fail.

import { execFile } from 'child_process';
import { existsSync, rmSync, readFileSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { tmpdir } from 'os';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = join(__dirname, '..');
const GENERATE = join(SKILL_DIR, 'generate.mjs');

// ---------------------------------------------------------------------------
// CLI args
// ---------------------------------------------------------------------------
const args = process.argv.slice(2);
const READONLY = args.includes('--readonly');
const VERBOSE = args.includes('--verbose');
const KEEP = args.includes('--keep');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const tempDirs = [];

function makeTempDir(label) {
  const dir = join(tmpdir(), `civitai-gen-test-${label}-${Date.now()}`);
  mkdirSync(dir, { recursive: true });
  tempDirs.push(dir);
  return dir;
}

function run(args, opts = {}) {
  return new Promise((resolve) => {
    const timeout = opts.timeout || 120000;
    execFile('node', [GENERATE, ...args], { timeout, maxBuffer: 1024 * 1024 }, (err, stdout, stderr) => {
      resolve({
        exitCode: err ? err.code || 1 : 0,
        stdout: stdout?.toString() || '',
        stderr: stderr?.toString() || '',
        error: err,
      });
    });
  });
}

function parseJson(str) {
  try {
    return JSON.parse(str);
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Test framework — register tests, run sequentially in main()
// ---------------------------------------------------------------------------
const tests = [];
const results = [];
let totalBuzz = 0;

function test(name, fn, opts = {}) {
  tests.push({ name, fn, readonly: opts.readonly || false });
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function assertJson(str, label) {
  const obj = parseJson(str);
  assert(obj !== null, `${label}: Expected valid JSON, got: ${str.slice(0, 200)}`);
  return obj;
}

// ---------------------------------------------------------------------------
// Shared state (for tests that depend on prior results)
// ---------------------------------------------------------------------------
let submittedWorkflowId = null;
let submitOutDir = null;

// ---------------------------------------------------------------------------
// Tests: Read-only (0 buzz)
// ---------------------------------------------------------------------------

test('help: shows usage without error', async () => {
  const r = await run([]);
  assert(r.exitCode === 0, `Expected exit 0, got ${r.exitCode}`);
  assert(r.stdout.includes('generate.mjs'), 'Help output should mention generate.mjs');
  assert(r.stdout.includes('COMMANDS'), 'Help output should list commands');
  assert(r.stdout.includes('VIDEO GENERATION'), 'Help should include video section');
}, { readonly: true });

test('help: --help flag', async () => {
  const r = await run(['--help']);
  assert(r.exitCode === 0, `Expected exit 0, got ${r.exitCode}`);
  assert(r.stdout.includes('COMMANDS'), 'Help output should list commands');
}, { readonly: true });

test('engines: human-readable output', async () => {
  const r = await run(['engines']);
  assert(r.exitCode === 0, `Expected exit 0, got ${r.exitCode}: ${r.stderr}`);
  assert(r.stderr.includes('Video Generation Engines'), 'Should show engines header');
  assert(r.stderr.includes('veo3'), 'Should list veo3 engine');
  assert(r.stderr.includes('Processes:'), 'Should show process info');
}, { readonly: true });

test('engines: --json output', async () => {
  const r = await run(['engines', '--json']);
  assert(r.exitCode === 0, `Expected exit 0, got ${r.exitCode}`);
  const data = assertJson(r.stdout, 'engines --json');
  const engines = data.engines || data;
  assert(Array.isArray(engines), 'JSON output should contain engines array');
  assert(engines.length > 0, 'Should have at least one engine');

  const veo3 = engines.find((e) => e.engine === 'veo3');
  assert(veo3, 'Should include veo3');
  assert(Array.isArray(veo3.processes), 'veo3 should have processes array');
  assert(veo3.processes.includes('txt2vid'), 'veo3 should support txt2vid');
  assert(veo3.label === 'Google VEO 3', `veo3 label should be "Google VEO 3", got "${veo3.label}"`);
}, { readonly: true });

test('cost: image estimation', async () => {
  const r = await run(['cost', '--prompt', 'test cat', '-n', '4']);
  assert(r.exitCode === 0, `Expected exit 0, got ${r.exitCode}: ${r.stderr}`);
  const data = assertJson(r.stdout, 'cost image');
  assert(data.type === 'image', `Expected type "image", got "${data.type}"`);
  assert(data.steps === 1, `Expected 1 step, got ${data.steps}`);
  assert(data.totalMedia === 4, `Expected 4 media, got ${data.totalMedia}`);
  assert(typeof data.cost.total === 'number', 'Cost total should be a number');
  assert(data.cost.total > 0, `Cost should be > 0, got ${data.cost.total}`);
  assert(typeof data.insufficientBuzz === 'boolean', 'insufficientBuzz should be boolean');
  assert(typeof data.ready === 'boolean', 'ready should be boolean');
}, { readonly: true });

test('cost: video estimation', async () => {
  const r = await run(['cost', '--engine', 'veo3', '--prompt', 'test robot', '--duration', '4', '--no-audio']);
  assert(r.exitCode === 0, `Expected exit 0, got ${r.exitCode}: ${r.stderr}`);
  const data = assertJson(r.stdout, 'cost video');
  assert(data.type === 'video', `Expected type "video", got "${data.type}"`);
  assert(data.steps === 1, `Expected 1 step, got ${data.steps}`);
  assert(data.totalMedia === 1, `Expected 1 media, got ${data.totalMedia}`);
  assert(data.cost.total > 0, `Video cost should be > 0, got ${data.cost.total}`);
}, { readonly: true });

test('cost: multi-prompt estimation', async () => {
  const r = await run(['cost', '--prompt', 'cat', '--prompt', 'dog', '--prompt', 'bird', '-n', '2']);
  assert(r.exitCode === 0, `Expected exit 0, got ${r.exitCode}: ${r.stderr}`);
  const data = assertJson(r.stdout, 'cost multi-prompt');
  assert(data.steps === 3, `Expected 3 steps, got ${data.steps}`);
  assert(data.totalMedia === 6, `Expected 6 media (3 prompts x 2), got ${data.totalMedia}`);
}, { readonly: true });

test('cost: bulk JSON estimation', async () => {
  const bulkDir = makeTempDir('bulk');
  const bulkFile = join(bulkDir, 'test-bulk.json');
  const { writeFileSync: wf } = await import('fs');
  wf(bulkFile, JSON.stringify([
    { prompt: 'a cat', quantity: 2, label: 'cat' },
    { prompt: 'a dog', quantity: 3, label: 'dog' },
  ]));

  const r = await run(['cost', '--bulk', bulkFile]);
  assert(r.exitCode === 0, `Expected exit 0, got ${r.exitCode}: ${r.stderr}`);
  const data = assertJson(r.stdout, 'cost bulk');
  assert(data.steps === 2, `Expected 2 steps, got ${data.steps}`);
  assert(data.totalMedia === 5, `Expected 5 media, got ${data.totalMedia}`);
}, { readonly: true });

test('error: missing prompt', async () => {
  const r = await run(['cost']);
  assert(r.exitCode !== 0, 'Should fail with no prompt');
  assert(r.stderr.includes('No jobs'), 'Should mention no jobs');
}, { readonly: true });

test('error: unknown command', async () => {
  const r = await run(['foobar']);
  assert(r.exitCode !== 0, 'Should fail with unknown command');
  assert(r.stderr.includes('Unknown command'), 'Should say unknown command');
}, { readonly: true });

test('status: missing workflow-id', async () => {
  const r = await run(['status']);
  assert(r.exitCode !== 0, 'Should fail without workflow-id');
  assert(r.stderr.includes('--workflow-id'), 'Should mention --workflow-id');
}, { readonly: true });

// ---------------------------------------------------------------------------
// Tests: Audio read-only (0 buzz — TTS, music, transcription)
// ---------------------------------------------------------------------------

test('help: shows TTS section', async () => {
  const r = await run(['--help']);
  assert(r.exitCode === 0, `Expected exit 0, got ${r.exitCode}`);
  assert(r.stdout.includes('TEXT-TO-SPEECH'), 'Help should include TTS section');
  assert(r.stdout.includes('MUSIC GENERATION'), 'Help should include music section');
  assert(r.stdout.includes('TRANSCRIPTION'), 'Help should include transcription section');
  assert(r.stdout.includes('--speaker'), 'Help should mention --speaker flag');
  assert(r.stdout.includes('--text'), 'Help should mention --text flag');
  assert(r.stdout.includes('--media-url'), 'Help should mention --media-url flag');
}, { readonly: true });

test('help: shows tts/music/transcribe commands', async () => {
  const r = await run(['--help']);
  assert(r.exitCode === 0, `Expected exit 0, got ${r.exitCode}`);
  assert(r.stdout.includes('tts'), 'Help should list tts command');
  assert(r.stdout.includes('music'), 'Help should list music command');
  assert(r.stdout.includes('transcribe'), 'Help should list transcribe command');
}, { readonly: true });

test('error: tts missing text', async () => {
  const r = await run(['tts', '--speaker', 'Chelsie']);
  assert(r.exitCode !== 0, 'Should fail without --text');
  assert(r.stderr.includes('--text'), 'Should mention --text');
}, { readonly: true });

test('error: tts missing speaker and ref-audio', async () => {
  const r = await run(['tts', '--text', 'hello']);
  assert(r.exitCode !== 0, 'Should fail without --speaker or --ref-audio');
  assert(r.stderr.includes('--speaker') || r.stderr.includes('speaker'), 'Should mention speaker requirement');
}, { readonly: true });

test('error: transcribe missing media-url', async () => {
  const r = await run(['transcribe']);
  assert(r.exitCode !== 0, 'Should fail without --media-url');
  assert(r.stderr.includes('--media-url'), 'Should mention --media-url');
}, { readonly: true });

test('error: music missing prompt', async () => {
  const r = await run(['music']);
  assert(r.exitCode !== 0, 'Should fail without --prompt');
  assert(r.stderr.includes('--prompt'), 'Should mention --prompt');
}, { readonly: true });

// ---------------------------------------------------------------------------
// Tests: Write (spends buzz)
// ---------------------------------------------------------------------------

test('submit: single image', async () => {
  submitOutDir = makeTempDir('submit');
  const r = await run(['submit', '--prompt', 'smoke test cat, simple flat color', '-n', '1', '-o', submitOutDir]);
  assert(r.exitCode === 0, `Expected exit 0, got ${r.exitCode}: ${r.stderr}`);
  const data = assertJson(r.stdout, 'submit');

  assert(data.workflowId, 'Should return workflowId');
  assert(data.steps === 1, `Expected 1 step, got ${data.steps}`);
  assert(data.totalMedia === 1, `Expected 1 media, got ${data.totalMedia}`);
  assert(data.cost, 'Should return cost');
  totalBuzz += data.cost?.total || 0;

  submittedWorkflowId = data.workflowId;

  // Check manifest was written
  const manifestPath = join(submitOutDir, 'workflow.json');
  assert(existsSync(manifestPath), 'Should write workflow.json manifest');
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8'));
  assert(manifest.workflowId === data.workflowId, 'Manifest workflowId should match');
});

test('status: check submitted workflow (human)', async () => {
  assert(submittedWorkflowId, 'Requires submit test to pass first');
  // Wait a moment for the workflow to register
  await new Promise((r) => setTimeout(r, 2000));

  const r = await run(['status', '--workflow-id', submittedWorkflowId]);
  assert(r.exitCode === 0, `Expected exit 0, got ${r.exitCode}: ${r.stderr}`);
  assert(r.stderr.includes('Workflow:'), 'Should show workflow header');
  assert(r.stderr.includes(submittedWorkflowId), 'Should show workflow ID');
});

test('status: check submitted workflow (json)', async () => {
  assert(submittedWorkflowId, 'Requires submit test to pass first');
  const r = await run(['status', '--workflow-id', submittedWorkflowId, '--json']);
  assert(r.exitCode === 0, `Expected exit 0, got ${r.exitCode}: ${r.stderr}`);
  const data = assertJson(r.stdout, 'status --json');
  assert(data.workflowId === submittedWorkflowId, 'Should return correct workflowId');
  assert(data.status, 'Should have status field');
  assert(Array.isArray(data.steps), 'Should have steps array');
  assert(data.summary, 'Should have summary object');
});

test('wait: end-to-end image gen', async () => {
  const outDir = makeTempDir('wait');
  const r = await run(
    ['wait', '--prompt', 'smoke test dog, simple flat color', '-n', '1', '--quiet', '-o', outDir],
    { timeout: 180000 }
  );
  assert(r.exitCode === 0, `Expected exit 0, got ${r.exitCode}: ${r.stderr}`);
  const data = assertJson(r.stdout, 'wait');

  assert(data.workflowId, 'Should return workflowId');
  assert(data.status === 'succeeded', `Expected status "succeeded", got "${data.status}"`);
  assert(data.type === 'image', `Expected type "image", got "${data.type}"`);
  assert(data.downloadedMedia === 1, `Expected 1 downloaded, got ${data.downloadedMedia}`);
  assert(data.failedDownloads === 0, `Expected 0 failed, got ${data.failedDownloads}`);
  assert(data.images.length === 1, `Expected 1 image path, got ${data.images.length}`);
  assert(data.duration > 0, 'Duration should be > 0');
  assert(data.cost, 'Should return cost');
  totalBuzz += data.cost?.total || 0;

  // Verify image file exists
  const imgPath = data.images[0];
  assert(existsSync(imgPath), `Image file should exist: ${imgPath}`);
});

test('download: from submitted workflow', async () => {
  assert(submittedWorkflowId, 'Requires submit test to pass first');
  assert(submitOutDir, 'Requires submit test output dir');

  // Wait for the submitted workflow to complete
  const pollR = await run(
    ['status', '--workflow-id', submittedWorkflowId, '--poll', '--json'],
    { timeout: 180000 }
  );
  const pollData = parseJson(pollR.stdout);
  // It may have already completed or may still be processing
  // Either way, try the download

  const r = await run(['download', '--workflow-id', submittedWorkflowId, '-o', submitOutDir]);
  assert(r.exitCode === 0, `Expected exit 0, got ${r.exitCode}: ${r.stderr}`);
  const data = assertJson(r.stdout, 'download');
  assert(typeof data.success === 'boolean', 'Should have success field');
  assert(typeof data.failed === 'number', 'Should have failed count');
  assert(typeof data.total === 'number', 'Should have total count');

  if (data.total > 0) {
    // Should have at least one image or video
    assert(
      (data.images?.length || 0) + (data.videos?.length || 0) > 0,
      'Should have downloaded at least one file'
    );
  }
});

test('wait: multi-prompt', async () => {
  const outDir = makeTempDir('multi');
  const r = await run(
    ['wait', '--prompt', 'red circle', '--prompt', 'blue square', '-n', '1', '--quiet', '-o', outDir],
    { timeout: 180000 }
  );
  assert(r.exitCode === 0, `Expected exit 0, got ${r.exitCode}: ${r.stderr}`);
  const data = assertJson(r.stdout, 'wait multi');

  assert(data.status === 'succeeded', `Expected succeeded, got "${data.status}"`);
  assert(data.downloadedMedia === 2, `Expected 2 downloaded, got ${data.downloadedMedia}`);
  assert(data.images.length === 2, `Expected 2 image paths, got ${data.images.length}`);
  totalBuzz += data.cost?.total || 0;
});

// ---------------------------------------------------------------------------
// Run all tests
// ---------------------------------------------------------------------------
async function main() {
  const mode = READONLY ? 'READ-ONLY' : 'FULL';
  console.log(`\ncivitai-gen smoke tests (${mode})\n${'='.repeat(50)}\n`);

  // Run registered tests sequentially
  for (const t of tests) {
    if (READONLY && !t.readonly) {
      results.push({ name: t.name, status: 'skipped', reason: '--readonly' });
      continue;
    }

    process.stdout.write(`  Running: ${t.name}...`);
    const start = Date.now();
    try {
      await t.fn();
      const ms = Date.now() - start;
      results.push({ name: t.name, status: 'pass', ms });
      process.stdout.write(` \x1b[32mPASS\x1b[0m (${ms}ms)\n`);
    } catch (err) {
      const ms = Date.now() - start;
      results.push({ name: t.name, status: 'FAIL', ms, error: err.message });
      process.stdout.write(` \x1b[31mFAIL\x1b[0m (${ms}ms)\n`);
    }
  }

  // Print summary
  console.log('');
  let passed = 0;
  let failed = 0;
  let skipped = 0;

  for (const r of results) {
    if (r.status === 'pass') {
      passed++;
      console.log(`  \x1b[32m PASS \x1b[0m ${r.name} (${r.ms}ms)`);
    } else if (r.status === 'skipped') {
      skipped++;
      console.log(`  \x1b[33m SKIP \x1b[0m ${r.name} (${r.reason})`);
    } else {
      failed++;
      console.log(`  \x1b[31m FAIL \x1b[0m ${r.name} (${r.ms}ms)`);
      if (VERBOSE || true) {
        console.log(`         ${r.error}`);
      }
    }
  }

  console.log(`\n${'='.repeat(50)}`);
  console.log(`  ${passed} passed, ${failed} failed, ${skipped} skipped`);
  if (totalBuzz > 0) {
    console.log(`  Buzz spent: ~${totalBuzz}`);
  }

  // Cleanup temp dirs
  if (!KEEP) {
    for (const dir of tempDirs) {
      try {
        rmSync(dir, { recursive: true, force: true });
      } catch {}
    }
  } else {
    console.log(`\n  Temp dirs preserved (--keep):`);
    for (const dir of tempDirs) {
      console.log(`    ${dir}`);
    }
  }

  console.log('');
  process.exit(failed > 0 ? 1 : 0);
}

main();
