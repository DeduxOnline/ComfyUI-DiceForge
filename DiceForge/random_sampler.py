import logging
import re
import comfy.samplers
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from .seed_modes import MEMORY, SEED_MODES, make_picker, pick_label, seed_mode_tooltip, fingerprint
SAMPLERS, SCHEDULERS = comfy.samplers.KSampler.SAMPLERS, comfy.samplers.KSampler.SCHEDULERS
# A list typed in a text field: names separated by commas or new lines, duplicates dropped; "*" (or "all") is every known name.
def parse_names(text, known, what):
    names = list(dict.fromkeys(name.strip() for name in re.split(r"[,\n]", text) if name.strip()))
    if any(name.lower() in ("*", "all") for name in names):
        return list(known)
    unknown = [name for name in names if name not in known]
    if unknown:
        raise ValueError(f"Random Sampler: unknown {what} {', '.join(unknown)}. Known {what}s: {', '.join(known)}.")
    if not names:
        raise ValueError(f"Random Sampler: no {what}s listed (use * for all).")
    return names
# Output for a list input of another node (KSampler's sampler_name and scheduler). Its type is the list of options itself, as in V1 nodes: ComfyUI's
# link check accepts that for list inputs, but not the plain "COMBO" type of a V3 Combo output ("Return type mismatch between linked nodes").
class OptionsOutput(io.Combo.Output):
    @property
    def io_type(self):
        return self.options
def options_output(display_name, options, tooltip):
    return OptionsOutput(display_name=display_name, options=list(options), tooltip=tooltip)
# Node schema (V3 / Nodes 2.0): picks a sampler and scheduler pair for KSampler from the listed ones, with the DiceForge seed modes: deck or
# sequential go through every pair once, for a sampler comparison with Dice Grid.
class RandomSampler(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DiceForgeRandomSampler",
            display_name="Random Sampler",
            category="DiceForge/sampling",
            description="Picks a sampler and scheduler pair from the listed ones for KSampler, with the DiceForge seed modes (deck, sequential... go through every pair once).",
            search_aliases=["random sampler", "random scheduler", "sampler", "scheduler", "sampler comparison", "random", "seed modes"],
            inputs=[
                io.String.Input(
                    "samplers",
                    multiline=True,
                    default="euler, euler_ancestral, dpmpp_2m, dpmpp_2m_sde, dpmpp_3m_sde",
                    tooltip="Samplers to pick from, separated by commas or new lines (the names in KSampler's list). * for every sampler.",
                ),
                io.String.Input(
                    "schedulers",
                    multiline=True,
                    default="normal, karras",
                    tooltip="Schedulers to pick from, separated by commas or new lines. * for every scheduler. Every sampler is paired with every scheduler.",
                ),
                io.Int.Input(
                    "seed",
                    default=0,
                    min=0,
                    max=0xFFFFFFFFFFFFFFFF,
                    control_after_generate=True,
                    tooltip="Seed for the pick. With deck or sequential, set control after generate to increment.",
                ),
                io.Combo.Input(
                    "seed_mode",
                    options=SEED_MODES,
                    default="random",
                    tooltip=seed_mode_tooltip("sampler and scheduler pairs").replace("(sorted by name)", "(each sampler with every scheduler, in the listed order)"),
                    advanced=True,
                ),
            ],
            outputs=[
                options_output("sampler_name", SAMPLERS, "Connect to the sampler_name input of KSampler (or KSampler Advanced)."),
                options_output("scheduler", SCHEDULERS, "Connect to the scheduler input of KSampler (or KSampler Advanced)."),
                io.String.Output(display_name="label", tooltip="\"sampler / scheduler\", for example for the label of Dice Grid."),
                io.String.Output(display_name="sampler_text", tooltip="The sampler name as text, for example for the row_label of an XY Dice Grid."),
                io.String.Output(display_name="scheduler_text", tooltip="The scheduler name as text, for example for the label of an XY Dice Grid."),
            ],
        )
    # Method to run the node every time in the modes that remember earlier runs, instead of using ComfyUI's cache.
    @classmethod
    def fingerprint_inputs(cls, seed_mode="random", **kwargs):
        return fingerprint(seed_mode)
    # Main method: every listed sampler with every listed scheduler is one option; the seed mode picks one pair.
    @classmethod
    def execute(cls, samplers="", schedulers="", seed=0, seed_mode="random"):
        pairs = [f"{sampler} / {scheduler}" for sampler in parse_names(samplers, SAMPLERS, "sampler") for scheduler in parse_names(schedulers, SCHEDULERS, "scheduler")]
        label = pick_label(pairs, make_picker(seed_mode, seed), seed)
        MEMORY.save()
        sampler, scheduler = label.split(" / ")
        logging.info(f"[DiceForge] Random Sampler | {label} | Seed: {seed} ({seed_mode})")
        return io.NodeOutput(sampler, scheduler, label, sampler, scheduler)
# Extension entry point for ComfyUI V3 node registration.
class RandomSamplerExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [RandomSampler]
async def comfy_entrypoint():
    return RandomSamplerExtension()
