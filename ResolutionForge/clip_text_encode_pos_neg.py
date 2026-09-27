import hashlib
import itertools
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
# (", " by default), and "2::a" gives an option weight 2 (1 by default). Returns the weighted options, the count range (None for a single pick) and the separator.
CHOICE_COUNT = re.compile(r"^\s*(\d+(?:-\d*)?|-\d+)\$\$(?:(.*?)\$\$)?(.*)$", re.S)
OPTION_WEIGHT = re.compile(r"^\s*(\d+(?:\.\d+)?)::(.*)$", re.S)
def parse_options(options):
    count_range, separator = None, ", "
    match = CHOICE_COUNT.match(options[0])
    if match:
        low, dash, high = match.group(1).partition("-")
        options = [match.group(3), *options[1:]]
        separator = match.group(2) if match.group(2) is not None else separator
        low = int(low or 0)
        high = (int(high) if high else len(options)) if dash else low
        count_range = (min(low, len(options)), min(max(low, high), len(options)))
    weighted = [(float(found.group(1)), found.group(2)) if (found := OPTION_WEIGHT.match(option)) else (1.0, option) for option in options]
    return weighted, count_range, separator
def pick_choices(options, picker):
    weighted, count_range, separator = parse_options(options)
    if count_range is None:
        return picker.pick(weighted, 1, all(weight == 1.0 for weight, _ in weighted)), separator
    return picker.pick_range(weighted, *count_range), separator
# Variables: "${name=value}" fills in value once (choices and wildcards included) and outputs nothing; "${name}" outputs that value anywhere in either prompt.
VARIABLE = re.compile(r"^\s*([A-Za-z_]\w*)\s*(?:=!?(.*))?$", re.S)
VARIABLE_USE = re.compile("\x00(\\w+)\x00") # Placeholder for "${name}", filled in after both prompts are expanded, so a variable can be used before it's set.
def parse_variable(text, i):
    options, end = parse_choice(text, i + 1)
    found = VARIABLE.match("|".join(options))
    return (found.group(1), found.group(2) and found.group(2).strip(), end) if found else None
def fill_variables(text, variables, depth=0):
    if depth > MAX_DEPTH:
        raise ValueError("Variables are nested too deep: check for variables that include each other.")
    def value(match):
        if match.group(1) not in variables:
            raise ValueError(f"Variable ${{{match.group(1)}}} is used but never set: add ${{{match.group(1)}=...}} to a prompt or a wildcard file.")
        return fill_variables(variables[match.group(1)], variables, depth + 1)
    return VARIABLE_USE.sub(value, text)
# Seed modes: how choices and wildcards are picked from one run to the next. Each picker returns the picked options, each with the picker to expand it with.
SEED_MODES = ["random", "deck", "shuffle", "balanced", "combinations", "mutate"]
class Picker:
    def pick_range(self, weighted, low, high):
        return self.pick(weighted, self.rng.randint(low, high), False) # Multi-pick: how many options, then which.
    def sub(self, text):
        return self # The picker to fill in a variable's value with.
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
class RandomPicker(Picker):
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
class DeckPicker(Picker):
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
class ShufflePicker(Picker):
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
class BalancedPicker(Picker):
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
# combinations: the seed numbers every combination of the options in both prompts (nested choices and wildcards included), so seeds 0, 1, 2... go
# through all of them once, then start over. The first choice changes fastest. Weights only matter as 0 (never); multi-picks count every set of options.
COMBINATION_LIMIT = 1000000 # Sets of options a multi-pick with varying options may list; more than this is an error instead of a long wait.
def count_combinations(text, memo, depth=0):
    if depth > MAX_DEPTH:
        raise ValueError("Wildcards are nested too deep: check for wildcard files that include each other.")
    if text not in memo:
        total, literal, i = 1, "", 0
        while i < len(text):
            char = text[i]
            i += 1
            if char == "\\" and i < len(text):
                literal += char + text[i]
                i += 1
            elif char == "{":
                options, i = parse_choice(text, i)
                weighted, count_range, _ = parse_options(options)
                total *= choice_combinations(weighted, count_range, memo, depth)
                literal += "\x01" # A choice breaks a wildcard name in two, as in expand().
            elif char == "$" and text.startswith("{", i) and (variable := parse_variable(text, i)):
                _name, value, i = variable
                total *= count_combinations(value, memo, depth + 1) if value is not None else 1
                literal += "\x01"
            else:
                literal += char
        for match in WILDCARD_PATTERN.finditer(literal):
            total *= sum(count_combinations(line, memo, depth + 1) for line in read_wildcard(match.group(1)))
        memo[text] = total
    return memo[text]
def option_combinations(weighted, memo, depth):
    return [(option, count_combinations(option, memo, depth + 1)) for weight, option in weighted if weight > 0]
