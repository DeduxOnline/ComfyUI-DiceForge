import hashlib
import itertools
import json
import logging
import math
import os
import random
import re
import sqlite3
import threading
import time
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
    weighted, locked = [], []
    for option in options:
        lock = option.lstrip().startswith("!")
        option = option.lstrip()[1:] if lock else option
        found = OPTION_WEIGHT.match(option)
        weight, option = (float(found.group(1)), found.group(2)) if found else (1.0, option)
        if option.lstrip().startswith("!") and not lock:
            lock, option = True, option.lstrip()[1:] # "3::!a" works like "!3::a".
        weighted.append((weight, option))
        if lock:
            locked.append(option)
    return weighted, count_range, separator, locked
def pick_choices(options, picker):
    weighted, count_range, separator, locked = parse_options(options)
    plain = count_range is None and all(weight == 1.0 for weight, _ in weighted)
    if locked:
        return picker.lock(weighted, count_range, plain, locked), separator
    if count_range is None:
        return picker.pick(weighted, 1, plain), separator
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
    def lock(self, weighted, count_range, plain, locked):
        return [(option, self) for option in locked] # "{!a|b}": always the options marked with !, in every mode.
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
    def lock(self, weighted, count_range, plain, locked):
        self.pick(weighted, 1, plain) if count_range is None else self.pick_range(weighted, *count_range) # Same randomness as without the lock, so the other choices keep their picks for this seed.
        return super().lock(weighted, count_range, plain, locked)
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
    def lock(self, weighted, count_range, plain, locked):
        if count_range is not None:
            self.rng.randint(*count_range) # Same randomness as without the lock, for the multi-pick counts after it.
        return super().lock(weighted, count_range, plain, locked)
# Memory for shuffle, balanced and mutate: kept in a SQLite file in the ComfyUI user folder, so it survives restarts and doesn't fill up RAM (only the
# list being picked from is read). Delete the file to start over. The least recently used entries are forgotten past MEMORY_LIMIT.
MEMORY_FILE = os.path.join(folder_paths.get_user_directory(), "ResolutionForge", "seed_memory.sqlite")
MEMORY_LIMIT = 20000
class SeedMemory:
    def __init__(self, path):
        self.path, self.lock, self.connection, self.writes = path, threading.Lock(), None, 0
    def database(self):
        if self.connection is not None and not os.path.exists(self.path):
            self.connection.close() # The file was deleted to start over: make a new one.
            self.connection = None
        if self.connection is None:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self.connection = sqlite3.connect(self.path, check_same_thread=False)
            self.connection.execute("CREATE TABLE IF NOT EXISTS memory (mode TEXT, key TEXT, value TEXT, used REAL, PRIMARY KEY (mode, key))")
        return self.connection
    @staticmethod
    def key(*parts):
        return hashlib.sha256(repr(parts).encode()).hexdigest()
    def get(self, mode, key):
        with self.lock:
            row = self.database().execute("SELECT value FROM memory WHERE mode = ? AND key = ?", (mode, key)).fetchone()
        return json.loads(row[0]) if row else None
    def set(self, mode, key, value):
        with self.lock:
            self.database().execute("INSERT OR REPLACE INTO memory VALUES (?, ?, ?, ?)", (mode, key, json.dumps(value), time.time()))
            self.writes += 1
    def save(self):
        with self.lock:
            if self.connection is not None and self.writes:
                self.connection.execute("DELETE FROM memory WHERE rowid IN (SELECT rowid FROM memory ORDER BY used DESC LIMIT -1 OFFSET ?)", (MEMORY_LIMIT,))
                self.connection.commit() # Once per run, not per pick.
                self.writes = 0
MEMORY = SeedMemory(MEMORY_FILE)
# shuffle: like shuffle in a music player. The node remembers where it is in a shuffled order of the options and picks the next one, so every option
# comes once before any repeats, whatever the seed does. Not reproducible: the same seed gives a different prompt each run. The order is stored as
# the seed that shuffled it and a position, so even a long wildcard file takes a few bytes.
class ShufflePicker(Picker):
    def __init__(self):
        self.rng = random.Random()
    def pick(self, weighted, count, plain):
        cards = deck_cards(weighted)
        key = MEMORY.key(cards)
        state = MEMORY.get("shuffle", key) or {"order": None, "position": 0, "last": None, "previous": None, "pending": []}
        decks, picked, skipped = {}, [], []
        for _ in range(2 * len(cards)):
            if len(picked) == count:
                break
            if state["pending"]:
                card = state["pending"].pop(0)
            else:
                if state["order"] is None or state["position"] >= len(cards):
                    state.update(order=self.rng.getrandbits(63), position=0, previous=state["last"]) # New round.
                if state["order"] not in decks:
                    deck = list(cards)
                    random.Random(state["order"]).shuffle(deck)
                    decks[state["order"]] = avoid_first(deck, state["previous"])
                card = decks[state["order"]][state["position"]]
                state["position"] += 1
            state["last"] = card
            (skipped if card in picked else picked).append(card)
        state["pending"] = skipped + state["pending"] # Skipped duplicates of a multi-pick come first next time.
        if cards:
            MEMORY.set("shuffle", key, state)
        return [(card, self) for card in picked]
