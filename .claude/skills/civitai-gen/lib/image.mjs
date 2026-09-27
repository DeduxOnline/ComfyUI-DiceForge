// lib/image.mjs — Image generation step builder & ecosystem configuration
//
// Exports: ECOSYSTEM_CONFIGS, DEFAULT_ECOSYSTEM, RESOLUTION_MULTIPLIERS,
//          buildImageStep, detectEcosystem, parseResources, resolveDimensions
//
// Zero npm dependencies. Requires Node 18+.

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
export const DEFAULT_ECOSYSTEM = 'flux1';

// ---------------------------------------------------------------------------
// Ecosystem & aspect ratio configuration
// ---------------------------------------------------------------------------
export const ECOSYSTEM_CONFIGS = {
  sd1: {
    label: 'SD 1.5',
    aspects: {
      square: { width: 512, height: 512 },
      landscape: { width: 768, height: 512 },
      portrait: { width: 512, height: 768 },
    },
  },
  sdxl: {
    label: 'SDXL / Pony / Illustrious',
    aspects: {
      square: { width: 1024, height: 1024 },
      landscape: { width: 1216, height: 832 },
      portrait: { width: 832, height: 1216 },
    },
  },
  flux1: {
    label: 'Flux.1',
    aspects: {
      square: { width: 1024, height: 1024 },
      landscape: { width: 1216, height: 832 },
      portrait: { width: 832, height: 1216 },
    },
  },
  flux2: {
    label: 'Flux.2',
    aspects: {
      square: { width: 1024, height: 1024 },
      landscape: { width: 1216, height: 832 },
      portrait: { width: 832, height: 1216 },
    },
  },
  auraflow: {
    label: 'Pony V7',
    aspects: {
      square: { width: 1536, height: 1536 },
      landscape: { width: 1536, height: 1024 },
      portrait: { width: 1024, height: 1536 },
    },
  },
  qwen: {
    label: 'Qwen',
    aspects: {
      square: { width: 1328, height: 1328 },
      landscape: { width: 1664, height: 928 },
      portrait: { width: 928, height: 1664 },
    },
  },
  zimage: {
    label: 'Z-Image',
    aspects: {
      square: { width: 1024, height: 1024 },
      landscape: { width: 1216, height: 832 },
      portrait: { width: 832, height: 1216 },
    },
  },
  chroma: {
    label: 'Chroma',
    aspects: {
      square: { width: 1024, height: 1024 },
      landscape: { width: 1216, height: 832 },
      portrait: { width: 832, height: 1216 },
    },
  },
  hidream: {
    label: 'HiDream',
    aspects: {
      square: { width: 1024, height: 1024 },
      landscape: { width: 1216, height: 832 },
      portrait: { width: 832, height: 1216 },
    },
  },
  seedream: {
    label: 'Seedream',
    aspects: {
      square: { width: 2048, height: 2048 },
      landscape: { width: 2560, height: 1440 },
      portrait: { width: 1440, height: 2560 },
    },
  },
  nanobanana: {
    label: 'Nano Banana',
    aspects: {
      square: { width: 2048, height: 2048 },
      landscape: { width: 2560, height: 1440 },
      portrait: { width: 1440, height: 2560 },
    },
  },
};

export const RESOLUTION_MULTIPLIERS = { small: 0.75, medium: 1.0, large: 1.5 };

// ---------------------------------------------------------------------------
// AIR URN parsing & resource handling
// ---------------------------------------------------------------------------
export function parseAirUrn(urn) {
  if (!urn || !urn.startsWith('urn:air:')) return null;
  const parts = urn.slice(8).split(':');
  if (parts.length < 4) return null;
  const ecosystem = parts[0];
  const type = parts[1];
  const source = parts[2];
  const idPart = parts.slice(3).join(':');
  const [modelId, versionId] = idPart.split('@');
  return { ecosystem, type, source, modelId, versionId };
}

export function detectEcosystem(modelUrn) {
  const parsed = parseAirUrn(modelUrn);
  if (!parsed) return DEFAULT_ECOSYSTEM;
  const eco = parsed.ecosystem.toLowerCase();
  if (ECOSYSTEM_CONFIGS[eco]) return eco;
  const stripped = eco.replace(/-/g, '');
  if (ECOSYSTEM_CONFIGS[stripped]) return stripped;
  if (eco === 'sd1') return 'sd1';
  if (eco === 'sdxl' || eco === 'pony') return 'sdxl';
  if (eco.startsWith('flux1')) return 'flux1';
  if (eco.startsWith('flux2')) return 'flux2';
  return DEFAULT_ECOSYSTEM;
}

function mapUrnTypeToApiType(urnType) {
  const map = {
    checkpoint: 'Checkpoint',
    lora: 'Lora',
    lycoris: 'LoCon',
    dora: 'DoRA',
    embedding: 'TextualInversion',
    hypernet: 'Hypernetwork',
    vae: 'VAE',
  };
  return map[urnType?.toLowerCase()] || 'Lora';
}

