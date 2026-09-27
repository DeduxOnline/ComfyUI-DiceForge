#!/usr/bin/env node

// civitai-gen experiment — Template expansion and parameter sweeps via generate.mjs (workflow-based)
// Wraps generate.mjs: expands wildcards → bulk JSON → generate (workflow API) → download with meaningful names
// Zero npm dependencies. Requires Node 18+ (native fetch).

import { readFileSync, writeFileSync, mkdirSync, renameSync, existsSync, unlinkSync, readdirSync } from 'fs';
import { join, dirname, resolve } from 'path';
import { spawn } from 'child_process';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const GENERATE_SCRIPT = join(__dirname, 'generate.mjs');
const WILDCARDS_DIR = join(__dirname, 'wildcards');

// ---------------------------------------------------------------------------
// Spec loading
// ---------------------------------------------------------------------------
function loadSpec(specPath) {
  const raw = readFileSync(resolve(specPath), 'utf-8');
  return JSON.parse(raw);
}

// ---------------------------------------------------------------------------
// Wildcard resolution
// ---------------------------------------------------------------------------
// Wildcard values can be:
//   - Array of strings/numbers:     ["blue", "red", 0.75]
//   - Array of named objects:       [{ "name": "spiky", "value": "male with spiky hair" }]
//   - String starting with "@":     "@characters.json" or "@colors.txt" (file reference)
function resolveWildcard(wildcard, specDir) {
  if (typeof wildcard === 'string' && wildcard.startsWith('@')) {
    const ref = wildcard.slice(1);
    
    // 1. Try as relative path from specDir
    const relPath = resolve(specDir, ref);
    if (existsSync(relPath)) {
      return loadWildcardFile(relPath);
    }
    
    // 2. Try as short name from wildcards registry
    const name = ref.replace(/\.(json|txt)$/, ''); // strip extension if given
    const jsonPath = join(WILDCARDS_DIR, `${name}.json`);
    const txtPath = join(WILDCARDS_DIR, `${name}.txt`);
    
    if (existsSync(jsonPath)) return loadWildcardFile(jsonPath);
    if (existsSync(txtPath)) return loadWildcardFile(txtPath);
    
    // 3. Not found — list available wildcards
    const available = listRegisteredWildcards();
    throw new Error(
      `Wildcard "@${ref}" not found.\n` +
      `  Checked: ${relPath}\n` +
      `  Registry: ${WILDCARDS_DIR}\n` +
      (available.length > 0 ? `  Available: ${available.join(', ')}` : '  No wildcards registered.')
    );
  }
  if (Array.isArray(wildcard)) return wildcard;
  throw new Error(`Invalid wildcard value: ${JSON.stringify(wildcard)}`);
}

function loadWildcardFile(filePath) {
  const content = readFileSync(filePath, 'utf-8');
  if (filePath.endsWith('.json')) {
    return JSON.parse(content);
  }
  // Plain text: one value per line
  return content.split('\n').map(l => l.trim()).filter(Boolean);
}

function listRegisteredWildcards() {
  try {
    const files = readdirSync(WILDCARDS_DIR);
    return files
      .filter(f => f.endsWith('.json') || f.endsWith('.txt'))
      .map(f => f.replace(/\.(json|txt)$/, ''));
  } catch {
    return [];
  }
}
// Normalize a wildcard entry to { name, value }
// Supports multiple field conventions:
//   { name, value }           — standard experiment format
//   { id, promptFragment }    — civitai character format
//   { name, text }            — alternative
//   { id, value }             — alternative
//   plain string/number       — used as both name and value
function normalizeEntry(entry) {
  if (entry != null && typeof entry === 'object') {
    const name = entry.name ?? entry.id ?? null;
    const value = entry.value ?? entry.promptFragment ?? entry.text ?? null;
    if (name != null && value != null) {
      return { name: String(name), value: String(value) };
    }
    // If only one field found, use it for both
    if (name != null) return { name: String(name), value: String(name) };
    if (value != null) return { name: String(value), value: String(value) };
    // Fallback: stringify the object
    return { name: JSON.stringify(entry), value: JSON.stringify(entry) };
  }
  return { name: String(entry), value: String(entry) };
}

