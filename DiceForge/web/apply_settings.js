import { app } from "../../scripts/app.js";
import { setField, PROMPT_NODE_TYPE } from "./wildcards.js";

// How an image was made (Civitai's generation data, as A1111, Forge, Civitai's generator or ComfyUI wrote it) put into the workflow: the prompts into
// the prompt nodes that feed a sampler, the seed, steps, CFG, sampler and scheduler into the samplers, the size into the empty latents. Used by
// "Use these settings" in Model info's image slider.

// A1111 / Forge sampler names to ComfyUI's ("DPM++ 2M Karras" is the sampler dpmpp_2m with the karras scheduler).
const SAMPLERS = {
  "euler a": "euler_ancestral", "euler": "euler", "lms": "lms", "heun": "heun", "dpm2": "dpm_2", "dpm2 a": "dpm_2_ancestral", "dpm++ 2s a": "dpmpp_2s_ancestral",
  "dpm++ 2m": "dpmpp_2m", "dpm++ sde": "dpmpp_sde", "dpm++ 2m sde": "dpmpp_2m_sde", "dpm++ 2m sde heun": "dpmpp_2m_sde", "dpm++ 3m sde": "dpmpp_3m_sde",
  "dpm fast": "dpm_fast", "dpm adaptive": "dpm_adaptive", "ddim": "ddim", "ddpm": "ddpm", "unipc": "uni_pc", "lcm": "lcm", "deis": "deis", "ipndm": "ipndm",
  "er sde": "er_sde", "res multistep": "res_multistep", "euler cfg++": "euler_cfg_pp", "euler a cfg++": "euler_ancestral_cfg_pp", "dpm++ 2m cfg++": "dpmpp_2m_cfg_pp",
  "dpm++ 2s a cfg++": "dpmpp_2s_ancestral_cfg_pp", "dpm++ sde gpu": "dpmpp_sde_gpu", "dpm++ 2m sde gpu": "dpmpp_2m_sde_gpu", "dpm++ 3m sde gpu": "dpmpp_3m_sde_gpu",
  "heun pp2": "heunpp2", "gradient estimation": "gradient_estimation", "seeds 2": "seeds_2", "seeds 3": "seeds_3", "sa solver": "sa_solver",
};
const SCHEDULERS = {
  "karras": "karras", "exponential": "exponential", "sgm uniform": "sgm_uniform", "simple": "simple", "normal": "normal", "ddim uniform": "ddim_uniform",
  "beta": "beta", "kl optimal": "kl_optimal", "linear quadratic": "linear_quadratic", "uniform": "normal", "automatic": null,
};
const plain = (name) => String(name ?? "").toLowerCase().replace(/[_]+/g, " ").replace(/\s+/g, " ").trim();
// ComfyUI's sampler and scheduler for a sampler name and schedule type, or null for what isn't known (left as it is).
export function comfySampler(sampler, scheduleType) {
  let name = plain(sampler), scheduler;
  if (scheduleType) {
    const type = plain(scheduleType);
    scheduler = type in SCHEDULERS ? SCHEDULERS[type] : type.replace(/ /g, "_"); // Automatic (null): the sampler's default, left as it is.
  }
  for (const suffix of Object.keys(SCHEDULERS)) {
    if (name.endsWith(` ${suffix}`) && SAMPLERS[name.slice(0, -suffix.length - 1)]) { // "DPM++ 2M Karras"
      if (scheduler === undefined) scheduler = SCHEDULERS[suffix];
      name = name.slice(0, -suffix.length - 1);
      break;
    }
  }
  const comfy = SAMPLERS[name] ?? (name ? name.replace(/ /g, "_") : null); // ComfyUI's own names pass as they are ("dpmpp_2m").
  return { sampler_name: comfy, scheduler: scheduler ?? null };
}
function number(value) {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value !== "string" || value.trim() === "") return null;
  return Number.isNaN(Number(value)) ? null : Number(value);
}
// The meta of an image as plain settings: { positive, negative, seed, steps, cfg, sampler_name, scheduler, width, height }, unknown ones left out.
export function settingsOf(meta) {
  const settings = {};
  if (typeof meta?.prompt === "string") settings.positive = meta.prompt;
  if (typeof meta?.negativePrompt === "string") settings.negative = meta.negativePrompt;
  if (number(meta?.seed) != null && number(meta.seed) >= 0) settings.seed = Math.trunc(number(meta.seed));
  if (number(meta?.steps) != null && number(meta.steps) >= 1) settings.steps = Math.round(number(meta.steps));
  if (number(meta?.cfgScale) != null) settings.cfg = number(meta.cfgScale);
  const { sampler_name, scheduler } = comfySampler(meta?.sampler, meta?.["Schedule type"] ?? meta?.scheduler);
  if (sampler_name) settings.sampler_name = sampler_name;
  if (scheduler) settings.scheduler = scheduler;
  const size = /^\s*(\d+)\s*[x×]\s*(\d+)\s*$/i.exec(String(meta?.Size ?? ""));
  if (size) Object.assign(settings, { width: Number(size[1]), height: Number(size[2]) });
  return settings;
}

