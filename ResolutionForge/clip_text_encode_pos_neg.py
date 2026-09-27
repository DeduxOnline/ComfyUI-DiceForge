import hashlib
import os
import random
import re
import folder_paths
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
# Wildcards: __name__ in a prompt is replaced by a random line of name.txt from the wildcards folders (ComfyUI/models/wildcards by default, more can be added in extra_model_paths.yaml).
folder_paths.add_model_folder_path("wildcards", os.path.join(folder_paths.models_dir, "wildcards"), is_default=True)
WILDCARD_PATTERN = re.compile(r"__([\w\-./]+?)__")
MAX_DEPTH = 50 # Nesting limit for wildcards and {a|b} choices, to stop wildcards that include each other forever.
# Wildcard file lookup: name may contain subfolders (__colors/warm__ -> colors/warm.txt), and must stay inside a wildcards folder.
def find_wildcard(name):
    for folder in folder_paths.get_folder_paths("wildcards"):
        folder = os.path.abspath(folder)
        path = os.path.abspath(os.path.join(folder, *name.split("/")) + ".txt")
        if path.startswith(folder + os.sep) and os.path.isfile(path):
            return path
    return None
# Wildcard file reading: one option per line, skipping empty lines and # comments.
def read_wildcard(name):
    path = find_wildcard(name)
    if path is None:
        folders = ", ".join(folder_paths.get_folder_paths("wildcards"))
        raise ValueError(f"Wildcard __{name}__ not found: put {name}.txt in one of the wildcards folders ({folders}).")
    with open(path, encoding="utf-8") as file:
        lines = [line.strip() for line in file]
    options = [line for line in lines if line and not line.startswith("#")]
    if not options:
        raise ValueError(f"Wildcard __{name}__ is empty: {path} has no lines to choose from.")
    return options
# Wildcard files signature (paths and modification times), so the node runs again when a wildcard file changes.
def wildcards_signature():
    entries = []
    for folder in folder_paths.get_folder_paths("wildcards"):
        for root, _dirs, files in os.walk(folder):
            entries += [(os.path.join(root, name), os.path.getmtime(os.path.join(root, name))) for name in files if name.endswith(".txt")]
    return hashlib.sha256(repr(sorted(entries)).encode()).hexdigest()
# Choice block parser for {a|b|{c|d}}, same syntax as the ComfyUI frontend dynamic prompts: returns the options and the position after the closing brace.
def parse_choice(text, i):
    options, choice, depth = [], "", 0
    while i < len(text):
        char = text[i]
        i += 1
        if char == "\\" and i < len(text):
            choice += char + text[i]
            i += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            if not depth:
                break
            depth -= 1
        elif char == "|" and not depth:
            options.append(choice)
            choice = ""
            continue
        choice += char
    options.append(choice)
    return options, i
# Prompt expansion: picks {a|b} choices, then replaces __name__ wildcards, expanding the picked text again so choices and wildcards can nest.
def expand(text, rng, depth=0):
    if depth > MAX_DEPTH:
        raise ValueError("Wildcards are nested too deep: check for wildcard files that include each other.")
    result, i = "", 0
    while i < len(text):
        char = text[i]
        i += 1
        if char == "\\" and i < len(text):
            result += char + text[i]
            i += 1
        elif char == "{":
            options, i = parse_choice(text, i)
            result += expand(rng.choice(options), rng, depth + 1)
        else:
            result += char
    return WILDCARD_PATTERN.sub(lambda match: expand(rng.choice(read_wildcard(match.group(1))), rng, depth + 1), result)
# Full prompt processing: strips // and /* */ comments like the frontend, expands choices and wildcards, then unescapes \{ \} \|.
def resolve_prompt(text, rng):
    text = re.sub(r"/\*[\s\S]*?\*/|//.*", "", text)
    return re.sub(r"\\([{}|])", r"\1", expand(text, rng))
# Node schema (V3 / Nodes 2.0) like CLIP Text Encode (Prompt), but with a positive prompt on top, a negative prompt below, and one conditioning output for each. Both prompts support {a|b} choices and __name__ wildcards, picked from the seed.
class CLIPTextEncodePositiveNegative(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="CLIPTextEncodePositiveNegative",
            display_name="CLIP Text Encode (Positive/Negative)",
            category="model/conditioning",
            description="Encodes a positive and a negative prompt with the same CLIP model, outputting a conditioning for each. Supports {a|b} choices and __name__ wildcards, picked from the seed.",
            search_aliases=["text", "prompt", "positive prompt", "negative prompt", "encode text", "text encoder", "encode prompt", "wildcards"],
            inputs=[
                io.String.Input(
                    "positive",
                    multiline=True,
                    tooltip="The positive prompt: what the image should contain. Supports {a|b} choices and __name__ wildcards.",
                ),
                io.String.Input(
                    "negative",
                    multiline=True,
                    tooltip="The negative prompt: what the image should avoid. Supports {a|b} choices and __name__ wildcards.",
                ),
                io.Clip.Input(
                    "clip",
                    tooltip="The CLIP model used for encoding both prompts.",
                ),
                io.Int.Input(
                    "seed",
                    default=0,
                    min=0,
                    max=0xFFFFFFFFFFFFFFFF,
                    control_after_generate=True,
                    tooltip="Seed for {a|b} choices and __name__ wildcards. The same seed always gives the same prompts.",
                    advanced=True,
                ),
            ],
            # Outputs for the node: positive and negative conditioning, then the prompts as encoded (with choices and wildcards filled in).
            outputs=[
                io.Conditioning.Output(display_name="positive", tooltip="Conditioning from the positive prompt."),
                io.Conditioning.Output(display_name="negative", tooltip="Conditioning from the negative prompt."),
                io.String.Output(display_name="positive_text", tooltip="The positive prompt as encoded, with choices and wildcards filled in."),
                io.String.Output(display_name="negative_text", tooltip="The negative prompt as encoded, with choices and wildcards filled in."),
            ],
        )
    # Method to run the node again when a wildcard file changes, even if the inputs are the same.
    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return wildcards_signature()
    # Encoding method, same as CLIP Text Encode (Prompt).
    @staticmethod
    def encode(clip, text):
        tokens = clip.tokenize(text)
        return clip.encode_from_tokens_scheduled(tokens)
    # Main method to fill in choices and wildcards from the seed, encode both prompts, and return the conditioning and the final prompts.
    @classmethod
    def execute(cls, positive, negative, clip, seed=0):
        if clip is None:
            raise RuntimeError("ERROR: clip input is invalid: None\n\nIf the clip is from a checkpoint loader node your checkpoint does not contain a valid clip or text encoder model.")
        rng = random.Random(seed) #Seed behavior for reproducible choices and wildcards.
        positive_text = resolve_prompt(positive, rng)
        negative_text = resolve_prompt(negative, rng)
        # Logging the prompts when choices or wildcards changed them, for debugging and verification purposes.
        if (positive_text, negative_text) != (positive, negative):
            print(f"[CLIP Text Encode] Seed: {seed} | Positive: {positive_text} | Negative: {negative_text}")
        return io.NodeOutput(cls.encode(clip, positive_text), cls.encode(clip, negative_text), positive_text, negative_text)
# Extension entry point for ComfyUI V3 node registration.
class CLIPTextEncodePositiveNegativeExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [CLIPTextEncodePositiveNegative]
async def comfy_entrypoint():
    return CLIPTextEncodePositiveNegativeExtension()
