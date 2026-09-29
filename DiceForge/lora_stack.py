import itertools
import json
import logging
import os
import comfy.sd
import comfy.utils
import folder_paths
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from .model_info import read_info, info_file
from .seed_modes import MEMORY, SEED_MODES, make_picker, pick_index, seed_mode_tooltip, fingerprint
# LoRA Stack: several LoRAs in one node, like rgthree's Power Lora Loader, with the DiceForge seed modes. The rows live in the "loras" input as JSON,
# edited by the frontend (web/lora_stack.js):
#   {"rows": [{"on": true, "lora": "x.safetensors", "strength": 1.0, "clip": 1.0, "random": false, "min": 0.6, "max": 1.0, "group": ""}, ...],
#    "groups": {"A": {"min": 1, "max": 1}}, "separate_clip": false}
# A row with random picks its strength between min and max (in steps of STRENGTH_STEP) by the seed mode. The rows of a group take turns: the node
# uses min to max of them, every combination being one option of the seed mode, so deck and shuffle go through all of them before repeating one.
STRENGTH_STEP = 0.05
SUBSET_LIMIT = 100000 # Combinations a group may list; a bigger group is an error instead of a long wait.
GROUPS = ("A", "B", "C", "D")
def parse_stack(text):
    try:
        stack = json.loads(text or "{}")
    except ValueError as error:
        raise ValueError(f"LoRA Stack: the stack data is not valid JSON ({error}). Re-add the LoRAs in the node.")
    rows = [row for row in stack.get("rows") or [] if isinstance(row, dict) and row.get("lora")]
    return rows, stack.get("groups") or {}, bool(stack.get("separate_clip"))