const widgetOf = (node, name) => node.widgets?.find((widget) => widget.name === name);
function setWidget(node, name, value) {
  const widget = widgetOf(node, name);
  if (!widget) return false;
  const values = Array.isArray(widget.options?.values) ? widget.options.values : null;
  if (values && !values.includes(value)) return false; // A sampler this ComfyUI doesn't have: left as it is.
  widget.value = value;
  widget.callback?.(value);
  return true;
}
const isSampler = (node) => ["steps", "cfg", "sampler_name", "scheduler"].every((name) => widgetOf(node, name));
// The node feeding an input of a node (by the input's name), if any.
function inputNode(node, name) {
  const slot = node.inputs?.findIndex((input) => input.name === name) ?? -1;
  return slot >= 0 ? node.getInputNode?.(slot) : null;
}
// Puts the settings into the workflow and says what it did: a list like ["prompts in CLIP Dual Text Encode", "seed, steps... in KSampler"].
export function applySettings(settings, graph = app.graph) {
  const done = [], skipped = [];
  const nodes = graph?.nodes ?? [];
  const samplers = nodes.filter(isSampler);
  // Prompts: the DiceForge prompt node, or the CLIP Text Encode nodes on a sampler's positive and negative inputs.
  if (settings.positive != null || settings.negative != null) {
    const dual = nodes.filter((node) => node.comfyClass === PROMPT_NODE_TYPE);
    const linked = dual.filter((node) => samplers.some((sampler) => [inputNode(sampler, "positive"), inputNode(sampler, "negative")].includes(node)));
    const targets = linked.length ? linked : dual.length === 1 ? dual : [];
    for (const node of targets) {
      if (settings.positive != null) setField(node, "positive", settings.positive);
      if (settings.negative != null) setField(node, "negative", settings.negative);
      done.push(`prompts in ${node.title || "CLIP Dual Text Encode"}`);
    }
    if (!targets.length) {
      for (const [field, key] of [["positive", "positive"], ["negative", "negative"]]) {
        if (settings[key] == null) continue;
        const encoders = new Set(samplers.map((sampler) => inputNode(sampler, field)).filter((node) => node && widgetOf(node, "text")));
        for (const node of encoders) if (setWidget(node, "text", settings[key])) done.push(`${field} prompt in ${node.title || node.comfyClass}`);
      }
    }
    if (!done.length) skipped.push("prompts (no prompt node feeds a sampler)");
  }
  // Seed and sampling settings into every sampler; the seed is kept (control after generate: fixed).
  for (const sampler of samplers) {
    const set = [];
    for (const name of ["steps", "cfg", "sampler_name", "scheduler"]) if (settings[name] != null && setWidget(sampler, name, settings[name])) set.push(name);
    const seedName = ["seed", "noise_seed"].find((name) => widgetOf(sampler, name));
    if (settings.seed != null && seedName && setWidget(sampler, seedName, settings.seed)) {
      set.unshift("seed");
      const control = sampler.widgets.find((widget) => widget.name === "control_after_generate" || widget.name === `control_after_generate_${seedName}`);
      if (control) setWidget(sampler, control.name, "fixed");
    }
    if (set.length) done.push(`${set.join(", ")} in ${sampler.title || sampler.comfyClass}`);
    for (const name of ["sampler_name", "scheduler"]) if (settings[name] && !set.includes(name)) skipped.push(`${name} ${settings[name]} (not in ${sampler.title || sampler.comfyClass}'s list)`);
  }
  if (!samplers.length && ["seed", "steps", "cfg", "sampler_name", "scheduler"].some((name) => settings[name] != null)) skipped.push("sampler settings (no sampler)");
  // Size: the empty latents with width and height.
  if (settings.width && settings.height) {
    const latents = nodes.filter((node) => /^Empty.*Latent/i.test(node.comfyClass ?? "") && widgetOf(node, "width") && widgetOf(node, "height"));
    for (const node of latents) {
      setWidget(node, "width", settings.width);
      setWidget(node, "height", settings.height);
      done.push(`${settings.width}×${settings.height} in ${node.title || node.comfyClass}`);
    }
    if (!latents.length) skipped.push(`size ${settings.width}×${settings.height} (no Empty Latent Image)`);
  }
  graph?.setDirtyCanvas?.(true, true);
  return { done, skipped };
}