// ---------------------------------------------------------------------------
// Expansion: cartesian product, zip, or random
// ---------------------------------------------------------------------------
function expandProduct(wildcardArrays) {
  // wildcardArrays: [{ key, entries: [{ name, value }] }, ...]
  if (wildcardArrays.length === 0) return [{}];

  let combos = [{}];
  for (const { key, entries } of wildcardArrays) {
    const next = [];
    for (const combo of combos) {
      for (const entry of entries) {
        next.push({ ...combo, [key]: entry });
      }
    }
    combos = next;
  }
  return combos;
}

function expandZip(wildcardArrays) {
  if (wildcardArrays.length === 0) return [{}];
  const len = wildcardArrays[0].entries.length;
  for (const { key, entries } of wildcardArrays) {
    if (entries.length !== len) {
      throw new Error(
        `Zip expansion requires all wildcards to have the same length. ` +
        `"${key}" has ${entries.length}, expected ${len}.`
      );
    }
  }
  const combos = [];
  for (let i = 0; i < len; i++) {
    const combo = {};
    for (const { key, entries } of wildcardArrays) {
      combo[key] = entries[i];
    }
    combos.push(combo);
  }
  return combos;
}

function expandRandom(wildcardArrays, count) {
  if (wildcardArrays.length === 0) return [{}];
  const combos = [];
  for (let i = 0; i < count; i++) {
    const combo = {};
    for (const { key, entries } of wildcardArrays) {
      combo[key] = entries[Math.floor(Math.random() * entries.length)];
    }
    combos.push(combo);
  }
  return combos;
}

function expand(wildcardArrays, mode) {
  if (!mode || mode === 'product') return expandProduct(wildcardArrays);
  if (mode === 'zip') return expandZip(wildcardArrays);
  const randomMatch = mode.match(/^random:(\d+)$/);
  if (randomMatch) return expandRandom(wildcardArrays, parseInt(randomMatch[1], 10));
  throw new Error(`Unknown expansion mode: "${mode}". Use: product, zip, random:N`);
}

// ---------------------------------------------------------------------------
// Template substitution
// ---------------------------------------------------------------------------
function substitute(template, combo) {
  if (template == null) return null;
  let result = String(template);
  for (const [key, entry] of Object.entries(combo)) {
    // Replace all occurrences of {key} with the entry's value
    result = result.replaceAll(`{${key}}`, entry.value);
  }
  return result;
}

// ---------------------------------------------------------------------------
// Filename generation
// ---------------------------------------------------------------------------
function sanitizeFilename(str) {
  return str
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40);
}

function buildFilename(namingTemplate, combo, imageIndex, format) {
  let name = namingTemplate;
  for (const [key, entry] of Object.entries(combo)) {
    name = name.replaceAll(`{${key}}`, sanitizeFilename(entry.name));
  }
  const ext = format === 'jpeg' ? 'jpeg' : 'png';
  return imageIndex != null ? `${name}-${imageIndex}.${ext}` : name;
}

// ---------------------------------------------------------------------------
// Build expanded jobs from spec
// ---------------------------------------------------------------------------
function buildExpandedJobs(spec, specDir) {
  const template = spec.template;
  if (!template || !template.prompt) {
    throw new Error('Spec must have a "template" with at least a "prompt" field.');
  }

  // Resolve all wildcards
  const wildcardArrays = [];
  for (const [key, raw] of Object.entries(spec.wildcards || {})) {
    const resolved = resolveWildcard(raw, specDir);
    const entries = resolved.map(normalizeEntry);
    wildcardArrays.push({ key, entries });
  }

  // Expand into combinations
  const combos = expand(wildcardArrays, spec.expansion);

  // Build a bulk entry for each combination
  const jobs = combos.map((combo) => {
    const entry = {};
    // Substitute wildcards into all template string fields
    for (const [field, val] of Object.entries(template)) {
      if (typeof val === 'string') {
        entry[field] = substitute(val, combo);
      } else {
        entry[field] = val;
      }
    }
    return { entry, combo };
  });

  return jobs;
}