def option_sets(options, low, high):
    for size in range(low, high + 1):
        for subset in itertools.combinations(options, size):
            yield subset, math.prod(combos for _, combos in subset)
def choice_combinations(weighted, count_range, memo, depth):
    options = option_combinations(weighted, memo, depth)
    if count_range is None:
        return sum(combos for _, combos in options) or 1
    high = min(count_range[1], len(options))
    low = min(count_range[0], high)
    sets = sum(math.comb(len(options), size) for size in range(low, high + 1))
    if all(combos == 1 for _, combos in options):
        return sets
    if sets > COMBINATION_LIMIT:
        raise ValueError(f"Too many combinations to list in a multi-pick of {len(options)} options with choices inside: use fewer options or a smaller count.")
    return sum(combos for _, combos in option_sets(options, low, high)) or 1
def unrank_set(rank, size, count):
    picked, start = [], 0
    for remaining in range(count, 0, -1):
        for index in range(start, size):
            block = math.comb(size - index - 1, remaining - 1)
            if rank < block:
                picked.append(index)
                start = index + 1
                break
            rank -= block
    return picked
class CombinationPicker(Picker):
    def __init__(self, index, memo, depth=0):
        self.index, self.memo, self.depth = index, memo, depth
    def take(self, combos):
        index, self.index = self.index % combos, self.index // combos # One digit of the seed per choice, in a mixed-radix number.
        return index
    def child(self, index):
        return CombinationPicker(index, self.memo, self.depth + 1)
    def pick(self, weighted, count, plain):
        options = option_combinations(weighted, self.memo, self.depth)
        index = self.take(sum(combos for _, combos in options) or 1)
        for option, combos in options:
            if index < combos:
                return [(option, self.child(index))]
            index -= combos
        return []
    def pick_range(self, weighted, low, high):
        options = option_combinations(weighted, self.memo, self.depth)
        high = min(high, len(options))
        low = min(low, high)
        index = self.take(choice_combinations(weighted, (low, high), self.memo, self.depth))
        if all(combos == 1 for _, combos in options):
            for size in range(low, high + 1):
                if index < math.comb(len(options), size):
                    return [(options[picked][0], self.child(0)) for picked in unrank_set(index, len(options), size)]
                index -= math.comb(len(options), size)
            return []
        for subset, combos in option_sets(options, low, high):
            if index < combos:
                picked = []
                for option, option_combos in subset:
                    picked.append((option, self.child(index % option_combos)))
                    index //= option_combos
                return picked
            index -= combos
        return []
    def sub(self, text):
        return self.child(self.take(count_combinations(text, self.memo, self.depth + 1)))
# mutate: the first run picks at random; every next run keeps the last prompt and changes just one choice (a different option), to explore variations
# of a good result. The node remembers the last picks for these prompts (until ComfyUI restarts), whatever the seed. Not reproducible.
MUTATE_TRACES = {}
class MutatePicker(Picker):
    def __init__(self, state, path=()):
        self.state, self.path, self.ordinal, self.rng = state, path, 0, state["rng"]
    def decide(self, weighted, fresh):
        address = self.path + (self.ordinal,) # Where this choice is: the choices and options above it, and its place among its siblings.
        self.ordinal += 1
        options = [option for weight, option in weighted if weight > 0]
        previous = self.state["last"].get(address, (None, 0))[0]
        if address != self.state["mutate"] and previous is not None and all(option in options for option in previous):
            picked = previous
        else:
            picked = fresh()
            for _ in range(20 if address == self.state["mutate"] else 0):
                if picked != previous:
                    break
                picked = fresh()
        self.state["now"][address] = (picked, len(options))
        return [(option, MutatePicker(self.state, address + (option,))) for option in picked]
    def pick(self, weighted, count, plain):
        return self.decide(weighted, lambda: [option for option, _ in RandomPicker(self.rng).pick(weighted, count, plain)])
    def pick_range(self, weighted, low, high):
        return self.decide(weighted, lambda: [option for option, _ in RandomPicker(self.rng).pick_range(weighted, low, high)])
# Comma cleanup after filling in: an empty option leaves "a, , b" or a trailing comma; this makes it "a, b".
def tidy_commas(text):
    text = re.sub(r"[ \t]*,(?:[ \t]*,)+", ",", text)
    text = re.sub(r"[ \t]+,", ",", text)
    text = re.sub(r"(^|\n)[ \t]*,[ \t]*", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r"^[\s,]+|[\s,]+$", "", text)
# Prompt expansion: picks {a|b} choices and sets ${name=value} variables, then replaces __name__ wildcards, expanding the picked text again so choices
# and wildcards can nest.
def expand(text, picker, depth, variables):
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
            result += separator.join(expand(option, child, depth + 1, variables) for option, child in picked)
        elif char == "$" and text.startswith("{", i) and (variable := parse_variable(text, i)):
            name, value, i = variable
            if value is None:
                result += f"\x00{name}\x00"
            else:
                variables[name] = expand(value, picker.sub(value), depth + 1, variables)
        else:
            result += char
    return WILDCARD_PATTERN.sub(lambda match: expand(*picker.pick([(1.0, line) for line in read_wildcard(match.group(1))], 1, True)[0], depth + 1, variables), result)
