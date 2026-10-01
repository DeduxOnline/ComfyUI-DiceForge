import asyncio
import itertools
import json
import logging
import math
import os
import re
import comfy.sd
import comfy.utils
import folder_paths
from aiohttp import web
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from .model_info import KINDS, json_body, read_info, info_file
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
    if stack is None:
        stack = {}
    if not isinstance(stack, dict):
        raise ValueError("LoRA Stack: the stack data is not a LoRA Stack (no rows). Re-add the LoRAs in the node.")
    return clean_rows(stack.get("rows")), clean_groups(stack.get("groups")), bool(stack.get("separate_clip"))
# Rows and groups as the node uses them, whatever the JSON holds (a hand-edited workflow, a preset from elsewhere): rows are objects with a LoRA name,
# groups are objects with min and max.
def clean_rows(rows):
    return [row for row in rows if isinstance(row, dict) and isinstance(row.get("lora"), str) and row["lora"]] if isinstance(rows, list) else []
def clean_groups(groups):
    return {name: settings for name, settings in groups.items() if isinstance(settings, dict)} if isinstance(groups, dict) else {}
def number(value, default):
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return value if math.isfinite(value) else default # NaN or infinity (possible in JSON written by hand) count as not set.
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
    total = sum(math.comb(len(rows), size) for size in range(low, high + 1)) # Counted before listing: 40 rows would be 2^40 combinations.
    if total > SUBSET_LIMIT:
        raise ValueError(f"LoRA Stack: group {name} has too many combinations ({total}): use fewer LoRAs or a smaller count.")
    subsets = [subset for size in range(low, high + 1) for subset in itertools.combinations(range(len(rows)), size)]
    if len(subsets) == 1:
        return [rows[index] for index in subsets[0]]
    labels = ", ".join(row["lora"] for row in rows)
    chosen = subsets[pick_index(len(subsets), picker, seed, f"LoRA Stack group {labels} {low}-{high}")]
    return [rows[index] for index in chosen]
# Trigger words of a LoRA: yours from Model info, else Civitai's (what the LoRA Browser shows).
def known_triggers(name):
    info = read_info("loras", name)
    user = [word.strip() for word in ((info.get("user") or {}).get("trigger_words") or "").split(",") if word.strip()]
    return user, [str(word).strip() for word in (info.get("civitai") or {}).get("trigger_words") or [] if str(word).strip()]
def trigger_words(name):
    user, civitai = known_triggers(name)
    return user or civitai
# The trigger words a row puts in the triggers output: "all" (default: the LoRA's trigger words), "none", or "custom" (the words picked in the
# row's 🏷 list, kept in the row).
def row_triggers(row):
    mode = row.get("triggers") or "all"
    if mode == "none":
        return []
    if mode == "custom":
        words = row.get("trigger_words")
        words = words.split(",") if isinstance(words, str) else words if isinstance(words, list) else [] # A list from the node; text with commas by hand.
        return [str(word).strip() for word in words if isinstance(word, (str, int, float)) and not isinstance(word, bool) and str(word).strip()]
    return trigger_words(row["lora"])
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
            triggers += [word for word in row_triggers(row) if word not in triggers]
        for path in list(cls.cache):
            if path not in paths:
                del cls.cache[path] # LoRAs no longer in the stack leave memory.
        MEMORY.save()
        logging.info(f"[DiceForge] LoRA Stack | {', '.join(info) or 'no LoRA'} | Seed: {seed} ({seed_mode})")
        return io.NodeOutput(model, clip, ", ".join(triggers), ", ".join(info))
# Presets: a stack saved as a file (ComfyUI/user/DiceForge/lora_presets/name.json), to apply in any LoRA Stack or share. The same file is what
# Export downloads and Import reads.
PRESET_FOLDER = os.path.join(folder_paths.get_user_directory(), "DiceForge", "lora_presets")
PRESET_NAME = re.compile(r"[\w\-. ()]+")
def preset_path(name):
    name = (name if isinstance(name, str) else "").strip().removesuffix(".json")
    if not PRESET_NAME.fullmatch(name) or name.startswith("."):
        raise web.HTTPBadRequest(text=f"LoRA Stack: {name!r} is not a usable preset name (letters, digits, space, - _ . ( )).")
    return name, os.path.join(PRESET_FOLDER, name + ".json")