// ---------------------------------------------------------------------------
// CLI argument parsing
// ---------------------------------------------------------------------------
function parseArgs(argv) {
  const args = argv.slice(2);
  const opts = {
    spec: null,
    output: './output',
    concurrency: null,   // null = use spec value or default 5
    dryRun: false,
    preview: null,
    help: false,
    // Inline mode
    template: null,
    wildcards: [],       // collected as ["key=val1,val2", ...]
    model: null,
    resources: null,
    negativePrompt: null,
    quantity: null,
    aspect: null,
    resolution: null,
    steps: null,
    cfgScale: null,
    format: 'png',
    naming: null,
    expansion: null,
    listWildcards: false,
    saveWildcardName: null,
    saveWildcardValues: null,
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    const next = () => {
      i++;
      if (i >= args.length) { console.error(`Missing value for ${arg}`); process.exit(1); }
      return args[i];
    };
    switch (arg) {
      case '--help': case '-h': opts.help = true; break;
      case '--spec': opts.spec = next(); break;
      case '--output': case '-o': opts.output = next(); break;
      case '--concurrency': opts.concurrency = parseInt(next(), 10); break;
      case '--dry-run': opts.dryRun = true; break;
      case '--preview': opts.preview = parseInt(next(), 10); break;
      case '--template': opts.template = next(); break;
      case '--wildcard': opts.wildcards.push(next()); break;
      case '--model': opts.model = next(); break;
      case '--resources': opts.resources = next(); break;
      case '--negative-prompt': opts.negativePrompt = next(); break;
      case '--quantity': case '-n': opts.quantity = parseInt(next(), 10); break;
      case '--aspect': opts.aspect = next(); break;
      case '--resolution': opts.resolution = next(); break;
      case '--steps': opts.steps = parseInt(next(), 10); break;
      case '--cfg-scale': opts.cfgScale = parseFloat(next()); break;
      case '--format': opts.format = next(); break;
      case '--naming': opts.naming = next(); break;
      case '--expansion': opts.expansion = next(); break;
      case '--list-wildcards': opts.listWildcards = true; break;
      case '--save-wildcard': opts.saveWildcardName = next(); opts.saveWildcardValues = next(); break;
      default: console.error(`Unknown flag: ${arg}`); process.exit(1);
    }
  }
  return opts;
}

// Build spec from inline CLI args
function specFromCli(opts) {
  if (!opts.template) {
    console.error('Error: --spec or --template is required. Run with --help for usage.');
    process.exit(1);
  }

  const template = { prompt: opts.template };
  if (opts.model) template.model = opts.model;
  if (opts.resources) template.resources = opts.resources;
  if (opts.negativePrompt) template.negativePrompt = opts.negativePrompt;
  if (opts.quantity) template.quantity = opts.quantity;
  if (opts.aspect) template.aspect = opts.aspect;
  if (opts.resolution) template.resolution = opts.resolution;
  if (opts.steps) template.steps = opts.steps;
  if (opts.cfgScale) template.cfgScale = opts.cfgScale;
  if (opts.format) template.format = opts.format;

  const wildcards = {};
  for (const wc of opts.wildcards) {
    const eqIdx = wc.indexOf('=');
    if (eqIdx === -1) {
      console.error(`Invalid wildcard format: "${wc}". Use: key=val1,val2,...`);
      process.exit(1);
    }
    const key = wc.slice(0, eqIdx);
    const valStr = wc.slice(eqIdx + 1);
    // Check if it's a file reference
    if (valStr.startsWith('@')) {
      wildcards[key] = valStr;
    } else {
      wildcards[key] = valStr.split(',').map(v => v.trim()).filter(Boolean);
    }
  }

  return {
    template,
    wildcards,
    expansion: opts.expansion || 'product',
    naming: opts.naming || null,
    concurrency: opts.concurrency || 5,
  };
}