# balanced: like the pseudo-random distribution in games. Each option earns credit for every pick (its share of the weights) and spends 1 when picked;
# its chance is its weight x e^(5 x credit). An option just picked gets a low chance, one missed for a while a higher one, so repeats are rare but
# possible, nothing waits too long, and in the long run every option comes exactly as often as its weight says. The node remembers the credits
# (in the memory file), whatever the seed. Not reproducible: the same seed gives a different prompt each run.
BALANCE_STRENGTH = 5.0 # Higher: fewer repeats, less randomness.
class BalancedPicker(Picker):
    def __init__(self):
        self.rng = random.Random()
    def pick(self, weighted, count, plain):
        key = MEMORY.key(weighted)
        total = sum(weight for weight, _ in weighted) or 1
        credits = MEMORY.get("balanced", key) or [0.0] * len(weighted)
        candidates, picked = list(range(len(weighted))), []
        while candidates and len(picked) < count:
            weights = [weighted[index][0] * math.exp(BALANCE_STRENGTH * credits[index]) for index in candidates]
            if sum(weights) <= 0:
                break
            index = candidates.pop(self.rng.choices(range(len(candidates)), weights=weights)[0])
            picked.append(index)
            credits = [credit + weighted[option][0] / total - (option == index) for option, credit in enumerate(credits)]
        MEMORY.set("balanced", key, [round(credit, 6) for credit in credits])
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
                weighted, count_range, _, locked = parse_options(options)
                total *= math.prod(count_combinations(option, memo, depth + 1) for option in locked) if locked else choice_combinations(weighted, count_range, memo, depth)
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
    def lock(self, weighted, count_range, plain, locked):
        return [(option, self.sub(option)) for option in locked] # A locked choice counts once, so it doesn't repeat combinations.
# mutate: the first run picks at random; every next run keeps the last prompt and changes just one choice (a different option), to explore variations
# of a good result. The node remembers the last picks for these prompts (in the memory file), whatever the seed. Not reproducible.
class MutatePicker(Picker):
    def __init__(self, state, path=()):
        self.state, self.path, self.ordinal, self.rng = state, path, 0, state["rng"]
    def address(self):
        self.ordinal += 1
        return self.path + (self.ordinal - 1,) # Where this choice is: the choices and options above it, and its place among its siblings.
    def lock(self, weighted, count_range, plain, locked):
        address = self.address()
        self.state["now"][address] = (locked, 1) # Never the one to change.
        return [(option, MutatePicker(self.state, address + (option,))) for option in locked]
    def decide(self, weighted, fresh):
        address = self.address()
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
# unescapes \{ \} \| \!, then tidies commas.
def strip_comments(text):
    return re.sub(r"/\*[\s\S]*?\*/|//.*", "", text)
def resolve_prompts(prompts, picker):
    variables = {}
    expanded = [expand(strip_comments(text), picker, 0, variables) for text in prompts]
    return [tidy_commas(re.sub(r"\\([{}|!])", r"\1", fill_variables(text, variables))) for text in expanded]
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
                    "shuffle: like shuffle in a music player, the node remembers the options already used and picks from the rest, whatever the seed; remembered in a file, so it continues after a restart. Not reproducible.\n"
                    "balanced: an option just picked gets a low chance, and options not picked for a while get a higher one, so repeats are rare but possible. Remembered in a file, so it continues after a restart. Not reproducible.\n"
                    "combinations: the seed numbers every combination of the options, so seeds 0, 1, 2... go through all of them once (the console shows how many). Reproducible.\n"
                    "mutate: keeps the last prompt and changes just one choice each run, to explore variations of a good result. Remembered in a file, so it continues after a restart. Not reproducible.",
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
            key = MEMORY.key(positive, negative)
            last = {tuple(address): (picked, options) for address, picked, options in MEMORY.get("mutate", key) or []}
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
            MEMORY.set("mutate", key, [[list(address), picked, options] for address, (picked, options) in state["now"].items()])
        MEMORY.save()
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