def preset_stack(data):
    stack = data.get("stack") if isinstance(data, dict) and "stack" in data else data # A preset file, or a bare stack.
    if not isinstance(stack, dict) or not isinstance(stack.get("rows"), list):
        raise web.HTTPBadRequest(text="LoRA Stack: this is not a LoRA Stack preset (no rows).")
    return {"rows": clean_rows(stack["rows"]), "groups": clean_groups(stack.get("groups")), "separate_clip": bool(stack.get("separate_clip"))}
def list_presets():
    presets = []
    if os.path.isdir(PRESET_FOLDER):
        for file in sorted(os.listdir(PRESET_FOLDER), key=str.lower):
            if file.endswith(".json"):
                try:
                    with open(os.path.join(PRESET_FOLDER, file), encoding="utf-8") as handle:
                        stack = preset_stack(json.load(handle))
                except (OSError, ValueError, web.HTTPException):
                    continue
                presets.append({"name": file[:-5], "loras": [row["lora"] for row in stack["rows"]], "modified": os.path.getmtime(os.path.join(PRESET_FOLDER, file))})
    return presets
# Base models for the mismatch warning: what Model info already knows about each file (nothing is hashed or asked here).
def cached_base(kind, name):
    path = folder_paths.get_full_path(kind, name) if kind in KINDS else None
    if not path:
        return None
    info, stat = read_info(kind, name), os.stat(path)
    if info.get("size") != stat.st_size or info.get("mtime") != stat.st_mtime:
        return None
    return (info.get("civitai") or {}).get("base_model")
def register_routes():
    try:
        from server import PromptServer
        routes = PromptServer.instance.routes
    except Exception: # Loaded outside the ComfyUI server (tests): no routes.
        return
    @routes.get("/diceforge/lora-presets")
    async def get_presets(request):
        return web.json_response({"folder": PRESET_FOLDER, "presets": list_presets()})
    @routes.get("/diceforge/lora-presets/file")
    async def get_preset(request):
        name, path = preset_path(request.rel_url.query.get("name"))
        if not os.path.isfile(path):
            raise web.HTTPNotFound(text=f"LoRA Stack: no preset {name}.")
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except ValueError as error:
            raise web.HTTPBadRequest(text=f"LoRA Stack: preset {name} is damaged, it is not valid JSON ({error}).") from None
        return web.json_response({"name": name, "stack": preset_stack(data)})
    @routes.post("/diceforge/lora-presets")
    async def save_preset(request):
        body = await json_body(request)
        name, path = preset_path(body.get("name"))
        stack = preset_stack(body.get("stack")) # Checked before anything is written.
        if os.path.isfile(path) and not body.get("overwrite"):
            raise web.HTTPConflict(text=f"LoRA Stack: a preset named {name} already exists.")
        os.makedirs(PRESET_FOLDER, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"type": "DiceForge LoRA Stack preset", "version": 1, "stack": stack}, handle, ensure_ascii=False, indent=1)
        return web.json_response({"saved": name})
    @routes.delete("/diceforge/lora-presets")
    async def delete_preset(request):
        name, path = preset_path(request.rel_url.query.get("name"))
        if os.path.isfile(path):
            os.remove(path)
        return web.json_response({"deleted": name})
    @routes.post("/diceforge/lora-triggers")
    async def lora_triggers(request):
        names = (await json_body(request)).get("loras")
        names = names[:500] if isinstance(names, list) else [] # Answers in the same order: an entry that isn't a file name gets no words.
        found = await asyncio.get_running_loop().run_in_executor(None, lambda: [known_triggers(name) if isinstance(name, str) else ([], []) for name in names])
        return web.json_response({"triggers": [{"user": user, "civitai": civitai} for user, civitai in found]})
    @routes.post("/diceforge/model-bases")
    async def model_bases(request):
        items = (await json_body(request)).get("items")
        items = items[:500] if isinstance(items, list) else []
        found = await asyncio.get_running_loop().run_in_executor(None, lambda: [cached_base(item.get("kind"), item.get("file"))
                                                                                if isinstance(item, dict) and isinstance(item.get("file"), str) else None for item in items])
        return web.json_response({"bases": found})
register_routes()
# Extension entry point for ComfyUI V3 node registration.
class LoraStackExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [LoraStack]
async def comfy_entrypoint():
    return LoraStackExtension()