// ---------------------------------------------------------------------------
// Help text
// ---------------------------------------------------------------------------
function printHelp() {
  const text = `
civitai-gen experiment — Template expansion and parameter sweeps via generate.mjs (workflow-based)

USAGE
  # From a spec file
  node experiment.mjs --spec avatars.json -o ./out

  # Inline wildcards
  node experiment.mjs \\
    --template "Burton Style, {color} theme, {character}" \\
    --wildcard color=blue,red,green \\
    --wildcard character=@characters.txt \\
    --model "urn:air:sdxl:checkpoint:civitai:827184@2514310" \\
    --resources "urn:air:sdxl:lora:civitai:185166@207862:{weight}" \\
    --wildcard weight=0.75,1.0,1.25 \\
    --naming "{color}-{character}-w{weight}" \\
    -n 2 -o ./out

  # Dry run (show expansion count and sample prompts)
  node experiment.mjs --spec avatars.json --dry-run

  # Preview first N expanded prompts
  node experiment.mjs --spec avatars.json --preview 5

SPEC FILE FORMAT
  {
    "template": {
      "prompt": "Style, {color} theme, {character}",
      "negativePrompt": "blurry, low quality",
      "model": "urn:air:sdxl:checkpoint:civitai:...",
      "resources": "urn:air:sdxl:lora:civitai:...:civitai:123@456:{weight}",
      "quantity": 2,
      "aspect": "square",
      "steps": 25,
      "cfgScale": 7
    },
    "wildcards": {
      "color": ["blue", "red", "green"],
      "character": [
        { "name": "spiky-male", "value": "male with spiky undercut, angular jaw" },
        { "name": "pixie-female", "value": "female with pixie cut, sharp cheekbones" }
      ],
      "weight": [0.75, 1.0, 1.25]
    },
    "expansion": "product",
    "naming": "{color}-{character}-w{weight}",
    "concurrency": 5
  }

WILDCARD VALUES
  Simple array:      ["blue", "red", "green"]
  Named objects:     [{ "name": "alias", "value": "full text for prompt" }]
  File reference:    "@characters.json" or "@values.txt" (one per line)
  Numbers:           [0.75, 1.0, 1.25] (for parameter sweeps)

  Named objects use "name" for filenames and "value" for prompt substitution.
  Simple values use the value itself for both.

EXPANSION MODES
  product      Cartesian product of all wildcards (default). 3×4×2 = 24 combos.
  zip          Parallel zip. All wildcards must have the same length.
  random:N     N random combinations sampled from all wildcards.

NAMING TEMPLATE
  Uses wildcard keys as variables: "{color}-{character}-w{weight}"
  Names are sanitized for filenames (lowercase, alphanumeric + hyphens).
  Image index is appended automatically: "blue-spiky-male-w1-0.png"
  When omitted, defaults to joining all wildcard names with hyphens.

FLAGS
  --spec <file>         Path to experiment spec JSON file
  --output, -o          Output directory (default: ./output)
  --concurrency <n>     Max parallel API requests (overrides spec)
  --dry-run             Show expansion stats without generating
  --preview <n>         Show first N expanded prompts without generating
  --help, -h            Show this help message

WILDCARD REGISTRY
  Wildcards are stored in the wildcards/ directory next to this script
  Reference by short name with @: --wildcard "color=@neon-colors"

  --list-wildcards          List all registered wildcards with previews
  --save-wildcard <name> <values>
                            Save a wildcard list to the registry
                            Values: comma-separated or @file.json/@file.txt

  Inline mode (alternative to --spec):
  --template <prompt>   Prompt template with {wildcards}
  --wildcard <k=v,v>    Define a wildcard (repeatable)
  --model <urn>         Checkpoint model AIR URN
  --resources <str>     Resources string (can contain {wildcards})
  --negative-prompt     Negative prompt
  --quantity, -n        Images per combo (default: 1)
  --aspect              Aspect ratio preset
  --resolution          Resolution scale
  --steps               Sampling steps
  --cfg-scale           CFG scale
  --format              Output format: png or jpeg
  --naming              Filename template
  --expansion           Expansion mode

OUTPUT
  Images are saved with meaningful names based on the naming template.
  A manifest.json is written alongside with the full mapping.
  Prints a JSON summary to stdout when complete (includes workflowId).
`.trimStart();
  console.log(text);
}