# Full prompt processing: strips // and /* */ comments like the frontend, expands choices and wildcards, fills in variables (shared by both prompts),
# unescapes \{ \} \|, then tidies commas.
def strip_comments(text):
    return re.sub(r"/\*[\s\S]*?\*/|//.*", "", text)
def resolve_prompts(prompts, picker):
    variables = {}
    expanded = [expand(strip_comments(text), picker, 0, variables) for text in prompts]
    return [tidy_commas(re.sub(r"\\([{}|])", r"\1", fill_variables(text, variables))) for text in expanded]
# Node schema (V3 / Nodes 2.0) like CLIP Text Encode (Prompt), but with a positive prompt on top, a negative prompt below, and one conditioning output for each. Both prompts support {a|b} choices and __name__ wildcards, picked from the seed.
REMEMBERING_MODES = ("shuffle", "balanced", "mutate")
class CLIPTextEncodePositiveNegative(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="CLIPTextEncodePositiveNegative",
            display_name="CLIP Dual Text Encode",
            category="model/conditioning",
            description="Encodes a positive and a negative prompt with the same CLIP model, outputting a conditioning for each. Supports {a|b} choices, __name__ wildcards and ${name} variables, picked from the seed.",
            search_aliases=["text", "prompt", "positive prompt", "negative prompt", "encode text", "text encoder", "encode prompt", "wildcards", "dynamic prompts"],
            inputs=[
                io.String.Input(
                    "positive",
                    multiline=True,
                    tooltip="The positive prompt: what the image should contain. Supports {a|b} choices, __name__ wildcards and ${name=value} / ${name} variables.",
                ),
                io.String.Input(
                    "negative",
                    multiline=True,
                    tooltip="The negative prompt: what the image should avoid. Supports {a|b} choices, __name__ wildcards and ${name=value} / ${name} variables.",
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
                    tooltip="Seed for {a|b} choices and __name__ wildcards. The same seed always gives the same prompts (except in shuffle, balanced and mutate modes).",
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
                    "balanced: an option just picked gets a low chance, and options not picked for a while get a higher one, so repeats are rare but possible. Remembered until ComfyUI restarts. Not reproducible.\n"
                    "combinations: the seed numbers every combination of the options, so seeds 0, 1, 2... go through all of them once (the console shows how many). Reproducible.\n"
                    "mutate: keeps the last prompt and changes just one choice each run, to explore variations of a good result. Remembered until ComfyUI restarts. Not reproducible.",
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
        return wildcards_signature(), os.urandom(8) if seed_mode in REMEMBERING_MODES else None # These modes give a new prompt every run, so it never uses the cache.
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
        note = ""
        if seed_mode == "combinations":
            memo = {}
            total = math.prod(count_combinations(strip_comments(text), memo) for text in (positive, negative))
            picker = CombinationPicker(seed % total, memo)
            note = f", combination {seed % total + 1} of {total}"
        elif seed_mode == "mutate":
            key = (positive, negative)
            last = MUTATE_TRACES.get(key, {})
            rng = random.Random()
            changeable = [address for address, (_picked, options) in last.items() if options > 1]
            state = {"rng": rng, "last": last, "now": {}, "mutate": rng.choice(changeable) if changeable else None}
            picker = MutatePicker(state)
        elif seed_mode == "shuffle":
            picker = ShufflePicker()
        elif seed_mode == "balanced":
            picker = BalancedPicker()
        elif seed_mode == "deck":
            picker = DeckPicker(random.Random(seed), seed, {})
        else:
            picker = RandomPicker(random.Random(seed)) # Seed behavior for reproducible choices and wildcards.
        positive_text, negative_text = resolve_prompts((positive, negative), picker)
        if seed_mode == "mutate":
            remember(MUTATE_TRACES, key, state["now"])
        # Logging the prompts when choices or wildcards changed them, for debugging and verification purposes.
        if (positive_text, negative_text) != (positive, negative):
            logging.info(f"[ResolutionForge] CLIP Dual Text Encode | Seed: {seed} ({seed_mode}{note}) | Positive: {positive_text} | Negative: {negative_text}")
        return io.NodeOutput(cls.encode(clip, positive_text), cls.encode(clip, negative_text))
# Extension entry point for ComfyUI V3 node registration.
class CLIPTextEncodePositiveNegativeExtension(ComfyExtension):
    @override
    async def get_node_list(self):
        return [CLIPTextEncodePositiveNegative]
async def comfy_entrypoint():
    return CLIPTextEncodePositiveNegativeExtension()
