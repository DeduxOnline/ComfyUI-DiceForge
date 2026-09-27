import hashlib
import logging
import math
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
# Choice options with the sd-dynamic-prompts extras: "{2$$a|b|c}" picks 2 different options (also "1-3", "-2", "2-"), "{2$$ and $$a|b}" sets the separator
# (", " by default), and "2::a" gives an option weight 2 (1 by default). Returns the picked options and the separator.
CHOICE_COUNT = re.compile(r"^\s*(\d+(?:-\d*)?|-\d+)\$\$(?:(.*?)\$\$)?(.*)$", re.S)
OPTION_WEIGHT = re.compile(r"^\s*(\d+(?:\.\d+)?)::(.*)$", re.S)
def pick_choices(options, picker):
    rng, count, separator = picker.rng, 1, ", "
    match = CHOICE_COUNT.match(options[0])
    if match:
        low, dash, high = match.group(1).partition("-")
        options = [match.group(3), *options[1:]]
        separator = match.group(2) if match.group(2) is not None else separator
        low = int(low or 0)
        high = (int(high) if high else len(options)) if dash else low
        count = rng.randint(min(low, len(options)), min(max(low, high), len(options)))
    weighted = [(float(found.group(1)), found.group(2)) if (found := OPTION_WEIGHT.match(option)) else (1.0, option) for option in options]
    plain = count == 1 and not match and all(weight == 1.0 for weight, _ in weighted)
    return picker.pick(weighted, count, plain), separator
# Seed modes: how choices and wildcards are picked from one run to the next. Each picker returns the picked options, each with the picker to expand it with.
SEED_MODES = ["random", "deck", "shuffle", "balanced"]
def stable_seed(*parts):
    return int.from_bytes(hashlib.sha256(repr(parts).encode()).digest()[:8], "big") # Unlike hash(), the same in every ComfyUI run.
def deck_cards(weighted):
    return [option for weight, option in weighted for _ in range(max(1, round(weight)) if weight > 0 else 0)] # Weight = copies of the option in the deck.
def avoid_first(deck, last):
    if deck and deck[0] == last:
        swap = next((index for index in range(1, len(deck) - 1) if deck[index] != last), None) # Never the last card, so the next deck can still check it.
        if swap is not None:
            deck[0], deck[swap] = deck[swap], deck[0]
    return deck
# random: every pick independent, from the seed (the same pick as before seed modes existed, so saved seeds give the same prompt).
class RandomPicker:
    def __init__(self, rng):
        self.rng = rng
    def pick(self, weighted, count, plain):
        if plain:
            return [(self.rng.choice([option for _, option in weighted]), self)]
        weighted, picked = list(weighted), []
        while weighted and len(picked) < count and sum(weight for weight, _ in weighted) > 0:
            index = self.rng.choices(range(len(weighted)), weights=[weight for weight, _ in weighted])[0]
            picked.append((weighted.pop(index)[1], self)) # Picked without repeats.
        return picked
# deck: the seed is a position in a shuffled deck of the options, so with control after generate on increment every option comes once before any repeats,
# and a new shuffle each round, like dealing from a deck. Options inside a picked option move one step each time that option comes up. Fully reproducible from the seed.
class DeckPicker:
    def __init__(self, rng, position, draws):
        self.rng, self.position, self.draws = rng, position, draws
    @staticmethod
    def deck(cards, round_number):
        if len(cards) <= 2:
            round_number = 0 # Two options simply alternate.
        deck = list(cards)
        random.Random(stable_seed(cards, round_number)).shuffle(deck)
        if round_number:
            last = list(cards)
            random.Random(stable_seed(cards, round_number - 1)).shuffle(last)
            avoid_first(deck, last[-1]) # No repeat across the end of one round and the start of the next.
        return deck
    def pick(self, weighted, count, plain):
        cards = tuple(deck_cards(weighted))
        if not cards:
            return []
        key = (cards, self.position)
        position = self.position + self.draws.get(key, 0) # The same deck again in this run takes the next cards, so it doesn't repeat within the prompt.
        picked, seen = [], set()
        for _ in range(2 * len(cards)):
            if len(picked) == count:
                break
            round_number, index = divmod(position, len(cards))
            card = self.deck(cards, round_number)[index]
            position += 1
            if card not in seen:
                seen.add(card)
                picked.append((card, DeckPicker(self.rng, round_number, self.draws)))
        self.draws[key] = position - self.position
        return picked