export function parseResources(resourceStr) {
  if (!resourceStr) return [];
  const resources = [];
  const entries = resourceStr.split(',').map((s) => s.trim()).filter(Boolean);

  for (const entry of entries) {
    const atIdx = entry.lastIndexOf('@');
    if (atIdx === -1) throw new Error(`Invalid resource AIR URN (missing @): ${entry}`);

    const afterAt = entry.slice(atIdx + 1);
    const colonIdx = afterAt.indexOf(':');

    let air, weight;
    if (colonIdx !== -1) {
      const weightStr = afterAt.slice(colonIdx + 1);
      const parsed = parseFloat(weightStr);
      if (!isNaN(parsed)) {
        weight = parsed;
        air = entry.slice(0, atIdx + 1 + colonIdx);
      } else {
        air = entry;
        weight = 1.0;
      }
    } else {
      air = entry;
      weight = 1.0;
    }

    const parsedUrn = parseAirUrn(air);
    const type = parsedUrn ? mapUrnTypeToApiType(parsedUrn.type) : 'Lora';
    resources.push({ air, weight, type });
  }
  return resources;
}

export function resolveDimensions(opts) {
  if (opts.widthExplicit && opts.heightExplicit) {
    return { width: opts.width, height: opts.height };
  }
  const ecosystem = detectEcosystem(opts.model);
  const config = ECOSYSTEM_CONFIGS[ecosystem] || ECOSYSTEM_CONFIGS[DEFAULT_ECOSYSTEM];
  const aspect = opts.aspect || 'square';
  const aspectDims = config.aspects[aspect];
  if (!aspectDims) {
    const available = Object.keys(config.aspects).join(', ');
    throw new Error(`Unknown aspect "${aspect}" for ${config.label}. Available: ${available}`);
  }
  let { width, height } = aspectDims;
  if (opts.resolution && opts.resolution !== 'medium') {
    const mult = RESOLUTION_MULTIPLIERS[opts.resolution];
    if (!mult) throw new Error(`Unknown resolution "${opts.resolution}". Use: small, medium, large`);
    width = Math.round((width * mult) / 8) * 8;
    height = Math.round((height * mult) / 8) * 8;
  }
  if (opts.widthExplicit) width = opts.width;
  if (opts.heightExplicit) height = opts.height;
  return { width, height };
}

// ---------------------------------------------------------------------------
// Build image workflow step
// ---------------------------------------------------------------------------
export function buildImageStep(job, stepIndex) {
  const dims = resolveDimensions(job);
  const resources = parseResources(job.resources);

  const additionalNetworks = {};
  for (const res of resources) {
    additionalNetworks[res.air] = {
      type: res.type,
      strength: res.weight,
    };
  }

  const input = {
    prompt: job.prompt,
    quantity: job.quantity ?? 1,
    width: dims.width,
    height: dims.height,
  };

  if (job.model) input.model = job.model;
  if (job.negativePrompt) input.negativePrompt = job.negativePrompt;
  if (job.steps) input.steps = job.steps;
  if (job.cfgScale) input.cfgScale = job.cfgScale;
  if (job.scheduler) input.scheduler = job.scheduler;
  if (job.seed != null) input.seed = job.seed;
  if (Object.keys(additionalNetworks).length > 0) {
    input.additionalNetworks = additionalNetworks;
  }

  // img2img
  if (job.sourceImage) {
    input.image = job.sourceImage;
    if (job.denoise != null) input.sourceImageDenoiseStrenght = job.denoise;
  }

  return {
    $type: 'textToImage',
    name: job.name || `step_${stepIndex}`,
    timeout: '00:20:00',
    metadata: {
      stepIndex,
      ...(job.label ? { label: job.label } : {}),
    },
    input,
  };
}

// ---------------------------------------------------------------------------
// Image-specific CLI arg extensions
// ---------------------------------------------------------------------------
export const IMAGE_ARG_HANDLERS = {
  '--model': (opts, next) => { opts.model = next(); },
  '--negative-prompt': (opts, next) => { opts.negativePrompt = next(); },
  '--steps': (opts, next) => { opts.steps = parseInt(next(), 10); },
  '--cfg-scale': (opts, next) => { opts.cfgScale = parseFloat(next()); },
  '--scheduler': (opts, next) => { opts.scheduler = next(); },
  '--seed': (opts, next) => { opts.seed = parseInt(next(), 10); },
  '--format': (opts, next) => { opts.format = next(); },
  '--quantity': (opts, next) => { opts.quantity = parseInt(next(), 10); },
  '-n': (opts, next) => { opts.quantity = parseInt(next(), 10); },
  '--resources': (opts, next) => { opts.resources = next(); },
  '--aspect': (opts, next) => { opts.aspect = next(); },
  '--resolution': (opts, next) => { opts.resolution = next(); },
  '--width': (opts, next) => { opts.width = parseInt(next(), 10); opts.widthExplicit = true; },
  '--height': (opts, next) => { opts.height = parseInt(next(), 10); opts.heightExplicit = true; },
  '--source-image': (opts, next) => { opts.sourceImage = next(); },
  '--denoise': (opts, next) => { opts.denoise = parseFloat(next()); },
};

export const IMAGE_HELP = `
IMAGE GENERATION (submit / wait)
  --prompt <text>        Text prompt (repeatable for multiple workflow steps)
  --bulk <file.json>     JSON array of job definitions
  --model <air>          Checkpoint model AIR URN
  --resources <list>     Comma-separated resources (LoRA AIRs with :weight)
  --negative-prompt <t>  Negative prompt
  --quantity / -n <num>  Images per step (default: 4)
  --aspect <name>        Aspect ratio preset (square, landscape, portrait)
  --resolution <size>    Resolution scale (small, medium, large)
  --width / --height     Explicit dimensions (overrides aspect)
  --steps <num>          Sampling steps
  --cfg-scale <num>      CFG scale
  --scheduler <name>     Sampler algorithm
  --seed <num>           Seed for reproducibility
  --source-image <url>   Source image URL for img2img
  --denoise <0-1>        Denoise strength for img2img
`;