// ---------------------------------------------------------------------------
// Run generate.mjs as subprocess
// ---------------------------------------------------------------------------
function runGenerate(bulkFile, outDir) {
  return new Promise((resolve, reject) => {
    const args = [GENERATE_SCRIPT, 'wait', '--bulk', bulkFile, '-o', outDir, '--quiet'];
    const proc = spawn(process.execPath, args, {
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    let stdout = '';
    proc.stdout.on('data', (d) => { stdout += d.toString(); });
    proc.stderr.on('data', (d) => { process.stderr.write(d); });

    proc.on('close', (code) => {
      let summary = null;
      try {
        summary = JSON.parse(stdout.trim());
      } catch {}
      resolve({ code, summary });
    });

    proc.on('error', reject);
  });
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
async function main() {
  const opts = parseArgs(process.argv);

  if (opts.help) {
    printHelp();
    process.exit(0);
  }


  // --- List wildcards ---
  if (opts.listWildcards) {
    const wildcards = listRegisteredWildcards();
    if (wildcards.length === 0) {
      console.log('No wildcards registered.');
      console.log(`Registry directory: ${WILDCARDS_DIR}`);
    } else {
      console.log(`Registered wildcards (${WILDCARDS_DIR}):\n`);
      for (const name of wildcards) {
        // Show count of values
        const jsonPath = join(WILDCARDS_DIR, `${name}.json`);
        const txtPath = join(WILDCARDS_DIR, `${name}.txt`);
        const filePath = existsSync(jsonPath) ? jsonPath : txtPath;
        try {
          const values = loadWildcardFile(filePath);
          const preview = values.slice(0, 5).map(v => 
            typeof v === 'object' ? (v.name || v.id || JSON.stringify(v)) : String(v)
          );
          const more = values.length > 5 ? `, ... (+${values.length - 5} more)` : '';
          console.log(`  @${name} (${values.length} values): ${preview.join(', ')}${more}`);
        } catch {
          console.log(`  @${name} (error reading)`);
        }
      }
    }
    process.exit(0);
  }

  // --- Save wildcard ---
  if (opts.saveWildcardName) {
    mkdirSync(WILDCARDS_DIR, { recursive: true });
    const name = opts.saveWildcardName;
    const valuesArg = opts.saveWildcardValues;
    
    let destPath;
    if (valuesArg.startsWith('@')) {
      // Copy from file
      const srcPath = resolve(valuesArg.slice(1));
      if (!existsSync(srcPath)) {
        console.error(`Source file not found: ${srcPath}`);
        process.exit(1);
      }
      const ext = srcPath.endsWith('.json') ? '.json' : '.txt';
      destPath = join(WILDCARDS_DIR, `${name}${ext}`);
      writeFileSync(destPath, readFileSync(srcPath));
    } else {
      // Comma-separated values → txt file
      const values = valuesArg.split(',').map(v => v.trim()).filter(Boolean);
      destPath = join(WILDCARDS_DIR, `${name}.txt`);
      writeFileSync(destPath, values.join('\n') + '\n');
    }
    console.log(`Saved wildcard "@${name}" → ${destPath}`);
    // Show the values
    const loaded = loadWildcardFile(destPath);
    console.log(`  ${loaded.length} values: ${loaded.slice(0, 8).join(', ')}${loaded.length > 8 ? '...' : ''}`);
    process.exit(0);
  }
  // Build spec from file or CLI
  let spec;
  let specDir = process.cwd();
  if (opts.spec) {
    spec = loadSpec(opts.spec);
    specDir = dirname(resolve(opts.spec));
  } else {
    spec = specFromCli(opts);
  }

  // Override concurrency from CLI if provided
  const concurrency = opts.concurrency ?? spec.concurrency ?? 5;

  // Expand wildcards into job list
  const jobs = buildExpandedJobs(spec, specDir);
  const quantity = spec.template.quantity ?? 1;
  const format = spec.template.format ?? opts.format ?? 'png';
  const totalImages = jobs.length * quantity;

  // Build naming template (default: join all wildcard keys)
  const wildcardKeys = Object.keys(spec.wildcards || {});
  const namingTemplate = opts.naming ?? spec.naming ??
    (wildcardKeys.length > 0 ? wildcardKeys.map(k => `{${k}}`).join('-') : 'img');

  // --- Dry run ---
  if (opts.dryRun) {
    console.log('=== DRY RUN ===');
    console.log(`Wildcards: ${wildcardKeys.join(', ') || '(none)'}`);
    for (const key of wildcardKeys) {
      const resolved = resolveWildcard(spec.wildcards[key], specDir);
      console.log(`  ${key}: ${resolved.length} values`);
    }
    console.log(`Expansion: ${spec.expansion || 'product'}`);
    console.log(`Combinations: ${jobs.length}`);
    console.log(`Quantity per combo: ${quantity}`);
    console.log(`Total images: ${totalImages}`);
    console.log(`Concurrency: ${concurrency}`);
    console.log(`Naming: ${namingTemplate}-{i}.${format === 'jpeg' ? 'jpeg' : 'png'}`);
    if (jobs.length > 0) {
      console.log('\nSample prompt (first combo):');
      console.log(`  ${jobs[0].entry.prompt.slice(0, 120)}...`);
      console.log(`Sample filename: ${buildFilename(namingTemplate, jobs[0].combo, 0, format)}`);
    }
    process.exit(0);
  }

  // --- Preview ---
  if (opts.preview != null) {
    const count = Math.min(opts.preview, jobs.length);
    console.log(`=== PREVIEW (${count} of ${jobs.length} combos, ${totalImages} total images) ===\n`);
    for (let i = 0; i < count; i++) {
      const { entry, combo } = jobs[i];
      const fname = buildFilename(namingTemplate, combo, 0, format);
      console.log(`[${i}] ${fname}`);
      console.log(`    prompt: ${entry.prompt.slice(0, 100)}${entry.prompt.length > 100 ? '...' : ''}`);
      if (entry.resources) console.log(`    resources: ${entry.resources}`);
      console.log();
    }
    console.log(`... ${jobs.length} total combos × ${quantity} quantity = ${totalImages} images`);
    process.exit(0);
  }

  // --- Generate ---
  console.error(`Experiment: ${jobs.length} combos × ${quantity} qty = ${totalImages} images`);
  console.error(`Output: ${resolve(opts.output)}
`);

  // Write bulk JSON with labels from naming template
  const outDir = resolve(opts.output);
  mkdirSync(outDir, { recursive: true });

  const bulkEntries = jobs.map(j => {
    const entry = { ...j.entry };
    entry.label = buildFilename(namingTemplate, j.combo, null, format);
    return entry;
  });
  const bulkFile = join(outDir, '.experiment-bulk.json');
  writeFileSync(bulkFile, JSON.stringify(bulkEntries, null, 2));

  // Write manifest
  const manifest = jobs.map((j, i) => ({
    jobIndex: i,
    wildcards: Object.fromEntries(
      Object.entries(j.combo).map(([k, v]) => [k, { name: v.name, value: v.value }])
    ),
    filename: buildFilename(namingTemplate, j.combo, null, format),
    prompt: j.entry.prompt,
  }));
  writeFileSync(join(outDir, 'manifest.json'), JSON.stringify(manifest, null, 2));

  const { code, summary } = await runGenerate(bulkFile, outDir);

  // Clean up bulk file
  try { unlinkSync(bulkFile); } catch {}

  const failedCount = summary?.failedDownloads ?? summary?.failed ?? 0;
  const result = {
    success: code === 0 && failedCount === 0,
    combos: jobs.length,
    total: totalImages,
    workflowId: summary?.workflowId ?? null,
    images: summary?.images ?? [],
    failed: failedCount,
  };

  console.log(JSON.stringify(result, null, 2));
  process.exit(code);
}

main().catch((err) => {
  console.error(`Fatal error: ${err.message}`);
  process.exit(1);
});
