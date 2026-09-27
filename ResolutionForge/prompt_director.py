import glob
import hashlib
import json
import os
import random
import re
import folder_paths
import yaml
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from .tag_library import get_library, tag_key
# Scene data: the YAML files next to this node, plus any YAML files in ComfyUI/models/prompt_director (their options are added to the slots with the same name).
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompt_director")
folder_paths.add_model_folder_path("prompt_director", os.path.join(folder_paths.models_dir, "prompt_director"), is_default=True)
RANDOM = "random"
NONE = "none"
CUSTOM = object() # Marks a slot filled from an override text input: conditions that require it never match, conditions that exclude it never trigger.
GROUP_ORDER = ["character", "outfit", "expression", "pose", "location", "details"] # Slot groups the LLM rewrites, in prompt order.
TAG_CHECKS = ["drop unknown", "keep unknown", "off"]
# Data file lookup: bundled files first, then user files.
def data_files():
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*.yaml")))
    for folder in folder_paths.get_folder_paths("prompt_director"):
        files += sorted(glob.glob(os.path.join(folder, "*.yaml")))
    return files
# Data loading: merges the slots (by name, keeping the first file's order) and the model presets of all data files.
def load_data():
    slots, models = {}, {}
    for path in data_files():
        with open(path, encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        for slot in data.get("slots", []):
            if slot["name"] in slots:
                slots[slot["name"]]["options"] += slot.get("options", [])
            else:
                slots[slot["name"]] = {"group": "details", "when": {}, **slot, "options": list(slot.get("options", []))}
        models.update(data.get("models", {}))
    for slot in slots.values():
        for option in slot["options"]:
            option.setdefault("id", option.get("tags", ""))
            option.setdefault("tags", "")
            option["names"] = {option["id"], *option.get("attrs", [])}
    return list(slots.values()), models
# Data files signature (paths and modification times), so the node runs again when a data file changes.
def data_signature():
    return hashlib.sha256(repr([(path, os.path.getmtime(path)) for path in data_files()]).encode()).hexdigest()
# Option ids of a slot, for the node's dropdowns (in data order, without duplicates).
def slot_ids(slots, name):
    slot = next((slot for slot in slots if slot["name"] == name), {"options": []})
    return list(dict.fromkeys(option["id"] for option in slot["options"]))
# Tag list cleanup: splits on commas, turns Danbooru underscores into spaces (except score_/source_/rating_ tags), lowercases, drops sentences and duplicates.
def clean_tags(*parts):
    tags, seen = [], set()
    for part in parts:
        for tag in str(part or "").replace("\n", ",").split(","):
            tag = tag.strip().strip("\"'").strip()
            if not tag or len(tag) > 60:
                continue
            if not tag.startswith(("score_", "source_", "rating_")):
                tag = tag.replace("_", " ")
            tag = re.sub(r"\s+", " ", tag.lower())
            if re.fullmatch(r"[^()\\:]+ \([^()\\:]+\)", tag):
                tag = tag.replace("(", "\\(").replace(")", "\\)") # Danbooru qualifiers like "bar (place)" are escaped, or the image model reads the brackets as a weight.
            if tag not in seen:
                seen.add(tag)
                tags.append(tag)
    return ", ".join(tags)
# Scene building: fills the slots in order, each option chosen at random (by seed) among those whose conditions match the slots picked before.
class Scene:
    def __init__(self, slots, forced, custom, rng):
        self.slots, self.forced, self.custom, self.rng = slots, forced, custom, rng
        self.picked = {} # slot name -> option dict, CUSTOM, or None when the slot is skipped
    # Condition check: every slot in `when` must have picked one of the names; slots not decided yet only fail when `strict` is set, override texts only when `custom_fails` is set.
    def matches(self, when, strict=True, custom_fails=True):
        for name, allowed in (when or {}).items():
            if name not in self.picked:
                if strict:
                    return False
                continue
            option = self.picked[name]
            if option is CUSTOM and not custom_fails:
                continue
            if option is None or option is CUSTOM or not option["names"] & set(allowed):
                return False
        return True
    # Exclusion check: true when any slot in `unless` picked one of the names.
    def excluded(self, unless):
        for name, blocked in (unless or {}).items():
            option = self.picked.get(name)
            if option is not None and option is not CUSTOM and option["names"] & set(blocked):
                return True
        return False
    # Option filter: conditions match, and the choice leaves every later forced slot possible (so a random location stays outdoor when the weather is forced to snow).
    def allowed(self, slot, option, lookahead=True):
        if not self.matches(option.get("when")) or self.excluded(option.get("unless")):
            return False
        if not lookahead:
            return True
        self.picked[slot["name"]] = option
        try:
            for later in self.slots[self.slots.index(slot) + 1:]:
                value = self.forced.get(later["name"])
                if value in (None, NONE, RANDOM):
                    continue
                if not self.matches(later["when"], strict=False):
                    return False
                targets = [candidate for candidate in later["options"] if candidate["id"] == value]
                if targets and not any(self.matches(target.get("when"), strict=False) and not self.excluded(target.get("unless")) for target in targets):
                    return False
            return True
        finally:
            del self.picked[slot["name"]]
    # Main method: picks every slot in order; forced dropdown values and override texts win over random picks.
    def build(self):
        for slot in self.slots:
            name, value = slot["name"], self.forced.get(slot["name"], RANDOM)
            if slot["group"] in self.custom:
                self.picked[name] = CUSTOM
                continue
            # A slot is skipped when it does not apply; a forced value still applies next to an override text (a forced snow with your own location).
            if value == NONE or not self.matches(slot["when"], custom_fails=value == RANDOM):
                self.picked[name] = None
                continue
            options = slot["options"] if value == RANDOM else [option for option in slot["options"] if option["id"] == value]
            if name == "scene" and value == RANDOM and set(self.custom) & {"character", "outfit", "expression", "pose"}:
                options = [option for option in options if "character" in option["names"]] # Your own outfit, pose, expression or appearance means there is a character.
            candidates = [option for option in options if self.allowed(slot, option)]
            candidates = candidates or [option for option in options if self.allowed(slot, option, lookahead=False)]
            if not candidates and value != RANDOM:
                candidates = options # A forced value is used even when its conditions do not match.
            if not candidates:
                self.picked[name] = None
                continue
            self.picked[name] = self.rng.choices(candidates, weights=[option.get("weight", 1) for option in candidates])[0]
        return self
    # Tags of a slot, or of every slot in a group (override text for overridden groups).
    def tags(self, name):
        option = self.picked.get(name)
        return option["tags"] if option not in (None, CUSTOM) else ""
    def group_tags(self, group):
        if group in self.custom:
            return self.custom[group]
        return clean_tags(*(self.tags(slot["name"]) for slot in self.slots if slot["group"] == group))
    def value(self, name):
        option = self.picked.get(name)
        return "custom" if option is CUSTOM else (option["id"] if option else NONE)
    @property
    def has_character(self):
        option = self.picked.get("scene")
        return option is not None and "character" in option["names"]
# LLM instructions: the model fills in the scene as Danbooru tags, keeping the fixed parts and the logic between slots.
SYSTEM_PROMPT = """You write prompts for anime image models that use Danbooru tags (Illustrious, Pony).
You get a scene plan: fixed parts that must stay as they are, suggestions, and sometimes an idea from the user.
Write the scene as Danbooru tags and answer with one JSON object only, no other text.

Rules:
- Every value is a string of lowercase Danbooru tags separated by commas. No sentences, no quality or rating tags, no artist names.
- Keep every FIXED part exactly. Follow the idea if there is one. Keep the suggestions unless they conflict with the idea or the fixed parts; then change them to fit.
- The scene must be consistent: the outfit fits the theme, place and weather; the pose fits the framing (no legs, shoes or feet tags for portrait or upper body); the expression fits the pose; the lighting fits the time of day and the weather. No contradicting tags.
- Only one character unless the idea asks for more. Do not add characters, text or logos.
- Add a few concrete details (accessories, props, background details, lighting) that fit the scene, 3 to 12 tags in "details".
"""
CHARACTER_KEYS = """{"character": "appearance tags: hair, eyes, body, accessories worn",
 "outfit": "clothing tags, shoes only if the feet are visible",
 "expression": "facial expression tags",
 "pose": "pose, action, gaze and held items",
 "location": "place and background tags",
 "details": "extra consistent details: props, background details, lighting, effects"}"""
SCENERY_KEYS = """{"location": "place and background tags",
 "details": "extra consistent details: background details, lighting, effects"}"""
# LLM request: the scene plan as text, with the fixed parts, suggestions, tag ideas and the JSON layout to answer with.
def llm_request(scene, idea, hints=None):
    lines = [f"Theme: {scene.value('theme')}"]
    fixed = [f"scene: {scene.tags('scene')}"]
    for name in ("framing", "time", "weather"):
        if scene.picked.get(name):
            fixed.append(f"{name}: {scene.tags(name)}")
    groups = GROUP_ORDER if scene.has_character else ["location", "details"]
    fixed += [f"{group}: {scene.custom[group]}" for group in groups if group in scene.custom]
    suggested = [f"{group}: {scene.group_tags(group)}" for group in groups if group not in scene.custom and scene.group_tags(group)]
    lines.append("FIXED:\n" + "\n".join(f"- {line}" for line in fixed))
    if suggested:
        lines.append("Suggestions:\n" + "\n".join(f"- {line}" for line in suggested))
    if idea.strip():
        lines.append(f"Idea: {idea.strip()}")
    if hints:
        lines.append("Tag ideas (real Danbooru tags; use only the ones that fit the scene, or none):\n" + "\n".join(f"- {group}: {', '.join(tags)}" for group, tags in hints.items() if tags))
    lines.append("Answer with this JSON layout:\n" + (CHARACTER_KEYS if scene.has_character else SCENERY_KEYS))
    return "\n\n".join(lines)
# LLM answer parsing: takes the first {...} block after any thinking, and returns its values as tag strings (None when there is no valid JSON).
def parse_llm_answer(text):
    text = text.split("</think>")[-1]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return {key: clean_tags(", ".join(map(str, value)) if isinstance(value, list) else value) for key, value in data.items()}
SLOTS, MODELS = load_data()
# Node schema (V3 / Nodes 2.0): builds a consistent anime scene prompt (Danbooru tags) from rules, optionally rewritten by an LLM such as Qwen3-VL.
class PromptDirector(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        choice = lambda name, extra=(): [RANDOM, *extra, *slot_ids(SLOTS, name)]
        override = lambda name, what: io.String.Input(name, default="", tooltip=f"Your own {what} tags. Leave empty to let the node pick them.", advanced=True)
        return io.Schema(
            node_id="PromptDirector",
            display_name="Prompt Director (Anime)",
            category="text",
            description="Builds a consistent anime scene prompt as Danbooru tags: theme, place, time, weather, outfit, pose and expression are picked from rules that keep them logical. Connect an LLM (for example Qwen3-VL from Load CLIP) to have it write the scene in more detail.",
            search_aliases=["prompt builder", "prompt generator", "scene", "danbooru", "illustrious", "pony", "tipo"],
            inputs=[
                io.String.Input("idea", multiline=True, default="", tooltip="Optional idea for the scene, as tags or words (for example: knight girl eating ramen). Used by the LLM; without an LLM it is added as tags."),
                io.Combo.Input("theme", options=choice("theme"), default=RANDOM, tooltip="Setting of the scene."),
                io.Combo.Input("scene", options=choice("scene"), default=RANDOM, tooltip="One character, or scenery without people."),
                io.Combo.Input("framing", options=choice("framing"), default=RANDOM, tooltip="How much of the character is visible. Poses and shoes follow it."),
                io.Combo.Input("model", options=list(MODELS), default=next(iter(MODELS), None), tooltip="Model family, for its quality, rating and negative tags."),
                io.Combo.Input("rating", options=["general", "sensitive"], default="general", tooltip="Content rating tag; also allows outfits like swimsuits when sensitive."),
                io.Int.Input("seed", default=0, min=0, max=0xFFFFFFFFFFFFFFFF, control_after_generate=True, tooltip="Seed for the random picks and the LLM. The same seed gives the same prompt."),
                io.Clip.Input("clip", optional=True, tooltip="Optional LLM to write the scene in more detail, such as Qwen3-VL loaded with Load CLIP. Without it, the prompt is built from the rules only."),
                io.Combo.Input("time", options=choice("time"), default=RANDOM, advanced=True),
                io.Combo.Input("weather", options=choice("weather", [NONE]), default=RANDOM, advanced=True, tooltip="Only used outdoors."),
                override("character", "appearance (hair, eyes)"),
                override("outfit", "outfit"),
                override("expression", "expression"),
                override("pose", "pose"),
                override("location", "location"),
                io.Int.Input("max_length", default=400, min=64, max=4096, advanced=True, tooltip="Maximum number of tokens the LLM writes."),
                io.Float.Input("temperature", default=0.8, min=0.01, max=2.0, step=0.01, advanced=True, tooltip="LLM creativity: higher gives more varied details."),
                io.Combo.Input("tag_check", options=TAG_CHECKS, default=TAG_CHECKS[0], advanced=True, tooltip="Checks the LLM's tags against the Danbooru tag library: fixes aliases, removes explicit tags (and sensitive ones when the rating is general) and tags that contradict each other; 'drop unknown' also removes tags the image model does not know."),
                io.Int.Input("tag_hints", default=20, min=0, max=100, advanced=True, tooltip="Number of real Danbooru tags suggested to the LLM for each part of the scene (0 to turn off)."),
            ],
            # Outputs for the node: the prompts, a readable breakdown of the scene, and the seed.
            outputs=[
                io.String.Output(display_name="positive_text", tooltip="Positive prompt: quality and rating tags, then the scene."),
                io.String.Output(display_name="negative_text", tooltip="Negative prompt for the chosen model and rating."),
                io.String.Output(display_name="scene", tooltip="What was picked for each slot, and whether the LLM was used."),
                io.Int.Output(display_name="seed", tooltip="The seed used for this run."),
            ],
        )
    # Method to run the node again when a data file changes, even if the inputs are the same.
    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return data_signature()
    # LLM call, the same way as the core Generate Text node, returning the decoded answer.
    @staticmethod
    def generate(clip, request, seed, max_length, temperature):
        tokens = clip.tokenize(request, image=None, skip_template=False, min_length=1, thinking=False, system_prompt=SYSTEM_PROMPT)
        generated_ids = clip.generate(tokens, do_sample=True, max_length=max_length, temperature=temperature, top_k=64, top_p=0.95, min_p=0.05, repetition_penalty=1.05, presence_penalty=0.0, seed=seed, mtp=True)
        return clip.decode(generated_ids)
    # Main method: builds the scene from the rules, lets the LLM rewrite it when connected, and assembles the prompts.
    @classmethod
    def execute(cls, idea="", theme=RANDOM, scene=RANDOM, framing=RANDOM, model=None, rating="general", seed=0, clip=None, time=RANDOM, weather=RANDOM,
                character="", outfit="", expression="", pose="", location="", max_length=400, temperature=0.8, tag_check=TAG_CHECKS[0], tag_hints=20):
        slots, models = load_data()
        forced = {"theme": theme, "scene": scene, "framing": framing, "time": time, "weather": weather}
        custom = {group: clean_tags(text) for group, text in [("character", character), ("outfit", outfit), ("expression", expression), ("pose", pose), ("location", location)] if text.strip()}
        rng = random.Random(seed) #Seed behavior for reproducible scenes.
        built = Scene(slots, forced, custom, rng)
        built.picked["rating"] = {"names": {rating}, "id": rating, "tags": ""} # Rating is a condition for some options (swimsuit).
        built.build()
        groups = GROUP_ORDER if built.has_character else ["location", "details"]
        parts = {group: built.group_tags(group) for group in groups}
        preset = models.get(model, {})
        min_count = preset.get("min_post_count", 100) # Tags with fewer Danbooru posts than this count as unknown to the image model.
        status, library, dropped = "not connected", None, []
        if clip is not None:
            library = get_library() if tag_check != "off" or tag_hints > 0 else None
            hint_rng = random.Random(f"{seed}-hints") # Separate random stream, so the hints do not change the scene picks.
            hints = {group: library.hints(group, tag_hints, rating, min_count, hint_rng) for group in groups if group not in custom} if library and tag_hints > 0 else None
            answer = cls.generate(clip, llm_request(built, idea, hints), seed, max_length, temperature)
            data = parse_llm_answer(answer)
            if data is None:
                status = "failed (no valid JSON in the answer), rules used instead"
                print(f"[Prompt Director] LLM answer was not valid JSON, using the rule-based scene. Answer: {answer[:500]}")
            else:
                status = "used"
                # Tag check: fixed tags come first, so an LLM tag that contradicts them (another framing, another hair length) is the one removed.
                taken = {tag_key(tag) for tag in clean_tags(built.tags("scene"), built.tags("framing"), *custom.values()).split(", ") if tag}
                for group in groups:
                    if group in custom or not data.get(group):
                        taken |= {tag_key(tag) for tag in parts[group].split(", ") if tag}
                        continue
                    tags = [tag for tag in data[group].split(", ") if tag]
                    if library and tag_check != "off":
                        tags, removed = library.check(tags, rating, min_count, tag_check == "drop unknown", taken)
                        dropped += removed
                    parts[group] = ", ".join(tags) or parts[group] # The LLM answer replaces the suggestion, so details like lighting follow the place it chose.
        # Prompt assembly: quality and rating first (Pony needs its score tags first), then the scene in Danbooru order.
        structure = [built.tags("scene"), idea if status != "used" else ""] # Without the LLM, the idea is added as tags.
        scene_tags = [parts.get("character"), parts.get("outfit"), parts.get("expression"), parts.get("pose"), built.tags("framing"), built.tags("theme"), parts.get("location"), built.tags("time"), built.tags("weather"), parts.get("details")]
        positive_text = clean_tags(preset.get("quality"), preset.get("rating", {}).get(rating), *structure, *scene_tags)
        negative_text = clean_tags(preset.get("negative"), preset.get("negative_rating", {}).get(rating))
        breakdown = [f"{slot['name']}: {built.value(slot['name'])}" for slot in slots] + [f"llm: {status}"]
        if library:
            breakdown += [f"tag library: {library.status}", f"removed tags: {', '.join(dropped) or 'none'}"]
        breakdown = "\n".join(breakdown)
        # Logging the scene for debugging and verification purposes.
        print(f"[Prompt Director] Seed: {seed} | LLM: {status} | {positive_text}")
        return io.NodeOutput(positive_text, negative_text, breakdown, seed)
# Extension entry point for ComfyUI V3 node registration.
class PromptDirectorExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [PromptDirector]
async def comfy_entrypoint():
    return PromptDirectorExtension()