# shuffle: like shuffle in a music player. The node remembers the options not used yet (until ComfyUI restarts) and picks from them, so every option comes once before any repeats,
# whatever the seed does. Not reproducible: the same seed gives a different prompt each run.
SHUFFLE_DECKS = {}
MEMORY_LIMIT = 1000 # Decks remembered at most (per mode); the oldest are forgotten first.
def remember(memory, key, value):
    memory.pop(key, None)
    memory[key] = value # Most recently used last.
    while len(memory) > MEMORY_LIMIT:
        memory.pop(next(iter(memory)))
class ShufflePicker:
    def __init__(self):
        self.rng = random.Random()
    def pick(self, weighted, count, plain):
        cards = deck_cards(weighted)
        key = tuple(cards)
        picked, skipped = [], []
        for _ in range(2 * len(cards)):
            if len(picked) == count:
                break
            deck, last = SHUFFLE_DECKS.pop(key, ([], None))
            if not deck:
                deck = list(cards)
                self.rng.shuffle(deck)
                avoid_first(deck, last)
            card = deck.pop(0)
            remember(SHUFFLE_DECKS, key, (deck, card))
            (skipped if card in picked else picked).append(card)
        if skipped:
            deck, last = SHUFFLE_DECKS[key]
            SHUFFLE_DECKS[key] = (skipped + deck, last) # Skipped duplicates of a multi-pick come first next time.
        return [(card, self) for card in picked]
# balanced: like the pseudo-random distribution in games. Each option earns credit for every pick (its share of the weights) and spends 1 when picked;
# its chance is its weight x e^(5 x credit). An option just picked gets a low chance, one missed for a while a higher one, so repeats are rare but
# possible, nothing waits too long, and in the long run every option comes exactly as often as its weight says. The node remembers the credits
# (until ComfyUI restarts), whatever the seed. Not reproducible: the same seed gives a different prompt each run.
BALANCED_CREDITS = {}
BALANCE_STRENGTH = 5.0 # Higher: fewer repeats, less randomness.
class BalancedPicker:
    def __init__(self):
        self.rng = random.Random()
    def pick(self, weighted, count, plain):
        key = tuple(weighted)
        total = sum(weight for weight, _ in weighted) or 1
        credits = list(BALANCED_CREDITS.get(key) or [0.0] * len(weighted))
        candidates, picked = list(range(len(weighted))), []
        while candidates and len(picked) < count:
            weights = [weighted[index][0] * math.exp(BALANCE_STRENGTH * credits[index]) for index in candidates]
            if sum(weights) <= 0:
                break
            index = candidates.pop(self.rng.choices(range(len(candidates)), weights=weights)[0])
            picked.append(index)
            credits = [credit + weighted[option][0] / total - (option == index) for option, credit in enumerate(credits)]
        remember(BALANCED_CREDITS, key, credits)
        return [(weighted[index][1], self) for index in picked]
# Comma cleanup after filling in: an empty option leaves "a, , b" or a trailing comma; this makes it "a, b".
def tidy_commas(text):
    text = re.sub(r"[ \t]*,(?:[ \t]*,)+", ",", text)
    text = re.sub(r"[ \t]+,", ",", text)
    text = re.sub(r"(^|\n)[ \t]*,[ \t]*", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r"^[\s,]+|[\s,]+$", "", text)
# Prompt expansion: picks {a|b} choices, then replaces __name__ wildcards, expanding the picked text again so choices and wildcards can nest.
def expand(text, picker, depth=0):
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
            picked, separator = pick_choices(options, picker)
            result += separator.join(expand(option, child, depth + 1) for option, child in picked)
        else:
            result += char
    return WILDCARD_PATTERN.sub(lambda match: expand(*picker.pick([(1.0, line) for line in read_wildcard(match.group(1))], 1, True)[0], depth + 1), result)
