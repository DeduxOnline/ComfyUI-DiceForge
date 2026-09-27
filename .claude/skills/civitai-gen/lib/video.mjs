// lib/video.mjs — Video generation step builder & engine registry
//
// Exports: VIDEO_ENGINE_REGISTRY, buildVideoStep, VIDEO_ARG_HANDLERS, VIDEO_HELP
//
// Zero npm dependencies. Requires Node 18+.

// ---------------------------------------------------------------------------
// Video engine registry — static capabilities for known engines.
// Unknown engines from the API still work in pass-through mode.
// ---------------------------------------------------------------------------
export const VIDEO_ENGINE_REGISTRY = {
  veo3: {
    label: 'Google VEO 3',
    processes: ['txt2vid', 'img2vid'],
    durations: [4, 6, 8],
    aspectRatios: ['16:9', '9:16'],
    defaults: { duration: 8, aspectRatio: '16:9', fastMode: true, version: '3.0' },
    features: ['audio', 'lora', 'fastMode'],
    notes: 'PG model — profanity/explicit language returns generic video, no refund.',
  },
  kling: {
    label: 'Kling',
    processes: ['txt2vid', 'img2vid'],
    durations: [5, 10],
    aspectRatios: ['16:9', '1:1', '9:16'],
    defaults: { duration: 5, aspectRatio: '16:9', model: 'v2.5-turbo' },
    features: ['cameraControl'],
    models: ['v1.6', 'v2', 'v2.5-turbo'],
  },
  wan: {
    label: 'Wan Video',
    processes: ['txt2vid', 'img2vid'],
    durations: [3, 5, 8, 10],
    aspectRatios: ['16:9', '1:1', '9:16'],
    defaults: { duration: 5, aspectRatio: '16:9', version: 'v2.5' },
    features: ['lora', 'interpolation'],
    versions: ['v2.1', 'v2.2', 'v2.2-5b', 'v2.5', 'v2.6'],
  },
  vidu: {
    label: 'Vidu 2.0 / Q3',
    processes: ['txt2vid', 'img2vid', 'ref2vid'],
    durations: [4, 8],
    aspectRatios: ['16:9', '1:1', '9:16'],
    defaults: { duration: 4, aspectRatio: '16:9' },
    features: ['movementAmplitude', 'style', 'promptEnhancer'],
  },
  sora: {
    label: 'Sora 2',
    processes: ['txt2vid', 'img2vid'],
    durations: [4, 8],
    aspectRatios: ['16:9', '9:16'],
    defaults: { duration: 4, aspectRatio: '16:9' },
    features: ['proMode'],
    resolutions: ['720p', '1080p'],
  },
  haiper: {
    label: 'Haiper 2.0',
    processes: ['txt2vid', 'img2vid'],
    durations: [2, 4, 8],
    aspectRatios: ['16:9', '4:3', '1:1', '3:4', '9:16'],
    defaults: { duration: 4, aspectRatio: '16:9' },
    resolutions: ['720', '1080', '2160'],
  },
  mochi: {
    label: 'Mochi 1',
    processes: ['txt2vid'],
    durations: [],
    aspectRatios: [],
    defaults: {},
    features: ['promptEnhancer'],
  },
  hunyuan: {
    label: 'Hunyuan Video',
    processes: ['txt2vid'],
    durations: [3, 5],
    aspectRatios: ['16:9', '3:2', '1:1', '2:3', '9:16'],
    defaults: { duration: 5, aspectRatio: '16:9' },
    features: ['lora'],
  },
  minimax: {
    label: 'Hailuo by MiniMax',
    processes: ['txt2vid', 'img2vid'],
    durations: [],
    aspectRatios: [],
    defaults: {},
    features: ['promptEnhancer'],
  },
  lightricks: {
    label: 'Lightricks',
    processes: ['txt2vid', 'img2vid'],
    durations: [5],
    aspectRatios: ['16:9', '9:16'],
    defaults: { duration: 5, aspectRatio: '16:9' },
  },
  ltx2: {
    label: 'LTX Video 2',
    processes: ['txt2vid', 'img2vid'],
    durations: [3, 5],
    aspectRatios: ['16:9', '9:16', '1:1', '4:3', '3:4'],
    defaults: { duration: 5, aspectRatio: '16:9' },
    features: ['audio', 'distilled'],
  },
  grok: {
    label: 'Grok Video (xAI)',
    processes: ['txt2vid', 'img2vid', 'edit2vid'],
    durations: [1, 4, 6, 15],
    aspectRatios: ['16:9', '4:3', '3:2', '1:1', '2:3', '3:4', '9:16'],
    defaults: { duration: 6, aspectRatio: '16:9' },
    features: ['edit'],
    resolutions: ['480p', '720p'],
    notes: 'Per-second pricing (~65–104 buzz/s). img2vid supports aspectRatio "auto".',
  },
  happyHorse: {
    label: 'Happy-Horse (Alibaba)',
    processes: ['txt2vid', 'img2vid', 'edit2vid', 'ref2vid'],
    durations: [3, 5, 15],
    aspectRatios: ['16:9', '9:16', '1:1', '4:3', '3:4'],
    defaults: { duration: 5, aspectRatio: '16:9' },
    features: ['multiReference', 'videoEdit'],
    resolutions: ['720p', '1080p'],
    notes: 'videoEdit billed at double rate (input + output seconds). sourceVideo must be Civitai-hosted URL/AIR.',
  },
};