def number(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
# Strength of a row: fixed, or picked in [min, max] on the STRENGTH_STEP grid (each row has its own list of values for the seed mode).
def row_strength(row, picker, seed):
    strength = number(row.get("strength"), 1.0)
    if not row.get("random"):
        return strength
    low, high = sorted((number(row.get("min"), strength), number(row.get("max"), strength)))
    count = int(round((high - low) / STRENGTH_STEP)) + 1
    return round(low + pick_index(count, picker, seed, f"LoRA Stack strength {row['lora']} {low} {high}") * STRENGTH_STEP, 4) if count > 1 else low
# The rows of a group to use: every set of min to max of its rows is one option.
def group_pick(name, rows, settings, picker, seed):
    low = max(0, int(number(settings.get("min"), 1)))
    high = max(low, int(number(settings.get("max"), low)))
    low, high = min(low, len(rows)), min(high, len(rows))
    subsets = [subset for size in range(low, high + 1) for subset in itertools.combinations(range(len(rows)), size)]
    if len(subsets) > SUBSET_LIMIT:
        raise ValueError(f"LoRA Stack: group {name} has too many combinations ({len(subsets)}): use fewer LoRAs or a smaller count.")
    if len(subsets) == 1:
        return [rows[index] for index in subsets[0]]
    labels = ", ".join(row["lora"] for row in rows)
    chosen = subsets[pick_index(len(subsets), picker, seed, f"LoRA Stack group {labels} {low}-{high}")]
    return [rows[index] for index in chosen]
# Trigger words of a LoRA: yours from Model info, else Civitai's (what the LoRA Browser shows).
def trigger_words(name):
    info = read_info("loras", name)
    words = [word.strip() for word in ((info.get("user") or {}).get("trigger_words") or "").split(",") if word.strip()]
    return words or list((info.get("civitai") or {}).get("trigger_words") or [])
def short_name(name):
    return os.path.splitext(os.path.basename(name.replace("\\", "/")))[0]
# Node schema (V3 / Nodes 2.0).
class LoraStack(io.ComfyNode):
    cache = {} # LoRA files already read, by path: kept while the stack uses them.
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DiceForgeLoraStack",
            display_name="LoRA Stack",
            category="DiceForge/loaders",
            description="Applies several LoRAs, each with its own on/off and strength, like rgthree's Power Lora Loader. A strength can be a random range, "
                "and groups of LoRAs can take turns (use 1 of these 5), picked with the DiceForge seed modes. Also outputs the trigger words and what was applied.",
            search_aliases=["lora", "loras", "lora stack", "power lora loader", "multiple loras", "lora loader", "random lora", "seed modes"],
            inputs=[
                io.Model.Input("model", tooltip="The diffusion model the LoRAs are applied to."),
                io.Clip.Input("clip", optional=True, tooltip="The CLIP model the LoRAs are applied to. Leave it unconnected to change only the model."),
                io.String.Input("loras", default='{"rows": [], "groups": {}}', tooltip="The LoRA rows, edited in the node (JSON)."),
                io.Int.Input(
                    "seed",
                    default=0,
                    min=0,
                    max=0xFFFFFFFFFFFFFFFF,
                    control_after_generate=True,
                    tooltip="Seed for random strengths and groups. With deck or sequential, set control after generate to increment.",
                ),
                io.Combo.Input("seed_mode", options=SEED_MODES, default="random", tooltip=seed_mode_tooltip("strengths and group combinations"), advanced=True),
            ],
            outputs=[
                io.Model.Output(display_name="model", tooltip="The model with the LoRAs applied."),
                io.Clip.Output(display_name="clip", tooltip="The CLIP with the LoRAs applied (unconnected CLIP input: nothing)."),
                io.String.Output(display_name="triggers", tooltip="The trigger words of the applied LoRAs (yours from Model info, else Civitai's), for CLIP Dual Text Encode."),
                io.String.Output(display_name="lora_info", tooltip="The applied LoRAs and strengths, for example 'detail 0.8, style_a 1.0', for a file name or a note."),
            ],
        )
    # Runs again when trigger words change in Model info, and every time in the modes that remember earlier runs.
    @classmethod
    def fingerprint_inputs(cls, loras="", seed_mode="random", **kwargs):
        rows, _groups, _separate = parse_stack(loras)
        info_times = []
        for row in rows:
            path = info_file("loras", row["lora"])
            info_times.append(os.path.getmtime(path) if os.path.isfile(path) else None)
        return info_times, fingerprint(seed_mode)
    @classmethod
    def load(cls, path):
        if path not in cls.cache:
            cls.cache[path] = comfy.utils.load_torch_file(path, safe_load=True, return_metadata=True) # (weights, metadata), as the core Load LoRA reads them.
        return cls.cache[path]
    # Picks the rows to use (groups) and their strengths by the seed mode, then applies them in order.
    @classmethod
    def execute(cls, model, loras="", seed=0, seed_mode="random", clip=None):
        rows, groups, separate_clip = parse_stack(loras)
        rows = [row for row in rows if row.get("on", True)]
        picker = make_picker(seed_mode, seed)
        used = set()
        for name in GROUPS:
            members = [row for row in rows if row.get("group") == name]
            if members:
                used.update(id(row) for row in group_pick(name, members, groups.get(name) or {}, picker, seed))
        applied, info, triggers, paths = [], [], [], set()
        for row in rows:
            if row.get("group") in GROUPS and id(row) not in used:
                continue
            path = folder_paths.get_full_path("loras", row["lora"])
            if path is None:
                raise ValueError(f"LoRA Stack: {row['lora']} is not in the loras folders. Pick another LoRA in the node or put the file back.")
            strength = row_strength(row, picker, seed)
            strength_clip = number(row.get("clip"), 1.0) if separate_clip else strength
            if clip is None:
                strength_clip = 0
            if strength != 0 or strength_clip != 0:
                lora, metadata = cls.load(path)
                model, clip = comfy.sd.load_lora_for_models(model, clip, lora, strength, strength_clip, lora_metadata=metadata)
            paths.add(path)
            applied.append((row["lora"], strength, strength_clip))
            info.append(f"{short_name(row['lora'])} {strength:g}" + (f"/{strength_clip:g}" if separate_clip and clip is not None and strength_clip != strength else ""))
            triggers += [word for word in trigger_words(row["lora"]) if word not in triggers]
        for path in list(cls.cache):
            if path not in paths:
                del cls.cache[path] # LoRAs no longer in the stack leave memory.
        MEMORY.save()
        logging.info(f"[DiceForge] LoRA Stack | {', '.join(info) or 'no LoRA'} | Seed: {seed} ({seed_mode})")
        return io.NodeOutput(model, clip, ", ".join(triggers), ", ".join(info))
# Extension entry point for ComfyUI V3 node registration.
class LoraStackExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [LoraStack]
async def comfy_entrypoint():
    return LoraStackExtension()