# Full prompt processing: strips // and /* */ comments like the frontend, expands choices and wildcards, unescapes \{ \} \|, then tidies commas.
def resolve_prompt(text, picker):
    text = re.sub(r"/\*[\s\S]*?\*/|//.*", "", text)
    return tidy_commas(re.sub(r"\\([{}|])", r"\1", expand(text, picker)))
# Node schema (V3 / Nodes 2.0) like CLIP Text Encode (Prompt), but with a positive prompt on top, a negative prompt below, and one conditioning output for each. Both prompts support {a|b} choices and __name__ wildcards, picked from the seed.
class CLIPTextEncodePositiveNegative(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="CLIPTextEncodePositiveNegative",
            display_name="CLIP Dual Text Encode",
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
                    tooltip="Seed for {a|b} choices and __name__ wildcards. The same seed always gives the same prompts (except in shuffle and balanced modes).",
                    advanced=True,
                ),
                io.Combo.Input(
                    "seed_mode",
                    options=SEED_MODES,
                    default="random",
                    tooltip="How choices and wildcards change from run to run.\n"
                    "random: every pick is independent, so the same option can come up again soon.\n"
                    "deck: the seed steps through a shuffled order of the options; with control after generate on increment, every option comes once before any repeats. Reproducible.\n"
                    "shuffle: like shuffle in a music player, the node remembers the options already used and picks from the rest, whatever the seed; resets when ComfyUI restarts. Not reproducible.\n"
                    "balanced: an option just picked gets a low chance, and options not picked for a while get a higher one, so repeats are rare but possible. Remembered until ComfyUI restarts. Not reproducible.",
                    advanced=True,
                ),
            ],
            # Outputs for the node: positive and negative conditioning, then the prompts as encoded (with choices and wildcards filled in).
            outputs=[
                io.Conditioning.Output(display_name="positive", tooltip="Conditioning from the positive prompt."),
                io.Conditioning.Output(display_name="negative", tooltip="Conditioning from the negative prompt."),
            ],
        )
    # Method to run the node again when a wildcard file changes, even if the inputs are the same.
    @classmethod
    def fingerprint_inputs(cls, seed_mode="random", **kwargs):
        return wildcards_signature(), os.urandom(8) if seed_mode in ("shuffle", "balanced") else None # shuffle and balanced give a new prompt every run, so it never uses the cache.
    # Encoding method, same as CLIP Text Encode (Prompt).
    @staticmethod
    def encode(clip, text):
        tokens = clip.tokenize(text)
        return clip.encode_from_tokens_scheduled(tokens)
    # Main method to fill in choices and wildcards from the seed, encode both prompts, and return the conditioning and the final prompts.
    @classmethod
    def execute(cls, positive, negative, clip, seed=0, seed_mode="random"):
        if clip is None:
            raise RuntimeError("ERROR: clip input is invalid: None\n\nIf the clip is from a checkpoint loader node your checkpoint does not contain a valid clip or text encoder model.")
        if seed_mode == "shuffle":
            picker = ShufflePicker()
        elif seed_mode == "balanced":
            picker = BalancedPicker()
        elif seed_mode == "deck":
            picker = DeckPicker(random.Random(seed), seed, {})
        else:
            picker = RandomPicker(random.Random(seed)) # Seed behavior for reproducible choices and wildcards.
        positive_text = resolve_prompt(positive, picker)
        negative_text = resolve_prompt(negative, picker)
        # Logging the prompts when choices or wildcards changed them, for debugging and verification purposes.
        if (positive_text, negative_text) != (positive, negative):
            logging.info(f"[ResolutionForge] CLIP Dual Text Encode | Seed: {seed} ({seed_mode}) | Positive: {positive_text} | Negative: {negative_text}")
        return io.NodeOutput(cls.encode(clip, positive_text), cls.encode(clip, negative_text))
# Extension entry point for ComfyUI V3 node registration.
class CLIPTextEncodePositiveNegativeExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [CLIPTextEncodePositiveNegative]
async def comfy_entrypoint():
    return CLIPTextEncodePositiveNegativeExtension()