// ---------------------------------------------------------------------------
// Build video workflow step
// ---------------------------------------------------------------------------
export function buildVideoStep(job, stepIndex) {
  const engine = job.engine;
  const registry = VIDEO_ENGINE_REGISTRY[engine] || {};
  const defaults = registry.defaults || {};

  const input = {
    engine,
    prompt: job.prompt,
  };

  if (job.sourceImage) {
    input.sourceImage = job.sourceImage;
  }
  if (job.images) {
    input.images = Array.isArray(job.images) ? job.images : [job.images];
  } else if (job.sourceImage && ['veo3', 'sora', 'wan'].includes(engine)) {
    input.images = [job.sourceImage];
    delete input.sourceImage;
  }

  const duration = job.duration ?? defaults.duration;
  if (duration != null) input.duration = duration;

  const aspectRatio = job.videoAspect ?? defaults.aspectRatio;
  if (aspectRatio) input.aspectRatio = aspectRatio;

  if (job.negativePrompt) input.negativePrompt = job.negativePrompt;
  if (job.seed != null) input.seed = job.seed;
  if (job.cfgScale != null) input.cfgScale = job.cfgScale;

  if (job.generateAudio != null) input.generateAudio = job.generateAudio;
  if (job.fastMode != null) input.fastMode = job.fastMode;
  else if (defaults.fastMode != null) input.fastMode = defaults.fastMode;
  if (job.version) input.version = job.version;
  else if (defaults.version) input.version = defaults.version;
  if (job.videoModel) input.model = job.videoModel;
  else if (defaults.model) input.model = defaults.model;
  if (job.enablePromptEnhancer != null) input.enablePromptEnhancer = job.enablePromptEnhancer;
  if (job.videoResolution) input.resolution = job.videoResolution;
  if (job.movementAmplitude) input.movementAmplitude = job.movementAmplitude;
  if (job.style) input.style = job.style;
  if (job.usePro != null) input.usePro = job.usePro;

  if (job.engineParams && typeof job.engineParams === 'object') {
    Object.assign(input, job.engineParams);
  }

  return {
    $type: 'videoGen',
    name: job.name || `step_${stepIndex}`,
    metadata: {
      stepIndex,
      ...(job.label ? { label: job.label } : {}),
    },
    input,
  };
}

// ---------------------------------------------------------------------------
// Video-specific CLI arg extensions
// ---------------------------------------------------------------------------
export const VIDEO_ARG_HANDLERS = {
  '--engine': (opts, next) => { opts.engine = next(); },
  '--duration': (opts, next) => { opts.duration = parseInt(next(), 10); },
  '--video-aspect': (opts, next) => { opts.videoAspect = next(); },
  '--generate-audio': (opts) => { opts.generateAudio = true; },
  '--no-audio': (opts) => { opts.generateAudio = false; },
  '--fast-mode': (opts) => { opts.fastMode = true; },
  '--no-fast-mode': (opts) => { opts.fastMode = false; },
  '--version': (opts, next) => { opts.version = next(); },
  '--video-model': (opts, next) => { opts.videoModel = next(); },
  '--prompt-enhancer': (opts) => { opts.enablePromptEnhancer = true; },
  '--video-resolution': (opts, next) => { opts.videoResolution = next(); },
  '--movement': (opts, next) => { opts.movementAmplitude = next(); },
  '--style': (opts, next) => { opts.style = next(); },
  '--pro': (opts) => { opts.usePro = true; },
};

export const VIDEO_HELP = `
VIDEO GENERATION (submit / wait — requires --engine)
  --engine <name>        Video engine (veo3, kling, wan, vidu, sora, etc.)
  --prompt <text>        Video prompt (what should happen in the video)
  --source-image <url>   Source image for img2vid (animate an image)
  --duration <sec>       Video duration in seconds
  --video-aspect <ratio> Aspect ratio (16:9, 9:16, 1:1)
  --generate-audio       Enable audio generation (veo3, ltx2)
  --no-audio             Disable audio generation
  --fast-mode            Use fast/turbo mode (veo3)
  --no-fast-mode         Use standard mode
  --version <ver>        Engine version (e.g., 3.0 for veo3, v2.5 for wan)
  --video-model <model>  Engine-specific model variant (e.g., v2.5-turbo for kling)
  --prompt-enhancer      Enable prompt enhancement
  --video-resolution <r> Resolution (720p, 1080p, etc.)
  --movement <amp>       Movement amplitude: auto, small, medium, large (vidu)
  --style <name>         Style preset (e.g., anime for vidu)
  --pro                  Use pro/professional mode (sora, kling)
`;
